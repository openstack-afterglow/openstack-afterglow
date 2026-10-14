import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import TrafficCountryMap from '../TrafficCountryMap.svelte';
import TrafficTrend from '../TrafficTrend.svelte';
import TrafficCoverage from '../TrafficCoverage.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/traffic-analytics';
import { trafficCountryName, formatTrafficTime } from '$lib/utils/trafficFormat';
import { parseTrafficSnapshot } from '$lib/types/trafficAnalytics';
import { countryAnchor, createTrafficMapSpec, trafficCountryAnchors, trafficGeography, trafficFlowWidth } from '$lib/utils/trafficMap';
import en from '$lib/i18n/messages/en/traffic-analytics.json';
import ko from '$lib/i18n/messages/ko/traffic-analytics.json';
import ja from '$lib/i18n/messages/ja/traffic-analytics.json';
import zh from '$lib/i18n/messages/zh-CN/traffic-analytics.json';
import { metrics, observations } from './observations';

beforeEach(() => {
	initLocale('en');
	vi.stubGlobal('ResizeObserver', class {
		observe() {}
		unobserve() {}
		disconnect() {}
	});
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); initLocale('ko'); });

describe('service country schema and map geometry', () => {
	it.each([null, 'KR', 'US'])('accepts service country %s', (site_country) => {
		const snapshot = observations(); snapshot.coverage.site_country = site_country;
		expect(parseTrafficSnapshot(snapshot, 'backend', '24h').coverage.site_country).toBe(site_country);
	});
	it.each([undefined, '', 'XX', 'kr', 'Kr', 'KOR', 'K', ' KR', 'KR ', 'KR\n', '한국', 42, false])('rejects invalid service country %s', (site_country) => {
		const snapshot = observations();
		expect(() => parseTrafficSnapshot({ ...snapshot, coverage: { ...snapshot.coverage, site_country } }, 'backend', '24h')).toThrow('Invalid traffic schema');
	});
	it('anchors the largest closed exterior polygon rather than remote islands, holes or an open ring', () => {
		expect(countryAnchor({ type: 'MultiPolygon', coordinates: [
			[[[100, 10], [101, 10], [101, 11], [100, 11], [100, 10]]],
			[[[0, 0], [8, 0], [8, 4], [0, 4], [0, 0]], [[1, 1], [2, 1], [2, 2], [1, 1]]],
			[[[20, 20], [90, 20], [90, 90]]],
		] })).toEqual([4, 2]);
		expect(countryAnchor({ type: 'Point', coordinates: [0, 0] })).toBeNull();
		expect(countryAnchor({ type: 'Polygon', coordinates: [[[0, 0], [8, 0], [8, 4]]] })).toBeNull();
	});
	it('uses polygon area rather than distant bounding-box corners to choose the mainland', () => {
		expect(countryAnchor({ type: 'MultiPolygon', coordinates: [
			[[[0, 0], [100, 80], [101, 80], [0, 0]]],
			[[[20, 20], [40, 20], [40, 40], [20, 40], [20, 20]]],
		] })).toEqual([30, 30]);
	});
	it('scales observed flow width logarithmically, including measured zero', () => {
		expect(trafficFlowWidth(0, 100)).toBe(1);
		expect(trafficFlowWidth(100, 100)).toBe(4);
		expect(trafficFlowWidth(10, 100)).toBeGreaterThan(1);
		expect(trafficFlowWidth(10, 100)).toBeLessThan(4);
	});
});

