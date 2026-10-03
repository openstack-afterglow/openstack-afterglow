<script lang="ts">
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { Alert, Button, Card, Pill } from '$lib/components/ui';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import {
		flavorCreateBlock,
		type FlavorCreateBlock,
		type FlavorOption as FlavorInfo,
		type FlavorQuotaBlocker,
	} from '$lib/types/flavor';

	interface QuotaPair { limit: number; in_use: number; }
	interface FlavorQuotaSummary {
		instances?: QuotaPair;
		cores?: QuotaPair;
		ram?: QuotaPair;       // MB
		gigabytes?: QuotaPair; // GB
	}

	let {
		adminMode = false,
		flavors,
		selectedId,
		selectedName = null,
		onSelect,
		quota,
		refreshing = false,
		refreshError = null,
		backgroundRefreshing = false,
		backgroundRefreshError = null,
		onRefresh,
	}: {
		/** Operator details belong to the administrator surface, not an admin identity in consumer mode. */
		adminMode?: boolean;
		flavors: FlavorInfo[];
		selectedId: string | null;
		selectedName?: string | null;
		onSelect: (id: string, name: string) => void;
		quota?: FlavorQuotaSummary | null;
		/** A locking initial, manual, or submit capacity refresh is in flight. */
		refreshing?: boolean;
		refreshError?: string | null;
		backgroundRefreshing?: boolean;
		backgroundRefreshError?: string | null;
		onRefresh: (mode: 'manual' | 'periodic') => Promise<unknown>;
	} = $props();

	// Mounted only while the flavor step is visible, so the timer stops with the step or panel.
	const ar = createAutoRefresh(async () => { await onRefresh('periodic'); }, {
		storageKey: 'vm-create-flavor-capacity',
		defaultActive: true,
		defaultInterval: 15,
		invokeOnMount: false,
	});

	const selectionLocked = $derived(refreshing || Boolean(refreshError));

	function parseGpuRequest(f: FlavorInfo): { model: string; count: number }[] {
		const alias = f.extra_specs?.['pci_passthrough:alias'] ?? '';
		if (!alias) return [];
		return alias.split(',')
			.map(e => e.trim())
			.filter(e => e.includes(':') && !e.toLowerCase().includes('audio'))
			.map(e => {
				const idx = e.lastIndexOf(':');
				return { model: e.slice(0, idx).trim(), count: parseInt(e.slice(idx + 1)) || 1 };
			});
	}

	// Project GPU quota per alias comes from the target-project eligibility in the fenced flavor list.
	// Host GPU fit is decided per flavor by the same-host capacity snapshot, never by a global aggregate.
	const projectGpuQuota = $derived.by(() => {
		const remaining = new Map<string, number>();
		for (const f of flavors) {
			for (const [alias, value] of Object.entries(f.eligibility?.remaining.gpus ?? {})) remaining.set(alias, value);
		}
		return [...remaining].map(([alias, value]) => ({
			alias,
			remaining: value,
			requested: selectedFlavor?.eligibility?.requirements.gpus[alias] ?? 0,
		}));
	});

	type AvailabilityView = 'selectable' | 'blocked';
	let availabilityView = $state<AvailabilityView>('selectable');
	type FlavorCategory = 'all' | 'general' | 'cpu' | 'memory' | 'gpu';
	let activeCategory = $state<FlavorCategory>('all');
	let searchTerm = $state('');
	let currentPage = $state(1);
	const PAGE_SIZE = 10;

	function hasGpu(flavor: FlavorInfo): boolean {
		return Object.keys(flavor.extra_specs ?? {}).some(
			(k) => k.toLowerCase().includes('gpu') || k.startsWith('pci_passthrough')
		);
	}

	function categorize(f: FlavorInfo): 'general' | 'cpu' | 'memory' | 'gpu' {
		if (f.name.startsWith('gpu.') || hasGpu(f)) return 'gpu';
		if (f.name.startsWith('c1.') || f.name.startsWith('cpu.')) return 'cpu';
		if (f.name.startsWith('r1.') || f.name.startsWith('mem.')) return 'memory';
		return 'general';
	}

	function isSelectable(f: FlavorInfo): boolean {
		return flavorCreateBlock(f) === null;
	}

	const selectableCount = $derived(flavors.filter(f => isSelectable(f)).length);
	const blockedCount = $derived(flavors.filter(f => !isSelectable(f)).length);

	const baseFlavors = $derived(
		availabilityView === 'selectable'
			? flavors.filter(f => isSelectable(f))
			: flavors.filter(f => !isSelectable(f))
	);

	const counts = $derived({
		general: baseFlavors.filter(f => categorize(f) === 'general').length,
		cpu: baseFlavors.filter(f => categorize(f) === 'cpu').length,
		memory: baseFlavors.filter(f => categorize(f) === 'memory').length,
		gpu: baseFlavors.filter(f => categorize(f) === 'gpu').length,
	});

	const filteredFlavors = $derived(
		activeCategory === 'all'
			? baseFlavors
			: baseFlavors.filter(f => categorize(f) === activeCategory)
	);

	const searchedFlavors = $derived(
		searchTerm.trim()
			? filteredFlavors.filter(f =>
				f.name.toLowerCase().includes(searchTerm.trim().toLowerCase()) ||
				String(f.vcpus).includes(searchTerm.trim()) ||
				ramLabel(f.ram).toLowerCase().includes(searchTerm.trim().toLowerCase())
			)
			: filteredFlavors
	);

	const totalPages = $derived(Math.max(1, Math.ceil(searchedFlavors.length / PAGE_SIZE)));

	const paginatedFlavors = $derived(
		searchedFlavors.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
	);

	$effect(() => {
		availabilityView;
		activeCategory;
		searchTerm;
		currentPage = 1;
	});

	function handleFlavorClick(f: FlavorInfo) {
		if (selectionLocked || !isSelectable(f)) return;
		onSelect(f.id, f.name);
	}

	const BLOCK_LABEL: Record<Exclude<FlavorCreateBlock, 'capacity_insufficient'> | 'missing', string> = {
		quota: '프로젝트 쿼터 부족',
		unchecked: '쿼터 또는 호스트 용량 확인 불가',
		missing: '현재 프로젝트 플레이버 목록에 없음',
	};
	/** Same-host capacity was not verified; such a flavor never admits creation. */
	const HOST_CAPACITY_UNCHECKED = '호스트 용량 확인 불가';

	/** The host check covers GPUs only when the flavor requests GPU aliases (quota requirements) or vGPU/pGPU resources. */
	function requestsHostGpu(f: FlavorInfo | undefined): boolean {
		if (Object.keys(f?.eligibility?.requirements.gpus ?? {}).length > 0) return true;
		return Object.keys(f?.extra_specs ?? {}).some(key => /^resources[^:]*:[VP]GPU$/.test(key));
	}

	function hostShortageLabel(f: FlavorInfo | undefined): string {
		return requestsHostGpu(f) ? '한 호스트에 CPU·RAM·GPU 여유 없음' : '한 호스트에 CPU·RAM 여유 없음';
	}

	function blockLabel(block: FlavorCreateBlock | 'missing', f: FlavorInfo | undefined): string {
		return block === 'capacity_insufficient' ? hostShortageLabel(f) : BLOCK_LABEL[block];
	}

	function flavorBlockerLabels(f: FlavorInfo): string[] {
		const labels = (f.eligibility?.blockers ?? []).map(blocker => blockerLabel(blocker, f));
		const block = flavorCreateBlock(f);
		// Missing eligibility or non-selectable eligibility may carry no blocker code.
		if (block && labels.length === 0) labels.push(blockLabel(block, f));
		return labels;
	}

	function hostCapacityText(f: FlavorInfo): string {
		const capacity = f.eligibility?.capacity;
		if (capacity?.status !== 'available' || capacity.remaining_vcpus == null || capacity.remaining_ram_mb == null) return '';
		return `한 호스트 기준 VM당 최대 ${capacity.cpu_resource_class ?? 'CPU'} ${capacity.remaining_vcpus} · RAM ${ramLabel(capacity.remaining_ram_mb)}`;
	}

	const NUMA_UNVERIFIED_NOTE = '호스트 합계 기준 · NUMA 셀·GPU 근접성 미확인 · Nova 최종 확인';

	/** Host totals fit, but the requested single NUMA cell is invisible to Placement and left to Nova. */
	function numaUnverified(f: FlavorInfo): boolean {
		const capacity = f.eligibility?.capacity;
		return capacity?.status === 'available' && capacity.numa_unverified === true;
	}

	function limitText(remaining: number, suffix = ''): string {
		return remaining < 0 ? '무제한' : `${remaining}${suffix}`;
	}

	function blockerLabel(blocker: FlavorQuotaBlocker, f: FlavorInfo): string {
		switch (blocker.code) {
			case 'instances_insufficient':
				return 'VM 쿼터 부족';
			case 'cores_insufficient': {
				const diff = blocker.required != null && blocker.remaining != null ? Math.max(0, blocker.required - blocker.remaining) : null;
				return diff ? `vCPU ${diff}개 부족` : 'vCPU 쿼터 부족';
			}
			case 'ram_insufficient': {
				const diff = blocker.required != null && blocker.remaining != null ? Math.max(0, blocker.required - blocker.remaining) : null;
				return diff ? `RAM ${Math.round(diff / 1024)}GB 부족` : 'RAM 쿼터 부족';
			}
			case 'gpu_insufficient': {
				const diff = blocker.required != null && blocker.remaining != null ? Math.max(0, blocker.required - blocker.remaining) : null;
				const res = blocker.resource ?? 'GPU';
				return diff ? `${res} ${diff}개 부족` : `${res} 쿼터 부족`;
			}
			case 'compute_quota_unavailable':
				return 'Compute 쿼터 확인 불가';
			case 'gpu_quota_unavailable':
				return 'GPU 쿼터 확인 불가';
			case 'host_capacity_insufficient':
				return hostShortageLabel(f);
			case 'host_capacity_unavailable':
				return HOST_CAPACITY_UNCHECKED;
			default:
				return blocker.code;
		}
	}
	function ramLabel(mb: number): string {
		return mb >= 1024 ? `${Math.round(mb / 1024)} GB` : `${mb} MB`;
	}

	function categoryBadge(f: FlavorInfo): { label: string; class: string } | null {
		const cat = categorize(f);
		if (cat === 'gpu') return { label: 'GPU', class: 'bg-purple-900/50 text-purple-300 border-purple-700/50' };
		if (cat === 'cpu') return { label: 'CPU', class: 'bg-sky-900/50 text-sky-300 border-sky-700/50' };
		if (cat === 'memory') return { label: '메모리', class: 'bg-surface-selected/50 text-warm-text border-action-warm/50' };
		return null;
	}

	function gpuSummary(f: FlavorInfo): string {
		const reqs = parseGpuRequest(f);
		if (reqs.length === 0) return '';
		return reqs.map(r => `${r.model} × ${r.count}`).join(', ');
	}

	const selectedFlavor = $derived(flavors.find(f => f.id === selectedId));
	const selectedBlock = $derived<FlavorCreateBlock | 'missing' | null>(
		selectedId ? (selectedFlavor ? flavorCreateBlock(selectedFlavor) : 'missing') : null
	);
	const selectedCapacity = $derived(selectedFlavor?.eligibility?.capacity ?? null);
	const capacityCheckedAt = $derived.by(() => {
		const latest = flavors.reduce((acc, f) => {
			const at = f.eligibility?.capacity?.checked_at ?? '';
			return at > acc ? at : acc;
		}, '');
		const date = latest ? new Date(latest) : null;
		return date && !Number.isNaN(date.getTime()) ? date.toLocaleTimeString('ko-KR') : '';
	});

	function networkBandwidth(f: FlavorInfo): string {
		const bw = f.extra_specs?.['quota:vif_outbound_peak'] ?? f.extra_specs?.['hw:bandwidth'] ?? '';
		if (bw) return `${bw} Gbps`;
		// Estimate from vCPU count
		if (f.vcpus >= 32) return '25 Gbps';
		if (f.vcpus >= 16) return '10 Gbps';
		if (f.vcpus >= 8) return '5 Gbps';
		if (f.vcpus >= 4) return '2.5 Gbps';
		return '1 Gbps';
	}
