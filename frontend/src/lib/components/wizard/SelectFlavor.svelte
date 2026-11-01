<script lang="ts">
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button, Card, CompactResourceCard, Pagination, ResponsiveTable, TableShell } from '$lib/components/ui';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import {
		flavorCreateBlock,
		type FlavorCreateBlock,
		type FlavorOption as FlavorInfo,
	} from '$lib/types/flavor';
	import { t } from '$lib/i18n/ns/vm-wizard';
	import { t as tp } from '$lib/i18n/ns/compute-pools';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { flavorGpuRequests } from '$lib/utils/flavorGpu';
	import { consumerFlavorLabel } from '$lib/utils/flavorDisplay';

	interface QuotaPair { limit: number; in_use: number; }
	interface FlavorQuotaSummary {
		instances?: QuotaPair;
		cores?: QuotaPair | null;
		ram?: QuotaPair | null; // MB
		gigabytes?: QuotaPair; // GB
	}

	function quotaPercent(value: number, limit: number): number {
		if (!Number.isFinite(value) || !Number.isFinite(limit) || limit < 0) return 0;
		if (limit === 0) return value > 0 ? 100 : 0;
		return Math.max(0, Math.min(100, (value / limit) * 100));
	}

	let {
		adminMode = false,
		catalogVisible = true,
		refreshVisible = true,
		previewFlavor = null,
		flavors,
		selectedId,
		selectedName = null,
		onSelect,
		quota,
		bootVolumeSizeGb,
		initialLoading = false,
		refreshing = false,
		refreshError = null,
		backgroundRefreshing = false,
		backgroundRefreshError = null,
		onRefresh,
	}: {
		/** Operator details belong to the administrator surface, not an admin identity in consumer mode. */
		adminMode?: boolean;
		catalogVisible?: boolean;
		refreshVisible?: boolean;
		previewFlavor?: FlavorInfo | null;
		flavors: FlavorInfo[];
		selectedId: string | null;
		selectedName?: string | null;
		onSelect: (id: string, name: string) => void;
		quota?: FlavorQuotaSummary | null;
		/** New root volume size; zero means booting from an existing volume. */
		bootVolumeSizeGb?: number;
		initialLoading?: boolean;
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
		enabled: () => refreshVisible,
	});

	const selectionLocked = $derived(initialLoading || refreshing || Boolean(refreshError));


	type FlavorCategory = 'all' | 'general' | 'cpu' | 'memory' | 'gpu';
	let activeCategory = $state<FlavorCategory>('all');
	let searchTerm = $state('');
	let activeGpuType = $state<string | null>(null);
	let currentPage = $state(1);
	const PAGE_SIZE = 10;

	function hasGpu(flavor: FlavorInfo): boolean {
		if (flavor.is_gpu === true || (flavor.gpu_count ?? 0) > 0 || (flavor.gpu_primary_aliases?.length ?? 0) > 0) return true;
		return Object.keys(flavor.extra_specs ?? {}).some(
			(k) => k.toLowerCase().includes('gpu') || k.startsWith('pci_passthrough')
		);
	}

	function categorize(f: FlavorInfo): 'general' | 'cpu' | 'memory' | 'gpu' {
		if (f.name.startsWith('gpu.') || hasGpu(f)) return 'gpu';
		if (Number.isFinite(f.vcpus) && f.vcpus > 0 && Number.isFinite(f.ram) && f.ram > 0 && f.ram / f.vcpus >= 4096) return 'memory';
		if (f.name.startsWith('c1.') || f.name.startsWith('cpu.') || f.name.startsWith('mem.')) return 'cpu';
		if (f.display_name?.startsWith('cpu.') || f.display_name?.startsWith('mem.')) return 'cpu';
		return 'general';
	}

	function isSelectable(f: FlavorInfo): boolean {
		return flavorCreateBlock(f) === null;
	}

	const creatableFlavors = $derived(flavors.filter(isSelectable));
	const gpuTypes = $derived([...new Set(creatableFlavors.flatMap(f => (flavorGpuRequests(f) ?? []).map(request => request.model)))].sort((a, b) => a.localeCompare(b, intlLocale())));
	// Keep an applied filter recognizable when refresh removes its last creatable flavor.
	const gpuTypeOptions = $derived(activeGpuType !== null && !gpuTypes.includes(activeGpuType) ? [...gpuTypes, activeGpuType] : gpuTypes);

	const uncheckedFlavors = $derived(flavors.filter(f => flavorCreateBlock(f) === 'unchecked'));
	const defaultZoneUnavailable = $derived(flavors.some(f => f.eligibility?.capacity?.reason === 'default_compute_zone_unavailable'));
	const hasFilters = $derived(activeCategory !== 'all' || activeGpuType !== null || Boolean(searchTerm.trim()));
	function resetFilters() {
		activeCategory = 'all';
		activeGpuType = null;
		searchTerm = '';
		currentPage = 1;
	}

	const counts = $derived({
		general: creatableFlavors.filter(f => categorize(f) === 'general').length,
		cpu: creatableFlavors.filter(f => categorize(f) === 'cpu').length,
		memory: creatableFlavors.filter(f => categorize(f) === 'memory').length,
		gpu: creatableFlavors.filter(f => categorize(f) === 'gpu').length,
	});

	const filteredFlavors = $derived(
		creatableFlavors.filter(f =>
			(activeCategory === 'all' || categorize(f) === activeCategory) &&
			(activeGpuType === null || (flavorGpuRequests(f) ?? []).some(request => request.model === activeGpuType))
		)
	);

	const searchedFlavors = $derived(
		searchTerm.trim()
			? filteredFlavors.filter(f =>
				f.name.toLowerCase().includes(searchTerm.trim().toLowerCase()) ||
				(f.display_name?.toLowerCase().includes(searchTerm.trim().toLowerCase()) ?? false) ||
				consumerFlavorLabel(f).toLowerCase().includes(searchTerm.trim().toLowerCase()) ||
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
		activeCategory;
		searchTerm;
		activeGpuType;
		currentPage = 1;
	});

	$effect(() => {
		if (currentPage > totalPages) currentPage = totalPages;
	});

	function handleFlavorClick(f: FlavorInfo) {
		if (selectionLocked || !isSelectable(f)) return;
		onSelect(f.id, f.name);
	}

	function selectionLabel(f: FlavorInfo): string {
		return consumerFlavorLabel(f);
	}

	function hostCapacityText(f: FlavorInfo): string {
		const capacity = f.eligibility?.capacity;
		if (capacity?.status !== 'available' || capacity.remaining_vcpus == null || capacity.remaining_ram_mb == null) return '';
		return t('flavor.host.capacityPerVm', {
			cpuClass: capacity.cpu_resource_class ?? 'CPU',
			vcpus: capacity.remaining_vcpus,
			ram: ramLabel(capacity.remaining_ram_mb),
		});
	}

	/** Host totals fit, but the requested single NUMA cell is invisible to Placement and left to Nova. */
	function numaUnverified(f: FlavorInfo): boolean {
		const capacity = f.eligibility?.capacity;
		return capacity?.status === 'available' && capacity.numa_unverified === true;
	}

	function ramLabel(mb: number): string {
		return mb >= 1024 ? `${mb / 1024} GB` : `${mb} MB`;
	}

	function categoryBadge(f: FlavorInfo): { label: string; class: string } | null {
		const cat = categorize(f);
		if (cat === 'gpu') return { label: 'GPU', class: 'bg-surface-sunken text-ink-1 border-line' };
		if (cat === 'cpu') return { label: 'CPU', class: 'bg-surface-sunken text-ink-1 border-line' };
		if (cat === 'memory') return { label: t('flavor.category.memoryBadge'), class: 'bg-surface-sunken text-ink-1 border-line' };
		return null;
	}

	function gpuSummary(f: FlavorInfo): string {
		const reqs = flavorGpuRequests(f);
		if (reqs == null) return tp('unknown');
		return reqs.map(r => `${r.model} × ${r.count}`).join(', ');
	}

	const selectedFlavor = $derived(previewFlavor ?? flavors.find(f => f.id === selectedId));
	const selectedNativeFlavor = $derived(flavors.find(f => f.id === selectedId));
	const selectedBlock = $derived<FlavorCreateBlock | 'missing' | null>(
		selectedId ? (selectedNativeFlavor ? flavorCreateBlock(selectedNativeFlavor) : 'missing') : null
	);
	const selectedCapacity = $derived(selectedFlavor?.eligibility?.capacity ?? null);
	const capacityCheckedAt = $derived.by(() => {
		const latest = flavors.reduce((acc, f) => {
			const at = f.eligibility?.capacity?.checked_at ?? '';
			return at > acc ? at : acc;
		}, '');
		const date = latest ? new Date(latest) : null;
		return date && !Number.isNaN(date.getTime()) ? date.toLocaleTimeString(intlLocale()) : '';
	});

	function networkBandwidth(f: FlavorInfo): string {
		// Nova passes quota:vif_* to libvirt, whose peak unit is KiB/s.
		const peak = f.extra_specs?.['quota:vif_outbound_peak'];
		if (peak) return `${peak} KiB/s`;
		const bw = f.extra_specs?.['hw:bandwidth'];
		if (bw) return `${bw} Gbps`;
		return tp('unknown');
	}
