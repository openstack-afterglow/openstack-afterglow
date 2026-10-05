<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatTile from '$lib/components/ui/StatTile.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import { t } from '$lib/i18n/ns/chat-studio';
	import RichText from '$lib/i18n/RichText.svelte';

	import { usageChartWindow } from '$lib/utils/chatUsageChartWindow';
	import { adminIdentityLabel } from '$lib/utils/adminIdentityLabel';
	interface SourceStat {
		source: string;
		tokens: number;
		raw_cost: number;
		request_count: number;
	}
	interface Overview {
		prompt_tokens: number;
		completion_tokens: number;
		total_tokens: number;
		credited_cost: number;
		raw_cost: number;
		request_count: number;
		unpriced_requests: number;
		active_users: number;
		conversation_count: number;
		by_source: SourceStat[];
	}
	interface ModelStat {
		model_name: string;
		prompt_tokens: number;
		completion_tokens: number;
		total_tokens: number;
		credited_cost: number;
		raw_cost: number;
		request_count: number;
		unpriced_requests: number;
	}
	interface UserStat {
		user_id: string;
		user_name?: string | null;
		prompt_tokens: number;
		completion_tokens: number;
		total_tokens: number;
		credited_cost: number;
		raw_cost: number;
		request_count: number;
	}
	interface MonthStat {
		month: string;
		ts: number;
		prompt_tokens: number;
		completion_tokens: number;
		total_tokens: number;
		credited_cost: number;
		raw_cost: number;
		request_count: number;
	}
	interface TimeStat {
		bucket: string;
		source: string;
		prompt_tokens: number;
		completion_tokens: number;
		total_tokens: number;
		credited_cost: number;
		request_count: number;
	}
	interface ProjectOption {
		id: string;
		name: string | null;
	}
	interface StatsResponse {
		range: string;
		project_id: string | null;
		overview: Overview;
		by_model: ModelStat[];
		monthly: MonthStat[];
		timeseries: TimeStat[];
		by_user: UserStat[];
		projects: ProjectOption[];
	}

	const RANGES = [
		{ value: '30d', get label() { return t('adminStats.range30Days'); } },
		{ value: '90d', get label() { return t('adminStats.range90Days'); } },
		{ value: '1y', get label() { return t('adminStats.rangeYear'); } },
		{ value: 'all', get label() { return t('adminStats.rangeAll'); } }
	];

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const USER_PAGE = 20;

	let range = $state('30d');
	let projectFilter = $state('');
	let selectedModel = $state('');
	let chartBucket = $state('hour');
	let data = $state<StatsResponse | null>(null);
	let timeSeries = $state<TimeStat[]>([]);
	let loading = $state(false);
	let loadingMore = $state(false);
	let loadingTimeSeries = $state(false);
	let timeSeriesError = $state('');
	let error = $state('');
	let userRows = $state<UserStat[]>([]);
	let userOffset = $state(0);
	let hasMoreUsers = $state(false);

	let timeSeriesGeneration = 0;
	const fmtInt = (n: number) => (n ?? 0).toLocaleString('en-US');
	const fmtCredit = (n: number) => (n ?? 0).toLocaleString('en-US', { maximumFractionDigits: 2 });
	const fmtUsd = (n: number) => `$${(n ?? 0).toFixed(4)}`;
	const CHART_BUCKETS = [
		{ value: '5m', get label() { return t('adminStats.bucket5Minutes'); } },
		{ value: '15m', get label() { return t('adminStats.bucket15Minutes'); } },
		{ value: 'hour', get label() { return t('adminStats.bucketHour'); } },
		{ value: 'day', get label() { return t('adminStats.bucketDay'); } },
		{ value: 'month', get label() { return t('adminStats.bucketMonth'); } }
	];
	const chartGranularityLabel = $derived(CHART_BUCKETS.find((item) => item.value === chartBucket)?.label ?? t('adminStats.bucketHour'));
	const fmtChartBucket = (bucket: string) => {
		if (chartBucket === 'month') return bucket;
		if (chartBucket === 'day') return bucket.slice(5);
		return `${bucket.slice(5, 10)} ${bucket.slice(11, 16)}`;
	};
	const chartWindowLabel = $derived(usageChartWindow(chartBucket)?.label ?? null);

	async function load() {
		if (!token) return;
		loading = true;
		error = '';
		try {
			const qs = new URLSearchParams({ range, user_limit: String(USER_PAGE), bucket: chartBucket });
			if (projectFilter) qs.set('project_id', projectFilter);
			const res = await api.get<StatsResponse>(`/api/v1/chat/admin/stats?${qs.toString()}`, token, projectId);
			data = res;
			userRows = res.by_user ?? [];
			userOffset = userRows.length;
			hasMoreUsers = userRows.length >= USER_PAGE;
		} catch (e) {
			error = e instanceof ApiError ? e.message : t('adminStats.loadFailed');
			data = null;
			userRows = [];
			hasMoreUsers = false;
		} finally {
			loading = false;
		}
	}

	async function loadMoreUsers() {
		if (!token || loadingMore) return;
		loadingMore = true;
		try {
			const qs = new URLSearchParams({ range, limit: String(USER_PAGE), offset: String(userOffset) });
			if (projectFilter) qs.set('project_id', projectFilter);
			const res = await api.get<{ users: UserStat[] }>(
				`/api/v1/chat/admin/stats/users?${qs.toString()}`,
				token,
				projectId
			);
			const more = res.users ?? [];
			userRows = [...userRows, ...more];
			userOffset += more.length;
			hasMoreUsers = more.length >= USER_PAGE;
		} catch {
			hasMoreUsers = false;
		} finally {
			loadingMore = false;
		}
	}

	async function loadTimeSeries() {
		if (!token) return;
		const generation = ++timeSeriesGeneration;
		loadingTimeSeries = true;
		timeSeriesError = '';
		try {
			const qs = new URLSearchParams({ range, bucket: chartBucket });
			if (projectFilter) qs.set('project_id', projectFilter);
			if (selectedModel) qs.set('model_name', selectedModel);
			const res = await api.get<{ series: TimeStat[] }>(
				`/api/v1/chat/admin/stats/timeseries?${qs.toString()}`,
				token,
				projectId
			);
			if (generation === timeSeriesGeneration) timeSeries = res.series ?? [];
		} catch (e) {
			if (generation === timeSeriesGeneration) {
				timeSeries = [];
				timeSeriesError = e instanceof ApiError ? e.message : t('adminStats.timeSeriesLoadFailed');
			}
		} finally {
			if (generation === timeSeriesGeneration) loadingTimeSeries = false;
		}
	}

	$effect(() => {
		void range;
		void projectFilter;
		if (token) void load();
	});
	$effect(() => {
		void range;
		void projectFilter;
		void chartBucket;
		void selectedModel;
		if (token) void loadTimeSeries();
	});

	function aggregateSeries(rows: TimeStat[]): Map<string, TimeStat> {
		const buckets = new Map<string, TimeStat>();
		for (const row of rows) {
			const current = buckets.get(row.bucket) ?? {
				bucket: row.bucket,
				source: 'all',
				prompt_tokens: 0,
				completion_tokens: 0,
				total_tokens: 0,
				credited_cost: 0,
				request_count: 0
			};
			current.prompt_tokens += row.prompt_tokens;
			current.completion_tokens += row.completion_tokens;
			current.total_tokens += row.total_tokens;
			current.credited_cost += row.credited_cost;
			current.request_count += row.request_count;
			buckets.set(row.bucket, current);
		}
		return buckets;
	}

	function formatBucket(date: Date): string {
		const iso = date.toISOString();
		if (chartBucket === 'month') return iso.slice(0, 7);
		if (chartBucket === 'day') return iso.slice(0, 10);
		const minute = chartBucket === '5m' || chartBucket === '15m' ? iso.slice(14, 16) : '00';
		return `${iso.slice(0, 10)} ${iso.slice(11, 13)}:${minute}:00`;
	}

	function advanceBucket(date: Date): void {
		if (chartBucket === 'month') date.setUTCMonth(date.getUTCMonth() + 1);
		else if (chartBucket === 'day') date.setUTCDate(date.getUTCDate() + 1);
		else if (chartBucket === '5m') date.setUTCMinutes(date.getUTCMinutes() + 5);
		else if (chartBucket === '15m') date.setUTCMinutes(date.getUTCMinutes() + 15);
		else date.setUTCHours(date.getUTCHours() + 1);
	}

	function floorBucket(date: Date): Date {
		const floored = new Date(date);
		floored.setUTCSeconds(0, 0);
		if (chartBucket === 'month') {
			floored.setUTCDate(1);
			floored.setUTCHours(0, 0, 0, 0);
		} else if (chartBucket === 'day') {
			floored.setUTCHours(0, 0, 0, 0);
		} else if (chartBucket === 'hour') {
			floored.setUTCMinutes(0);
		} else {
			const interval = chartBucket === '5m' ? 5 : 15;
			floored.setUTCMinutes(Math.floor(floored.getUTCMinutes() / interval) * interval);
		}
		return floored;
	}

	function chartStart(now: Date, rows: TimeStat[]): Date {
		const window = usageChartWindow(chartBucket);
		if (window) return floorBucket(new Date(now.getTime() - window.milliseconds));
		if (chartBucket !== 'month') return floorBucket(now);
		if (range === 'all') {
			const oldest = rows
				.map((row) => row.bucket)
				.filter((bucket) => /^\d{4}-\d{2}$/.test(bucket))
				.sort()[0];
			if (oldest) return floorBucket(new Date(`${oldest}-01T00:00:00.000Z`));
		}
		const days = range === '1y' ? 365 : range === '90d' ? 90 : 30;
		return floorBucket(new Date(now.getTime() - days * 24 * 60 * 60 * 1000));
	}

	function filledSeries(rows: TimeStat[]): TimeStat[] {
		const aggregate = aggregateSeries(rows);
		const end = floorBucket(new Date());
		const points: TimeStat[] = [];
		for (const cursor = chartStart(end, rows); cursor <= end; advanceBucket(cursor)) {
			const bucket = formatBucket(cursor);
			points.push(
				aggregate.get(bucket) ?? {
					bucket,
					source: 'all',
					prompt_tokens: 0,
					completion_tokens: 0,
					total_tokens: 0,
					credited_cost: 0,
					request_count: 0
				}
			);
		}
		return points;
	}

	const overview = $derived(data?.overview);
	const models = $derived(data?.by_model ?? []);
	const users = $derived(userRows);
	const chartPoints = $derived(filledSeries(timeSeries));
	const maxHourlyTokens = $derived(Math.max(1, ...chartPoints.map((point) => point.total_tokens)));
	const maxModelTokens = $derived(Math.max(1, ...models.map((m) => m.total_tokens)));
	const hasData = $derived((overview?.request_count ?? 0) > 0);

	const cardCls = 'rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)]';
	const selectCls =
		'rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-base)] px-3 py-1.5 text-sm text-[var(--color-ink-1)] focus:outline-none focus:border-[var(--color-accent)]';
