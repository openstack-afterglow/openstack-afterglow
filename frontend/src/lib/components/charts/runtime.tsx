import { createRoot } from 'react-dom/client';
import { useMemo, type CSSProperties, type ReactNode } from 'react';
import { MotionConfig } from 'motion/react';
import { LineChart, Line } from '$lib/vendor/bklit-ui/charts/line-chart';
import { AreaChart, Area } from '$lib/vendor/bklit-ui/charts/area-chart';
import { BarChart } from '$lib/vendor/bklit-ui/charts/bar-chart';
import { Bar } from '$lib/vendor/bklit-ui/charts/bar';
import { BarXAxis } from '$lib/vendor/bklit-ui/charts/bar-x-axis';
import { BarYAxis } from '$lib/vendor/bklit-ui/charts/bar-y-axis';
import { RingChart } from '$lib/vendor/bklit-ui/charts/ring-chart';
import { Ring } from '$lib/vendor/bklit-ui/charts/ring';
import { Gauge } from '$lib/vendor/bklit-ui/charts/gauge';
import { XAxis } from '$lib/vendor/bklit-ui/charts/x-axis';
import { YAxis } from '$lib/vendor/bklit-ui/charts/y-axis';
import { ChartTooltip } from '$lib/vendor/bklit-ui/charts/tooltip/chart-tooltip';
import { TooltipContent } from '$lib/vendor/bklit-ui/charts/tooltip/tooltip-content';
import { ChartHostProvider } from '$lib/vendor/bklit-ui/charts/host-config';
import { StaticChartPreviewProvider } from '$lib/vendor/bklit-ui/charts/static-chart-preview-context';
import type { ChartDatum, ChartSpec, ChartRenderOptions, ChartMount } from './types';
import { ChoroplethMap } from './runtime-map';

type SeriesSpec = Extract<ChartSpec, { kind: 'time-series' | 'bar' }>;
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const clampPercent = (value: number) => isNumber(value) ? Math.max(0, Math.min(100, value)) : 0;

/** Normalization never mutates API rows; missing/nonfinite observations remain null. */
function normalizeRows(rows: ChartDatum[], spec: SeriesSpec): Record<string, unknown>[] {
	const normalized = rows.filter((row) => spec.kind !== 'time-series' || isNumber(row[spec.xKey])).map((row) => {
		const next: Record<string, unknown> = { ...row };
		for (const series of spec.series) next[series.key] = isNumber(row[series.key]) ? row[series.key] : null;
		return next;
	});
	if (spec.kind === 'time-series') normalized.sort((a, b) => (a[spec.xKey] as number) - (b[spec.xKey] as number));
	return normalized;
}

function SeriesChart({ spec, options }: { spec: SeriesSpec; options: ChartRenderOptions }) {
	const data = useMemo(() => normalizeRows(spec.data, spec), [spec]);
	const seriesData = useMemo(() => spec.series.map((series) => series.data ? normalizeRows(series.data, spec) : undefined), [spec]);
	const hasGaps = data.some((row) => spec.series.some((series) => !isNumber(row[series.key])));
	const numberFormat = useMemo(() => new Intl.NumberFormat(options.locale, { maximumFractionDigits: 2 }), [options.locale]);
	const dateFormat = useMemo(() => new Intl.DateTimeFormat(options.locale, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }), [options.locale]);
	const span = spec.kind === 'time-series' && data.length > 1 ? Number(data.at(-1)?.[spec.xKey]) - Number(data[0][spec.xKey]) : 0;
	const axisDateFormat = useMemo(() => new Intl.DateTimeFormat(options.locale, span >= 86_400_000
		? { month: 'short', day: 'numeric', ...(span >= 366 * 86_400_000 ? { year: 'numeric' as const } : {}) }
		: { hour: '2-digit', minute: '2-digit' }), [options.locale, span]);
	const formatValue = spec.formatValue ?? ((value: number) => numberFormat.format(value));
	const formatTime = spec.kind === 'time-series' ? spec.formatTime ?? ((value: number) => axisDateFormat.format(value)) : undefined;
	const formatTooltipTime = spec.kind === 'time-series' ? spec.formatTime ?? ((value: number) => dateFormat.format(value)) : undefined;
	const tooltip = spec.tooltips ?? !spec.compact;
	const rows = (point: Record<string, unknown>) => spec.series.filter((series) => isNumber(point[series.key])).map((series) => ({ color: series.color, label: series.label, value: formatValue(point[series.key] as number) }));
	const nativeTooltip = tooltip ? <ChartTooltip
		showDatePill={false}
		showDots={!hasGaps && !options.reducedMotion && spec.kind === 'time-series'}
		damping={options.reducedMotion ? 0 : undefined}
		rows={rows}
		content={({ point }) => <TooltipContent
			title={formatTooltipTime && isNumber(point[spec.xKey]) ? formatTooltipTime(point[spec.xKey] as number) : spec.kind === 'bar' && spec.formatCategory ? spec.formatCategory(String(point[spec.xKey] ?? ''), 'detail') : String(point[spec.xKey] ?? '')}
			rows={rows(point)}
		/>}
	/> : null;
	const margin = spec.compact ? { top: 0, right: 0, bottom: 0, left: 0 } : { top: 12, right: 16, bottom: 32, left: spec.kind === 'bar' && spec.orientation === 'horizontal' ? 88 : 80 };
	let plot: ReactNode;
	if (spec.kind === 'bar') {
		plot = <BarChart data={data} xDataKey={spec.xKey} orientation={spec.orientation} stacked={spec.stacked}
			margin={margin} aspectRatio="" className={tooltip ? 'h-full' : 'h-full pointer-events-none'} animationDuration={options.reducedMotion ? 0 : 500}
			barGap={spec.compact ? 0 : undefined} stackGap={0}
			enterTransition={options.reducedMotion ? { duration: 0, delay: 0 } : undefined}>
			{spec.series.map((series) => <Bar key={series.key} dataKey={series.key} fill={series.color} stroke={series.color}
				animate={!options.reducedMotion} fadedOpacity={1} lineCap="butt" groupGap={spec.compact ? 0 : undefined} />)}
			{!spec.compact && (spec.orientation === 'horizontal' ? <><BarYAxis /><YAxis formatValue={formatValue} /></> : <><BarXAxis formatLabel={spec.formatCategory ? value => spec.formatCategory!(value, 'axis') : undefined} /><YAxis formatValue={formatValue} /></>)}
			{nativeTooltip}
		</BarChart>;
	} else {
		const Chart = spec.series.some((series) => series.area) ? AreaChart : LineChart;
		plot = <Chart data={data} xDataKey={spec.xKey} margin={margin} aspectRatio=""
			style={{ height: options.height, ...(!tooltip ? { pointerEvents: 'none' as const, touchAction: 'pan-y' as const } : {}) }} animationDuration={options.reducedMotion ? 0 : 500}
			yDomainTween={!options.reducedMotion && !spec.domain} yDomainTweenDuration={options.reducedMotion ? 0 : 250}>
			{spec.series.map((series, index) => {
				const source = seriesData[index];
				const animate = !options.reducedMotion && !hasGaps && !source;
				const common = { dataKey: series.key, data: source, stroke: series.color, strokeWidth: spec.compact ? 1.5 : 2, animate,
					fadeEdges: false, showHighlight: tooltip && !hasGaps && !source && !options.reducedMotion, loading: false,
					dashFromIndex: series.dashed ? 0 : undefined };
				return series.area ? <Area key={series.key} {...common} fill={series.color} fillOpacity={0.18} /> : <Line key={series.key} {...common} />;
			})}
			{!spec.compact && <><XAxis tickMode="data" /><YAxis formatValue={formatValue} /></>}
			{nativeTooltip}
		</Chart>;
	}
	return <ChartHostProvider value={{ yDomain: spec.domain, formatTime, reducedMotion: options.reducedMotion }}>
		{options.reducedMotion ? <StaticChartPreviewProvider>{plot}</StaticChartPreviewProvider> : plot}
	</ChartHostProvider>;
}

