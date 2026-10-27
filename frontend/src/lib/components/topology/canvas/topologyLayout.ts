// Pure deterministic layout and orthogonal cable geometry; no DOM reads.
import { byName, clamp, mean, r1 } from './canvasHelpers';
import type {
	CanvasEdge,
	CanvasGraph,
	CanvasNet,
	CanvasNode,
	CanvasNic,
	EdgeGeometry,
	GeometryResult,
	LayoutResult,
	LbNode,
	ManualPositions,
	Pt,
	Rect,
	RouterNode,
	Side,
	ViewState,
	VmNode,
} from './types';

/** 캔버스 단위 상수(px @ k=1). */
export const L = {
	VM_W: 232, VM_HEAD: 40, NIC_ROW: 20, VM_PAD_B: 6,
	SW_W: 232, SW_H: 48,
	INTERNET_W: 232, INTERNET_H: 64, INTERNET_GAP: 48,
	RT_W: 200, RT_H: 68,
	LB_W: 264, LB_H: 68,
	COL_GAP: 24, ROW_GAP: 24, SW_TO_ROW: 48,
	PAD_X: 28, PAD_T: 36, PAD_B: 24, ZONE_GAP: 56, RT_GAP: 40,
	/** Internet starts at PROV_Y; provider switches reserve an upstream Internet row when needed. */
	PROV_Y: 36, ROUTER_GAP: 80, LOWER_GAP: 96,
} as const;

export const K_MIN = 0.35;
export const K_MAX = 2.2;
export const FIT_K_MAX = 1.25;

export const vmH = (rows: number): number => L.VM_HEAD + L.NIC_ROW * Math.max(1, rows) + L.VM_PAD_B;

export function nodeSize(node: CanvasNode): { w: number; h: number } {
	switch (node.kind) {
		case 'vm': return { w: L.VM_W, h: vmH(node.rows) };
		case 'internet': return { w: L.INTERNET_W, h: L.INTERNET_H };
		case 'switch': return { w: L.SW_W, h: L.SW_H };
		case 'router': return { w: L.RT_W, h: L.RT_H };
		case 'lb': return { w: L.LB_W, h: L.LB_H };
	}
}

export function rectUnion(rects: readonly Rect[]): Rect | null {
	let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
	for (const r of rects) {
		x1 = Math.min(x1, r.x); y1 = Math.min(y1, r.y);
		x2 = Math.max(x2, r.x + r.w); y2 = Math.max(y2, r.y + r.h);
	}
	return Number.isFinite(x1) ? { x: x1, y: y1, w: x2 - x1, h: y2 - y1 } : null;
}

/** 존 사각형 = 멤버 rect 합집합 + 패딩. 멤버십은 토폴로지로 고정되며 드래그는 존을 늘릴 뿐 재배정하지 않는다. */
export function zoneRectFrom(pos: ReadonlyMap<string, Rect>, memberIds: readonly string[] | undefined): Rect | null {
	if (!memberIds) return null;
	const u = rectUnion(memberIds.map((id) => pos.get(id)).filter((r): r is Rect => Boolean(r)));
	if (!u) return null;
	return { x: u.x - L.PAD_X, y: u.y - L.PAD_T, w: u.w + 2 * L.PAD_X, h: u.h + L.PAD_T + L.PAD_B };
}

/** Empty networks retain a selectable downstream area without making the switch a zone member. */
export function networkZoneRect(pos: ReadonlyMap<string, Rect>, netId: string, members: readonly string[] | undefined): Rect | null {
	const occupied = zoneRectFrom(pos, members);
	if (occupied) return occupied;
	const sw = pos.get('sw:' + netId);
	return sw ? { x: sw.x - L.PAD_X, y: sw.y + sw.h + L.SW_TO_ROW - L.PAD_T, w: sw.w + 2 * L.PAD_X, h: L.PAD_T + L.PAD_B } : null;
}

