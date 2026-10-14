import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React, { act } from 'react';
import { mountChart } from './runtime';
import type { ChartMount, ChartSpec } from './types';
import { decimateTimeSeries } from '$lib/vendor/bklit-ui/charts/decimate-time-series';

const viewport = vi.hoisted(() => ({ width: 600, height: 100 }));
// Supply only jsdom's missing layout; all scales, segments and paths are native Bklit.
vi.mock('@visx/responsive', () => ({
	ParentSize: ({ children }: { children: (size: typeof viewport) => React.ReactNode }) => children(viewport),
}));
let container: HTMLDivElement;
let chart: ChartMount | undefined;
let pathLengthDescriptor: PropertyDescriptor | undefined;
beforeEach(() => {
	vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
	// jsdom lacks SVG length measurement. Reveal animation is disabled in these tests.
	pathLengthDescriptor = Object.getOwnPropertyDescriptor(SVGElement.prototype, 'getTotalLength');
	Object.defineProperty(SVGElement.prototype, 'getTotalLength', { configurable: true, value: () => 0 });
	viewport.width = 600; viewport.height = 100;
	container = document.createElement('div'); document.body.append(container);
});
afterEach(async () => {
	await act(async () => chart?.destroy()); chart = undefined;
	container.remove(); vi.unstubAllGlobals();
	if (pathLengthDescriptor) Object.defineProperty(SVGElement.prototype, 'getTotalLength', pathLengthDescriptor);
	else Reflect.deleteProperty(SVGElement.prototype, 'getTotalLength');
});
async function draw(spec: ChartSpec) {
	await act(async () => {
		const options = { height: viewport.height, locale: 'en-US', reducedMotion: true };
		if (chart) chart.update(spec, options);
		else chart = mountChart(container, spec, options);
	});
}

describe('native Bklit chart data boundaries', () => {
	it('keeps stacked capacity segment endpoints exact in a five-pixel chart and clips excess at the quota', async () => {
		viewport.height = 5;
		const spec: ChartSpec = {
			kind: 'bar', orientation: 'horizontal', stacked: true, compact: true, domain: [0, 100],
			xKey: 'category', data: [{ category: 'capacity', used: 70, proposed: 20 }],
			series: [{ key: 'used', label: 'Used', color: 'var(--color-chart-1)' }, { key: 'proposed', label: 'Proposed', color: 'var(--color-chart-2)' }],
		};
		await draw(spec);
		const used = container.querySelector('rect[fill="var(--color-chart-1)"]')!;
		const proposed = container.querySelector('rect[fill="var(--color-chart-2)"]')!;
		expect([Number(used.getAttribute('x')), Number(used.getAttribute('width'))]).toEqual([0, 420]);
		expect([Number(proposed.getAttribute('x')), Number(proposed.getAttribute('width')), Number(proposed.getAttribute('height'))]).toEqual([420, 120, 5]);
		await draw({ ...spec, data: [{ category: 'capacity', used: 95, proposed: 20 }] });
		const clipped = container.querySelector('rect[fill="var(--color-chart-2)"]')!;
		expect([Number(clipped.getAttribute('x')), Number(clipped.getAttribute('width'))]).toEqual([570, 30]);
	});

	it('breaks paths at unavailable measurements while retaining a true zero on the explicit baseline', async () => {
		const spec: ChartSpec = {
			kind: 'time-series', compact: true, domain: [0, 100], xKey: 'ts',
			data: [50, 60, null, 40, 50, NaN, 10, 20].map((value, index) => ({ ts: index * 60_000, value })),
			series: [{ key: 'value', label: 'Usage', color: 'var(--color-chart-1)' }],
		};
		await draw(spec);
		const path = container.querySelector('path[stroke="var(--color-chart-1)"]')!.getAttribute('d')!;
		expect(path.match(/M/g)).toHaveLength(3);
		expect(path).toMatch(/^M0,50(?=[A-Z])/);
		expect(path).not.toMatch(/NaN|Infinity/);
		await draw({ ...spec, data: [{ ts: 0, value: 0 }, { ts: 60_000, value: 0 }] });
		expect(container.querySelector('path[stroke="var(--color-chart-1)"]')!.getAttribute('d')).toMatch(/^M0,100(?=[A-Z])/);
	});

	it('uses each series actual timestamps on one shared time scale without manufacturing aligned samples', async () => {
		await draw({
			kind: 'time-series', compact: true, domain: [0, 100], xKey: 'ts',
			data: [{ ts: 0, rx: 10 }, { ts: 30_000, tx: 20 }, { ts: 60_000, rx: 30 }, { ts: 90_000, tx: 40 }],
			series: [
				{ key: 'rx', label: 'Receive', color: 'var(--color-chart-1)', data: [{ ts: 0, rx: 10 }, { ts: 60_000, rx: 30 }] },
				{ key: 'tx', label: 'Transmit', color: 'var(--color-chart-2)', data: [{ ts: 30_000, tx: 20 }, { ts: 90_000, tx: 40 }] },
			],
		});
		expect(container.querySelector('path[stroke="var(--color-chart-1)"]')!.getAttribute('d')).toBe('M0,90L400,70');
		expect(container.querySelector('path[stroke="var(--color-chart-2)"]')!.getAttribute('d')).toBe('M200,80L600,60');
	});
	it('retains an early observed spike and each endpoint once when downsampling long histories', () => {
		const history = Array.from({ length: 720 }, (_, index) => ({ timestamp: index * 3_600_000, value: index === 1 ? 1000 : 10 }));
		const sampled = decimateTimeSeries(history, 450, ['value']);
		expect(sampled).toContain(history[1]);
		expect(sampled[0]).toBe(history[0]);
		expect(sampled.at(-1)).toBe(history.at(-1));
		expect(new Set(sampled.map(row => row.timestamp)).size).toBe(sampled.length);
		expect(sampled.every((row, index) => index === 0 || row.timestamp > sampled[index - 1].timestamp)).toBe(true);
	});
});
