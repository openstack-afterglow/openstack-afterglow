// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { allocateFlowDots, assignTenantColors, buildGraph, buildMemberEdges, edgeRate, edgeStyle, FLOW_DOT_BUDGET, FLOW_MIN_BPS, flowStreams, matchesQuery, relatedSet, switchThroughput, trunkIntensityBps } from '../topologyGraph';
import { edgeIntensity, flowDotCount } from '../canvasHelpers';
import { NO_TELEMETRY_STYLE } from '../canvasHelpers';
import { autoLayout } from '../topologyLayout';
import type { RouterNode, VmNode } from '../types';
import { makeFixture, makeTraffic, mkInst, mkLb, OTHER, P } from './fixtures';

const vm = (g: ReturnType<typeof buildGraph>, id: string): VmNode => {
	const n = g.nodes.get(id);
	if (!n || n.kind !== 'vm') throw new Error(`vm ${id} 없음`);
	return n;
};
const router = (g: ReturnType<typeof buildGraph>, id: string): RouterNode => {
	const n = g.nodes.get(id);
	if (!n || n.kind !== 'router') throw new Error(`router ${id} 없음`);
	return n;
};

describe('buildGraph 가시성 규칙(레인 뷰 컨트롤러와 동일)', () => {
	it('showAll=false 이면 외부·공유·자기 프로젝트 네트워크만, 라우터·VM·LB 는 프로젝트 일치만 포함한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		expect(g.nets.map((n) => n.id)).toEqual(['net-pub', 'net-transit', 'net-app', 'net-lab', 'net-mgmt', 'net-web']);
		expect(g.nodes.has('sw:net-other')).toBe(false);
		expect(g.nodes.has('rtr-other')).toBe(false);
		expect(g.nodes.has('vm-other-01')).toBe(false);
		expect(g.nodes.has('lb-web')).toBe(true);
	});

	it('projectId=null + showAll 이면 전체를 포함하고 합성 코어 노드는 만들지 않는다', () => {
		const g = buildGraph(makeFixture(), { projectId: null, showAll: true });
		expect(g.nodes.has('sw:net-other')).toBe(true);
		expect(g.nodes.has('rtr-other')).toBe(true);
		expect(g.nodes.has('vm-other-01')).toBe(true);
		// 외부망 자체가 인터넷 경계를 나타내므로 상위 L3 코어 노드는 두지 않는다
		expect(g.nodes.has('core')).toBe(false);
		expect([...g.nodes.values()].map((n) => n.kind)).not.toContain('core');
		// FIP 선은 코어가 아니라 외부망 스위치로 향한다
		const fipTargets = new Set(g.edges.filter((e) => e.kind === 'fip').map((e) => e.to));
		expect(fipTargets.size).toBeGreaterThan(0);
		for (const t of fipTargets) expect(g.nodes.get(t)?.kind).toBe('switch');
	});

	it('외부 네트워크가 없으면 FIP 엣지를 만들지 않는다', () => {
		const data = makeFixture();
		data.networks = data.networks.filter((n) => !n.is_external);
		const g = buildGraph(data, { projectId: P, showAll: false });
		expect(g.edges.some((e) => e.kind === 'fip')).toBe(false);
	});

	it('네트워크 순서는 외부 → 공유 → 내부, 각 그룹 이름순이며 라우터에 닿지 않는 tenant 는 isolated', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		expect(g.nets.map((n) => n.kind)).toEqual(['external', 'shared', 'internal', 'internal', 'internal', 'internal']);
		expect(g.netById.get('net-mgmt')?.isolated).toBe(true);
		expect(g.netById.get('net-lab')?.isolated).toBe(true);
		expect(g.netById.get('net-web')?.isolated).toBe(false);
		expect(g.netById.get('net-transit')?.isolated).toBe(false);
	});
});

