import type { ChoroplethSpec } from './mapTypes';

export interface ChartSeries {
	key: string;
	label: string;
	color: string;
	area?: boolean;
	dashed?: boolean;
	/** Optional independently sampled source; absent peer timestamps do not break this series. */
	data?: ChartDatum[];
}

/** Times are epoch milliseconds; null/undefined values are gaps, never zero. */
export type ChartDatum = Record<string, string | number | null | undefined>;

interface SeriesSpec {
	data: ChartDatum[];
	xKey: string;
	series: ChartSeries[];
	domain?: [number, number];
	compact?: boolean;
	tooltips?: boolean;
	formatValue?: (value: number) => string;
}

export type ChartSpec =
	| ChoroplethSpec
	| (SeriesSpec & {
		kind: 'time-series';
		formatTime?: (timestamp: number) => string;
	})
	| (SeriesSpec & {
		kind: 'bar';
		orientation?: 'horizontal' | 'vertical';
		stacked?: boolean;
		/** Abbreviate axis labels without changing source keys or detailed values. */
		formatCategory?: (value: string, context: 'axis' | 'detail') => string;
	})
	| {
		kind: 'ring';
		value: number;
		max: number;
		size: number;
		stroke: number;
		color: string;
		track?: string;
	}
	| {
		kind: 'gauge';
		value: number;
		color: string;
		track?: string;
	};

export interface ChartRenderOptions {
	height: number;
	locale: string;
	reducedMotion: boolean;
}

export interface ChartMount {
	update(spec: ChartSpec, options: ChartRenderOptions): void;
	destroy(): void;
}