</script>

<div class="flex min-w-0 max-w-full flex-col">
{#if initialLoading}
	<LoadingState variant="surface" label={t('flavor.loading')} />
{:else}
<!-- 용량 확인 상태: 기존 목록과 선택을 유지한 채 새로고침/오류를 표시한다. -->
{#if refreshVisible}
<div class="order-1 mb-3 flex flex-wrap items-center justify-between gap-2">
	<p class="text-xs text-[var(--color-ink-2)]" role="status" aria-live="polite">
		{#if refreshing}
			<LoadingState variant="inline" label={t(adminMode ? 'flavor.refresh.checkingAdmin' : 'flavor.refresh.checking')} />
		{:else if backgroundRefreshing}
			<LoadingState variant="inline" label={t(adminMode ? 'flavor.refresh.backgroundAdmin' : 'flavor.refresh.background')} />
		{:else if capacityCheckedAt}
			{t(adminMode ? 'flavor.refresh.checkedAtAdmin' : 'flavor.refresh.checkedAt', { time: capacityCheckedAt })}
		{:else}
			{t(adminMode ? 'flavor.refresh.neverCheckedAdmin' : 'flavor.refresh.neverChecked')}
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
{/if}

{#if backgroundRefreshError}
	<p class="order-1 mb-3 text-xs text-[var(--color-state-warning-text)]" role="status" aria-live="polite">{t('flavor.refresh.backgroundFailed')}</p>
{/if}

{#if refreshError}
	<Alert tone="danger" title={t('flavor.refresh.errorTitle')} class="order-1 mb-3">
		<p>{t('flavor.refresh.errorBody', { error: refreshError })}</p>
		<details class="mt-2 text-sm"><summary class="cursor-pointer">{t('flavor.failure.details')}</summary><p class="mt-2 break-words">{refreshError}</p></details>
		{#snippet actions()}
			<Button variant="danger-outline" size="sm" disabled={refreshing} onclick={() => { void onRefresh('manual'); }}>{t('flavor.refresh.retry')}</Button>
		{/snippet}
	</Alert>
{/if}

{#if selectedBlock}
	<Alert tone="warning" title={t('flavor.selected.blockedTitle')} class="order-1 mb-3">
		{t('flavor.selected.unavailableBody', { name: selectedNativeFlavor ? consumerFlavorLabel(selectedNativeFlavor) : t('flavor.selected.fallbackName') })}
	</Alert>
{/if}

{#if !refreshError && (defaultZoneUnavailable || uncheckedFlavors.length > 0)}
	<Alert tone="warning" title={t(defaultZoneUnavailable ? 'flavor.policy.title' : 'flavor.failure.title')} class="order-1 mb-3">
		<p>{t(defaultZoneUnavailable ? (adminMode ? 'flavor.policy.helpAdmin' : 'flavor.policy.help') : 'flavor.failure.reason')}</p>
		{#snippet actions()}<Button variant="secondary" size="sm" disabled={refreshing} onclick={() => { void onRefresh('manual'); }}>{t('flavor.refresh.retry')}</Button>{/snippet}
	</Alert>
{/if}

{#if catalogVisible && (flavors.length > 0 || hasFilters)}
<p class="order-2 mb-3 text-xs text-ink-2">{t('flavor.availability.selectable', { count: creatableFlavors.length })}</p>

<!-- 카테고리 필터 탭 -->
<div class="order-3 mb-4 flex flex-wrap gap-2">
	{#each ([
		{ key: 'all', label: t('flavor.category.all', { count: creatableFlavors.length }) },
		{ key: 'general', label: t('flavor.category.general', { count: counts.general }) },
		{ key: 'cpu', label: t('flavor.category.cpu', { count: counts.cpu }) },
		{ key: 'memory', label: t('flavor.category.memory', { count: counts.memory }) },
		{ key: 'gpu', label: t('flavor.category.gpu', { count: counts.gpu }) },
	] as const) as tab}
		<button
			onclick={() => { activeCategory = tab.key; if (tab.key !== 'all' && tab.key !== 'gpu') activeGpuType = null; }}
			aria-pressed={activeCategory === tab.key}
			class="min-h-11 md:min-h-9 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {activeCategory === tab.key
				? 'bg-surface-selected text-ink-0 border border-line-2'
				: 'bg-surface-sunken text-ink-2 border border-transparent hover:bg-surface-selected'}"
		>{tab.label}</button>
	{/each}
</div>

{#if gpuTypeOptions.length > 0}
	<div class="order-3 mb-4" role="group" aria-label={t('flavor.gpuFilter.title')}>
		<p class="mb-2 text-xs font-medium text-ink-2">{t('flavor.gpuFilter.title')}</p>
		<div class="flex flex-wrap gap-2">
			<Button variant={activeGpuType === null ? 'secondary' : 'subtle'} size="sm" class="max-w-full" ariaPressed={activeGpuType === null} onclick={() => { activeGpuType = null; }}><span class="min-w-0 whitespace-normal break-words">{t('flavor.gpuFilter.all')}</span></Button>
			{#each gpuTypeOptions as model (model)}
				<Button variant={activeGpuType === model ? 'secondary' : 'subtle'} size="sm" class="max-w-full" ariaPressed={activeGpuType === model} onclick={() => { activeGpuType = model; if (activeCategory !== 'all' && activeCategory !== 'gpu') activeCategory = 'gpu'; }}><span class="min-w-0 whitespace-normal break-words">{model}</span></Button>
			{/each}
		</div>
	</div>
{/if}

<!-- 통합 검색 -->
<div class="order-4 relative mb-4">
	<span class="absolute left-3 top-1/2 -translate-y-1/2 text-ink-2 pointer-events-none">
		<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"/>
		</svg>
	</span>
	<input
		type="search"
		placeholder={t('flavor.searchPlaceholder')}
		aria-label={t('flavor.searchPlaceholder')}
		bind:value={searchTerm}
		class="w-full min-h-11 md:min-h-9 rounded-lg border border-line bg-surface-base pl-9 pr-3 py-2 text-sm text-ink-1 placeholder-ink-2 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
	/>
</div>
{/if}

<!-- 프로젝트 quota delta 미터 -->
{#snippet quotaDelta(used: number, requested: number, limit: number, critical: boolean)}
	{@const usedPercent = quotaPercent(used, limit)}
	{@const deltaPercent = Math.min(100 - usedPercent, quotaPercent(requested, limit))}
	<div class="quota-track relative mt-auto h-[5px] rounded-full bg-surface-sunken overflow-hidden">
		<BklitChart
			spec={{
				kind: 'bar', orientation: 'horizontal', stacked: true, compact: true, tooltips: false,
				data: [{ category: '', used: usedPercent, requested: deltaPercent }], xKey: 'category', domain: [0, 100],
				series: [
					{ key: 'used', label: '', color: 'var(--color-accent)' },
					{ key: 'requested', label: '', color: critical ? 'var(--color-state-danger)' : 'var(--color-action-warm)' },
				],
			}}
			height={5} decorative
		/>

	</div>
{/snippet}

{#snippet quotaCell(label: string, pair: QuotaPair | null | undefined, requested: number, unit = '', divisor = 1)}
	<div class="flex flex-col gap-1.5 bg-surface-base px-3 py-2" role="group" aria-label={label}>
		<span class="text-xs uppercase tracking-wider text-ink-2 font-mono font-semibold">{label}</span>
		{#if pair}
			{@const critical = pair.limit >= 0 && pair.in_use + requested > pair.limit}
			<div class="flex min-w-0 flex-wrap items-baseline gap-1 font-mono [overflow-wrap:anywhere]">
				<span class="text-sm text-ink-2">{pair.in_use / divisor}{unit}</span>
				{#if requested > 0}
					<span class="text-ink-2 text-xs">→</span>
					<span class="text-sm font-bold {critical ? 'text-state-danger-text' : 'text-warm-text'}">{(pair.in_use + requested) / divisor}{unit}</span>
				{/if}
				<span class="text-ink-2 text-xs">/ {pair.limit < 0 ? '∞' : `${pair.limit / divisor}${unit}`}</span>
			</div>
			{#if pair.limit >= 0}
				{@render quotaDelta(pair.in_use, requested, pair.limit, critical)}
			{/if}
		{:else}
			<span class="text-sm text-ink-2">{tp('unknown')}</span>
		{/if}
	</div>
{/snippet}

{#if quota}
	{@const reqVm = selectedFlavor ? 1 : 0}
	{@const reqCpu = selectedFlavor?.vcpus ?? 0}
	{@const reqRamMb = selectedFlavor?.ram ?? 0}
	{@const reqDiskGb = selectedFlavor ? (bootVolumeSizeGb ?? selectedFlavor.disk) : 0}
	<div class="order-1 mb-4 overflow-hidden rounded-xl border border-line bg-surface-base/70 md:mb-5">
		<div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-3 py-2 border-b border-line">
			<span class="text-xs text-ink-2 font-medium">{t('flavor.quota.title')}</span>
			<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2">
				<span class="flex items-center gap-1"><i class="inline-block w-2 h-2 shrink-0 rounded-full bg-accent"></i>{t('flavor.quota.currentUsage')}</span>
				<span class="flex items-center gap-1"><i class="inline-block w-2 h-2 shrink-0 rounded-full bg-action-warm"></i>{t('flavor.quota.addedVm')}</span>
			</div>
		</div>
		<div class="grid grid-cols-2 gap-px bg-surface-sunken @2xl/panel:grid-cols-4">
			{@render quotaCell(t('flavor.quota.vm'), quota.instances, reqVm)}
			{@render quotaCell('vCPU', quota.cores, reqCpu)}
			{@render quotaCell('RAM', quota.ram, reqRamMb, 'GB', 1024)}
			{@render quotaCell(t('flavor.quota.disk'), quota.gigabytes, reqDiskGb, 'GB')}
		</div>
	</div>
{/if}

<!-- 관리자 전용: 현재 선택 가능한 플레이버의 호스트 용량 스냅샷 -->
{#if adminMode && selectedFlavor?.eligibility && selectedBlock === null}
	<Card surface="base" padding="sm" class="order-1 mb-4">
		<p class="mb-2 text-xs font-medium text-[var(--color-ink-2)]">
			{#snippet conditionFlavorName(text: string)}<span class="font-mono text-[var(--color-ink-0)]">{text}</span>{/snippet}
			<RichText segments={t.rich('flavor.conditions.title', { name: consumerFlavorLabel(selectedFlavor) })} tags={{ name: conditionFlavorName }} />
		</p>
		<dl class="text-xs">
			<div>
				<dt class="mb-1 text-[var(--color-ink-2)]">{t('flavor.conditions.hostMax')}</dt>
				<dd class="font-mono text-[var(--color-ink-1)]">
					{#if selectedCapacity?.remaining_vcpus != null && selectedCapacity.remaining_ram_mb != null}
						{selectedCapacity.cpu_resource_class ?? 'CPU'} {selectedCapacity.remaining_vcpus} · RAM {ramLabel(selectedCapacity.remaining_ram_mb)}
						<span class="block text-[var(--color-ink-2)]">{t('flavor.conditions.hostCandidates', { count: selectedCapacity.candidate_hosts })}</span>
					{:else}
						{t('flavor.conditions.hostAvailable')}
					{/if}
					{#if selectedCapacity?.numa_unverified}
						<span class="block text-[var(--color-state-warning-text)]">{t('flavor.conditions.numaWarning')}</span>
					{/if}
				</dd>
			</div>
		</dl>
		<p class="mt-2 text-xs text-[var(--color-ink-2)]">{t('flavor.conditions.notReserved')}</p>
	</Card>
{/if}


{#if catalogVisible && !refreshError && !defaultZoneUnavailable && uncheckedFlavors.length === 0 && creatableFlavors.length === 0}
	<Alert tone="neutral" title={t('flavor.available.emptyTitle')} class="order-6 mb-4">{t('flavor.available.emptyBody')}</Alert>
{:else if catalogVisible && !refreshError && creatableFlavors.length > 0 && searchedFlavors.length === 0 && hasFilters}
	<Alert tone="neutral" title={t('flavor.empty')} class="order-6 mb-4">
		{t('flavor.filter.reason')}
		{#snippet actions()}<Button variant="secondary" size="sm" onclick={resetFilters}>{t('flavor.filter.reset')}</Button>{/snippet}
	</Alert>
{/if}


{#if catalogVisible && searchedFlavors.length > 0}
<div class="order-6 min-w-0">
<ResponsiveTable>
	{#snippet cards()}
		{#each paginatedFlavors as flavor (flavor.id)}
			{@const badge = categoryBadge(flavor)}
			{@const gpu = gpuSummary(flavor)}
			{@const hostCapacity = adminMode ? hostCapacityText(flavor) : ''}
			{@const cellUnverified = adminMode && numaUnverified(flavor)}
			<CompactResourceCard selected={selectedId === flavor.id}>
				<h3 class="break-words text-sm font-medium line-clamp-2" title={consumerFlavorLabel(flavor)}>{consumerFlavorLabel(flavor)}</h3>
				{#if badge}<span class="text-xs text-ink-2">{badge.label}</span>{/if}
				<dl class="flex flex-wrap gap-x-4 gap-y-1 text-xs"><div><dt class="text-ink-2">vCPU</dt><dd>{flavor.vcpus}</dd></div><div><dt class="text-ink-2">RAM</dt><dd>{ramLabel(flavor.ram)}</dd></div><div><dt class="text-ink-2">{t('flavor.disk')}</dt><dd>{flavor.disk} GB</dd></div></dl>
				{#snippet actions()}<Button variant="secondary" size="sm" disabled={selectionLocked} ariaPressed={selectedId === flavor.id} onclick={() => handleFlavorClick(flavor)}>{t('flavor.selectLabel', { name: selectionLabel(flavor) })}</Button>{/snippet}
				{#snippet details()}
					<div class="space-y-1 break-words text-xs text-ink-2">
						<p>{t('flavor.network')}: {networkBandwidth(flavor)}</p>
						{#if flavor.is_public}<p>{t('flavor.public')}</p>{/if}
						{#if gpu}<p>{gpu}</p>{/if}
						{#if hostCapacity}<p>{hostCapacity}</p>{/if}
						{#if cellUnverified}<p class="text-state-warning-text">{t('flavor.host.numaUnverifiedNote')}</p>{/if}
					</div>
				{/snippet}
			</CompactResourceCard>
		{/each}
	{/snippet}
<TableShell density="compact">
<div class="min-w-[39rem]">
	<div class="grid grid-cols-[2fr_80px_90px_100px_100px] border-b border-line px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-ink-2">
		<div>{t('flavor.name')}</div>
		<div class="text-center">VCPU</div>
		<div class="text-center">RAM</div>
		<div class="text-center">{t('flavor.ssdDisk')}</div>
		<div class="text-center">{t('flavor.network')}</div>
	</div>

	{#each paginatedFlavors as flavor (flavor.id)}
		{@const badge = categoryBadge(flavor)}
		{@const gpu = gpuSummary(flavor)}
		{@const hostCapacity = adminMode ? hostCapacityText(flavor) : ''}
		{@const cellUnverified = adminMode && numaUnverified(flavor)}
		<button
			onclick={() => handleFlavorClick(flavor)}
			aria-label={t('flavor.selectLabel', { name: selectionLabel(flavor) })}
			aria-pressed={selectedId === flavor.id}
			disabled={selectionLocked}
			class="grid w-full grid-cols-[2fr_80px_90px_100px_100px] border-b border-line/60 px-4 py-3 text-sm tabular-nums transition-colors hover:bg-surface-selected focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink-2
				{selectedId === flavor.id ? 'bg-surface-selected ring-1 ring-inset ring-line-2' : 'bg-surface-base'}"
		>
			<div class="flex min-w-0 items-center gap-3">
				<div class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-line-2 bg-surface-sunken">
					<svg class="h-4 w-4 text-ink-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 002 2v10a2 2 0 00-2 2zM9 9h6v6H9V9z"/>
					</svg>
				</div>
				<div class="min-w-0">
					<div class="flex items-center gap-2">
						<span class="truncate font-medium text-ink-0">{consumerFlavorLabel(flavor)}</span>
						{#if badge}
							<span class="rounded border px-1.5 py-0.5 text-xs {badge.class}">{badge.label}</span>
						{/if}
						{#if flavor.is_public}
							<span class="rounded border border-line-2 bg-surface-sunken px-1.5 py-0.5 text-xs text-ink-2">{t('flavor.public')}</span>
						{/if}
					</div>
					{#if gpu}
						<div class="mt-0.5 text-xs text-ink-2">{gpu}</div>
					{/if}
					{#if hostCapacity}
						<div class="mt-0.5 text-xs text-ink-2">{hostCapacity}</div>
					{/if}
					{#if cellUnverified}
						<div class="mt-0.5 text-xs text-[var(--color-state-warning-text)]">{t('flavor.host.numaUnverifiedNote')}</div>
					{/if}
				</div>
			</div>
			<div class="self-center text-center text-ink-2">{flavor.vcpus}</div>
			<div class="self-center text-center text-ink-2">{ramLabel(flavor.ram)}</div>
			<div class="self-center text-center text-ink-2">{flavor.disk} GB</div>
			<div class="self-center text-center text-xs text-ink-2">{networkBandwidth(flavor)}</div>
		</button>
	{/each}

</div>
</TableShell>
</ResponsiveTable>
</div>
{/if}

<!-- 페이지네이션 -->
{#if catalogVisible && searchedFlavors.length > 0}
<div class="order-7 min-w-0">
	<Pagination
		page={currentPage}
		{totalPages}
		hasPrev={currentPage > 1}
		hasNext={currentPage < totalPages}
		onPrev={() => currentPage = Math.max(1, currentPage - 1)}
		onNext={() => currentPage = Math.min(totalPages, currentPage + 1)}
		note={t('flavor.pagination.range', { count: searchedFlavors.length, start: (currentPage - 1) * PAGE_SIZE + 1, end: Math.min(currentPage * PAGE_SIZE, searchedFlavors.length) })}
	/>
</div>
{/if}
{/if}
</div>
