import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import { setLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-telemetry';
import type { GnocchiOverview, MetricMeasures, NativeMetric, NativePage, NativeResource, TelemetryAuthority } from '$lib/api/adminTelemetry';
import type * as AdminTelemetryApi from '$lib/api/adminTelemetry';

type MessageKey = Parameters<typeof t>[0];

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('$lib/api/adminTelemetry', async importOriginal => ({
	...await importOriginal<typeof AdminTelemetryApi>(),
	adminTelemetryRequest: mocks.request,
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'admin-a', sessionId: 'session-a', domainId: 'domain-a', identityDomainId: 'home-a', isSystemAdmin: true }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
}));

import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { TelemetryError } from '$lib/api/adminTelemetry';
// Exercise the actual route and dashboard; do not replace the consumer with a controller stub.
import Page from '../../../../routes/admin/monitoring/gnocchi/+page.svelte';

const r1 = '10000000-0000-0000-0000-000000000001';
const r2 = '10000000-0000-0000-0000-000000000002';
const m1 = '20000000-0000-0000-0000-000000000001';
const m2 = '20000000-0000-0000-0000-000000000002';
const sampleTime = '2026-10-17T01:02:03+00:00';
const resource = (id = r1): NativeResource => ({ id, type: 'generic', project_id: 'tenant-a', metrics: { cpu: m1 } });
const metric = (id = m1): NativeMetric => ({ id, name: 'cpu', unit: 'ns', resource_id: r1, archive_policy_name: 'native-policy' });
const page = <T>(items: T[], next_marker: string | null = null): NativePage<T> => ({ status: 'available', error: null, items, next_marker, truncated: false });
const section = <T>(data: T) => ({ status: 'available' as const, error: null, data });
function overview(): GnocchiOverview {
	return {
		status: 'available', error: null, checked_at: sampleTime,
		capabilities: section({ aggregation_methods: ['mean', 'max'] }),
		processing: section({ storage: { measures_to_process: 0 } }),
		archive_policies: section([{ name: 'native-policy', back_window: 0, aggregation_methods: ['mean', 'max'], definition: [{ granularity: 60, points: 100, timespan: 6000 }] }]),
		archive_policy_rules: section([{ name: 'cpu-rule', metric_pattern: 'cpu*', archive_policy_name: 'native-policy' }]),
		resource_types: section(['generic', { name: 'instance' }]),
	};
}
function samples(value = 0, id = m1): MetricMeasures {
	return { status: 'available', error: null, metric: metric(id), measures: [{ timestamp: sampleTime, granularity: 300, value }], truncated: false };
}
function respond(path: string): unknown {
	const url = new URL(path, 'https://telemetry.test');
	if (url.pathname === '/gnocchi') return overview();
	if (url.pathname === '/gnocchi/resources') return page([resource()]);
	if (url.pathname === '/gnocchi/metrics') return page([metric(), metric(m2)]);
	if (url.pathname.includes('/measures')) return samples(0, url.pathname.split('/')[3]);
	throw new Error(`Unexpected test request: ${path}`);
}
const sectionUI = (key: MessageKey) => within(screen.getByRole('heading', { name: t(key) }).closest('section')!);
const pagination = (key: MessageKey) => within(screen.getByRole('group', { name: t(key) }));
async function settle() { await tick(); await Promise.resolve(); await tick(); }
async function selectFirstMetric() { await fireEvent.click(await screen.findByRole('button', { name: m1 })); }

beforeEach(() => {
	setLocale('en');
	auth.update(state => ({ ...state, token: 'token-a', projectId: 'project-a', userId: 'admin-a', sessionId: 'session-a', domainId: 'domain-a', identityDomainId: 'home-a', isSystemAdmin: true }));
	authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	mocks.request.mockReset().mockImplementation((path: string) => Promise.resolve(respond(path)));
});
afterEach(() => { cleanup(); setLocale('ko'); });

