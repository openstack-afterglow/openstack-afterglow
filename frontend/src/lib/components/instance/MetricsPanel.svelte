<script lang="ts">
	import { untrack } from 'svelte';
	import { api } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';
	import { t } from '$lib/i18n/ns/instance';
	import RichText from '$lib/i18n/RichText.svelte';
	import { ActivityIndicator, AnimatedNumber } from '$lib/components/ui';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import type { ChartDatum, ChartSpec as BklitSpec } from '$lib/components/charts/types';

	interface Props {
		instanceId: string;
		isGpu?: boolean;
	}

	type RangeKey = '15m' | '1h' | '6h' | '24h' | '7d';
	type MetricKey = 'cpu' | 'memory' | 'network_rx' | 'network_tx' | 'disk_read' | 'disk_write' | 'gpu_util' | 'gpu_mem';

	interface Series {
		ts: number;
		value: number | null;
	}

	let { instanceId, isGpu = false }: Props = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	type TabKey = 'chart' | 'grafana';
	let activeTab: TabKey = $state('chart');

	let range: RangeKey = $state('1h');

	const RANGES: RangeKey[] = ['15m', '1h', '6h', '24h', '7d'];
	const RANGE_LABELS: Record<RangeKey, string> = $derived({ '15m': t('metrics.range15m'), '1h': t('metrics.range1h'), '6h': t('metrics.range6h'), '24h': t('metrics.range24h'), '7d': t('metrics.range7d') });

	type MetricState = { data: Series[] | null; error: string | null };

	let metrics: Record<string, MetricState> = $state({
		cpu: { data: null, error: null },
		memory: { data: null, error: null },
		network_rx: { data: null, error: null },
		network_tx: { data: null, error: null },
		disk_read: { data: null, error: null },
		disk_write: { data: null, error: null },
		gpu_util: { data: null, error: null },
		gpu_mem: { data: null, error: null },
	});

	const baseMetrics: MetricKey[] = ['cpu', 'memory', 'network_rx', 'network_tx', 'disk_read', 'disk_write'];
	const gpuMetrics: MetricKey[] = ['gpu_util', 'gpu_mem'];

	// 통계 요약 (min/avg/max) — metrics-summary 엔드포인트
	type StatInfo = { min: number | null; avg: number | null; max: number | null };
	let summaryStats: Record<string, StatInfo> = $state({});

	async function loadSummary() {
		if (!token || !projectId) return;
		try {
			const resp = await api.get<{
				prometheus_available: boolean;
				stats: Record<string, StatInfo>;
			}>(
				`/api/v1/instances/${instanceId}/metrics-summary?range=${range}`,
				token,
				projectId,
			);
			summaryStats = resp.prometheus_available ? resp.stats : {};
		} catch {
			summaryStats = {};
		}
	}

	async function loadAll() {
		if (!token) return;
		const keys: MetricKey[] = isGpu ? [...baseMetrics, ...gpuMetrics] : baseMetrics;
		// summary는 차트와 독립적으로 로드 (실패해도 차트 미영향)
		void loadSummary();
		try {
			const resp = await api.get<{
				metrics: Record<string, { series: Series[]; error: string | null }>;
			}>(
				`/api/v1/instances/${instanceId}/metrics-batch?metrics=${keys.join(',')}&range=${range}`,
				token,
				projectId,
			);
			for (const k of keys) {
				const r = resp.metrics[k];
				metrics[k] = r ? { data: r.series, error: r.error } : { data: [], error: null };
			}
		} catch (e: unknown) {
			const msg = e instanceof Error ? e.message : String(e);
			for (const k of keys) metrics[k] = { data: [], error: msg };
		}
	}

	const storageKey = untrack(() => instanceId);
	const ar = createAutoRefresh(loadAll, {
		storageKey: `instance-${storageKey}-metrics`,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60],
	});

	// reload when range changes
	$effect(() => {
		void range;
		loadAll();
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
		formatY?: (v: number) => string;
	}

	const CHARTS: ChartSpec[] = [
		{ key: 'cpu', get title() { return t('metrics.cpuUsage'); }, color: 'var(--color-accent)', unit: '%', yMax: 100 },
		{ key: 'memory', get title() { return t('metrics.memoryUsage'); }, color: 'var(--color-state-success)', unit: '%', yMax: 100 },
		{ key: 'network_rx', get title() { return t('metrics.networkIo'); }, color: 'var(--color-accent)', unit: '', extraKey: 'network_tx', extraColor: 'var(--color-state-danger)', formatY: formatBytes },
		{ key: 'disk_read', get title() { return t('metrics.diskIo'); }, color: 'var(--color-accent-2)', unit: '', extraKey: 'disk_write', extraColor: 'var(--color-state-warning)', formatY: formatBytes },
	];

	const GPU_CHARTS: ChartSpec[] = [
		{ key: 'gpu_util', get title() { return t('metrics.gpuUsage'); }, color: 'var(--color-accent-2)', unit: '%', yMax: 100 },
		{ key: 'gpu_mem', get title() { return t('metrics.gpuMemory'); }, color: 'var(--color-state-warning)', unit: '%', yMax: 100 },
	];

	const activeCharts = $derived(isGpu ? [...CHARTS, ...GPU_CHARTS] : CHARTS);

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
			formatValue: chart.formatY ?? ((value) => `${value.toFixed(1)}${chart.unit}`),
		};
	}
</script>

<div>
	<!-- 탭 헤더 -->
	<div class="flex items-center justify-between mb-4">
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
		<div class="flex items-center gap-2">
			<!-- range 토글 -->
			<div class="flex gap-1">
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
		<GrafanaEmbed
			dashboardKey={isGpu ? 'instance-gpu' : 'instance-cpu'}
			vars={{ uuid: instanceId }}
			height={520}
			desktopHeight={700}
		/>
	{:else}
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
								<AnimatedNumber value={latest} format={chart.formatY ?? ((value) => `${value.toFixed(1)}${chart.unit}`)} />
							{:else}—{/if}
						</span>
					{/if}
				</div>

				{#if m.data === null}
					<div class="flex items-center justify-center h-20"><ActivityIndicator label={t('metrics.loading')} /></div>
				{:else if m.error}
					<div class="flex items-center justify-center h-20 text-red-500 text-xs">{m.error}</div>
				{:else if m.data.length === 0}
					<div class="flex items-center justify-center h-20 text-ink-2 text-xs">{t('metrics.empty')}</div>
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
					<div class="flex gap-4 mt-2 pt-2 border-t border-line-2/60 text-xs text-ink-2">
						{#snippet statValue(value: number | null)}<strong class="text-ink-2 font-medium">{#if value != null}<AnimatedNumber {value} format={chart.formatY ?? ((v) => `${v.toFixed(1)}${chart.unit}`)} />{:else}—{/if}</strong>{/snippet}
						{#snippet statMin(_text: string)}{@render statValue(s.min)}{/snippet}
						{#snippet statAvg(_text: string)}{@render statValue(s.avg)}{/snippet}
						{#snippet statMax(_text: string)}{@render statValue(s.max)}{/snippet}
						<span><RichText segments={t.rich('metrics.minimum', { value: '' })} tags={{ strong: statMin }} /></span>
						<span><RichText segments={t.rich('metrics.average', { value: '' })} tags={{ strong: statAvg }} /></span>
						<span><RichText segments={t.rich('metrics.maximum', { value: '' })} tags={{ strong: statMax }} /></span>
					</div>
				{/if}
			</div>
		{/each}
	</div>
	{/if}
</div>