function ChartView({ spec, options }: { spec: ChartSpec; options: ChartRenderOptions }) {
	let plot: ReactNode;
	if (spec.kind === 'choropleth') {
		plot = <ChoroplethMap spec={spec} options={options} />;
	} else if (spec.kind === 'ring') {
		const percent = isNumber(spec.max) && spec.max > 0 && isNumber(spec.value) ? clampPercent(spec.value / spec.max * 100) : 0;
		plot = <div style={{ '--border': spec.track ?? 'var(--color-line)', width: spec.size, height: spec.size } as CSSProperties}>
			<RingChart data={[{ label: '', value: percent, maxValue: 100, color: spec.color }]} size={spec.size}
				strokeWidth={spec.stroke} baseInnerRadius={Math.max(0, spec.size / 2 - spec.stroke)} padding={0}
				ringGap={0} hoveredIndex={null} enterTransition={options.reducedMotion ? { duration: 0, delay: 0 } : undefined}>
				<Ring index={0} color={spec.color} showGlow={false} animate={!options.reducedMotion} />
			</RingChart>
		</div>;
	} else if (spec.kind === 'gauge') {
		plot = <Gauge orientation="linear" continuous value={clampPercent(spec.value)} activeFill={spec.color}
			inactiveFill={spec.track ?? 'var(--color-line)'} activeFillOpacity={1} inactiveFillOpacity={1}
			linearHeight={options.height} minWidth={0} uniformWidth notchCornerRadius={0}
			geometryScrubbing={options.reducedMotion} enterTransition={options.reducedMotion ? { duration: 0, delay: 0 } : undefined} />;
	} else {
		plot = <SeriesChart spec={spec} options={options} />;
	}
	return <MotionConfig reducedMotion={options.reducedMotion ? 'always' : 'never'}>
		<ChartHostProvider value={{ reducedMotion: options.reducedMotion }}>{plot}</ChartHostProvider>
	</MotionConfig>;
}

/** Called only by the Svelte host's client-side lazy import. */
export function mountChart(element: HTMLElement, spec: ChartSpec, options: ChartRenderOptions): ChartMount {
	const root = createRoot(element);
	let destroyed = false;
	const update = (nextSpec: ChartSpec, nextOptions: ChartRenderOptions) => {
		if (destroyed) return;
		// Remount on motion-policy changes to cancel all active Motion subscriptions.
		root.render(<ChartView key={`${nextSpec.kind}:${nextOptions.reducedMotion}`} spec={nextSpec} options={nextOptions} />);
	};
	update(spec, options);
	return {
		update,
		destroy() {
			if (destroyed) return;
			destroyed = true;
			root.unmount();
		}
	};
}
