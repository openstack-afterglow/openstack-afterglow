<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { api } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import RichText from '$lib/i18n/RichText.svelte';
	import { ActivityIndicator, AnimatedNumber, Button } from '$lib/components/ui';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import type { ChartDatum, ChartSpec as BklitSpec } from '$lib/components/charts/types';

	interface Props {
		instanceId: string;
		isGpu?: boolean;
		projectId?: string;
	}

	type RangeKey = '15m' | '1h' | '6h' | '24h' | '7d';
	type MetricKey = 'cpu' | 'memory' | 'network_rx' | 'network_tx' | 'disk_read' | 'disk_write' | 'gpu_util' | 'gpu_mem' | 'disk_read_iops' | 'disk_write_iops' | 'network_rx_packets' | 'network_tx_packets' | 'memory_resident' | 'disk_allocation' | 'memory_swap_in' | 'memory_swap_out';

	interface Series {
		ts: number;
		value: number | null;
	}

	let { instanceId, isGpu = false, projectId: instanceProjectId }: Props = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived(instanceProjectId ?? $auth.projectId ?? undefined);
	let authEpoch = $state(0);
	const unsubscribeAuth = auth.subscribe(() => { authEpoch += 1; });
	let generation = 0;
	onDestroy(() => { unsubscribeAuth(); generation += 1; });

	type TabKey = 'chart' | 'grafana';
	let activeTab: TabKey = $state('chart');

	let range: RangeKey = $state('1h');
	const context = $derived(`${authEpoch}:${projectId}:${instanceId}:${range}:${isGpu}`);
	let metricsContext = $state('');

	const RANGES: RangeKey[] = ['15m', '1h', '6h', '24h', '7d'];
	const RANGE_LABELS: Record<RangeKey, string> = $derived({ '15m': t('metrics.range15m'), '1h': t('metrics.range1h'), '6h': t('metrics.range6h'), '24h': t('metrics.range24h'), '7d': t('metrics.range7d') });

	type Metadata = { source?: string | null; unit?: string; status?: string; native_status?: string | null };
	type MetricState = Metadata & { data: Series[] | null; error: string | null };
	type MetricResponse = Metadata & { series: Series[]; error: string | null };
	const baseMetrics: MetricKey[] = ['cpu', 'memory', 'network_rx', 'network_tx', 'disk_read', 'disk_write'];
	const gpuMetrics: MetricKey[] = ['gpu_util', 'gpu_mem'];
	const nativeMetrics: MetricKey[] = ['disk_read_iops', 'disk_write_iops', 'network_rx_packets', 'network_tx_packets', 'memory_resident', 'disk_allocation', 'memory_swap_in', 'memory_swap_out'];
	function emptyMetrics(): Record<string, MetricState> {
		return Object.fromEntries([...baseMetrics, ...gpuMetrics, ...nativeMetrics].map((key) => [key, { data: null, error: null }]));
	}
	let metrics: Record<string, MetricState> = $state(emptyMetrics());
	type StatInfo = Metadata & { min: number | null; avg: number | null; max: number | null };
	let summaryStats: Record<string, StatInfo> = $state({});
	let showNative = $state(false);

	async function loadAll() {
		const request = { token, projectId, instanceId, range, isGpu, epoch: authEpoch, generation: ++generation };
		const current = () => request.generation === generation && request.token === token
			&& request.projectId === projectId && request.instanceId === instanceId && request.range === range
			&& request.isGpu === isGpu && request.epoch === authEpoch;
		if (!request.token || !request.projectId || !request.instanceId) return;
		const keys = [...baseMetrics, ...nativeMetrics, ...(request.isGpu ? gpuMetrics : [])];
		void api.get<{ monitoring_available: boolean; stats: Record<string, StatInfo> }>(
			`/api/v1/instances/${request.instanceId}/metrics-summary?range=${request.range}`,
			request.token, request.projectId,
		).then((resp) => {
			if (current()) summaryStats = resp.monitoring_available ? resp.stats : {};
		}).catch(() => { if (current()) summaryStats = {}; });
		try {
			const resp = await api.get<{ metrics: Record<string, MetricResponse> }>(
				`/api/v1/instances/${request.instanceId}/metrics-batch?metrics=${keys.join(',')}&range=${request.range}`,
				request.token, request.projectId,
			);
			if (!current()) return;
			for (const key of keys) {
				const result = resp.metrics[key];
				metrics[key] = result ? { ...result, data: result.series } : { data: [], error: null, status: 'not_collected' };
			}
		} catch (e: unknown) {
			if (!current()) return;
			const error = e instanceof Error ? e.message : String(e);
			for (const key of keys) metrics[key] = { data: [], error, status: 'unavailable' };
		}
	}

	const storageKey = untrack(() => instanceId);
	const ar = createAutoRefresh(loadAll, {
		storageKey: `instance-${storageKey}-metrics`,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60],
	});

	$effect(() => {
		void token; void projectId; void instanceId; void range; void isGpu; void authEpoch;
		untrack(() => {
			generation += 1;
			metrics = emptyMetrics();
			metricsContext = context;
			summaryStats = {};
			void loadAll();
		});
	});


	function formatBytes(b: number): string {
		if (b >= 1_000_000) return `${(b / 1_000_000).toFixed(1)}MB/s`;
		if (b >= 1_000) return `${(b / 1_000).toFixed(1)}KB/s`;
		return `${b.toFixed(0)}B/s`;
	}


	interface ChartSpec {
		key: MetricKey;
		title: string;
		color: string;
		unit: string;
		yMax?: number;
		extraKey?: MetricKey;
		extraColor?: string;
	}

	const CHARTS: ChartSpec[] = [
		{ key: 'cpu', get title() { return t('metrics.cpuUsage'); }, color: 'var(--color-accent)', unit: '%', yMax: 100 },
		{ key: 'memory', get title() { return t('metrics.memoryUsage'); }, color: 'var(--color-state-success)', unit: '%', yMax: 100 },
		{ key: 'network_rx', get title() { return t('metrics.networkIo'); }, color: 'var(--color-accent)', unit: 'B/s', extraKey: 'network_tx', extraColor: 'var(--color-state-danger)' },
		{ key: 'disk_read', get title() { return t('metrics.diskIo'); }, color: 'var(--color-accent-2)', unit: 'B/s', extraKey: 'disk_write', extraColor: 'var(--color-state-warning)' },
	];

	const GPU_CHARTS: ChartSpec[] = [
		{ key: 'gpu_util', get title() { return t('metrics.gpuUsage'); }, color: 'var(--color-accent-2)', unit: '%', yMax: 100 },
		{ key: 'gpu_mem', get title() { return t('metrics.gpuMemory'); }, color: 'var(--color-state-warning)', unit: '%', yMax: 100 },
	];

	const NATIVE_CHARTS: ChartSpec[] = [
		{ key: 'disk_read_iops', get title() { return t('metrics.diskIops'); }, color: 'var(--color-accent-2)', unit: 'request/s', extraKey: 'disk_write_iops', extraColor: 'var(--color-state-warning)' },
		{ key: 'network_rx_packets', get title() { return t('metrics.networkPackets'); }, color: 'var(--color-accent)', unit: 'packet/s', extraKey: 'network_tx_packets', extraColor: 'var(--color-state-danger)' },
		{ key: 'memory_resident', get title() { return t('metrics.memoryResident'); }, color: 'var(--color-state-success)', unit: 'MiB' },
		{ key: 'disk_allocation', get title() { return t('metrics.diskAllocation'); }, color: 'var(--color-accent-2)', unit: 'B' },
		{ key: 'memory_swap_in', get title() { return t('metrics.swapIn'); }, color: 'var(--color-accent)', unit: 'MiB/s' },
		{ key: 'memory_swap_out', get title() { return t('metrics.swapOut'); }, color: 'var(--color-state-warning)', unit: 'MiB/s' },
	];
	const activeCharts = $derived([...CHARTS, ...(isGpu ? GPU_CHARTS : []), ...(showNative ? NATIVE_CHARTS : [])]);

	function formatMetric(chart: ChartSpec, metadata: Metadata, value: number): string {
		const unit = metadata.unit ?? chart.unit;
		if (unit === 'B/s') return formatBytes(value);
		return `${value.toFixed(1)}${unit === '%' ? '' : ' '}${unit}`;
	}
	function statusLabel(status: string | null | undefined): string {
		return t('metrics.status', { status: status ?? 'unknown' });
	}
	function metricDescription(metadata: Metadata, unit: string): string {
		const source = metadata.source ?? t('metrics.noSource');
		const fallback = metadata.source && metadata.source !== 'gnocchi' && metadata.native_status
			? ` · ${t('metrics.fallback')}` : '';
		const native = metadata.native_status ? ` · Gnocchi: ${statusLabel(metadata.native_status)}` : '';
		return `${source}${fallback} · ${statusLabel(metadata.status)} · ${metadata.unit ?? unit}${native}`;
	}
	function hasValues(samples: Series[] | null | undefined): boolean {
		return samples?.some((sample) => sample.value != null && Number.isFinite(sample.value)) ?? false;
	}

	function metricChart(chart: ChartSpec, primary: Series[], extra: Series[]): BklitSpec {
		const rows = new Map<number, ChartDatum>();
		let maximum = 0.001;
		function add(samples: Series[], key: string) {
			for (const sample of samples) {
				if (!Number.isFinite(sample.ts)) continue;
				const time = sample.ts * 1000;
				const row = rows.get(time) ?? { time };
				const value = sample.value;
				row[key] = typeof value === 'number' && Number.isFinite(value) ? value : null;
				if (typeof value === 'number' && Number.isFinite(value)) maximum = Math.max(maximum, value);
				rows.set(time, row);
			}
		}
		add(primary, chart.key);
		if (chart.extraKey) add(extra, chart.extraKey);
		const data = [...rows.values()].sort((a, b) => Number(a.time) - Number(b.time));
		return {
			kind: 'time-series',
			data,
			xKey: 'time',
			series: [
				{ key: chart.key, label: chart.extraKey ? t('metrics.readLegend') : chart.title, color: chart.color, area: true, data: data.filter((row) => Object.hasOwn(row, chart.key)) },
				...(chart.extraKey ? [{ key: chart.extraKey, label: t('metrics.writeLegend'), color: chart.extraColor ?? chart.color, dashed: true, data: data.filter((row) => Object.hasOwn(row, chart.extraKey!)) }] : []),
			],
			domain: [0, chart.yMax ?? maximum],
			formatValue: (value) => formatMetric(chart, metrics[chart.key], value),
		};
	}
