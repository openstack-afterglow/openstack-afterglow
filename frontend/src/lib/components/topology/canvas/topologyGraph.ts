// 순수 함수: wire payload(TopologyData) → CanvasGraph. DOM 과 Svelte 런타임을 참조하지 않는다.
// 가시성·정렬·NIC 해석 규칙은 레인 뷰 topologyDerivedController 와 동일하다.
// 예외: 로드밸런서 vipNetId 는 역참조 결과가 가시 네트워크일 때만 채택해(컨트롤러보다 엄격) 나머지는 parked 로 둔다.
import type { FloatingIpInfo } from '$lib/types/networks';
import type {
	SubnetDetail,
	TopologyData,
	TopologyNetwork,
	TopologyTraffic,
	TrafficRate,
} from '$lib/types/topology';
import { _ipv4InCidr, byName, cmpArr, edgeIntensity, flowDotCount, flowRate, NO_TELEMETRY_STYLE, normalizeMac, slug, uniq } from './canvasHelpers';
import type {
	CanvasEdge,
	CanvasFip,
	CanvasGraph,
	CanvasNet,
	CanvasNic,
	CanvasNode,
	EdgeStyle,
	LayoutResult,
	LbNode,
	QueryMatch,
	Rect,
	RouterNode,
	RouterPort,
	VmNode,
} from './types';

export interface BuildGraphOpts {
	projectId: string | null;
	showAll: boolean;
}

export const switchId = (netId: string): string => `sw:${netId}`;

function netColor(kind: CanvasNet['kind']): string {
	if (kind === 'external') return 'var(--color-topology-external)';
	if (kind === 'shared') return 'var(--color-topology-shared)';
	return 'var(--color-topology-internal)';
}

function edgeKey(e: Omit<CanvasEdge, 'key'>, nicKey?: string): string {
	return `${e.kind}:${e.from}>${e.to}${nicKey ? ':' + nicKey : ''}`;
}

