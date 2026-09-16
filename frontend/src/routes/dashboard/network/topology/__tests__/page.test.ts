import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TopologyData } from '$lib/types/topology';

const { mocks, toastMock } = vi.hoisted(() => ({
	mocks: { get: vi.fn(), post: vi.fn(), prefetch: vi.fn() },
	toastMock: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {
		status: number;
		constructor(status: number, message: string) {
			super(message);
			this.status = status;
		}
	},
	api: mocks,
}));
vi.mock('$lib/stores/toast', () => ({ toast: toastMock }));
vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe: (fn: (val: { token: string; projectId: string; isSystemAdmin: boolean }) => void) => {
			fn({ token: 'test-token', projectId: 'project-1', isSystemAdmin: false });
			return () => {};
		},
	},
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
import { ApiError } from '$lib/api/client';
import Page from '../+page.svelte';

const testTopologyData: TopologyData = {
	networks: [
		{
			id: 'net-empty',
			name: 'empty-net',
			status: 'ACTIVE',
			is_external: false,
			is_shared: false,
			project_id: 'project-1',
			mtu: 1450,
			subnet_details: [],
		},
	],
	routers: [
		{
			id: 'rtr-1',
			name: 'my-router',
			status: 'ACTIVE',
			external_gateway_network_id: null,
			external_gateway_ips: [],
			interface_ips: [],
			is_distributed: false,
			is_ha: false,
			connected_subnet_ids: [],
			dvr_subnet_ids: [],
			project_id: 'project-1',
			enable_snat: false,
			routes: [],
		},
	],
	instances: [],
	floating_ips: [],
	load_balancers: [],
};

describe('Topology page cable connect flow', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.get.mockImplementation(async (url: string) => {
			if (url === '/api/v1/networks/topology') return testTopologyData;
			if (url === '/api/v1/networks/topology/traffic') return { networks: {}, instances: {}, load_balancers: {} };
			return {};
		});
	});

	it('서브넷 생성 성공 후 라우터 연결 실패 시, 재시도 시 서브넷을 중복 생성하지 않고 라우터 연결만 1회 추가 호출한다', async () => {

		// 1단계: 서브넷 생성은 성공, 라우터 연결은 첫 시도에 500 오류로 실패하도록 설정
		mocks.post.mockImplementation(async (url: string) => {
			if (url === '/api/v1/networks/net-empty/subnets') {
				return {
					id: 'sub-new-1',
					name: 'empty-net-subnet',
					cidr: '10.88.0.0/24',
					gateway_ip: null,
					dhcp_enabled: true,
				};
			}
			if (url === '/api/v1/routers/rtr-1/interfaces') {
				throw new ApiError(500, 'Router interface attachment timed out');
			}
			return {};
		});

		render(Page);

		// 토폴로지 데이터 로드 대기
		await waitFor(() => {
			expect(screen.getByText('empty-net')).not.toBeNull();
		});

		// 캔버스 노드 카드에서 핸들 드래그 시뮬레이션
		const routerCard = document.querySelector('button[data-node-id="rtr-1"]')!;
		const handle = routerCard.querySelector('[data-link-handle]')!;
		const targetSw = document.querySelector('button[data-node-id="sw:net-empty"]')!;

		// 드래그 앤 드롭: rtr-1 -> sw:net-empty
		const downEv = new MouseEvent('pointerdown', { bubbles: true, cancelable: true, button: 0 });
		Object.defineProperty(downEv, 'pointerId', { value: 1 });
		Object.defineProperty(downEv, 'pointerType', { value: 'mouse' });
		handle.dispatchEvent(downEv);
		const moveEv = new MouseEvent('pointermove', { bubbles: true, cancelable: true });
		Object.defineProperty(moveEv, 'pointerId', { value: 1 });
		Object.defineProperty(moveEv, 'pointerType', { value: 'mouse' });
		targetSw.dispatchEvent(moveEv);

		const upEv = new MouseEvent('pointerup', { bubbles: true, cancelable: true, button: 0 });
		Object.defineProperty(upEv, 'pointerId', { value: 1 });
		Object.defineProperty(upEv, 'pointerType', { value: 'mouse' });
		targetSw.dispatchEvent(upEv);

		// 확인 모달 열림 확인
		await waitFor(() => {
			expect(screen.getByText('컴포넌트 연결 확인')).not.toBeNull();
			expect(screen.getByText(/이 네트워크에는 활성 서브넷이 없습니다/)).not.toBeNull();
		});

		// CIDR 입력 후 1차 제출
		const cidrInput = screen.getByPlaceholderText('10.0.0.0/24');
		await fireEvent.input(cidrInput, { target: { value: '10.88.0.0/24' } });

		const submitBtn = screen.getByRole('button', { name: '연결하기' });
		await fireEvent.click(submitBtn);

		// 1차 시도 결과 검증:
		// - 서브넷 생성 POST 1회 호출됨
		// - 라우터 인터페이스 연결 POST 1회 호출됨 (오류 발생)
		// - toast.warning 경고 노출
		// - 모달이 닫히지 않고 "라우터 연결 재시도" 상태로 전환됨
		await waitFor(() => {
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/networks/net-empty/subnets',
				expect.objectContaining({ cidr: '10.88.0.0/24' }),
				'test-token',
				'project-1'
			);
			expect(mocks.post).toHaveBeenCalledWith(
				'/api/v1/routers/rtr-1/interfaces',
				{ subnet_id: 'sub-new-1', auto_gateway: true },
				'test-token',
				'project-1'
			);
			expect(toastMock.warning).toHaveBeenCalledWith(
				expect.stringContaining('서브넷은 생성되었으나 라우터 인터페이스 연결에 실패했습니다')
			);
			expect(screen.getByText('생성 완료된 서브넷')).not.toBeNull();
			expect(screen.getByText('생성 완료된 서브넷')).not.toBeNull();
			expect(screen.getAllByText('10.88.0.0/24').length).toBeGreaterThanOrEqual(1);
		});

		// 2단계: 라우터 연결 재시도 성공으로 mock 동작 변경
		mocks.post.mockImplementation(async (url: string) => {
			if (url === '/api/v1/routers/rtr-1/interfaces') {
				return { subnet_id: 'sub-new-1', port_id: 'port-1' };
			}
			return {};
		});

		// 재시도 버튼 클릭
		const retryBtn = screen.getByRole('button', { name: '라우터 연결 재시도' });
		await fireEvent.click(retryBtn);

		// 2차 시도 결과 검증:
		// - 서브넷 생성 POST는 여전히 총 1회만 호출됨 (중복 생성 방지)
		// - 라우터 인터페이스 POST는 총 2회 호출됨 (1차 실패 + 2차 재시도)
		// - 토폴로지 새로고침 및 성공 토스트 노출
		await waitFor(() => {
			const subnetPostCalls = mocks.post.mock.calls.filter((call) => call[0] === '/api/v1/networks/net-empty/subnets');
			const routerPostCalls = mocks.post.mock.calls.filter((call) => call[0] === '/api/v1/routers/rtr-1/interfaces');

			expect(subnetPostCalls).toHaveLength(1);
			expect(routerPostCalls).toHaveLength(2);
			expect(toastMock.success).toHaveBeenCalledWith('my-router 를 empty-net 의 게이트웨이로 연결했습니다.');
			expect(screen.queryByText('컴포넌트 연결 확인')).toBeNull();
		});
	});
});
