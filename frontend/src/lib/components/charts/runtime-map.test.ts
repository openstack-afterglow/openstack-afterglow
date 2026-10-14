import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import type { Root } from 'react-dom/client';
import { fireEvent, within } from '@testing-library/dom';
import { ChoroplethMap } from './runtime-map';
import type { ChoroplethSpec } from './mapTypes';
import { ChartHostProvider } from '$lib/vendor/bklit-ui/charts/host-config';
import { createTrafficMapSpec, trafficFlowWidth } from '$lib/utils/trafficMap';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { trafficCountryName } from '$lib/utils/trafficFormat';
import { t } from '$lib/i18n/ns/traffic-analytics';
import { metrics, observations } from '$lib/components/admin/traffic/__tests__/observations';

const viewport = vi.hoisted(() => ({ width: 720, height: 360 }));
// jsdom has no layout; retain actual Bklit projection/feature/tooltip rendering.
vi.mock('@visx/responsive', () => ({
	ParentSize: ({ children }: { children: (size: typeof viewport) => React.ReactNode }) => children(viewport),
}));

let container: HTMLDivElement;
let root: Root;
const options = { height: 360, locale: 'en-US', reducedMotion: true };
beforeEach(() => {
	initLocale('en'); viewport.width = 720; viewport.height = 360;
	vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
	container = document.createElement('div'); document.body.append(container);
	root = createRoot(container);
});
afterEach(async () => {
	await act(async () => root.unmount()); container.remove();
	vi.unstubAllGlobals(); initLocale('ko');
});

async function draw(spec: ChoroplethSpec) {
	await act(async () => {
		root.render(React.createElement(ChartHostProvider, { value: { reducedMotion: true }, children: React.createElement(ChoroplethMap, { spec, options }) }));
	});
}

