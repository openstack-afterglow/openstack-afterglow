import { describe, expect, it } from 'vitest';
import { buildGraph, buildMemberEdges } from '../topologyGraph';
import {
	K_MAX,
	K_MIN,
	L,
	applyManualPositions,
	autoLayout,
	computeGeometry,
	contentBounds,
	fitTransform,
	nodeBounds,
	rectUnion,
	resolveManualOverlap,
	stableOrder,
	vmH,
	zoneRectFrom,
	zoomAt,
} from '../topologyLayout';
import type { TopologyData, TopologyInstance, TopologyIpAddress, TopologyNetwork, TopologyRouter } from '$lib/types/topology';
import type { CanvasGraph, LayoutResult, Rect } from '../types';
import { makeFixture, mkInst, mkLb, mkNet, OTHER, P } from './fixtures';

const inside = (inner: Rect, outer: Rect) =>
	inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h;

const build = (data = makeFixture()) => {
	const graph = buildGraph(data, { projectId: P, showAll: false });
	const layout = autoLayout(graph);
	return { graph, layout };
};

const sortedPos = (pos: Map<string, Rect>) => [...pos.entries()].sort(([a], [b]) => a.localeCompare(b));

describe('autoLayout 결정론', () => {
	it('같은 입력이면 같은 출력이고 입력 배열 순서를 바꿔도 위치가 같다', () => {
		const a = build();
		const b = build();
		expect(sortedPos(a.layout.pos)).toEqual(sortedPos(b.layout.pos));
		expect(a.layout.domOrder).toEqual(b.layout.domOrder);
		const shuffled = makeFixture();
		shuffled.instances.reverse();
		shuffled.networks.reverse();
		shuffled.routers.reverse();
		const c = build(shuffled);
		expect(sortedPos(c.layout.pos)).toEqual(sortedPos(a.layout.pos));
		expect(c.layout.order).toEqual(a.layout.order);
	});

	it('같은 그래프로 두 번 호출하면 pos·order·domOrder 가 완전히 같다(인접 가중치 메모이제이션 후에도 순수)', () => {
		const graph = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const first = autoLayout(graph);
		const second = autoLayout(graph);
		expect(sortedPos(second.pos)).toEqual(sortedPos(first.pos));
		expect(second.order.lower).toEqual(first.order.lower);
		expect(second.order.provider).toEqual(first.order.provider);
		expect(second.domOrder).toEqual(first.domOrder);
		expect([...second.home.entries()]).toEqual([...first.home.entries()]);
	});

	it('모든 노드에 위치가 있고 domOrder 는 노드 집합과 일치한다', () => {
		const { graph, layout } = build();
		expect([...layout.pos.keys()].sort()).toEqual([...graph.nodes.keys()].sort());
		expect([...layout.domOrder].sort()).toEqual([...graph.nodes.keys()].sort());
		// 합성 코어 노드를 없앤 뒤로 domOrder 는 provider 스위치부터 시작한다
		expect(layout.domOrder).not.toContain('core');
		expect(layout.domOrder[0]).toBe(`sw:${layout.order.provider[0]}`);
	});
});

describe('autoLayout 존 순서와 home', () => {
	it('provider → provider 에 라우터로 닿는 망 → 독립 망 순으로 밴드가 나뉜다', () => {
		const { layout } = build();
		expect(layout.order.provider).toEqual(['net-pub', 'net-transit']);
		// net-web·net-app 은 rtr-edge(net-pub 게이트웨이)와 rtr-transit(공유 net-transit)을 통해 provider 에 닿는다
		expect(layout.order.lower).toEqual(['net-app', 'net-web']);
		// 라우터가 없는 net-lab·net-mgmt 는 독립 밴드로 내려가고 isolated 인 net-mgmt 가 마지막이다
		expect(layout.order.solo).toEqual(['net-lab', 'net-mgmt']);
		const { ROUTER_Y, LOWER_Y, SOLO_ROUTER_Y, SOLO_Y } = layout.bands;
		expect(LOWER_Y).toBeGreaterThan(ROUTER_Y);
		expect(SOLO_ROUTER_Y).toBeGreaterThan(LOWER_Y);
		expect(SOLO_Y).toBeGreaterThanOrEqual(SOLO_ROUTER_Y);
	});

	it('밴드는 세로로 겹치지 않는다: provider 바닥 ≤ linked 상단, linked 바닥 ≤ solo 상단', () => {
		const { graph, layout } = build();
		const { zones } = computeGeometry(graph, layout);
		const top = (ids: string[]) => Math.min(...ids.map((id) => zones.get(id)!.y));
		const bottom = (ids: string[]) => Math.max(...ids.map((id) => zones.get(id)!).map((z) => z.y + z.h));
		const { provider, lower, solo } = layout.order;
		expect(provider.length && lower.length && solo.length).toBeTruthy();
		expect(bottom(provider)).toBeLessThanOrEqual(top(lower));
		expect(bottom(lower)).toBeLessThanOrEqual(top(solo));
	});

	it('home 쌍은 같은 밴드에서 맞닿은 존만 고른다 — 밴드가 다르면 단일 home + 긴 케이블이다', () => {
		const { graph, layout } = build();
		// db-01 은 net-app·net-web·net-mgmt 3-homed 지만 같은 밴드에서 맞닿은 쌍은 (net-app, net-web) 뿐이다
		expect(layout.home.get('vm-db-01')).toEqual(['net-app', 'net-web']);
		// app-01 의 두 망(net-app=linked, net-mgmt=solo)은 다른 밴드라 경계 컬럼이 성립하지 않는다
		expect(layout.home.get('vm-app-01')).toEqual(['net-app']);
		expect(layout.home.get('vm-bastion-01')).toEqual(['net-web']);
		expect(layout.home.get('vm-worker-01')).toEqual(['net-transit']);
		const { zones } = computeGeometry(graph, layout);
		const db = layout.pos.get('vm-db-01')!;
		expect(inside(db, zones.get('net-app')!)).toBe(true);
		expect(inside(db, zones.get('net-web')!)).toBe(true);
		expect(inside(db, zones.get('net-mgmt')!)).toBe(false);
		expect(layout.zoneMembers.get('net-app')).toContain('vm-db-01');
		expect(layout.zoneMembers.get('net-web')).toContain('vm-db-01');
		expect(layout.zoneMembers.get('net-mgmt')).not.toContain('vm-db-01');
		expect(layout.zoneMembers.get('net-app')).toContain('vm-app-01');
		expect(layout.zoneMembers.get('net-mgmt')).not.toContain('vm-app-01');
		expect(layout.zoneMembers.get('net-web')).toEqual(expect.arrayContaining(['sw:net-web', 'lb-web', 'vm-web-01', 'vm-bastion-01']));
	});

	it('라우터는 GW 인 tenant 네트워크의 존에 속하고 provider 존에는 속하지 않는다', () => {
		const { graph, layout } = build();
		// rtr-edge: net-pub(외부 uplink) + net-web·net-app 게이트웨이 / rtr-transit: net-transit(공유 uplink) + net-app
		expect(layout.zoneMembers.get('net-web')).toContain('rtr-edge');
		expect(layout.zoneMembers.get('net-app')).toEqual(expect.arrayContaining(['rtr-edge', 'rtr-transit']));
		// uplink 네트워크(외부·공유)에는 라우터가 들어가지 않는다 → provider 존이 라우터 밴드로 내려오지 않는다
		expect(layout.zoneMembers.get('net-pub')).not.toContain('rtr-edge');
		expect(layout.zoneMembers.get('net-transit')).not.toContain('rtr-transit');

		const { zones } = computeGeometry(graph, layout);
		const edge = layout.pos.get('rtr-edge')!;
		// GW 인 두 존 모두가 라우터를 감싼다 → 라우터가 두 네트워크의 경계에 놓인다
		expect(inside(edge, zones.get('net-web')!)).toBe(true);
		expect(inside(edge, zones.get('net-app')!)).toBe(true);
		expect(inside(edge, zones.get('net-pub')!)).toBe(false);
		// provider 존은 라우터 위에서 끝난다
		expect(zones.get('net-pub')!.y + zones.get('net-pub')!.h).toBeLessThan(edge.y);
		// tenant 존은 라우터까지 위로 확장된다(스위치 행보다 위에서 시작)
		expect(zones.get('net-web')!.y).toBeLessThan(layout.pos.get('sw:net-web')!.y);
	});

	it('서로 공유 VM 이 없는 존은 겹치지 않는다', () => {
		const { graph, layout } = build();
		const { zones } = computeGeometry(graph, layout);
		const web = zones.get('net-web')!, lab = zones.get('net-lab')!, mgmt = zones.get('net-mgmt')!;
		const overlap = (a: Rect, b: Rect) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
		expect(overlap(web, lab)).toBe(false);
		expect(overlap(mgmt, lab)).toBe(false);
		expect(overlap(web, mgmt)).toBe(false);
	});
});

