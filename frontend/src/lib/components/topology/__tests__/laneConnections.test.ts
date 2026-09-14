// 레인 뷰 연결선 강도 계약. 캔버스와 같은 `edgeIntensity` 를 쓰되
// **계측 없음(undefined)을 0 으로 뭉개지 않는다** — 0 bps 는 "쟀더니 0" 이라 다른 값이다.
import { describe, expect, it } from 'vitest';
import { P, makeFixture, makeTraffic } from '../canvas/__tests__/fixtures';
import { createTopologyDerivedController } from '../topologyDerivedController.svelte';
import { edgeIntensity, NO_TELEMETRY_STYLE } from '../topologyHelpers';
import type { TopologyTraffic } from '$lib/types/topology';

function controller(traffic: TopologyTraffic | null) {
	return createTopologyDerivedController({
		data: () => makeFixture(),
		projectId: () => P,
		showAll: () => false,
		traffic: () => traffic,
		selectedId: () => null,
		hoveredId: () => null,
		anchors: () => new Map(),
		sidebarHeight: () => 600,
		searchTerm: () => '',
	});
}

/** 인스턴스 행의 연결선(= floating 이 아닌 것)만 고른다. floating 은 폭을 1.5 로 덮어쓴다. */
const conn = (c: ReturnType<typeof controller>, key: string) => c.connections.find((x) => x.key === key);

describe('레인 뷰 연결선 강도', () => {
	it('계측이 없는 연결은 NO_TELEMETRY_STYLE 이다 (0 bps 로 뭉개지 않는다)', () => {
		// 트래픽 자체가 없으면 모든 인스턴스 연결이 "계측 없음" 이어야 한다
		const none = controller(null);
		const web03 = conn(none, 'vm-web-03|net-web');
		expect(web03).toBeDefined();
		expect(web03!.width).toBe(NO_TELEMETRY_STYLE.width);
		expect(web03!.opacity).toBe(NO_TELEMETRY_STYLE.opacity);
	});

	it('트래픽이 있어도 그 NIC 표본이 없으면 계측 없음이다', () => {
		// makeTraffic 에는 vm-web-03 의 인터페이스가 없다
		const c = controller(makeTraffic());
		const missing = conn(c, 'vm-web-03|net-web');
		expect(missing!.width).toBe(NO_TELEMETRY_STYLE.width);

		const measured = conn(c, 'vm-web-01|net-web');
		expect(measured!.width).toBe(edgeIntensity(3.2e6 + 1.1e6).width);
		expect(measured!.opacity).toBe(edgeIntensity(3.2e6 + 1.1e6).opacity);
	});

	it('**측정된 0 은 계측 없음보다 굵고 진하다** — 둘이 같아 보이면 살아있는 링크가 죽어 보인다', () => {
		const t = makeTraffic();
		t.interfaces!['port-web-03-eth0'] = {
			instance_id: 'vm-web-03', network_id: 'net-web',
			mac_address: 'fa:16:3e:a1:00:13', rx_bps: 0, tx_bps: 0,
		};
		const c = controller(t);
		const zero = conn(c, 'vm-web-03|net-web')!;
		expect(zero.width).toBeGreaterThan(NO_TELEMETRY_STYLE.width);
		expect(zero.opacity).toBeGreaterThan(NO_TELEMETRY_STYLE.opacity);
		expect(zero.width).toBe(edgeIntensity(0).width);
	});
});