export function buildGraph(data: TopologyData, opts: BuildGraphOpts): CanvasGraph {
	const { projectId, showAll } = opts;
	const visibleNetworks: TopologyNetwork[] = showAll
		? data.networks
		: data.networks.filter((n) => n.is_external || n.is_shared || (projectId != null && n.project_id === projectId));
	const ownedBy = <T extends { project_id?: string | null }>(items: readonly T[]): T[] =>
		items.filter((item) => projectId == null || item.project_id === projectId);
	const routers = ownedBy(data.routers);
	const instances = ownedBy(data.instances);
	const loadBalancers = ownedBy(data.load_balancers ?? []);

	const ext = visibleNetworks.filter((n) => n.is_external).sort(byName);
	const shr = visibleNetworks.filter((n) => !n.is_external && n.is_shared).sort(byName);
	const int = visibleNetworks.filter((n) => !n.is_external && !n.is_shared).sort(byName);

	// subnet 인덱스와 이름 해석은 전체 네트워크 기준(컨트롤러와 동일), 노드 생성은 가시 네트워크 기준
	const subnetNet = new Map<string, string>();
	const subnetById = new Map<string, SubnetDetail & { netId: string }>();
	for (const n of data.networks) {
		for (const sub of n.subnet_details) {
			subnetNet.set(sub.id, n.id);
			subnetById.set(sub.id, { ...sub, netId: n.id });
		}
	}

	const routersRaw = routers.map((r) => {
		const extNetId = r.external_gateway_network_id || null;
		const intNetIds = uniq(
			r.connected_subnet_ids.map((id) => subnetNet.get(id)).filter((id): id is string => Boolean(id)),
		).filter((id) => id !== extNetId);
		return { raw: r, extNetId, intNetIds };
	});
	const touched = new Set<string>();
	for (const r of routersRaw) {
		if (r.extNetId) touched.add(r.extNetId);
		r.intNetIds.forEach((id) => touched.add(id));
	}

	const nets: CanvasNet[] = [...ext, ...shr, ...int].map((n) => {
		const kind: CanvasNet['kind'] = n.is_external ? 'external' : n.is_shared ? 'shared' : 'internal';
		const tier: CanvasNet['tier'] = kind === 'internal' ? 'tenant' : 'provider';
		return {
			id: n.id,
			name: n.name,
			kind,
			tier,
			status: n.status,
			project_id: n.project_id,
			isolated: tier === 'tenant' && !touched.has(n.id),
			subnets: n.subnet_details,
			cidrs: n.subnet_details.map((x) => x.cidr),
			color: netColor(kind),
			raw: n,
		};
	});
	const netById = new Map(nets.map((n) => [n.id, n]));

	const nodes = new Map<string, CanvasNode>();
	const edges: CanvasEdge[] = [];
	const addEdge = (e: Omit<CanvasEdge, 'key'>, nicKey?: string): CanvasEdge => {
		const edge: CanvasEdge = { ...e, key: edgeKey(e, nicKey) };
		edges.push(edge);
		return edge;
	};

	for (const n of nets) {
		const id = switchId(n.id);
		nodes.set(id, {
			id,
			kind: 'switch',
			netId: n.id,
			name: 'vSwitch-' + slug(n.name),
			role: n.tier === 'provider' ? 'Provider Bridge' : 'Tenant OVS Bridge',
			isolated: n.isolated,
			status: n.status,
			netIds: [n.id],
		});
	}

	for (const r of routersRaw) {
		const ports: RouterPort[] = [];
		if (r.extNetId) ports.push({ label: 'gw', netId: r.extNetId, ip: r.raw.external_gateway_ips?.[0] ?? null, subnet: null });
		r.intNetIds.forEach((nid, i) => {
			const ipi = r.raw.interface_ips.find((x) => subnetNet.get(x.subnet_id) === nid);
			ports.push({ label: `if${i}`, netId: nid, ip: ipi?.ip_address ?? null, subnet: ipi ? (subnetById.get(ipi.subnet_id) ?? null) : null });
		});
		const badges = [
			r.raw.is_distributed && 'DVR',
			r.raw.is_ha && 'HA',
			r.raw.enable_snat && 'SNAT',
			!r.extNetId && '게이트웨이 없음',
		].filter((b): b is string => typeof b === 'string');
		const node: RouterNode = {
			id: r.raw.id,
			kind: 'router',
			name: r.raw.name,
			status: r.raw.status,
			extNetId: r.extNetId,
			intNetIds: r.intNetIds,
			ports,
			badges,
			raw: r.raw,
			netIds: [r.extNetId, ...r.intNetIds].filter((id): id is string => Boolean(id)),
		};
		nodes.set(node.id, node);
		if (r.extNetId && netById.has(r.extNetId)) addEdge({ kind: 'trunk', from: node.id, to: switchId(r.extNetId), netId: r.extNetId });
		for (const nid of r.intNetIds) if (netById.has(nid)) addEdge({ kind: 'trunk', from: node.id, to: switchId(nid), netId: nid });
	}

	const fipByAddr = new Map<string, FloatingIpInfo>(data.floating_ips.map((f) => [f.floating_ip_address, f]));
	const nameToNets = new Map<string, TopologyNetwork[]>();
	for (const n of data.networks) {
		const arr = nameToNets.get(n.name) ?? [];
		arr.push(n);
		nameToNets.set(n.name, arr);
	}
	// 컨트롤러의 resolveNetId 와 동일: 이름 유일 → 즉시, 중복 → CIDR 포함 검사, 실패 → 첫 번째
	const resolveNetId = (name: string, ip: string): string | undefined => {
		const arr = nameToNets.get(name);
		if (!arr?.length) return undefined;
		if (arr.length === 1) return arr[0].id;
		for (const n of arr) for (const s of n.subnet_details) if (_ipv4InCidr(ip, s.cidr)) return n.id;
		return arr[0].id;
	};
	const rankNet = (nid: string): (string | number)[] => {
		const n = netById.get(nid);
		return [n?.tier === 'provider' ? 0 : 1, n?.name ?? '', nid];
	};

	for (const inst of instances) {
		type Group = { netId: string; ips: string[]; mac: string | null; portId: string | null; fips: CanvasFip[] };
		const groups = new Map<string, Group>();
		for (const a of inst.ip_addresses) {
			if (a.type === 'floating') continue;
			const nid = a.network_id || resolveNetId(a.network_name, a.addr);
			if (!nid || !netById.has(nid)) continue;
			// port_id 가 있으면 포트 단위, 없으면 네트워크 단위로 NIC 을 묶는다
			const key = a.port_id ?? 'net:' + nid;
			let g = groups.get(key);
			if (!g) {
				g = { netId: nid, ips: [], mac: a.mac_addr ?? null, portId: a.port_id ?? null, fips: [] };
				groups.set(key, g);
			}
			g.ips.push(a.addr);
		}
		const nics: CanvasNic[] = [...groups.values()]
			.sort((a, b) => cmpArr(rankNet(a.netId), rankNet(b.netId)) || a.ips[0].localeCompare(b.ips[0]))
			.map((g, idx) => ({ ...g, idx, rowIdx: 0, label: `eth${idx}`, ip: g.ips[0], key: `${inst.id}|${g.netId}|${idx}` }));
		for (const a of inst.ip_addresses) {
			if (a.type !== 'floating') continue;
			const f = fipByAddr.get(a.addr);
			const owner = nics.find((n) => f?.fixed_ip_address != null && n.ips.includes(f.fixed_ip_address)) ?? nics[0];
			if (!owner) continue;
			owner.fips.push({
				addr: a.addr,
				netId: f?.floating_network_id ?? a.network_id ?? null,
				fixed: f?.fixed_ip_address ?? null,
				status: f?.status ?? null,
			});
		}
		let row = 0;
		for (const nic of nics) {
			nic.rowIdx = row;
			row += 1 + nic.fips.length;
		}
		const node: VmNode = {
			id: inst.id,
			kind: 'vm',
			name: inst.name,
			status: inst.status,
			nics,
			rows: Math.max(1, row),
			netIds: uniq(nics.map((n) => n.netId)),
			parked: nics.length === 0,
			meta: { flavor_name: inst.flavor_name ?? null, image_id: inst.image_id ?? null, project_id: inst.project_id ?? null },
			isDatabase: inst.is_database === true,
			raw: inst,
		};
		nodes.set(node.id, node);
		for (const nic of nics) {
			addEdge({ kind: 'cable', from: inst.id, to: switchId(nic.netId), netId: nic.netId, nic, portId: nic.portId, instanceId: inst.id }, nic.key);
			// Floating IP 선은 그 IP 가 속한 외부 네트워크의 가상 스위치로 직접 잇는다
			// (합성 코어 노드를 없앤 뒤로 외부망 자체가 인터넷 경계를 나타낸다).
			for (const f of nic.fips) {
				const target = f.netId && netById.has(f.netId) ? f.netId : null;
				if (!target) continue;
				addEdge({ kind: 'fip', from: inst.id, to: switchId(target), netId: target, nic, fip: f, instanceId: inst.id }, `${nic.key}|fip|${f.addr}`);
			}
		}
	}

	for (const lb of loadBalancers) {
		// vipNetId: vip_network_id 가 가시 네트워크면 그대로, 아니면 vip_subnet_id 로 역참조한다.
		// subnetNet 은 전체 네트워크 인덱스이므로 역참조 결과도 가시 네트워크일 때만 채택한다(아니면 parked → '미연결' 스트립).
		let vipNetId: string | null = null;
		if (lb.vip_network_id && netById.has(lb.vip_network_id)) {
			vipNetId = lb.vip_network_id;
		} else {
			const resolved = lb.vip_subnet_id ? subnetNet.get(lb.vip_subnet_id) : undefined;
			vipNetId = resolved && netById.has(resolved) ? resolved : null;
		}
		const node: LbNode = {
			id: lb.id,
			kind: 'lb',
			name: lb.name,
			status: lb.provisioning_status,
			operating: lb.operating_status,
			vipNetId,
			vip: lb.vip_address,
			listeners: lb.listeners ?? [],
			members: lb.members ?? [],
			memberVmIds: uniq((lb.members ?? []).map((m) => m.server_id).filter((id): id is string => Boolean(id))),
			raw: lb,
			netIds: vipNetId ? [vipNetId] : [],
			parked: !vipNetId,
		};
		nodes.set(node.id, node);
		if (vipNetId) addEdge({ kind: 'lbvip', from: lb.id, to: switchId(vipNetId), netId: vipNetId, lbId: lb.id });
	}

	const edgesByNode = new Map<string, CanvasEdge[]>();
	const push = (id: string, e: CanvasEdge) => {
		const arr = edgesByNode.get(id) ?? [];
		arr.push(e);
		edgesByNode.set(id, arr);
	};
	for (const e of edges) {
		push(e.from, e);
		push(e.to, e);
	}
	return { nets, netById, nodes, edges, edgesByNode, subnetNet, subnetById, fipByAddr };
}