</script>

<div class="flex flex-col">
<!-- 용량 확인 상태: 기존 목록과 선택을 유지한 채 새로고침/오류를 표시한다. -->
<div class="order-1 mb-3 flex flex-wrap items-center justify-between gap-2">
	<p class="text-xs text-[var(--color-ink-2)]" role="status" aria-live="polite">
		{#if refreshing}
			{adminMode
				? '현재 프로젝트 쿼터와 호스트 용량을 다시 확인하는 중입니다. 확인이 끝날 때까지 선택과 진행을 보류합니다.'
				: '생성 가능 여부를 다시 확인하는 중입니다. 확인이 끝날 때까지 선택과 진행을 보류합니다.'}
		{:else if backgroundRefreshing}
			{adminMode
				? '현재 프로젝트 쿼터와 호스트 용량을 자동으로 확인하는 중입니다. 기존 스냅샷으로 선택과 진행을 계속할 수 있습니다.'
				: '생성 가능 여부를 자동으로 확인하는 중입니다. 선택과 진행을 계속할 수 있습니다.'}
		{:else if capacityCheckedAt}
			{capacityCheckedAt} {adminMode
				? '확인 기준 스냅샷입니다. 예약이 아니며 Nova가 생성 시 다시 확인합니다.'
				: '확인 기준입니다. 생성 전에 다시 확인합니다.'}
		{:else}
			{adminMode
				? '호스트 용량을 확인한 시각이 없습니다. 용량을 확인하지 못한 플레이버는 생성할 수 없습니다.'
				: '생성 가능 여부를 확인하지 못했습니다. 확인되지 않은 플레이버는 생성할 수 없습니다.'}
		{/if}
	</p>
	<AutoRefreshControl
		bind:active={ar.active}
		bind:intervalSeconds={ar.intervalSeconds}
		intervalOptions={ar.intervalOptions}
		refreshing={refreshing || backgroundRefreshing}
		onManualRefresh={() => { void onRefresh('manual'); }}
	/>
</div>

{#if backgroundRefreshError}
	<p class="order-1 mb-3 text-xs text-[var(--color-state-warning-text)]" role="status" aria-live="polite">최근 자동 확인 실패 · 생성 직전에 다시 확인합니다</p>
{/if}

{#if refreshError}
	<Alert tone="danger" title="플레이버 용량을 다시 확인하지 못했습니다" class="order-1 mb-3">
		{refreshError}. 확인에 성공할 때까지 플레이버를 선택하거나 다음 단계로 진행할 수 없습니다.
		{#snippet actions()}
			<Button variant="danger-outline" size="sm" disabled={refreshing} onclick={() => { void onRefresh('manual'); }}>다시 확인</Button>
		{/snippet}
	</Alert>
{/if}

{#if selectedBlock}
	<Alert tone="warning" title="선택한 플레이버로 지금 생성할 수 없습니다" class="order-1 mb-3">
		{selectedFlavor?.name ?? selectedName ?? '선택한 플레이버'}: {blockLabel(selectedBlock, selectedFlavor)}.
		다른 플레이버를 직접 선택하세요. 선택은 자동으로 바뀌지 않습니다.
	</Alert>
{/if}

<div class="order-2 mb-3 flex flex-wrap items-center justify-between gap-2">
	<div class="flex items-center gap-1.5">
		<button
			type="button"
			onclick={() => { availabilityView = 'selectable'; }}
			class="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors {availabilityView === 'selectable'
				? 'bg-[var(--color-accent)] text-[var(--color-surface-canvas)] shadow-sm'
				: 'bg-[var(--color-surface-sunken)] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-raised)]'}"
		>
			생성 가능 ({selectableCount})
		</button>
		<button
			type="button"
			onclick={() => { availabilityView = 'blocked'; }}
			class="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors {availabilityView === 'blocked'
				? 'bg-[var(--color-surface-sunken)] text-[var(--color-state-danger-text)] border border-[var(--color-state-danger)]/50'
				: 'bg-[var(--color-surface-sunken)] text-[var(--color-ink-2)] hover:bg-[var(--color-surface-raised)]'}"
		>
			생성 불가 ({blockedCount})
		</button>
	</div>
	<p class="text-xs text-[var(--color-ink-2)]">
		{#if adminMode}
			{availabilityView === 'selectable'
				? '프로젝트 쿼터와 한 컴퓨트 호스트의 여유(GPU 플레이버는 GPU 포함)를 확인해 지금 선택할 수 있는 플레이버입니다.'
				: '프로젝트 쿼터 부족, 한 호스트의 여유 부족, 또는 확인 불가로 지금 생성할 수 없는 플레이버입니다.'}
		{:else}
			{availabilityView === 'selectable'
				? '프로젝트 쿼터와 현재 자원 여유를 확인해 지금 선택할 수 있는 플레이버입니다.'
				: '프로젝트 쿼터 부족, 자원 여유 부족, 또는 확인 불가로 지금 생성할 수 없는 플레이버입니다.'}
		{/if}
	</p>
</div>

<!-- 카테고리 필터 탭 -->
<div class="order-3 mb-4 flex flex-wrap gap-2">
	{#each ([
		{ key: 'all', label: `전체 (${flavors.length})` },
		{ key: 'general', label: `범용 (${counts.general})` },
		{ key: 'cpu', label: `CPU (${counts.cpu})` },
		{ key: 'memory', label: `메모리 (${counts.memory})` },
		{ key: 'gpu', label: `GPU (${counts.gpu})` },
	] as const) as tab}
		<button
			onclick={() => { activeCategory = tab.key; }}
			class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors {activeCategory === tab.key
				? 'bg-action-warm text-action-on-warm'
				: 'bg-surface-sunken text-ink-2 hover:bg-surface-selected'}"
		>{tab.label}</button>
	{/each}
</div>

<!-- 통합 검색 -->
<div class="order-4 relative mb-4">
	<span class="absolute left-3 top-1/2 -translate-y-1/2 text-ink-2 pointer-events-none">
		<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"/>
		</svg>
	</span>
	<input
		type="search"
		placeholder="플레이버 이름, vCPU, RAM으로 검색..."
		bind:value={searchTerm}
		class="w-full bg-surface-base border border-line text-ink-1 rounded-lg pl-9 pr-3 py-2 text-sm outline-none focus:border-line-2 placeholder-ink-3"
	/>
</div>

<!-- 프로젝트 quota delta 미터 -->
{#if quota}
	{@const reqVm = selectedFlavor ? 1 : 0}
	{@const reqCpu = selectedFlavor?.vcpus ?? 0}
	{@const reqRamMb = selectedFlavor?.ram ?? 0}
	{@const reqDiskGb = 0}
	{@const limVm = quota.instances?.limit ?? -1}
	{@const limCpu = quota.cores?.limit ?? -1}
	{@const limRamMb = quota.ram?.limit ?? -1}
	{@const limDiskGb = quota.gigabytes?.limit ?? -1}
	{@const curVm = quota.instances?.in_use ?? 0}
	{@const curCpu = quota.cores?.in_use ?? 0}
	{@const curRamMb = quota.ram?.in_use ?? 0}
	{@const curDiskGb = quota.gigabytes?.in_use ?? 0}
	{@const critVm = limVm >= 0 && curVm + reqVm > limVm}
	{@const critCpu = limCpu >= 0 && curCpu + reqCpu > limCpu}
	{@const critRam = limRamMb >= 0 && curRamMb + reqRamMb > limRamMb}
	{@const critDisk = limDiskGb >= 0 && curDiskGb + reqDiskGb > limDiskGb}
	<div class="order-1 mb-4 overflow-hidden rounded-xl border border-line bg-surface-base/70 md:mb-5">
		<div class="flex items-center justify-between px-3 py-2 border-b border-line">
			<span class="text-xs text-ink-2 font-medium">
				프로젝트 잔여 쿼터
				{#if selectedFlavor}<span class="text-warm-text ml-1">— 선택 flavor 반영</span>{/if}
			</span>
			<div class="hidden items-center gap-3 text-xs text-ink-2 @md/panel:flex">
				<span class="flex items-center gap-1"><i class="inline-block w-2 h-2 rounded-full bg-surface-selected"></i>현재 사용</span>
				<span class="flex items-center gap-1"><i class="inline-block w-2 h-2 rounded-full bg-action-warm"></i>이번 VM 추가</span>
			</div>
		</div>
		<div class="grid grid-cols-2 gap-px bg-surface-sunken @2xl/panel:grid-cols-4">
			<!-- VM cell -->
			<div class="flex flex-col gap-1.5 bg-surface-base px-3 py-2">
				<span class="text-xs uppercase tracking-wider text-ink-2 font-mono font-semibold">VM</span>
				<div class="flex items-baseline gap-1 font-mono">
					<span class="text-sm text-ink-2">{curVm}</span>
					{#if reqVm > 0}
						<span class="text-ink-2 text-xs">→</span>
						<span class="text-sm font-bold {critVm ? 'text-red-400' : 'text-warm-text'}">{curVm + reqVm}</span>
					{/if}
					{#if limVm >= 0}<span class="text-ink-2 text-xs">/ {limVm}</span>{/if}
				</div>
				{#if limVm >= 0}
					{@const curPct = Math.min(100, (curVm / limVm) * 100)}
					{@const deltaPct = Math.min(100 - curPct, (reqVm / limVm) * 100)}
					<div class="relative h-[5px] rounded-full bg-surface-sunken overflow-hidden">
						<div class="absolute left-0 top-0 h-full bg-surface-selected rounded-full" style="width:{curPct}%"></div>
						<div class="absolute top-0 h-full rounded-r-full {critVm ? 'bg-red-500' : 'bg-action-warm'}" style="left:{curPct}%; width:{deltaPct}%"></div>
					</div>
				{/if}
			</div>
			<!-- vCPU cell -->
			<div class="flex flex-col gap-1.5 bg-surface-base px-3 py-2">
				<span class="text-xs uppercase tracking-wider text-ink-2 font-mono font-semibold">vCPU</span>
				<div class="flex items-baseline gap-1 font-mono">
					<span class="text-sm text-ink-2">{curCpu}</span>
					{#if reqCpu > 0}
						<span class="text-ink-2 text-xs">→</span>
						<span class="text-sm font-bold {critCpu ? 'text-red-400' : 'text-warm-text'}">{curCpu + reqCpu}</span>
					{/if}
					{#if limCpu >= 0}<span class="text-ink-2 text-xs">/ {limCpu}</span>{/if}
				</div>
				{#if limCpu >= 0}
					{@const curPct = Math.min(100, (curCpu / limCpu) * 100)}
					{@const deltaPct = Math.min(100 - curPct, (reqCpu / limCpu) * 100)}
					<div class="relative h-[5px] rounded-full bg-surface-sunken overflow-hidden">
						<div class="absolute left-0 top-0 h-full bg-surface-selected rounded-full" style="width:{curPct}%"></div>
						<div class="absolute top-0 h-full rounded-r-full {critCpu ? 'bg-red-500' : 'bg-action-warm'}" style="left:{curPct}%; width:{deltaPct}%"></div>
					</div>
				{/if}
			</div>
			<!-- RAM cell -->
			<div class="flex flex-col gap-1.5 bg-surface-base px-3 py-2">
				<span class="text-xs uppercase tracking-wider text-ink-2 font-mono font-semibold">RAM</span>
				<div class="flex items-baseline gap-1 font-mono">
					<span class="text-sm text-ink-2">{Math.round(curRamMb / 1024)}GB</span>
					{#if reqRamMb > 0}
						<span class="text-ink-2 text-xs">→</span>
						<span class="text-sm font-bold {critRam ? 'text-red-400' : 'text-warm-text'}">{Math.round((curRamMb + reqRamMb) / 1024)}GB</span>
					{/if}
					{#if limRamMb >= 0}<span class="text-ink-2 text-xs">/ {Math.round(limRamMb / 1024)}GB</span>{/if}
				</div>
				{#if limRamMb >= 0}
					{@const curPct = Math.min(100, (curRamMb / limRamMb) * 100)}
					{@const deltaPct = Math.min(100 - curPct, (reqRamMb / limRamMb) * 100)}
					<div class="relative h-[5px] rounded-full bg-surface-sunken overflow-hidden">
						<div class="absolute left-0 top-0 h-full bg-surface-selected rounded-full" style="width:{curPct}%"></div>
						<div class="absolute top-0 h-full rounded-r-full {critRam ? 'bg-red-500' : 'bg-action-warm'}" style="left:{curPct}%; width:{deltaPct}%"></div>
					</div>
				{/if}
			</div>
			<!-- DISK cell -->
			<div class="flex flex-col gap-1.5 bg-surface-base px-3 py-2">
				<span class="text-xs uppercase tracking-wider text-ink-2 font-mono font-semibold">DISK</span>
				{#if limDiskGb < 0}
					<div class="flex items-baseline gap-1 font-mono">
						<span class="text-sm text-ink-2">{curDiskGb}GB</span>
						<span class="text-ink-2 text-xs">/ ∞</span>
					</div>
					<div class="relative h-[5px] rounded-full bg-surface-sunken overflow-hidden">
						<div class="absolute left-0 top-0 h-full bg-surface-selected rounded-full" style="width:0%"></div>
					</div>
				{:else}
					<div class="flex items-baseline gap-1 font-mono">
						<span class="text-sm text-ink-2">{curDiskGb}GB</span>
						{#if reqDiskGb > 0}
							<span class="text-ink-2 text-xs">→</span>
							<span class="text-sm font-bold {critDisk ? 'text-red-400' : 'text-warm-text'}">{curDiskGb + reqDiskGb}GB</span>
						{/if}
						<span class="text-ink-2 text-xs">/ {limDiskGb}GB</span>
					</div>
					{@const curPct = Math.min(100, (curDiskGb / limDiskGb) * 100)}
					{@const deltaPct = Math.min(100 - curPct, (reqDiskGb / limDiskGb) * 100)}
					<div class="relative h-[5px] rounded-full bg-surface-sunken overflow-hidden">
						<div class="absolute left-0 top-0 h-full bg-surface-selected rounded-full" style="width:{curPct}%"></div>
						<div class="absolute top-0 h-full rounded-r-full {critDisk ? 'bg-red-500' : 'bg-action-warm'}" style="left:{curPct}%; width:{deltaPct}%"></div>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<!-- 선택 플레이버의 프로젝트 쿼터와 관리자 전용 호스트 용량 스냅샷 -->
{#if selectedFlavor?.eligibility}
	{@const eligibility = selectedFlavor.eligibility}
	<Card surface="base" padding="sm" class="order-1 mb-4">
		<p class="mb-2 text-xs font-medium text-[var(--color-ink-2)]">선택한 플레이버 <span class="font-mono text-[var(--color-ink-0)]">{selectedFlavor.name}</span> 생성 조건</p>
		<dl class="grid grid-cols-1 gap-3 text-xs {adminMode ? '@md/panel:grid-cols-2' : ''}">
			<div>
				<dt class="mb-1 text-[var(--color-ink-2)]">현재 대상 프로젝트 잔여 쿼터</dt>
				<dd class="font-mono text-[var(--color-ink-1)]">
					VM {limitText(eligibility.remaining.instances)} · vCPU {limitText(eligibility.remaining.cores)} · RAM {eligibility.remaining.ram_mb < 0 ? '무제한' : ramLabel(eligibility.remaining.ram_mb)}
					{#each Object.entries(eligibility.requirements.gpus) as [alias, required]}
						<span class="block">GPU {alias}: 필요 {required} / 잔여 {limitText(eligibility.remaining.gpus[alias] ?? 0)}</span>
					{/each}
				</dd>
			</div>
			{#if adminMode}
				<div>
					<dt class="mb-1 text-[var(--color-ink-2)]">한 호스트 기준 VM당 최대 (스냅샷)</dt>
					<dd class="font-mono text-[var(--color-ink-1)]">
						{#if selectedCapacity?.status === 'available' && selectedCapacity.remaining_vcpus != null && selectedCapacity.remaining_ram_mb != null}
							{selectedCapacity.cpu_resource_class ?? 'CPU'} {selectedCapacity.remaining_vcpus} · RAM {ramLabel(selectedCapacity.remaining_ram_mb)}
							<span class="block text-[var(--color-ink-2)]">조건을 만족하는 호스트 {selectedCapacity.candidate_hosts}대 중 한 호스트에서 함께 확인한 값</span>
						{:else if selectedCapacity?.status === 'available'}
							여유 있음
						{:else if selectedCapacity?.status === 'insufficient'}
							{hostShortageLabel(selectedFlavor)}
						{:else}
							{HOST_CAPACITY_UNCHECKED}
						{/if}
						{#if selectedCapacity?.status === 'available' && selectedCapacity.numa_unverified}
							<span class="block text-[var(--color-state-warning-text)]">호스트 합계 기준이며 단일 NUMA 셀 여유와 GPU의 NUMA 근접성은 확인하지 않았습니다. Nova가 생성 시 최종 확인하며 No valid host로 거부될 수 있습니다.</span>
						{/if}
					</dd>
				</div>
			{/if}
		</dl>
		{#if adminMode}
			<p class="mt-2 text-xs text-[var(--color-ink-2)]">용량은 예약이 아닌 확인 시점 값이며, Nova가 생성 요청 시 다시 확인하므로 생성이 보장되지는 않습니다.</p>
		{/if}
	</Card>
{/if}

<!-- 프로젝트 GPU 쿼터: 호스트 GPU 여유가 아니라 현재 대상 프로젝트의 GPU 쿼터 잔여량이다. -->
{#if projectGpuQuota.length > 0 && (activeCategory === 'all' || activeCategory === 'gpu')}
	<div class="order-5 mb-4">
		<p class="mb-2 text-xs text-[var(--color-ink-2)]">{adminMode ? '프로젝트 GPU 쿼터 잔여 · 호스트 GPU 여유는 플레이버별 용량 확인으로 판단합니다' : '프로젝트 GPU 쿼터 잔여'}</p>
		<div class="flex flex-wrap gap-2">
			{#each projectGpuQuota as gpuQuota}
				<Pill tone={gpuQuota.remaining >= 0 && gpuQuota.requested > gpuQuota.remaining ? 'danger' : gpuQuota.remaining === 0 ? 'warning' : 'neutral'}>
					<span class="font-mono">{gpuQuota.alias} {limitText(gpuQuota.remaining)}{#if gpuQuota.requested > 0} · 선택 {gpuQuota.requested}{/if}</span>
				</Pill>
			{/each}
		</div>
	</div>
{/if}

<!-- 모바일 플레이버 카드: 가로 스크롤 없이 이름과 핵심 스펙을 함께 표시한다. -->
<div class="order-6 space-y-2 @2xl/panel:hidden">
	{#each paginatedFlavors as flavor}
		{@const badge = categoryBadge(flavor)}
		{@const gpu = gpuSummary(flavor)}
		{@const selectable = isSelectable(flavor)}
		{@const blockers = flavorBlockerLabels(flavor)}
		{@const hostCapacity = adminMode ? hostCapacityText(flavor) : ''}
		{@const cellUnverified = adminMode && numaUnverified(flavor)}
		<button
			onclick={() => handleFlavorClick(flavor)}
			aria-label={`${flavor.name} 플레이버 선택`}
			disabled={!selectable || selectionLocked}
			class="w-full rounded-xl border p-3 text-left transition-colors {selectedId === flavor.id
				? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10 ring-1 ring-[var(--color-accent)]/30'
				: selectable
					? 'border-[var(--color-line)] bg-[var(--color-surface-raised)] hover:border-[var(--color-line-2)]'
					: 'border-[var(--color-line)] bg-[var(--color-surface-sunken)]/60 opacity-60 cursor-not-allowed'}"
		>
			<div class="flex items-start gap-3">
				<div class="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-sunken)]">
					<svg class="h-4 w-4 text-[var(--color-ink-2)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"/>
					</svg>
				</div>
				<div class="min-w-0 flex-1">
					<div class="break-words font-mono text-sm font-semibold text-[var(--color-ink-0)]">{flavor.name}</div>
					<div class="mt-1 flex flex-wrap gap-1.5">
						{#if badge}
							<span class="rounded border px-1.5 py-0.5 text-xs {badge.class}">{badge.label}</span>
						{/if}
						{#if flavor.is_public}
							<span class="rounded border border-[var(--color-line)] bg-[var(--color-surface-sunken)] px-1.5 py-0.5 text-xs text-[var(--color-ink-2)]">공용</span>
						{/if}
						<span class="text-xs text-[var(--color-ink-3)]">{networkBandwidth(flavor)}</span>
					</div>
				</div>
			</div>
			<dl class="mt-3 grid grid-cols-3 gap-2 border-t border-[var(--color-line)] pt-2.5 font-mono">
				<div>
					<dt class="text-xs uppercase tracking-wide text-[var(--color-ink-3)]">vCPU</dt>
					<dd class="mt-0.5 text-sm text-[var(--color-ink-1)]">{flavor.vcpus}</dd>
				</div>
				<div>
					<dt class="text-xs uppercase tracking-wide text-[var(--color-ink-3)]">RAM</dt>
					<dd class="mt-0.5 text-sm text-[var(--color-ink-1)]">{ramLabel(flavor.ram)}</dd>
				</div>
				<div>
					<dt class="text-xs uppercase tracking-wide text-[var(--color-ink-3)]">Disk</dt>
					<dd class="mt-0.5 text-sm text-[var(--color-ink-1)]">{flavor.disk} GB</dd>
				</div>
			</dl>
			{#if gpu}
				<div class="mt-2 text-xs text-[var(--color-accent-2)]">{gpu}</div>
			{/if}
			{#if hostCapacity}
				<div class="mt-1 text-xs text-[var(--color-ink-2)]">{hostCapacity}</div>
			{/if}
			{#if cellUnverified}
				<div class="mt-0.5 text-xs text-[var(--color-state-warning-text)]">{NUMA_UNVERIFIED_NOTE}</div>
			{/if}
			{#if blockers.length > 0}
				<div class="mt-2 flex flex-wrap gap-1">
					{#each blockers as label}
						<span class="rounded border border-[var(--color-state-danger)]/40 bg-[var(--color-surface-sunken)] px-1.5 py-0.5 text-xs text-[var(--color-state-danger-text)] font-medium">
							{label}
						</span>
					{/each}
				</div>
			{/if}
		</button>
	{/each}
	{#if searchedFlavors.length === 0}
		<div class="py-8 text-center text-sm text-[var(--color-ink-3)]">조건에 맞는 플레이버가 없습니다</div>
	{/if}
</div>

<!-- 데스크톱에서는 스펙 비교를 위한 표를 유지한다. -->
<div class="order-6 hidden overflow-hidden rounded-xl border border-line bg-[#0B1220] @2xl/panel:block">
	<div class="grid grid-cols-[2fr_80px_90px_100px_100px] border-b border-line px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-ink-2">
		<div>이름</div>
		<div class="text-center">VCPU</div>
		<div class="text-center">RAM</div>
		<div class="text-center">디스크(SSD)</div>
		<div class="text-center">네트워크</div>
	</div>

	{#each paginatedFlavors as flavor}
		{@const badge = categoryBadge(flavor)}
		{@const gpu = gpuSummary(flavor)}
		{@const selectable = isSelectable(flavor)}
		{@const blockers = flavorBlockerLabels(flavor)}
		{@const hostCapacity = adminMode ? hostCapacityText(flavor) : ''}
		{@const cellUnverified = adminMode && numaUnverified(flavor)}
		<button
			onclick={() => handleFlavorClick(flavor)}
			disabled={!selectable || selectionLocked}
			class="grid w-full grid-cols-[2fr_80px_90px_100px_100px] border-b border-line/60 px-4 py-3 text-sm transition-all
				{selectedId === flavor.id ? 'border-l-2 border-l-blue-500 bg-surface-selected/20' : ''}
				{selectable ? 'hover:bg-surface-sunken/40' : 'opacity-60 cursor-not-allowed bg-[var(--color-surface-sunken)]/30'}"
		>
			<div class="flex min-w-0 items-center gap-3">
				<div class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-line-2 bg-surface-sunken">
					<svg class="h-4 w-4 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 002 2v10a2 2 0 00-2 2zM9 9h6v6H9V9z"/>
					</svg>
				</div>
				<div class="min-w-0">
					<div class="flex items-center gap-2">
						<span class="truncate font-medium text-ink-0">{flavor.name}</span>
						{#if badge}
							<span class="rounded border px-1.5 py-0.5 text-xs {badge.class}">{badge.label}</span>
						{/if}
						{#if flavor.is_public}
							<span class="rounded border border-line-2 bg-surface-sunken px-1.5 py-0.5 text-xs text-ink-2">공용</span>
						{/if}
					</div>
					{#if gpu}
						<div class="mt-0.5 text-xs text-purple-400">{gpu}</div>
					{/if}
					{#if hostCapacity}
						<div class="mt-0.5 text-xs text-ink-2">{hostCapacity}</div>
					{/if}
					{#if cellUnverified}
						<div class="mt-0.5 text-xs text-[var(--color-state-warning-text)]">{NUMA_UNVERIFIED_NOTE}</div>
					{/if}
					{#if blockers.length > 0}
						<div class="mt-1 flex flex-wrap gap-1">
							{#each blockers as label}
								<span class="rounded border border-[var(--color-state-danger)]/40 bg-[var(--color-surface-sunken)] px-1.5 py-0.5 text-xs text-[var(--color-state-danger-text)] font-medium">
									{label}
								</span>
							{/each}
						</div>
					{/if}
				</div>
			</div>
			<div class="self-center text-center text-ink-2">{flavor.vcpus}</div>
			<div class="self-center text-center text-ink-2">{ramLabel(flavor.ram)}</div>
			<div class="self-center text-center text-ink-2">{flavor.disk} GB</div>
			<div class="self-center text-center text-xs text-ink-2">{networkBandwidth(flavor)}</div>
		</button>
	{/each}

	{#if searchedFlavors.length === 0}
		<div class="py-8 text-center text-sm text-ink-2">조건에 맞는 플레이버가 없습니다</div>
	{/if}
</div>

<!-- 페이지네이션 -->
{#if totalPages > 1}
<div class="order-7 mt-3 flex items-center justify-between text-xs text-ink-2">
	<span>{searchedFlavors.length}개 중 {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, searchedFlavors.length)}</span>
	<div class="flex gap-1">
		<button
			onclick={() => currentPage = Math.max(1, currentPage - 1)}
			disabled={currentPage === 1}
			class="px-2 py-1 rounded bg-surface-sunken text-ink-2 hover:bg-surface-selected disabled:opacity-30 disabled:cursor-not-allowed"
		>이전</button>
		{#each Array.from({ length: totalPages }, (_, i) => i + 1) as p}
			<button
				onclick={() => currentPage = p}
				class="px-2 py-1 rounded {p === currentPage ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken text-ink-2 hover:bg-surface-selected'}"
			>{p}</button>
		{/each}
		<button
			onclick={() => currentPage = Math.min(totalPages, currentPage + 1)}
			disabled={currentPage === totalPages}
			class="px-2 py-1 rounded bg-surface-sunken text-ink-2 hover:bg-surface-selected disabled:opacity-30 disabled:cursor-not-allowed"
		>다음</button>
	</div>
</div>
{/if}
</div>
