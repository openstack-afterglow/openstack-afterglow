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
import { _ipv4InCidr, byName, cmpArr, edgeIntensity, normalizeMac, slug, uniq } from './canvasHelpers';
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
 * trunk → networks[netId] (라우터 exporter 없음: 네트워크 합산)
 * lbvip → load_balancers[lbId]
 */
export function edgeRate(e: CanvasEdge, traffic: TopologyTraffic | null | undefined): TrafficRate | null {
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
			return t.networks?.[e.netId] ?? null;
		case 'lbvip':
			return e.lbId ? (t.load_balancers?.[e.lbId] ?? null) : null;
		default:
			return null;
	}
}

export function edgeStyle(e: CanvasEdge, traffic: TopologyTraffic | null | undefined, graph: CanvasGraph): EdgeStyle {
	const rate = edgeRate(e, traffic);
	const bps = rate ? rate.rx_bps + rate.tx_bps : null;
	let { opacity, width } = bps == null ? { opacity: 0.4, width: 1.5 } : edgeIntensity(bps);
	let dash: string | null = null;
	if (e.kind === 'fip') { width = 1.5; opacity = opacity * 0.6; dash = '4 3'; }
	if (e.kind === 'lbvip') { width = 2; opacity = 0.75; }
	if (e.kind === 'lbmember') { width = 1.5; opacity = 0.75; dash = '4 3'; }
	if (e.kind === 'trunk') width = Math.max(2.5, width);
	const from = graph.nodes.get(e.from);
	if (from?.kind === 'vm' && from.status === 'SHUTOFF') dash = '6 4';
	if (from?.kind === 'router' && from.status === 'DOWN') dash = '6 4';
	return { opacity, width, dash, bps, rate };
}

/** 이 미만이면 흐름을 그리지 않는다 — "사용량 없음" 을 0 이 아니라 "점 없음" 으로 읽게 한다. */
export const FLOW_MIN_BPS = 1e5;

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
): FlowStream[] {
	if (edge.kind === 'cable' && isolatedNet) {
		return [
			{ bps: rate.tx_bps, dir: true, internal: true },
			{ bps: rate.rx_bps, dir: false, internal: true },
		].filter((s) => s.bps >= FLOW_MIN_BPS);
	}
	const bps = rate.rx_bps + rate.tx_bps;
	if (bps < FLOW_MIN_BPS) return [];
	return [{ bps, dir: rate.tx_bps >= rate.rx_bps, internal: false }];
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

