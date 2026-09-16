// TopologyNetworkPanel: 읽기 전용 행, 관리자 전용 provider 행의 노출 조건, 멤버 버튼 콜백.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import TopologyNetworkPanel from '../TopologyNetworkPanel.svelte';
import { makeFixture, makeTraffic } from './fixtures';

function renderPanel(networkId: string, showProvider: boolean, mutate?: (data: ReturnType<typeof makeFixture>) => void) {
	const data = makeFixture();
	mutate?.(data);
	const onSelectInstance = vi.fn();
	const onSelectRouter = vi.fn();
	const utils = render(TopologyNetworkPanel, {
		props: { networkId, data, traffic: makeTraffic(), showProvider, onSelectInstance, onSelectRouter },
	});
	return { ...utils, onSelectInstance, onSelectRouter };
}

describe('TopologyNetworkPanel', () => {
	afterEach(cleanup);

	it('사용자 화면에서는 provider 행을 렌더링하지 않는다', () => {
		renderPanel('net-web', false, (data) => {
			const web = data.networks.find((n) => n.id === 'net-web')!;
			web.provider_network_type = 'vxlan';
			web.provider_segmentation_id = 4011;
			web.provider_physical_network = null;
		});
		expect(screen.getByRole('heading', { name: 'web-net' })).toBeTruthy();
		expect(screen.getByText('읽기 전용')).toBeTruthy();
		expect(screen.getByText('내부 네트워크')).toBeTruthy();
		expect(screen.getByText('10.10.1.0/24', { selector: 'dd' })).toBeTruthy();
		expect(screen.getByText('1450', { selector: 'dd' })).toBeTruthy();
		expect(screen.getByText(/^▼ 5\.8M\s+▲ 2\.0M$/)).toBeTruthy();
		expect(screen.queryByText('네트워크 타입')).toBeNull();
		expect(screen.queryByText('VXLAN VNI')).toBeNull();
		expect(screen.queryByText('물리 네트워크')).toBeNull();
		expect(screen.queryByText('관리자')).toBeNull();
	});

	it('showProvider 이면 네트워크 타입·세그먼트·물리 네트워크 행을 관리자 pill 과 함께 보여준다', () => {
		renderPanel('net-pub', true, (data) => {
			const pub = data.networks.find((n) => n.id === 'net-pub')!;
			pub.provider_network_type = 'vlan';
			pub.provider_segmentation_id = 120;
			pub.provider_physical_network = 'physnet1';
		});
		expect(screen.getByText('네트워크 타입')).toBeTruthy();
		expect(screen.getByText('vlan')).toBeTruthy();
		expect(screen.getByText('VLAN 태그')).toBeTruthy();
		expect(screen.getByText('120')).toBeTruthy();
		expect(screen.getByText('물리 네트워크')).toBeTruthy();
		expect(screen.getByText('physnet1')).toBeTruthy();
		expect(screen.getAllByText('관리자')).toHaveLength(3);
		expect(screen.getByText('외부 네트워크')).toBeTruthy();
	});

	it('격리 네트워크는 격리 표시와 안내문을 보여주고 라우터가 없다', () => {
		renderPanel('net-lab', false);
		expect(screen.getByText('내부 네트워크 · 격리 (라우터 없음)')).toBeTruthy();
		expect(screen.getByText(/다른 네트워크와 통신할 수 없습니다/)).toBeTruthy();
		expect(screen.getByText('연결된 라우터 없음')).toBeTruthy();
	});

	it('서브넷 표와 멤버(인스턴스·라우터) 버튼을 렌더링하고 콜백을 호출한다', async () => {
		const { onSelectInstance, onSelectRouter } = renderPanel('net-web', false);
		expect(screen.getByRole('columnheader', { name: 'CIDR' })).toBeTruthy();
		expect(screen.getByRole('cell', { name: 'web-net-subnet' })).toBeTruthy();
		// web-net NIC 보유 인스턴스: web-01, web-02, web-03, db-01(eth2), bastion-01(eth1)
		const web01 = screen.getByRole('button', { name: /^web-01/ });
		const db01 = screen.getByRole('button', { name: /^db-01/ });
		expect(web01).toBeTruthy();
		expect(db01).toBeTruthy();
		expect(screen.queryByRole('button', { name: /^app-01/ })).toBeNull();
		await fireEvent.click(web01);
		expect(onSelectInstance).toHaveBeenCalledWith('vm-web-01');
		const router = screen.getByRole('button', { name: /^edge-router/ });
		await fireEvent.click(router);
		expect(onSelectRouter).toHaveBeenCalledWith('rtr-edge');
		expect(screen.queryByRole('button', { name: /^transit-router/ })).toBeNull();
	});

	it('자체 닫기 버튼을 그리지 않는다 — SlidePanel 이 이미 제공한다', () => {
		// 자식이 × 를 또 그리면 헤더에 닫기 버튼이 두 개 보인다(사용자 신고 버그).
		renderPanel('net-web', true);
		const closers = screen.queryAllByRole('button', { name: /닫기|close/i });
		expect(closers).toEqual([]);
		expect([...document.querySelectorAll('button')].filter((b) => b.textContent?.trim() === '×')).toEqual([]);
	});

	it('같은 상태 값을 한 화면에 두 번 보여주지 않는다', () => {
		// 헤더 StatusChip 과 본문 "상태" 행이 같은 값을 동시에 보여주던 중복을 막는다.
		renderPanel('net-web', true);
		expect(screen.getAllByText('ACTIVE')).toHaveLength(1);
	});

	it('응답에 없는 네트워크 id 는 안내문만 보여준다', () => {
		renderPanel('net-missing', true);
		expect(screen.getByText('현재 토폴로지 응답에 없는 네트워크입니다.')).toBeTruthy();
		expect(screen.queryByText('네트워크 타입')).toBeNull();
	});
});