export function autoLayout(graph: CanvasGraph): LayoutResult {
	const pos = new Map<string, Rect>();
	const domOrder: string[] = [];
	const all = [...graph.nodes.values()];
	const vms = all.filter((n): n is VmNode => n.kind === 'vm');
	const routers = all.filter((n): n is RouterNode => n.kind === 'router');
	const lbs = all.filter((n): n is LbNode => n.kind === 'lb');
	const providerNets = graph.nets.filter((n) => n.tier === 'provider');
	const tenantNets = graph.nets.filter((n) => n.tier === 'tenant');
	const domainOf = new Map(graph.domainGroups?.flatMap((group) => group.netIds.map((id) => [id, group.id] as const)) ?? []);
	const setPos = (id: string, x: number, y: number) => {
		const node = graph.nodes.get(id);
		if (!node) return;
		const { w, h } = nodeSize(node);
		pos.set(id, { x, y, w, h });
	};
	// 인접 가중치: 두 네트워크를 함께 가진 VM 1.0, 함께 연결한 라우터 0.5.
	// VM·라우터를 한 번만 훑어 서로 다른 네트워크 쌍의 공출현 합을 미리 집계하고, w(a, b) 는 O(1) 조회로 둔다.
	const pairW = new Map<string, Map<string, number>>();
	const addPair = (a: string, b: string, v: number) => {
		let row = pairW.get(a);
		if (!row) { row = new Map(); pairW.set(a, row); }
		row.set(b, (row.get(b) ?? 0) + v);
	};
	const addCooccurrence = (ids: readonly string[], v: number) => {
		const u = [...new Set(ids)];
		for (let i = 0; i < u.length; i++) {
			for (let j = i + 1; j < u.length; j++) { addPair(u[i], u[j], v); addPair(u[j], u[i], v); }
		}
	};
	for (const vm of vms) addCooccurrence(vm.netIds, 1);
	for (const r of routers) addCooccurrence(r.intNetIds, 0.5);
	const w = (a: string, b: string): number => pairW.get(a)?.get(b) ?? 0;
	const cmpRank = (a: { isolated: boolean; name: string; id: string }, b: { isolated: boolean; name: string; id: string }) =>
		(a.isolated ? 1 : 0) - (b.isolated ? 1 : 0) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id);

	// 1. 깊이 계층: provider(외부·공유) = depth 0, 라우터 홉마다 +1.
	// 라우터는 자기가 무는 망들을 잇는 hyperedge 다 — extNetId 와 intNetIds 를 대칭으로 본다.
	// (external_gateway_network_id 가 null 이면서 공유망 uplink 를 connected_subnet_ids 로 무는 라우터가 실제로 있고,
	//  게이트웨이 없는 peering/HA 라우터도 홉이다)
	// 도달성은 **비가시 망까지 포함**해 계산한다 — 가시성으로 끊으면 다른 프로젝트 망을 경유하는 사슬이 끊겨
	// 독립 망으로 오분류된다. 가시성 제한은 "행 배정"과 "존 멤버십"에만 건다.
	const provIdx = new Map(providerNets.map((n, i) => [n.id, i]));
	const routerNetSets = routers.map((r) => ({
		r,
		nets: [...new Set([r.extNetId, ...r.intNetIds].filter((v): v is string => Boolean(v)))],
	}));
	/** netId → provider 로부터의 최단 라우터 홉 수. provider 는 0 고정, 도달 불가 망은 map 에 없다(= 독립). */
	const depth = new Map<string, number>();
	for (const id of provIdx.keys()) depth.set(id, 0);
	{
		let frontier = new Set<string>(provIdx.keys());
		let pending = routerNetSets;
		for (let d = 0; frontier.size && pending.length; d++) {
			const next = new Set<string>();
			const rest: typeof pending = [];
			for (const rs of pending) {
				if (!rs.nets.some((id) => frontier.has(id))) { rest.push(rs); continue; }
				for (const id of rs.nets) if (!depth.has(id)) { depth.set(id, d + 1); next.add(id); }
			}
			// 한 번 소비된 라우터는 이후 아무 망에도 값을 주지 못한다(그 시점에 자기 망 전부에 값이 생겼다)
			pending = rest;
			frontier = next;
		}
	}
	/**
	 * 라우터 행. 도달 불가 라우터는 map 에 없다(= 독립 행).
	 * m·hasDeeper 는 **가시 망으로만** 계산한다 — 비가시 브리지 망으로 m+1 을 잡으면 가시 망이 하나도 없는
	 * 유령 행이 생기고 그 라우터가 자기 존에서 떨어져 나간다.
	 */
	const routerBand = new Map<string, number>();
	for (const { r, nets } of routerNetSets) {
		if (!nets.some((id) => depth.has(id))) continue; // 도달 불가 → 독립 행
		const visible = nets.filter((id) => graph.netById.has(id));
		let m = Infinity;
		for (const id of visible) { const d = depth.get(id); if (d != null && d < m) m = d; }
		// 도달 가능하지만 가시 망이 하나도 없으면 최상단 tenant 행에 둔다
		if (!Number.isFinite(m)) { routerBand.set(r.id, 1); continue; }
		const hasDeeper = visible.some((id) => depth.get(id) === m + 1);
		// 게이트웨이 라우터는 자기가 더 깊게 만든 망의 행(m+1)에, 모든 망이 같은 깊이인 lateral 라우터는 그 깊이 행(m)에.
		// Provider bands have no router lane, so provider-only/lateral routers start in tenant row 1.
		routerBand.set(r.id, hasDeeper ? m + 1 : Math.max(m, 1));
	}
	let maxBand = 0;
	for (const n of tenantNets) { const d = depth.get(n.id); if (d != null && d > maxBand) maxBand = d; }
	for (const b of routerBand.values()) if (b > maxBand) maxBand = b;

	// 밴드 안에서만 greedy 인접 체인(오른쪽 끝 우선, 동점은 rank)을 돌린다 — 밴드가 다르면 세로로 떨어져 경계 컬럼이 성립하지 않는다.
	const chainOrder = (nets: readonly CanvasNet[]): CanvasNet[] => {
		const out: CanvasNet[] = [];
		if (!nets.length) return out;
		let remaining = [...nets];
		const start = remaining
			.map((n) => ({ n, s: remaining.reduce((acc, b) => (b === n ? acc : acc + w(n.id, b.id)), 0) }))
			.sort((a, b) => b.s - a.s || cmpRank(a.n, b.n))[0].n;
		out.push(start);
		remaining = remaining.filter((n) => n !== start);
		for (;;) {
			let best: { c: CanvasNet; end: 'left' | 'right'; s: number } | null = null;
			for (const c of remaining) {
				for (const end of ['right', 'left'] as const) {
					const anchor = end === 'left' ? out[0] : out[out.length - 1];
					const sc = w(c.id, anchor.id);
					if (sc <= 0) continue;
					if (!best || sc > best.s || (sc === best.s && cmpRank(c, best.c) < 0)) best = { c, end, s: sc };
				}
			}
			if (!best) break;
			if (best.end === 'left') out.unshift(best.c); else out.push(best.c);
			const chosen = best.c;
			remaining = remaining.filter((n) => n !== chosen);
		}
		out.push(...remaining.sort(cmpRank));
		return out;
	};
	// tenant 망을 깊이별 행으로 나눈다(위→아래). 도달 불가 망은 앵커가 없어 절대 깊이가 정의되지 않으므로
	// (루트를 임의로 고르면 망 이름 하나로 전체가 재적층된다) 맨 아래 한 행으로 두고 내부 계층을 만들지 않는다.
	// 행 목록은 graph.nets / sortedRouters 를 **필터**해서 만든다 — depth Map 의 삽입 순서는 입력 배열 순서에
	// 의존하므로 Map 순회로 행을 만들면 결정론이 깨진다.
	const sortedRouters = [...routers].sort(byName);
	const rowSpecs: Array<{ key: number | null; nets: CanvasNet[]; routers: RouterNode[] }> = [];
	for (let d = 1; d <= maxBand; d++) {
		const nets = chainOrder(tenantNets.filter((n) => depth.get(n.id) === d));
		const rowRouters = sortedRouters.filter((r) => routerBand.get(r.id) === d);
		if (!nets.length && !rowRouters.length) continue; // 멤버 0 인 행은 자리를 차지하지 않는다
		rowSpecs.push({ key: d, nets, routers: rowRouters });
	}
	const soloNets = chainOrder(tenantNets.filter((n) => !depth.has(n.id)));
	const soloRouters = sortedRouters.filter((r) => routerBand.get(r.id) == null);
	if (soloNets.length || soloRouters.length) rowSpecs.push({ key: null, nets: soloNets, routers: soloRouters });

	const order = rowSpecs.flatMap((s) => s.nets);
	const orderIdx = new Map(order.map((n, i) => [n.id, i]));
	/**
	 * 같은 행에서 좌우로 맞닿은 존 쌍만 경계(교차) 컬럼을 가질 수 있다 — 행이 다르면 세로로 떨어져 성립하지 않는다.
	 * provider 행은 넣지 않는다: homePair 가 provider 쌍을 돌려주면 placeGrid 의 isHome(v, [net.id]) 도
	 * placeTenantBand 의 isHome(v, [net.id, next.id]) 도 걸리지 않아 그 VM 이 위치를 못 받는다.
	 */
	const adjPairs: Array<[string, string]> = [];
	for (const s of rowSpecs) {
		for (let i = 0; i < s.nets.length - 1; i++) {
			const a = s.nets[i].id, b = s.nets[i + 1].id;
			if (!graph.domainGroups || domainOf.get(a) === domainOf.get(b)) adjPairs.push([a, b]);
		}
	}

	// 2. home 존: 인접 쌍 중 가장 무거운 쌍(경계 배치) 또는 첫 tenant 존, tenant 가 없으면 첫 provider 존(측면 VM)
	// 최대 2개 존만 갖는다 — 3개 이상이면 사이에 있는 다른 존을 rect 가 덮어 "멤버를 공유하지 않는데 겹치는" 거짓 신호가 생긴다.
	const homePair = (lower: readonly string[]): string[] => {
		let best: { a: string; b: string; s: number } | null = null;
		for (const [a, b] of adjPairs) {
			if (lower.includes(a) && lower.includes(b)) {
				const sc = w(a, b);
				if (!best || sc > best.s) best = { a, b, s: sc };
			}
		}
		return best ? [best.a, best.b] : [lower[0]];
	};
	const home = new Map<string, string[]>();
	const parked: string[] = [];
	for (const vm of vms) {
		if (!vm.netIds.length) { parked.push(vm.id); home.set(vm.id, []); continue; }
		const lower = vm.netIds.filter((id) => orderIdx.has(id)).sort((a, b) => (orderIdx.get(a) ?? 0) - (orderIdx.get(b) ?? 0));
		if (!lower.length) {
			const prov = vm.netIds.filter((id) => provIdx.has(id)).sort((a, b) => (provIdx.get(a) ?? 0) - (provIdx.get(b) ?? 0));
			home.set(vm.id, prov.length ? [prov[0]] : []);
			if (!prov.length) parked.push(vm.id);
			continue;
		}
		home.set(vm.id, homePair(lower));
	}
	for (const lb of lbs) if (lb.parked) parked.push(lb.id);
	const zoneMembers = new Map<string, string[]>(graph.nets.map((n) => [n.id, []]));
	for (const lb of lbs) if (lb.vipNetId && zoneMembers.has(lb.vipNetId)) zoneMembers.get(lb.vipNetId)?.push(lb.id);
	for (const vm of vms) for (const nid of home.get(vm.id) ?? []) zoneMembers.get(nid)?.push(vm.id);
	// Router home guides placement only: routers and switches are upstream of downstream network zones.
	const routerHome = new Map<string, string[]>();
	for (const r of routers) {
		const band = routerBand.get(r.id) ?? null; // null = 독립 행
		// Restrict placement homes to this router's depth band, including the independent band.
		const gwNets = r.intNetIds
			.filter((id) => orderIdx.has(id) && (depth.get(id) ?? null) === band)
			.sort((a, b) => (orderIdx.get(a) ?? 0) - (orderIdx.get(b) ?? 0));
		const zonesOf = gwNets.length ? homePair(gwNets) : [];
		routerHome.set(r.id, zonesOf);
	}
	const isHome = (vm: VmNode, ids: readonly string[]) => {
		const hm = home.get(vm.id) ?? [];
		return hm.length === ids.length && hm.every((v, i) => v === ids[i]);
	};
	const gridCols = (n: number) => (n <= 1 ? 1 : clamp(Math.ceil(Math.sqrt(n * 1.5)), 1, 6));
	const gridWidth = (n: number) => (n ? gridCols(n) * L.VM_W + (gridCols(n) - 1) * L.COL_GAP : 0);
	/**
	 * Switches sit above downstream zones; each zone stacks LB → instance → database tiers.
	 */
	/** 네트워크별 인스턴스 계층 시작 y — 경계 컬럼도 이 아래에서 시작해야 LB 보다 위로 올라가지 않는다 */
	const vmTierY = new Map<string, number>();
	const placeGrid = (net: { id: string }, singles: VmNode[], netLbs: LbNode[], x: number, topY: number, sink: string[]): number => {
		const swId = 'sw:' + net.id;
		const plain = singles.filter((v) => !v.isDatabase);
		const dbs = singles.filter((v) => v.isDatabase);
		const innerW = Math.max(L.SW_W, gridWidth(plain.length), gridWidth(dbs.length), netLbs.length ? L.LB_W : 0);
		setPos(swId, x + innerW / 2 - L.SW_W / 2, topY); domOrder.push(swId); sink.push(swId);
		let rowY = topY + L.SW_H + L.SW_TO_ROW;
		// VM 격자의 x 는 LB 개수와 무관하다(LB 는 세로로만 밀어낸다) → LB 보다 먼저 계산해 LB 정렬 기준으로 쓴다.
		const vmX = new Map<string, number>();
		for (const tier of [plain, dbs]) {
			if (!tier.length) continue;
			const cols = gridCols(tier.length);
			const gx = x + (innerW - gridWidth(tier.length)) / 2;
			tier.forEach((vm, i) => vmX.set(vm.id, gx + (i % cols) * (L.VM_W + L.COL_GAP)));
		}
		/**
		 * LB 는 자기 뒤에 물린 멤버 인스턴스 **위**에 오도록 왼쪽 변을 맞춘다. 멤버가 여럿이면 가장 왼쪽 멤버 기준이다
		 * (멤버가 아래 행에 있어도 컬럼이 같으므로 결과가 같다). 멤버가 없거나 이 존 격자에 없으면 예전처럼 가운데 정렬한다.
		 *
		 * LB 카드가 VM 보다 넓으므로(264 vs 232) 마지막 컬럼 멤버에 정렬하면 격자 오른쪽으로 최대 32px 삐져나온다.
		 * 존 폭 안으로 clamp 하면 정렬이 그만큼 어긋나므로, 대신 **콘텐츠 오른쪽 끝을 그만큼 넓혀** 반환한다 —
		 * 다음 존은 이 값 뒤에서 시작하므로 존끼리 겹치지 않고 정렬은 정확하게 유지된다.
		 * 왼쪽으로는 삐져나올 수 없다: innerW ≥ gridWidth 라 gx ≥ x 이고 LB 는 어떤 멤버의 x 에 맞춰도 ≥ x 다.
		 */
		let contentRight = x + innerW;
		for (const lb of netLbs) {
			const memberXs = lb.memberVmIds.map((id) => vmX.get(id)).filter((v): v is number => v != null);
			const lbX = memberXs.length ? Math.min(...memberXs) : x + innerW / 2 - L.LB_W / 2;
			setPos(lb.id, lbX, rowY);
			domOrder.push(lb.id); sink.push(lb.id);
			contentRight = Math.max(contentRight, lbX + L.LB_W);
			rowY += L.LB_H + L.ROW_GAP;
		}
		vmTierY.set(net.id, rowY);
		for (const tier of [plain, dbs]) {
			if (!tier.length) continue;
			const cols = gridCols(tier.length);
			for (let r = 0; r * cols < tier.length; r++) {
				const row = tier.slice(r * cols, (r + 1) * cols);
				const rowH = Math.max(...row.map((v) => vmH(v.rows)));
				row.forEach((vm) => { setPos(vm.id, vmX.get(vm.id) ?? x, rowY); domOrder.push(vm.id); sink.push(vm.id); });
				rowY += rowH + L.ROW_GAP;
			}
		}
		return contentRight;
	};


	// 3. provider 티어: tenant 존과 같은 계층 규칙(스위치 → LB → 인스턴스 → DB)으로 스위치 아래에 쌓는다.
	// 예전에는 직접 VM 을 스위치 양측에 flank 했지만, 평면도에서 계층이 위→아래로 읽히지 않아 제거했다.
	const providerIds: string[] = [];
	let x = 0;
	const providerY = L.PROV_Y + (providerNets.some((n) => n.kind === 'external') ? L.INTERNET_H + L.INTERNET_GAP : 0);
	for (const net of providerNets) {
		const direct = vms.filter((v) => isHome(v, [net.id])).sort(byName);
		const netLbs = lbs.filter((lb) => lb.vipNetId === net.id).sort(byName);
		x = placeGrid(net, direct, netLbs, x, providerY, providerIds) + 2 * L.PAD_X + L.ZONE_GAP;
		if (net.kind === 'external') {
			const sw = pos.get('sw:' + net.id)!;
			const id = 'internet:' + net.id;
			setPos(id, sw.x + (sw.w - L.INTERNET_W) / 2, L.PROV_Y);
			domOrder.splice(domOrder.indexOf('sw:' + net.id), 0, id);
			providerIds.push(id);
		}
	}
	const providerW = providerNets.length ? x - L.ZONE_GAP - 2 * L.PAD_X : 0;
	/**
	 * Band bottom includes downstream zones, including empty-network placeholders.
	 */
	const bandBottom = (nets: readonly CanvasNet[], fallback: number): number => {
		let b = fallback;
		for (const net of nets) {
			const zr = networkZoneRect(pos, net.id, zoneMembers.get(net.id));
			if (zr) b = Math.max(b, zr.y + zr.h);
		}
		return b;
	};

	// 4~5. 위에서 아래로 커서를 한 번만 전진시키며 행을 쌓는다: [행 d 라우터 레인 + 행 d 존] 을 d = 1..maxBand, 마지막에 독립 행.
	// 멤버가 하나도 없는 행은 자리를 차지하지 않으므로 깊이 1 뿐인 토폴로지는 예전과 같은 모양이 된다.
	// ROUTER_GAP separates each preceding downstream zone from the next upstream router lane.
	const nameOf = (id: string) => graph.nodes.get(id)?.name ?? id;
	const placeTenantBand = (bandOrder: readonly CanvasNet[], sink: string[], topY: number): number => {
		let bx0 = 0;
		let lastWasBorder = false;
		for (let i = 0; i < bandOrder.length; i++) {
			const net = bandOrder[i];
			const singles = vms.filter((v) => isHome(v, [net.id])).sort(byName);
			const netLbs = lbs.filter((lb) => lb.vipNetId === net.id).sort(byName);
			const contentRight = placeGrid(net, singles, netLbs, bx0, topY, sink);
			const next = bandOrder[i + 1];
			const borderAll = next ? vms.filter((v) => isHome(v, [net.id, next.id])).sort(byName) : [];
			// 경계(멀티 NIC) VM 도 계층 규칙을 지킨다: 양쪽 존의 인스턴스 계층 시작점 아래에서 일반 → DB 순으로 쌓는다
			const border = [...borderAll.filter((v) => !v.isDatabase), ...borderAll.filter((v) => v.isDatabase)];
			if (border.length) {
				const bx = contentRight + L.COL_GAP;
				// next 존은 아직 배치되지 않아 vmTierY 가 없다 → LB 개수로 시작 y 를 미리 계산한다
				const tierYOf = (netId: string) => {
					const known = vmTierY.get(netId);
					if (known != null) return known;
					const cnt = lbs.filter((lb) => lb.vipNetId === netId).length;
					return topY + L.SW_H + L.SW_TO_ROW + cnt * (L.LB_H + L.ROW_GAP);
				};
				let by = Math.max(tierYOf(net.id), next ? tierYOf(next.id) : 0);
				for (const vm of border) { setPos(vm.id, bx, by); domOrder.push(vm.id); sink.push(vm.id); by += vmH(vm.rows) + L.ROW_GAP; }
				bx0 = bx + L.VM_W + L.COL_GAP;
				lastWasBorder = true;
			} else {
				bx0 = contentRight + 2 * L.PAD_X + L.ZONE_GAP;
				lastWasBorder = false;
			}
		}
		return bandOrder.length ? (lastWasBorder ? bx0 - L.COL_GAP : bx0 - L.ZONE_GAP - 2 * L.PAD_X) : 0;
	};

	interface Band { key: number | null; nets: readonly CanvasNet[]; bandRouters: RouterNode[]; ids: string[]; routerY: number; tenantY: number; width: number }
	const bands: Band[] = [];
	let cursor = providerNets.length ? bandBottom(providerNets, providerY) : L.PROV_Y;
	for (const spec of rowSpecs) {
		const { nets, routers: bandRouters } = spec;
		const routerY = cursor + L.ROUTER_GAP;
		const tenantY = bandRouters.length ? routerY + L.RT_H + L.LOWER_GAP : routerY;
		bandRouters.forEach((r) => domOrder.push(r.id));
		const ids: string[] = [];
		const width = placeTenantBand(nets, ids, tenantY);
		bands.push({ key: spec.key, nets, bandRouters, ids, routerY, tenantY, width });
		cursor = nets.length ? bandBottom(nets, tenantY) : routerY + L.RT_H;
	}
	const first = bands[0] ?? null;
	const last = bands[bands.length - 1] ?? null;
	const fallbackRouterY = (providerNets.length ? bandBottom(providerNets, providerY) : L.PROV_Y) + L.ROUTER_GAP;
	const ROUTER_Y = first?.routerY ?? fallbackRouterY;
	const LOWER_Y = first?.tenantY ?? ROUTER_Y;
	const SOLO_ROUTER_Y = last?.routerY ?? ROUTER_Y;
	const SOLO_Y = last?.tenantY ?? LOWER_Y;
	const lowerW = Math.max(0, ...bands.map((b) => b.width));

	// 6. 수평 정렬: 좁은 밴드를 가운데로. 분류는 각 밴드가 실제로 배치한 id 목록으로만 한다.
	const totalW = Math.max(providerW, lowerW);
	const shiftIds = (ids: readonly string[], dx: number) => {
		if (!dx) return;
		for (const id of ids) { const p = pos.get(id); if (p) p.x += dx; }
	};
	shiftIds(providerIds, (totalW - providerW) / 2);
	for (const b of bands) shiftIds(b.ids, (totalW - b.width) / 2);
	// 7. 라우터 밴드: 상단/하단 스위치 중심의 평균을 목표로 1-D 분리
	const cxOf = (nid: string): number | null => {
		const p = pos.get('sw:' + nid);
		return p ? p.x + p.w / 2 : null;
	};
	// Placement homes align routers with their downstream switches, without expanding network zones.
	// Routers without a tenant home use a separate lane beside the tenant band.
	// 1-D 분리와 lift 보정은 밴드마다 따로 돌린다 — y 가 다른 라우터끼리 옆으로 밀어낼 이유가 없고,
	// lift 를 공유하면 한쪽 밴드가 목표 x 에서 통째로 밀려난다.
	for (const b of bands) {
		if (!b.bandRouters.length) continue;
		// b.width 는 중앙 정렬(shiftIds) **이전** 폭이다. 밴드가 최광폭이 아니면 실제 콘텐츠 우단은
		// (totalW + b.width) / 2 이므로, b.width 만 쓰면 레인이 밴드 **안쪽**에 떨어져 라우터가 남의 존에 갇힌다
		// (측정: provider 7 + tenant 2 에서 rtr-zero 가 net-t1 존에 완전히 포섭).
		const zonelessLaneX = (b.nets.length ? (totalW + b.width) / 2 + L.ZONE_GAP : totalW) + L.RT_W / 2;
		const desired = b.bandRouters
			.map((r) => {
				const homeCx = (routerHome.get(r.id) ?? []).map(cxOf).filter((v): v is number => v != null);
				const lo = mean(homeCx);
				if (lo != null) return { r, d: lo };
				const upper = [r.extNetId, ...r.intNetIds.filter((id) => provIdx.has(id))]
					.filter((id): id is string => Boolean(id)).map(cxOf).filter((v): v is number => v != null);
				return { r, d: b.nets.length ? zonelessLaneX : (mean(upper) ?? totalW / 2) };
			})
			.sort((a, c) => a.d - c.d || byName(a.r, c.r));
		const xs: number[] = [];
		for (let i = 0; i < desired.length; i++) xs.push(i === 0 ? desired[i].d : Math.max(desired[i].d, xs[i - 1] + L.RT_W + L.RT_GAP));
		const shift = xs.length ? xs.reduce((acc, v, i) => acc + (v - desired[i].d), 0) / xs.length : 0;
		// 상한 clamp 를 두지 않는다 — 좁은 콘텐츠 폭에 여러 라우터를 밀어넣으면 1-D 분리 결과가 다시 겹친다.
		// 밴드가 콘텐츠보다 넓어지면 contentBounds/fitAll 이 그만큼 넓게 잡아주므로 잘려 보이지 않는다.
		// 왼쪽 하한도 개별로 적용하면 안 된다: 일부만 하한에 걸리면 sweep 이 확보한 간격이 깨져 라우터끼리 겹친다.
		// 전체를 같은 양(lift)만큼 평행 이동해 간격을 그대로 보존한다.
		const lift = xs.length ? Math.max(0, L.RT_W / 2 - Math.min(...xs.map((v) => v - shift))) : 0;
		desired.forEach((d, i) => setPos(d.r.id, xs[i] - shift + lift - L.RT_W / 2, b.routerY));
	}
	// 8. 미연결 주차 스트립(존 아님) — 반드시 라우터 배치 **뒤에** 둔다.
	// 라우터보다 먼저 놓으면 라우터의 x(존 밖 zoneless 레인, sweep+lift)와 y(밴드별 routerY)를 알 수 없어
	// 아래 밴드 라우터와 겹친다. 실제로 solo 라우터 + 미연결 VM 조합에서 겹침이 발생했다.
	// 이미 배치된 모든 노드의 오른쪽 끝 바깥에 두고 최상단부터 아래로 쌓는다.
	if (parked.length) {
		let placedRight = 0;
		for (const p of pos.values()) placedRight = Math.max(placedRight, p.x + p.w);
		const parkX = placedRight + L.ZONE_GAP * 2;
		let py = L.PROV_Y;
		for (const id of [...parked].sort((a, b) => nameOf(a).localeCompare(nameOf(b)) || a.localeCompare(b))) {
			setPos(id, parkX, py); domOrder.push(id);
			py += (pos.get(id)?.h ?? 0) + L.ROW_GAP;
		}
	}
	// 콘텐츠 우단·바닥: 노드와 존 rect 를 모두 포함한다(SVG 레이어 크기·드래그 여유의 기준).
	// totalW 는 밴드 중앙 정렬용 폭이라 존 밖 라우터 레인·주차 스트립을 포함하지 않는다 —
	// 그걸 SVG 폭에 쓰면 오른쪽 콘텐츠가 잘린다(측정: 실우단 3184 vs totalW+800 = 1376).
	let BOTTOM_Y = 0;
	let RIGHT_X = 0;
	for (const p of pos.values()) {
		BOTTOM_Y = Math.max(BOTTOM_Y, p.y + p.h);
		RIGHT_X = Math.max(RIGHT_X, p.x + p.w);
	}
	for (const net of graph.nets) {
		const zr = networkZoneRect(pos, net.id, zoneMembers.get(net.id));
		if (!zr) continue;
		BOTTOM_Y = Math.max(BOTTOM_Y, zr.y + zr.h);
		RIGHT_X = Math.max(RIGHT_X, zr.x + zr.w);
	}
	const result: LayoutResult = {
		pos,
		order: {
			provider: providerNets.map((n) => n.id),
			// lower 의 기존 의미("provider 에 닿는 망을 위→아래·좌→우로 전개한 순서")를 그대로 보존한다.
			// [...lower, ...solo] === bands.rows.flatMap(r => r.netIds) 가 항등식이라 기존 소비자가 무수정으로 통과한다.
			lower: bands.filter((b) => b.key !== null).flatMap((b) => b.nets.map((n) => n.id)),
			solo: last && last.key === null ? last.nets.map((n) => n.id) : [],
		},
		home,
		zoneMembers,
		parked: new Set(parked),
		domOrder,
		bands: {
			rows: bands.map((b) => ({
				depth: b.key,
				netIds: b.nets.map((n) => n.id),
				routerIds: b.bandRouters.map((r) => r.id),
				routerY: b.routerY,
				tenantY: b.tenantY,
			})),
			ROUTER_Y, LOWER_Y, SOLO_ROUTER_Y, SOLO_Y, BOTTOM_Y, RIGHT_X, totalW,
		},
	};
	packDomainGroups(graph, result);
	if (graph.domainGroups?.length) {
		const geometry = computeGeometry(graph, result);
		const bounds = contentBounds(geometry.zones, result.pos, geometry.domains);
		result.bands.RIGHT_X = bounds.x + bounds.w;
		result.bands.BOTTOM_Y = bounds.y + bounds.h;
	}
	return result;
}

