export type TrafficSource = 'backend' | 'frontend';
export type TrafficRange = '24h' | '7d' | '30d';
export const trafficOrigins = ['internal', 'external', 'unknown', 'legacy_unclassified'] as const;
export type TrafficOrigin = typeof trafficOrigins[number];
export type TrafficOriginFilter = 'all' | TrafficOrigin;
export type TrafficOrigins = Record<TrafficOrigin, number>;
export const geoReasons = ['address_unavailable', 'invalid_address', 'non_global', 'database_unconfigured', 'database_unavailable', 'range_missing', 'country_invalid', 'lookup_failed', 'peer_unverified', 'forwarded_missing', 'forwarded_invalid', 'forwarded_all_trusted', 'legacy_unclassified'] as const;
export const originReasons = ['peer_unverified', 'address_unavailable', 'invalid_address', 'forwarded_missing', 'forwarded_invalid', 'forwarded_all_trusted', 'non_global_noncluster', 'legacy_unclassified'] as const;
export interface TrafficMetrics {
	requests: number; success: number; errors: number;
	status_1xx: number; status_2xx: number; status_3xx: number; status_4xx: number; status_5xx: number;
	pageviews: number; unlocated: number; request_bytes: number | null; response_bytes: number | null;
	request_bytes_known: number; response_bytes_known: number;
	visitor_identity_known: number;
	latency_ms_total: number; latency_ms_max: number; unique_visitors: number | null;
}
export interface TrafficSnapshot {
	state: 'available' | 'partial' | 'unavailable' | 'disabled'; source: TrafficSource; range: TrafficRange;
    retention_days: number; generated_at: number; origin: TrafficOriginFilter; origins: TrafficOrigins | null;
    coverage: { description: string; geo_source: 'offline_mmdb' | 'unconfigured' | 'unavailable'; site_country: string | null; unique_method: string;
        geo_provider: string | null; geo_version: string | null; geo_attribution: string | null;
        geo_unknown_reasons: Partial<Record<typeof geoReasons[number], number>>;
        origin_unknown_reasons: Partial<Record<typeof originReasons[number], number>>;
        classified_requests: number | null; legacy_unclassified_requests: number | null; classification_policy: string;
        dropped_events: number | null; reporter_dropped_events: number | null; observed_since: number | null; last_observed_at: number | null };
	totals: TrafficMetrics | null;
	countries: Array<TrafficMetrics & { country: string }>;
    routes: Array<TrafficMetrics & { route: string; origins: TrafficOrigins }>;
	series: Array<{ at: number; metrics: TrafficMetrics | null }>;
}
export type TrafficMetric = keyof TrafficMetrics | 'latency_avg';
const counts = ['requests', 'success', 'errors', 'status_1xx', 'status_2xx', 'status_3xx', 'status_4xx', 'status_5xx', 'pageviews', 'unlocated', 'request_bytes_known', 'response_bytes_known', 'visitor_identity_known'] as const;
const nullableCounts = ['request_bytes', 'response_bytes', 'unique_visitors'] as const;
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const nonnegative = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0;
const count = (v: unknown): v is number => nonnegative(v) && Number.isSafeInteger(v);
const nullable = (v: unknown, guard = nonnegative) => v === null || guard(v);
function metrics(v: unknown): v is TrafficMetrics {
	return object(v) && counts.every(k => count(v[k])) && nullableCounts.every(k => nullable(v[k], count)) &&
		nonnegative(v.latency_ms_total) && nonnegative(v.latency_ms_max) &&
		(v.request_bytes_known as number) <= (v.requests as number) && (v.response_bytes_known as number) <= (v.requests as number) && (v.visitor_identity_known as number) <= (v.requests as number);
}
function origins(v: unknown): v is TrafficOrigins {
    return object(v) && Object.keys(v).length === trafficOrigins.length && trafficOrigins.every(k => count(v[k]));
}
function reasons(v: unknown, allowed: readonly string[]): boolean {
    return object(v) && Object.entries(v).every(([key, value]) => allowed.includes(key) && count(value));
}
export function parseTrafficSnapshot(value: unknown, source: TrafficSource, range: TrafficRange, origin: TrafficOriginFilter = 'all'): TrafficSnapshot {
	if (!object(value)) throw new Error('Invalid traffic schema');
	const c = value.coverage;
	if (typeof value.state !== 'string' || !['available', 'partial', 'unavailable', 'disabled'].includes(value.state) || value.source !== source || value.range !== range ||
        value.origin !== origin || !(value.origins === null || origins(value.origins)) ||
		!count(value.retention_days) || !nonnegative(value.generated_at) || !object(c) || typeof c.description !== 'string' || typeof c.unique_method !== 'string' ||
        typeof c.geo_source !== 'string' || !['offline_mmdb', 'unconfigured', 'unavailable'].includes(c.geo_source) || !nullable(c.dropped_events, count) || !nullable(c.reporter_dropped_events, count) || !nullable(c.observed_since) || !nullable(c.last_observed_at) ||
        ![c.geo_provider, c.geo_version, c.geo_attribution].every(v => v === null || typeof v === 'string') ||
        !reasons(c.geo_unknown_reasons, geoReasons) || !reasons(c.origin_unknown_reasons, originReasons) ||
        !nullable(c.classified_requests, count) || !nullable(c.legacy_unclassified_requests, count) || typeof c.classification_policy !== 'string' ||
		!(c.site_country === null || (typeof c.site_country === 'string' && /^[A-Z]{2}$/.test(c.site_country) && c.site_country.length === 2 && c.site_country !== 'XX')) ||
		!(value.totals === null || metrics(value.totals)) ||
		!Array.isArray(value.countries) || !value.countries.every(v => metrics(v) && object(v) && typeof v.country === 'string' && /^[A-Z]{2}$/.test(v.country)) ||
        !Array.isArray(value.routes) || !value.routes.every(v => metrics(v) && object(v) && typeof v.route === 'string' && origins(v.origins) && trafficOrigins.reduce((sum, k) => sum + (v.origins as TrafficOrigins)[k], 0) === v.requests) ||
		!Array.isArray(value.series) || !value.series.every(v => object(v) && nonnegative(v.at) && (v.metrics === null || metrics(v.metrics)))) throw new Error('Invalid traffic schema');
	const snapshot = value as unknown as TrafficSnapshot;
	if (new Set(snapshot.countries.map(v => v.country)).size !== snapshot.countries.length ||
        new Set(snapshot.routes.map(v => v.route)).size !== snapshot.routes.length ||
        (snapshot.totals === null ? snapshot.origins !== null : snapshot.origins === null) ||
        (snapshot.origins !== null && trafficOrigins.reduce((sum, k) => sum + snapshot.origins![k], 0) !== (snapshot.totals?.requests ?? 0)) ||
        (snapshot.origins !== null && trafficOrigins.some(k => origin !== 'all' && origin !== k && snapshot.origins![k] !== 0)) ||
		snapshot.series.some((v, i, all) => i > 0 && v.at <= all[i - 1].at)) throw new Error('Invalid traffic schema');
	return snapshot;
}
export function metricValue(metrics: TrafficMetrics | null, key: TrafficMetric): number | null {
	if (!metrics) return null;
	return key === 'latency_avg' ? (metrics.requests > 0 ? metrics.latency_ms_total / metrics.requests : null) : metrics[key];
}
// Spark does not represent gaps: only plot the latest contiguous observed tail.
export function trafficTrend(series: TrafficSnapshot['series'], key: TrafficMetric): number[] {
	const values: number[] = [];
	for (let i = series.length - 1; i >= 0; i--) {
		const value = metricValue(series[i].metrics, key);
		if (value === null) break;
		values.push(value);
	}
	return values.reverse();
}
export function countryIntensity(requests: number | null, max: number): number | null {
	return requests === null ? null : max === 0 ? 0 : Math.log1p(requests) / Math.log1p(max);
}