describe('autoLayout 존 겹침 불변식', () => {
	/** 존 rect 가 겹치면 반드시 멤버를 공유한다(겹침 = 공유의 신호). 위반 쌍을 모두 돌려준다. */
	function falseOverlaps(graph: CanvasGraph, layout: LayoutResult) {
		const { zones } = computeGeometry(graph, layout);
		const ids = [...zones.keys()];
		const ov = (a: Rect, b: Rect) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
		const bad: string[] = [];
		for (let i = 0; i < ids.length; i++) {
			for (let j = i + 1; j < ids.length; j++) {
				const A = layout.zoneMembers.get(ids[i]) ?? [], B = layout.zoneMembers.get(ids[j]) ?? [];
				if (ov(zones.get(ids[i])!, zones.get(ids[j])!) && !A.some((x: string) => B.includes(x))) bad.push(`${ids[i]} x ${ids[j]}`);
			}
		}
		return bad;
	}

	/** tenant 망 n개, 각 망마다 자기 라우터가 같은 외부망으로 uplink — 실제 배포에서 가장 흔한 모양. */
	function perNetRouterData(n: number): TopologyData {
		const networks: TopologyData['networks'] = [
			{ id: 'net-pub', name: 'public', status: 'ACTIVE', is_external: true, is_shared: false, project_id: null,
				subnet_details: [{ id: 'sn-pub', name: 'pub', cidr: '203.0.113.0/24', gateway_ip: '203.0.113.1', dhcp_enabled: false }] },
		];
		const routers: TopologyData['routers'] = [];
		const instances: TopologyData['instances'] = [];
		for (let i = 0; i < n; i++) {
			networks.push({ id: `net-t${i}`, name: `tenant-${i}`, status: 'ACTIVE', is_external: false, is_shared: false, project_id: 'p',
				subnet_details: [{ id: `sn-t${i}`, name: `t${i}`, cidr: `10.${i}.0.0/24`, gateway_ip: `10.${i}.0.1`, dhcp_enabled: true }] });
			routers.push({ id: `rtr-${i}`, name: `r-${i}`, status: 'ACTIVE', external_gateway_network_id: 'net-pub',
				external_gateway_ips: [`203.0.113.${10 + i}`], interface_ips: [{ ip_address: `10.${i}.0.1`, subnet_id: `sn-t${i}` }],
				is_distributed: false, is_ha: false, connected_subnet_ids: [`sn-t${i}`], dvr_subnet_ids: [], project_id: 'p' });
			for (let k = 0; k < 2; k++) instances.push({ id: `vm-${i}-${k}`, name: `vm-${i}-${k}`, status: 'ACTIVE', project_id: 'p',
				network_names: [`tenant-${i}`], ip_addresses: [{ addr: `10.${i}.0.${10 + k}`, type: 'fixed', network_name: `tenant-${i}`, network_id: `net-t${i}`, port_id: `p-${i}-${k}`, mac_addr: `fa:16:3e:00:${i}:${k}` }] });
		}
		return { networks, routers, instances, floating_ips: [], load_balancers: [] };
	}

	it('망마다 자기 외부 GW 라우터가 있어도 소속 존 밖으로 밀리지 않는다', () => {
		const graph = buildGraph(perNetRouterData(10), { projectId: 'p', showAll: false });
		const layout = autoLayout(graph);
		expect(falseOverlaps(graph, layout)).toEqual([]);
		// 각 라우터는 자기 home 존에만 둘러싸인다(남의 존에 갇히지 않는다)
		const { zones } = computeGeometry(graph, layout);
		for (let i = 0; i < 10; i++) {
			const r = layout.pos.get(`rtr-${i}`)!;
			const enclosing = [...zones.entries()].filter(([, z]) => inside(r, z)).map(([n]) => n);
			expect(enclosing).toEqual(['net-t' + i]);
		}
	});

	it('기본 픽스처와 대규모 픽스처 모두 거짓 겹침이 없다', () => {
		const base = build();
		expect(falseOverlaps(base.graph, base.layout)).toEqual([]);
		const largeGraph = buildGraph(makeLargeTenantData(), { projectId: P, showAll: false });
		expect(falseOverlaps(largeGraph, autoLayout(largeGraph))).toEqual([]);
	});

	it('한 네트워크에 라우터가 여러 개(HA)여도 서로 겹치지 않는다', () => {
		// 좁은 tenant 망 하나에 라우터 n개 — sweep 이 확보한 간격이 하한 적용으로 깨지면 여기서 겹친다
		for (const n of [1, 2, 3, 5, 8]) {
			const data = perNetRouterData(1);
			for (let i = 1; i < n; i++) {
				data.routers.push({ id: `rtr-ha-${i}`, name: `ha-${i}`, status: 'ACTIVE', external_gateway_network_id: 'net-pub',
					external_gateway_ips: [`203.0.113.${50 + i}`], interface_ips: [{ ip_address: '10.0.0.1', subnet_id: 'sn-t0' }],
					is_distributed: false, is_ha: true, connected_subnet_ids: ['sn-t0'], dvr_subnet_ids: [], project_id: 'p' });
			}
			const graph = buildGraph(data, { projectId: 'p', showAll: false });
			const layout = autoLayout(graph);
			const rs = [...graph.nodes.values()].filter((x) => x.kind === 'router')
				.map((x) => layout.pos.get(x.id)!).sort((a, b) => a.x - b.x);
			for (let i = 1; i < rs.length; i++) {
				expect(rs[i].x - (rs[i - 1].x + rs[i - 1].w)).toBeGreaterThanOrEqual(L.RT_GAP);
			}
			expect(Math.min(...rs.map((r) => r.x))).toBeGreaterThanOrEqual(0);
		}
	});

	it('provider 망만 연결된 라우터는 어떤 tenant 존에도 갇히지 않는다', () => {
		const data = perNetRouterData(4);
		data.networks.push({ id: 'net-shared', name: 'shared-net', status: 'ACTIVE', is_external: false, is_shared: true, project_id: null,
			subnet_details: [{ id: 'sn-shared', name: 'shared', cidr: '198.51.100.0/24', gateway_ip: '198.51.100.1', dhcp_enabled: true }] });
		data.routers.push({ id: 'rtr-shared', name: 'shared-only', status: 'ACTIVE', external_gateway_network_id: null,
			external_gateway_ips: [], interface_ips: [{ ip_address: '198.51.100.1', subnet_id: 'sn-shared' }],
			is_distributed: false, is_ha: false, connected_subnet_ids: ['sn-shared'], dvr_subnet_ids: [], project_id: 'p' });
		const graph = buildGraph(data, { projectId: 'p', showAll: true });
		const layout = autoLayout(graph);
		const { zones } = computeGeometry(graph, layout);
		const r = layout.pos.get('rtr-shared')!;
		const tenantZones = layout.order.lower.map((id) => zones.get(id)!).filter(Boolean);
		expect(tenantZones.some((z) => inside(r, z))).toBe(false);
		expect(falseOverlaps(graph, layout)).toEqual([]);
	});
});

describe('autoLayout 계층 순서', () => {
	/** 존마다 스위치 → LB → 일반 인스턴스 → DB 인스턴스가 위에서 아래로 지켜지는지 검사한다(경계 VM 포함). */
	function hierarchyViolations(graph: CanvasGraph, layout: LayoutResult) {
		const bad: string[] = [];
		const y = (id: string) => layout.pos.get(id)!.y;
		const bottom = (id: string) => layout.pos.get(id)!.y + layout.pos.get(id)!.h;
		for (const nid of [...layout.order.provider, ...layout.order.lower, ...layout.order.solo]) {
			const members = (layout.zoneMembers.get(nid) ?? []).filter((m) => layout.pos.has(m));
			const kindOf = (m: string) => graph.nodes.get(m)?.kind;
			const sw = 'sw:' + nid;
			const zoneLbs = members.filter((m) => kindOf(m) === 'lb');
			const vms = members.filter((m) => kindOf(m) === 'vm');
			const plain = vms.filter((m) => !(graph.nodes.get(m) as { isDatabase?: boolean }).isDatabase);
			const dbs = vms.filter((m) => (graph.nodes.get(m) as { isDatabase?: boolean }).isDatabase);
			for (const lb of zoneLbs) if (bottom(sw) > y(lb)) bad.push(`${nid}: 스위치가 LB 아래`);
			for (const v of [...plain, ...dbs]) if (bottom(sw) > y(v)) bad.push(`${nid}: 스위치가 인스턴스 아래`);
			for (const v of [...plain, ...dbs]) for (const lb of zoneLbs) if (bottom(lb) > y(v)) bad.push(`${nid}: LB 가 인스턴스 아래`);
			// DB 는 같은 컬럼(같은 x) 안에서 일반 인스턴스 아래에 온다. 멀티 NIC 경계 VM 은 두 존의 교차 컬럼에
			// 놓이는 규칙이 우선하므로, 다른 컬럼의 일반 인스턴스와는 세로 순서를 강제하지 않는다.
			const colOf = (m: string) => Math.round(layout.pos.get(m)!.x);
			for (const d of dbs) for (const v of plain) {
				if (colOf(d) === colOf(v) && y(d) < bottom(v)) bad.push(`${nid}: DB 가 같은 컬럼의 인스턴스 위`);
			}
		}
		// 라우터는 자신이 속한 존의 스위치보다 위
		for (const node of graph.nodes.values()) {
			if (node.kind !== 'router') continue;
			for (const [nid, members] of layout.zoneMembers) {
				if (!members.includes(node.id)) continue;
				if (bottom(node.id) > y('sw:' + nid)) bad.push(`${nid}: 라우터가 스위치 아래`);
			}
		}
		return [...new Set(bad)];
	}

	it('기본·대규모 픽스처 모두 라우터 > 스위치 > LB > 인스턴스 > DB 순서를 지킨다', () => {
		const withDb = makeFixture();
		for (const inst of withDb.instances) if (inst.id === 'vm-web-02' || inst.id === 'vm-app-01') inst.is_database = true;
		const g1 = buildGraph(withDb, { projectId: P, showAll: false });
		expect(hierarchyViolations(g1, autoLayout(g1))).toEqual([]);
		const g2 = buildGraph(makeLargeTenantData(), { projectId: P, showAll: false });
		expect(hierarchyViolations(g2, autoLayout(g2))).toEqual([]);
	});

	it('멀티 NIC(경계) 인스턴스도 인접 존의 LB 아래에서 시작하고 DB 는 그 뒤에 온다', () => {
		const data = makeFixture();
		// 경계 컬럼(net-app|net-web)이 걸치는 두 존 각각에 LB 를 둔다 → 경계 VM 은 두 LB 아래에서 시작해야 한다
		data.load_balancers = [
			...(data.load_balancers ?? []),
			mkLb('lb-app', 'app-lb', { vipNetId: 'net-app', vip: '10.10.2.200' }),
			mkLb('lb-web2', 'web-lb-2', { vipNetId: 'net-web', vip: '10.10.1.201' }),
		];
		// 같은 경계 컬럼에 일반 VM 과 DB VM 을 함께 둔다(순서 규칙 확인용)
		data.instances.push(mkInst('vm-edge-01', 'edge-01', 'ACTIVE', [['net-app', '10.10.2.41', 'a2:00:41'], ['net-web', '10.10.1.41', 'a1:00:41']]));
		data.instances.find((i) => i.id === 'vm-db-01')!.is_database = true;
		const graph = buildGraph(data, { projectId: P, showAll: false });
		const layout = autoLayout(graph);
		expect(hierarchyViolations(graph, layout)).toEqual([]);
		expect(layout.home.get('vm-edge-01')).toEqual(['net-app', 'net-web']);
		const border = layout.pos.get('vm-db-01')!;
		for (const lbId of ['lb-app', 'lb-web2']) {
			const lb = layout.pos.get(lbId)!;
			expect(border.y).toBeGreaterThanOrEqual(lb.y + lb.h);
		}
		// 같은 경계 컬럼의 일반 VM 이 DB VM 보다 위
		const plainBorder = layout.pos.get('vm-edge-01')!;
		expect(plainBorder.x).toBe(border.x);
		expect(border.y).toBeGreaterThanOrEqual(plainBorder.y + plainBorder.h);
	});
});