/** tenant 존 순서에 따라 내부 네트워크 색을 두 톤으로 교차 배정한다(인접 존 구분용). */
export function assignTenantColors(graph: CanvasGraph, lowerOrder: readonly string[]): void {
	lowerOrder.forEach((nid, i) => {
		const n = graph.netById.get(nid);
		if (n && n.kind === 'internal') {
			n.color = i % 2 === 0 ? 'var(--color-topology-internal)' : 'var(--color-topology-internal-2)';
		}
	});
}

export function colorOfNet(graph: CanvasGraph | null | undefined, netId: string | null | undefined): string {
	return (netId && graph?.netById.get(netId)?.color) || 'var(--color-state-neutral)';
}

/** LB 활성화 시 지연 생성하는 멤버 곡선. VIP 네트워크의 NIC 에 앵커하고 없으면 첫 NIC 을 쓴다. */
export function buildMemberEdges(graph: CanvasGraph, lbId: string, pos?: ReadonlyMap<string, Rect>): CanvasEdge[] {
	const lb = graph.nodes.get(lbId);
	if (!lb || lb.kind !== 'lb') return [];
	const out: CanvasEdge[] = [];
	for (const m of lb.members) {
		const vm = m.server_id ? graph.nodes.get(m.server_id) : undefined;
		if (!vm || vm.kind !== 'vm') continue;
		if (pos && !pos.has(vm.id)) continue;
		const nic = vm.nics.find((n) => n.netId === lb.vipNetId) ?? vm.nics[0];
		if (!nic) continue;
		out.push({ kind: 'lbmember', from: lb.id, to: vm.id, netId: lb.vipNetId ?? nic.netId, toNic: nic, lbId: lb.id, memberId: m.id, key: `lbmember:${lb.id}>${vm.id}:${m.id}` });
	}
	return out;
}

