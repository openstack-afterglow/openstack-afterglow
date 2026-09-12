<script lang="ts">
	// 캔버스형 토폴로지 뷰. 순수 모듈(topologyGraph/topologyLayout)에 파생을 맡기고 이 컴포넌트는
	// 상호작용(팬/줌/드래그/검색/선택)과 DOM 배선만 담당한다. 콜백 계약은 GlobalTopology 와 동일하며 onSelectNetwork 만 추가된다.
	import { onMount, untrack } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import Button from '$lib/components/ui/Button.svelte';
	import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';
	import type { TopologyData, TopologyLoadBalancer, TopologyTraffic } from '$lib/types/topology';
	import { prefersReducedMotion } from '$lib/utils/motion';
	import { fmtRate, fmtRateShort, flowDotCount, flowRate, KIND_LABEL, NET_KIND_LABEL, clamp, wheelIntent } from './canvasHelpers';
	import CanvasEdgeLayer, { type EdgeRenderItem } from './CanvasEdgeLayer.svelte';
	import CanvasHud, { type HudBadgeItem, type HudLabelItem } from './CanvasHud.svelte';
	import CanvasNodeCard from './CanvasNodeCard.svelte';
	import CanvasToolbar from './CanvasToolbar.svelte';
	import CanvasZoneLayer, { type ZoneRenderItem } from './CanvasZoneLayer.svelte';
	import { clearManualPositions, layoutStorageKey, loadManualPositions, saveManualPositions, type LayoutScope } from './layoutStorage';
	import {
		assignTenantColors,
		buildGraph,
		buildMemberEdges,
		colorOfNet,
		edgeRate,
		edgeStyle,
		FLOW_MIN_BPS,
		flowStreams,
		matchesQuery,
		relatedSet,
		switchId,
	} from './topologyGraph';
	import { FIT_K_MAX, K_MAX, K_MIN, applyManualPositions, autoLayout, computeGeometry, contentBounds, nodeBounds, resolveManualOverlap, zoomAt as zoomAtPure } from './topologyLayout';
	import type { CanvasEdge, CanvasNet, EdgeStyle, ManualPositions, Rect, ViewState } from './types';
	import { createViewport } from './viewport.svelte';

	interface Props {
		data: TopologyData;
		traffic?: TopologyTraffic | null;
		projectId?: string | null;
		showAll?: boolean;
		/** 부모가 전달하면 controlled(GlobalTopology 와 동일). 네트워크 id 를 주면 해당 스위치를 강조한다. */
		selectedId?: string | null;
		/** 관리자 화면: 존 라벨에 VLAN/VXLAN·MTU pill 표시 */
		adminView?: boolean;
		storageScope?: LayoutScope;
		onSelectInstance?: (id: string) => void;
		onSelectRouter?: (id: string) => void;
		onSelectLoadBalancer?: (lb: TopologyLoadBalancer) => void;
		onSelectNetwork?: (networkId: string) => void;
		onIntentInstance?: (id: string) => void;
		onIntentRouter?: (id: string) => void;
		onCancelIntent?: () => void;
	}

	let {
		data,
		traffic = null,
		projectId = null,
		showAll = false,
		selectedId: selectedIdProp = undefined,
		adminView = false,
		storageScope = 'user',
		onSelectInstance,
		onSelectRouter,
		onSelectLoadBalancer,
		onSelectNetwork,
		onIntentInstance,
		onIntentRouter,
		onCancelIntent,
	}: Props = $props();

	// ───────── 그래프·자동 배치(구조 변경에만 반응, traffic 은 읽지 않는다)
	const built = $derived.by(() => {
		const graph = buildGraph(data, { projectId, showAll });
		const layout = autoLayout(graph);
		assignTenantColors(graph, [...layout.order.lower, ...layout.order.solo]);
		return { graph, layout };
	});
	const graph = $derived(built.graph);
	const layout = $derived(built.layout);
	const storageKey = $derived(layoutStorageKey(storageScope, projectId));

	/** 현재 노드 위치(수동 배치 반영). 드래그는 항목 단위로 갱신해 해당 카드만 다시 그린다. */
	const pos = new SvelteMap<string, Rect>();
	let manual = $state<ManualPositions>({});
	const manualCount = $derived(Object.keys(manual).length);
	let lastStorageKey: string | null = null;
	/** 마지막으로 저장소에 기록한(또는 저장소에서 읽은) 수동 위치. 같으면 localStorage 쓰기를 생략한다. */
	let lastSaved: ManualPositions | null = null;
	/** 수동 배치를 적용하기 전의 순수 자동 배치 좌표(applyManualPositions 가 layout.pos 를 제자리 수정하므로 따로 보관). */
	let autoPos = new Map<string, { x: number; y: number }>();
	let slotOrderCache: Map<string, string[]> | undefined;
	let needsInitialFit = true;
	/** 드래그 중인 노드 id($effect.pre 가 초기화 시점에 동기 실행되므로 그보다 먼저 선언한다) */
	let draggingId = $state<string | null>(null);

	function sameManual(a: ManualPositions, b: ManualPositions): boolean {
		const keys = Object.keys(a);
		if (keys.length !== Object.keys(b).length) return false;
		for (const k of keys) {
			const p = a[k], q = b[k];
			if (!q || p.x !== q.x || p.y !== q.y) return false;
		}
		return true;
	}

	function persistManual(key: string, next: ManualPositions) {
		if (lastSaved && sameManual(next, lastSaved)) return;
		saveManualPositions(key, next);
		lastSaved = next;
	}

	// 구조 변경: 수동 위치를 id 로 유지하고 새 id 는 자동 배치, 사라진 id 는 정리 후 저장한다.
	$effect.pre(() => {
		const { layout: fresh } = built;
		const key = storageKey;
		untrack(() => {
			const sameKey = key === lastStorageKey;
			const source = sameKey ? manual : loadManualPositions(key);
			if (!sameKey) lastSaved = source;
			lastStorageKey = key;
			autoPos = new Map([...fresh.pos].map(([id, r]) => [id, { x: r.x, y: r.y }]));
			const pruned = applyManualPositions(fresh, source);
			manual = pruned;
			persistManual(key, pruned);
			slotOrderCache = undefined;
			for (const id of [...pos.keys()]) if (!fresh.pos.has(id)) pos.delete(id);
			for (const [id, r] of fresh.pos) {
				// 드래그 중인 노드는 손가락 아래 위치를 유지한다(놓을 때 commitManual 이 확정)
				if (id === draggingId) continue;
				const cur = pos.get(id);
				if (!cur || cur.x !== r.x || cur.y !== r.y || cur.w !== r.w || cur.h !== r.h) pos.set(id, { ...r });
			}
		});
	});

	// ───────── 뷰포트
	const vp = createViewport();
	let viewportEl = $state<HTMLDivElement | null>(null);
	let flowGroupEl = $state<SVGGElement | null>(null);
	let searchElement = $state<HTMLInputElement | null>(null);
	let vw = $state(0);
	let vh = $state(0);
	let panning = $state(false);
	let gesturing = $state(false);
	let armedId = $state<string | null>(null);

	const lod = $derived(vp.k >= 0.9 ? 'full' : vp.k >= 0.65 ? 'nobps' : vp.k >= 0.5 ? 'noip' : 'compact');
	const badgesHidden = $derived(vp.k < 0.45);
	const worldTransform = $derived(`translate(${vp.panX}px, ${vp.panY}px) scale(${vp.k})`);
	const gridSize = $derived(`${120 * vp.k}px ${120 * vp.k}px, ${120 * vp.k}px ${120 * vp.k}px, ${24 * vp.k}px ${24 * vp.k}px, ${24 * vp.k}px ${24 * vp.k}px`);
	const gridPosition = $derived(`${vp.panX}px ${vp.panY}px`);
	const svgW = $derived(Math.max(layout.bands.RIGHT_X + 800, 1600));
	const svgH = $derived(Math.max(layout.bands.BOTTOM_Y + 1200, 1600));

	function measure(): { w: number; h: number } {
		return { w: viewportEl?.clientWidth ?? 0, h: viewportEl?.clientHeight ?? 0 };
	}

	// ───────── 선택·호버·검색
	let internalSel = $state<string | null>(null);
	let hoveredId = $state<string | null>(null);
	let hoveredNicKey = $state<string | null>(null);
	let hoveredEdgeKey = $state<string | null>(null);
	let query = $state('');
	let matchIdx = -1;
	let liveText = $state('');
	let liveTimer: ReturnType<typeof setTimeout> | null = null;

	function resolveSelected(id: string | null | undefined): string | null {
		if (!id) return null;
		if (graph.nodes.has(id)) return id;
		if (graph.netById.has(id)) return switchId(id);
		return null;
	}
	const selectedId = $derived(
		selectedIdProp !== undefined
			? resolveSelected(selectedIdProp)
			: resolveSelected(internalSel),
	);
	// 구조 갱신으로 사라진 노드의 stale hoveredId 가 캔버스 전체를 흐리게 하지 않도록 현재 그래프에 있는 경우만 활성으로 본다
	const activeId = $derived(selectedId ?? (hoveredId && graph.nodes.has(hoveredId) ? hoveredId : null));
	const activeNode = $derived(activeId ? (graph.nodes.get(activeId) ?? null) : null);
	const selectedNode = $derived(selectedId ? (graph.nodes.get(selectedId) ?? null) : null);
	/** 존 라벨 aria-pressed 용: 스위치(네트워크)가 선택된 경우에만 채운다(호버 파생 activeNets 와 분리) */
	const selectedNetId = $derived(selectedNode?.kind === 'switch' ? selectedNode.netId : null);
	const related = $derived(activeId ? relatedSet(graph, layout, activeId) : null);
	const activeNets = $derived.by(() => {
		const set = new Set<string>();
		if (!activeNode || !activeId) return set;
		if (activeNode.kind === 'switch') set.add(activeNode.netId);
		for (const nid of activeNode.netIds) set.add(nid);
		// FIP 선은 그 IP 가 속한 외부망 스위치로 이어진다 → 그 외부망 존·라벨도 함께 강조해야
		// 선·카드만 켜지고 존 틴트는 꺼지는 반쪽 강조가 생기지 않는다
		if (activeNode.kind === 'vm') {
			for (const nic of activeNode.nics) for (const f of nic.fips) if (f.netId) set.add(f.netId);
		}
		for (const [nid, members] of layout.zoneMembers) if (members.includes(activeId)) set.add(nid);
		return set;
	});
	const match = $derived(matchesQuery(graph, query));
	const matchList = $derived(match ? layout.domOrder.filter((id) => match.nodes.has(id)) : []);

	function announce(msg: string) {
		if (liveTimer) clearTimeout(liveTimer);
		liveText = '';
		liveTimer = setTimeout(() => { liveText = msg; }, 30);
	}

	function select(id: string) {
		const node = graph.nodes.get(id);
		if (!node) return;
		// 같은 노드를 다시 누르면 선택 해제다 — 부모 핸들러도 토글이므로 두 모드에서 aria-pressed 와 패널 상태가 일치한다
		if (selectedId === id) { clearSelection(); return; }
		announce(`${KIND_LABEL[node.kind]} ${node.name} 선택됨`);
		internalSel = id;
		if (node.kind === 'vm') onSelectInstance?.(node.id);
		else if (node.kind === 'router') onSelectRouter?.(node.id);
		else if (node.kind === 'lb') onSelectLoadBalancer?.(node.raw);
		else if (node.kind === 'switch') onSelectNetwork?.(node.netId);
	}

	function selectNetwork(netId: string) {
		if (!graph.netById.has(netId)) return;
		select(switchId(netId));
	}

	function clearSelection() {
		const cur = selectedId;
		if (!cur) return;
		const node = graph.nodes.get(cur);
		internalSel = null;
		if (!node) return;
		// 부모가 토글 방식으로 패널을 닫도록 같은 콜백을 다시 호출한다(제어·비제어 모드 동일)
		if (node.kind === 'vm') onSelectInstance?.(node.id);
		else if (node.kind === 'router') onSelectRouter?.(node.id);
		else if (node.kind === 'lb') onSelectLoadBalancer?.(node.raw);
		else if (node.kind === 'switch') onSelectNetwork?.(node.netId);
	}

	function fireIntent(id: string) {
		const node = graph.nodes.get(id);
		if (node?.kind === 'vm') onIntentInstance?.(id);
		else if (node?.kind === 'router') onIntentRouter?.(id);
	}

	function setHover(id: string | null) {
		if (hoveredId === id) return;
		if (hoveredId) onCancelIntent?.();
		hoveredId = id;
		if (id) fireIntent(id);
	}

	function onNodeFocus(id: string) {
		ensureVisible(id);
		fireIntent(id);
	}

	function onNodeBlur() {
		onCancelIntent?.();
	}

	// ───────── 기하·스타일 파생
	const memberEdges = $derived(activeNode?.kind === 'lb' ? buildMemberEdges(graph, activeNode.id, pos) : []);
	const allEdges = $derived([...graph.edges, ...memberEdges]);
	const geometry = $derived.by(() => {
		const res = computeGeometry(graph, { pos, zoneMembers: layout.zoneMembers }, memberEdges, slotOrderCache);
		slotOrderCache = res.slotOrder;
		return res;
	});
	const baseStyles = $derived.by(() => {
		const m = new Map<string, EdgeStyle>();
		for (const e of allEdges) m.set(e.key, edgeStyle(e, traffic, graph));
		return m;
	});
	const nicRates = $derived.by(() => {
		const m = new Map<string, string>();
		for (const e of graph.edges) if (e.kind === 'cable' && e.nic) m.set(e.nic.key, fmtRateShort(edgeRate(e, traffic)));
		return m;
	});

	const edgeRender = $derived.by((): EdgeRenderItem[] => {
		const out: EdgeRenderItem[] = [];
		const q = match;
		const active = activeId;
		for (const e of allEdges) {
			const g = geometry.geom.get(e.key);
			const base = baseStyles.get(e.key);
			if (!g || !base) continue;
			let op = base.opacity, w = base.width;
			const incident = Boolean(active) && (e.from === active || e.to === active);
			const hovered = hoveredEdgeKey === e.key || (hoveredNicKey != null && e.nic?.key === hoveredNicKey);
			if (active) op = incident ? Math.min(1, op * 1.4) : selectedId ? 0.12 : 0.2;
			else if (q && !(q.nodes.has(e.from) || q.nodes.has(e.to))) op = 0.15;
			if (hovered) { op = 1; w = base.width + 0.5; }
			const toNode = graph.nodes.get(e.to);
			const net = graph.netById.get(e.netId);
			out.push({
				key: e.key,
				kind: e.kind,
				netId: e.netId,
				d: g.d,
				color: colorOfNet(graph, e.netId),
				opacity: op,
				width: w,
				dash: base.dash,
				forced: e.kind === 'fip' && incident,
				hitTitle: e.kind === 'trunk'
					? `트렁크 · ${net?.name ?? ''} · 네트워크 합산 트래픽 (라우터 exporter 없음)`
					: null,
				port: toNode?.kind === 'switch' && (e.kind === 'cable' || e.kind === 'lbvip') ? g.b : null,
			});
		}
		return out;
	});

	const zoneRender = $derived.by((): ZoneRenderItem[] =>
		graph.nets
			.map((n) => ({ n, rect: geometry.zones.get(n.id) }))
			.filter((z): z is { n: CanvasNet; rect: Rect } => Boolean(z.rect))
			.sort((a, b) => b.rect.w * b.rect.h - a.rect.w * a.rect.h)
			.map(({ n, rect }) => ({
				netId: n.id,
				name: n.name,
				rect,
				color: n.color,
				active: activeNets.has(n.id),
				dim: Boolean(match) && !match!.nets.has(n.id),
				match: Boolean(match) && match!.nets.has(n.id),
				down: n.status !== 'ACTIVE',
			})),
	);

	function segmentLabel(n: CanvasNet): string | null {
		const r = n.raw;
		if (r.provider_segmentation_id == null) return null;
		return `${r.provider_network_type === 'vlan' ? 'VLAN 태그' : 'VXLAN VNI'} ${r.provider_segmentation_id}`;
	}

	const hudLabels = $derived.by((): HudLabelItem[] => {
		const { panX, panY, k } = vp;
		const out: HudLabelItem[] = [];
		// 행(밴드)마다 따로 돌아야 한다 — 아래 prev 밀기는 "같은 줄에서 왼쪽 존과 겹치면 오른쪽으로" 규칙이라
		// 여러 행을 flatten 한 배열로 돌리면 행 경계를 넘어 이어져 라벨이 자기 존 밖으로 밀린다.
		for (const list of [layout.order.provider, ...layout.bands.rows.map((r) => r.netIds)]) {
			let prev: Rect | null = null;
			for (const nid of list) {
				const z = geometry.zones.get(nid);
				const n = graph.netById.get(nid);
				if (!z || !n) continue;
				let lx = z.x + 12;
				if (prev && prev.x + prev.w > z.x) lx = prev.x + prev.w + 12;
				const sx = lx * k + panX, sy = z.y * k + panY;
				const avail = Math.max(56, (z.x + z.w) * k + panX - sx - 8);
				const adminPills: string[] = [];
				if (adminView) {
					const seg = segmentLabel(n);
					if (seg) adminPills.push(seg);
					if (n.raw.mtu != null) adminPills.push(`MTU ${n.raw.mtu}`);
				}
				const dimBySearch = Boolean(match) && !match!.nets.has(nid);
				const dimByActive = !match && Boolean(activeId) && !activeNets.has(nid) && !(related?.has(switchId(nid)) ?? false);
				out.push({
					netId: nid,
					name: n.name,
					cidrText: n.cidrs.length > 1 ? `${n.cidrs[0]} 외 ${n.cidrs.length - 1}` : (n.cidrs[0] ?? ''),
					kindLabel: NET_KIND_LABEL[n.kind],
					isInternet: n.kind === 'external',
					isolated: n.isolated,
					statusText: n.status !== 'ACTIVE' ? n.status : null,
					adminPills,
					color: n.color,
					sx,
					sy,
					avail,
					size: avail >= 240 ? 'full' : avail >= 120 ? 'mid' : 'min',
					active: activeNets.has(nid),
					dim: dimBySearch || dimByActive,
				});
				prev = z;
			}
		}
		return out;
	});

	const hudBadges = $derived.by((): HudBadgeItem[] => {
		const { panX, panY, k } = vp;
		const out: HudBadgeItem[] = [];
		for (const e of graph.edges) {
			if (e.kind !== 'trunk') continue;
			const g = geometry.geom.get(e.key);
			if (!g) continue;
			const incident = Boolean(activeId) && (e.from === activeId || e.to === activeId);
			out.push({
				key: e.key,
				netId: e.netId,
				netName: graph.netById.get(e.netId)?.name ?? '',
				sx: g.mid.x * k + panX,
				sy: g.mid.y * k + panY,
				rateText: fmtRate(edgeRate(e, traffic)),
				dim: (Boolean(activeId) && !incident) || (Boolean(match) && !match!.nets.has(e.netId)),
			});
		}
		return out;
	});

	const offscreen = $derived.by(() => {
		if (vw <= 0 || vh <= 0) return false;
		const b = contentBounds(geometry.zones, pos);
		const { panX, panY, k } = vp;
		const x1 = b.x * k + panX, y1 = b.y * k + panY, x2 = x1 + b.w * k, y2 = y1 + b.h * k;
		return x2 < 0 || y2 < 0 || x1 > vw || y1 > vh;
	});

	// ───────── rAF 스케줄러(프레임당 뷰 1회 + 드래그 위치 1회)
	let raf = 0;
	let pendingView: ViewState | null = null;
	let pendingDrag: { id: string; x: number; y: number } | null = null;
	const rafFn = (cb: FrameRequestCallback): number =>
		typeof requestAnimationFrame === 'function' ? requestAnimationFrame(cb) : (setTimeout(() => cb(performance.now()), 16) as unknown as number);
	const cafFn = (id: number) => { if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(id); else clearTimeout(id); };
	function schedule() { if (!raf) raf = rafFn(frame); }
	function flushPending() {
		if (pendingView) { vp.set(pendingView); pendingView = null; }
		if (pendingDrag) {
			const cur = pos.get(pendingDrag.id);
			if (cur) pos.set(pendingDrag.id, { ...cur, x: pendingDrag.x, y: pendingDrag.y });
			pendingDrag = null;
		}
	}
	function frame() { raf = 0; flushPending(); }
	function currentView(): ViewState { return pendingView ?? vp.view; }

	// ───────── 뷰 조작
	function fitAll() {
		const { w, h } = measure();
		pendingView = null;
		vp.fitBounds(contentBounds(geometry.zones, pos), w, h, 40, FIT_K_MAX);
	}
	function fitZone(nid: string) {
		const z = geometry.zones.get(nid);
		if (!z) return;
		const { w, h } = measure();
		pendingView = null;
		vp.fitBounds(z, w, h, 48, 1.4);
	}
	function zoomBy(f: number) {
		const { w, h } = measure();
		pendingView = zoomAtPure(currentView(), w / 2, h / 2, currentView().k * f);
		schedule();
	}
	function focusNode(id: string, kMin = K_MIN, kMax = FIT_K_MAX) {
		const b = nodeBounds(id, { pos, zoneMembers: layout.zoneMembers }, geometry.zones);
		if (!b) return;
		const { w, h } = measure();
		pendingView = null;
		vp.fitBounds(b, w, h, 48, kMax, kMin);
	}
	function ensureVisible(id: string) {
		const p = pos.get(id);
		if (!p) return;
		const { w, h } = measure();
		if (w <= 0 || h <= 0) return;
		const { panX, panY, k } = currentView();
		const sx1 = p.x * k + panX, sy1 = p.y * k + panY, sx2 = sx1 + p.w * k, sy2 = sy1 + p.h * k;
		if (sx1 >= 0 && sy1 >= 0 && sx2 <= w && sy2 <= h) return;
		pendingView = { k, panX: w / 2 - (p.x + p.w / 2) * k, panY: h / 2 - (p.y + p.h / 2) * k };
		schedule();
	}

	function commitManual(id: string) {
		flushPending();
		const dropped = pos.get(id);
		if (!dropped) return;
		// 저장하는 것은 **사용자가 놓은 자리(의도)** 다. 밀어낸 결과를 저장하면 다음 구조 갱신 때
		// 그 값을 다시 해소해 핀이 조금씩 걸어간다. 의도를 두면 해소가 (의도, 자동 배치)의 순수 함수가 된다.
		const r = { ...dropped };
		// 화면에는 겹치지 않는 가까운 자리를 보여준다(방금 놓은 노드만 움직인다).
		const moved = resolveManualOverlap(pos, [id]);
		if (moved[id]) {
			pos.set(id, { ...pos.get(id)!, ...moved[id] });
			announce(`${graph.nodes.get(id)?.name ?? '노드'} 를 겹치지 않는 가까운 자리로 옮겼습니다`);
		}
		const auto = autoPos.get(id);
		if (auto && auto.x === r.x && auto.y === r.y) {
			// 자동 배치 좌표와 같으면 핀을 만들지 않는다(이미 있던 핀은 해제)
			if (!(id in manual)) return;
			const rest = { ...manual };
			delete rest[id];
			manual = rest;
		} else {
			manual = { ...manual, [id]: { x: r.x, y: r.y } };
		}
		persistManual(storageKey, manual);
	}

	function resetLayout() {
		const fresh = autoLayout(graph);
		manual = {};
		clearManualPositions(storageKey);
		lastSaved = {};
		slotOrderCache = undefined;
		pendingDrag = null;
		for (const [id, r] of fresh.pos) pos.set(id, { ...r });
		fitAll();
		announce('배치를 초기화했습니다');
	}

	function nudge(id: string, dx: number, dy: number) {
		flushPending();
		const r = pos.get(id);
		if (!r) return;
		pos.set(id, { ...r, x: r.x + dx, y: r.y + dy });
		commitManual(id);
	}

	function onSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			query = '';
			matchIdx = -1;
			(e.target as HTMLInputElement | null)?.blur();
			viewportEl?.focus({ preventScroll: true });
		} else if (e.key === 'Enter' && matchList.length) {
			e.preventDefault();
			matchIdx = (matchIdx + 1) % matchList.length;
			const id = matchList[matchIdx];
			focusNode(id);
			announce(`${matchIdx + 1}/${matchList.length} ${graph.nodes.get(id)?.name ?? id}`);
		}
	}

	// 검색어 변경: 결과 수를 aria-live 로 알린다
	$effect(() => {
		const m = match;
		const n = matchList.length;
		untrack(() => {
			matchIdx = -1;
			if (m) announce(n ? `검색 결과 ${n}개` : '검색 결과 없음');
		});
	});

	// ───────── 포인터·키보드(모두 뷰포트 한 곳에, 명령형 등록: wheel passive:false, a11y 린트 회피가 아니라 단일 제스처 모델 유지 목적)
	type Gesture = {
		id: string | null;
		target: 'node' | 'zone' | 'edge' | 'bg';
		zoneNet: string | null;
		c0: { x: number; y: number };
		p0: Rect | null;
		view0: ViewState;
		moved: boolean;
		type: string;
		dragArmed: boolean;
	};
	type Pinch = { k0: number; view0: ViewState; mid0: { x: number; y: number }; dist0: number };
	let pinching = false;
	/** 존/배경 더블클릭 억제용: 직전 클릭 판정의 대상과 시각 */
	const DBL_SUPPRESS_MS = 300;

	$effect(() => {
		const el = viewportEl;
		if (!el) return;
		const pointers = new Map<number, { x: number; y: number }>();
		let gesture: Gesture | null = null;
		let pinch: Pinch | null = null;
		// 핀치가 한 번이라도 시작된 멀티터치 시퀀스: 남은 포인터는 클릭·드래그로 해석하지 않는다(모든 포인터가 떨어지면 해제)
		let pinchConsumed = false;
		let lastClick: { key: string; t: number } | null = null;
		let longPress: ReturnType<typeof setTimeout> | null = null;
		const clearLongPress = () => { if (longPress) { clearTimeout(longPress); longPress = null; } };
		const closest = (t: EventTarget | null, sel: string): HTMLElement | SVGElement | null =>
			t instanceof Element ? (t.closest(sel) as HTMLElement | SVGElement | null) : null;
		const local = (e: PointerEvent) => { const r = el.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };

		const onDown = (e: PointerEvent) => {
			if (e.pointerType === 'mouse' && e.button !== 0) return;
			if (closest(e.target, '[data-hud-control]')) return;
			try { el.setPointerCapture?.(e.pointerId); } catch { /* jsdom 등 미지원 환경 */ }
			if (pointers.size === 0) pinchConsumed = false;
			pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
			if (pointers.size === 2) {
				const pts = [...pointers.values()];
				const r = el.getBoundingClientRect();
				pinch = {
					k0: currentView().k,
					view0: { ...currentView() },
					mid0: { x: (pts[0].x + pts[1].x) / 2 - r.left, y: (pts[0].y + pts[1].y) / 2 - r.top },
					dist0: Math.max(1, Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y)),
				};
				pinching = true;
				pinchConsumed = true;
				gesture = null;
				draggingId = null;
				armedId = null;
				// 중단된 드래그의 대기 프레임은 버린다(반영되면 manual 핀 없이 위치만 어긋난다)
				pendingDrag = null;
				// 팬이 핀치로 승격되면 팬 상태(.is-panning)도 해제한다
				panning = false;
				clearLongPress();
				stopFlow();
				return;
			}
			// 세 번째 이후 포인터는 새 제스처를 만들지 않는다(놓을 때 select/clearSelection 오발화 방지)
			if (pinchConsumed) return;
			const nodeEl = closest(e.target, '[data-node-id]');
			const zoneEl = closest(e.target, '[data-zone-net]');
			const edgeEl = closest(e.target, '[data-edge-net]');
			const id = nodeEl?.getAttribute('data-node-id') ?? null;
			const p = id ? pos.get(id) : null;
			gesture = {
				id,
				target: nodeEl ? 'node' : zoneEl ? 'zone' : edgeEl ? 'edge' : 'bg',
				zoneNet: zoneEl?.getAttribute('data-zone-net') ?? edgeEl?.getAttribute('data-edge-net') ?? null,
				c0: { x: e.clientX, y: e.clientY },
				p0: p ? { ...p } : null,
				view0: { ...currentView() },
				moved: false,
				type: e.pointerType,
				dragArmed: Boolean(id) && e.pointerType !== 'touch',
			};
			if (!nodeEl) el.focus({ preventScroll: true });
			if (nodeEl && e.pointerType === 'touch') {
				longPress = setTimeout(() => {
					if (gesture && !gesture.moved) { gesture.dragArmed = true; armedId = gesture.id; }
				}, 350);
			}
			gesturing = true;
		};

		const onMove = (e: PointerEvent) => {
			if (!pointers.has(e.pointerId)) return;
			pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
			if (pinch) {
				const pts = [...pointers.values()];
				if (pts.length < 2) return;
				const r = el.getBoundingClientRect();
				const mid = { x: (pts[0].x + pts[1].x) / 2 - r.left, y: (pts[0].y + pts[1].y) / 2 - r.top };
				const dist = Math.max(1, Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y));
				const k2 = clamp((pinch.k0 * dist) / pinch.dist0, K_MIN, K_MAX);
				const { mid0, view0, k0 } = pinch;
				pendingView = { k: k2, panX: mid.x - (mid0.x - view0.panX) * (k2 / k0), panY: mid.y - (mid0.y - view0.panY) * (k2 / k0) };
				schedule();
				return;
			}
			const g = gesture;
			if (!g) return;
			const dx = e.clientX - g.c0.x, dy = e.clientY - g.c0.y;
			const thr = g.type === 'touch' ? 8 : 4;
			if (!g.moved) {
				if (Math.hypot(dx, dy) < thr) return;
				g.moved = true;
				if (g.dragArmed && g.id) draggingId = g.id;
				else { clearLongPress(); g.dragArmed = false; panning = true; }
			}
			if (g.dragArmed && g.id && g.p0) {
				const k = g.view0.k;
				pendingDrag = { id: g.id, x: g.p0.x + dx / k, y: g.p0.y + dy / k };
			} else {
				pendingView = { k: g.view0.k, panX: g.view0.panX + dx, panY: g.view0.panY + dy };
			}
			schedule();
		};

		const onEnd = (e: PointerEvent) => {
			pointers.delete(e.pointerId);
			clearLongPress();
			if (pinch) {
				if (pointers.size < 2) { pinch = null; pinching = false; panning = false; gesturing = false; resumeFlow(); }
				if (pointers.size === 0) pinchConsumed = false;
				return;
			}
			if (pinchConsumed) {
				// 핀치가 소비한 시퀀스의 잔여 포인터: 클릭·드래그 판정 없이 상태만 정리한다
				gesture = null;
				draggingId = null;
				armedId = null;
				pendingDrag = null;
				panning = false;
				if (pointers.size === 0) { pinchConsumed = false; gesturing = false; }
				return;
			}
			const g = gesture;
			if (!g) return;
			gesture = null;
			draggingId = null;
			armedId = null;
			panning = false;
			gesturing = false;
			// 취소된 제스처는 대기 중인 드래그 프레임을 반영하지 않고 버린다
			if (e.type === 'pointercancel') { pendingDrag = null; return; }
			if (!g.moved) {
				if (g.target === 'node' && g.id) {
					select(g.id);
					lastClick = null;
				} else {
					// 같은 존/배경을 300ms 안에 다시 클릭한 경우(더블클릭 두 번째 up)는 판정하지 않는다 → dblclick 이 fitZone/fitAll 만 수행
					const key = `${g.target}:${g.zoneNet ?? ''}`;
					const now = performance.now();
					if (lastClick && lastClick.key === key && now - lastClick.t < DBL_SUPPRESS_MS) {
						lastClick = null;
					} else {
						lastClick = { key, t: now };
						if ((g.target === 'zone' || g.target === 'edge') && g.zoneNet) selectNetwork(g.zoneNet);
						else clearSelection();
					}
				}
			} else if (g.dragArmed && g.id) {
				commitManual(g.id);
			}
		};

		const onWheel = (e: WheelEvent) => {
			e.preventDefault();
			// deltaMode: 0 픽셀, 1 줄, 2 페이지
			const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? el.clientHeight || window.innerHeight : 1;
			const v = currentView();
			if (wheelIntent(e) === 'zoom') {
				// 마우스 휠, ctrl/⌘+휠, 트랙패드 핀치는 커서 기준 확대·축소
				const r = el.getBoundingClientRect();
				pendingView = zoomAtPure(v, e.clientX - r.left, e.clientY - r.top, v.k * Math.exp(-e.deltaY * unit * 0.0015));
			} else {
				// 트랙패드 두 손가락 스크롤은 위치 이동(스크롤 방향으로 뷰가 따라간다)
				pendingView = { k: v.k, panX: v.panX - e.deltaX * unit, panY: v.panY - e.deltaY * unit };
			}
			schedule();
		};

		const onDbl = (e: MouseEvent) => {
			if (closest(e.target, '[data-node-id], [data-hud-control]')) return;
			const zoneEl = closest(e.target, '[data-zone-net]');
			const nid = zoneEl?.getAttribute('data-zone-net');
			if (nid) fitZone(nid); else fitAll();
		};

		// NIC 행·트렁크 히트 경로 호버는 위임으로 처리한다(정적 요소에 핸들러를 두지 않기 위해)
		const onOver = (e: PointerEvent) => {
			const nic = closest(e.target, '[data-nic]')?.getAttribute('data-nic') ?? null;
			const edge = closest(e.target, '[data-edge-key]')?.getAttribute('data-edge-key') ?? null;
			if (nic !== hoveredNicKey) hoveredNicKey = nic;
			if (edge !== hoveredEdgeKey) hoveredEdgeKey = edge;
		};
		const onOut = (e: PointerEvent) => {
			if (e.relatedTarget instanceof Node && el.contains(e.relatedTarget)) return;
			hoveredNicKey = null;
			hoveredEdgeKey = null;
		};

		const onKey = (e: KeyboardEvent) => {
			const t = e.target as HTMLElement | null;
			if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
			const nodeEl = closest(t, '[data-node-id]');
			const nodeId = nodeEl?.getAttribute('data-node-id') ?? null;
			const arrow = ({ ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] } as Record<string, [number, number] | undefined>)[e.key];
			let handled = true;
			if (arrow && nodeId && e.shiftKey) nudge(nodeId, arrow[0] * 8, arrow[1] * 8);
			else if (arrow) {
				const step = e.shiftKey ? 200 : 40;
				const v = currentView();
				pendingView = { k: v.k, panX: v.panX - arrow[0] * step, panY: v.panY - arrow[1] * step };
				schedule();
			} else if (e.key === '+' || e.key === '=') zoomBy(1.2);
			else if (e.key === '-' || e.key === '_') zoomBy(1 / 1.2);
			else if (e.key === '0' || e.key === 'f' || e.key === 'F') fitAll();
			else if (e.key === 'r' || e.key === 'R') resetLayout();
			else if (e.key === 'Escape') { if (selectedId) clearSelection(); else handled = false; }
			else if (e.key === '/') searchElement?.focus();
			else handled = false;
			if (handled) e.preventDefault();
		};

		el.addEventListener('pointerdown', onDown);
		el.addEventListener('pointermove', onMove);
		el.addEventListener('pointerup', onEnd);
		el.addEventListener('pointercancel', onEnd);
		el.addEventListener('wheel', onWheel, { passive: false });
		el.addEventListener('dblclick', onDbl);
		el.addEventListener('pointerover', onOver);
		el.addEventListener('pointerout', onOut);
		el.addEventListener('keydown', onKey);
		return () => {
			clearLongPress();
			el.removeEventListener('pointerdown', onDown);
			el.removeEventListener('pointermove', onMove);
			el.removeEventListener('pointerup', onEnd);
			el.removeEventListener('pointercancel', onEnd);
			el.removeEventListener('wheel', onWheel);
			el.removeEventListener('dblclick', onDbl);
			el.removeEventListener('pointerover', onOver);
			el.removeEventListener('pointerout', onOut);
			el.removeEventListener('keydown', onKey);
		};
	});

	// ───────── 뷰포트 크기·초기 맞춤
	onMount(() => {
		// 뷰포트가 아직 측정되지 않았으면(k=1 유지) 크기가 잡힌 뒤 첫 화면 맞춤을 수행한다
		const sync = () => {
			const { w, h } = measure();
			vw = w;
			vh = h;
			if (needsInitialFit && w > 0 && h > 0) { needsInitialFit = false; fitAll(); }
		};
		sync();
		let ro: ResizeObserver | null = null;
		if (typeof ResizeObserver === 'function' && viewportEl) {
			ro = new ResizeObserver(sync);
			ro.observe(viewportEl);
		}
		const onVis = () => { if (document.visibilityState === 'visible') resumeFlow(); else stopFlow(); };
		document.addEventListener('visibilitychange', onVis);
		let mq: MediaQueryList | null = null;
		const onMq = () => { reducedMotion = prefersReducedMotion(); };
		if (typeof window.matchMedia === 'function') {
			mq = window.matchMedia(REDUCED_MOTION_QUERY);
			mq.addEventListener?.('change', onMq);
		}
		return () => {
			ro?.disconnect();
			document.removeEventListener('visibilitychange', onVis);
			mq?.removeEventListener?.('change', onMq);
			stopFlow();
			if (raf) { cafFn(raf); raf = 0; }
			if (liveTimer) clearTimeout(liveTimer);
		};
	});

	// ───────── 패킷 흐름 시뮬레이션(기본 on · 토글로 끌 수 있음 · reduced-motion 하드 off · DESIGN.md named motion exception)
	let flowOn = $state(true);
	let reducedMotion = $state(prefersReducedMotion());
	type FlowDot = { el: SVGCircleElement; key: string; t: number; dir: boolean; speed: number };
	type FlowPath = { path: SVGPathElement; d: string; len: number };
	const flow = { dots: [] as FlowDot[], paths: new Map<string, FlowPath>(), raf: 0, last: 0 };
	const hasPathApi = typeof SVGPathElement !== 'undefined' && 'getPointAtLength' in SVGPathElement.prototype && 'getTotalLength' in SVGPathElement.prototype;
	/** 실제 애니메이션 게이트: 토글 on 이고 reduced-motion 이 아닐 때만. flowOn 자체는 effect 에서 쓰지 않는다(체크박스는 툴바가 disabled 처리). */
	const flowActive = $derived(flowOn && !reducedMotion);
	const flowAllowed = () =>
		hasPathApi && flowActive && !pinching && (typeof document === 'undefined' || document.visibilityState === 'visible');

	function stopFlow() {
		if (flow.raf) cafFn(flow.raf);
		flow.raf = 0;
	}
	function resumeFlow() {
		if (flow.dots.length && !flow.raf && flowAllowed()) {
			flow.last = performance.now();
			flow.raf = rafFn(flowStep);
		}
	}
	function flowStep(ts: number) {
		flow.raf = 0;
		if (!flowAllowed()) return;
		const dt = Math.min(0.05, (ts - flow.last) / 1000);
		flow.last = ts;
		for (const d of flow.dots) {
			const fp = flow.paths.get(d.key);
			if (!fp) continue;
			const cur = fp.path.getAttribute('d') ?? '';
			if (cur !== fp.d) { fp.d = cur; fp.len = fp.path.getTotalLength() || 1; }
			d.t = (d.t + (dt * d.speed) / fp.len) % 1;
			const p = fp.path.getPointAtLength((d.dir ? d.t : 1 - d.t) * fp.len);
			d.el.setAttribute('transform', `translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})`);
		}
		flow.raf = rafFn(flowStep);
	}
	function rebuildFlow() {
		stopFlow();
		const g = flowGroupEl;
		if (g) g.replaceChildren();
		flow.dots = [];
		flow.paths.clear();
		if (!g || !flowAllowed() || !viewportEl) return;
		for (const p of viewportEl.querySelectorAll<SVGPathElement>('path.edge[data-key]')) {
			const key = p.getAttribute('data-key');
			if (key) flow.paths.set(key, { path: p, d: p.getAttribute('d') ?? '', len: p.getTotalLength() || 1 });
		}
		const cands: { e: CanvasEdge; bps: number; rate: { rx_bps: number; tx_bps: number } }[] = [];
		for (const e of graph.edges) {
			if (e.kind !== 'cable' && e.kind !== 'trunk') continue;
			const st = baseStyles.get(e.key);
			if (!st?.bps || !st.rate) continue;
			const from = graph.nodes.get(e.from);
			if (from?.kind === 'vm' && from.status === 'SHUTOFF') continue;
			if (from?.kind === 'router' && from.status === 'DOWN') continue;
			if (st.bps < FLOW_MIN_BPS) continue;
			cands.push({ e, bps: st.bps, rate: st.rate });
		}
		cands.sort((a, b) => b.bps - a.bps);
		let total = 0;
		const r = (2.5 / Math.max(vp.k, K_MIN)).toFixed(2);
		const emit = (key: string, netId: string, n: number, dir: boolean, speed: number, internal: boolean) => {
			for (let i = 0; i < n; i++) {
				const el = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
				el.setAttribute('class', internal ? 'flow-dot is-internal' : 'flow-dot');
				el.setAttribute('r', r);
				el.style.setProperty('--net', colorOfNet(graph, netId));
				g.append(el);
				flow.dots.push({ el, key, t: i / n, dir, speed });
			}
		};
		for (const c of cands) {
			if (total >= 60) break;
			const p = flow.paths.get(c.e.key);
			if (!p) continue;
			const isolatedNet = graph.netById.get(c.e.netId)?.isolated === true;
			for (const s of flowStreams(c.e, c.rate, isolatedNet)) {
				if (total >= 60) break;
				// 점 개수는 경로 길이에 맞춰 정한다 — 목표는 개수가 아니라 통과 **빈도**다
				const n = Math.min(flowDotCount(s.bps, p.len), 60 - total);
				total += n;
				emit(c.e.key, c.e.netId, n, s.dir, flowRate(s.bps).speed, s.internal);
			}
		}
		resumeFlow();
	}
	// 게이트(토글+reduced-motion)·구조·트래픽 변화에만 재생성한다(드래그·팬은 점 개수를 바꾸지 않는다)
	$effect(() => {
		void flowActive; void built; void baseStyles; void flowGroupEl;
		untrack(rebuildFlow);
		return stopFlow;
	});
	$effect(() => {
		const r = (2.5 / Math.max(vp.k, K_MIN)).toFixed(2);
		untrack(() => { for (const d of flow.dots) d.el.setAttribute('r', r); });
	});

	// ───────── DOM 순서·투어 셀렉터
	const firstRouterId = $derived(layout.domOrder.find((id) => graph.nodes.get(id)?.kind === 'router') ?? null);
	const helpId = 'topology-canvas-help';