describe('autoLayout 밴드와 주차', () => {
	it('라우터는 provider 존 하단과 LOWER_Y 사이 밴드에 놓이고 서로 겹치지 않는다', () => {
		const { graph, layout } = build();
		const { zones } = computeGeometry(graph, layout);
		const providerBottom = Math.max(...layout.order.provider.map((id) => zones.get(id)!).map((z) => z.y + z.h));
		const { ROUTER_Y, LOWER_Y } = layout.bands;
		expect(ROUTER_Y).toBeGreaterThan(providerBottom);
		expect(ROUTER_Y + L.RT_H).toBeLessThan(LOWER_Y);
		const rs = ['rtr-edge', 'rtr-transit'].map((id) => layout.pos.get(id)!);
		for (const r of rs) expect(r.y).toBe(ROUTER_Y);
		const [a, b] = rs.sort((p, q) => p.x - q.x);
		expect(b.x - (a.x + a.w)).toBeGreaterThanOrEqual(L.RT_GAP);
		expect(layout.pos.get('sw:net-web')!.y).toBe(LOWER_Y);
		expect(layout.pos.get('sw:net-pub')!.y).toBe(L.PROV_Y);
	});

	it('콘텐츠가 y=0 위로 넘치지 않고 bands.BOTTOM_Y 가 실제 바닥을 덮는다', () => {
		// 원점이 (0,0) 이고 width/height 만 가진 zones/edges SVG 레이어를 쓰므로 음수 y 는 잘린다(PROV_Y = PAD_T).
		// 아래끝은 svgH 가 BOTTOM_Y 로 계산되므로 BOTTOM_Y 가 노드·존 rect 를 모두 덮어야 잘리지 않는다.
		const graph = buildGraph(makeFixture(), { projectId: null, showAll: true });
		const layout = autoLayout(graph);
		for (const [id, p] of layout.pos) {
			expect(p.y, `node ${id}`).toBeGreaterThanOrEqual(0);
			expect(p.y + p.h, `node ${id}`).toBeLessThanOrEqual(layout.bands.BOTTOM_Y);
		}
		for (const [nid, members] of layout.zoneMembers) {
			const z = zoneRectFrom(layout.pos, members);
			if (!z) continue;
			expect(z.y, `zone ${nid}`).toBeGreaterThanOrEqual(0);
			expect(z.y + z.h, `zone ${nid}`).toBeLessThanOrEqual(layout.bands.BOTTOM_Y);
		}
	});

	it('provider 존도 직접 VM 을 스위치 아래에 두어 계층 순서가 위→아래로 읽힌다', () => {
		const { layout } = build();
		const sw = layout.pos.get('sw:net-transit')!, w1 = layout.pos.get('vm-worker-01')!;
		// flank(스위치 좌우) 가 아니라 스위치 아래 행에 놓인다
		expect(w1.y).toBeGreaterThanOrEqual(sw.y + sw.h);
	});

	it('존 내부는 라우터 > 스위치 > LB > 인스턴스 > DB 순으로 아래로 쌓인다', () => {
		// net-web: 라우터(rtr-edge) · 스위치 · LB(web-lb) · 일반 VM · DB VM 이 모두 있는 존을 만든다
		const data = makeFixture();
		const dbVm = data.instances.find((i) => i.id === 'vm-web-02')!;
		dbVm.is_database = true;
		const graph = buildGraph(data, { projectId: P, showAll: false });
		const layout = autoLayout(graph);
		const y = (id: string) => layout.pos.get(id)!.y;
		const bottom = (id: string) => layout.pos.get(id)!.y + layout.pos.get(id)!.h;
		expect(bottom('rtr-edge')).toBeLessThanOrEqual(y('sw:net-web'));
		expect(bottom('sw:net-web')).toBeLessThanOrEqual(y('lb-web'));
		expect(bottom('lb-web')).toBeLessThanOrEqual(y('vm-web-01'));
		// DB 인스턴스는 일반 인스턴스 계층 아래
		expect(y('vm-web-02')).toBeGreaterThanOrEqual(bottom('vm-web-01'));
	});

	it('NIC 이 없는 인스턴스는 parked 로 표시되고 주차 스트립(가장 오른쪽)에 위치한다', () => {
		const { layout } = build();
		expect(layout.parked.has('vm-orphan-01')).toBe(true);
		const orphan = layout.pos.get('vm-orphan-01')!;
		expect(orphan.h).toBe(vmH(1));
		const others = [...layout.pos.entries()].filter(([id]) => id !== 'vm-orphan-01').map(([, r]) => r.x + r.w);
		expect(orphan.x).toBeGreaterThan(Math.max(...others));
		expect(layout.zoneMembers.get('net-web')).not.toContain('vm-orphan-01');
	});

	it('직접 VM 이 6개를 넘는 provider 네트워크는 그리드로 내려간다', () => {
		const data = makeFixture();
		for (let i = 0; i < 7; i++) {
			data.instances.push({ id: `vm-edge-${i}`, name: `edge-${i}`, status: 'ACTIVE', project_id: P, network_names: ['transit-shared'], ip_addresses: [{ addr: `198.51.100.${100 + i}`, type: 'fixed', network_name: 'transit-shared', network_id: 'net-transit', port_id: `port-edge-${i}`, mac_addr: `fa:16:3e:00:01:${i}` }] });
		}
		const { layout } = build(data);
		const sw = layout.pos.get('sw:net-transit')!;
		for (let i = 0; i < 7; i++) expect(layout.pos.get(`vm-edge-${i}`)!.y).toBeGreaterThanOrEqual(sw.y + sw.h + L.SW_TO_ROW);
	});
});

describe('applyManualPositions', () => {
	it('존재하는 id 만 적용하고 나머지는 잘라낸 map 을 돌려준다', () => {
		const { layout } = build();
		const before = { ...layout.pos.get('vm-web-01')! };
		const pruned = applyManualPositions(layout, { 'vm-web-01': { x: 10, y: 20 }, 'vm-gone': { x: 1, y: 2 }, 'vm-web-02': { x: Number.NaN, y: 3 } });
		expect(pruned).toEqual({ 'vm-web-01': { x: 10, y: 20 } });
		expect(layout.pos.get('vm-web-01')).toEqual({ x: 10, y: 20, w: before.w, h: before.h });
		expect(applyManualPositions(layout, null)).toEqual({});
	});

	it('드래그로 옮긴 VM 을 따라 존 rect 가 늘어난다(멤버십은 유지)', () => {
		const { graph, layout } = build();
		const zBefore = computeGeometry(graph, layout).zones.get('net-lab')!;
		applyManualPositions(layout, { 'vm-lab-01': { x: zBefore.x + zBefore.w + 500, y: zBefore.y } });
		const zAfter = computeGeometry(graph, layout).zones.get('net-lab')!;
		expect(zAfter.w).toBeGreaterThan(zBefore.w + 400);
		expect(layout.zoneMembers.get('net-lab')).toContain('vm-lab-01');
	});
});