describe('buildGraph NIC 그룹화와 FIP', () => {
	it('port_id 가 같으면 하나의 NIC 으로 묶고 다르면 같은 네트워크라도 별도 NIC 이다', () => {
		const data = makeFixture();
		data.instances.push({
			id: 'vm-multi', name: 'multi', status: 'ACTIVE', project_id: P, network_names: ['web-net'],
			ip_addresses: [
				{ addr: '10.10.1.50', type: 'fixed', network_name: 'web-net', network_id: 'net-web', port_id: 'port-multi-a', mac_addr: 'fa:16:3e:00:00:50' },
				{ addr: '10.10.1.51', type: 'fixed', network_name: 'web-net', network_id: 'net-web', port_id: 'port-multi-a', mac_addr: 'fa:16:3e:00:00:50' },
				{ addr: '10.10.1.52', type: 'fixed', network_name: 'web-net', network_id: 'net-web', port_id: 'port-multi-b', mac_addr: 'fa:16:3e:00:00:52' },
			],
		});
		const g = buildGraph(data, { projectId: P, showAll: false });
		const node = vm(g, 'vm-multi');
		expect(node.nics).toHaveLength(2);
		expect(node.nics[0]).toMatchObject({ label: 'eth0', portId: 'port-multi-a', ips: ['10.10.1.50', '10.10.1.51'], ip: '10.10.1.50', rowIdx: 0 });
		expect(node.nics[1]).toMatchObject({ label: 'eth1', portId: 'port-multi-b', rowIdx: 1 });
		expect(node.rows).toBe(2);
		expect(g.edges.filter((e) => e.kind === 'cable' && e.from === 'vm-multi')).toHaveLength(2);
	});

	it('port_id 가 없으면 네트워크 단위로 묶고 network_id 가 없으면 이름+CIDR 로 해석한다', () => {
		const data = makeFixture();
		// 이름이 중복되는 두 네트워크: CIDR 로 구분해야 한다
		data.networks.push({ ...data.networks[2], id: 'net-web-dup', subnet_details: [{ id: 'sn-web-dup', name: 'dup', cidr: '10.10.7.0/24', gateway_ip: '10.10.7.1', dhcp_enabled: true }] });
		data.instances.push({
			id: 'vm-legacy', name: 'legacy', status: 'ACTIVE', project_id: P, network_names: ['web-net'],
			ip_addresses: [
				{ addr: '10.10.7.9', type: 'fixed', network_name: 'web-net' },
				{ addr: '10.10.7.10', type: 'fixed', network_name: 'web-net' },
			],
		});
		const g = buildGraph(data, { projectId: P, showAll: false });
		const node = vm(g, 'vm-legacy');
		expect(node.nics).toHaveLength(1);
		expect(node.nics[0]).toMatchObject({ netId: 'net-web-dup', portId: null, mac: null, ips: ['10.10.7.9', '10.10.7.10'] });
	});

	it('NIC 순서는 provider 우선 → 네트워크 이름 → IP 이며 FIP 는 fixed IP 를 가진 NIC 에 붙는다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const bastion = vm(g, 'vm-bastion-01');
		expect(bastion.nics.map((n) => n.netId)).toEqual(['net-transit', 'net-web']);
		expect(bastion.nics[0].fips).toHaveLength(0);
		expect(bastion.nics[1].fips).toEqual([{ addr: '203.0.113.100', netId: 'net-pub', fixed: '10.10.1.5', status: 'ACTIVE' }]);
		// FIP 행이 포함되어 rows 는 3, eth1 은 rowIdx 1
		expect(bastion.rows).toBe(3);
		expect(bastion.nics[1].rowIdx).toBe(1);
		const fipEdge = g.edges.find((e) => e.kind === 'fip' && e.from === 'vm-bastion-01');
		// FIP 선은 해당 외부망의 가상 스위치로 직접 이어진다
		expect(fipEdge).toMatchObject({ to: 'sw:net-pub', netId: 'net-pub', nic: bastion.nics[1] });
		const db = vm(g, 'vm-db-01');
		expect(db.nics.map((n) => n.netId)).toEqual(['net-app', 'net-mgmt', 'net-web']);
	});

	it('NIC 이 없는 인스턴스는 parked 이고 케이블이 없다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const orphan = vm(g, 'vm-orphan-01');
		expect(orphan.parked).toBe(true);
		expect(orphan.rows).toBe(1);
		expect(g.edgesByNode.get('vm-orphan-01')).toBeUndefined();
		expect(orphan.meta).toEqual({ flavor_name: 'cpu.2c_4g', image_id: 'img-debian', project_id: P });
	});
});