describe('Gnocchi route read-only service diagnostics', () => {
	it('keeps failed and partial sections independent from processing zero, policies, rules and inventory', async () => {
		const result = overview();
		result.status = 'partial';
		result.capabilities = { status: 'unavailable', error: 'safe_failure', data: null };
		result.archive_policies.status = 'partial';
		result.archive_policy_rules = { status: 'forbidden', error: 'safe_forbidden', data: null };
		mocks.request.mockImplementation((path: string) => {
			if (path === '/gnocchi') return Promise.resolve(result);
			if (path.startsWith('/gnocchi/resources?')) return Promise.reject(new TelemetryError(503, 'telemetry_unavailable'));
			return Promise.resolve(respond(path));
		});
		render(Page);
		await screen.findByRole('heading', { name: t('gnocchi.capabilities') });
		expect(sectionUI('gnocchi.capabilities').getByText(t('status.unavailable'))).toBeTruthy();
		expect(sectionUI('gnocchi.processing').getByText('0')).toBeTruthy();
		expect(sectionUI('gnocchi.archivePolicies').getByText(t('status.partial'))).toBeTruthy();
		expect(within(screen.getByRole('table', { name: t('gnocchi.archivePolicies') })).getByText('native-policy')).toBeTruthy();
		expect(sectionUI('gnocchi.archivePolicyRules').getByText(t('status.forbidden'))).toBeTruthy();
		expect(sectionUI('gnocchi.resources').getByText(t('gnocchi.unverifiedPage'))).toBeTruthy();
		expect(await screen.findByRole('button', { name: m1 })).toBeTruthy();
		expect(screen.getByText(t('gnocchi.processingHelp'))).toBeTruthy();
		expect(screen.getByRole('link', { name: t('gnocchi.aodh') }).getAttribute('href')).toBe('/admin/monitoring/aodh');
		expect(screen.queryByText('safe_failure')).toBeNull();
	});

	it('renders catalog absence instead of zero counts and leaves the sibling service reachable', async () => {
		const result = overview();
		result.status = 'not_configured';
		for (const key of ['capabilities', 'processing', 'archive_policies', 'archive_policy_rules', 'resource_types'] as const) {
			result[key] = { status: 'not_configured', error: 'telemetry_not_configured', data: null };
		}
		mocks.request.mockImplementation((path: string) => Promise.resolve(path === '/gnocchi' ? result : { ...page([]), status: 'not_configured' }));
		render(Page);
		await screen.findByRole('heading', { name: t('gnocchi.processing') });
		expect(sectionUI('gnocchi.processing').getByText(t('status.notConfigured'))).toBeTruthy();
		expect(sectionUI('gnocchi.processing').queryByText('0')).toBeNull();
		expect(sectionUI('gnocchi.resources').queryByText(t('gnocchi.loadedPage', { page: 1, count: 0 }))).toBeNull();
		expect(sectionUI('gnocchi.metrics').getByText(t('gnocchi.unverifiedPage'))).toBeTruthy();
		expect(screen.getByRole('link', { name: t('gnocchi.aodh') })).toBeTruthy();
	});

	it('allows successful inventories when the overview transport fails and refreshes explicitly without writes', async () => {
		mocks.request.mockImplementation((path: string) => path === '/gnocchi' ? Promise.reject(new TelemetryError(503, 'telemetry_unavailable')) : Promise.resolve(respond(path)));
		render(Page);
		await screen.findByRole('button', { name: m1 });
		expect(screen.getByText(t('status.unavailable'))).toBeTruthy();
		mocks.request.mockImplementation((path: string) => Promise.resolve(respond(path)));
		await fireEvent.click(screen.getAllByRole('button', { name: t('refresh') })[0]);
		await screen.findByRole('heading', { name: t('gnocchi.capabilities') });
		expect(mocks.request.mock.calls.filter(([path]) => path === '/gnocchi')).toHaveLength(2);
		for (const [, authority, options] of mocks.request.mock.calls) {
			expect(authority).toEqual({ token: 'token-a', projectId: 'project-a' });
			expect(options?.method ?? 'GET').toBe('GET');
		}
	});

	it('follows short resource pages using native markers through an explicit empty page and supports previous', async () => {
		mocks.request.mockImplementation((path: string) => {
			const url = new URL(path, 'https://telemetry.test');
			if (url.pathname === '/gnocchi/resources') {
				const marker = url.searchParams.get('marker');
				return Promise.resolve(marker === r2 ? page([]) : marker === r1 ? page([resource(r2)], r2) : page([resource()], r1));
			}
			return Promise.resolve(respond(path));
		});
		render(Page);
		await screen.findByRole('button', { name: r1 });
		expect(sectionUI('gnocchi.resources').getByText(t('gnocchi.loadedPage', { page: 1, count: 1 }))).toBeTruthy();
		await fireEvent.click(pagination('gnocchi.resources').getByRole('button', { name: t('next') }));
		await screen.findByRole('button', { name: r2 });
		expect(mocks.request).toHaveBeenCalledWith(`/gnocchi/resources?type=generic&limit=25&marker=${r1}`, expect.anything());
		await fireEvent.click(pagination('gnocchi.resources').getByRole('button', { name: t('next') }));
		await waitFor(() => expect(sectionUI('gnocchi.resources').getByText(t('gnocchi.emptyPage'))).toBeTruthy());
		expect((pagination('gnocchi.resources').getByRole('button', { name: t('next') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(pagination('gnocchi.resources').getByRole('button', { name: t('previous') }));
		await screen.findByRole('button', { name: r2 });
	});

	it('pages metrics independently with native markers and does not infer completion from a short page', async () => {
		mocks.request.mockImplementation((path: string) => {
			const url = new URL(path, 'https://telemetry.test');
			if (url.pathname === '/gnocchi/metrics') {
				const marker = url.searchParams.get('marker');
				return Promise.resolve(marker === m2 ? page([]) : marker === m1 ? page([metric(m2)], m2) : page([metric()], m1));
			}
			return Promise.resolve(respond(path));
		});
		render(Page);
		await screen.findByRole('button', { name: m1 });
		await fireEvent.click(pagination('gnocchi.metrics').getByRole('button', { name: t('next') }));
		await screen.findByRole('button', { name: m2 });
		expect(mocks.request).toHaveBeenCalledWith(`/gnocchi/metrics?limit=25&marker=${m1}`, expect.anything());
		expect(screen.getByRole('button', { name: r1 })).toBeTruthy();
		await fireEvent.click(pagination('gnocchi.metrics').getByRole('button', { name: t('next') }));
		await waitFor(() => expect(sectionUI('gnocchi.metrics').getByText(t('gnocchi.emptyPage'))).toBeTruthy());
		expect((pagination('gnocchi.metrics').getByRole('button', { name: t('next') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(pagination('gnocchi.metrics').getByRole('button', { name: t('previous') }));
		await screen.findByRole('button', { name: m2 });
	});

	it('selects named resource metric links and displays native units, timestamps, grain and measured zero in an accessible table', async () => {
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: r1 }));
		const link = screen.getByRole('button', { name: `cpu · ${m1}` });
		await fireEvent.click(link);
		const table = await screen.findByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` });
		const row = within(table).getAllByRole('row')[1];
		expect(within(row).getAllByRole('cell').map(cell => cell.textContent)).toEqual([sampleTime, '300', '0', 'ns']);
		expect(link.getAttribute('aria-pressed')).toBe('true');
		expect(within(table).getByRole('columnheader', { name: t('gnocchi.nativeGrain') })).toBeTruthy();
		expect(table.closest('[role="region"]')?.getAttribute('tabindex')).toBe('0');
		expect(sectionUI('gnocchi.measures').queryByText(t('gnocchi.noData'))).toBeNull();
		expect(mocks.request).toHaveBeenCalledWith(`/gnocchi/metrics/${m1}/measures?hours=1&aggregation=mean`, expect.anything());
	});

	it('distinguishes an empty successful window from measured zero and preserves raw non-percent values', async () => {
		mocks.request.mockImplementation((path: string) => Promise.resolve(path.includes('/measures') ? { ...samples(), measures: [] } : respond(path)));
		render(Page); await selectFirstMetric();
		await screen.findByText(t('gnocchi.noData'));
		expect(screen.queryByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` })).toBeNull();
		mocks.request.mockImplementation((path: string) => Promise.resolve(path.includes('/measures') ? samples(123456789.125) : respond(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('gnocchi.readMeasures') }));
		await screen.findByText('123456789.125');
		expect(screen.queryByText('123456789.125%')).toBeNull();
		expect(screen.queryByText(t('gnocchi.noData'))).toBeNull();
	});

	it('shows partial and truncated samples without representing incomplete absence as no data', async () => {
		mocks.request.mockImplementation((path: string) => Promise.resolve(path.includes('/measures') ? { ...samples(), status: 'partial', truncated: true, measures: [] } : respond(path)));
		render(Page); await selectFirstMetric();
		await screen.findByText(t('gnocchi.samplesTruncated'));
		expect(sectionUI('gnocchi.measures').getByText(t('status.partial'))).toBeTruthy();
		expect(screen.getByText(t('gnocchi.noVerifiedSamples'))).toBeTruthy();
		expect(screen.queryByText(t('gnocchi.noData'))).toBeNull();
		mocks.request.mockImplementation((path: string) => Promise.resolve(path.includes('/measures') ? { ...samples(0), status: 'partial', truncated: true } : respond(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('gnocchi.readMeasures') }));
		await screen.findByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` });
		expect(screen.getByText(t('gnocchi.samplesTruncated'))).toBeTruthy();
	});

	it('requires explicit measure reads and bounds hours and optional positive finite granularity', async () => {
		render(Page); await selectFirstMetric();
		await screen.findByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` });
		const initialCalls = mocks.request.mock.calls.length;
		const hoursInput = screen.getByLabelText(t('gnocchi.hours'));
		const grainInput = screen.getByLabelText(t('gnocchi.granularity'));
		const read = screen.getByRole('button', { name: t('gnocchi.readMeasures') }) as HTMLButtonElement;
		for (const value of ['0', '169', '1.5', '', 'Infinity']) {
			await fireEvent.input(hoursInput, { target: { value } });
			expect(read.disabled).toBe(true);
		}
		await fireEvent.input(hoursInput, { target: { value: '168' } });
		for (const value of ['0', '-1', 'Infinity', 'NaN']) {
			await fireEvent.input(grainInput, { target: { value } });
			expect(read.disabled).toBe(true);
		}
		await fireEvent.input(grainInput, { target: { value: '0.5' } });
		await fireEvent.change(screen.getByLabelText(t('gnocchi.aggregation')), { target: { value: 'max' } });
		expect(mocks.request.mock.calls).toHaveLength(initialCalls);
		expect(read.disabled).toBe(false);
		await fireEvent.click(read);
		await waitFor(() => expect(mocks.request).toHaveBeenCalledWith(`/gnocchi/metrics/${m1}/measures?hours=168&aggregation=max&granularity=0.5`, expect.anything()));
		await screen.findByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` });
		await fireEvent.input(grainInput, { target: { value: '' } });
		await fireEvent.input(hoursInput, { target: { value: '1' } });
		await fireEvent.click(read);
		await waitFor(() => expect(mocks.request).toHaveBeenLastCalledWith(`/gnocchi/metrics/${m1}/measures?hours=1&aggregation=max`, expect.anything()));
		expect(mocks.request.mock.calls.some(([path]) => path.includes('refresh=true'))).toBe(false);
	});

	it('does not invent a unit and distinguishes a measure read failure from an empty successful window', async () => {
		mocks.request.mockImplementation((path: string) => {
			if (path.startsWith('/gnocchi/metrics?')) return Promise.resolve(page([{ ...metric(), unit: null }]));
			if (path.includes('/measures')) return Promise.resolve({ ...samples(), metric: { ...metric(), unit: null } });
			return Promise.resolve(respond(path));
		});
		render(Page); await selectFirstMetric();
		const table = await screen.findByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` });
		expect(within(table).getByRole('cell', { name: t('gnocchi.unitUnknown') })).toBeTruthy();
		mocks.request.mockImplementation((path: string) => path.includes('/measures') ? Promise.reject(new TelemetryError(403, 'telemetry_forbidden')) : Promise.resolve(respond(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('gnocchi.readMeasures') }));
		await waitFor(() => expect(sectionUI('gnocchi.measures').getByText(t('status.forbidden'))).toBeTruthy());
		expect(screen.getByText(t('gnocchi.noVerifiedSamples'))).toBeTruthy();
		expect(screen.queryByText(t('gnocchi.noData'))).toBeNull();
		expect(screen.queryByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` })).toBeNull();
	});

	it.each(['resources', 'metrics'] as const)('does not label an empty partial %s page as a verified zero count', async kind => {
		mocks.request.mockImplementation((path: string) => Promise.resolve(path.startsWith(`/gnocchi/${kind}?`) ? { ...page([]), status: 'partial', truncated: true } : respond(path)));
		render(Page);
		await waitFor(() => expect(sectionUI(`gnocchi.${kind}`).getByText(t('gnocchi.unverifiedPage'))).toBeTruthy());
		expect(sectionUI(`gnocchi.${kind}`).getByText(t('status.partial'))).toBeTruthy();
		expect(sectionUI(`gnocchi.${kind}`).queryByText(t('gnocchi.loadedPage', { page: 1, count: 0 }))).toBeNull();
	});

	it('routes horizontal region keyboard navigation to the actual TableShell scroll viewport', async () => {
		render(Page); await selectFirstMetric();
		const table = await screen.findByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` });
		const region = table.closest('[role="region"]') as HTMLElement;
		const viewport = region.firstElementChild as HTMLElement;
		Object.defineProperties(viewport, { scrollWidth: { value: 500, configurable: true }, clientWidth: { value: 200, configurable: true } });
		await fireEvent.keyDown(region, { key: 'ArrowRight' });
		expect(viewport.scrollLeft).toBe(80);
		await fireEvent.keyDown(region, { key: 'ArrowLeft' });
		expect(viewport.scrollLeft).toBe(0);
		await fireEvent.keyDown(region, { key: 'End' });
		expect(viewport.scrollLeft).toBe(300);
		await fireEvent.keyDown(region, { key: 'Home' });
		expect(viewport.scrollLeft).toBe(0);
	});
});