describe('computeGeometry', () => {
	it('모든 엣지(+extraEdges)에 베지어 path 와 중점이 생기고 슬롯 순서는 재계산해도 안정적이다', () => {
		const { graph, layout } = build();
		const extra = buildMemberEdges(graph, 'lb-web', layout.pos);
		const g1 = computeGeometry(graph, layout, extra);
		expect(g1.geom.size).toBe(graph.edges.length + extra.length);
		for (const [, g] of g1.geom) {
			expect(g.d.startsWith('M')).toBe(true);
			expect(g.d).toContain(' C');
			expect(Number.isFinite(g.mid.x) && Number.isFinite(g.mid.y)).toBe(true);
		}
		const g2 = computeGeometry(graph, layout, extra, g1.slotOrder);
		expect([...g2.slotOrder.entries()]).toEqual([...g1.slotOrder.entries()]);
		expect([...g2.geom.entries()]).toEqual([...g1.geom.entries()]);
	});

	it('VM 케이블은 NIC 행 높이에서 출발하고 스위치 슬롯은 폭 안에 균등 분배된다', () => {
		const { graph, layout } = build();
		const { geom } = computeGeometry(graph, layout);
		const db = layout.pos.get('vm-db-01')!;
		const cables = graph.edges.filter((e) => e.kind === 'cable' && e.from === 'vm-db-01');
		for (const e of cables) {
			const g = geom.get(e.key)!;
			if (g.sa === 'LEFT' || g.sa === 'RIGHT') {
				expect(g.a.y).toBeCloseTo(db.y + L.VM_HEAD + e.nic!.rowIdx * L.NIC_ROW + L.NIC_ROW / 2);
			} else {
				expect(g.a.y === db.y || g.a.y === db.y + db.h).toBe(true);
			}
			const sw = layout.pos.get(e.to)!;
			expect(g.b.x).toBeGreaterThanOrEqual(sw.x);
			expect(g.b.x).toBeLessThanOrEqual(sw.x + sw.w);
		}
	});

	it('stableOrder 는 8 단위 이내 교차에서는 이전 순서를 유지하고 그 이상이면 교환한다', () => {
		type It = { k: string; v: number };
		const items: It[] = [{ k: 'a', v: 10 }, { k: 'b', v: 15 }];
		expect(stableOrder(['b', 'a'], items, (i) => i.k, (i) => i.v).map((i) => i.k)).toEqual(['b', 'a']);
		const far: It[] = [{ k: 'a', v: 10 }, { k: 'b', v: 30 }];
		expect(stableOrder(['b', 'a'], far, (i) => i.k, (i) => i.v).map((i) => i.k)).toEqual(['a', 'b']);
		expect(stableOrder(undefined, [{ k: 'z', v: 5 }, { k: 'y', v: 5 }], (i) => i.k, (i) => i.v).map((i) => i.k)).toEqual(['y', 'z']);
		expect(stableOrder(['gone'], items, (i) => i.k, (i) => i.v).map((i) => i.k)).toEqual(['a', 'b']);
	});

	it('nodeBounds 는 노드와 소속 존을 합치고 contentBounds 는 전체를 감싼다', () => {
		const { graph, layout } = build();
		const { zones } = computeGeometry(graph, layout);
		const nb = nodeBounds('vm-db-01', layout, zones)!;
		expect(inside(zones.get('net-app')!, nb) && inside(zones.get('net-web')!, nb)).toBe(true);
		const cb = contentBounds(zones, layout.pos);
		for (const r of layout.pos.values()) expect(inside(r, cb)).toBe(true);
		expect(contentBounds(new Map(), new Map())).toEqual({ x: 0, y: 0, w: 100, h: 100 });
		expect(rectUnion([])).toBeNull();
		expect(zoneRectFrom(new Map(), ['x'])).toBeNull();
	});
});

describe('뷰 변환', () => {
	it('zoomAt 은 커서 아래의 캔버스 점을 고정하고 k 를 [0.35, 2.2] 로 클램프한다', () => {
		const view = { panX: 120, panY: -40, k: 0.8 };
		const sx = 300, sy = 200;
		const before = { x: (sx - view.panX) / view.k, y: (sy - view.panY) / view.k };
		const next = zoomAt(view, sx, sy, 1.3);
		expect(next.k).toBe(1.3);
		expect((sx - next.panX) / next.k).toBeCloseTo(before.x);
		expect((sy - next.panY) / next.k).toBeCloseTo(before.y);
		expect(zoomAt(view, sx, sy, 99).k).toBe(K_MAX);
		expect(zoomAt(view, sx, sy, 0.01).k).toBe(K_MIN);
	});

	it('fitTransform 은 bounds 를 가운데 맞추고 k 를 클램프한다', () => {
		const b = { x: 100, y: 50, w: 1000, h: 500 };
		const v = fitTransform(b, 1200, 800, 40);
		expect(v.k).toBeCloseTo(Math.min(1120 / 1000, 720 / 500));
		expect(v.panX + (b.x + b.w / 2) * v.k).toBeCloseTo(600);
		expect(v.panY + (b.y + b.h / 2) * v.k).toBeCloseTo(400);
		expect(fitTransform({ x: 0, y: 0, w: 10, h: 10 }, 1200, 800).k).toBe(1.25);
		expect(fitTransform({ x: 0, y: 0, w: 100000, h: 10 }, 1200, 800).k).toBe(K_MIN);
		expect(fitTransform({ x: 0, y: 0, w: 0, h: 0 }, 1200, 800).k).toBe(1.25);
	});
});

// ───────── 합성 대형 그래프(60 tenant 네트워크 / 600 VM). 인덱스 산술만 쓰므로 실행마다 동일하다.
const BIG_NETS = 60;
const BIG_VMS = 600;
const netTag = (i: number) => String(i).padStart(2, '0');
const bigNetId = (i: number) => `net-t${netTag(i)}`;
const bigNetName = (i: number) => `tenant-${netTag(i)}`;

function makeLargeTenantData(): TopologyData {
	const networks: TopologyNetwork[] = [];
	for (let i = 0; i < BIG_NETS; i++) {
		networks.push(mkNet(bigNetId(i), bigNetName(i), `10.${100 + i}.0.0/24`, `10.${100 + i}.0.1`, { project: P }));
	}
	// 대부분의 VM 은 인접한 두 네트워크에 dual-home 시켜 home 존(경계 VM) 루프를 태운다.
	const instances: TopologyInstance[] = [];
	for (let k = 0; k < BIG_VMS; k++) {
		const tag = String(k).padStart(3, '0');
		const first = k % (BIG_NETS - 1);
		const nicOf = (netIdx: number, eth: number): TopologyIpAddress => ({
			addr: `10.${100 + netIdx}.0.${10 + (k % 200)}`,
			type: 'fixed',
			network_name: bigNetName(netIdx),
			network_id: bigNetId(netIdx),
			port_id: `port-bulk-${tag}-eth${eth}`,
			mac_addr: `fa:16:3e:b${eth}:${netTag(netIdx)}:${tag.slice(1)}`,
		});
		const ip_addresses = k % 10 === 0 ? [nicOf(first, 0)] : [nicOf(first, 0), nicOf(first + 1, 1)];
		instances.push({
			id: `vm-bulk-${tag}`, name: `bulk-${tag}`, status: 'ACTIVE', project_id: P,
			network_names: [...new Set(ip_addresses.map((a) => a.network_name))],
			ip_addresses, flavor_name: 'cpu.2c_4g', image_id: 'img-ubuntu',
		});
	}
	// 라우터도 3개 두어 intNetIds 쌍(0.5) 가중치 경로까지 포함한다.
	const routers: TopologyRouter[] = [0, 1, 2].map((r) => {
		const idxs = [r * 4, r * 4 + 1, r * 4 + 2];
		const subnets = idxs.map((i) => `sn-t${netTag(i)}`);
		return {
			id: `rtr-bulk-${r}`, name: `bulk-router-${r}`, status: 'ACTIVE',
			external_gateway_network_id: null, external_gateway_ips: [],
			interface_ips: idxs.map((i) => ({ ip_address: `10.${100 + i}.0.1`, subnet_id: `sn-t${netTag(i)}` })),
			is_distributed: false, is_ha: false, connected_subnet_ids: subnets, dvr_subnet_ids: [],
			project_id: P, enable_snat: false, routes: [],
		};
	});
	return { networks, routers, instances, floating_ips: [] };
}

