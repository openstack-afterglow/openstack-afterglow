import { describe, expect, it } from 'vitest';
import {
	WAYGATE_TRAFFIC_LIMIT,
	WAYGATE_TRAFFIC_STALE_MS,
	appendClientTraffic,
	currentClientTraffic,
	formatTrafficBytes,
	type ClientTrafficHistory,
} from '../waygateTraffic';

const base = Date.parse('2026-09-27T00:00:00Z');

function report(offsetSeconds: number, gatewayRx: number | null, gatewayTx: number | null) {
	return {
		last_reported_at: new Date(base + offsetSeconds * 1000).toISOString(),
		rx_bytes: gatewayRx,
		tx_bytes: gatewayTx,
	};
}

function feed(...reports: [number, number | null, number | null][]) {
	let history: ClientTrafficHistory | undefined;
	for (const [offset, rx, tx] of reports) {
		history = appendClientTraffic(history, report(offset, rx, tx), base + offset * 1000);
	}
	return history!;
}

describe('Waygate client traffic history', () => {
	it('uses the client perspective and server report intervals for rates', () => {
		// Gateway received 1000 B from the client and transmitted 4000 B to it over 10 s.
		const history = feed([0, 1000, 2000], [10, 2000, 6000]);
		expect(history.samples.at(-1)).toMatchObject({ rxBytes: 6000, txBytes: 2000, rxRate: 400, txRate: 100 });
		expect(currentClientTraffic(history, base + 12_000)).toMatchObject({ fresh: true, rxRate: 400, txRate: 100 });
	});

	it('shows totals but no rate until two contiguous reports exist', () => {
		const history = feed([0, 10, 20]);
		expect(history.samples[0]).toMatchObject({ rxBytes: 20, txBytes: 10, rxRate: null, txRate: null });
	});

	it('ignores duplicate and out-of-order report timestamps', () => {
		const history = feed([0, 0, 0], [10, 100, 100], [10, 900, 900], [5, 50, 50]);
		expect(history.samples.map((sample) => sample.timestamp)).toEqual([base, base + 10_000]);
		expect(history.samples.at(-1)?.rxRate).toBe(10);
	});

	it('does not turn counter resets or long gaps into traffic spikes', () => {
		const reset = feed([0, 5000, 5000], [10, 20, 30]);
		expect(reset.samples.at(-1)).toMatchObject({ rxRate: null, txRate: null, rxBytes: 30 });
		const gap = feed([0, 0, 0], [WAYGATE_TRAFFIC_STALE_MS / 1000 + 1, 90_000, 90_000]);
		expect(gap.samples.at(-1)?.rxRate).toBeNull();
	});

	it('breaks continuity after missing reports or peers', () => {
		let history = feed([0, 0, 0]);
		history = appendClientTraffic(history, { last_reported_at: null, rx_bytes: null, tx_bytes: null }, base + 5000);
		expect(currentClientTraffic(history, base + 5000).fresh).toBe(false);
		history = appendClientTraffic(history, report(10, 100, 100), base + 10_000);
		expect(history.samples.at(-1)?.rxRate).toBeNull();
		history = appendClientTraffic(history, report(20, null, null), base + 20_000);
		history = appendClientTraffic(history, report(30, 300, 300), base + 30_000);
		expect(history.samples.at(-1)?.rxRate).toBeNull();
	});

	it('marks stopped or already-old reports stale without clearing totals', () => {
		const stopped = feed([0, 0, 0], [10, 100, 100]);
		expect(currentClientTraffic(stopped, base + 10_000 + WAYGATE_TRAFFIC_STALE_MS + 1)).toEqual({ fresh: false, rxRate: null, txRate: null });
		const cached = appendClientTraffic(undefined, report(0, 1, 1), base + WAYGATE_TRAFFIC_STALE_MS + 1);
		expect(currentClientTraffic(cached, base + WAYGATE_TRAFFIC_STALE_MS + 1).fresh).toBe(false);
		expect(cached.samples[0].rxBytes).toBe(1);
	});

	it('expires an already-aged report based on report time, not browser arrival', () => {
		let history = appendClientTraffic(undefined, report(0, 0, 0), base + 85_000);
		history = appendClientTraffic(history, report(10, 100, 200), base + 95_000);
		expect(currentClientTraffic(history, base + 95_000)).toEqual({ fresh: true, rxRate: 20, txRate: 10 });
		// Same cached report arrives again, but its timestamp has now aged past 90 s.
		history = appendClientTraffic(history, report(10, 100, 200), base + 101_000);
		expect(currentClientTraffic(history, base + 101_000)).toEqual({ fresh: false, rxRate: null, txRate: null });
	});

	it('keeps a bounded report history', () => {
		const reports: [number, number, number][] = Array.from({ length: WAYGATE_TRAFFIC_LIMIT + 5 }, (_, index) => [index * 10, index, index]);
		const history = feed(...reports);
		expect(history.samples).toHaveLength(WAYGATE_TRAFFIC_LIMIT);
		expect(history.samples[0].timestamp).toBe(base + 50_000);
	});

	it('formats missing counters distinctly from zero and fractional rates as bytes', () => {
		expect(formatTrafficBytes(null)).toBe('—');
		expect(formatTrafficBytes(0)).toBe('0 B');
		expect(formatTrafficBytes(0.4)).toBe('0 B');
		expect(formatTrafficBytes(1536)).toBe('1.5 KiB');
	});
});