describe('Gnocchi mounted consumer request ownership', () => {
	it('ignores a previous metric selection even when the same metric is selected again (ABA)', async () => {
		const old = Promise.withResolvers<MetricMeasures>();
		let reads = 0;
		mocks.request.mockImplementation((path: string) => {
			if (path.includes('/measures')) return ++reads === 1 ? old.promise : Promise.resolve(samples(42, path.includes(m2) ? m2 : m1));
			return Promise.resolve(respond(path));
		});
		render(Page); await selectFirstMetric();
		await fireEvent.click(screen.getByRole('button', { name: m2 }));
		await screen.findByText('42');
		await selectFirstMetric(); await screen.findByText('42');
		old.resolve(samples(987654)); await old.promise; await settle();
		expect(screen.queryByText('987654')).toBeNull();
		expect(screen.getByRole('button', { name: m1 }).getAttribute('aria-pressed')).toBe('true');
	});

	it.each([
		['gnocchi.hours', 'input', '2'],
		['gnocchi.aggregation', 'change', 'max'],
		['gnocchi.granularity', 'input', '60'],
	] as const)('invalidates pending measures immediately on %s changes before an explicit reread', async (key, event, value) => {
		const old = Promise.withResolvers<MetricMeasures>();
		mocks.request.mockImplementation((path: string) => path.includes('/measures') ? old.promise : Promise.resolve(respond(path)));
		render(Page); await selectFirstMetric();
		await fireEvent[event](screen.getByLabelText(t(key)), { target: { value } });
		old.resolve(samples(987654)); await old.promise; await settle();
		expect(screen.queryByText('987654')).toBeNull();
		expect(screen.getByText(t('gnocchi.pendingMeasures'))).toBeTruthy();
		mocks.request.mockImplementation((path: string) => Promise.resolve(path.includes('/measures') ? samples(42) : respond(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('gnocchi.readMeasures') }));
		await screen.findByText('42');
	});

	it('keeps a newer same-metric read when window controls return to the original range (ABA)', async () => {
		const old = Promise.withResolvers<MetricMeasures>();
		mocks.request.mockImplementation((path: string) => path.includes('/measures') ? old.promise : Promise.resolve(respond(path)));
		render(Page); await selectFirstMetric();
		const input = screen.getByLabelText(t('gnocchi.hours'));
		await fireEvent.input(input, { target: { value: '2' } });
		await fireEvent.input(input, { target: { value: '1' } });
		mocks.request.mockImplementation((path: string) => Promise.resolve(path.includes('/measures') ? samples(42) : respond(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('gnocchi.readMeasures') }));
		await screen.findByText('42');
		old.resolve(samples(987654)); await old.promise; await settle();
		expect(screen.queryByText('987654')).toBeNull();
		expect(screen.getByText('42')).toBeTruthy();
	});

	it('drops a late resource type page and clears resource links and measurements on type change', async () => {
		const old = Promise.withResolvers<NativePage<NativeResource>>();
		render(Page);
		await fireEvent.click(await screen.findByRole('button', { name: r1 }));
		await fireEvent.click(screen.getByRole('button', { name: `cpu · ${m1}` }));
		await screen.findByRole('table', { name: `${t('gnocchi.measures')} · ${m1}` });
		mocks.request.mockImplementation((path: string) => path.startsWith('/gnocchi/resources?') && path.includes('type=instance') ? old.promise : Promise.resolve(respond(path)));
		await fireEvent.change(screen.getByLabelText(t('gnocchi.resourceType')), { target: { value: 'instance' } });
		expect(screen.queryByRole('button', { name: `cpu · ${m1}` })).toBeNull();
		expect(screen.getByText(t('gnocchi.selectMetric'))).toBeTruthy();
		await fireEvent.change(screen.getByLabelText(t('gnocchi.resourceType')), { target: { value: 'generic' } });
		await screen.findByRole('button', { name: r1 });
		old.resolve(page([resource('late-resource-type')])); await old.promise; await settle();
		expect(screen.queryByRole('button', { name: 'late-resource-type' })).toBeNull();
		expect(mocks.request).toHaveBeenCalledWith('/gnocchi/resources?type=instance&limit=25', expect.anything());
	});

	it.each(['resources', 'metrics'] as const)('discards a late %s next page after returning to the previous marker', async kind => {
		const old = Promise.withResolvers<NativePage<NativeResource | NativeMetric>>();
		mocks.request.mockImplementation((path: string) => {
			const url = new URL(path, 'https://telemetry.test');
			if (url.pathname === `/gnocchi/${kind}`) {
				if (url.searchParams.has('marker')) return old.promise;
				return Promise.resolve(kind === 'resources' ? page([resource()], r1) : page([metric()], m1));
			}
			return Promise.resolve(respond(path));
		});
		render(Page);
		const id = kind === 'resources' ? r1 : m1;
		await screen.findByRole('button', { name: id });
		await fireEvent.click(pagination(`gnocchi.${kind}`).getByRole('button', { name: t('next') }));
		await fireEvent.click(pagination(`gnocchi.${kind}`).getByRole('button', { name: t('previous') }));
		await screen.findByRole('button', { name: id });
		old.resolve(page([kind === 'resources' ? resource('late-page') : metric('late-page')])); await old.promise; await settle();
		expect(screen.queryByRole('button', { name: 'late-page' })).toBeNull();
	});

	it('does not revive late overview, resource or metric snapshots after a same-task context ABA', async () => {
		const oldOverview = Promise.withResolvers<GnocchiOverview>();
		const oldResources = Promise.withResolvers<NativePage<NativeResource>>();
		const oldMetrics = Promise.withResolvers<NativePage<NativeMetric>>();
		mocks.request.mockImplementation((path: string) => path === '/gnocchi' ? oldOverview.promise : path.startsWith('/gnocchi/resources?') ? oldResources.promise : oldMetrics.promise);
		render(Page);
		await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(3));
		mocks.request.mockImplementation((path: string) => Promise.resolve(respond(path)));
		auth.update(state => ({ ...state, projectId: 'project-b' }));
		auth.update(state => ({ ...state, projectId: 'project-a' }));
		await screen.findByRole('button', { name: m1 });
		const stale = overview(); stale.processing = section({ stale_processing: 987654 });
		oldOverview.resolve(stale); oldResources.resolve(page([resource('late-resource')])); oldMetrics.resolve(page([metric('late-metric')]));
		await Promise.all([oldOverview.promise, oldResources.promise, oldMetrics.promise]); await settle();
		expect(screen.queryByText('987654')).toBeNull();
		expect(screen.queryByRole('button', { name: 'late-resource' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'late-metric' })).toBeNull();
	});

	it.each(['token', 'userId', 'sessionId', 'domainId', 'identityDomainId', 'projectId'] as const)('clears selected measures and drops late responses on %s replacement', async key => {
		const old = Promise.withResolvers<MetricMeasures>();
		mocks.request.mockImplementation((path: string) => path.includes('/measures') ? old.promise : Promise.resolve(respond(path)));
		render(Page); await selectFirstMetric();
		auth.update(state => ({ ...state, [key]: 'replacement' }));
		await screen.findByText(t('gnocchi.selectMetric'));
		old.resolve(samples(987654)); await old.promise; await settle();
		expect(screen.queryByText('987654')).toBeNull();
		expect(screen.queryByLabelText(t('gnocchi.hours'))).toBeNull();
		const expected: TelemetryAuthority = { token: key === 'token' ? 'replacement' : 'token-a', projectId: key === 'projectId' ? 'replacement' : 'project-a' };
		await waitFor(() => expect(mocks.request).toHaveBeenCalledWith('/gnocchi', expected));
	});

	it.each(['admin', 'ready', 'switching', 'logout'] as const)('clears private state and blocks new reads during %s authority loss', async kind => {
		const old = Promise.withResolvers<MetricMeasures>();
		mocks.request.mockImplementation((path: string) => path.includes('/measures') ? old.promise : Promise.resolve(respond(path)));
		render(Page); await selectFirstMetric();
		const reads = mocks.request.mock.calls.length;
		if (kind === 'admin') auth.update(state => ({ ...state, isSystemAdmin: false }));
		if (kind === 'ready') authReady.set(false);
		if (kind === 'switching') projectSwitching.set(true);
		if (kind === 'logout') logoutInProgress.set(true);
		await screen.findByText(t('gnocchi.accessRequired'));
		old.resolve(samples(987654)); await old.promise; await settle();
		expect(screen.queryByText('987654')).toBeNull();
		expect(screen.queryByRole('button', { name: m1 })).toBeNull();
		expect(mocks.request.mock.calls).toHaveLength(reads);
	});

	it('disposes its context on unmount so late reads cannot republish or trigger more requests', async () => {
		const old = Promise.withResolvers<MetricMeasures>();
		mocks.request.mockImplementation((path: string) => path.includes('/measures') ? old.promise : Promise.resolve(respond(path)));
		const view = render(Page); await selectFirstMetric();
		const reads = mocks.request.mock.calls.length;
		view.unmount();
		auth.update(state => ({ ...state, projectId: 'project-b' }));
		old.resolve(samples(987654)); await old.promise; await settle();
		expect(mocks.request.mock.calls).toHaveLength(reads);
		expect(screen.queryByText('987654')).toBeNull();
	});
});