describe('autoLayout 대형 그래프', () => {
	it('네트워크 60개 · VM 600개도 모든 노드를 배치하고 시간 상한 안에 끝난다', () => {
		const graph = buildGraph(makeLargeTenantData(), { projectId: P, showAll: false });
		expect(graph.nets).toHaveLength(BIG_NETS);
		const t0 = performance.now();
		const layout = autoLayout(graph);
		const elapsed = performance.now() - t0;
		expect([...graph.nodes.keys()].filter((id) => !layout.pos.has(id))).toEqual([]);
		expect(layout.pos.size).toBe(graph.nodes.size);
		expect(new Set(layout.domOrder)).toEqual(new Set(graph.nodes.keys()));
		expect(layout.domOrder).toHaveLength(graph.nodes.size);
		// 외부 게이트웨이가 없는 프리셋이라 tenant 망 전체가 독립(solo) 밴드로 간다
		expect([...layout.order.lower, ...layout.order.solo]).toHaveLength(BIG_NETS);
		// 인접 체인이 실제로 만들어져 경계 VM(home 2개) 루프가 돌았는지 확인한다(퇴화하면 이 단정이 먼저 깨진다)
		const borderVms = [...layout.home.values()].filter((h) => h.length === 2).length;
		expect(borderVms).toBeGreaterThan(300);
		// w(a, b) 를 조회마다 VM·라우터 전수 스캔으로 계산하면 O(N²·V) 로 폭주한다.
		// pairW 메모이제이션(공출현 1회 집계 + O(1) 조회)이 이 상한을 지키는 근거다.
		expect(elapsed).toBeLessThan(400);
	});
});

describe('미연결 LB 주차', () => {
	it('VIP 네트워크가 보이지 않는 LB 도 위치·domOrder 를 받아 미연결 스트립에 렌더된다', () => {
		const data = makeFixture();
		// 다른 프로젝트 사설 네트워크의 subnet 을 VIP 로 가진 LB: 역참조가 거부되어 parked 가 된다
		data.load_balancers!.push(mkLb('lb-hidden', 'hidden-lb', { vipSubnetId: 'sn-other', vip: '10.20.1.100' }));
		const { layout } = build(data);
		expect(layout.parked.has('lb-hidden')).toBe(true);
		const rect = layout.pos.get('lb-hidden');
		expect(rect).toBeTruthy();
		expect(layout.domOrder).toContain('lb-hidden');
		// 주차 스트립: NIC 없는 인스턴스와 같은 x 열, 어떤 존 멤버도 아니다
		expect(rect!.x).toBe(layout.pos.get('vm-orphan-01')!.x);
		for (const members of layout.zoneMembers.values()) expect(members).not.toContain('lb-hidden');
	});
});

describe('블럭 비겹침', () => {
	/** 모든 노드 rect 쌍을 검사한다. 겹치는 쌍의 설명 목록을 돌려준다. */
	function nodeOverlaps(pos: ReadonlyMap<string, Rect>): string[] {
		const e = [...pos.entries()];
		const out: string[] = [];
		for (let i = 0; i < e.length; i++) {
			for (let j = i + 1; j < e.length; j++) {
				const a = e[i][1], b = e[j][1];
				if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) out.push(`${e[i][0]}×${e[j][0]}`);
			}
		}
		return out;
	}

	/** provider→linked 라우터 1개 + solo 망에 붙은 라우터 N개 + 미연결 VM M개 */
	function soloRoutersAndParked(soloRouters: number, parkedVms: number): TopologyData {
		const networks: TopologyNetwork[] = [
			mkNet('net-pub', 'public', '203.0.113.0/24', '203.0.113.1', { external: true }),
			mkNet('net-linked', 'linked-net', '10.10.1.0/24', '10.10.1.1', { project: P }),
			mkNet('net-solo', 'solo-net', '10.10.9.0/24', '10.10.9.1', { project: P }),
		];
		const routers: TopologyRouter[] = [
			{ id: 'rtr-edge', name: 'edge-router', status: 'ACTIVE', external_gateway_network_id: 'net-pub', external_gateway_ips: ['203.0.113.10'], interface_ips: [{ ip_address: '10.10.1.1', subnet_id: 'sn-linked' }], is_distributed: false, is_ha: false, connected_subnet_ids: ['sn-linked'], dvr_subnet_ids: [], project_id: P, enable_snat: true, routes: [] },
		];
		for (let i = 0; i < soloRouters; i++) {
			routers.push({ id: `rtr-s${i}`, name: `solo-router-${String(i).padStart(2, '0')}`, status: 'ACTIVE', external_gateway_network_id: null, external_gateway_ips: [], interface_ips: [{ ip_address: `10.10.9.${i + 2}`, subnet_id: 'sn-solo' }], is_distributed: false, is_ha: false, connected_subnet_ids: ['sn-solo'], dvr_subnet_ids: [], project_id: P, enable_snat: false, routes: [] });
		}
		const instances: TopologyInstance[] = [];
		for (let i = 0; i < parkedVms; i++) {
			instances.push({ id: `vm-orphan-${i}`, name: `orphan-${String(i).padStart(2, '0')}`, status: 'SHUTOFF', project_id: P, network_names: [], ip_addresses: [], flavor_name: 'cpu.2c_4g', image_id: 'img' });
		}
		return { networks, routers, instances, floating_ips: [], load_balancers: [] };
	}

	it('미연결 주차 스트립이 아래 밴드의 라우터와 겹치지 않는다', () => {
		// 주차 스트립을 라우터보다 먼저 배치하면 라우터의 x(존 밖 레인·sweep·lift)와 y(밴드별 routerY)를
		// 알 수 없어 solo 밴드 라우터와 정면으로 겹친다. 실제로 R=2·PK=2 에서 겹침이 발생했었다.
		for (let routers = 1; routers <= 8; routers++) {
			for (let parkedVms = 1; parkedVms <= 6; parkedVms++) {
				const layout = autoLayout(buildGraph(soloRoutersAndParked(routers, parkedVms), { projectId: P, showAll: false }));
				expect(nodeOverlaps(layout.pos), `solo 라우터 ${routers}개 · 미연결 VM ${parkedVms}개`).toEqual([]);
			}
		}
	});

	it('기존 픽스처와 대규모·다밴드 배치 모두 블럭이 겹치지 않는다', () => {
		const cases: Array<[string, CanvasGraph]> = [
			['픽스처(사용자)', buildGraph(makeFixture(), { projectId: P, showAll: false })],
			['픽스처(관리자 전체)', buildGraph(makeFixture(), { projectId: null, showAll: true })],
			['대규모(망 60·VM 600)', buildGraph(makeLargeTenantData(), { projectId: P, showAll: false })],
		];
		for (const [label, graph] of cases) expect(nodeOverlaps(autoLayout(graph).pos), label).toEqual([]);
	});
});

describe('존 밖 라우터 레인', () => {
	/** provider 가 넓고 tenant 밴드가 좁으며, 어느 존에도 속하지 않는 라우터가 있는 형태 */
	function wideProviderZeroRouter(nProv: number, nTen: number): TopologyData {
		const networks: TopologyNetwork[] = [];
		const instances: TopologyInstance[] = [];
		for (let i = 0; i < nProv; i++) {
			networks.push(mkNet(`net-p${i}`, `prov-${i}`, `203.0.${i}.0/24`, `203.0.${i}.1`, i === 0 ? { external: true } : { shared: true }));
			instances.push(mkInst(`vm-p${i}`, `p${i}-01`, 'ACTIVE', [[`net-p${i}`, `203.0.${i}.50`, `p${i}:00:50`]]));
		}
		for (let i = 0; i < nTen; i++) {
			networks.push(mkNet(`net-t${i}`, `ten-${i}`, `10.${i}.0.0/24`, `10.${i}.0.1`, { project: P }));
			for (let j = 0; j < 6; j++) instances.push(mkInst(`vm-t${i}-${j}`, `t${i}-${j}`, 'ACTIVE', [[`net-t${i}`, `10.${i}.0.${10 + j}`, `t${i}:0${j}:10`]]));
		}
		const tenSubs = Array.from({ length: nTen }, (_, i) => `sn-t${i}`);
		const routers: TopologyRouter[] = [
			{ id: 'rtr-gw', name: 'gw-router', status: 'ACTIVE', external_gateway_network_id: 'net-p0', external_gateway_ips: ['203.0.0.10'], interface_ips: tenSubs.map((sn, i) => ({ ip_address: `10.${i}.0.1`, subnet_id: sn })), is_distributed: false, is_ha: false, connected_subnet_ids: tenSubs, dvr_subnet_ids: [], project_id: P, enable_snat: true, routes: [] },
			// 인터페이스가 하나도 없어 어떤 존에도 속하지 않는다 → 존 밖 레인으로 간다
			{ id: 'rtr-zero', name: 'zero-router', status: 'ACTIVE', external_gateway_network_id: 'net-p0', external_gateway_ips: ['203.0.0.11'], interface_ips: [], is_distributed: false, is_ha: false, connected_subnet_ids: [], dvr_subnet_ids: [], project_id: P, enable_snat: true, routes: [] },
		];
		return { networks, routers, instances, floating_ips: [], load_balancers: [] };
	}

	it('존에 속하지 않는 라우터는 좁은 밴드가 중앙 정렬된 뒤에도 존 안에 갇히지 않는다', () => {
		// 레인 x 를 중앙 정렬 **이전** 폭(b.width)으로 잡으면, 밴드가 최광폭이 아닐 때 레인이 밴드 안쪽에 떨어진다.
		// provider 7 · tenant 2 에서 rtr-zero 가 net-t1 존에 완전히 포섭되던 결함의 회귀 테스트.
		for (const [nProv, nTen] of [[7, 2], [5, 1], [10, 1], [3, 2]] as const) {
			const graph = buildGraph(wideProviderZeroRouter(nProv, nTen), { projectId: P, showAll: false });
			const layout = autoLayout(graph);
			const { zones } = computeGeometry(graph, layout);
			const r = layout.pos.get('rtr-zero')!;
			for (const [nid, zone] of zones) {
				if ((layout.zoneMembers.get(nid) ?? []).includes('rtr-zero')) continue;
				const encloses = r.x >= zone.x && r.y >= zone.y && r.x + r.w <= zone.x + zone.w && r.y + r.h <= zone.y + zone.h;
				expect(encloses, `provider ${nProv} · tenant ${nTen} 에서 rtr-zero 가 ${nid} 존에 갇힘`).toBe(false);
			}
		}
	});
});