</script>

<div class="max-w-6xl p-4 md:p-8">
	<PageHeader
		breadcrumb={t('adminStats.breadcrumb')}
		title={t('adminStats.title')}
		subtitle={t('adminStats.subtitle')}
	/>

	<!-- 필터 -->
	<div class="mb-6 flex flex-wrap items-center gap-3">
		<div class="flex gap-1 rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-1">
			{#each RANGES as r (r.value)}
				<button
					onclick={() => (range = r.value)}
					class="rounded px-3 py-1 text-xs font-medium transition-colors {range === r.value
						? 'bg-[var(--color-accent)] text-[var(--color-ink-0)]'
						: 'text-[var(--color-ink-3)] hover:text-[var(--color-ink-1)]'}"
				>
					{r.label}
				</button>
			{/each}
		</div>
		<select class={selectCls} bind:value={projectFilter}>
			<option value="">{t('adminStats.allProjects')}</option>
			{#each data?.projects ?? [] as project (project.id)}
				<option value={project.id}>{adminIdentityLabel(project.name, project.id)}</option>
			{/each}
		</select>
		{#if loading}<span class="text-xs text-[var(--color-ink-3)]">{t('adminStats.loading')}</span>{/if}
	</div>

	{#if error}
		<div
			class="mb-6 rounded-lg border border-[var(--color-state-danger)] bg-[var(--color-state-danger)]/10 px-4 py-3 text-sm text-[var(--color-state-danger)]"
		>
			{error}
		</div>
	{/if}

	{#if !loading && !hasData}
		<EmptyState headline={t('adminStats.emptyTitle')} description={t('adminStats.emptyDescription')} />
	{:else if overview}
		<!-- KPI 카드 -->
		<div class="mb-8 grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-7">
			<StatTile label={t('adminStats.inputTokens')} value={fmtInt(overview.prompt_tokens)} accent="blue" />
			<StatTile label={t('adminStats.outputTokens')} value={fmtInt(overview.completion_tokens)} accent="violet" />
			<StatTile label={t('adminStats.totalRequests')} value={fmtInt(overview.request_count)} accent="cyan" />
			<StatTile label={t('adminStats.activeUsers')} value={fmtInt(overview.active_users)} accent="emerald" />
			<StatTile label={t('adminStats.deductedCredits')} value={fmtCredit(overview.credited_cost)} accent="amber" />
			<StatTile label={t('adminStats.costUsd')} value={fmtUsd(overview.raw_cost)} accent="rose" />
			<StatTile label={t('adminStats.unpricedBilling')} value={fmtInt(overview.unpriced_requests)} accent="rose" />
		</div>

		<section class="{cardCls} mb-8 p-5">
			<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
				<div>
					<h3 class="text-sm font-semibold text-[var(--color-ink-1)]">{t('adminStats.chartTitle', { granularity: chartGranularityLabel })}</h3>
					<p class="mt-1 text-xs text-[var(--color-ink-3)]">
						{selectedModel
							? t('adminStats.chartModelUsage', { model: selectedModel, granularity: chartGranularityLabel, hasWindow: chartWindowLabel ? 'yes' : 'no', window: chartWindowLabel ?? '' })
							: t('adminStats.chartAllUsage', { granularity: chartGranularityLabel, hasWindow: chartWindowLabel ? 'yes' : 'no', window: chartWindowLabel ?? '' })}
					</p>
				</div>
				<div class="flex flex-wrap gap-2">
					<select class={selectCls} bind:value={chartBucket} aria-label={t('adminStats.selectBucket')}>
						{#each CHART_BUCKETS as bucket (bucket.value)}
							<option value={bucket.value}>{bucket.label}</option>
						{/each}
					</select>
					<select class={selectCls} bind:value={selectedModel} aria-label={t('adminStats.selectModel')}>
						<option value="">{t('adminStats.allModels')}</option>
						{#each models as model (model.model_name)}
							<option value={model.model_name}>{model.model_name}</option>
						{/each}
					</select>
				</div>
			</div>
			{#if loadingTimeSeries}
				<p class="text-sm text-[var(--color-ink-3)]">{t('adminStats.chartLoading', { granularity: chartGranularityLabel })}</p>
			{:else if timeSeriesError}
				<p class="text-sm text-[var(--color-state-danger)]">{timeSeriesError}</p>
			{:else if timeSeries.length === 0}
				<p class="text-sm text-[var(--color-ink-3)]">{t('adminStats.chartEmpty', { granularity: chartGranularityLabel })}</p>
			{:else}
				<div class="overflow-x-auto pb-1">
					<div class="flex h-48 min-w-[42rem] items-end gap-px">
						{#each chartPoints as point, index (point.bucket)}
							<div class="grid h-full min-w-0 flex-1 grid-rows-[minmax(0,1fr)_2rem] gap-1">
								<div class="relative h-full w-full">
									<div
										class="absolute inset-x-0 bottom-0 flex flex-col-reverse overflow-hidden rounded-t"
										style="height: {point.total_tokens > 0 ? Math.max(0.5, (point.total_tokens / maxHourlyTokens) * 100) : 0}%"
										title={t('adminStats.chartTooltip', { bucket: point.bucket, input: fmtInt(point.prompt_tokens), output: fmtInt(point.completion_tokens), total: fmtInt(point.total_tokens) })}
									>
										<div
											class="w-full bg-[var(--color-accent)]"
											style="height: {point.total_tokens > 0 ? (point.prompt_tokens / point.total_tokens) * 100 : 0}%"
										></div>
										<div
											class="w-full bg-[var(--color-accent-2)]"
											style="height: {point.total_tokens > 0 ? (point.completion_tokens / point.total_tokens) * 100 : 0}%"
										></div>
									</div>
								</div>
								<div class="flex h-8 flex-col items-center justify-end">
									{#if chartBucket === 'month'}
										<span class="text-[0.6rem] font-medium text-[var(--color-ink-2)]">{fmtInt(point.total_tokens)}</span>
									{/if}
									{#if index % Math.ceil(chartPoints.length / 8) === 0 || index === chartPoints.length - 1}
										<span class="w-full truncate text-center text-[0.6rem] text-[var(--color-ink-3)]">
											{fmtChartBucket(point.bucket)}
										</span>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				</div>
				<div class="mt-4 flex items-center gap-4 text-xs text-[var(--color-ink-3)]">
					<span class="flex items-center gap-1.5">
						<span class="inline-block h-2 w-2 rounded-full bg-[var(--color-accent)]"></span>{t('adminStats.inputTokens')}
					</span>
					<span class="flex items-center gap-1.5">
						<span class="inline-block h-2 w-2 rounded-full bg-[var(--color-accent-2)]"></span>{t('adminStats.outputTokens')}
					</span>
				</div>
			{/if}
		</section>


		<!-- 모델별 -->
		<section class="mb-8">
			<h3 class="mb-3 text-sm font-semibold text-[var(--color-ink-1)]">{t('adminStats.modelUsage')}</h3>
			{#if models.length === 0}
				<p class="text-sm text-[var(--color-ink-3)]">{t('adminStats.modelEmpty')}</p>
			{:else}
				<TableShell>
					<table>
						<thead>
							<tr class="text-xs uppercase tracking-wide">
								<th>{t('adminStats.model')}</th>
								<th class="text-right">{t('adminStats.share')}</th>
								<th class="text-right">{t('adminStats.input')}</th>
								<th class="text-right">{t('adminStats.output')}</th>
								<th class="text-right">{t('adminStats.totalTokens')}</th>
								<th class="text-right">{t('adminStats.requests')}</th>
								<th class="text-right">{t('adminStats.credits')}</th>
								<th class="text-right">{t('adminStats.cost')}</th>
								<th class="text-right">{t('adminStats.unpriced')}</th>
							</tr>
						</thead>
						<tbody>
							{#each models as m (m.model_name)}
								<tr>
									<td class="text-sm font-medium text-[var(--color-ink-1)]">{m.model_name}</td>
									<td class="w-32">
										<div class="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
											<div
												class="h-full rounded-full bg-[var(--color-accent)]"
												style="width: {(m.total_tokens / maxModelTokens) * 100}%"
											></div>
										</div>
									</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtInt(m.prompt_tokens)}</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtInt(m.completion_tokens)}</td>
									<td class="text-right text-sm font-medium text-[var(--color-ink-1)]">{fmtInt(m.total_tokens)}</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtInt(m.request_count)}</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtCredit(m.credited_cost)}</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtUsd(m.raw_cost)}</td>
									<td class="text-right text-sm text-[var(--color-state-warning)]">{fmtInt(m.unpriced_requests)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
			{/if}
		</section>

		<!-- 사용자별 -->
		<section>
			{#snippet userUsageNote(text: string)}<span class="text-xs font-normal text-[var(--color-ink-3)]">{text}</span>{/snippet}
			<h3 class="mb-3 text-sm font-semibold text-[var(--color-ink-1)]">
				<RichText segments={t.rich('adminStats.userUsageTitle')} tags={{ note: userUsageNote }} />
			</h3>
			{#if users.length === 0}
				<p class="text-sm text-[var(--color-ink-3)]">{t('adminStats.userEmpty')}</p>
			{:else}
				<TableShell>
					<table>
						<thead>
							<tr class="text-xs uppercase tracking-wide">
								<th>{t('adminStats.user')}</th>
								<th class="text-right">{t('adminStats.input')}</th>
								<th class="text-right">{t('adminStats.output')}</th>
								<th class="text-right">{t('adminStats.totalTokens')}</th>
								<th class="text-right">{t('adminStats.requests')}</th>
								<th class="text-right">{t('adminStats.credits')}</th>
								<th class="text-right">{t('adminStats.cost')}</th>
							</tr>
						</thead>
						<tbody>
							{#each users as u (u.user_id)}
								<tr>
									<td class="text-sm font-medium text-[var(--color-ink-1)]" title={u.user_id}>
										{adminIdentityLabel(u.user_name, u.user_id)}
									</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtInt(u.prompt_tokens)}</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtInt(u.completion_tokens)}</td>
									<td class="text-right text-sm font-medium text-[var(--color-ink-1)]">{fmtInt(u.total_tokens)}</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtInt(u.request_count)}</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtCredit(u.credited_cost)}</td>
									<td class="text-right text-sm text-[var(--color-ink-2)]">{fmtUsd(u.raw_cost)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
				{#if hasMoreUsers}
					<div class="mt-3 flex justify-center">
						<button
							onclick={loadMoreUsers}
							disabled={loadingMore}
							class="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface-raised)] px-4 py-1.5 text-sm text-[var(--color-ink-2)] transition-colors hover:text-[var(--color-ink-0)] disabled:opacity-60"
						>
							{loadingMore ? t('adminStats.loading') : t('adminStats.loadMore')}
						</button>
					</div>
				{/if}
			{/if}
		</section>
	{/if}
</div>