describe('buildGraph 라우터·LB', () => {
	it('라우터 포트와 배지(DVR/HA/SNAT/게이트웨이 없음)를 만든다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const edge = router(g, 'rtr-edge');
		expect(edge.badges).toEqual(['HA', 'SNAT']);
		expect(edge.ports.map((p) => [p.label, p.netId, p.ip])).toEqual([['gw', 'net-pub', '203.0.113.10'], ['if0', 'net-web', '10.10.1.1'], ['if1', 'net-app', '10.10.2.1']]);
		expect(g.edges.filter((e) => e.kind === 'trunk' && e.from === 'rtr-edge').map((e) => e.to)).toEqual(['sw:net-pub', 'sw:net-web', 'sw:net-app']);
		const transit = router(g, 'rtr-transit');
		expect(transit.badges).toEqual(['DVR', '게이트웨이 없음']);
		expect(transit.extNetId).toBeNull();
		expect(transit.intNetIds).toEqual(['net-transit', 'net-app']);
	});

	it('LB 의 vipNetId 는 vip_network_id 가 없으면 vip_subnet_id 로 역참조한다', () => {
		const data = makeFixture();
		data.load_balancers![0].vip_network_id = null;
		const g = buildGraph(data, { projectId: P, showAll: false });
		const lb = g.nodes.get('lb-web');
		expect(lb?.kind === 'lb' && lb.vipNetId).toBe('net-web');
		expect(lb?.kind === 'lb' && lb.memberVmIds).toEqual(['vm-web-01', 'vm-web-02']);
		expect(g.edges.find((e) => e.kind === 'lbvip')).toMatchObject({ from: 'lb-web', to: 'sw:net-web', lbId: 'lb-web' });
	});

	it('vip_network_id 가 없고 vip_subnet_id 가 비가시 네트워크면 vipNetId 는 null·parked 이고 lbvip 엣지도 없다', () => {
		const data = makeFixture();
		// 다른 프로젝트 사설 네트워크(net-other)의 subnet 을 VIP 로 가진 LB. LB 자체는 내 프로젝트 소유라 노드로는 보인다.
		data.load_balancers!.push(mkLb('lb-hidden', 'hidden-lb', { vipSubnetId: 'sn-other', vip: '10.20.1.100' }));
		const g = buildGraph(data, { projectId: P, showAll: false });
		expect(g.netById.has('net-other')).toBe(false);
		const lb = g.nodes.get('lb-hidden');
		expect(lb?.kind).toBe('lb');
		expect(lb?.kind === 'lb' && lb.vipNetId).toBeNull();
		expect(lb?.kind === 'lb' && lb.parked).toBe(true);
		expect(lb?.kind === 'lb' && lb.netIds).toEqual([]);
		expect(g.edges.some((e) => e.kind === 'lbvip' && e.lbId === 'lb-hidden')).toBe(false);
		expect(g.edgesByNode.get('lb-hidden')).toBeUndefined();
		// 같은 subnet 이 보이는 관리자 보기에서는 역참조가 성립한다
		const admin = buildGraph(data, { projectId: null, showAll: true });
		const adminLb = admin.nodes.get('lb-hidden');
		expect(adminLb?.kind === 'lb' && adminLb.vipNetId).toBe('net-other');
		expect(adminLb?.kind === 'lb' && adminLb.parked).toBe(false);
		expect(admin.edges.some((e) => e.kind === 'lbvip' && e.lbId === 'lb-hidden' && e.to === 'sw:net-other')).toBe(true);
		expect(admin.netById.get('net-other')?.project_id).toBe(OTHER);
	});

	it('멤버 곡선은 VIP 네트워크의 NIC 에 앵커한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const edges = buildMemberEdges(g, 'lb-web');
		expect(edges.map((e) => e.to)).toEqual(['vm-web-01', 'vm-web-02']);
		expect(edges[0]).toMatchObject({ kind: 'lbmember', netId: 'net-web', memberId: 'mbr-1', key: 'lbmember:lb-web>vm-web-01:mbr-1' });
		expect(edges[0].toNic?.netId).toBe('net-web');
		expect(buildMemberEdges(g, 'vm-web-01')).toEqual([]);
	});
});

