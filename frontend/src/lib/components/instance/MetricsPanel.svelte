<script lang="ts">
	import { untrack } from 'svelte';
	import { api } from '$lib/api/client';
	import { auth } from '$lib/stores/auth';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import GrafanaEmbed from '$lib/components/monitoring/GrafanaEmbed.svelte';

	interface Props {
		instanceId: string;
		isGpu?: boolean;
	}

	type RangeKey = '15m' | '1h' | '6h' | '24h' | '7d';
	type MetricKey = 'cpu' | 'memory' | 'network_rx' | 'network_tx' | 'disk_read' | 'disk_write' | 'gpu_util' | 'gpu_mem';

	interface Series {
		ts: number;
		value: number;
	}

	let { instanceId, isGpu = false }: Props = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	type TabKey = 'chart' | 'grafana';
	let activeTab: TabKey = $state('chart');

	let range: RangeKey = $state('1h');

	const RANGES: RangeKey[] = ['15m', '1h', '6h', '24h', '7d'];
	const RANGE_LABELS: Record<RangeKey, string> = { '15m': '15분', '1h': '1시간', '6h': '6시간', '24h': '24시간', '7d': '7일' };

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

	// --- SVG chart helpers ---
	const SVG_W = 480;
	const SVG_H = 120;
	const PAD_L = 38;
	const PAD_R = 12;
	const PAD_T = 10;
	const PAD_B = 22;

	function chartX(ts: number, minTs: number, tsRange: number): number {
		return PAD_L + ((ts - minTs) / Math.max(1, tsRange)) * (SVG_W - PAD_L - PAD_R);
	}
	function chartY(val: number, maxVal: number): number {
		return PAD_T + (1 - val / Math.max(0.001, maxVal)) * (SVG_H - PAD_T - PAD_B);
	}

	function buildPolyline(pts: Series[], maxVal: number, minTs: number, tsRange: number): string {
		return pts.map(p => `${chartX(p.ts, minTs, tsRange)},${chartY(p.value, maxVal)}`).join(' ');
	}

	function formatBytes(b: number): string {
		if (b >= 1_000_000) return `${(b / 1_000_000).toFixed(1)}MB/s`;
		if (b >= 1_000) return `${(b / 1_000).toFixed(1)}KB/s`;
		return `${b.toFixed(0)}B/s`;
	}

	function latestValue(d: Series[] | null): string {
		if (!d || d.length === 0) return '—';
		return d[d.length - 1].value.toFixed(1);
	}

	function xLabels(pts: Series[], minTs: number, tsRange: number): { ts: number; label: string }[] {
		if (pts.length === 0) return [];
		const step = Math.max(1, Math.floor(pts.length / 4));
		const result: { ts: number; label: string }[] = [];
		for (let i = 0; i < pts.length; i += step) {
			const d = new Date(pts[i].ts * 1000);
			result.push({
				ts: pts[i].ts,
				label: `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`,
			});
		}
		return result;
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
		{ key: 'cpu', title: 'CPU 사용률', color: '#3b82f6', unit: '%', yMax: 100 },
		{ key: 'memory', title: '메모리 사용률', color: '#4ade80', unit: '%', yMax: 100 },
		{ key: 'network_rx', title: '네트워크 I/O', color: '#60a5fa', unit: '', extraKey: 'network_tx', extraColor: '#f87171', formatY: formatBytes },
		{ key: 'disk_read', title: '디스크 I/O', color: '#a78bfa', unit: '', extraKey: 'disk_write', extraColor: '#fbbf24', formatY: formatBytes },
	];

	const GPU_CHARTS: ChartSpec[] = [
		{ key: 'gpu_util', title: 'GPU 사용률', color: '#c084fc', unit: '%', yMax: 100 },
		{ key: 'gpu_mem', title: 'GPU 메모리', color: '#fbbf24', unit: '%', yMax: 100 },
	];

	const activeCharts = $derived(isGpu ? [...CHARTS, ...GPU_CHARTS] : CHARTS);
</script>