describe('resolveManualOverlap', () => {
	it('수동 노드만 움직여 겹침을 없애고, 자동 배치 노드는 그대로 둔다', () => {
		const graph = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const layout = autoLayout(graph);
		const before = new Map([...layout.pos].map(([id, r]) => [id, { ...r }]));
		const target = layout.pos.get('vm-web-01')!;
		// vm-web-02 를 vm-web-01 위로 정확히 겹쳐 놓는다
		layout.pos.set('vm-web-02', { ...layout.pos.get('vm-web-02')!, x: target.x + 8, y: target.y + 8 });
		const moves = resolveManualOverlap(layout.pos, ['vm-web-02']);
		expect(Object.keys(moves)).toEqual(['vm-web-02']);
		// 자동 노드는 한 칸도 움직이지 않았다
		for (const [id, r] of layout.pos) {
			if (id === 'vm-web-02') continue;
			expect({ id, x: r.x, y: r.y }).toEqual({ id, x: before.get(id)!.x, y: before.get(id)!.y });
		}
		// 겹침이 사라졌다
		const moved = layout.pos.get('vm-web-02')!;
		for (const [id, r] of layout.pos) {
			if (id === 'vm-web-02') continue;
			expect(moved.x < r.x + r.w && r.x < moved.x + moved.w && moved.y < r.y + r.h && r.y < moved.y + moved.h, `${id} 와 겹침`).toBe(false);
		}
	});

	it('같은 지점에 여러 개를 쌓아도 전부 흩어지고 결과가 결정론적이다', () => {
		const ids = ['vm-web-02', 'vm-app-01', 'vm-app-02', 'vm-monitor-01', 'vm-lab-01'];
		const run = () => {
			const layout = autoLayout(buildGraph(makeFixture(), { projectId: P, showAll: false }));
			const t = layout.pos.get('vm-web-01')!;
			ids.forEach((id, i) => layout.pos.set(id, { ...layout.pos.get(id)!, x: t.x + i, y: t.y + i }));
			const moves = resolveManualOverlap(layout.pos, ids);
			const e = [...layout.pos.entries()];
			let overlaps = 0;
			for (let i = 0; i < e.length; i++) {
				for (let j = i + 1; j < e.length; j++) {
					const a = e[i][1], b = e[j][1];
					if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) overlaps++;
				}
			}
			return { moves, overlaps };
		};
		const first = run(), second = run();
		expect(first.overlaps).toBe(0);
		expect(second.moves).toEqual(first.moves);
	});

	it('사방이 동일 거리로 비어 있으면 아래를 고른다(계층은 제약이 아니라 타이브레이크)', () => {
		// 막는 블럭이 하나뿐이면 상·하·좌·우 첫 빈 자리가 모두 같은 거리다. 그때 아래를 골라야 한다.
		// (거리가 다르면 더 가까운 쪽을 고른다 — 계층은 제약이 아니므로 위로 갈 수도 있다)
		const pos = new Map<string, Rect>([
			['blocker', { x: 0, y: 0, w: 100, h: 100 }],
			['movable', { x: 0, y: 0, w: 100, h: 100 }],
		]);
		const moves = resolveManualOverlap(pos, ['movable']);
		expect(moves.movable).toBeDefined();
		expect(moves.movable.x).toBe(0);
		expect(moves.movable.y).toBeGreaterThan(0);
		expect(pos.get('movable')!.y).toBeGreaterThanOrEqual(100);
	});

	it('MAX_RING 안에 빈 자리가 없으면 원위치를 유지한다(사용자가 다시 옮길 수 있다)', () => {
		// 이동 대상보다 훨씬 큰 블럭이 사방을 막으면 링 탐색이 끝까지 가도 자리를 못 찾는다.
		const pos = new Map<string, Rect>([
			['wall', { x: -100000, y: -100000, w: 200000, h: 200000 }],
			['movable', { x: 0, y: 0, w: 100, h: 100 }],
		]);
		const moves = resolveManualOverlap(pos, ['movable']);
		expect(moves).toEqual({});
		expect(pos.get('movable')).toEqual({ x: 0, y: 0, w: 100, h: 100 });
	});

	it('applyManualPositions 는 화면 좌표만 밀어내고 반환값은 사용자 의도 좌표를 유지한다', () => {
		const graph = buildGraph(makeFixture(), { projectId: P, showAll: false });
		const layout = autoLayout(graph);
		const target = layout.pos.get('vm-web-01')!;
		const intent = { x: target.x + 8, y: target.y + 8 };
		const pruned = applyManualPositions(layout, { 'vm-web-02': { ...intent } });
		const shown = layout.pos.get('vm-web-02')!;
		// 화면에는 겹치지 않는 가까운 자리를 보여준다
		expect(shown.x < target.x + target.w && target.x < shown.x + shown.w
			&& shown.y < target.y + target.h && target.y < shown.y + shown.h).toBe(false);
		expect({ x: shown.x, y: shown.y }).not.toEqual(intent);
		// 저장 대상은 놓은 자리 그대로다 — 해소 결과를 저장하면 구조가 바뀔 때마다 핀이 걸어간다(아래 회귀 테스트)
		expect(pruned['vm-web-02']).toEqual(intent);
	});

	it('의도 좌표를 저장하면 구조가 바뀌어도 핀이 누적 이동하지 않는다', () => {
		// net-web 에 VM 을 늘려 자동 배치를 밀어낸다 → 수동 핀 주변 점유가 매번 달라진다
		const fixtureWith = (n: number) => {
			const d = makeFixture();
			const proto = d.instances.find((i) => i.id === 'vm-web-01')!;
			for (let k = 0; k < n; k++) {
				d.instances.push({
					...structuredClone(proto),
					id: `vm-extra-${k}`,
					name: `extra-${String(k).padStart(2, '0')}`,
					ip_addresses: proto.ip_addresses.map((a, i) => ({ ...a, addr: `10.10.1.${180 + k}`, port_id: `port-extra-${k}-eth${i}` })),
				});
			}
			return d;
		};
		const layoutOf = (n: number) => autoLayout(buildGraph(fixtureWith(n), { projectId: P, showAll: false }));
		const t = layoutOf(0).pos.get('vm-web-01')!;
		const intent = { x: t.x + 8, y: t.y + 8 };

		// 현재 계약(의도 저장): 저장값은 절대 변하지 않는다
		for (let n = 0; n <= 4; n++) {
			const pruned = applyManualPositions(layoutOf(n), { 'vm-web-02': { ...intent } });
			expect(pruned['vm-web-02'], `VM+${n}`).toEqual(intent);
		}

		// 되먹임 계약(해소 결과 저장)이라면 핀이 걸어간다 — 이 테스트가 그 회귀를 잡는다
		let fed = { ...intent };
		const trail: string[] = [];
		for (let n = 0; n <= 4; n++) {
			const l = layoutOf(n);
			applyManualPositions(l, { 'vm-web-02': { ...fed } });
			const shown = l.pos.get('vm-web-02')!;
			fed = { x: shown.x, y: shown.y };
			trail.push(`${fed.x},${fed.y}`);
		}
		expect(new Set(trail).size, `되먹이면 핀이 이동한다: ${trail.join(' → ')}`).toBeGreaterThan(1);
		expect(fed).not.toEqual(intent);
	});

	it('같은 의도 좌표는 같은 구조에서 항상 같은 자리로 해소된다(멱등)', () => {
		const build = () => autoLayout(buildGraph(makeFixture(), { projectId: P, showAll: false }));
		const a = build(), b = build();
		const t = a.pos.get('vm-web-01')!;
		const intent = { x: t.x + 8, y: t.y + 8 };
		applyManualPositions(a, { 'vm-web-02': { ...intent } });
		applyManualPositions(b, { 'vm-web-02': { ...intent } });
		expect(a.pos.get('vm-web-02')).toEqual(b.pos.get('vm-web-02'));
	});
});

