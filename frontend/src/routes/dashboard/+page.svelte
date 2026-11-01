<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { t as tc } from '$lib/i18n/ns/common';
	import { onDestroy, onMount, untrack } from 'svelte';
	import { auth, canWrite } from '$lib/stores/auth';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import { siteConfig } from '$lib/config/site';
	import { api } from '$lib/api/client';
	import type {
		DashboardOverviewSummary,
	} from '$lib/types/compute';
	import type { DashboardAlert, DashboardOverviewQuotas } from '$lib/types/quotas';
	import type { DashboardK3sStats } from '$lib/types/k3s';
	import type { AnnouncementUser } from '$lib/types/announcements';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { Alert, AnimatedNumber, Button, PageShell, SectionHeader } from '$lib/components/ui';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import type { ChartSpec } from '$lib/components/charts/types';
	import DashboardGreetingHeader from '$lib/components/dashboard/overview/DashboardGreetingHeader.svelte';
	import DashboardStatTiles from '$lib/components/dashboard/overview/DashboardStatTiles.svelte';
	import RecentInstancesCard from '$lib/components/dashboard/overview/RecentInstancesCard.svelte';
	import QuotaUsageCard from '$lib/components/dashboard/overview/QuotaUsageCard.svelte';
	import RangeToggle from '$lib/components/dashboard/overview/RangeToggle.svelte';
	import UsageScheduleReminders from '$lib/components/instance/UsageScheduleReminders.svelte';

	type Range = '24h' | '7d' | '14d';
	type SyncStatus = 'waiting' | 'partial' | 'complete';
	type BatchMode = 'initial' | 'auto' | 'manual';
	type Domain = 'summary' | 'quotas' | 'k3s' | 'trend' | 'announcements';

	interface TrendSeries {
		data: number[];
		points: number;
		available: boolean;
		source: string | null;
		status: string;
		native_status: string | null;
	}

	interface TrendData {
		vcpu: TrendSeries;
		memory: TrendSeries;
		storage: TrendSeries;
		network: TrendSeries & { unit: string };
		monitoring_available: boolean;
		scope?: 'native_policy';
		range: Range;
	}

	interface ResourceState<T> {
		data: T | null;
		pending: boolean;
		disabled: boolean;
		error: string | null;
		lastSuccessAt: number | null;
	}

	interface RequestSlot {
		generation: number;
		controller: AbortController | null;
		batchId: number | null;
	}

	interface BatchState {
		id: number;
		mode: BatchMode;
		refresh: boolean;
		enabled: Set<Domain>;
		succeeded: Set<Domain>;
		settled: Set<Domain>;
		retired: boolean;
		finished: boolean;
		done: Promise<void>;
		resolveDone: () => void;
	}

	const VALID_RANGES: readonly Range[] = ['24h', '7d', '14d'];
	const savedRange = typeof localStorage !== 'undefined'
		? localStorage.getItem('dashboard-overview-range') as Range | null
		: null;

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const context = $derived($authDisplayContext.key);
	const k3sDisabled = $derived(!($siteConfig.services?.k3s ?? false));
	const authLoading = $derived(!$authDisplayContext.ready);

	function newResource<T>(disabled = false): ResourceState<T> {
		return { data: null, pending: false, disabled, error: null, lastSuccessAt: null };
	}

	let summaryState = $state<ResourceState<DashboardOverviewSummary>>(newResource());
	let quotasState = $state<ResourceState<DashboardOverviewQuotas>>(newResource());
	let k3sState = $state<ResourceState<DashboardK3sStats>>(newResource());
	let trendState = $state<ResourceState<TrendData>>(newResource());
	let announcementsState = $state<ResourceState<AnnouncementUser[]>>(newResource());
	let range = $state<Range>(savedRange && VALID_RANGES.includes(savedRange) ? savedRange : '14d');
	let visibleProjectId = $state<string | null>(null);
	let visibleContext = $state<string | null>(null);
	let refreshing = $state(false);
	let syncStatus = $state<SyncStatus>('waiting');
	let lastSuccessfulSyncAt = $state<number | null>(null);

	const slots: Record<Domain, RequestSlot> = {
		summary: { generation: 0, controller: null, batchId: null },
		quotas: { generation: 0, controller: null, batchId: null },
		k3s: { generation: 0, controller: null, batchId: null },
		trend: { generation: 0, controller: null, batchId: null },
		announcements: { generation: 0, controller: null, batchId: null },
	};

	let projectEpoch = 0;
	let nextBatchId = 0;
	let initialContext = $state<string | null>(null);
	const initialLoadPending = $derived(Boolean(projectId && initialContext !== context));
	let currentBatch: BatchState | null = null;
	let manualBatchId: number | null = null;

	const alerts = $derived.by(() => {
		const result: DashboardAlert[] = [];
		const errors = summaryState.data?.instances.error ?? 0;
		if (errors > 0) {
			result.push({
				type: 'instance_error',
				severity: 'danger',
				message: t('overview.errorInstances', { count: errors }),
				count: errors,
			});
		}
		result.push(...(quotasState.data?.alerts ?? []));
		return result;
	});
	// 관리자 공지(영속·읽음추적) — 쿼터 경고(파생·일시적)와 같은 카드에서 병합 표시.
	const announcements = $derived(announcementsState.data ?? []);
	const alertsPending = $derived(
		authLoading || initialLoadPending
			|| (summaryState.pending && summaryState.data === null)
			|| (quotasState.pending && quotasState.data === null)
			|| (announcementsState.pending && announcementsState.data === null),
	);
	const alertsFailed = $derived(Boolean(summaryState.error || quotasState.error || announcementsState.error));
	const alertsCompleteEmpty = $derived(
		!alertsPending
			&& !alertsFailed
			&& summaryState.data !== null
			&& quotasState.data !== null
			&& announcementsState.data !== null
			&& alerts.length === 0
			&& announcements.length === 0,
	);

	function newBatch(mode: BatchMode, enabled: Domain[]): BatchState {
		let resolveDone!: () => void;
		const done = new Promise<void>((resolve) => {
			resolveDone = resolve;
		});
		return {
			id: ++nextBatchId,
			mode,
			refresh: mode === 'manual',
			enabled: new Set(enabled),
			succeeded: new Set(),
			settled: new Set(),
			retired: false,
			finished: false,
			done,
			resolveDone,
		};
	}

	function retireBatch(batch: BatchState | null): void {
		if (!batch || batch.retired || batch.finished) return;
		batch.retired = true;
		batch.resolveDone();
		if (currentBatch === batch) currentBatch = null;
		if (manualBatchId === batch.id) {
			manualBatchId = null;
			refreshing = false;
		}
	}

	function abortAllSlots(): void {
		for (const slot of Object.values(slots)) {
			slot.generation += 1;
			slot.controller?.abort();
			slot.controller = null;
			slot.batchId = null;
		}
	}

	function resetResources(): void {
		summaryState = newResource();
		quotasState = newResource();
		k3sState = newResource(k3sDisabled);
		trendState = newResource();
		announcementsState = newResource();
		syncStatus = 'waiting';
		lastSuccessfulSyncAt = null;
	}

	function finishBatch(batch: BatchState): void {
		if (batch.retired || batch.finished || currentBatch !== batch) return;
		if (batch.settled.size !== batch.enabled.size) return;
		batch.finished = true;
		batch.resolveDone();
		currentBatch = null;
		if (manualBatchId === batch.id) {
			manualBatchId = null;
			refreshing = false;
		}
	}

	function settleDomain(batch: BatchState | null, domain: Domain, succeeded: boolean): void {
		if (!batch || batch.retired || currentBatch !== batch) return;
		batch.settled.add(domain);
		if (succeeded) {
			batch.succeeded.add(domain);
			lastSuccessfulSyncAt = Date.now();
			syncStatus = batch.succeeded.size === batch.enabled.size ? 'complete' : 'partial';
		}
		finishBatch(batch);
	}

	function ownsRequest(
		slot: RequestSlot,
		generation: number,
		batchId: number | null,
		requestProjectId: string,
		requestEpoch: number,
		requestContext: string,
		requestRange?: Range,
	): boolean {
		return (
			projectEpoch === requestEpoch
			&& context === requestContext
			&& visibleContext === requestContext
			&& projectId === requestProjectId
			&& visibleProjectId === requestProjectId
			&& slot.generation === generation
			&& slot.batchId === batchId
			&& (requestRange === undefined || range === requestRange)
		);
	}

	function errorFor(domain: Domain): string {
		return {
			summary: t('overview.summaryFailed'),
			quotas: t('overview.quotasFailed'),
			k3s: t('overview.droverFailed'),
			trend: t('overview.metricsFailed'),
			announcements: t('overview.announcementsFailed'),
		}[domain];
	}

	async function loadResource<T>(
		domain: Domain,
		state: ResourceState<T>,
		path: string,
		batch: BatchState | null,
		requestRange?: Range,
		read?: (signal: AbortSignal) => Promise<T>,
	): Promise<void> {
		const requestProjectId = projectId;
		const requestToken = token;
		const requestContext = context;
		if (!$authDisplayContext.ready || !requestProjectId || !requestToken || visibleContext !== requestContext) return;

		const slot = slots[domain];
		slot.controller?.abort();
		const controller = new AbortController();
		const generation = ++slot.generation;
		const batchId = batch?.id ?? null;
		const requestEpoch = projectEpoch;
		slot.controller = controller;
		slot.batchId = batchId;
		state.pending = true;
		state.disabled = false;
		state.error = null;

		try {
			const data = read ? await read(controller.signal) : await api.get<T>(path, requestToken, requestProjectId, {
				refresh: batch?.refresh,
				signal: controller.signal,
			});
			if (!ownsRequest(slot, generation, batchId, requestProjectId, requestEpoch, requestContext, requestRange)) return;
			state.data = data;
			state.error = null;
			state.lastSuccessAt = Date.now();
			settleDomain(batch, domain, true);
		} catch {
			if (!ownsRequest(slot, generation, batchId, requestProjectId, requestEpoch, requestContext, requestRange)) return;
			state.error = errorFor(domain);
			settleDomain(batch, domain, false);
		} finally {
			if (ownsRequest(slot, generation, batchId, requestProjectId, requestEpoch, requestContext, requestRange)) {
				state.pending = false;
				slot.controller = null;
			}
		}
	}

	async function loadSnapshot(batch: BatchState): Promise<void> {
		type Section<T> = { data: T | null; error: string | null };
		type Snapshot = { summary: Section<DashboardOverviewSummary>; quotas: Section<DashboardOverviewQuotas> };
		const path = '/api/v1/dashboard/snapshot?recent_limit=12';
		let pending: Promise<Snapshot> | null = null;
		const read = (signal: AbortSignal) => pending ??= api.get<Snapshot>(path, token, projectId, {
			refresh: batch.refresh, signal,
		});
		await Promise.all([
			loadResource('summary', summaryState, path, batch, undefined, async (signal) => {
				const section = (await read(signal)).summary;
				if (section.error || !section.data) throw new Error('summary_unavailable');
				return section.data;
			}),
			loadResource('quotas', quotasState, path, batch, undefined, async (signal) => {
				const section = (await read(signal)).quotas;
				if (section.error || !section.data) throw new Error('quotas_unavailable');
				return section.data;
			}),
		]);
	}

	async function loadK3s(batch: BatchState | null): Promise<void> {
		if (k3sDisabled) {
			k3sState.disabled = true;
			return;
		}
		await loadResource('k3s', k3sState, '/api/v1/dashboard/k3s-stats', batch);
	}

	async function loadAnnouncements(batch: BatchState | null): Promise<void> {
		await loadResource('announcements', announcementsState, '/api/v1/announcements', batch);
	}

	async function loadTrend(batch: BatchState | null, requestedRange = range): Promise<void> {
		await loadResource(
			'trend',
			trendState,
			`/api/v1/dashboard/metrics/trend?range=${requestedRange}&include_network=false`,
			batch,
			requestedRange,
		);
	}

	async function fetchAll(mode: BatchMode): Promise<void> {
		const active = currentBatch;
		if (active && !active.retired && !active.finished) {
			if (mode !== 'manual') {
				await active.done;
				return;
			}
			retireBatch(active);
		}
		if (!$authDisplayContext.ready || !token || !projectId || projectId !== visibleProjectId) return;

		const enabled: Domain[] = ['summary', 'quotas', 'trend', 'announcements'];
		if (!k3sDisabled) enabled.push('k3s');
		const batch = newBatch(mode, enabled);
		currentBatch = batch;
		if (mode === 'manual') {
			manualBatchId = batch.id;
			refreshing = true;
		}
		if (!lastSuccessfulSyncAt) syncStatus = 'waiting';

		void loadSnapshot(batch);
		if (!k3sDisabled) void loadK3s(batch);
		else k3sState.disabled = true;
		void loadTrend(batch);
		void loadAnnouncements(batch);
		await batch.done;
	}

	async function forceRefresh(): Promise<void> {
		await fetchAll('manual');
	}

	function handleRangeChange(nextRange: Range): void {
		range = nextRange;
		trendState.data = null;
		localStorage.setItem('dashboard-overview-range', nextRange);
		if (!$authDisplayContext.ready) return;
		const batch = currentBatch;
		if (batch && !batch.retired && !batch.finished && batch.enabled.has('trend') && !batch.settled.has('trend')) {
			void loadTrend(batch, nextRange);
			return;
		}
		void loadTrend(null, nextRange);
	}

	const ar = createAutoRefresh(() => fetchAll('auto'), {
		storageKey: 'dashboard-home',
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

	function updateVisibleContext(next: { key: string; project: string | null }): void {
		if (next.key === visibleContext) return;
		retireBatch(currentBatch);
		projectEpoch += 1;
		abortAllSlots();
		resetResources();
		visibleProjectId = next.project;
		visibleContext = next.key;
		initialContext = null;
	}
	// Initialize before child mounts, then fence even same-tick scope A → B → A.
	$effect.pre(() => updateVisibleContext($authDisplayContext));
	onMount(() => authDisplayContext.subscribe(updateVisibleContext));

	$effect(() => {
		const ready = $authDisplayContext.ready;
		const nextContext = context;
		if (!ready || !token || !projectId || nextContext !== visibleContext || initialContext === nextContext) return;
		initialContext = nextContext;
		untrack(() => void fetchAll('initial'));
	});

	onDestroy(() => {
		retireBatch(currentBatch);
		projectEpoch += 1;
		abortAllSlots();
	});

	function severityDotColor(severity: DashboardAlert['severity'] | AnnouncementUser['severity']): string {
		if (severity === 'danger') return 'var(--color-state-danger)';
		if (severity === 'warning') return 'var(--color-state-warning)';
		return 'var(--color-accent)';
	}

	function telemetrySource(source: string): string {
		if (source === 'gnocchi') return t('telemetry.native');
		if (source === 'prometheus') return t('telemetry.fallback');
		if (source === 'mixed') return t('telemetry.mixed');
		return t('telemetry.source', { source });
	}

	function telemetryStatus(status: string): string {
		if (status === 'partial') return t('telemetry.partial');
		if (status === 'not_configured') return t('overview.metricsNotConfigured');
		if (status === 'forbidden') return t('telemetry.forbidden');
		if (status === 'unavailable') return t('telemetry.unavailable');
		return t('telemetry.noData');
	}

	const startReady = $derived(!authLoading && !initialLoadPending && summaryState.data?.instances.total === 0);
	const currentTrend = $derived(trendState.data?.range === range ? trendState.data : null);
	const trendCards = $derived([
		{ label: t('overview.vcpu', { range }), color: 'var(--color-accent)', key: 'vcpu' as const, unit: '%' },
		{ label: t('overview.memory', { range }), color: 'var(--color-accent-2)', key: 'memory' as const, unit: '%' },
		{ label: t('overview.disk', { range }), color: 'var(--color-warm)', key: 'storage' as const, unit: '%' },
	]);
	function hasSamples(series: TrendSeries | undefined): boolean {
		return Boolean(series?.available && (series.status === 'available' || series.status === 'partial') && series.data.some(Number.isFinite));
	}

	function trendChart(data: number[], label: string, color: string): ChartSpec {
		const known = data.filter(Number.isFinite);
		const min = known.length ? Math.min(...known) : 0;
		const max = known.length ? Math.max(...known) : 0;
		return {
			kind: 'time-series',
			data: data.map((value, index) => ({ sample: index + 1, value: Number.isFinite(value) ? value : null })),
			xKey: 'sample',
			series: [{ key: 'value', label, color, area: true }],
			domain: min === max ? [min - 0.5, max + 0.5] : [min, max],
			compact: true,
			tooltips: true,
			formatTime: (sample) => String(sample),
			formatValue: (value) => `${value.toFixed(1)}%`,
		};
	}
</script>

{#key visibleContext}
<PageShell class="flex flex-col gap-5">
	<DashboardGreetingHeader
		username={$auth.username ?? ''}
		projectName={$auth.projectName ?? '—'}
		{ar}
		{refreshing}
		onForceRefresh={forceRefresh}
		{syncStatus}
		{lastSuccessfulSyncAt}
	/>

	<DashboardStatTiles
		summary={summaryState.data}
		summaryPending={authLoading || initialLoadPending || summaryState.pending}
		summaryError={summaryState.error}
		quotas={quotasState.data}
		quotasPending={authLoading || initialLoadPending || quotasState.pending}
		quotasError={quotasState.error}
		k3sStats={k3sState.data}
		k3sPending={authLoading || initialLoadPending || k3sState.pending}
		k3sError={k3sState.error}
		{k3sDisabled}
	/>

	<section aria-label={t('telemetry.collection')} class="min-w-0 space-y-3">
		<div class="flex flex-wrap items-center justify-between gap-2">
			<h2 class="text-sm font-semibold text-ink-0">{t('overview.trend')}</h2>
			<div class="flex flex-wrap items-center gap-3">
				<Button variant="link" href="/dashboard/observability">{t('telemetry.openMonitoring')}</Button>
				<RangeToggle value={range} onchange={handleRangeChange} />
			</div>
		</div>
		<div class="grid grid-cols-1 gap-3.5 md:grid-cols-3">
			{#each trendCards as card (card.key)}
				{@const series = currentTrend?.[card.key]}
				{@const available = hasSamples(series)}
				{@const pending = (authLoading || initialLoadPending || trendState.pending) && !currentTrend}
				{@const current = available && Number.isFinite(series!.data.at(-1)) ? series!.data.at(-1)! : null}
				{@const known = available ? series!.data.filter(Number.isFinite) : []}
				<div role="group" aria-label={card.label} aria-busy={pending} data-metric={card.key} data-state={pending ? 'loading' : available ? trendState.error ? 'stale' : 'ready' : trendState.error && !currentTrend ? 'error' : series?.status ?? 'empty'} class="metric-slot min-w-0 rounded-lg border border-line bg-surface-base p-5">
					<div class="flex min-h-11 items-baseline justify-between gap-2">
						<h3 class="min-w-0 flex-1 text-xs text-ink-2">{card.label}</h3>
						{#if current !== null}
							<span class="shrink-0 text-xl font-semibold tabular-nums text-ink-0"><AnimatedNumber value={current} format={(value) => value.toFixed(1)} /><span class="ml-0.5 text-xs text-ink-2">{card.unit}</span></span>
						{/if}
					</div>
					<div class="metric-slot-content">
						{#if available}
							<BklitChart spec={trendChart(series!.data, card.label, card.color)} height={72} label={`${card.label} · ${tc('chart.data')}`} showData xLabel={tc('chart.category')} class="w-full" />
						{:else if pending}
							<LoadingState variant="section" label={tc('state.loadingNamed', { name: card.label })} />
						{:else if trendState.error && !currentTrend}
							<p role="status" class="text-sm text-state-danger-text">{t('overview.metricsFailed')}</p>
						{:else}
							<p class="text-sm text-ink-2">{series ? telemetryStatus(series.status) : currentTrend && !currentTrend.monitoring_available ? t('overview.metricsNotConfigured') : t('telemetry.noData')}</p>
						{/if}
					</div>
					<div class="metric-slot-meta text-xs text-ink-2">
						<details>
							<summary class="w-fit cursor-pointer rounded-sm py-2 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]">{t('telemetry.collection')}{#if trendState.error && currentTrend} · <span class="text-state-danger-text">{t('overview.refreshFailed')}</span>{/if}</summary>
							<div class="space-y-1 pb-2">
								{#if pending}<LoadingState variant="inline" label={tc('state.loadingNamed', { name: card.label })} />
								{:else if available}
									{#if series?.source}<p>{telemetrySource(series.source)}</p>{/if}
									{#if series?.status === 'partial'}<p class="text-state-warning-text">{t('telemetry.partial')}</p>{/if}
									{#if series?.source && series.source !== 'gnocchi' && series.native_status && series.native_status !== 'available'}<p>{t('telemetry.nativeState', { status: telemetryStatus(series.native_status) })}</p>{/if}
								{:else}<p>{series ? t('telemetry.nativeState', { status: telemetryStatus(series.native_status ?? series.status) }) : t('telemetry.unavailable')}</p>{/if}
								{#if card.key === 'vcpu' && currentTrend?.scope === 'native_policy'}<p>{t('telemetry.nativePolicy')}</p>{/if}
							</div>
						</details>
						{#if available}<p class="tabular-nums">{t('overview.minMax', { min: Math.min(...known).toFixed(1), max: Math.max(...known).toFixed(1), unit: card.unit })}</p>{/if}
					</div>
				</div>
			{/each}
		</div>
	</section>

	<div class="grid grid-cols-1 gap-3.5 lg:grid-cols-[2fr_1fr]">
		<div data-tour={startReady ? undefined : 'dashboard-recent'}>
			<RecentInstancesCard
				instances={summaryState.data?.recent_instances ?? []}
				pending={authLoading || initialLoadPending || (summaryState.pending && summaryState.data === null)}
				error={summaryState.error}
				loaded={summaryState.data !== null}
			>
				{#snippet emptyContent()}
					{#if startReady}
						<section aria-labelledby="dashboard-start-title" data-tour="dashboard-recent">
							<h2 id="dashboard-start-title" class="text-lg font-semibold text-ink-0">{t('start.title')}</h2>
							<p class="mt-1 text-sm text-ink-2">{t('start.description')}</p>
							<div class="mt-4 flex flex-wrap gap-2">
								{#if $canWrite && $auth.token && projectId}<Button href="/dashboard/compute/instances">{t('start.create')}</Button>{/if}
								<Button variant="secondary" href="/dashboard/compute/images">{t('start.images')}</Button>
								<Button variant="ghost" href="/docs">{t('start.guide')}</Button>
							</div>
						</section>
					{:else}<p class="py-2 text-sm text-ink-2">{t('recentInstances.empty')}</p>{/if}
				{/snippet}
			</RecentInstancesCard>
		</div>

		<div class="flex flex-col gap-3.5">
			<div class="bg-surface-base border border-line rounded-lg p-5">
				<SectionHeader title={t('overview.systemAlerts')}>
					{#snippet right()}
						<a href="/dashboard/notifications" class="text-[13px] text-ink-2 hover:text-ink-0 transition-colors">{t('overview.viewAll')}</a>
					{/snippet}
				</SectionHeader>
				{#if alertsPending && !alertsFailed && alerts.length === 0 && announcements.length === 0}
					<LoadingState variant="section" class="mt-3" label={tc('state.loadingNamed', { name: t('overview.systemAlerts') })} />
				{:else if alertsCompleteEmpty}
					<p class="mt-3 min-h-10 text-sm text-ink-2">{t('overview.noAlerts')}</p>
				{:else}
					<ul class="system-alert-list mt-3 flex flex-col gap-2">
						{#each alerts as alert}
							<li class="flex items-start gap-2.5 text-sm">
								<span
									class="mt-1.5 w-2 h-2 rounded-full flex-shrink-0"
									style="background: {severityDotColor(alert.severity)};"
								></span>
								<span class="flex-1 text-[var(--color-ink-0)] text-xs leading-snug">{alert.message}</span>
								{#if alert.count > 1}
								<span class="text-xs text-ink-2 tabular-nums flex-shrink-0">×{alert.count}</span>
								{/if}
							</li>
						{/each}
						{#each announcements as announcement}
							<li class="flex items-start gap-2.5 text-sm">
								<span
									class="mt-1.5 w-2 h-2 rounded-full flex-shrink-0"
									style="background: {severityDotColor(announcement.severity)};"
								></span>
								<a
									href="/dashboard/notifications?focus={announcement.id}"
									class="flex-1 text-[var(--color-ink-0)] text-xs leading-snug hover:text-[var(--color-accent)] hover:underline underline-offset-2 transition-colors"
								>
									{announcement.title}
									{#if !announcement.is_read}
										<span class="ml-1 text-xs uppercase tracking-wide text-[var(--color-accent)]">{t('overview.new')}</span>
									{/if}
								</a>
							</li>
						{/each}
						{#if alertsFailed}
							<li><Alert tone="danger">{t('overview.alertsPartial')}</Alert></li>
						{/if}
					</ul>
				{/if}
			</div>

			<UsageScheduleReminders />

			<QuotaUsageCard
				quotas={quotasState.data}
				pending={authLoading || initialLoadPending || quotasState.pending}
				error={quotasState.error}
			/>
		</div>
	</div>
</PageShell>
{/key}

<style>
	.metric-slot {
		display: grid;
		grid-template-rows: auto 1fr auto;
		gap: 0.5rem;
	}
	.metric-slot-content { min-block-size: 7.5rem; }
	.metric-slot-meta { min-block-size: 3.5rem; }

	@media (min-width: 1024px) {
		.system-alert-list {
			max-block-size: clamp(5.5rem, 14vh, 12rem);
			overflow-y: auto;
			scrollbar-gutter: stable;
		}
	}

	@media (min-width: 1024px) and (min-height: 840px) {
		.system-alert-list {
			max-block-size: clamp(8rem, 19vh, 18rem);
		}
	}

	@media (min-width: 1024px) and (min-height: 1080px) {
		.system-alert-list {
			max-block-size: clamp(10rem, 24vh, 24rem);
		}
	}
</style>
