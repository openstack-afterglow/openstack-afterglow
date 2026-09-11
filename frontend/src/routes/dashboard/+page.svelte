<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth, authReady } from '$lib/stores/auth';
	import { siteConfig } from '$lib/config/site';
	import { api } from '$lib/api/client';
	import type {
		DashboardOverviewSummary,
	} from '$lib/types/compute';
	import type { DashboardAlert, DashboardOverviewQuotas } from '$lib/types/quotas';
	import type { DashboardK3sStats } from '$lib/types/k3s';
	import type { AnnouncementUser } from '$lib/types/announcements';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { Alert, PageShell, Spark, SectionHeader } from '$lib/components/ui';
	import DashboardGreetingHeader from '$lib/components/dashboard/overview/DashboardGreetingHeader.svelte';
	import DashboardStatTiles from '$lib/components/dashboard/overview/DashboardStatTiles.svelte';
	import RecentInstancesCard from '$lib/components/dashboard/overview/RecentInstancesCard.svelte';
	import QuotaUsageCard from '$lib/components/dashboard/overview/QuotaUsageCard.svelte';
	import RangeToggle from '$lib/components/dashboard/overview/RangeToggle.svelte';

	type Range = '24h' | '7d' | '14d';
	type SyncStatus = 'waiting' | 'partial' | 'complete';
	type BatchMode = 'initial' | 'auto' | 'manual';
	type Domain = 'summary' | 'quotas' | 'k3s' | 'trend' | 'announcements';

	interface TrendSeries {
		data: number[];
		points: number;
		available: boolean;
	}

	interface TrendData {
		vcpu: TrendSeries;
		memory: TrendSeries;
		storage: TrendSeries;
		network: TrendSeries & { unit: string };
		prometheus_available: boolean;
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
	const k3sDisabled = $derived(!($siteConfig.services?.k3s ?? false));
	const authLoading = $derived(!$authReady);

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
	let initialProjectId = $state<string | null>(null);
	const initialLoadPending = $derived(Boolean(projectId && initialProjectId !== projectId));
	let currentBatch: BatchState | null = null;
	let manualBatchId: number | null = null;

	const alerts = $derived.by(() => {
		const result: DashboardAlert[] = [];
		const errors = summaryState.data?.instances.error ?? 0;
		if (errors > 0) {
			result.push({
				type: 'instance_error',
				severity: 'danger',
				message: `오류 상태 인스턴스 ${errors}개`,
				count: errors,
			});
		}
		result.push(...(quotasState.data?.alerts ?? []));
		return result;
	});
	// 관리자 공지(영속·읽음추적) — 쿼터 경고(파생·일시적)와 같은 카드에서 병합 표시.
	const announcements = $derived(announcementsState.data ?? []);
	const alertsPending = $derived(
		authLoading || initialLoadPending || summaryState.pending || quotasState.pending || announcementsState.pending,
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
		requestRange?: Range,
	): boolean {
		return (
			projectEpoch === requestEpoch
			&& visibleProjectId === requestProjectId
			&& slot.generation === generation
			&& slot.batchId === batchId
			&& (requestRange === undefined || range === requestRange)
		);
	}

	function errorFor(domain: Domain): string {
		return {
			summary: '인스턴스 현황을 불러오지 못했습니다',
			quotas: '쿼터를 불러오지 못했습니다',
			k3s: 'Drover 클러스터 현황을 불러오지 못했습니다',
			trend: '메트릭을 불러오지 못했습니다',
			announcements: '공지를 불러오지 못했습니다',
		}[domain];
	}

	async function loadResource<T>(
		domain: Domain,
		state: ResourceState<T>,
		path: string,
		batch: BatchState | null,
		requestRange?: Range,
	): Promise<void> {
		const requestProjectId = projectId;
		if (!$authReady || !requestProjectId || !token) return;

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
			const data = await api.get<T>(path, token, requestProjectId, {
				refresh: batch?.refresh,
				signal: controller.signal,
			});
			if (!ownsRequest(slot, generation, batchId, requestProjectId, requestEpoch, requestRange)) return;
			state.data = data;
			state.error = null;
			state.lastSuccessAt = Date.now();
			settleDomain(batch, domain, true);
		} catch {
			if (!ownsRequest(slot, generation, batchId, requestProjectId, requestEpoch, requestRange)) return;
			state.error = errorFor(domain);
			settleDomain(batch, domain, false);
		} finally {
			if (ownsRequest(slot, generation, batchId, requestProjectId, requestEpoch, requestRange)) {
				state.pending = false;
				slot.controller = null;
			}
		}
	}

	async function loadSummary(batch: BatchState | null): Promise<void> {
		await loadResource(
			'summary',
			summaryState,
			'/api/v1/dashboard/summary?view=overview&recent_limit=12',
			batch,
		);
	}

	async function loadQuotas(batch: BatchState | null): Promise<void> {
		await loadResource(
			'quotas',
			quotasState,
			'/api/v1/dashboard/quotas?view=overview',
			batch,
		);
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
		if (!$authReady || !token || !projectId || projectId !== visibleProjectId) return;

		const enabled: Domain[] = ['summary', 'quotas', 'trend', 'announcements'];
		if (!k3sDisabled) enabled.push('k3s');
		const batch = newBatch(mode, enabled);
		currentBatch = batch;
		if (mode === 'manual') {
			manualBatchId = batch.id;
			refreshing = true;
		}
		if (!lastSuccessfulSyncAt) syncStatus = 'waiting';

		void loadSummary(batch);
		void loadQuotas(batch);
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
		localStorage.setItem('dashboard-overview-range', nextRange);
		if (!$authReady) return;
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

	$effect.pre(() => {
		const nextProjectId = $auth.projectId ?? null;
		if (nextProjectId === visibleProjectId) return;
		retireBatch(currentBatch);
		projectEpoch += 1;
		abortAllSlots();
		resetResources();
		visibleProjectId = nextProjectId;
		initialProjectId = null;
	});

	$effect(() => {
		const ready = $authReady;
		const nextProjectId = $auth.projectId;
		if (!ready || !nextProjectId || nextProjectId !== visibleProjectId || initialProjectId === nextProjectId) return;
		initialProjectId = nextProjectId;
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
</script>

{#key visibleProjectId}
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

	<div class="flex items-center justify-between mb-1">
		<p class="text-xs tracking-tight text-[var(--color-ink-2)]">사용 추세</p>
		<RangeToggle value={range} onchange={handleRangeChange} />
	</div>
	<div class="grid grid-cols-1 md:grid-cols-3 gap-3.5">
		{#each [
			{ label: `vCPU 사용률 (${range})`, color: 'var(--color-accent)', key: 'vcpu' as const, unit: '%' },
			{ label: `메모리 (${range})`, color: 'var(--color-accent-2)', key: 'memory' as const, unit: '%' },
			{ label: `디스크 사용률 (${range})`, color: 'var(--color-warm)', key: 'storage' as const, unit: '%' },
		] as card}
			{@const currentTrend = trendState.data?.range === range ? trendState.data : null}
			{@const series = currentTrend?.[card.key]}
			{@const hasData = (series?.data.length ?? 0) > 0}
			{@const current = hasData ? series!.data.at(-1)! : null}
			{@const min = hasData ? Math.min(...series!.data) : null}
			{@const max = hasData ? Math.max(...series!.data) : null}
			<div class="bg-surface-base border border-line rounded-lg p-5 flex flex-col gap-2">
				<div class="flex items-baseline justify-between">
					<p class="text-xs tracking-tight text-[var(--color-ink-2)]">{card.label}</p>
					{#if current !== null}
						<span class="text-xl font-semibold tabular-nums text-[var(--color-ink-0)]">
							{current.toFixed(1)}<span class="ml-0.5 text-xs text-[var(--color-ink-2)]">{card.unit}</span>
						</span>
					{/if}
				</div>
				<div class="min-h-[72px] flex items-center w-full">
					{#if (authLoading || initialLoadPending || trendState.pending) && !hasData}
						<div class="h-[72px] w-full bg-surface-sunken/60 rounded animate-pulse"></div>
					{:else if hasData}
						<Spark data={series!.data} color={card.color} height={72} class="w-full" />
					{:else if trendState.error}
						<p class="text-[11px] italic text-[var(--color-state-danger)]">메트릭을 불러오지 못했습니다</p>
					{:else if !currentTrend || !currentTrend.prometheus_available}
						<p class="text-xs italic text-[var(--color-ink-2)]">메트릭 수집 미설정</p>
					{:else}
						<p class="text-xs text-[var(--color-ink-2)]">해당 메트릭 수집 대기 중</p>
					{/if}
				</div>
				{#if hasData}
					<p class="text-xs tabular-nums text-[var(--color-ink-2)]">
						min {min!.toFixed(1)}{card.unit} · max {max!.toFixed(1)}{card.unit}
						{#if trendState.error} · 갱신 실패{/if}
					</p>
				{/if}
			</div>
		{/each}
	</div>

	<div class="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-3.5">
		<div data-tour="dashboard-recent">
			<RecentInstancesCard
				instances={summaryState.data?.recent_instances ?? []}
				pending={authLoading || initialLoadPending || summaryState.pending}
				error={summaryState.error}
			/>
		</div>

		<div class="flex flex-col gap-3.5">
			<div class="bg-surface-base border border-line rounded-lg p-5">
				<SectionHeader title="시스템 알림">
					{#snippet right()}
						<a href="/dashboard/notifications" class="text-[13px] text-[var(--color-ink-3)] hover:text-[var(--color-ink-1)] transition-colors">모두 보기 →</a>
					{/snippet}
				</SectionHeader>
				{#if alertsPending && alerts.length === 0 && announcements.length === 0}
					<ul class="mt-3 flex flex-col gap-2 animate-pulse">
						<li class="h-4 bg-surface-sunken/60 rounded"></li>
						<li class="h-4 bg-surface-sunken/60 rounded w-3/4"></li>
					</ul>
				{:else if alertsCompleteEmpty}
					<p class="text-sm text-[var(--color-ink-3)] mt-4">알림 없음</p>
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
									<span class="text-[10px] text-[var(--color-ink-3)] tabular-nums flex-shrink-0">×{alert.count}</span>
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
										<span class="ml-1 text-[9px] uppercase tracking-wide text-[var(--color-accent)]">new</span>
									{/if}
								</a>
							</li>
						{/each}
						{#if alertsFailed}
							<li><Alert tone="danger">일부 알림을 불러오지 못했습니다</Alert></li>
						{/if}
					</ul>
				{/if}
			</div>

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
