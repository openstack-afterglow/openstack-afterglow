import type { TrafficMetrics, TrafficNetwork, TrafficSnapshot } from '$lib/types/trafficAnalytics';

// Synthetic observations for unit tests only; production UI never generates traffic data.
export function metrics(overrides: Partial<TrafficMetrics> = {}): TrafficMetrics {
	return { requests: 10, success: 8, errors: 2, status_1xx: 0, status_2xx: 8, status_3xx: 0, status_4xx: 1, status_5xx: 1,
		pageviews: 3, unlocated: 2, request_bytes: null, response_bytes: 400, request_bytes_known: 0, response_bytes_known: 8,
		latency_ms_total: 120, latency_ms_max: 40, unique_visitors: 4, visitor_identity_known: 8, ...overrides };
}
export function observations(overrides: Partial<TrafficSnapshot> = {}): TrafficSnapshot {
	return { state: 'partial', source: 'backend', range: '24h', origin: 'all', origins: { internal: 3, external: 4, unknown: 2, legacy_unclassified: 1 }, retention_days: 30, generated_at: 1700007200,
		coverage: { description: 'Observed test server only', geo_source: 'unconfigured', geo_provider: null, geo_version: null, geo_attribution: null, geo_unknown_reasons: { non_global: 2 }, origin_unknown_reasons: { non_global_noncluster: 2, legacy_unclassified: 1 }, classified_requests: 7, legacy_unclassified_requests: 1, classification_policy: 'Exact configured CIDRs only', site_country: null, unique_method: 'Rotating HLL', dropped_events: 2, reporter_dropped_events: null, observed_since: 1700000000, last_observed_at: 1700003600 },
		totals: metrics(), countries: [{ ...metrics({ unique_visitors: null }), country: 'KR' }, { ...metrics({ requests: 0, success: 0, errors: 0, status_2xx: 0, status_4xx: 0, status_5xx: 0, pageviews: 0, unlocated: 0, response_bytes: 0, response_bytes_known: 0, visitor_identity_known: 0, latency_ms_total: 0, latency_ms_max: 0, unique_visitors: null }), country: 'US' }, { ...metrics({ unique_visitors: null }), country: 'XX' }],
		networks: [],
		routes: [{ ...metrics({ unique_visitors: null }), route: '/admin', origins: { internal: 3, external: 4, unknown: 2, legacy_unclassified: 1 } }],
		series: [{ at: 1700000000, metrics: metrics({ requests: 8 }) }, { at: 1700003600, metrics: metrics({ requests: 10 }) }], ...overrides };
}
export function networkObservations(): TrafficNetwork[] {
	return [
		{ network: '172.30.0.0/16', basis: 'resolved_client' as const, requests: 3, errors: 1 },
		{ network: '172.31.0.0/16', basis: 'socket_peer' as const, requests: 4, errors: 2 },
		{ network: '10.8.0.0/16', basis: 'resolved_client' as const, requests: 2, errors: 0 },
		{ network: '172.30.0.0/16', basis: 'socket_peer' as const, requests: 1, errors: 0 },
	].map(({ requests, errors, ...identity }) => ({
		...metrics({ requests, errors, success: requests - errors, status_2xx: requests - errors, status_4xx: errors, status_5xx: 0,
			pageviews: 0, unlocated: requests, response_bytes: null, response_bytes_known: 0, visitor_identity_known: 0, unique_visitors: null }),
		...identity, kind: 'private' as const,
	}));
}