/**
 * 검색어 해석: CIDR(포함 검사) → IP prefix → MAC(콜론 유무 무관) → 이름 포함.
 * 빈 검색어는 null. 매칭된 네트워크의 스위치는 항상 nodes 에 포함된다.
 */
export function matchesQuery(graph: CanvasGraph, raw: string): QueryMatch | null {
	const q = raw.trim().toLowerCase();
	if (!q) return null;
	const nodes = new Set<string>();
	const nets = new Set<string>();
	const isCidr = /^\d+\.\d+\.\d+\.\d+\/\d+$/.test(q);
	const isIpish = /^[\d.]+$/.test(q);
	const macQ = normalizeMac(q);
	const isMac = !isIpish && macQ.length >= 4 && /^[0-9a-f:.\-]+$/.test(q);
	for (const n of graph.nets) {
		const hit = isCidr
			? n.cidrs.some((c) => c === q || _ipv4InCidr(c.split('/')[0], q))
			: isIpish
				? n.cidrs.some((c) => c.includes(q))
				: isMac
					? false
					: n.name.toLowerCase().includes(q) || n.cidrs.some((c) => c.includes(q));
		if (hit) {
			nets.add(n.id);
			nodes.add(switchId(n.id));
		}
	}
	for (const node of graph.nodes.values()) {
		let hit = false;
		if (node.kind === 'vm') {
			if (isCidr) hit = node.nics.some((nic) => nic.ips.some((ip) => _ipv4InCidr(ip, q)) || nic.fips.some((f) => _ipv4InCidr(f.addr, q)));
			else if (isIpish) hit = node.nics.some((nic) => nic.ips.some((ip) => ip.startsWith(q)) || nic.fips.some((f) => f.addr.startsWith(q)));
			else if (isMac) hit = node.nics.some((nic) => Boolean(nic.mac) && normalizeMac(nic.mac).includes(macQ));
			else hit = node.name.toLowerCase().includes(q);
		} else if (node.kind === 'router') {
			hit = isCidr
				? node.ports.some((p) => Boolean(p.ip) && _ipv4InCidr(p.ip as string, q))
				: isIpish
					? node.ports.some((p) => Boolean(p.ip) && (p.ip as string).startsWith(q))
					: isMac
						? false
						: node.name.toLowerCase().includes(q);
		} else if (node.kind === 'lb') {
			hit = isCidr
				? Boolean(node.vip) && _ipv4InCidr(node.vip as string, q)
				: isIpish
					? (node.vip ?? '').startsWith(q)
					: isMac
						? false
						: node.name.toLowerCase().includes(q);
		} else if (node.kind === 'switch') {
			if (!isCidr && !isIpish && !isMac && node.name.toLowerCase().includes(q)) {
				hit = true;
				nets.add(node.netId);
			}
		}
		if (hit) nodes.add(node.id);
	}
	for (const nid of nets) nodes.add(switchId(nid));
	return { nodes, nets };
}