/** Ownership groups include their upstream devices, but network zones never do. */
function domainNodeIds(graph: CanvasGraph, netIds: readonly string[], zoneMembers: ReadonlyMap<string, string[]>): Set<string> {
	const ids = new Set(netIds.flatMap((id) => ['sw:' + id, 'internet:' + id, ...(zoneMembers.get(id) ?? [])]));
	for (const node of graph.nodes.values()) {
		if (node.kind !== 'router') continue;
		const connected = graph.nets.filter((net) => node.netIds.includes(net.id));
		const owned = connected.filter((net) => Boolean(node.raw.project_id) && net.project_id === node.raw.project_id);
		const candidates = owned.length ? owned : connected;
		const home = candidates.find((net) => net.tier === 'tenant') ?? candidates[0];
		if (home && netIds.includes(home.id)) ids.add(node.id);
	}
	return ids;
}

/** Domain padding reserves a separate label row above all owned network content. */
export function domainRects(graph: CanvasGraph, zones: ReadonlyMap<string, Rect>, pos?: ReadonlyMap<string, Rect>, zoneMembers: ReadonlyMap<string, string[]> = new Map()): Map<string, Rect> {
	const result = new Map<string, Rect>();
	for (const group of graph.domainGroups ?? []) {
		const upstream = pos ? [...domainNodeIds(graph, group.netIds, zoneMembers)].map((id) => pos.get(id)) : [];
		const bounds = rectUnion([...group.netIds.map((id) => zones.get(id)), ...upstream].filter((r): r is Rect => Boolean(r)));
		if (bounds) result.set(group.id, { x: bounds.x - 28, y: bounds.y - 96, w: bounds.w + 56, h: bounds.h + 124 });
	}
	return result;
}

