import { describe, expect, it } from 'vitest';
import {
	WAYGATE_TRAFFIC_LIMIT,
	waygateTrafficFreshnessMs,
	appendClientTraffic,
	currentClientTraffic,
	formatTrafficBytes,
	type ClientTrafficHistory,
} from '../waygateTraffic';

const base = Date.parse('2026-09-27T00:00:00Z');
const legacyFreshnessMs = waygateTrafficFreshnessMs(null, 1);

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
		history = appendClientTraffic(history, report(offset, rx, tx), base + offset * 1000, legacyFreshnessMs);
	}
	return history!;
}

describe('Waygate client traffic history', () => {
	it('uses the client perspective and server report intervals for rates', () => {
		// Gateway received 1000 B from the client and transmitted 4000 B to it over 10 s.
		const history = feed([0, 1000, 2000], [10, 2000, 6000]);
		expect(history.samples.at(-1)).toMatchObject({ rxBytes: 6000, txBytes: 2000, rxRate: 400, txRate: 100 });
		expect(currentClientTraffic(history, base + 12_000, legacyFreshnessMs)).toMatchObject({ fresh: true, rxRate: 400, txRate: 100 });
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
		const gap = feed([0, 0, 0], [legacyFreshnessMs / 1000 + 1, 90_000, 90_000]);
		expect(gap.samples.at(-1)?.rxRate).toBeNull();
	});

	it('breaks continuity after missing reports or peers', () => {
		let history = feed([0, 0, 0]);
		history = appendClientTraffic(history, { last_reported_at: null, rx_bytes: null, tx_bytes: null }, base + 5000, legacyFreshnessMs);
		expect(currentClientTraffic(history, base + 5000, legacyFreshnessMs).fresh).toBe(false);
		history = appendClientTraffic(history, report(10, 100, 100), base + 10_000, legacyFreshnessMs);
		expect(history.samples.at(-1)?.rxRate).toBeNull();
		history = appendClientTraffic(history, report(20, null, null), base + 20_000, legacyFreshnessMs);
		history = appendClientTraffic(history, report(30, 300, 300), base + 30_000, legacyFreshnessMs);
		expect(history.samples.at(-1)?.rxRate).toBeNull();
	});

	it('marks stopped or already-old reports stale without clearing totals', () => {
		const stopped = feed([0, 0, 0], [10, 100, 100]);
		expect(currentClientTraffic(stopped, base + 10_000 + legacyFreshnessMs + 1, legacyFreshnessMs)).toEqual({ fresh: false, rxRate: null, txRate: null });
		const cached = appendClientTraffic(undefined, report(0, 1, 1), base + legacyFreshnessMs + 1, legacyFreshnessMs);
		expect(currentClientTraffic(cached, base + legacyFreshnessMs + 1, legacyFreshnessMs).fresh).toBe(false);
		expect(cached.samples[0].rxBytes).toBe(1);
	});

	it('expires an already-aged report based on report time, not browser arrival', () => {
		let history = appendClientTraffic(undefined, report(0, 0, 0), base + 35_000, legacyFreshnessMs);
		history = appendClientTraffic(history, report(10, 100, 200), base + 45_000, legacyFreshnessMs);
		expect(currentClientTraffic(history, base + 45_000, legacyFreshnessMs)).toEqual({ fresh: true, rxRate: 20, txRate: 10 });
		// Polling the same cached report does not extend freshness beyond the report's age.
		history = appendClientTraffic(history, report(10, 100, 200), base + 56_000, legacyFreshnessMs);
		expect(currentClientTraffic(history, base + 56_000, legacyFreshnessMs)).toEqual({ fresh: false, rxRate: null, txRate: null });
	});

	it('tracks fast, slow and legacy report cadences without inventing rates across gaps', () => {
		const fast = waygateTrafficFreshnessMs(1, 1);
		const slow = waygateTrafficFreshnessMs(60, 1);
		expect(fast).toBe(5000);
		expect(slow).toBe(180_000);
		expect(waygateTrafficFreshnessMs(1, 30)).toBe(90_000);
		expect(legacyFreshnessMs).toBe(45_000);
		const fastHistory = appendClientTraffic(appendClientTraffic(undefined, report(0, 0, 0), base, fast), report(6, 600, 600), base + 6000, fast);
		expect(fastHistory.samples.at(-1)?.rxRate).toBeNull();
		expect(currentClientTraffic(fastHistory, base + 12_000, fast).fresh).toBe(false);
		const slowHistory = appendClientTraffic(appendClientTraffic(undefined, report(0, 0, 0), base, slow), report(100, 1000, 1000), base + 100_000, slow);
		expect(slowHistory.samples.at(-1)?.rxRate).toBe(10);
		expect(currentClientTraffic(slowHistory, base + 100_000 + slow, slow).fresh).toBe(true);
		expect(currentClientTraffic(slowHistory, base + 100_000 + slow + 1, slow).fresh).toBe(false);
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