/**
 * 엣지별 텔레메트리 소스.
 * cable → interfaces[portId], 없으면 같은 인스턴스+네트워크 인터페이스 합산
 * trunk → 그 트렁크가 **실어 나르는 네트워크들**의 합산. 라우터 exporter 가 없어 링크 자체는 계측되지 않는다.
 *   - 라우터 → 하위(tenant) 스위치: 그 하위 네트워크 하나(networks[netId]).
 *   - 라우터 → provider 스위치(uplink): 그 **라우터가 직접 무는 tenant 네트워크들**의 합.
 *     provider 네트워크 전체 합(networks[providerId])을 쓰면 provider 에 붙은 라우터 수만큼 같은 값이
 *     복제돼, 다른 테넌트 트래픽까지 자기 uplink 로 주장하게 된다.
 * lbvip → load_balancers[lbId]
 */
export function edgeRate(
	e: CanvasEdge,
	traffic: TopologyTraffic | null | undefined,
	graph: CanvasGraph,
): TrafficRate | null {
	const t = traffic;
	if (!t) return null;
	switch (e.kind) {
		case 'cable': {
			if (e.portId && t.interfaces?.[e.portId]) return t.interfaces[e.portId];
			let acc: TrafficRate | null = null;
			for (const v of Object.values(t.interfaces ?? {})) {
				if (v.instance_id === e.instanceId && v.network_id === e.netId) {
					acc = acc ?? { rx_bps: 0, tx_bps: 0 };
					acc.rx_bps += v.rx_bps;
					acc.tx_bps += v.tx_bps;
				}
			}
			return acc;
		}
		case 'trunk':
			return sumNetworks(t, trunkNetIds(e, graph));
		case 'lbvip':
			return e.lbId ? (t.load_balancers?.[e.lbId] ?? null) : null;
		default:
			return null;
	}
}

/** 대상 스위치가 external 또는 shared provider tier인 트렁크인지 판별한다. */
export function isUplinkTrunk(e: Pick<CanvasEdge, 'kind' | 'from' | 'netId'>, graph: CanvasGraph): boolean {
	if (e.kind !== 'trunk') return false;
	return graph.nodes.get(e.from)?.kind === 'router' && graph.netById.get(e.netId)?.tier === 'provider';
}

