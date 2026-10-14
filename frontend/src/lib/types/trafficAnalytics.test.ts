import { describe, expect, it } from 'vitest';
import { countryIntensity, metricValue, parseTrafficSnapshot, trafficTrend } from './trafficAnalytics';
import { metrics, observations } from '$lib/components/admin/traffic/__tests__/observations';

describe('traffic snapshot schema and unknown coverage', () => {
	it('accepts exact source, nullable buckets and nullable geographic visitor estimates without inventing zero', () => {
		const input = observations({ series: [{ at: 100, metrics: null }, { at: 200, metrics: metrics() }] });
		const parsed = parseTrafficSnapshot(input, 'backend', '24h');
		expect(parsed).toBe(input); expect(parsed.series[0].metrics).toBeNull(); expect(parsed.countries[0].unique_visitors).toBeNull();
	});
	it('keeps absent totals and measured zero as distinct states', () => {
		const absent = observations({ totals: null, origins: null, countries: [], routes: [], series: [] });
		expect(parseTrafficSnapshot(absent, 'backend', '24h').totals).toBeNull();
		expect(metricValue(metrics({ requests: 0 }), 'requests')).toBe(0); expect(metricValue(null, 'requests')).toBeNull();
	});
	it('rejects response source/range mixing and malformed coverage', () => {
		expect(() => parseTrafficSnapshot(observations({ source: 'frontend' }), 'backend', '24h')).toThrow();
		expect(() => parseTrafficSnapshot(observations({ range: '7d' }), 'backend', '24h')).toThrow();
		for (const field of ['last_observed_at', 'observed_since', 'reporter_dropped_events', 'dropped_events']) {
			const input = observations(); Reflect.deleteProperty(input.coverage, field);
			expect(() => parseTrafficSnapshot(input, 'backend', '24h')).toThrow();
		}
		expect(() => parseTrafficSnapshot({ ...observations(), coverage: { ...observations().coverage, geo_source: 'header' } }, 'backend', '24h')).toThrow();
	});
    it('fences origin selections and rejects forged reason/cardinality dimensions', () => {
        expect(() => parseTrafficSnapshot(observations(), 'backend', '24h', 'external')).toThrow();
        const selected = observations({ origin: 'external', origins: { internal: 0, external: 10, unknown: 0, legacy_unclassified: 0 }, routes: [] });
        expect(parseTrafficSnapshot(selected, 'backend', '24h', 'external')).toBe(selected);
        expect(() => parseTrafficSnapshot({ ...selected, origins: { ...selected.origins, internal: 1 } }, 'backend', '24h', 'external')).toThrow();
        const invalid = observations(); Object.assign(invalid.coverage.geo_unknown_reasons, { 'raw-ip-8.8.8.8': 1 });
        expect(() => parseTrafficSnapshot(invalid, 'backend', '24h')).toThrow();
        const inconsistent = observations(); inconsistent.routes[0].origins.internal++;
        expect(() => parseTrafficSnapshot(inconsistent, 'backend', '24h')).toThrow();
    });
	it.each([-1, Infinity, NaN, 1.5, '0', undefined])('rejects invalid request counters %s', (requests) => {
		expect(() => parseTrafficSnapshot({ ...observations(), totals: { ...metrics(), requests } }, 'backend', '24h')).toThrow();
	});
	it('rejects missing country/route arrays, malformed nullable byte values, unsafe integers and identity coverage beyond requests', () => {
		for (const override of [{ countries: undefined }, { routes: undefined }, { totals: { ...metrics(), request_bytes: -1 } }, { totals: { ...metrics(), response_bytes: Number.MAX_SAFE_INTEGER + 1 } }, { totals: { ...metrics(), visitor_identity_known: 11 } }, { totals: { ...metrics(), request_bytes_known: 11 } }]) {
			expect(() => parseTrafficSnapshot({ ...observations(), ...override }, 'backend', '24h')).toThrow();
		}
	});
	it('rejects duplicate countries and unsorted/duplicate bucket timestamps', () => {
		const input = observations(); input.countries.push(input.countries[0]); expect(() => parseTrafficSnapshot(input, 'backend', '24h')).toThrow();
		for (const times of [[20, 10], [10, 10]]) expect(() => parseTrafficSnapshot(observations({ series: times.map(at => ({ at, metrics: metrics() })) }), 'backend', '24h')).toThrow();
	});
	it('never joins a Spark across missing observations or substitutes unknown bytes with zeros', () => {
		const series = [{ at: 100, metrics: metrics({ requests: 100 }) }, { at: 200, metrics: null }, { at: 300, metrics: metrics({ requests: 0 }) }, { at: 400, metrics: metrics({ requests: 5 }) }];
		expect(trafficTrend(series, 'requests')).toEqual([0, 5]); expect(trafficTrend([...series, { at: 500, metrics: null }], 'requests')).toEqual([]);
		expect(trafficTrend([{ at: 100, metrics: metrics({ response_bytes: null }) }, { at: 200, metrics: metrics({ response_bytes: 0 }) }], 'response_bytes')).toEqual([0]);
		expect(metricValue(metrics({ requests: 0 }), 'latency_avg')).toBeNull(); expect(metricValue(metrics(), 'latency_avg')).toBe(12);
	});
	it('distinguishes absent map coverage from measured zero and uses relative logarithmic intensity', () => {
		expect(countryIntensity(null, 100)).toBeNull(); expect(countryIntensity(0, 100)).toBe(0); expect(countryIntensity(0, 0)).toBe(0);
		expect(countryIntensity(100, 100)).toBe(1); expect(countryIntensity(10, 100)).toBeGreaterThan(0.1);
	});
});