describe('matchesQuery', () => {
	const g = buildGraph(makeFixture(), { projectId: P, showAll: false });

	it('빈 검색어는 null', () => {
		expect(matchesQuery(g, '   ')).toBeNull();
	});

	it('CIDR 은 포함 검사로 VM·라우터·네트워크를 찾는다', () => {
		const m = matchesQuery(g, '10.10.1.0/24')!;
		expect(m.nets.has('net-web')).toBe(true);
		expect(m.nodes.has('sw:net-web')).toBe(true);
		expect(m.nodes.has('vm-web-01')).toBe(true);
		expect(m.nodes.has('vm-db-01')).toBe(true);
		expect(m.nodes.has('rtr-edge')).toBe(true);
		expect(m.nodes.has('lb-web')).toBe(true);
		expect(m.nodes.has('vm-app-01')).toBe(false);
	});

	it('IP prefix 는 startsWith, FIP 도 포함한다', () => {
		const m = matchesQuery(g, '10.10.2.')!;
		expect([...m.nodes].filter((id) => id.startsWith('vm-')).sort()).toEqual(['vm-app-01', 'vm-db-01']);
		expect(matchesQuery(g, '203.0.113.10')!.nodes.has('vm-web-01')).toBe(true);
	});

	it('MAC 은 콜론 유무와 대소문자에 무관하게 찾는다', () => {
		expect(matchesQuery(g, 'FA:16:3E:A1:00:11')!.nodes).toEqual(new Set(['vm-web-01']));
		expect(matchesQuery(g, 'a10011')!.nodes).toEqual(new Set(['vm-web-01']));
		expect(matchesQuery(g, 'a1-00')!.nodes.has('vm-web-01')).toBe(true);
	});

	it('이름은 VM·라우터·LB·스위치를 포함 검색하고 매칭 네트워크의 스위치를 포함한다', () => {
		const m = matchesQuery(g, 'web')!;
		expect(m.nodes.has('vm-web-01')).toBe(true);
		expect(m.nodes.has('lb-web')).toBe(true);
		expect(m.nodes.has('sw:net-web')).toBe(true);
		expect(m.nets.has('net-web')).toBe(true);
		expect(matchesQuery(g, 'edge')!.nodes).toEqual(new Set(['rtr-edge']));
		expect(matchesQuery(g, 'vSwitch-public')!.nodes).toEqual(new Set(['sw:net-pub']));
	});
});

