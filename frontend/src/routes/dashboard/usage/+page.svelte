<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { onDestroy, untrack } from 'svelte';
	import { auth, authReady } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import {
		ActivityIndicator,
		Alert,
		AnimatedNumber,
		EmptyState,
		PageHeader,
		PageShell,
		Pill,
		QuotaBar,
		ResourceToolbar,
		SectionHeader,
		Spark,
		StatusChip,
		ToggleGroup,
	} from '$lib/components/ui';

	interface TopInstance {
		id: string;
		name: string;
		flavor_name: string;
		vcpus: number;
		ram_mb: number;
		disk_gb: number;
		status: string;
		usage_hours: number;
		cpu_pct?: number | null;
		ram_pct?: number | null;
		cpu_source: string | null;
		ram_source: string | null;
		cpu_status: string;
		ram_status: string;
		cpu_native_status: string | null;
		ram_native_status: string | null;
	}

	interface UsageStats {
		range: string;
		top_instances: TopInstance[];
	}

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
		range: '24h' | '7d' | '14d';
	}

	let data = $state<UsageStats | null>(null);
	let trendData = $state<TrendData | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let trendLoading = $state(true);
	let trendError = $state(false);
	let loadGeneration = 0;
	let controller: AbortController | null = null;
	let visibleContext = $state<string | null>(null);
	let initialContext = $state<string | null>(null);
	let period = $state<'24h' | '7d' | '30d'>('7d');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const trendRange = $derived<'24h' | '7d' | '14d'>(period === '30d' ? '14d' : period);
	const context = $derived(JSON.stringify([$authReady, token, $auth.userId, $auth.identityDomainId, projectId, period]));

	async function fetchData() {
		if (!$authReady || !token || !projectId || visibleContext !== context) return;
		const requestToken = token;
		const requestProjectId = projectId;
		const requestPeriod = period;
		const requestTrendRange = trendRange;
		const requestContext = context;
		const generation = ++loadGeneration;
		controller?.abort();
		controller = new AbortController();
		const options = { signal: controller.signal };
		const ownsRequest = () => generation === loadGeneration
			&& context === requestContext && visibleContext === requestContext;
		loading = !data;
		trendLoading = !trendData;
		error = null;
		trendError = false;
		const statsPromise = api.get<UsageStats>(
			`/api/v1/dashboard/usage-stats?range=${requestPeriod}`,
			requestToken,
			requestProjectId,
			options,
		);
		const trendPromise = api.get<TrendData>(
			`/api/v1/dashboard/metrics/trend?range=${requestTrendRange}`,
			requestToken,
			requestProjectId,
			options,
		).then((value) => {
			if (ownsRequest()) trendData = value.range === requestTrendRange ? value : null;
		}).catch(() => {
			if (ownsRequest()) {
				trendData = null;
				trendError = true;
			}
		}).finally(() => {
			if (ownsRequest()) trendLoading = false;
		});
		try {
			const value = await statsPromise;
			if (ownsRequest()) data = value.range === requestPeriod ? value : null;
		} catch (loadError) {
			if (ownsRequest()) error = loadError instanceof Error ? loadError.message : t('usage.loadFailed');
		} finally {
			if (ownsRequest()) loading = false;
		}
		void trendPromise;
	}

	$effect.pre(() => {
		const nextContext = context;
		if (nextContext === visibleContext) return;
		loadGeneration += 1;
		controller?.abort();
		controller = null;
		data = null;
		trendData = null;
		error = null;
		trendError = false;
		loading = true;
		trendLoading = true;
		visibleContext = nextContext;
		initialContext = null;
	});

	$effect(() => {
		const nextContext = context;
		if (!$authReady || !token || !projectId || visibleContext !== nextContext || initialContext === nextContext) return;
		initialContext = nextContext;
		untrack(() => void fetchData());
	});

	onDestroy(() => {
		loadGeneration += 1;
		controller?.abort();
	});

	const ar = createAutoRefresh(fetchData, {
		storageKey: 'dashboard-usage',
		defaultActive: true,
		defaultInterval: 60,
		invokeOnMount: false,
	});

	function isGpu(flavorName: string): boolean {
		const lower = flavorName.toLowerCase();
		return lower.startsWith('g1.') || lower.startsWith('gpu');
	}

	function telemetrySource(source: string): string {
		if (source === 'gnocchi') return t('telemetry.native');
		if (source === 'prometheus') return t('telemetry.fallback');
		if (source === 'mixed') return t('telemetry.mixed');
		return t('telemetry.source', { source });
	}

	function telemetryStatus(status: string): string {
		if (status === 'partial') return t('telemetry.partial');
		if (status === 'not_configured') return t('usage.notConfigured');
		if (status === 'forbidden') return t('telemetry.forbidden');
		if (status === 'unavailable') return t('telemetry.unavailable');
		return t('telemetry.noData');
	}

	function usageValue(value: number | null | undefined, status: string): number | null {
		return value != null && (status === 'available' || status === 'partial') ? value : null;
	}