describe('native Bklit choropleth adapter', () => {
	it('renders geographic native features with accessible selection and stable hover/focus nodes', async () => {
		const onSelect = vi.fn(), onHover = vi.fn();
		const spec = createTrafficMapSpec(observations().countries, 'KR', '', '', onSelect, onHover);
		await draw(spec);
		const map = within(container).getByRole('group', { name: t('map.label') });
		expect(map.getAttribute('aria-hidden')).toBeNull();
		const korea = within(map).getByRole('button', { name: `${trafficCountryName('KR')}: ${t('metrics.requests')} 10` });
		const zero = within(map).getByRole('button', { name: `${trafficCountryName('US')}: ${t('metrics.requests')} 0` });
		const absent = within(map).getByRole('button', { name: `${trafficCountryName('CA')}: ${t('noObservations')}` });
		expect(zero.getAttribute('fill')).not.toBe(absent.getAttribute('fill'));
		await act(async () => { fireEvent.mouseOver(korea); });
		expect(onHover).toHaveBeenLastCalledWith('KR');
		expect(within(map).getByRole('button', { name: korea.getAttribute('aria-label')! })).toBe(korea);
		await act(async () => { fireEvent.focusIn(korea); });
		expect(onHover).toHaveBeenLastCalledWith('KR');
		for (const key of ['Enter', ' ']) {
			await act(async () => { fireEvent.keyDown(korea, { key }); });
			expect(onSelect).toHaveBeenLastCalledWith('KR');
		}
		await act(async () => { fireEvent.click(korea); });
		expect(onSelect).toHaveBeenCalledTimes(3);
		await draw({ ...spec, selectedKey: 'KR', activeKey: 'KR' });
		expect(korea.getAttribute('aria-pressed')).toBe('true'); expect(korea.getAttribute('tabindex')).toBe('0');
		await act(async () => { fireEvent.mouseOut(korea); fireEvent.focusOut(korea); });
		expect(onHover).toHaveBeenLastCalledWith(null);
	});
	it('draws every located access-flow annotation through the native projection, retaining measured metadata', async () => {
		const countries = [
			{ ...metrics({ requests: 100, success: 90, errors: 10 }), country: 'US' },
			{ ...metrics({ requests: 10, success: 2, errors: 8 }), country: 'JP' },
			{ ...metrics({ requests: 50 }), country: 'KR' },
			{ ...metrics(), country: 'SG' }, { ...metrics(), country: 'XX' },
		];
		await draw(createTrafficMapSpec(countries, 'KR', 'JP', 'JP', vi.fn(), vi.fn()));
		const flows = [...container.querySelectorAll('.access-flow')];
		expect(flows.map(flow => flow.getAttribute('data-country'))).toEqual(['US', 'JP']);
		const [us, jp] = flows;
		expect(Number(us.getAttribute('stroke-width'))).toBe(4);
		expect(Number(jp.getAttribute('stroke-width'))).toBeCloseTo(trafficFlowWidth(10, 100) + 1.5);
		expect(us.getAttribute('stroke')).toContain('10%'); expect(jp.getAttribute('stroke')).toContain('80%');
		expect(us.getAttribute('stroke-dasharray')).toBeNull(); expect(jp.getAttribute('stroke-dasharray')).toBe('5 3');
		expect(jp.classList.contains('highlighted')).toBe(true); expect(us.getAttribute('opacity')).toBe('0.35');
		expect(container.querySelector('.access-flows')?.getAttribute('pointer-events')).toBe('none');
		expect(container.querySelector('.site-marker')).toBeTruthy();
		expect(Number(container.querySelector('.site-traffic-ring')?.getAttribute('r'))).toBeGreaterThan(4);
		for (const flow of flows) expect(flow.getAttribute('d')).not.toMatch(/NaN|Infinity/);
	});
	it('retains visible measured-zero flow without creating an absent site ring', async () => {
		await draw(createTrafficMapSpec([{ ...metrics({ requests: 0, success: 0, errors: 0 }), country: 'US' }], 'KR', '', '', vi.fn(), vi.fn()));
		const flow = container.querySelector('.access-flow')!;
		expect(flow.getAttribute('stroke-width')).toBe('1'); expect(flow.getAttribute('stroke')).toContain('0%');
		expect(flow.getAttribute('stroke-dasharray')).toBeNull();
		expect(container.querySelector('.site-marker')).toBeTruthy(); expect(container.querySelector('.site-traffic-ring')).toBeNull();
	});
	it.each([null, 'SG', 'XX'])('does not draw an invented site or flows for %s', async site => {
		await draw(createTrafficMapSpec(observations().countries, site, '', '', vi.fn(), vi.fn()));
		expect(container.querySelector('.site-marker')).toBeNull(); expect(container.querySelector('.access-flow')).toBeNull();
	});
	it.each([[320, 160], [768, 384], [1280, 640]])('keeps native map dimensions and annotation geometry bounded at %s×%s', async (width, height) => {
		viewport.width = width; viewport.height = height;
		await draw(createTrafficMapSpec(observations().countries, 'KR', '', '', vi.fn(), vi.fn()));
		const map = within(container).getByRole('group', { name: t('map.label') });
		expect(map.getAttribute('width')).toBe(String(width)); expect(map.getAttribute('height')).toBe(String(height));
		expect(container.querySelector('.access-flow')?.getAttribute('d')).not.toMatch(/NaN|Infinity/);
	});
	it('updates existing native features after observation refresh without turning missingness into zero', async () => {
		await draw(createTrafficMapSpec(observations().countries, 'KR', 'KR', 'KR', vi.fn(), vi.fn()));
		const korea = within(container).getByRole('button', { name: `${trafficCountryName('KR')}: ${t('metrics.requests')} 10` });
		await draw(createTrafficMapSpec([], 'KR', 'KR', 'KR', vi.fn(), vi.fn()));
		expect(within(container).getByRole('button', { name: `${trafficCountryName('KR')}: ${t('noObservations')}` })).toBe(korea);
		expect(korea.getAttribute('aria-pressed')).toBe('true');
		expect(container.querySelector('.access-flow')).toBeNull(); expect(container.querySelector('.site-traffic-ring')).toBeNull();
		expect(container.querySelector('.site-marker')).toBeTruthy();
	});
	it.each(['en', 'ko', 'ja', 'zh-CN'] as const)('localizes native observation labels in %s', async locale => {
		initLocale(locale);
		await draw(createTrafficMapSpec(observations().countries, 'KR', '', '', vi.fn(), vi.fn()));
		expect(within(container).getByRole('button', { name: `${trafficCountryName('US')}: ${t('metrics.requests')} 0` })).toBeTruthy();
		expect(within(container).getByRole('button', { name: `${trafficCountryName('CA')}: ${t('noObservations')}` })).toBeTruthy();
	});
});