describe('깊이 계층(provider 로부터의 라우터 홉)', () => {
	const rtr = (id: string, ext: string | null, subs: string[]): TopologyRouter => ({
		id, name: id, status: 'ACTIVE', external_gateway_network_id: ext, external_gateway_ips: ext ? ['203.0.113.9'] : [],
		interface_ips: subs.map((sn, i) => ({ ip_address: `10.${i}.0.1`, subnet_id: sn })),
		is_distributed: false, is_ha: false, connected_subnet_ids: subs, dvr_subnet_ids: [], project_id: P,
		enable_snat: Boolean(ext), routes: [],
	});

	/** public → d1·d1b → d2·d2b → d3 사슬 + 깊이마다 lateral 라우터 + 도달 불가 섬 + 행 교차/행 내부 멀티 NIC */
	function makeDepthChainData(): TopologyData {
		const networks: TopologyNetwork[] = [
			mkNet('net-pub', 'public', '203.0.113.0/24', '203.0.113.1', { external: true }),
			mkNet('net-d1', 'd1-net', '10.1.0.0/24', '10.1.0.1', { project: P }),
			mkNet('net-d1b', 'd1b-net', '10.11.0.0/24', '10.11.0.1', { project: P }),
			mkNet('net-d2', 'd2-net', '10.2.0.0/24', '10.2.0.1', { project: P }),
			mkNet('net-d2b', 'd2b-net', '10.22.0.0/24', '10.22.0.1', { project: P }),
			mkNet('net-d3', 'd3-net', '10.3.0.0/24', '10.3.0.1', { project: P }),
			mkNet('net-i1', 'i1-net', '10.9.0.0/24', '10.9.0.1', { project: P }),
			mkNet('net-i2', 'i2-net', '10.99.0.0/24', '10.99.0.1', { project: P }),
		];
		const routers: TopologyRouter[] = [
			rtr('rtr-edge', 'net-pub', ['sn-d1', 'sn-d1b']),   // m=0, 더 깊은 망 보유 → 행 1
			rtr('rtr-lat1', null, ['sn-d1', 'sn-d1b']),        // 전부 깊이 1 → 행 1 (lateral)
			rtr('rtr-h2', null, ['sn-d1', 'sn-d2', 'sn-d2b']), // m=1, 더 깊은 망 보유 → 행 2
			rtr('rtr-lat2', null, ['sn-d2', 'sn-d2b']),        // 전부 깊이 2 → 행 2 (lateral)
			rtr('rtr-h3', null, ['sn-d2', 'sn-d3']),           // m=2, 더 깊은 망 보유 → 행 3
			rtr('rtr-isl', null, ['sn-i1', 'sn-i2']),          // provider 에 닿지 않음 → 독립 행
		];
		const instances: TopologyInstance[] = [
			mkInst('vm-d1-01', 'd1-01', 'ACTIVE', [['net-d1', '10.1.0.11', 'd1:00:11']]),
			mkInst('vm-d2-01', 'd2-01', 'ACTIVE', [['net-d2', '10.2.0.11', 'd2:00:11']]),
			mkInst('vm-d2b-01', 'd2b-01', 'ACTIVE', [['net-d2b', '10.22.0.11', 'd2:0b:11']]),
			mkInst('vm-d3-01', 'd3-01', 'ACTIVE', [['net-d3', '10.3.0.11', 'd3:00:11']]),
			// 행을 가로지르는 멀티 NIC(깊이 1 + 깊이 2)과 같은 행 안의 멀티 NIC(깊이 2 + 깊이 2)
			mkInst('vm-span-12', 'span-12', 'ACTIVE', [['net-d1', '10.1.0.31', 'd1:00:31'], ['net-d2', '10.2.0.31', 'd2:00:31']]),
			mkInst('vm-span-2b', 'span-2b', 'ACTIVE', [['net-d2', '10.2.0.41', 'd2:00:41'], ['net-d2b', '10.22.0.41', 'd2:0b:41']]),
			// 행 1 의 **마지막** 존과 행 2 의 **첫** 존을 무는 VM — adjPairs 를 행 경계 너머로 만들면 여기서 잘못된 경계 컬럼이 생긴다
			mkInst('vm-span-edge', 'span-edge', 'ACTIVE', [['net-d1b', '10.11.0.51', 'd1:0b:51'], ['net-d2', '10.2.0.51', 'd2:00:51']]),
			mkInst('vm-i1-01', 'i1-01', 'ACTIVE', [['net-i1', '10.9.0.11', 'i1:00:11']]),
		];
		return { networks, routers, instances, floating_ips: [], load_balancers: [] };
	}

	const buildDepth = (data = makeDepthChainData()) => {
		const graph = buildGraph(data, { projectId: P, showAll: false });
		return { graph, layout: autoLayout(graph) };
	};

	it('provider 로부터의 홉 수대로 행이 나뉘고 독립 망은 맨 아래 한 행이다', () => {
		const { layout } = buildDepth();
		const rows = layout.bands.rows;
		expect(rows.map((r) => r.depth)).toEqual([1, 2, 3, null]);
		expect(rows.map((r) => [...r.netIds].sort())).toEqual([
			['net-d1', 'net-d1b'],
			['net-d2', 'net-d2b'],
			['net-d3'],
			['net-i1', 'net-i2'],
		]);
	});

	it('모든 네트워크가 provider 행과 tenant 행에 정확히 한 번씩 담긴다', () => {
		const { graph, layout } = buildDepth();
		const placed = [...layout.order.provider, ...layout.bands.rows.flatMap((r) => r.netIds)];
		expect(new Set(placed).size).toBe(placed.length); // 중복 없음
		expect([...placed].sort()).toEqual(graph.nets.map((n) => n.id).sort());
		// order.lower/solo 별칭이 rows 와 같은 집합을 덮는다(기존 소비자 호환)
		expect([...layout.order.lower, ...layout.order.solo]).toEqual(layout.bands.rows.flatMap((r) => r.netIds));
	});

	it('라우터는 자기 행 레인에 놓인다: 게이트웨이는 더 깊은 쪽 행, lateral 은 자기 깊이 행', () => {
		const { layout } = buildDepth();
		expect(layout.bands.rows.map((r) => r.routerIds)).toEqual([
			['rtr-edge', 'rtr-lat1'],
			['rtr-h2', 'rtr-lat2'],
			['rtr-h3'],
			['rtr-isl'],
		]);
		for (const row of layout.bands.rows) {
			for (const id of row.routerIds) expect(layout.pos.get(id)!.y, id).toBe(row.routerY);
		}
	});

	it('라우터는 자기 행 존의 멤버만 된다 — 다른 행 존을 끌어내리지 않는다', () => {
		const { layout } = buildDepth();
		// rtr-h2 는 net-d1(깊이 1)도 물지만 자기 행은 2 이므로 net-d1 존의 멤버가 아니다
		expect(layout.zoneMembers.get('net-d1')).toEqual(expect.arrayContaining(['rtr-edge', 'rtr-lat1']));
		expect(layout.zoneMembers.get('net-d1')).not.toContain('rtr-h2');
		expect(layout.zoneMembers.get('net-d2')).toEqual(expect.arrayContaining(['rtr-h2', 'rtr-lat2']));
		expect(layout.zoneMembers.get('net-d2')).not.toContain('rtr-h3');
		expect(layout.zoneMembers.get('net-d3')).toContain('rtr-h3');
		expect(layout.zoneMembers.get('net-i1')).toContain('rtr-isl');
	});

	it('행끼리 세로로 겹치지 않고 기하·계층 불변식이 유지된다', () => {
		const { graph, layout } = buildDepth();
		const { zones } = computeGeometry(graph, layout);
		const rows = layout.bands.rows;
		// 행 봉쇄: 다음 행의 라우터 레인(존 rect 상단은 그보다 PAD_T 위)이 앞 행 바닥보다 아래
		for (let i = 0; i < rows.length - 1; i++) {
			const bottom = Math.max(...rows[i].netIds.map((id) => zones.get(id)!).map((z) => z.y + z.h));
			expect(rows[i + 1].routerY - L.PAD_T, `행 ${i} → ${i + 1}`).toBeGreaterThan(bottom);
			expect(rows[i + 1].routerY).toBeGreaterThan(rows[i].tenantY);
		}
		// 거짓 존 겹침: 멤버를 공유하지 않는데 rect 가 겹치는 쌍
		const zids = [...zones.keys()];
		const bad: string[] = [];
		for (let i = 0; i < zids.length; i++) {
			for (let j = i + 1; j < zids.length; j++) {
				const A = layout.zoneMembers.get(zids[i]) ?? [], B = layout.zoneMembers.get(zids[j]) ?? [];
				const a = zones.get(zids[i])!, b = zones.get(zids[j])!;
				if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h && !A.some((x) => B.includes(x))) bad.push(`${zids[i]} x ${zids[j]}`);
			}
		}
		expect(bad).toEqual([]);
		// 비멤버 라우터가 남의 존에 갇히지 않는다
		for (const n of graph.nodes.values()) {
			if (n.kind !== 'router') continue;
			const p = layout.pos.get(n.id)!;
			for (const [nid, z] of zones) {
				if ((layout.zoneMembers.get(nid) ?? []).includes(n.id)) continue;
				expect(p.x >= z.x && p.y >= z.y && p.x + p.w <= z.x + z.w && p.y + p.h <= z.y + z.h, `${n.id}@${nid}`).toBe(false);
			}
		}
		// 잘림 없음
		for (const [id, p] of layout.pos) {
			expect(p.y, id).toBeGreaterThanOrEqual(0);
			expect(p.y + p.h, id).toBeLessThanOrEqual(layout.bands.BOTTOM_Y);
		}
	});

	it('행을 가로지르는 멀티 NIC 은 단일 home(가장 얕은 행), 같은 행이면 경계 컬럼을 만든다', () => {
		const { layout } = buildDepth();
		// 깊이 1·2 를 무는 VM 은 경계 컬럼이 성립하지 않아 얕은 쪽 한 곳에만 속한다
		expect(layout.home.get('vm-span-12')).toEqual(['net-d1']);
		// 행 1 의 마지막 존과 행 2 의 첫 존을 무는 VM 도 마찬가지다(행 경계는 인접이 아니다)
		const rows = layout.bands.rows;
		expect([rows[0].netIds.at(-1), rows[1].netIds[0]]).toEqual(['net-d1b', 'net-d2']);
		expect(layout.home.get('vm-span-edge')).toEqual(['net-d1b']);
		// 같은 행(깊이 2)의 두 망을 무는 VM 은 두 존의 경계 컬럼에 놓인다
		expect(layout.home.get('vm-span-2b')).toEqual(['net-d2', 'net-d2b']);
	});

	it('두 존에 걸친 home 은 언제나 같은 행 안에 있다', () => {
		const { layout } = buildDepth();
		const rowOf = new Map<string, number>();
		layout.bands.rows.forEach((r, i) => r.netIds.forEach((n) => rowOf.set(n, i)));
		for (const [vmId, hm] of layout.home) {
			if (hm.length < 2) continue;
			expect(new Set(hm.map((n) => rowOf.get(n))).size, `${vmId} home=${hm.join('+')}`).toBe(1);
		}
	});

	it('입력 배열 순서를 뒤집어도 같은 결과다(행 구성이 Map 삽입 순서에 의존하지 않는다)', () => {
		const data = makeDepthChainData();
		const reversed: TopologyData = {
			...data,
			networks: [...data.networks].reverse(),
			routers: [...data.routers].reverse(),
			instances: [...data.instances].reverse(),
		};
		const a = buildDepth(data).layout, b = buildDepth(reversed).layout;
		expect(b.bands.rows).toEqual(a.bands.rows);
		expect(b.domOrder).toEqual(a.domOrder);
		expect([...b.pos.entries()].sort()).toEqual([...a.pos.entries()].sort());
	});

	it('보이지 않는 다른 프로젝트 망을 경유해도 사슬이 끊기지 않는다', () => {
		// net-pub → rtr-a → net-hidden(타 프로젝트) → rtr-b → net-tgt.
		// 도달성을 가시 망으로만 계산하면 net-tgt 이 독립 망으로 오분류된다.
		const data: TopologyData = {
			networks: [
				mkNet('net-pub', 'public', '203.0.113.0/24', '203.0.113.1', { external: true }),
				mkNet('net-hidden', 'hidden-net', '10.5.0.0/24', '10.5.0.1', { project: OTHER }),
				mkNet('net-tgt', 'target-net', '10.6.0.0/24', '10.6.0.1', { project: P }),
			],
			routers: [rtr('rtr-a', 'net-pub', ['sn-hidden']), rtr('rtr-b', null, ['sn-hidden', 'sn-tgt'])],
			instances: [mkInst('vm-tgt-01', 'tgt-01', 'ACTIVE', [['net-tgt', '10.6.0.11', 't6:00:11']])],
			floating_ips: [], load_balancers: [],
		};
		const graph = buildGraph(data, { projectId: P, showAll: false });
		const layout = autoLayout(graph);
		expect(layout.order.lower).toEqual(['net-tgt']);
		expect(layout.order.solo).toEqual([]);
		// 가시 망이 없는 rtr-a 때문에 빈 행이 생기지 않는다
		expect(layout.bands.rows.every((r) => r.netIds.length || r.routerIds.length)).toBe(true);
		expect(layout.zoneMembers.get('net-tgt')).toContain('rtr-b');
	});
});