describe('edgeRate / edgeStyle', () => {
	const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
	const t = makeTraffic();
	const cable = (vmId: string, netId: string) => g.edges.find((e) => e.kind === 'cable' && e.from === vmId && e.netId === netId)!;

	it('traffic 이 null 이면 폭 1.5 / 불투명도 0.4', () => {
		expect(edgeStyle(cable('vm-web-01', 'net-web'), null, g)).toMatchObject({ width: 1.5, opacity: 0.4, dash: null, bps: null, rate: null });
	});

	it('cable 은 interfaces[portId], 없으면 인스턴스+네트워크 합산, 하위 trunk 는 networks, lbvip 는 load_balancers', () => {
		expect(edgeRate(cable('vm-web-01', 'net-web'), t, g)).toEqual(t.interfaces!['port-web-01-eth0']);
		const noPort = { ...cable('vm-app-01', 'net-app'), portId: null };
		expect(edgeRate(noPort, t, g)).toEqual({ rx_bps: 1.4e7, tx_bps: 6.0e6 });
		expect(edgeRate(cable('vm-web-03', 'net-web'), t, g)).toBeNull();
		const trunk = g.edges.find((e) => e.kind === 'trunk' && e.netId === 'net-web')!;
		expect(edgeRate(trunk, t, g)).toEqual(t.networks['net-web']);
		expect(edgeRate(g.edges.find((e) => e.kind === 'fip')!, t, g)).toBeNull();
		expect(edgeRate(g.edges.find((e) => e.kind === 'lbvip')!, t, g)).toEqual({ rx_bps: 2.9e6, tx_bps: 2.7e6 });
	});

	it('provider 트렁크는 provider 전체값을 복제하지 않고 라우터별 하위 네트워크만 합산한다', () => {
		const all = buildGraph(makeFixture(), { projectId: null, showAll: true });
		const traffic = makeTraffic();
		traffic.networks['net-pub'] = { rx_bps: 438e6, tx_bps: 72e6 };
		traffic.networks['net-other'] = { rx_bps: 7e6, tx_bps: 3e6 };
		const edgeUplink = all.edges.find((e) => e.kind === 'trunk' && e.from === 'rtr-edge' && e.netId === 'net-pub')!;
		const otherUplink = all.edges.find((e) => e.kind === 'trunk' && e.from === 'rtr-other' && e.netId === 'net-pub')!;
		const sharedUplink = all.edges.find((e) => e.kind === 'trunk' && e.from === 'rtr-transit' && e.netId === 'net-transit')!;

		expect(edgeRate(edgeUplink, traffic, all)).toEqual({ rx_bps: 19.8e6, tx_bps: 8e6 });
		expect(edgeRate(otherUplink, traffic, all)).toEqual({ rx_bps: 7e6, tx_bps: 3e6 });
		expect(edgeRate(sharedUplink, traffic, all)).toEqual({ rx_bps: 14e6, tx_bps: 6e6 });
	});

	it('트래픽 강도는 edgeIntensity 를 따른다', () => {
		// 4.3e6 는 1e6 과 1e7 사이 → 계단이 아니라 연속 보간값이 나온다
		const mid = edgeStyle(cable('vm-web-01', 'net-web'), t, g);
		expect(mid.bps).toBe(4.3e6);
		expect(mid.width).toBeGreaterThan(3.0);
		expect(mid.width).toBeLessThan(3.6);
		expect(mid.opacity).toBeGreaterThan(0.8);
		expect(mid.opacity).toBeLessThan(0.9);
		const trunk = g.edges.find((e) => e.kind === 'trunk' && e.netId === 'net-mgmt')!;
		expect(trunk).toBeUndefined();
		const appTrunk = g.edges.find((e) => e.kind === 'trunk' && e.netId === 'net-app' && e.from === 'rtr-edge')!;
		// 계측이 없으면 NO_TELEMETRY_STYLE 이다(예전의 트렁크 하한 2.5 가 아니다)
		expect(edgeStyle(appTrunk, null, g)).toMatchObject({ ...NO_TELEMETRY_STYLE });
		const trunkStyled = edgeStyle(appTrunk, t, g);
		expect(trunkStyled.width).toBeGreaterThan(mid.width);
		expect(trunkStyled.opacity).toBeGreaterThan(mid.opacity);
	});

	it('트렁크 강도는 증명된 구간 [max, rx+tx] 안의 중점이다 — east-west 이중 계상', () => {
		const appTrunk = g.edges.find((e) => e.kind === 'trunk' && e.netId === 'net-app' && e.from === 'rtr-edge')!;
		// networks['net-app'] 은 그 망에 붙은 NIC 합이라 동서 트래픽이 보내는 쪽 tx 와 받는 쪽 rx 로
		// 두 번 잡힌다. 실제 통과량 T 는 max(rx,tx) ≤ T ≤ rx+tx 로만 좁혀지고 EW 는 계측 불가다.
		expect(edgeRate(appTrunk, t, g)).toEqual({ rx_bps: 1.4e7, tx_bps: 6.0e6 });
		const bps = edgeStyle(appTrunk, t, g).bps!;
		expect(bps).toBeGreaterThanOrEqual(1.4e7);       // 하계 max
		expect(bps).toBeLessThanOrEqual(2.0e7);          // 상계 rx+tx
		expect(bps).toBe(1.4e7 + 6.0e6 / 2);             // 중점
		// 케이블은 그대로 rx+tx 다 — NIC 하나의 두 방향은 진짜로 서로 다른 방향이다
		expect(edgeStyle(cable('vm-web-01', 'net-web'), t, g).bps).toBe(3.2e6 + 1.1e6);
	});

	it('순수 east-west 는 rx+tx 의 2배 과대를 피하고, 양방향 남북은 max 의 2배 과소를 피한다', () => {
		// 순수 east-west(rx≈tx, 실제 통과량 ≈ rx): rx+tx 였다면 2배였다
		expect(switchThroughput({ rx_bps: 10e6, tx_bps: 10e6 })).toBe(15e6);
		expect(switchThroughput({ rx_bps: 10e6, tx_bps: 10e6 })).toBeLessThan(20e6);
		// 순수 단방향 남북(한쪽이 0): 두 끝값이 일치하므로 추정도 정확하다
		expect(switchThroughput({ rx_bps: 10e6, tx_bps: 0 })).toBe(10e6);
		// 어떤 입력에서도 구간을 벗어나지 않는다
		for (const [rx, tx] of [[0, 0], [1, 0], [3e5, 7e5], [9e8, 1e3]] as const) {
			const v = switchThroughput({ rx_bps: rx, tx_bps: tx });
			expect(v).toBeGreaterThanOrEqual(Math.max(rx, tx));
			expect(v).toBeLessThanOrEqual(rx + tx);
		}
	});

	it('uplink 는 **망별로 추정한 뒤 더한다** — 합산 뒤 추정하면 반대 방향 망이 상쇄된다', () => {
		const all = buildGraph(makeFixture(), { projectId: null, showAll: true });
		const traffic = makeTraffic();
		// rtr-edge 는 tenant 망 두 개(net-web, net-app)를 문다.
		traffic.networks['net-web'] = { rx_bps: 10e6, tx_bps: 0 };   // 순수 다운로드
		traffic.networks['net-app'] = { rx_bps: 0, tx_bps: 10e6 };   // 순수 업로드
		const uplink = all.edges.find((e) => e.kind === 'trunk' && e.from === 'rtr-edge' && e.netId === 'net-pub')!;

		// 먼저 합산하면 {10M, 10M} 이 되어 east-west 로 오인되고 15M 이 된다.
		expect(switchThroughput(edgeRate(uplink, traffic, all)!)).toBe(15e6);
		// 망별로 추정하면 둘 다 순수 남북이라 10M + 10M = 20M 로 정확하다.
		expect(trunkIntensityBps(uplink, traffic, all)).toBe(20e6);
		expect(edgeStyle(uplink, traffic, all).bps).toBe(20e6);
	});

	it('한가한 트렁크는 바쁜 케이블보다 가늘다 — 굵기 하한이 위계를 뒤집지 않는다', () => {
		// 예전에는 `Math.max(2.5, width)` 때문에 **모든 트렁크가 2.5px 로 같아지고**
		// 가장 바쁜 케이블보다도 굵었다(실측 2026-09-13: 케이블 최대 2.28 < 트렁크 일괄 2.5).
		const quiet = { ...t, networks: { ...t.networks, 'net-web': { rx_bps: 5e3, tx_bps: 4e3 } } };
		const webTrunk = g.edges.find((e) => e.kind === 'trunk' && e.netId === 'net-web')!;
		const styled = edgeStyle(webTrunk, quiet, g);
		// **하한이 있었다면 2.5 로 올라갔을 값**이다. edgeIntensity 결과와 정확히 같아야 한다.
		expect(styled.width).toBe(edgeIntensity(styled.bps!).width);
		expect(styled.width).toBeLessThan(2.5);
		expect(styled.width).toBeLessThan(edgeStyle(cable('vm-app-01', 'net-app'), t, g).width);
		// 그래도 "계측 없음" 보다는 굵다
		expect(styled.width).toBeGreaterThan(NO_TELEMETRY_STYLE.width);
	});

	it('FIP 는 0.6배 불투명도·폭 1.5·대시 4 3, LB 링크는 고정 스타일', () => {
		const fip = g.edges.find((e) => e.kind === 'fip' && e.from === 'vm-web-01')!;
		expect(edgeStyle(fip, null, g)).toMatchObject({ width: 1.5, opacity: 0.24, dash: '4 3' });
		expect(edgeStyle(g.edges.find((e) => e.kind === 'lbvip')!, t, g)).toMatchObject({ width: 2, opacity: 0.75, dash: null });
		expect(edgeStyle(buildMemberEdges(g, 'lb-web')[0], t, g)).toMatchObject({ width: 1.5, opacity: 0.75, dash: '4 3' });
	});

	it('SHUTOFF VM 의 케이블과 DOWN 라우터의 트렁크는 대시 6 4', () => {
		expect(edgeStyle(cable('vm-web-03', 'net-web'), t, g).dash).toBe('6 4');
		const data = makeFixture();
		data.routers[1].status = 'DOWN';
		const g2 = buildGraph(data, { projectId: P, showAll: false });
		const trunk = g2.edges.find((e) => e.kind === 'trunk' && e.from === 'rtr-transit')!;
		expect(edgeStyle(trunk, t, g2).dash).toBe('6 4');
		expect(edgeStyle(g2.edges.find((e) => e.kind === 'trunk' && e.from === 'rtr-edge')!, t, g2).dash).toBeNull();
	});
});