/** Move ownership groups as rigid units. Cross-domain NICs remain real edges, never shared membership. */
export function packDomainGroups(graph: CanvasGraph, layout: Pick<LayoutResult, 'pos' | 'zoneMembers'>, initial = true): void {
	if (!graph.domainGroups?.length) return;
	const zones = new Map<string, Rect>();
	for (const [id, members] of layout.zoneMembers) {
		const rect = networkZoneRect(layout.pos, id, members);
		if (rect) zones.set(id, rect);
	}
	const boxes = domainRects(graph, zones, layout.pos, layout.zoneMembers);
	const placed: Rect[] = [];
	const grouped = new Set<string>();
	let right = 0;
	for (const group of graph.domainGroups) {
		const box = boxes.get(group.id);
		if (!box) continue;
		const target = { ...box };
		if (initial) { target.x = right; target.y = 0; }
		else {
			for (const previous of placed) {
				if (target.x < previous.x + previous.w + L.ZONE_GAP && target.x + target.w + L.ZONE_GAP > previous.x && target.y < previous.y + previous.h && target.y + target.h > previous.y) target.x = previous.x + previous.w + L.ZONE_GAP;
			}
		}
		const ids = domainNodeIds(graph, group.netIds, layout.zoneMembers);
		for (const id of ids) {
			const rect = layout.pos.get(id);
			if (rect) layout.pos.set(id, { ...rect, x: rect.x + target.x - box.x, y: rect.y + target.y - box.y });
			grouped.add(id);
		}
		placed.push(target);
		right = Math.max(right, target.x + target.w + L.ZONE_GAP);
	}
	// Unconnected resources and routers without a tenant home stay outside every domain box.
	const outside = [...layout.pos].filter(([id]) => !grouped.has(id));
	if (outside.length && outside.some(([, rect]) => placed.some((box) => rect.x < box.x + box.w && rect.x + rect.w > box.x && rect.y < box.y + box.h && rect.y + rect.h > box.y))) {
		const left = Math.min(...outside.map(([, rect]) => rect.x));
		for (const [id, rect] of outside) layout.pos.set(id, { ...rect, x: rect.x + right - left });
	}
}