</script>

<div class="canvas-root">
	<CanvasToolbar
		bind:query
		bind:flowOn
		bind:searchElement
		{reducedMotion}
		matchCount={match ? matchList.length : null}
		onfit={fitAll}
		onreset={resetLayout}
		onsearchkeydown={onSearchKeydown}
	/>

	<div class="stage">
		<!-- role=application 은 WAI-ARIA 위젯 컨테이너이며 포커스를 받아 키보드 조작을 위임한다. aria-query 분류 때문에 svelte 가 오탐한다. -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<div
			bind:this={viewportEl}
			class="viewport"
			class:is-panning={panning}
			role="application"
			tabindex="0"
			aria-label="네트워크 토폴로지 캔버스"
			aria-describedby={helpId}
			data-badges={badgesHidden ? 'hidden' : 'shown'}
			style:background-size={gridSize}
			style:background-position={gridPosition}
		>
			<div class="world topology-world" class:is-gesturing={gesturing} data-lod={lod} style:transform={worldTransform}>
				<CanvasZoneLayer zones={zoneRender} width={svgW} height={svgH} />
				<CanvasEdgeLayer edges={edgeRender} width={svgW} height={svgH} />
				<svg class="layer-flow" aria-hidden="true" width={svgW} height={svgH}><g bind:this={flowGroupEl}></g></svg>
				<div class="layer-nodes">
					{#each layout.domOrder as id (id)}
						{@const node = graph.nodes.get(id)}
						{@const rect = pos.get(id)}
						{#if node && rect}
							<CanvasNodeCard
								{node}
								{rect}
								{graph}
								selected={id === selectedId}
								dim={Boolean(match) && !match!.nodes.has(id)}
								faded={!match && Boolean(activeId) && !(related?.has(id) ?? true)}
								dragging={draggingId === id}
								armed={armedId === id}
								{nicRates}
								rateText={node.kind === 'switch' ? fmtRate(traffic?.networks?.[node.netId]) : node.kind === 'lb' ? fmtRate(traffic?.load_balancers?.[id]) : null}
								dataTour={id === firstRouterId ? 'admin-network-resource' : undefined}
								onselect={select}
								onhover={setHover}
								onfocusnode={onNodeFocus}
								onblurnode={onNodeBlur}
							/>
						{/if}
					{/each}
				</div>
			</div>

			<CanvasHud labels={hudLabels} badges={hudBadges} {badgesHidden} {selectedNetId} onselectnet={selectNetwork} />

			<div class="corner" data-hud-control>
				<Button variant="secondary" size="icon" ariaLabel="확대" title="확대 (+)" onclick={() => zoomBy(1.2)}>+</Button>
				<Button variant="secondary" size="icon" ariaLabel="축소" title="축소 (−)" onclick={() => zoomBy(1 / 1.2)}>−</Button>
				<Button variant="secondary" size="icon" ariaLabel="화면 맞춤" title="화면 맞춤 (0)" onclick={fitAll}>⤢</Button>
			</div>

			{#if offscreen}
				<div class="offscreen-hint" data-hud-control>
					<Button variant="secondary" size="sm" onclick={fitAll}>콘텐츠로 돌아가기</Button>
				</div>
			{/if}
			{#if manualCount > 0}
				<div class="manual-chip" data-hud-control>
					<Button variant="subtle" size="xs" onclick={resetLayout}>수동 배치 {manualCount}개 · 초기화</Button>
				</div>
			{/if}
		</div>
		<p class="stage-help" id={helpId}>
			트랙패드 두 손가락 스크롤로 화면 이동, 마우스 휠·<span class="mono">Ctrl</span>(<span class="mono">⌘</span>)+휠·핀치로 확대·축소. 캔버스에 포커스한 뒤 화살표로 화면 이동(<span class="mono">Shift</span>와 함께 누르면 크게), <span class="mono">+</span>/<span class="mono">-</span> 확대·축소, <span class="mono">0</span>·<span class="mono">f</span> 화면 맞춤, <span class="mono">r</span> 배치 초기화, <span class="mono">/</span> 검색, <span class="mono">Esc</span> 선택 해제. 노드에 포커스한 뒤 <span class="mono">Enter</span>로 상세, <span class="mono">Shift+화살표</span>로 노드 이동.
		</p>
	</div>

	<div class="sr-only" aria-live="polite" aria-atomic="true">{liveText}</div>
</div>

<style>
	.canvas-root { display: grid; gap: 0.75rem; }
	.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
	.stage { position: relative; }
	.viewport {
		position: relative;
		overflow: hidden;
		height: clamp(420px, 68dvh, 820px);
		border: 1px solid var(--color-line);
		border-radius: 0.5rem;
		background-color: var(--color-surface-canvas);
		background-image:
			linear-gradient(var(--color-topology-grid-major) 1px, transparent 1px),
			linear-gradient(90deg, var(--color-topology-grid-major) 1px, transparent 1px),
			linear-gradient(var(--color-topology-grid-minor) 1px, transparent 1px),
			linear-gradient(90deg, var(--color-topology-grid-minor) 1px, transparent 1px);
		touch-action: none;
		cursor: grab;
		user-select: none;
		-webkit-user-select: none;
		outline: none;
	}
	.viewport:focus-visible { box-shadow: var(--focus-ring); }
	.viewport.is-panning { cursor: grabbing; }
	@media (max-width: 767px) { .viewport { height: min(62dvh, 560px); } }
	.world { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
	.world.is-gesturing { will-change: transform; }
	.layer-flow { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none; }
	.layer-flow :global(.flow-dot) { fill: var(--net); stroke: var(--color-surface-base); stroke-width: 1; pointer-events: none; }
	/* 내부 통신(라우터 없는 망) 점은 테두리를 없애 게이트웨이 방향 점과 구분한다 — 색만으로 구분하지 않도록 범례에 설명이 있다 */
	.layer-flow :global(.flow-dot.is-internal) { stroke: none; }
	.layer-nodes { position: absolute; left: 0; top: 0; width: 0; height: 0; }
	.corner { position: absolute; right: 0.75rem; bottom: 0.75rem; display: flex; flex-direction: column; gap: 0.25rem; }
	@media (max-width: 767px) { .corner :global(.btn-icon) { width: 44px; height: 44px; } }
	.offscreen-hint { position: absolute; left: 50%; top: 0.75rem; transform: translateX(-50%); }
	.manual-chip { position: absolute; left: 0.75rem; bottom: 0.75rem; }
	.stage-help { margin: 0.375rem 0.25rem 0; font-size: 0.75rem; color: var(--color-ink-3); }
	.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
	@media (forced-colors: active) {
		.viewport:focus-visible { outline: 2px solid CanvasText; }
	}
</style>
