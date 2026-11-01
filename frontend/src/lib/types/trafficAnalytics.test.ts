import { describe, expect, it } from 'vitest';
import { countryIntensity, metricValue, parseTrafficSnapshot, trafficTrend } from './trafficAnalytics';
import { metrics, networkObservations, observations } from '$lib/components/admin/traffic/__tests__/observations';

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
		expect(() => parseTrafficSnapshot({ ...observations(), coverage: { ...observations().coverage, geo_source: 'offline_cidr' } }, 'backend', '24h')).toThrow();
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
	it('rejects duplicate route keys and unknown reason dimensions without exposing address evidence', () => {
		const duplicate = observations(); duplicate.routes.push(duplicate.routes[0]);
		expect(() => parseTrafficSnapshot(duplicate, 'backend', '24h')).toThrow();
		const invalid = observations(); Object.assign(invalid.coverage.origin_unknown_reasons, { 'raw-ip-192.0.2.10': 1 });
		expect(() => parseTrafficSnapshot(invalid, 'backend', '24h')).toThrow();
	});
	it('requires network observations and preserves separate ranges and address bases without changing country totals', () => {
		const input = observations({ networks: networkObservations() });
		const parsed = parseTrafficSnapshot(input, 'backend', '24h');
		expect(parsed.networks).toBe(input.networks);
		expect(parsed.networks.filter(row => row.network === '172.30.0.0/16').map(row => row.basis)).toEqual(['resolved_client', 'socket_peer']);
		expect(parsed.countries.find(row => row.country === 'XX')?.requests).toBe(10);
		expect(parsed.totals?.requests).toBe(10);
		const missing = observations(); Reflect.deleteProperty(missing, 'networks');
		expect(() => parseTrafficSnapshot(missing, 'backend', '24h')).toThrow('Invalid traffic schema');
		for (const networks of [null, {}, '172.30.0.0/16']) expect(() => parseTrafficSnapshot({ ...input, networks }, 'backend', '24h')).toThrow();
	});
	it.each([
		['fc00::/7', 'private'], ['fe80::/10', 'link_local'], ['::1/128', 'loopback'], ['::/128', 'unspecified'],
		['2001:db8::/32', 'documentation'], ['100.64.0.0/10', 'shared'], ['198.18.0.0/15', 'benchmark'],
		['ff00::/8', 'multicast'], ['240.0.0.0/4', 'reserved'], ['10.255.0.0/16', 'private'],
	])('accepts standard privacy-preserving range %s as %s', (network, kind) => {
		const input = { ...observations(), networks: [{ ...metrics(), network, kind, basis: 'resolved_client' }] };
		expect(parseTrafficSnapshot(input, 'backend', '24h').networks[0]).toMatchObject({ network, kind });
	});
	it.each([
		{ network: '172.30.1.99/32' }, { network: '172.30.1.0/24' }, { network: '172.30.0.1/16' },
		{ network: '10.256.0.0/16' }, { network: '10.08.0.0/16' }, { network: '172.32.0.0/16' },
		{ network: '8.8.0.0/16' }, { network: '0.0.0.0/0' }, { network: '172.30.0.0/16\n' },
		{ network: 'fc12:3456:789a::/48' }, { network: 'fe80::1234/128' }, { network: 'fc00::/129' },
		{ network: 'fc00::/7%eth0' }, { network: 'fc00:::/7' }, { network: '<script>/16' },
		{ network: 'a'.repeat(100) }, { network: null }, { network: 'FC00::/7' },
		{ kind: 'vpn' }, { kind: 'loopback' }, { kind: undefined }, { basis: undefined }, { basis: 'forwarded_for' },
		{ requests: -1 }, { errors: Number.MAX_SAFE_INTEGER + 1 },
	])('rejects unsafe or malformed network row %j', (override) => {
		const networks = [{ ...networkObservations()[0], ...override }];
		expect(() => parseTrafficSnapshot({ ...observations(), networks }, 'backend', '24h')).toThrow('Invalid traffic schema');
	});
	it('rejects duplicate network and basis keys while permitting the same range with distinct evidence', () => {
		const networks = networkObservations(); networks.push({ ...networks[0] });
		expect(() => parseTrafficSnapshot(observations({ networks }), 'backend', '24h')).toThrow('Invalid traffic schema');
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
