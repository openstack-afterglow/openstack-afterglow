import type { FeatureCollection, Geometry } from 'geojson';
import geographicData from '$lib/assets/traffic/countries.geo.json';
import type { ChoroplethSpec, MapCoordinate } from '$lib/components/charts/mapTypes';
import { countryIntensity } from '$lib/types/trafficAnalytics';
import type { TrafficSnapshot } from '$lib/types/trafficAnalytics';
import { t } from '$lib/i18n/ns/traffic-analytics';
import { formatTrafficValue, trafficCountryName } from './trafficFormat';

// Unrounded, pinned Natural Earth coordinates; Bklit owns geographic projection.
export const trafficGeography = geographicData as FeatureCollection<Geometry, Record<string, unknown>>;

/** Keep the established mainland bounding-box anchor, now in geographic degrees. */
export function countryAnchor(geometry: Geometry): MapCoordinate | null {
	const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
	let largestArea = 0;
	let anchor: MapCoordinate | null = null;
	for (const polygon of polygons) {
		const ring = polygon[0];
		if (!ring || ring.length < 4 || ring[0][0] !== ring.at(-1)?.[0] || ring[0][1] !== ring.at(-1)?.[1]) continue;
		let area = 0;
		let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
		for (let i = 0; i < ring.length - 1; i++) {
			const a = ring[i], b = ring[i + 1];
			if (!Number.isFinite(a[0]) || !Number.isFinite(a[1]) || !Number.isFinite(b[0]) || !Number.isFinite(b[1])) { area = NaN; break; }
			area += a[0] * b[1] - b[0] * a[1];
			minX = Math.min(minX, a[0]); maxX = Math.max(maxX, a[0]);
			minY = Math.min(minY, a[1]); maxY = Math.max(maxY, a[1]);
		}
		if (Math.abs(area) > largestArea) {
			largestArea = Math.abs(area);
			anchor = [(minX + maxX) / 2, (minY + maxY) / 2];
		}
	}
	return anchor;
}

export const trafficCountryAnchors: Record<string, MapCoordinate> = {};
for (const feature of trafficGeography.features) {
	const code = feature.properties.country;
	const anchor = countryAnchor(feature.geometry);
	if (typeof code === 'string' && anchor) trafficCountryAnchors[code] = anchor;
}

export function trafficFlowWidth(requests: number, maxRequests: number): number {
	return maxRequests > 0 ? 1 + 3 * Math.log1p(requests) / Math.log1p(maxRequests) : 1;
}

/** Map API observations into the generic chart boundary without losing missingness. */
export function createTrafficMapSpec(
	countries: TrafficSnapshot['countries'], siteCountry: string | null, selectedKey: string, activeKey: string,
	onSelect: ChoroplethSpec['onSelect'], onHover: ChoroplethSpec['onHover']
): ChoroplethSpec {
	const byCountry = Object.fromEntries(countries.map(row => [row.country, row]));
	const max = Math.max(0, ...countries.filter(row => row.country !== 'XX').map(row => row.requests));
	const features: ChoroplethSpec['features'] = {};
	for (const feature of trafficGeography.features) {
		const code = feature.properties.country;
		if (typeof code !== 'string') continue;
		const value = byCountry[code]?.requests ?? null;
		const intensity = countryIntensity(value, max);
		const name = trafficCountryName(code);
		features[code] = {
			name, value,
			label: `${name}: ${value === null ? t('noObservations') : `${t('metrics.requests')} ${formatTrafficValue(value)}`}`,
			fill: intensity === null ? 'var(--color-surface-sunken)' : `color-mix(in oklab, var(--color-accent) ${15 + intensity * 75}%, var(--color-surface-base))`,
		};
	}
	const site = siteCountry && siteCountry !== 'XX' ? trafficCountryAnchors[siteCountry] : undefined;
	const flows = site ? countries.filter(row => row.country !== 'XX' && row.country !== siteCountry && trafficCountryAnchors[row.country]) : [];
	const flowMax = Math.max(0, ...flows.map(row => row.requests));
	const siteRequests = siteCountry ? byCountry[siteCountry]?.requests ?? null : null;
	return {
		kind: 'choropleth', data: trafficGeography, featureKey: 'country', features, label: t('map.label'),
		selectedKey, activeKey, onSelect, onHover,
		flows: flows.map(row => ({
			key: row.country, from: trafficCountryAnchors[row.country], to: site!,
			color: `color-mix(in oklab, var(--color-chart-3) ${row.requests > 0 ? Math.min(100, row.errors / row.requests * 100) : 0}%, var(--color-chart-1))`,
			width: trafficFlowWidth(row.requests, flowMax) + (activeKey === row.country ? 1.5 : 0),
			dashed: row.errors > row.success, highlighted: activeKey === row.country,
			opacity: activeKey && activeKey !== row.country && activeKey !== siteCountry ? 0.35 : 1,
		})),
		anchor: site ? { coordinate: site, radius: siteRequests !== null && siteRequests > 0 ? 4 + 6 * (countryIntensity(siteRequests, max) ?? 0) : null } : undefined,
	};
}