</script>

	{#snippet usageTelemetry(source: string | null, status: string, nativeStatus: string | null, hasValue: boolean)}
		{#if source}<p class="mt-1 text-xs text-ink-2">{telemetrySource(source)}</p>{/if}
		{#if !hasValue || status !== 'available'}
			<p class="mt-1 text-xs text-ink-2">{telemetryStatus(status)}</p>
		{/if}
		{#if source && source !== 'gnocchi' && nativeStatus && nativeStatus !== 'available'}
			<p class="mt-1 text-xs text-ink-2">{t('telemetry.nativeState', { status: telemetryStatus(nativeStatus) })}</p>
		{/if}
	{/snippet}
<PageShell class="space-y-6">
	<PageHeader breadcrumb={t('usage.breadcrumb')} title={t('usage.title')} subtitle={$auth.projectName ?? '—'} />
	<ResourceToolbar label={t('usage.toolbar')}>
		{#snippet filters()}
			<ToggleGroup
				value={period}
				options={[
					{ value: '24h', label: '24h' },
					{ value: '7d', label: '7d' },
					{ value: '30d', label: '30d' },
				]}
				onchange={(next) => { period = next as typeof period; }}
				ariaLabel={t('usage.period')}
			/>
		{/snippet}
		{#snippet actions()}
			<button
				type="button"
				onclick={() => { ar.active = !ar.active; }}
				class="min-h-8 rounded-md border border-line-2 px-3 text-xs font-medium text-ink-2 transition-colors hover:bg-surface-selected hover:text-ink-0"
				aria-pressed={ar.active}
			>{t(ar.active ? 'usage.autoRefreshOn' : 'usage.autoRefreshOff')}</button>
		{/snippet}
	</ResourceToolbar>

{#key visibleContext}
	{#if loading}
		<LoadingSkeleton variant="table" rows={6} />
	{:else if error}
		<Alert tone="danger">{error}</Alert>
	{:else if data}
		<!-- Observed utilization only; missing telemetry stays empty. -->
		{#if trendData?.scope === 'native_policy'}
			<p class="text-xs text-ink-2">{t('telemetry.nativePolicy')}</p>
		{/if}
		<div class="grid grid-cols-1 sm:grid-cols-4 gap-3.5">
		{#if trendLoading}
			<ActivityIndicator label={t('usage.loadingTrend')} class="sm:col-span-4" />
		{/if}
			{#each [
				{ label: t('usage.vcpuTrend', { range: trendRange }),    unit: '%',     color: 'var(--color-accent)',      key: 'vcpu'    as const },
				{ label: t('usage.ramTrend', { range: trendRange }),      unit: '%',     color: 'var(--color-accent-2)',    key: 'memory'  as const },
				{ label: t('usage.diskTrend', { range: trendRange }), unit: '%', color: 'var(--color-warm)', key: 'storage' as const },
				{ label: t('usage.networkTrend', { range: trendRange }), unit: 'KiB/s', color: 'var(--color-state-info)', key: 'network' as const },
			] as card}
				{@const rawSeries  = trendData?.[card.key]}
				{@const seriesData = rawSeries?.data ?? []}
				{@const displayUnit = card.unit}
				{@const hasData = Boolean(rawSeries?.available && (rawSeries.status === 'available' || rawSeries.status === 'partial') && seriesData.length > 0)}
				{@const current = hasData ? seriesData.at(-1)! : null}
				{@const min     = hasData ? Math.min(...seriesData) : null}
				{@const max     = hasData ? Math.max(...seriesData) : null}
				<div role="group" aria-label={card.label} class="bg-surface-base border border-line rounded-lg p-5 flex flex-col gap-2">
					<div class="flex items-baseline justify-between">
						<p class="text-xs uppercase tracking-wide text-[var(--color-ink-3)]">{card.label}</p>
						{#if current !== null}
							<span class="text-xl font-semibold tabular-nums text-[var(--color-ink-0)]">
								<AnimatedNumber value={current} format={(n) => n.toFixed(1)} /><span class="text-xs text-[var(--color-ink-3)] ml-0.5">{displayUnit}</span>
							</span>
						{/if}
					</div>
					<div class="min-h-[72px] flex items-center">
						{#if hasData}
							<Spark data={seriesData} color={card.color} height={72} class="w-full" />
						{:else if trendLoading}
							<div class="h-[72px] w-full motion-skeleton rounded" aria-hidden="true"></div>
						{:else if trendError}
							<p class="text-xs text-state-danger-text">{t('overview.metricsFailed')}</p>
						{:else if rawSeries}
							<p class="text-xs text-ink-2">{telemetryStatus(rawSeries.status)}</p>
						{:else if trendData && !trendData.monitoring_available}
							<p class="text-xs italic text-ink-2">{t('usage.notConfigured')}</p>
						{:else}
							<p class="text-xs text-ink-2">{t('telemetry.noData')}</p>
						{/if}
					</div>
					{#if rawSeries?.source}
						<p class="text-xs text-ink-2">{telemetrySource(rawSeries.source)}</p>
					{/if}
					{#if hasData && rawSeries?.status === 'partial'}
						<p class="text-xs text-state-warning-text">{t('telemetry.partial')}</p>
					{/if}
					{#if rawSeries?.source && rawSeries.source !== 'gnocchi' && rawSeries.native_status && rawSeries.native_status !== 'available'}
						<p class="text-xs text-ink-2">{t('telemetry.nativeState', { status: telemetryStatus(rawSeries.native_status) })}</p>
					{/if}
					{#if hasData}
						<p class="text-xs tabular-nums text-[var(--color-ink-3)]">
							{t('usage.minMax', { min: min!.toFixed(1), max: max!.toFixed(1), unit: displayUnit })}
						</p>
					{/if}
				</div>
			{/each}
		</div>

		<!-- Top consumers table -->
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<SectionHeader title={t('usage.topInstances')} meta={t('usage.count', { count: data.top_instances.length })} />
			{#if data.top_instances.length === 0}
				<div class="mt-6 text-center text-sm text-ink-2 py-6">{t('usage.empty')}</div>
			{:else}
				<div class="mt-4 overflow-x-auto">
					<table class="w-full text-xs">
						<thead>
							<tr class="border-b border-line">
								<th class="text-left pb-2 text-xs uppercase tracking-wide text-[var(--color-ink-3)] font-medium w-8">#</th>
								<th class="text-left pb-2 text-xs uppercase tracking-wide text-[var(--color-ink-3)] font-medium">{t('usage.instance')}</th>
								<th class="text-left pb-2 text-xs uppercase tracking-wide text-[var(--color-ink-3)] font-medium">{t('usage.flavor')}</th>
								<th class="text-left pb-2 text-xs uppercase tracking-wide text-[var(--color-ink-3)] font-medium w-44">vCPU</th>
								<th class="text-left pb-2 text-xs uppercase tracking-wide text-[var(--color-ink-3)] font-medium w-44">RAM</th>
								<th class="text-left pb-2 text-xs uppercase tracking-wide text-[var(--color-ink-3)] font-medium">{t('usage.status')}</th>
							</tr>
						</thead>
						<tbody class="motion-stagger">
							{#each data.top_instances as inst, i (inst.id)}
								{@const cpuPct = usageValue(inst.cpu_pct, inst.cpu_status)}
								{@const ramPct = usageValue(inst.ram_pct, inst.ram_status)}
								<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
									<td class="py-2.5 text-ink-2 font-mono">{i + 1}</td>
									<td class="py-2.5">
										<div class="flex items-center gap-2">
											<span class="text-ink-0 font-medium truncate max-w-[140px]">{inst.name}</span>
											{#if isGpu(inst.flavor_name)}
												<Pill tone="accent">GPU</Pill>
											{/if}
										</div>
									</td>
									<td class="py-2.5 text-ink-2 font-mono">{inst.flavor_name}</td>
									<td class="py-2.5 pr-4">
										<div class="flex items-center gap-2">
											<span class="tabular-nums text-ink-0 font-medium whitespace-nowrap">{inst.vcpus} vCPU</span>
											<span class="tabular-nums text-[var(--color-ink-3)] w-8 text-right shrink-0">
												{cpuPct !== null ? `${cpuPct.toFixed(0)}%` : '—'}
											</span>
											{#if cpuPct !== null}
												<div class="flex-1 min-w-[48px]">
													<QuotaBar label="" used={cpuPct} limit={100} size="xs" showValue={false} />
												</div>
											{/if}
										</div>
										{@render usageTelemetry(inst.cpu_source, inst.cpu_status, inst.cpu_native_status, cpuPct !== null)}
									</td>
									<td class="py-2.5 pr-4">
										<div class="flex items-center gap-2">
											<span class="tabular-nums text-ink-0 font-medium whitespace-nowrap">{Math.round(inst.ram_mb / 1024)} GB</span>
											<span class="tabular-nums text-[var(--color-ink-3)] w-8 text-right shrink-0">
												{ramPct !== null ? `${ramPct.toFixed(0)}%` : '—'}
											</span>
											{#if ramPct !== null}
												<div class="flex-1 min-w-[48px]">
													<QuotaBar label="" used={ramPct} limit={100} size="xs" showValue={false} />
												</div>
											{/if}
										</div>
										{@render usageTelemetry(inst.ram_source, inst.ram_status, inst.ram_native_status, ramPct !== null)}
									</td>
									<td class="py-2.5">
										<StatusChip status={inst.status} />
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{:else}
		<EmptyState headline={t('usage.noData')} description={t('usage.noDataHelp')} />
	{/if}
{/key}
</PageShell>