/**
 * 저장된 수동 위치를 layout.pos 에 적용한다(크기는 유지). 현재 그래프에 없는 id 는 버리고,
 * 남은 항목만 담은 새 map 을 반환한다(호출자가 저장소를 갱신할 때 사용).
 */
/** 수동 배치 겹침 해소 상수 */
const MANUAL = {
	/** 밀어낸 뒤 다른 블럭과 유지할 최소 간격 */
	GAP: 12,
	/** 후보 자리 격자 간격. 자동 배치의 열 간격과 같게 두어 밀려난 노드가 격자에 정렬된다 */
	STEP: L.COL_GAP,
	/** 링 탐색 상한. 넘으면 원위치를 유지한다(사용자가 다시 옮길 수 있다) */
	MAX_RING: 400,
	/** 점유 사각형 공간 해시 셀 크기 */
	CELL: 256,
} as const;

const overlaps = (a: Rect, b: Rect): boolean =>
	a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/**
 * 수동으로 놓인 노드가 다른 블럭과 겹치지 않도록 드롭 지점에서 가장 가까운 빈 자리로 옮긴다.
 *
 * - **자동 배치 노드는 움직이지 않는다.** 자동 배치는 이미 비겹침을 보장하므로(밴드·존·그리드 규칙),
 *   그것을 건드리면 계층과 존 기하가 함께 무너진다. 움직이는 것은 `movableIds` 뿐이다.
 * - 결정론: id 를 정렬 순서로 하나씩 확정하고, 각 노드는 "이미 확정된 집합" 에 대해서만 자리를 찾는다.
 *   앞서 확정한 노드를 되돌리지 않으므로 진동이 구조적으로 불가능하다.
 *   (겹친 두 노드를 서로 밀어내는 MTV 방식은 A→B→A 로 진동해 수렴하지 않는다)
 * - 동점 후보 중에서는 **위로 올라가지 않는 쪽**을 고른다. 계층(라우터>스위치>LB>인스턴스>DB)은
 *   수동 배치에서는 사용자 의도이므로 제약이 아니지만, 굳이 뒤집을 이유도 없어 타이브레이크로만 쓴다.
 *
 * @returns 실제로 옮겨진 노드의 새 좌표
 */