/**
 * 트렁크가 실어 나르는 네트워크 id 목록.
 * provider uplink는 그 라우터가 직접 무는 tenant 네트워크들, 그 밖에는 트렁크가 꽂힌 네트워크 하나다.
 * shared provider는 external_gateway_network_id 없이 일반 interface로 연결될 수 있으므로 extNetId만 보면 안 된다.
 * 하위 tenant 네트워크가 하나도 없는 uplink는 실어 나를 것이 없으므로 빈 목록이다(= 데이터 없음).
 */
export function trunkNetIds(e: Pick<CanvasEdge, 'kind' | 'from' | 'netId'>, graph: CanvasGraph): string[] {
	if (e.kind !== 'trunk') return [];
	const from = graph.nodes.get(e.from);
	if (!isUplinkTrunk(e, graph) || from?.kind !== 'router') return [e.netId];
	return from.intNetIds.filter((id) => graph.netById.get(id)?.tier === 'tenant');
}

function sumNetworks(traffic: TopologyTraffic, netIds: readonly string[]): TrafficRate | null {
	let acc: TrafficRate | null = null;
	for (const id of netIds) {
		const v = traffic.networks?.[id];
		if (!v) continue;
		acc = acc ?? { rx_bps: 0, tx_bps: 0 };
		acc.rx_bps += v.rx_bps;
		acc.tx_bps += v.tx_bps;
	}
	return acc;
}

/**
 * 네트워크 값 하나에서 **스위치를 실제로 통과한 양**을 추정한다.
 *
 * `traffic.networks[N]` 은 그 망에 붙은 NIC 들의 합이므로
 *
 *   rx = EW + IN,  tx = EW + OUT     (EW = 망 내부 통신, IN/OUT = 남북 유입·유출)
 *
 * 이고 실제 통과량은 `T = EW + IN + OUT = rx + tx − EW` 다. 동서 트래픽은 보내는 쪽 tx 와
 * 받는 쪽 rx 로 **두 번** 잡히기 때문이다. `0 ≤ EW ≤ min(rx,tx)` 이므로 T 는
 *
 *   max(rx,tx)  ≤  T  ≤  rx + tx
 *
 * 로만 좁혀진다 — 미지수 3개에 식 2개라 EW 를 계측으로 가를 수 없다(`flowStreams` 와 같은 한계).
 * 두 끝값은 각각 최악 2배 틀린다: 순수 동서에서 `rx+tx` 가 2배 과대(실측 2026-09-13:
 * dmslab 3-tier 235k/230k → 465k), 양방향 남북에서 `max` 가 2배 과소다.
 * 그래서 구간의 **중점**을 쓴다 — 과대 1.5배·과소 1.33배로 최악 오차가 가장 작고,
 * 로그축에서 1.5배는 0.18 decade(굵기 0.08px)라 눈에 띄지 않는다.
 */
export function switchThroughput(rate: { rx_bps: number; tx_bps: number }): number {
	return Math.max(rate.rx_bps, rate.tx_bps) + Math.min(rate.rx_bps, rate.tx_bps) / 2;
}

/**
 * 강도 인코딩(굵기·불투명도·흐름)에 쓸 스칼라.
 *
 * - **케이블과 그 밖**: `rx + tx`. NIC 하나의 두 방향은 진짜로 서로 다른 방향이라 이중 계상이 없다.
 * - **트렁크**: `switchThroughput`.
 */
export function intensityBps(kind: CanvasEdge['kind'], rate: { rx_bps: number; tx_bps: number }): number {
	return kind === 'trunk' ? switchThroughput(rate) : rate.rx_bps + rate.tx_bps;
}

/**
 * 트렁크 강도 스칼라. **망별로 추정한 뒤 더한다** — 합산 뒤 추정하면 안 된다.
 *
 * `switchThroughput` 은 선형이 아니라 두 순서가 다른 값을 낸다. 반례: 라우터가 순수 다운로드
 * 망(rx 10M/tx 0)과 순수 업로드 망(rx 0/tx 10M)을 물면 먼저 합산했을 때 {10M, 10M} 이 되어
 * 동서 통신으로 오인되고 15M 으로 추정되지만, 실제 uplink 통과량은 20M 이다. 망마다 따로 추정하면
 * 10M + 10M = 20M 으로 정확하다.
 */