// ── 사용량 추이 (`loadHistory`) ───────────────────────────────────────────────

import type { TopologyTrafficHistory } from '$lib/types/topology';

function makeHistory(over: Partial<TopologyTrafficHistory> = {}): TopologyTrafficHistory {
	return {
		network_id: 'net-web',
		range: '15m',
		step_s: 15,
		window: '30s',
		series: [
			{ ts: 100, rx_bps: 1_000_000, tx_bps: 500_000 },
			{ ts: 115, rx_bps: 3_000_000, tx_bps: 1_000_000 },
		],
		stats: {
			avg: { rx_bps: 2_000_000, tx_bps: 750_000 },
			max: { rx_bps: 3_000_000, tx_bps: 1_000_000 },
			latest: { rx_bps: 3_000_000, tx_bps: 1_000_000 },
		},
		_meta: { source: 'network_nic_sum', router_traffic: 'exporter_required' },
		...over,
	};
}

describe('TopologyNetworkPanel 사용량 추이', () => {
	afterEach(cleanup);

	it('loadHistory 가 없으면 섹션 자체를 렌더링하지 않는다', () => {
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false },
		});
		expect(screen.queryByText('사용량 추이')).toBeNull();
	});

	it('series 를 스파크라인과 평균·최대·최근 통계로 보여준다', async () => {
		const loadHistory = vi.fn().mockResolvedValue(makeHistory());
		const { container } = render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(screen.getByText('최근 15분')).toBeTruthy());

		expect(loadHistory).toHaveBeenCalledWith('net-web', '15m');
		// rx/tx 두 선이 같은 축에 올라간다
		expect(container.querySelectorAll('polyline')).toHaveLength(2);
		// 위 `합산 트래픽` 행과 같은 방향별 표기여야 대조가 된다
		expect(screen.getByText('평균')).toBeTruthy();
		expect(screen.getByText(/^▼ 2\.0M\s+▲ 750k$/)).toBeTruthy();
		expect(screen.getByText('최대')).toBeTruthy();
		expect(screen.getByText('최근')).toBeTruthy();
		expect(screen.getAllByText(/^▼ 3\.0M\s+▲ 1\.0M$/)).toHaveLength(2);
		// 색만으로 rx/tx 를 구분하지 않는다
		expect(screen.getByText('▼ 수신')).toBeTruthy();
		expect(screen.getByText('▲ 송신')).toBeTruthy();
	});

	it('구간 토글로 30분·1시간을 고를 수 있다 (API 만 지원하고 UI 에 없으면 쓸 수 없는 기능이다)', async () => {
		const loadHistory = vi.fn().mockResolvedValue(makeHistory());
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(loadHistory).toHaveBeenCalledWith('net-web', '15m'));

		// 백엔드 `_HISTORY_RANGES` 의 세 구간이 모두 노출돼야 한다
		const group = screen.getByRole('group', { name: '사용량 추이 구간' });
		expect([...group.querySelectorAll('button')].map((b) => b.textContent?.trim())).toEqual(['15분', '30분', '1시간']);

		await fireEvent.click(screen.getByRole('button', { name: '1시간' }));
		await vi.waitFor(() => expect(loadHistory).toHaveBeenLastCalledWith('net-web', '1h'));
	});

	it('같은 구간을 다시 눌러도 재조회하지 않는다', async () => {
		const loadHistory = vi.fn().mockResolvedValue(makeHistory());
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(loadHistory).toHaveBeenCalledTimes(1));

		await fireEvent.click(screen.getByRole('button', { name: '15분' }));
		await fireEvent.click(screen.getByRole('button', { name: '15분' }));
		expect(loadHistory).toHaveBeenCalledTimes(1);
	});

	it('스파크라인은 축 상한을 별도 숫자로 내보내지 않는다', async () => {
		// 축 상한은 통계의 `최대` 가 이미 말한다. 같은 값을 다른 라벨("최고")로 한 번 더 쓰면
		// 두 숫자가 다른 의미인지 사용자가 판단할 수 없다.
		const loadHistory = vi.fn().mockResolvedValue(makeHistory());
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(screen.getByText('최대')).toBeTruthy());
		// "최고 5.2Mbps" 처럼 숫자를 동반한 별도 최고값이 없어야 한다
		// (캡션의 "방향별 최고값" 같은 설명 문구는 허용).
		expect(screen.queryByText(/최고\s*[\d.]/)).toBeNull();
	});

	it('통계를 rx+tx 합계 하나로 내보내지 않는다', async () => {
		// 합계(4.0M)로 두면 위 `합산 트래픽`(▼ ▲ 방향별)과 대조할 수 없는 세 번째 숫자가 된다.
		const loadHistory = vi.fn().mockResolvedValue(makeHistory());
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(screen.getByText('최대')).toBeTruthy());
		expect(screen.queryByText('4.0Mbps')).toBeNull();
		expect(screen.queryByText(/^4\.0M$/)).toBeNull();
	});

	it('999bps 미만도 `500bbps` 같은 접미사 중복 없이 표기한다', async () => {
		// formatBps 가 0<bps<1000 에서 이미 `b` 를 붙인다 — 호출부가 `bps` 를 또 붙이면 `500bbps` 가 된다.
		const loadHistory = vi.fn().mockResolvedValue(
			makeHistory({
				series: [{ ts: 100, rx_bps: 500, tx_bps: 73 }],
				stats: {
					avg: { rx_bps: 500, tx_bps: 73 },
					max: { rx_bps: 500, tx_bps: 73 },
					latest: { rx_bps: 500, tx_bps: 73 },
				},
			}),
		);
		const { container } = render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(screen.getByText('최대')).toBeTruthy());
		expect(container.textContent).not.toMatch(/bbps|bbits|bb/);
		expect(screen.getAllByText(/^▼ 500b\s+▲ 73b$/).length).toBeGreaterThan(0);
	});

	it('표본 시각을 밝힌다 (합산 트래픽은 폴링, 이 섹션은 열 때 1회)', async () => {
		const ts = Math.floor(Date.parse('2026-09-11T04:05:00Z') / 1000);
		const d = new Date(ts * 1000);
		const hhmm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
		const loadHistory = vi.fn().mockResolvedValue(
			makeHistory({ series: [{ ts, rx_bps: 1_000_000, tx_bps: 0 }] }),
		);
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(screen.getByText(new RegExp(`${hhmm} 기준`))).toBeTruthy());
	});

	it('라우터↔스위치가 아니라 NIC 합산임을 캡션으로 밝힌다', async () => {
		const loadHistory = vi.fn().mockResolvedValue(makeHistory());
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(screen.getByText(/네트워크 합산/)).toBeTruthy());
		expect(screen.getByText(/라우터↔스위치 트래픽이 아니다/)).toBeTruthy();
		expect(screen.getByText(/최대는 방향별 최고값/)).toBeTruthy();
	});

	it('표본이 없으면 0 이 아니라 없다고 말한다', async () => {
		const loadHistory = vi.fn().mockResolvedValue(
			makeHistory({ series: [], stats: { avg: null, max: null, latest: null } }),
		);
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(screen.getByText('표시할 사용량 표본이 없습니다.')).toBeTruthy());
		expect(screen.queryByText('0bps')).toBeNull();
		expect(screen.queryByText('평균')).toBeNull();
	});

	it('조회 실패는 패널을 깨지 않고 안내문만 남긴다', async () => {
		const loadHistory = vi.fn().mockRejectedValue(new Error('503'));
		render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data: makeFixture(), traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(screen.getByText('사용량 추이를 불러오지 못했습니다.')).toBeTruthy());
		// 나머지 상세는 그대로 보인다
		expect(screen.getByRole('heading', { name: 'web-net' })).toBeTruthy();
	});

	it('traffic 이 갱신돼도 재조회하지 않는다 (패널 열 때 1회)', async () => {
		const loadHistory = vi.fn().mockResolvedValue(makeHistory());
		const data = makeFixture();
		const { rerender } = render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data, traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(loadHistory).toHaveBeenCalledTimes(1));

		// 트래픽 폴링은 15초마다 부모를 리렌더한다 — 그때마다 Prometheus 를 치면 안 된다.
		const bumped = makeTraffic();
		bumped.networks['net-web'] = { rx_bps: 9_000_000, tx_bps: 9_000_000 };
		await rerender({ networkId: 'net-web', data, traffic: bumped, showProvider: false, loadHistory });
		await rerender({ networkId: 'net-web', data, traffic: bumped, showProvider: false, loadHistory: vi.fn() });
		expect(loadHistory).toHaveBeenCalledTimes(1);
	});

	it('다른 네트워크를 선택하면 그 네트워크로 다시 조회한다', async () => {
		const loadHistory = vi.fn().mockResolvedValue(makeHistory());
		const data = makeFixture();
		const { rerender } = render(TopologyNetworkPanel, {
			props: { networkId: 'net-web', data, traffic: makeTraffic(), showProvider: false, loadHistory },
		});
		await vi.waitFor(() => expect(loadHistory).toHaveBeenCalledTimes(1));

		await rerender({ networkId: 'net-app', data, traffic: makeTraffic(), showProvider: false, loadHistory });
		await vi.waitFor(() => expect(loadHistory).toHaveBeenCalledTimes(2));
		expect(loadHistory).toHaveBeenLastCalledWith('net-app', '15m');
	});
});