export function resolveManualOverlap(pos: Map<string, Rect>, movableIds: readonly string[]): ManualPositions {
	const movable = new Set(movableIds);
	const cells = new Map<string, Array<{ id: string; r: Rect }>>();
	const cellKeys = (r: Rect): string[] => {
		const out: string[] = [];
		for (let cx = Math.floor(r.x / MANUAL.CELL); cx <= Math.floor((r.x + r.w) / MANUAL.CELL); cx++) {
			for (let cy = Math.floor(r.y / MANUAL.CELL); cy <= Math.floor((r.y + r.h) / MANUAL.CELL); cy++) out.push(`${cx},${cy}`);
		}
		return out;
	};
	const index = (id: string, r: Rect) => {
		for (const k of cellKeys(r)) {
			let bucket = cells.get(k);
			if (!bucket) { bucket = []; cells.set(k, bucket); }
			bucket.push({ id, r });
		}
	};
	const box = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
	for (const [id, r] of pos) {
		if (movable.has(id)) continue;
		index(id, r);
		box.minX = Math.min(box.minX, r.x); box.minY = Math.min(box.minY, r.y);
		box.maxX = Math.max(box.maxX, r.x + r.w); box.maxY = Math.max(box.maxY, r.y + r.h);
	}
	if (!Number.isFinite(box.minX)) { box.minX = box.minY = box.maxX = box.maxY = 0; }

	const moves: ManualPositions = {};
	for (const id of [...movableIds].sort()) {
		const p = pos.get(id);
		if (!p) continue;
		const free = (x: number, y: number): boolean => {
			const g = MANUAL.GAP;
			const probe: Rect = { x: x - g, y: y - g, w: p.w + 2 * g, h: p.h + 2 * g };
			const seen = new Set<string>();
			for (const k of cellKeys(probe)) {
				for (const e of cells.get(k) ?? []) {
					if (seen.has(e.id)) continue;
					seen.add(e.id);
					if (overlaps(probe, e.r)) return false;
				}
			}
			return true;
		};
		if (!free(p.x, p.y)) {
			// 링 상한: 점유 사각형 **바깥으로 완전히 빠져나가는 데 필요한 링**을 넘길 이유가 없다.
			// 그 지점부터는 반드시 비어 있으므로 탐색 결과는 그대로이고 낭비만 사라진다.
			// (사각형이 이 상한보다 큰 퇴화 입력에서는 MAX_RING 이 걸리고 못 찾으면 원위치를 유지한다)
			const escape = Math.min(
				box.maxX + MANUAL.GAP - p.x,
				p.x + p.w + MANUAL.GAP - box.minX,
				box.maxY + MANUAL.GAP - p.y,
				p.y + p.h + MANUAL.GAP - box.minY,
			);
			const maxRing = Math.min(MANUAL.MAX_RING, Math.max(1, Math.ceil(escape / MANUAL.STEP) + 1));
			// 후보 정렬 키: [거리, 위쪽이면 1, |가로|, 가로, 세로] 사전식 최소
			let best: { x: number; y: number; key: number[] } | null = null;
			for (let ring = 1; ring <= maxRing; ring++) {
				// 이 링의 최소 거리가 이미 찾은 최선보다 멀면 더 볼 필요가 없다 → 최근접이 보장된다
				if (best && ring * MANUAL.STEP > best.key[0]) break;
				for (let i = -ring; i <= ring; i++) {
					for (let j = -ring; j <= ring; j++) {
						if (Math.max(Math.abs(i), Math.abs(j)) !== ring) continue;
						const key = [Math.hypot(i * MANUAL.STEP, j * MANUAL.STEP), j < 0 ? 1 : 0, Math.abs(i), i, j];
						if (best) {
							let worse = false;
							for (let t = 0; t < key.length; t++) {
								if (key[t] !== best.key[t]) { worse = key[t] > best.key[t]; break; }
							}
							if (worse) continue;
						}
						const x = p.x + i * MANUAL.STEP, y = p.y + j * MANUAL.STEP;
						if (!free(x, y)) continue;
						best = { x, y, key };
					}
				}
			}
			// 상한 안에서 못 찾았으면(점유 사각형이 MAX_RING 보다 큰 퇴화 입력) 원위치를 유지한다.
			// 사각형 바깥에 억지로 던지면 드롭 지점에서 수천 px 떨어진 곳에 놓여 사용자가 노드를 잃는다.
			if (best) {
				p.x = best.x;
				p.y = best.y;
				moves[id] = { x: p.x, y: p.y };
			}
		}
		index(id, p);
	}
	return moves;
}

/**
 * 저장된 수동 위치를 layout.pos 에 적용한다(크기는 유지). 현재 그래프에 없는 id 는 버리고,
 * 겹침이 생기면 `resolveManualOverlap` 으로 밀어낸다.
 *
 * **반환값은 밀어낸 뒤 좌표가 아니라 입력받은 "사용자 의도" 좌표다.**
 * 해소 결과를 저장하면 다음 구조 갱신 때 그 값을 다시 해소해 핀이 조금씩 걸어간다
 * (측정: VM 을 한 대씩 추가할 때마다 저장 좌표가 774 → 870 → 894 로 이동).
 * 의도를 보존하면 해소는 (의도, 자동 배치)의 순수 함수가 되어 같은 구조에서 항상 같은 자리에 놓인다.
 */