export function trunkIntensityBps(
	e: CanvasEdge,
	traffic: TopologyTraffic | null | undefined,
	graph: CanvasGraph,
): number | null {
	let acc: number | null = null;
	for (const id of trunkNetIds(e, graph)) {
		const v = traffic?.networks?.[id];
		if (!v) continue;
		acc = (acc ?? 0) + switchThroughput(v);
	}
	return acc;
}

export function edgeStyle(e: CanvasEdge, traffic: TopologyTraffic | null | undefined, graph: CanvasGraph): EdgeStyle {
	const rate = edgeRate(e, traffic, graph);
	// 트렁크는 `edgeRate` 가 이미 합쳐 놓은 값이 아니라 망별 추정의 합을 쓴다(`trunkIntensityBps`).
	const bps = e.kind === 'trunk' ? trunkIntensityBps(e, traffic, graph) : rate ? rate.rx_bps + rate.tx_bps : null;
	// 계측이 없을 때만 NO_TELEMETRY_STYLE 이다. 0 bps 는 "쟀더니 0" 이라 edgeIntensity 의 하한으로 간다.
	let { opacity, width } = bps == null ? { ...NO_TELEMETRY_STYLE } : edgeIntensity(bps);
	let dash: string | null = null;
	if (e.kind === 'fip') { width = 1.5; opacity = opacity * 0.6; dash = '4 3'; }
	if (e.kind === 'lbvip') { width = 2; opacity = 0.75; }
	if (e.kind === 'lbmember') { width = 1.5; opacity = 0.75; dash = '4 3'; }
	// 트렁크 굵기 하한(구 `Math.max(2.5, width)`)은 없다. 하한이 스케일 상단을 눌러
	// **모든 트렁크가 2.5px 로 같아지고** 가장 바쁜 케이블보다도 굵어져 위계가 뒤집혔다.
	const from = graph.nodes.get(e.from);
	if (from?.kind === 'vm' && from.status === 'SHUTOFF') dash = '6 4';
	if (from?.kind === 'router' && from.status === 'DOWN') dash = '6 4';
	return { opacity, width, dash, bps, rate };
}

/**
 * 이 미만이면 흐름을 그리지 않는다 — "사용량 없음" 을 0 이 아니라 "점 없음" 으로 읽게 한다.
 * 실측(2026-09-13)에서 NIC 43개 중 `1e5` 이상은 4개뿐이라 흐름이 사실상 보이지 않았다.
 * `1e4` 는 같은 표본에서 21/43 이 이 문턱을 넘는다.
 *
 * **다만 화면에 실제로 점이 붙는 엣지 수는 이 문턱이 아니라 `rebuildFlow` 의 전역 점 예산(60)이
 * 정한다.** 후보를 bps 내림차순으로 훑으며 예산이 차면 멈추므로, 문턱을 넘고도 점이 없는 엣지가
 * 생긴다(실측 표본·경로 길이 기준 상위 8~15개만 배정). 이는 문턱과 무관한 성능 예산이며 굵기·
 * 불투명도는 43개 전부에 그대로 실린다.
 */
export const FLOW_MIN_BPS = 1e4;

/** 한 엣지에 흘릴 점 스트림. `dir=true` 는 엣지의 from→to(인스턴스→스위치) 방향이다. */
export interface FlowStream {
	bps: number;
	dir: boolean;
	internal: boolean;
}

/**
 * 엣지 하나에 어떤 점 스트림을 흘릴지 정한다.
 *
 * - **라우터가 전혀 없는 망(isolated)의 케이블**: 나갈 경로가 없으므로 그 망의 NIC 트래픽은
 *   정의상 전부 내부 통신이다. tx(인스턴스→스위치)와 rx(스위치→인스턴스)를 각각의 사용량만큼
 *   따로 흘려 인스턴스 ↔ 스위치 ↔ 인스턴스가 눈에 보이게 한다.
 * - **그 밖의 모든 엣지**: 게이트웨이 방향 한 줄만 흘린다. 라우터가 있는 망은 내부/외부 비중을
 *   계측으로 가를 수 없다(Σtx = 내부+유출, Σrx = 내부+유입 — 미지수 3개에 식 2개). 없는 데이터는 그리지 않는다.
 *
 * 쌍 단위(A→B) 경로는 어느 경우에도 계측되지 않는다 — exporter 에 peer 라벨이 없다.
 */
