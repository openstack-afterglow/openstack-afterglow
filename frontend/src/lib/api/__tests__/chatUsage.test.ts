// @vitest-environment node
import { describe, it, expect } from 'vitest';
import { pivotTimeseries, bucketToTs, sourceRow, type TimeseriesRow } from '../chatUsage';

describe('bucketToTs', () => {
	it('parses month/day/hour buckets to epoch seconds ascending', () => {
		expect(bucketToTs('2026-07')).toBeGreaterThan(0);
		const day = bucketToTs('2026-07-21');
		const hour = bucketToTs('2026-07-21 10:00:00');
		expect(hour).toBeGreaterThan(day);
	});
	it('returns 0 for invalid', () => {
		expect(bucketToTs('')).toBe(0);
		expect(bucketToTs('nonsense')).toBe(0);
	});
});

describe('pivotTimeseries', () => {
	const rows: TimeseriesRow[] = [
		{ bucket: '2026-07-21', source: 'web', total_tokens: 100, credited_cost: 1, request_count: 3 },
		{ bucket: '2026-07-21', source: 'api', total_tokens: 40, credited_cost: 0.4, request_count: 2 },
		{ bucket: '2026-07-20', source: 'api', total_tokens: 10, credited_cost: 0.1, request_count: 1 }
	];

	it('pivots sources per bucket and sorts by ts ascending', () => {
		const pts = pivotTimeseries(rows, 'total_tokens');
		expect(pts.map((p) => p.bucket)).toEqual(['2026-07-20', '2026-07-21']); // 오름차순
		const jul21 = pts.find((p) => p.bucket === '2026-07-21')!;
		expect(jul21.web).toBe(100);
		expect(jul21.api).toBe(40);
		expect(jul21.total).toBe(140);
	});

	it('supports credited_cost metric', () => {
		const pts = pivotTimeseries(rows, 'credited_cost');
		const jul21 = pts.find((p) => p.bucket === '2026-07-21')!;
		expect(jul21.total).toBeCloseTo(1.4);
	});

	it('empty input → empty', () => {
		expect(pivotTimeseries([])).toEqual([]);
	});
});

describe('sourceRow', () => {
	it('returns matching source or zeroed default', () => {
		const by = [{ source: 'api', tokens: 5, credited_cost: 0.5, request_count: 2 }];
		expect(sourceRow(by, 'api').tokens).toBe(5);
		expect(sourceRow(by, 'web')).toEqual({ source: 'web', tokens: 0, credited_cost: 0, request_count: 0 });
	});
});