describe('assignTenantColors / relatedSet', () => {
	it('tenant 존 순서대로 내부 색을 두 톤으로 교차 배정하고 provider 는 건드리지 않는다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const layout = autoLayout(g);
		const tenantOrder = [...layout.order.lower, ...layout.order.solo];
		assignTenantColors(g, tenantOrder);
		const colors = tenantOrder.map((id) => g.netById.get(id)!.color);
		expect(colors).toEqual(['var(--color-topology-internal)', 'var(--color-topology-internal-2)', 'var(--color-topology-internal)', 'var(--color-topology-internal-2)']);
		expect(g.netById.get('net-pub')?.color).toBe('var(--color-topology-external)');
		expect(g.netById.get('net-transit')?.color).toBe('var(--color-topology-shared)');
	});

	it('relatedSet 은 직접 이웃 + 스위치 존 멤버 + LB 멤버를 포함한다', () => {
		const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const layout = autoLayout(g);
		const fromVm = relatedSet(g, layout, 'vm-app-01');
		expect(fromVm).toEqual(new Set(['vm-app-01', 'sw:net-app', 'sw:net-mgmt']));
		const fromSw = relatedSet(g, layout, 'sw:net-web');
		expect(fromSw.has('rtr-edge')).toBe(true);
		expect(fromSw.has('vm-web-01')).toBe(true);
		expect(fromSw.has('lb-web')).toBe(true);
		const fromLb = relatedSet(g, null, 'lb-web');
		expect(fromLb).toEqual(new Set(['lb-web', 'sw:net-web', 'vm-web-01', 'vm-web-02']));
		expect(relatedSet(g, layout, 'nope')).toEqual(new Set(['nope']));
	});

	it('mkInst 헬퍼는 project 기본값 P 로 생성한다', () => {
		expect(mkInst('x', 'x', 'ACTIVE', [['net-web', '10.10.1.99', '00:00:99']]).project_id).toBe(P);
	});
});


