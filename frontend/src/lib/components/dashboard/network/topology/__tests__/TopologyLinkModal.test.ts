import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import TopologyLinkModal from '../TopologyLinkModal.svelte';
import type { TopologyNetwork } from '$lib/types/topology';

const mockTenantNet: TopologyNetwork = {
	id: 'net-app',
	name: 'app-net',
	status: 'ACTIVE',
	is_external: false,
	is_shared: false,
	project_id: 'proj-1',
	mtu: 1450,
	subnet_details: [
		{ id: 'sub-1', name: 'app-sub-1', cidr: '10.10.1.0/24', gateway_ip: '10.10.1.1', dhcp_enabled: true },
		{ id: 'sub-2', name: 'app-sub-2', cidr: '10.10.2.0/24', gateway_ip: '10.10.2.1', dhcp_enabled: true },
	],
};

const mockExternalNet: TopologyNetwork = {
	id: 'net-pub',
	name: 'public',
	status: 'ACTIVE',
	is_external: true,
	is_shared: true,
	project_id: null,
	mtu: 1500,
	subnet_details: [
		{ id: 'sub-pub', name: 'pub-sub', cidr: '203.0.113.0/24', gateway_ip: '203.0.113.1', dhcp_enabled: false },
	],
};

describe('TopologyLinkModal', () => {
	it('vm-net 연결 시 인스턴스-네트워크 프리뷰와 NIC 설명 및 연결 확인을 수행한다', async () => {
		const onConfirm = vi.fn();
		const onClose = vi.fn();

		render(TopologyLinkModal, {
			props: {
				open: true,
				request: {
					kind: 'vm-net',
					instanceId: 'vm-1',
					instanceName: 'web-server-01',
					networkId: 'net-app',
					networkName: 'app-net',
				},
				network: mockTenantNet,
				onConfirm,
				onClose,
			},
		});

		expect(screen.getByText('컴포넌트 연결 확인')).not.toBeNull();
		expect(screen.getAllByText('web-server-01').length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('app-net').length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText(/새 가상 네트워크 인터페이스\(NIC\)를 생성하여/)).not.toBeNull();

		const submitBtn = screen.getByRole('button', { name: '연결하기' });
		await fireEvent.click(submitBtn);

		expect(onConfirm).toHaveBeenCalledTimes(1);
		expect(onConfirm).toHaveBeenCalledWith({ kind: 'vm-net' });
	});

	it('router-gateway 연결 시 라우터-외부망 프리뷰와 외부 게이트웨이 설명을 표시한다', async () => {
		const onConfirm = vi.fn();

		render(TopologyLinkModal, {
			props: {
				open: true,
				request: {
					kind: 'router-gateway',
					routerId: 'rtr-1',
					routerName: 'edge-router',
					networkId: 'net-pub',
					networkName: 'public',
				},
				network: mockExternalNet,
				onConfirm,
				onClose: vi.fn(),
			},
		});

		expect(screen.getAllByText('edge-router').length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('public').length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText(/외부 게이트웨이\(Default Route\)를/)).not.toBeNull();

		const submitBtn = screen.getByRole('button', { name: '연결하기' });
		await fireEvent.click(submitBtn);

		expect(onConfirm).toHaveBeenCalledWith({ kind: 'router-gateway' });
	});

	it('router-net 연결 시 서브넷이 여러 개인 경우 선택 드롭다운을 제공한다', async () => {
		const onConfirm = vi.fn();

		render(TopologyLinkModal, {
			props: {
				open: true,
				request: {
					kind: 'router-net',
					routerId: 'rtr-1',
					routerName: 'edge-router',
					networkId: 'net-app',
					networkName: 'app-net',
				},
				network: mockTenantNet,
				subnets: mockTenantNet.subnet_details,
				onConfirm,
				onClose: vi.fn(),
			},
		});

		const select = screen.getByRole('combobox');
		expect(select).not.toBeNull();

		// 두 번째 서브넷 선택
		await fireEvent.change(select, { target: { value: 'sub-2' } });

		const submitBtn = screen.getByRole('button', { name: '연결하기' });
		await fireEvent.click(submitBtn);

		expect(onConfirm).toHaveBeenCalledWith({ kind: 'router-net', subnetId: 'sub-2' });
	});

	it('router-net 연결 시 서브넷이 0개인 경우 서브넷 생성 입력을 제공한다', async () => {
		const onConfirm = vi.fn();

		const emptyNet: TopologyNetwork = {
			...mockTenantNet,
			subnet_details: [],
		};

		render(TopologyLinkModal, {
			props: {
				open: true,
				request: {
					kind: 'router-net',
					routerId: 'rtr-1',
					routerName: 'edge-router',
					networkId: 'net-app',
					networkName: 'app-net',
				},
				network: emptyNet,
				subnets: [],
				onConfirm,
				onClose: vi.fn(),
			},
		});

		expect(screen.getByText(/새 서브넷을 생성한 후/)).not.toBeNull();

		const cidrInput = screen.getByPlaceholderText('10.0.0.0/24');
		await fireEvent.input(cidrInput, { target: { value: '10.50.0.0/24' } });

		const submitBtn = screen.getByRole('button', { name: '연결하기' });
		await fireEvent.click(submitBtn);

		expect(onConfirm).toHaveBeenCalledWith({
			kind: 'router-net',
			create: {
				name: 'app-net-subnet',
				cidr: '10.50.0.0/24',
				dhcp: true,
			},
		});
	});

	it('취소 버튼 클릭 시 onClose 콜백을 호출한다', async () => {
		const onClose = vi.fn();

		render(TopologyLinkModal, {
			props: {
				open: true,
				request: {
					kind: 'vm-net',
					instanceId: 'vm-1',
					instanceName: 'web-server-01',
					networkId: 'net-app',
					networkName: 'app-net',
				},
				network: mockTenantNet,
				onConfirm: vi.fn(),
				onClose,
			},
		});

		const cancelBtn = screen.getByRole('button', { name: '취소' });
		await fireEvent.click(cancelBtn);

		expect(onClose).toHaveBeenCalledTimes(1);
	});

	it('createdSubnet 전달 시 생성 입력 대신 재시도 안내를 표시하고 router-net subnetId 페이로드를 전달한다', async () => {
		const onConfirm = vi.fn();

		render(TopologyLinkModal, {
			props: {
				open: true,
				request: {
					kind: 'router-net',
					routerId: 'rtr-1',
					routerName: 'edge-router',
					networkId: 'net-app',
					networkName: 'app-net',
				},
				network: mockTenantNet,
				subnets: [],
				createdSubnet: {
					id: 'sub-created-1',
					name: 'already-created-sub',
					cidr: '10.99.0.0/24',
					gateway_ip: '10.99.0.1',
					dhcp_enabled: true,
				},
				onConfirm,
				onClose: vi.fn(),
			},
		});

		expect(screen.getByText('생성 완료된 서브넷')).not.toBeNull();
		expect(screen.getByText('already-created-sub')).not.toBeNull();
		expect(screen.getByText(/서브넷 생성이 완료되었습니다\. 라우터 게이트웨이 인터페이스 연결만 재시도합니다\./)).not.toBeNull();

		const retryBtn = screen.getByRole('button', { name: '라우터 연결 재시도' });
		await fireEvent.click(retryBtn);

		expect(onConfirm).toHaveBeenCalledTimes(1);
		expect(onConfirm).toHaveBeenCalledWith({
			kind: 'router-net',
			subnetId: 'sub-created-1',
		});
	});
});