export function flowStreams(
	edge: Pick<CanvasEdge, 'kind' | 'netId'>,
	rate: { rx_bps: number; tx_bps: number },
	isolatedNet: boolean,
	/** 게이트웨이 방향 스트림에 쓸 스칼라. 생략하면 `intensityBps` 로 계산한다.
	 *  uplink 트렁크처럼 `edgeStyle` 이 망별 합으로 따로 계산하는 경우 그 값을 넘겨야 어긋나지 않는다. */
	aggregateBps?: number,
): FlowStream[] {
	if (edge.kind === 'cable' && isolatedNet) {
		return [
			{ bps: rate.tx_bps, dir: true, internal: true },
			{ bps: rate.rx_bps, dir: false, internal: true },
		].filter((s) => s.bps >= FLOW_MIN_BPS);
	}
	const bps = aggregateBps ?? intensityBps(edge.kind, rate);
	if (bps < FLOW_MIN_BPS) return [];
	return [{ bps, dir: rate.tx_bps >= rate.rx_bps, internal: false }];
}

/**
 * 흐름 점 전역 예산. **성능 한도**이며 사용량 문턱(`FLOW_MIN_BPS`)과는 별개다.
 * 대규모(인스턴스 40+) 화면에서 rAF 마다 옮길 원 개수의 상한이다.
 */
export const FLOW_DOT_BUDGET = 60;

export interface FlowAllocation {
	key: string;
	netId: string;
	n: number;
	dir: boolean;
	speed: number;
	internal: boolean;
}

/**
 * 전역 예산 안에서 어떤 엣지에 점을 몇 개 줄지 정한다.
 *
 * 후보는 **bps 내림차순**이어야 한다. 예산이 모자라는 스트림은 **잘라서 그리지 않고 건너뛴다** —
 * 잘린 개수는 통과 빈도를 그만큼 거짓으로 낮춰(8개 중 4개면 절반) 사용량을 잘못 읽게 만든다.
 * 건너뛴 뒤에도 계속 훑으므로 남은 예산은 더 한가한(그래서 더 적게 필요한) 엣지에게 돌아간다.
 *
 * 그 결과 화면에 점이 붙는 엣지 수는 `FLOW_MIN_BPS` 가 아니라 이 예산이 정한다.
 * 굵기·불투명도에는 이런 절단이 없어 모든 엣지가 사용량대로 그려진다.
 */
export function allocateFlowDots(
	cands: readonly { key: string; netId: string; streams: readonly FlowStream[]; len: number }[],
	budget: number = FLOW_DOT_BUDGET,
): FlowAllocation[] {
	const out: FlowAllocation[] = [];
	let total = 0;
	for (const c of cands) {
		if (total >= budget) break;
		for (const s of c.streams) {
			const n = flowDotCount(s.bps, c.len);
			if (total + n > budget) continue;
			total += n;
			out.push({ key: c.key, netId: c.netId, n, dir: s.dir, speed: flowRate(s.bps).speed, internal: s.internal });
		}
	}
	return out;
}

/** activeId 와 직접 연결된 노드 집합(자기 자신 포함). 스위치는 존 멤버, LB 는 멤버 VM 을 포함한다. */
export function relatedSet(graph: CanvasGraph, layout: Pick<LayoutResult, 'zoneMembers'> | null, activeId: string): Set<string> {
	const set = new Set<string>([activeId]);
	const node = graph.nodes.get(activeId);
	if (!node) return set;
	for (const e of graph.edgesByNode.get(activeId) ?? []) {
		set.add(e.from);
		set.add(e.to);
	}
	if (node.kind === 'switch') for (const id of layout?.zoneMembers.get(node.netId) ?? []) set.add(id);
	if (node.kind === 'lb') for (const id of node.memberVmIds) set.add(id);
	return set;
}