describe('country map observations and equivalent controls', () => {
	it('ships detailed local geographic features with no invented unlocated or small-territory geometry', () => {
		expect(trafficGeography.features).toHaveLength(177);
		for (const code of ['US', 'KR', 'JP', 'CN', 'FR', 'BR', 'AU']) {
			const feature = trafficGeography.features.find(feature => feature.properties.country === code)!;
			expect(['Polygon', 'MultiPolygon']).toContain(feature.geometry.type);
			expect(trafficCountryAnchors[code].every(Number.isFinite)).toBe(true);
		}
		expect(trafficCountryAnchors.XX).toBeUndefined();
		expect(trafficCountryAnchors.SG).toBeUndefined();
	});
	it('keeps no observations, measured zero and unlocated values distinct at the chart boundary', () => {
		const spec = createTrafficMapSpec(observations().countries, null, '', '', vi.fn(), vi.fn());
		expect(spec.features.US.value).toBe(0);
		expect(spec.features.CA.value).toBeNull();
		expect(spec.features.US.fill).not.toBe(spec.features.CA.fill);
		expect(spec.features.US.label).toBe(`${trafficCountryName('US')}: ${t('metrics.requests')} 0`);
		expect(spec.features.CA.label).toBe(`${trafficCountryName('CA')}: ${t('noObservations')}`);
		expect(spec.features.XX).toBeUndefined();
		render(TrafficCountryMap, { countries: observations().countries });
		for (const key of ['map.zero', 'noObservations', 'map.low'] as const) expect(screen.getByText(t(key))).toBeTruthy();
		expect(screen.getByRole('button', { name: `${t('map.unknown')} (XX)` })).toBeTruthy();
	});
	it('supports ranking hover/focus, country select, ranking select and clearing without hiding unknown visitors', async () => {
		render(TrafficCountryMap, { countries: observations().countries });
		const korea = screen.getByRole('button', { name: `${trafficCountryName('KR')} (KR)` });
		const detail = screen.getByRole('region', { name: t('map.detail') });
		await fireEvent.pointerEnter(korea); expect(within(detail).getByText(`${trafficCountryName('KR')} (KR)`)).toBeTruthy();
		expect(within(detail).getAllByText(t('unknown')).length).toBeGreaterThan(0);
		await fireEvent.pointerLeave(korea.parentElement!); expect(within(detail).getByText(t('map.select'))).toBeTruthy();
		await fireEvent.focus(korea); expect(within(detail).getByText(`${trafficCountryName('KR')} (KR)`)).toBeTruthy();
		await fireEvent.focusOut(korea); await fireEvent.click(korea); expect(korea.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.change(screen.getByLabelText(t('map.select')), { target: { value: 'CA' } }); expect(within(detail).getByText(t('noObservations'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: `${t('map.unknown')} (XX)` })); expect(within(detail).getByText(`${t('map.unknown')} (XX)`)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('map.clear') })); expect(within(detail).getByText(t('map.select'))).toBeTruthy();
	});
	it('keeps observed small territories reachable even when the source map omits their polygons', async () => {
		render(TrafficCountryMap, { countries: [{ ...metrics({ unique_visitors: null }), country: 'SG' }] });
		await fireEvent.click(screen.getByRole('button', { name: `${trafficCountryName('SG')} (SG)` }));
		expect(within(screen.getByRole('region', { name: t('map.detail') })).getByText(`${trafficCountryName('SG')} (SG)`)).toBeTruthy();
		expect((screen.getByLabelText(t('map.select')) as HTMLSelectElement).value).toBe('SG');
	});
	it.each([null, 'SG', 'XX'])('does not invent service geometry for site country %s', (siteCountry) => {
		const spec = createTrafficMapSpec(observations().countries, siteCountry, '', '', vi.fn(), vi.fn());
		expect(spec.flows).toEqual([]); expect(spec.anchor).toBeUndefined();
		render(TrafficCountryMap, { countries: observations().countries, siteCountry });
		expect(screen.getByText(t(siteCountry ? 'map.flows.noShape' : 'map.flows.unconfigured'))).toBeTruthy();
		expect(screen.getByText(t('map.flows.note'))).toBeTruthy();
	});
	it('keeps all observed flow width, error share/pattern, highlight and site-ring metadata', () => {
		const countries = [
			{ ...metrics({ requests: 100, success: 90, errors: 10 }), country: 'US' },
			{ ...metrics({ requests: 10, success: 2, errors: 8 }), country: 'JP' },
			{ ...metrics({ requests: 50 }), country: 'KR' },
			{ ...metrics(), country: 'SG' }, { ...metrics(), country: 'XX' }
		];
		const spec = createTrafficMapSpec(countries, 'KR', 'JP', 'JP', vi.fn(), vi.fn());
		expect(spec.flows?.map(flow => flow.key)).toEqual(['US', 'JP']);
		const [us, jp] = spec.flows!;
		expect(us.width).toBe(4); expect(jp.width).toBeCloseTo(trafficFlowWidth(10, 100) + 1.5);
		expect(us.color).toContain('10%'); expect(jp.color).toContain('80%');
		expect(jp.dashed).toBe(true); expect(us.dashed).toBe(false);
		expect(jp.highlighted).toBe(true); expect(jp.opacity).toBe(1); expect(us.opacity).toBe(0.35);
		expect(jp.to).toEqual(trafficCountryAnchors.KR); expect(jp.from).toEqual(trafficCountryAnchors.JP);
		expect(spec.anchor?.coordinate).toEqual(trafficCountryAnchors.KR); expect(spec.anchor?.radius).toBeGreaterThan(4);
		render(TrafficCountryMap, { countries, siteCountry: 'KR' });
		expect(screen.getByText(t('map.flows.sameCountry', { count: '50' }))).toBeTruthy();
	});
	it('keeps measured-zero flow visible without a false failure tint, and missing site traffic distinct', () => {
		const spec = createTrafficMapSpec(observations().countries, 'KR', '', '', vi.fn(), vi.fn());
		expect(spec.flows).toHaveLength(1);
		expect(spec.flows![0]).toMatchObject({ key: 'US', width: 1, dashed: false });
		expect(spec.flows![0].color).toContain('0%');
		const missingSite = createTrafficMapSpec([{ ...metrics(), country: 'US' }], 'KR', '', '', vi.fn(), vi.fn());
		expect(missingSite.anchor?.radius).toBeNull();
		render(TrafficCountryMap, { countries: [{ ...metrics(), country: 'US' }], siteCountry: 'KR' });
		expect(screen.getByText(t('map.flows.sameCountry', { count: t('noObservations') }))).toBeTruthy();
	});
	it('shows responses equal to status-observed requests alongside successes and failures', async () => {
		render(TrafficCountryMap, { countries: [{ ...metrics({ requests: 15, success: 11, errors: 4 }), country: 'KR' }], siteCountry: 'KR' });
		await fireEvent.click(screen.getByRole('button', { name: `${trafficCountryName('KR')} (KR)` }));
		const detail = within(screen.getByRole('region', { name: t('map.detail') }));
		for (const [key, value] of [['requests', '15'], ['responses', '15'], ['success', '11'], ['errors', '4']] as const) {
			expect(detail.getByText(t(`metrics.${key}`)).parentElement?.querySelector('dd')?.textContent).toBe(value);
		}
		expect(detail.getByText(t('map.responsesNote'))).toBeTruthy();
	});
	it.each(['en', 'ko', 'ja', 'zh-CN'] as const)('explains flow, error-pattern and location limitations in %s', (locale) => {
		initLocale(locale);
		render(TrafficCountryMap, { countries: observations().countries, siteCountry: 'KR' });
		for (const key of ['map.flows.note', 'map.flows.failure', 'map.flows.width'] as const) expect(screen.getByText(t(key))).toBeTruthy();
	});
});