describe('flowStreams — 내부 통신 vs 게이트웨이 방향', () => {
	const g = buildGraph(makeFixture(), { projectId: P, showAll: false });
	const cableTo = (netId: string) => ({ kind: 'cable' as const, netId });

	it('격리 네트워크(라우터 없음)의 케이블은 tx·rx 를 양방향으로 흘린다', () => {
		// net-lab 은 라우터가 붙지 않아 isolated 다 → 그 망 트래픽은 정의상 전부 내부 통신
		expect(g.netById.get('net-lab')!.isolated).toBe(true);
		const st = flowStreams(cableTo('net-lab'), { rx_bps: 4e6, tx_bps: 9e6 }, true);
		expect(st).toHaveLength(2);
		expect(st.every((x) => x.internal)).toBe(true);
		expect(st.find((x) => x.dir)).toMatchObject({ bps: 9e6 });   // 인스턴스 → 스위치
		expect(st.find((x) => !x.dir)).toMatchObject({ bps: 4e6 });  // 스위치 → 인스턴스
	});

	it('라우터가 있는 네트워크는 게이트웨이 방향 한 줄만 흘린다', () => {
		expect(g.netById.get('net-web')!.isolated).toBe(false);
		const st = flowStreams(cableTo('net-web'), { rx_bps: 4e6, tx_bps: 9e6 }, false);
		expect(st).toHaveLength(1);
		expect(st[0]).toMatchObject({ bps: 13e6, dir: true, internal: false });
		// rx 가 더 크면 방향이 반대다
		expect(flowStreams(cableTo('net-web'), { rx_bps: 9e6, tx_bps: 4e6 }, false)[0].dir).toBe(false);
	});

	it('트렁크는 격리 여부와 무관하게 항상 단일 방향이다(라우터↔스위치는 north-south)', () => {
		const st = flowStreams({ kind: 'trunk', netId: 'net-lab' }, { rx_bps: 4e6, tx_bps: 9e6 }, true);
		expect(st).toHaveLength(1);
		expect(st[0].internal).toBe(false);
		// 트렁크는 edgeStyle 과 같은 스칼라(switchThroughput)를 쓴다 — 합(13e6)이 아니다
		expect(st[0].bps).toBe(switchThroughput({ rx_bps: 4e6, tx_bps: 9e6 }));
		expect(st[0].bps).toBe(11e6);
		// 상위 호출자가 계산한 값을 넘기면 그것을 쓴다(uplink 는 망별 합이라 다르다)
		expect(flowStreams({ kind: 'trunk', netId: 'net-lab' }, { rx_bps: 4e6, tx_bps: 9e6 }, true, 20e6)[0].bps).toBe(20e6);
	});

	it('예산이 모자라면 잘라 그리지 않고 통째로 건너뛴다 — 잘린 개수는 빈도를 거짓으로 낮춘다', () => {
		const len = 400;
		const mk = (i: number, bps: number) => ({
			key: `e${i}`, netId: 'net-web', len,
			streams: [{ bps, dir: true, internal: false }],
		});
		// bps 내림차순 후보 20개. 각자 flowDotCount 만큼 원하면 예산(60)을 훨씬 넘는다.
		const cands = Array.from({ length: 20 }, (_, i) => mk(i, 1e9 / 10 ** (i / 4)));
		const wanted = cands.reduce((n, c) => n + flowDotCount(c.streams[0].bps, len), 0);
		expect(wanted).toBeGreaterThan(FLOW_DOT_BUDGET);

		const alloc = allocateFlowDots(cands);
		expect(alloc.reduce((n, a) => n + a.n, 0)).toBeLessThanOrEqual(FLOW_DOT_BUDGET);
		// **배정된 엣지는 전부 원하는 개수를 그대로 받는다** — 절반만 받은 엣지가 있으면 안 된다
		for (const a of alloc) expect(a.n).toBe(flowDotCount(cands.find((c) => c.key === a.key)!.streams[0].bps, len));
		// 바쁜 쪽부터 배정한다
		expect(alloc[0].key).toBe('e0');
		// 예산에 못 든 엣지가 실제로 있다(= 문턱이 아니라 예산이 표시 여부를 정한다)
		expect(alloc.length).toBeLessThan(cands.length);
	});

	it('예산이 넉넉하면 모든 후보가 원하는 개수를 받는다', () => {
		const cands = [200, 400].map((len, i) => ({
			key: `e${i}`, netId: 'net-web', len,
			streams: [{ bps: 5e6, dir: true, internal: false }],
		}));
		const alloc = allocateFlowDots(cands, 1000);
		expect(alloc).toHaveLength(2);
		for (const [i, a] of alloc.entries()) expect(a.n).toBe(flowDotCount(5e6, cands[i].len));
	});

	it('FLOW_MIN_BPS 미만 스트림은 버린다 — 한쪽만 미달이면 그쪽만 사라진다', () => {
		expect(flowStreams(cableTo('net-lab'), { rx_bps: 10, tx_bps: 9e6 }, true)).toHaveLength(1);
		expect(flowStreams(cableTo('net-lab'), { rx_bps: 10, tx_bps: 9e6 }, true)[0].dir).toBe(true);
		expect(flowStreams(cableTo('net-lab'), { rx_bps: 10, tx_bps: 20 }, true)).toEqual([]);
		// 합산이 문턱을 넘으면 게이트웨이 방향은 남는다
		expect(flowStreams(cableTo('net-web'), { rx_bps: 6e4, tx_bps: 6e4 }, false)).toHaveLength(1);
		expect(flowStreams(cableTo('net-web'), { rx_bps: 10, tx_bps: 20 }, false)).toEqual([]);
		// 실환경 중간대(1e4~1e5)는 흐름이 **보여야** 한다 — 예전 문턱(1e5)에서는 NIC 43개 중 4개만 남았다
		expect(flowStreams(cableTo('net-web'), { rx_bps: 1.5e4, tx_bps: 1e4 }, false)).toHaveLength(1);
		expect(flowStreams(cableTo('net-lab'), { rx_bps: 5e4, tx_bps: 2e4 }, true)).toHaveLength(2);
		expect(FLOW_MIN_BPS).toBe(1e4);
	});
});