<div>
	<!-- 탭 헤더 -->
	<div class="flex items-center justify-between mb-4">
		<div class="flex gap-1">
			<button
				onclick={() => { activeTab = 'chart'; }}
				class="text-xs px-3 py-1 rounded transition-colors {activeTab === 'chart' ? 'bg-action-warm text-ink-0' : 'text-ink-3 hover:text-ink-2 border border-line-2'}"
			>차트</button>
			<button
				onclick={() => { activeTab = 'grafana'; }}
				class="text-xs px-3 py-1 rounded transition-colors {activeTab === 'grafana' ? 'bg-action-warm text-ink-0' : 'text-ink-3 hover:text-ink-2 border border-line-2'}"
			>Grafana</button>
		</div>

		{#if activeTab === 'chart'}
		<div class="flex items-center gap-2">
			<!-- range 토글 -->
			<div class="flex gap-1">
				{#each RANGES as r}
					<button
						onclick={() => { range = r; }}
						class="text-xs px-2 py-0.5 rounded transition-colors {range === r ? 'bg-surface-selected text-ink-0' : 'text-ink-3 hover:text-ink-2'}"
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
		{#each activeCharts as chart}
			{@const m = metrics[chart.key]}
			{@const ex = chart.extraKey ? metrics[chart.extraKey] : null}
			<div class="bg-surface-sunken border border-line-2 rounded-lg p-4">
				<div class="flex items-center justify-between mb-2">
					<span class="text-xs font-semibold text-ink-2">{chart.title}</span>
					{#if m.data && m.data.length > 0}
						<span class="text-sm font-bold text-ink-0">
							{chart.formatY ? chart.formatY(m.data[m.data.length - 1].value) : `${latestValue(m.data)}${chart.unit}`}
						</span>
					{/if}
				</div>

				{#if m.data === null}
					<div class="flex items-center justify-center h-20 text-ink-3 text-xs">로딩 중…</div>
				{:else if m.error}
					<div class="flex items-center justify-center h-20 text-red-500 text-xs">{m.error}</div>
				{:else if m.data.length === 0}
					<div class="flex items-center justify-center h-20 text-ink-3 text-xs">메트릭 없음 (인스턴스 미가동 또는 exporter 미연동)</div>
				{:else}
					{@const pts = m.data}
					{@const exPts = ex?.data ?? []}
					{@const minTs = pts[0].ts}
					{@const tsRange = pts[pts.length - 1].ts - minTs}
					{@const allVals = [...pts.map(p => p.value), ...exPts.map(p => p.value)]}
					{@const maxVal = chart.yMax ?? Math.max(0.001, ...allVals)}
					{@const labels = xLabels(pts, minTs, tsRange)}
					<svg viewBox="0 0 {SVG_W} {SVG_H}" class="w-full" style="height:120px">
						<!-- 그리드 -->
						{#each [0.25, 0.5, 0.75, 1] as frac}
							<line
								x1={PAD_L} y1={chartY(maxVal * frac, maxVal)}
								x2={SVG_W - PAD_R} y2={chartY(maxVal * frac, maxVal)}
								stroke="#374151" stroke-width="1"
							/>
							<text x={PAD_L - 4} y={chartY(maxVal * frac, maxVal) + 3} text-anchor="end" font-size="8" fill="#6b7280">
								{chart.formatY ? chart.formatY(maxVal * frac) : Math.round(maxVal * frac)}
							</text>
						{/each}

						<!-- 메인 영역 채우기 -->
						{#if pts.length > 1}
							<polygon
								points="{chartX(pts[0].ts, minTs, tsRange)},{chartY(0, maxVal)} {buildPolyline(pts, maxVal, minTs, tsRange)} {chartX(pts[pts.length-1].ts, minTs, tsRange)},{chartY(0, maxVal)}"
								fill={chart.color}
								opacity="0.1"
							/>
							<polyline
								points={buildPolyline(pts, maxVal, minTs, tsRange)}
								fill="none"
								stroke={chart.color}
								stroke-width="2"
								stroke-linejoin="round"
								stroke-linecap="round"
							/>
						{/if}

						<!-- 추가 라인 (network_tx / disk_write) -->
						{#if chart.extraKey && exPts.length > 1}
							<polyline
								points={buildPolyline(exPts, maxVal, minTs, tsRange)}
								fill="none"
								stroke={chart.extraColor}
								stroke-width="1.5"
								stroke-dasharray="4 2"
								opacity="0.8"
							/>
						{/if}

						<!-- X축 레이블 -->
						{#each labels as lbl}
							<text x={chartX(lbl.ts, minTs, tsRange)} y={SVG_H - 4} text-anchor="middle" font-size="8" fill="#6b7280">
								{lbl.label}
							</text>
						{/each}
					</svg>

					<!-- 범례 (이중 라인일 때만) -->
					{#if chart.extraKey}
						<div class="flex gap-3 mt-1">
							<div class="flex items-center gap-1">
								<div class="w-4 h-0.5" style="background:{chart.color}"></div>
								<span class="text-xs text-ink-3">rx / read</span>
							</div>
							<div class="flex items-center gap-1">
								<div class="w-4 h-0.5 border-t border-dashed" style="border-color:{chart.extraColor}"></div>
								<span class="text-xs text-ink-3">tx / write</span>
							</div>
						</div>
					{/if}
				{/if}

				<!-- 통계 요약 행 (min / avg / max) -->
				{#if summaryStats[chart.key]}
					{@const s = summaryStats[chart.key]}
					<div class="flex gap-4 mt-2 pt-2 border-t border-line-2/60 text-[11px] text-ink-3">
						<span>최소 <span class="text-ink-2 font-medium">{s.min != null ? (chart.formatY ? chart.formatY(s.min) : `${s.min.toFixed(1)}${chart.unit}`) : '—'}</span></span>
						<span>평균 <span class="text-ink-2 font-medium">{s.avg != null ? (chart.formatY ? chart.formatY(s.avg) : `${s.avg.toFixed(1)}${chart.unit}`) : '—'}</span></span>
						<span>최대 <span class="text-ink-2 font-medium">{s.max != null ? (chart.formatY ? chart.formatY(s.max) : `${s.max.toFixed(1)}${chart.unit}`) : '—'}</span></span>
					</div>
				{/if}
			</div>
		{/each}
	</div>
	{/if}
</div>