</script>

<div>
	<!-- 탭 헤더 -->
	<div class="flex flex-wrap items-center justify-between gap-3 mb-4">
		<div class="flex gap-1">
			<button
				onclick={() => { activeTab = 'chart'; }}
				class="text-xs px-3 py-1 rounded transition-colors {activeTab === 'chart' ? 'bg-action-warm text-ink-0' : 'text-ink-2 hover:text-ink-2 border border-line-2'}"
			>{t('metrics.chart')}</button>
			<button
				onclick={() => { activeTab = 'grafana'; }}
				class="text-xs px-3 py-1 rounded transition-colors {activeTab === 'grafana' ? 'bg-action-warm text-ink-0' : 'text-ink-2 hover:text-ink-2 border border-line-2'}"
			>Grafana</button>
		</div>

		{#if activeTab === 'chart'}
		<div class="flex flex-wrap items-center gap-2">
			<!-- range 토글 -->
			<div class="flex flex-wrap gap-1">
				{#each RANGES as r}
					<button
						onclick={() => { range = r; }}
						class="text-xs px-2 py-0.5 rounded transition-colors {range === r ? 'bg-surface-selected text-ink-0' : 'text-ink-2 hover:text-ink-2'}"
					>{RANGE_LABELS[r]}</button>
				{/each}
			</div>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				onManualRefresh={loadAll}
			/>
		</div>
		{/if}
	</div>

	{#if activeTab === 'grafana'}
		{#key context}
		<GrafanaEmbed
			dashboardKey={isGpu ? 'instance-gpu' : 'instance-cpu'}
			vars={{ uuid: instanceId }}
			height={520}
			desktopHeight={700}
		/>
		{/key}
	{:else if metricsContext !== context}
		<ActivityIndicator label={t('metrics.loading')} />
	{:else}
	<div class="mb-4 space-y-2">
		<Button variant="secondary" size="sm" ariaExpanded={showNative} onclick={() => { showNative = !showNative; }}>{t('metrics.nativeMeasurements')}</Button>
		{#if showNative}<p class="text-xs text-ink-2">{t('metrics.nativeMeasurementsHelp')}</p>{/if}
	</div>
	<div class="grid grid-cols-1 @3xl/panel:grid-cols-2 gap-4">
		{#each activeCharts as chart (chart.key)}
			{@const m = metrics[chart.key]}
			{@const ex = chart.extraKey ? metrics[chart.extraKey] : null}
			<div class="bg-surface-sunken border border-line-2 rounded-lg p-4">
				<div class="flex items-center justify-between mb-2">
					<span class="text-xs font-semibold text-ink-2">{chart.title}</span>
					{#if m.data && m.data.length > 0}
						{@const latest = m.data[m.data.length - 1].value}
						<span class="text-sm font-bold text-ink-0">
							{#if latest != null && Number.isFinite(latest)}
								<AnimatedNumber value={latest} format={(value) => formatMetric(chart, m, value)} />
							{:else}—{/if}
						</span>
					{/if}
				</div>
				<div class="mb-2 space-y-1 text-xs text-ink-2 break-words" aria-live="polite">
					<p>{chart.extraKey ? `${t('metrics.readLegend')}: ` : ''}{metricDescription(m, chart.unit)}</p>
					{#if ex}<p>{t('metrics.writeLegend')}: {metricDescription(ex, chart.unit)}</p>{/if}
				</div>

				{#if m.data === null}
					<div class="flex items-center justify-center h-20"><ActivityIndicator label={t('metrics.loading')} /></div>
				{:else if !hasValues(m.data) && !hasValues(ex?.data)}
					<div class="flex items-center justify-center h-20 text-ink-2 text-xs">{m.status === 'not_collected' ? t('metrics.empty') : m.error ?? t('metrics.empty')}</div>
				{:else}
					<BklitChart spec={metricChart(chart, m.data, ex?.data ?? [])} height={120} label={chart.title} />

					<!-- 범례 (이중 라인일 때만) -->
					{#if chart.extraKey}
						<div class="flex gap-3 mt-1">
							<div class="flex items-center gap-1">
								<div class="w-4 h-0.5" style="background:{chart.color}"></div>
								<span class="text-xs text-ink-2">{t('metrics.readLegend')}</span>
							</div>
							<div class="flex items-center gap-1">
								<div class="w-4 h-0.5 border-t border-dashed" style="border-color:{chart.extraColor}"></div>
								<span class="text-xs text-ink-2">{t('metrics.writeLegend')}</span>
							</div>
						</div>
					{/if}
				{/if}

				<!-- 통계 요약 행 (min / avg / max) -->
				{#if summaryStats[chart.key]}
					{@const s = summaryStats[chart.key]}
					<div class="flex flex-wrap gap-4 mt-2 pt-2 border-t border-line-2/60 text-xs text-ink-2">
						{#snippet statValue(value: number | null)}<strong class="text-ink-2 font-medium">{#if value != null && Number.isFinite(value)}<AnimatedNumber {value} format={(v) => formatMetric(chart, s, v)} />{:else}—{/if}</strong>{/snippet}
						{#snippet statMin(_text: string)}{@render statValue(s.min)}{/snippet}
						{#snippet statAvg(_text: string)}{@render statValue(s.avg)}{/snippet}
						{#snippet statMax(_text: string)}{@render statValue(s.max)}{/snippet}
						<span><RichText segments={t.rich('metrics.minimum', { value: '' })} tags={{ strong: statMin }} /></span>
						<span><RichText segments={t.rich('metrics.average', { value: '' })} tags={{ strong: statAvg }} /></span>
						<span><RichText segments={t.rich('metrics.maximum', { value: '' })} tags={{ strong: statMax }} /></span>
						<span>{metricDescription(s, chart.unit)}</span>
					</div>
				{/if}
			</div>
		{/each}
	</div>
	{/if}
</div>