export function applyManualPositions(layout: LayoutResult, manual: ManualPositions | null | undefined): ManualPositions {
	const pruned: ManualPositions = {};
	if (!manual) return pruned;
	for (const [id, p] of Object.entries(manual)) {
		const rect = layout.pos.get(id);
		if (!rect || !Number.isFinite(p?.x) || !Number.isFinite(p?.y)) continue;
		rect.x = p.x;
		rect.y = p.y;
		pruned[id] = { x: p.x, y: p.y };
	}
	// 자동 배치가 바뀌면(노드 추가·삭제·존 재정렬) 예전에 저장된 좌표가 새 자동 노드와 겹칠 수 있다.
	// layout.pos 는 해소된 좌표로 갱신되지만 pruned(저장 대상)는 의도 그대로 둔다.
	resolveManualOverlap(layout.pos, Object.keys(pruned));
	return pruned;
}

// ───────── 기하
const TAN: Record<Side, [number, number]> = { TOP: [0, -1], BOTTOM: [0, 1], LEFT: [-1, 0], RIGHT: [1, 0] };
export const center = (p: Rect): Pt => ({ x: p.x + p.w / 2, y: p.y + p.h / 2 });

export function sideFor(dx: number, dy: number): Side {
	if (Math.abs(dy) >= Math.abs(dx) * 0.6) return dy < 0 ? 'TOP' : 'BOTTOM';
	return dx < 0 ? 'LEFT' : 'RIGHT';
}

/** VM 앵커: 상/하변은 NIC 인덱스로 분산, 좌/우변은 NIC 행 중심 y. */
export function vmAnchor(vm: VmNode, p: Rect, nic: CanvasNic | undefined, side: Side): Pt {
	const rowIdx = nic ? nic.rowIdx : 0, n = Math.max(1, vm.nics.length), idx = nic ? nic.idx : 0;
	const rowY = p.y + L.VM_HEAD + rowIdx * L.NIC_ROW + L.NIC_ROW / 2;
	switch (side) {
		case 'TOP': return { x: p.x + p.w * (idx + 1) / (n + 1), y: p.y };
		case 'BOTTOM': return { x: p.x + p.w * (idx + 1) / (n + 1), y: p.y + p.h };
		case 'LEFT': return { x: p.x, y: Math.min(rowY, p.y + p.h - 6) };
		default: return { x: p.x + p.w, y: Math.min(rowY, p.y + p.h - 6) };
	}
}

export function slotAnchor(p: Rect, side: Side, k: number, m: number): Pt {
	const f = (k + 1) / (m + 1);
	switch (side) {
		case 'TOP': return { x: p.x + p.w * f, y: p.y };
		case 'BOTTOM': return { x: p.x + p.w * f, y: p.y + p.h };
		case 'LEFT': return { x: p.x, y: p.y + p.h * f };
		default: return { x: p.x + p.w, y: p.y + p.h * f };
	}
}

/** 이전 순서를 우선 유지하고, 8 단위 이상 교차할 때만 인접 교환(드래그 중 슬롯 튐 방지). */
export function stableOrder<T>(prevKeys: readonly string[] | undefined, items: readonly T[], keyOf: (it: T) => string, valOf: (it: T) => number): T[] {
	let arr: T[];
	const sortFresh = (a: T, b: T) => valOf(a) - valOf(b) || keyOf(a).localeCompare(keyOf(b));
	if (prevKeys) {
		const byKey = new Map(items.map((it) => [keyOf(it), it]));
		arr = [];
		for (const k of prevKeys) {
			const it = byKey.get(k);
			if (it !== undefined) { arr.push(it); byKey.delete(k); }
		}
		arr.push(...[...byKey.values()].sort(sortFresh));
	} else {
		arr = [...items].sort(sortFresh);
	}
	let swapped = true;
	while (swapped) {
		swapped = false;
		for (let i = 0; i < arr.length - 1; i++) {
			if (valOf(arr[i]) > valOf(arr[i + 1]) + 8) {
				[arr[i], arr[i + 1]] = [arr[i + 1], arr[i]];
				swapped = true;
			}
		}
	}
	return arr;
}

/** Right-angle route with outward endpoint stubs. Reversed/moved nodes detour outside their bounds. */
export function orthogonal(a: Pt, sa: Side, b: Pt, sb: Side, endpointBounds?: Rect, obstacles: readonly Rect[] = []): EdgeGeometry {
	const verticalA = sa === 'TOP' || sa === 'BOTTOM';
	const verticalB = sb === 'TOP' || sb === 'BOTTOM';
	const gap = verticalA === verticalB ? Math.abs(verticalA ? b.y - a.y : b.x - a.x) : 48;
	const stub = Math.min(12, Math.max(8, gap / 3));
	const p = { x: a.x + TAN[sa][0] * stub, y: a.y + TAN[sa][1] * stub };
	const q = { x: b.x + TAN[sb][0] * stub, y: b.y + TAN[sb][1] * stub };
	const points: Pt[] = [a, p];
	if (verticalA && verticalB) {
		if (sa !== sb && (q.y - p.y) * TAN[sa][1] >= 0) {
			const y = (p.y + q.y) / 2;
			points.push({ x: p.x, y }, { x: q.x, y });
		} else if (sa === sb) {
			const y = sa === 'TOP' ? Math.min(p.y, q.y) : Math.max(p.y, q.y);
			points.push({ x: p.x, y }, { x: q.x, y });
		} else {
			const left = endpointBounds?.x ?? Math.min(a.x, b.x);
			const right = endpointBounds ? endpointBounds.x + endpointBounds.w : Math.max(a.x, b.x);
			const x = a.x + b.x < left + right ? left - 24 : right + 24;
			points.push({ x, y: p.y }, { x, y: q.y });
		}
	} else if (!verticalA && !verticalB) {
		if (sa !== sb && (q.x - p.x) * TAN[sa][0] >= 0) {
			const x = (p.x + q.x) / 2;
			points.push({ x, y: p.y }, { x, y: q.y });
		} else if (sa === sb) {
			const x = sa === 'LEFT' ? Math.min(p.x, q.x) : Math.max(p.x, q.x);
			points.push({ x, y: p.y }, { x, y: q.y });
		} else {
			const y = (endpointBounds?.y ?? Math.min(a.y, b.y)) - 24;
			points.push({ x: p.x, y }, { x: q.x, y });
		}
	} else {
		points.push(verticalA ? { x: p.x, y: q.y } : { x: q.x, y: p.y });
	}
	points.push(q, b);
	// Dense grids reserve their row/column gaps for cables, not unrelated card faces.
	const blocked = (candidate: readonly Pt[]): boolean => candidate.slice(1).some((end, i) => {
		const start = candidate[i];
		return obstacles.some((rect) => start.x === end.x
			? start.x > rect.x && start.x < rect.x + rect.w && Math.max(start.y, end.y) > rect.y && Math.min(start.y, end.y) < rect.y + rect.h
			: start.y > rect.y && start.y < rect.y + rect.h && Math.max(start.x, end.x) > rect.x && Math.min(start.x, end.x) < rect.x + rect.w);
	});
	if (obstacles.length && blocked(points)) {
		let shortest: Pt[] | null = null;
		let bestLength = Infinity;
		const xs = new Set(obstacles.flatMap((rect) => [rect.x - 12, rect.x + rect.w + 12]));
		const ys = new Set(obstacles.flatMap((rect) => [rect.y - 12, rect.y + rect.h + 12]));
		for (const axis of ['x', 'y'] as const) for (const value of axis === 'x' ? xs : ys) {
			const candidate = axis === 'x'
				? [a, p, { x: value, y: p.y }, { x: value, y: q.y }, q, b]
				: [a, p, { x: p.x, y: value }, { x: q.x, y: value }, q, b];
			const length = candidate.slice(1).reduce((sum, end, i) => sum + Math.abs(end.x - candidate[i].x) + Math.abs(end.y - candidate[i].y), 0);
			if (length >= bestLength || blocked(candidate)) continue;
			shortest = candidate; bestLength = length;
		}
		if (shortest) points.splice(0, points.length, ...shortest);
	}
	const route: Pt[] = [];
	for (const point of points) {
		const last = route.at(-1);
		if (last?.x === point.x && last.y === point.y) continue;
		const previous = route.at(-2);
		if (previous && last && ((previous.x === last.x && last.x === point.x) || (previous.y === last.y && last.y === point.y))) route.pop();
		route.push(point);
	}
	const lengths = route.slice(1).map((point, i) => Math.abs(point.x - route[i].x) + Math.abs(point.y - route[i].y));
	let remaining = lengths.reduce((total, length) => total + length, 0) / 2;
	let mid = a;
	for (let i = 0; i < lengths.length; i++) {
		if (remaining <= lengths[i]) {
			const fraction = lengths[i] ? remaining / lengths[i] : 0;
			mid = { x: route[i].x + (route[i + 1].x - route[i].x) * fraction, y: route[i].y + (route[i + 1].y - route[i].y) * fraction };
			break;
		}
		remaining -= lengths[i];
	}
	return { d: route.map((point, i) => `${i ? 'L' : 'M'}${r1(point.x)} ${r1(point.y)}`).join(' '), a, b, mid, sa, sb };
}

