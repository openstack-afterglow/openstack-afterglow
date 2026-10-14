import type { TrafficMetrics, TrafficSnapshot } from '$lib/types/trafficAnalytics';

// Synthetic observations for unit tests only; production UI never generates traffic data.
export function metrics(overrides: Partial<TrafficMetrics> = {}): TrafficMetrics {
	return { requests: 10, success: 8, errors: 2, status_1xx: 0, status_2xx: 8, status_3xx: 0, status_4xx: 1, status_5xx: 1,
		pageviews: 3, unlocated: 2, request_bytes: null, response_bytes: 400, request_bytes_known: 0, response_bytes_known: 8,
		latency_ms_total: 120, latency_ms_max: 40, unique_visitors: 4, visitor_identity_known: 8, ...overrides };
}
export function observations(overrides: Partial<TrafficSnapshot> = {}): TrafficSnapshot {
	return { state: 'partial', source: 'backend', range: '24h', retention_days: 30, generated_at: 1700007200,
		coverage: { description: 'Observed test server only', geo_source: 'unconfigured', site_country: null, unique_method: 'Rotating HLL', dropped_events: 2, reporter_dropped_events: null, observed_since: 1700000000, last_observed_at: 1700003600 },
		totals: metrics(), countries: [{ ...metrics({ unique_visitors: null }), country: 'KR' }, { ...metrics({ requests: 0, success: 0, errors: 0, status_2xx: 0, status_4xx: 0, status_5xx: 0, pageviews: 0, unlocated: 0, response_bytes: 0, response_bytes_known: 0, visitor_identity_known: 0, latency_ms_total: 0, latency_ms_max: 0, unique_visitors: null }), country: 'US' }, { ...metrics({ unique_visitors: null }), country: 'XX' }],
		routes: [{ ...metrics({ unique_visitors: null }), route: '/admin' }],
		series: [{ at: 1700000000, metrics: metrics({ requests: 8 }) }, { at: 1700003600, metrics: metrics({ requests: 10 }) }], ...overrides };
}