describe('LB 는 멤버 인스턴스 위에 정렬된다', () => {
	/** net-lab(라우터 없는 단일 존)에 VM 4대 + LB 1개. 멤버를 골라 정렬 기준을 판별한다. */
	function build(memberSuffixes: string[]) {
		const data = makeFixture();
		// 판별을 위해 격자가 3컬럼이 되도록 net-lab 에 srv-a..d 를 둔다(gridCols(4) === 3)
		data.instances = data.instances.filter((i) => i.id !== 'vm-lab-01');
		for (const [k, n] of ['a', 'b', 'c', 'd'].entries()) {
			data.instances.push(mkInst(`vm-srv-${n}`, `srv-${n}`, 'ACTIVE', [['net-lab', `10.10.9.1${k}`, `a9:00:1${k}`]]));
		}
		data.load_balancers = [
			mkLb('lb-lab', 'lab-lb', {
				vipNetId: 'net-lab',
				vip: '10.10.9.200',
				members: memberSuffixes.map((n) => ({
					id: `m-${n}`, address: `10.10.9.1${['a', 'b', 'c', 'd'].indexOf(n)}`, protocol_port: 80,
					status: 'ACTIVE', subnet_id: 'sn-lab', pool_id: 'pool-lab', server_id: `vm-srv-${n}`,
				})),
			}),
		];
		const graph = buildGraph(data, { projectId: P, showAll: false });
		const layout = autoLayout(graph);
		return { graph, layout, lb: layout.pos.get('lb-lab')!, vmOf: (n: string) => layout.pos.get(`vm-srv-${n}`)! };
	}

	it('멤버가 여럿이면 가장 왼쪽 멤버의 x 에 맞춘다', () => {
		const { lb, vmOf } = build(['a', 'b']);
		expect(lb).toBeTruthy();
		expect(lb.x).toBe(Math.min(vmOf('a').x, vmOf('b').x));
	});

	it('멤버가 첫 컬럼이 아니면 LB 도 그 컬럼으로 옮겨간다(존 왼쪽 끝 정렬이 아니다)', () => {
		// srv-b·srv-c 는 격자 2·3번째 컬럼이다 → LB 는 srv-b 위로 가야 하고 첫 컬럼(srv-a)이 아니다
		const { lb, vmOf } = build(['b', 'c']);
		expect(lb.x).toBe(vmOf('b').x);
		expect(lb.x).toBeGreaterThan(vmOf('a').x);
	});

	it('멤버가 아래 행에 있어도 같은 컬럼 위에 온다', () => {
		// gridCols(4) === 3 이라 srv-d 는 두 번째 행 첫 컬럼이다
		const { lb, vmOf } = build(['d']);
		expect(vmOf('d').y).toBeGreaterThan(vmOf('a').y);
		expect(lb.x).toBe(vmOf('d').x);
		expect(lb.x).toBe(vmOf('a').x);
	});

	it('LB 는 항상 멤버보다 위에 있고 존 폭을 넘지 않는다', () => {
		for (const members of [['a'], ['b', 'c'], ['d'], ['a', 'b', 'c', 'd']]) {
			const { graph, layout, lb, vmOf } = build(members);
			for (const n of members) expect(lb.y + lb.h, `members=${members}`).toBeLessThanOrEqual(vmOf(n).y);
			// 계층은 유지된다: 스위치 → LB → 인스턴스
			const sw = layout.pos.get('sw:net-lab')!;
			expect(sw.y + sw.h, `members=${members}`).toBeLessThanOrEqual(lb.y);
			// LB 카드가 VM 보다 넓어 마지막 컬럼 멤버에 정렬하면 격자 밖으로 삐져나온다.
			// 그 오버행이 콘텐츠 폭에 반영돼야 **이웃 존**을 침범하지 않는다(멤버를 공유하지 않는 존과 겹치면 거짓 신호다).
			const own = layout.zoneMembers.get('net-lab') ?? [];
			const zone = zoneRectFrom(layout.pos, own)!;
			for (const [nid, mem] of layout.zoneMembers) {
				if (nid === 'net-lab') continue;
				if (mem.some((m) => own.includes(m))) continue; // 경계 컬럼을 공유하는 존은 겹쳐도 정상
				const other = zoneRectFrom(layout.pos, mem);
				if (!other) continue;
				const hit = zone.x < other.x + other.w && other.x < zone.x + zone.w
					&& zone.y < other.y + other.h && other.y < zone.y + zone.h;
				expect(hit, `members=${members} vs ${nid}`).toBe(false);
			}
			void graph;
		}
	});

	it('LB 오버행이 콘텐츠 폭에 반영되어 다음 존과의 간격이 줄지 않는다', () => {
		// LB 카드(264)는 VM(232)보다 넓어 마지막 컬럼 멤버에 정렬하면 격자 오른쪽으로 32px 삐져나온다.
		// 이 오버행을 콘텐츠 폭에 반영하지 않으면 오른쪽 이웃 존이 그만큼 가까이 붙는다.
		const { layout, lb } = build(['c']);
		const lbRight = lb.x + lb.w;
		// 같은 행에서 net-lab 오른쪽에 있는 가장 가까운 존
		let nearest: number | null = null;
		for (const [nid, mem] of layout.zoneMembers) {
			if (nid === 'net-lab') continue;
			const z = zoneRectFrom(layout.pos, mem);
			if (!z || z.x < lbRight) continue;
			if (nearest === null || z.x < nearest) nearest = z.x;
		}
		expect(nearest, '오른쪽 이웃 존이 있어야 판별된다').not.toBeNull();
		// 존 rect 는 콘텐츠에서 PAD_X 만큼 왼쪽으로 넓어지므로, 간격은 ZONE_GAP 이상이어야 한다
		expect(nearest! - lbRight).toBeGreaterThanOrEqual(L.ZONE_GAP);
	});

	it('멤버가 없으면 예전처럼 가운데 정렬한다', () => {
		const { layout, lb } = build([]);
		const sw = layout.pos.get('sw:net-lab')!;
		expect(lb.x + lb.w / 2).toBeCloseTo(sw.x + sw.w / 2, 6);
	});
});
