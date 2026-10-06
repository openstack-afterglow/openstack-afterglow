<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import { onMount, untrack, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import NetworkLane from './topology/NetworkLane.svelte';
	import ConnectionOverlay from './topology/ConnectionOverlay.svelte';
	import TopologyHeader from './topology/TopologyHeader.svelte';
	import TopologySidebar from './topology/TopologySidebar.svelte';
	import { createTopologyDerivedController } from './topology/topologyDerivedController.svelte.ts';
	import { createFirstArrival } from './topology/firstArrival.svelte.ts';
	import { LANE_W, LANE_GAP, LANE_PAD, SIDEBAR_W } from './topology/topologyHelpers.ts';
	import type {
		TopologyData, TopologyTraffic, TopologyLoadBalancer, ItemRow,
	} from './topology/types.ts';

	let {
		data,
		projectId = null,
		showAll = false,
		arrivalScope = projectId ?? '',
		fitWidth: _fitWidth = false,
		traffic = null,
		selectedId: selectedIdProp = undefined as string | null | undefined,
		onSelectInstance = undefined,
		onSelectRouter = undefined,
		onSelectLoadBalancer = undefined,
		onIntentInstance = undefined,
		onIntentRouter = undefined,
		onCancelIntent = undefined,
	}: {
		data: TopologyData;
		projectId?: string | null;
		showAll?: boolean;
		arrivalScope?: string;
		fitWidth?: boolean;
		traffic?: TopologyTraffic | null;
		selectedId?: string | null;
		onSelectInstance?: (id: string) => void;
		onSelectRouter?: (id: string) => void;
		onSelectLoadBalancer?: (lb: TopologyLoadBalancer) => void;
		onIntentInstance?: (id: string) => void;
		onIntentRouter?: (id: string) => void;
		onCancelIntent?: () => void;
	} = $props();

	// selectedId: 부모가 prop 으로 전달하면 controlled, 아니면 내부 상태 사용
	let _selectedId = $state<string | null>(null);
	const selectedId = $derived(selectedIdProp !== undefined ? selectedIdProp : _selectedId);
	let hoveredId = $state<string | null>(null);
	let isLight = $state(false);
	let searchTerm = $state('');
	let highlightedNetId = $state<string | null>(null);
	let groupCollapsed = $state({ router: false, lb: false, instance: false });
	let containerEl = $state<HTMLElement | null>(null);
	let sidebarEl = $state<HTMLElement | null>(null);
	let sidebarHeight = $state(0);
	let scrollEl = $state<HTMLElement | null>(null);
	let scrollLeft = $state(0);
	let anchors = $state(new Map<string, { x: number; y: number }>());

	function onBodyScroll() { scrollLeft = scrollEl?.scrollLeft ?? 0; }

	const ctrl = createTopologyDerivedController({
		data: () => data,
		projectId: () => projectId,
		showAll: () => showAll,
		traffic: () => traffic,
		selectedId: () => selectedId,
		hoveredId: () => hoveredId,
		anchors: () => anchors,
		sidebarHeight: () => sidebarHeight,
		searchTerm: () => searchTerm,
	});

	// 진입 모션은 스코프(프로젝트·전체 보기)별 첫 도착에만 켠다. 자동 갱신·재측정·스크롤·검색·그룹 접기는 다시 켜지 않는다.
	const arrival = createFirstArrival({
		scope: () => arrivalScope,
		data: () => data,
		filter: () => `${projectId ?? ''}|${showAll}|${searchTerm}|${groupCollapsed.router}|${groupCollapsed.lb}|${groupCollapsed.instance}`,
		ready: () => ctrl.orderedNetworks.length > 0 || ctrl.filteredRows.length > 0 || ctrl.filteredLbItems.length > 0,
	});

	function offsetWithin(el: HTMLElement, ancestor: HTMLElement): { x: number; y: number } {
		let x = 0, y = 0;
		let cur: HTMLElement | null = el;
		while (cur && cur !== ancestor) {
			x += cur.offsetLeft;
			y += cur.offsetTop;
			cur = cur.offsetParent as HTMLElement | null;
		}
		return { x, y };
	}

	function measureAnchors() {
		if (!sidebarEl) return;
		const m = new Map<string, { x: number; y: number }>();
		for (const el of sidebarEl.querySelectorAll<HTMLElement>('[data-anchor-key]')) {
			const key = el.dataset.anchorKey;
			if (!key) continue;
			const off = offsetWithin(el, sidebarEl);
			m.set(key, { x: off.x + el.offsetWidth, y: off.y + el.offsetHeight / 2 });
		}
		untrack(() => { anchors = m; });
	}

	let raf = 0;
	function scheduleMeasure() {
		cancelAnimationFrame(raf);
		raf = requestAnimationFrame(() => measureAnchors());
	}

	onMount(() => {
		isLight = document.documentElement.classList.contains('light');
		const themeObs = new MutationObserver(() => {
			isLight = document.documentElement.classList.contains('light');
		});
		themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

		const ro = new ResizeObserver((entries) => {
			for (const entry of entries) {
				if (entry.target === sidebarEl) {
					untrack(() => { sidebarHeight = entry.contentRect.height; });
				}
			}
			scheduleMeasure();
		});
		if (containerEl) ro.observe(containerEl);
		if (sidebarEl) ro.observe(sidebarEl);

		tick().then(() => {
			if (sidebarEl) sidebarHeight = sidebarEl.offsetHeight;
			measureAnchors();
		});

		return () => { themeObs.disconnect(); ro.disconnect(); cancelAnimationFrame(raf); };
	});

	$effect(() => {
		void ctrl.filteredRows; void ctrl.filteredLbItems;
		scheduleMeasure();
	});


	function intentRow(row: ItemRow) {
		if (row.type === 'instance') onIntentInstance?.(row.id);
		else if (row.type === 'router') onIntentRouter?.(row.id);
	}
	function selectRow(row: ItemRow) {
		onCancelIntent?.();
		if (selectedIdProp === undefined) {
			_selectedId = _selectedId === row.id ? null : row.id;
		}
		if (row.type === 'instance') {
			onSelectInstance?.(row.id);
			if (!onSelectInstance) goto(`/dashboard/instances/${row.id}`);
		} else if (row.type === 'router') onSelectRouter?.(row.id);
	}

	function selectLb(lb: TopologyLoadBalancer) {
		onCancelIntent?.();
		if (selectedIdProp === undefined) {
			_selectedId = _selectedId === lb.id ? null : lb.id;
		}
		onSelectLoadBalancer?.(lb);
	}
</script>

<div class="w-full" bind:this={containerEl}>
	<TopologyHeader
		bind:searchTerm
		{isLight}
		{traffic}
		totalTraffic={ctrl.totalTraffic}
	/>

	{#if ctrl.orderedNetworks.length > 0}
		<div class="sticky top-0 z-30 overflow-hidden -mx-6 px-0 mb-1"
		     style="background: {isLight ? '#f9fafb' : '#111827'}">
			<div class="flex" style="width: max-content; transform: translateX({-scrollLeft}px); will-change: transform">
				<div style="width: {SIDEBAR_W + 24}px; flex-shrink: 0"></div>
				<div class="flex-shrink-0" style="width: {ctrl.canvasContentW}px">
					<div class="flex py-2" style="gap: {LANE_GAP}px; padding-left: {LANE_PAD}px; padding-right: {LANE_PAD}px">
						{#each ctrl.orderedNetworks as net, i (net.id)}
							<div style="width: {LANE_W}px; flex-shrink: 0">
								<NetworkLane
									mode="card"
									{net}
									color={ctrl.netColors.get(net.id) ?? '#3b82f6'}
									{traffic}
									highlighted={highlightedNetId === net.id}
									dimmed={highlightedNetId !== null && highlightedNetId !== net.id}
									laneHeight={ctrl.laneHeight}
									onSelect={() => { highlightedNetId = highlightedNetId === net.id ? null : net.id; }}
									entering={arrival.active}
									enterIndex={i}
								/>
							</div>
						{/each}
					</div>
				</div>
			</div>
		</div>
	{/if}

	<!-- 가로 스크롤 뷰포트: 이 박스 안에서만 horizontal scroll -->
	<div class="overflow-x-auto" bind:this={scrollEl} onscroll={onBodyScroll}>
		<div class="flex items-start relative" style="min-width: max-content">
			<!-- 사이드바: sticky left, sidebarEl 에 바인딩하여 anchor 측정 기준점 확보 -->
			<div
				class="sticky left-0 z-20 flex-shrink-0 flex flex-col gap-3 pr-4"
				style="width: {SIDEBAR_W}px; background: {isLight ? '#f9fafb' : '#111827'}"
				bind:this={sidebarEl}
			>
				<TopologySidebar
					routerRows={ctrl.routerRows}
					filteredLbItems={ctrl.filteredLbItems}
					instanceRows={ctrl.instanceRows}
					{selectedId}
					bind:hoveredId
					netColors={ctrl.netColors}
					instNetBps={ctrl.instNetBps}
					{isLight}
					bind:groupCollapsed
					onSelectRow={selectRow}
					onSelectLb={selectLb}
					onScheduleMeasure={scheduleMeasure}
					onIntentRow={intentRow}
					{onCancelIntent}
					entering={arrival.active}
					sidebarOrder={ctrl.sidebarOrder}
				/>
			</div>

			<!-- 네트워크 레인 (rail 모드: 헤더 카드는 sticky 행에 별도) -->
			<div class="flex-shrink-0" style="width: {ctrl.canvasContentW}px">
				{#if ctrl.orderedNetworks.length === 0}
					<div class="flex items-center justify-center h-40 text-sm"
					     style="color: {isLight ? '#9ca3af' : '#4b5563'}">
						{t('empty.networks')}
					</div>
				{:else}
					<div class="flex" style="gap: {LANE_GAP}px; padding: 0 {LANE_PAD}px">
						{#each ctrl.orderedNetworks as net, i (net.id)}
							<div style="width: {LANE_W}px; flex-shrink: 0">
								<NetworkLane
									mode="rail"
									{net}
									color={ctrl.netColors.get(net.id) ?? '#3b82f6'}
									{traffic}
									highlighted={highlightedNetId === net.id}
									dimmed={highlightedNetId !== null && highlightedNetId !== net.id}
									laneHeight={ctrl.laneHeight}
									entering={arrival.active}
									enterIndex={i}
								/>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<ConnectionOverlay
				width={SIDEBAR_W + ctrl.canvasContentW}
				height={sidebarHeight || 400}
				connections={ctrl.connections}
				laneXMap={ctrl.laneXMap}
				{anchors}
				lbCurves={ctrl.lbCurves}
				selectedKey={selectedId}
				hoveredKey={hoveredId}
				entering={arrival.active}
			/>
		</div>
	</div>
</div>