describe('trends and source disclosures', () => {
	it('prints plotted min/max beside the autoscaled Spark and keeps timestamps available as text', () => {
		render(TrafficTrend, { snapshot: observations(), metric: 'requests' });
		expect(screen.getByText(t('trend.range', { min: '8', max: '10' }))).toBeTruthy();
		expect(screen.getByText(formatTrafficTime(1700000000))).toBeTruthy();
	});
	it('does not draw across a gap or infer a wave when only one observation remains', () => {
		const snapshot = observations({ series: [{ at: 100, metrics: metrics({ requests: 1 }) }, { at: 200, metrics: null }, { at: 300, metrics: metrics({ requests: 10 }) }] });
		render(TrafficTrend, { snapshot, metric: 'requests' });
		expect(screen.getByText(t('trend.awaiting'))).toBeTruthy();
		expect(screen.getByText(t('unknown'))).toBeTruthy();
	});
	it('shows byte and visitor identity coverage without substituting zero for unknown values', () => {
		const { unmount } = render(TrafficTrend, { snapshot: observations(), metric: 'request_bytes' });
		expect(screen.getAllByText(t('unknown')).length).toBeGreaterThan(0);
		expect(screen.getByText(t('bytes.coverage', { known: '0', total: '10' }))).toBeTruthy(); unmount();
		render(TrafficTrend, { snapshot: observations(), metric: 'unique_visitors' });
		expect(screen.getByText(t('unique.coverage', { known: '8', total: '10' }))).toBeTruthy();
	});
	it.each(['en', 'ko', 'ja', 'zh-CN'] as const)('renders complete privacy and source-freshness disclosures in %s', (locale) => {
		initLocale(locale); const snapshot = observations({ source: 'frontend' });
		render(TrafficCoverage, { snapshot, source: 'frontend' });
		for (const key of ['coverage.source', 'coverage.frontend', 'coverage.proxy', 'coverage.privacy', 'coverage.bytes', 'coverage.latency', 'coverage.freshness', 'coverage.lastObserved'] as const) expect(screen.getByText(t(key))).toBeTruthy();
		expect(screen.getByText(formatTrafficTime(snapshot.coverage.last_observed_at))).toBeTruthy();
		expect(screen.getByText(t('coverage.retention', { days: '30' }))).toBeTruthy();
	});
	it('keeps unknown reporter drops and absent source timestamps unknown rather than claiming a healthy reporter', () => {
		const snapshot = observations(); snapshot.coverage.last_observed_at = null; snapshot.coverage.observed_since = null;
		render(TrafficCoverage, { snapshot, source: 'backend' });
		expect(screen.getAllByText(t('unknown')).length).toBeGreaterThanOrEqual(3);
		expect(screen.getByText(t('coverage.freshness'))).toBeTruthy();
	});
	it('keeps matching namespace keys and ICU substitution names in every catalog', () => {
		const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();
		for (const catalog of [en, ja, zh]) {
			expect(Object.keys(catalog).sort()).toEqual(Object.keys(ko).sort());
			for (const key of Object.keys(ko) as Array<keyof typeof ko>) {
				expect(catalog[key].length).toBeGreaterThan(0); expect(placeholders(catalog[key])).toEqual(placeholders(ko[key]));
			}
		}
	});
});