/**
 * 존 rect, 엣지 path, 슬롯 순서를 한 번에 계산한다. 노드 위치가 바뀔 때마다 호출한다.
 * extraEdges contains lazily generated LB member links; prevSlotOrder preserves drag hysteresis.
 */
export function computeGeometry(
	graph: CanvasGraph,
	layout: Pick<LayoutResult, 'pos' | 'zoneMembers'>,
	extraEdges: readonly CanvasEdge[] = [],
	prevSlotOrder?: ReadonlyMap<string, string[]>,
): GeometryResult {
	const pos = layout.pos;
	const zones = new Map<string, Rect>();
	for (const net of graph.nets) {
		const r = networkZoneRect(pos, net.id, layout.zoneMembers.get(net.id));
		if (r) zones.set(net.id, r);
	}
	const edges = [...graph.edges, ...extraEdges];
	type SlotItem = { edge: CanvasEdge; end: 'from' | 'to'; key: number };
	const perSlot = new Map<string, SlotItem[]>();
	const sides = new Map<string, { sa: Side; sb: Side }>();
	const push = (k: string, v: SlotItem) => {
		const arr = perSlot.get(k) ?? [];
		arr.push(v);
		perSlot.set(k, arr);
	};
	for (const e of edges) {
		const pa = pos.get(e.from), pb = pos.get(e.to);
		if (!pa || !pb) continue;
		const ca = center(pa), cb = center(pb);
		let sa: Side = 'TOP', sb: Side = 'BOTTOM';
		if (e.kind === 'uplink' || e.kind === 'lbmember') { sa = 'BOTTOM'; sb = 'TOP'; }
		else if (e.kind === 'trunk' && cb.y >= ca.y) { sa = 'BOTTOM'; sb = 'TOP'; }
		sides.set(e.key, { sa, sb });
		push(`${e.from}|${sa}`, { edge: e, end: 'from', key: sa === 'TOP' || sa === 'BOTTOM' ? cb.x : cb.y });
		push(`${e.to}|${sb}`, { edge: e, end: 'to', key: sb === 'TOP' || sb === 'BOTTOM' ? ca.x : ca.y });
	}
	const slotOrder = new Map<string, string[]>();
	const slotPt = new Map<string, Pt>();
	for (const [nk, items] of perSlot) {
		const bar = nk.lastIndexOf('|');
		const nodeId = nk.slice(0, bar), side = nk.slice(bar + 1) as Side;
		const p = pos.get(nodeId);
		if (!p) continue;
		const ordered = stableOrder(prevSlotOrder?.get(nk), items, (it) => it.edge.key, (it) => it.key);
		slotOrder.set(nk, ordered.map((it) => it.edge.key));
		const node = graph.nodes.get(nodeId);
		if (node?.kind === 'vm') {
			const groups = new Map<string, SlotItem[]>();
			for (const item of ordered) {
				const key = (item.end === 'from' ? item.edge.nic : item.edge.toNic)?.key ?? '';
				const group = groups.get(key) ?? [];
				group.push(item); groups.set(key, group);
			}
			for (const group of groups.values()) group.forEach((it, k) => {
				const base = vmAnchor(node, p, it.end === 'from' ? it.edge.nic : it.edge.toNic, side);
				const delta = group.length > 1 ? ((k + 1) / (group.length + 1) - 0.5) * 16 : 0;
				const point = side === 'TOP' || side === 'BOTTOM' ? { x: base.x + delta, y: base.y } : { x: base.x, y: base.y + delta };
				slotPt.set(`${it.edge.key}|${it.end}`, point);
			});
		} else ordered.forEach((it, k) => slotPt.set(`${it.edge.key}|${it.end}`, slotAnchor(p, side, k, ordered.length)));
	}
	const obstacles = [...pos.values()];
	const geom = new Map<string, EdgeGeometry>();
	for (const e of edges) {
		const pa = pos.get(e.from), pb = pos.get(e.to);
		const sd = sides.get(e.key);
		if (!pa || !pb || !sd) continue;
		const a = slotPt.get(`${e.key}|from`);
		const b = slotPt.get(`${e.key}|to`);
		if (!a || !b) continue;
		geom.set(e.key, orthogonal(a, sd.sa, b, sd.sb, rectUnion([pa, pb]) ?? undefined, obstacles));
	}
	return { geom, slotOrder, zones, domains: domainRects(graph, zones, pos, layout.zoneMembers) };
}

export function contentBounds(zones: ReadonlyMap<string, Rect>, pos: ReadonlyMap<string, Rect>, domains?: ReadonlyMap<string, Rect>): Rect {
	return rectUnion([...zones.values(), ...pos.values(), ...(domains?.values() ?? [])]) ?? { x: 0, y: 0, w: 100, h: 100 };
}

/** bounds 를 뷰포트에 맞추는 변환. k 는 [kMin, kMax] 로 클램프. */
export function fitTransform(bounds: Rect, viewportW: number, viewportH: number, pad = 40, kMin = K_MIN, kMax = FIT_K_MAX): ViewState {
	const bw = Math.max(1, bounds.w), bh = Math.max(1, bounds.h);
	const k = clamp(Math.min((viewportW - 2 * pad) / bw, (viewportH - 2 * pad) / bh), kMin, kMax);
	return { k, panX: (viewportW - bw * k) / 2 - bounds.x * k, panY: (viewportH - bh * k) / 2 - bounds.y * k };
}

/** 화면 좌표 (sx, sy) 아래의 캔버스 점이 고정되도록 확대/축소. */
export function zoomAt(view: ViewState, sx: number, sy: number, k2: number): ViewState {
	const k = clamp(k2, K_MIN, K_MAX);
	return { k, panX: sx - (sx - view.panX) * (k / view.k), panY: sy - (sy - view.panY) * (k / view.k) };
}

/** 노드 rect 와 그 노드가 속한 존 rect 의 합집합(포커스 이동용). */
export function nodeBounds(id: string, layout: Pick<LayoutResult, 'pos' | 'zoneMembers'>, zones: ReadonlyMap<string, Rect>): Rect | null {
	const rects: Rect[] = [];
	const p = layout.pos.get(id);
	if (p) rects.push(p);
	for (const [nid, members] of layout.zoneMembers) {
		const z = zones.get(nid);
		if (z && members.includes(id)) rects.push(z);
	}
	return rectUnion(rects);
}
