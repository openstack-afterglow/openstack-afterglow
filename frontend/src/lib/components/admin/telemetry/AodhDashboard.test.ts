import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get, writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as AdminTelemetry from '$lib/api/adminTelemetry';
import type { AodhDetail, AodhOverview, NativeAlarm, NativePage, TelemetryStatus } from '$lib/api/adminTelemetry';
import type * as SvelteReactivity from 'svelte/reactivity';

const viewport = vi.hoisted(() => ({ desktop: true }));
vi.mock('svelte/reactivity', async importOriginal => ({
	...await importOriginal<typeof SvelteReactivity>(),
	MediaQuery: class { get current() { return viewport.desktop; } },
}));

vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'user-a', sessionId: 'session-a', domainId: 'domain-a', identityDomainId: 'home-a', isSystemAdmin: true }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
}));
const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('$lib/api/adminTelemetry', async importOriginal => ({
	...await importOriginal<typeof AdminTelemetry>(),
	adminTelemetryRequest: mocks.request,
}));

import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-telemetry';
import { TelemetryError } from '$lib/api/adminTelemetry';
import AodhPage from '../../../../routes/admin/monitoring/aodh/+page.svelte';

const initialAuth = get(auth);
const firstId = '11111111-1111-4111-8111-111111111111';
const secondId = '22222222-2222-4222-8222-222222222222';
const thirdId = '33333333-3333-4333-8333-333333333333';
function alarm(id = firstId, name = 'CPU high', state = 'alarm'): NativeAlarm {
	return { alarm_id: id, name, state, type: 'gnocchi_resources_threshold', enabled: true, severity: 'moderate' };
}
function page(items: NativeAlarm[] = [], status: TelemetryStatus = 'available', marker: string | null = items.at(-1)?.alarm_id ?? null): NativePage<NativeAlarm> {
	return { status, error: status === 'available' ? null : 'telemetry_native_unavailable', items, next_marker: marker, truncated: false };
}
function overview(alarms = page([alarm()])): AodhOverview {
	return { status: 'available', error: null, checked_at: '2026-10-16T12:00:00Z', capabilities: { status: 'available', error: null, data: { api: { alarms: true } } }, alarms };
}
function details(value = alarm()): AodhDetail {
	return { status: 'available', error: null, alarm: value, history: { status: 'available', error: null, items: [{ event_id: 'event-a', type: 'state transition', timestamp: '2026-10-16T11:00:00Z', user_id: 'operator', project_id: 'project-a' }], next_marker: null, truncated: false } };
}
function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
async function settle() { await Promise.resolve(); await tick(); }
function count(label: string) {
	const region = screen.getByRole('region', { name: t('aodh.loadedCounts') });
	return within(region).getByText(label, { selector: 'dt' }).nextElementSibling?.textContent;
}
function readAlarm(name = 'CPU high') { return screen.getByRole('button', { name: t('aodh.selectNamed', { name }) }); }

beforeEach(() => {
	vi.resetAllMocks();
	viewport.desktop = true;
	initLocale('en');
	auth.set({ ...initialAuth }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	mocks.request.mockResolvedValue(overview());
});
afterEach(() => { cleanup(); auth.set({ ...initialAuth }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false); initLocale('ko'); });

describe('rendered Aodh route', () => {
	it('keeps compact alarm selection, history disclosure and native paging reachable', async () => {
		viewport.desktop = false;
		mocks.request.mockResolvedValueOnce(overview()).mockResolvedValueOnce(details()).mockResolvedValueOnce(page([alarm(secondId, 'Next alarm', 'ok')]));
		render(AodhPage);
		await fireEvent.click(await screen.findByRole('button', { name: t('aodh.selectNamed', { name: 'CPU high' }) }));
		const history = screen.getByRole('region', { name: t('history') });
		await within(history).findByText('state transition');
		expect(screen.queryByRole('table')).toBeNull();
		const disclosure = history.querySelector('summary');
		expect(disclosure).toBeTruthy();
		await fireEvent.click(disclosure!);
		expect(within(history).getByText('event-a')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('next') }));
		await screen.findByRole('button', { name: t('aodh.selectNamed', { name: 'Next alarm' }) });
		expect(mocks.request).toHaveBeenCalledTimes(3);
	});
	it('counts only verified current-page native states and opens without mutations', async () => {
		mocks.request.mockResolvedValue(overview(page([alarm(), alarm(secondId, 'Healthy', 'ok'), alarm(thirdId, 'No sample', 'insufficient data'), alarm('44444444-4444-4444-8444-444444444444', 'Unknown', 'new-native-state')])));
		render(AodhPage);
		await screen.findByRole('table', { name: t('aodh.alarms') });
		expect(count(t('aodh.loaded'))).toBe('4');
		expect(count(t('aodh.ok'))).toBe('1');
		expect(count(t('aodh.alarm'))).toBe('1');
		expect(count(t('aodh.insufficientData'))).toBe('1');
		expect(count(t('aodh.unknownState'))).toBe('1');
		expect(screen.getByText(t('aodh.loadedCountsHelp'))).toBeTruthy();
		expect(screen.getByText(t('aodh.capabilitiesHelp'))).toBeTruthy();
		expect(screen.getByRole('table', { name: t('aodh.alarms') }).getAttribute('tabindex')).toBe('0');
		expect(screen.getByRole('link', { name: t('aodh.create') }).getAttribute('href')).toBe('/admin/monitoring/aodh/settings?create=1');
		expect(screen.getByRole('link', { name: t('aodh.settings') }).getAttribute('href')).toBe('/admin/monitoring/aodh/settings');
		expect(screen.getByRole('link', { name: t('aodh.gnocchi') }).getAttribute('href')).toBe('/admin/monitoring/gnocchi');
		expect(mocks.request.mock.calls).toEqual([['/aodh?limit=25', { token: 'token-a', projectId: 'project-a' }]]);
	});

	it('distinguishes verified zero from an independent capabilities failure', async () => {
		const response = overview(page());
		response.status = 'partial'; response.capabilities = { status: 'forbidden', error: 'telemetry_native_forbidden', data: null };
		mocks.request.mockResolvedValue(response);
		render(AodhPage);
		await screen.findByText(t('aodh.emptyPage'));
		expect(count(t('aodh.loaded'))).toBe('0');
		expect(count(t('aodh.alarm'))).toBe('0');
		expect(screen.getByText(t('status.forbidden'))).toBeTruthy();
		expect(screen.getByText(t('status.partial'))).toBeTruthy();
		expect(screen.queryByText(t('aodh.countsUnknown'))).toBeNull();
	});

	it.each([
		['forbidden', 'status.forbidden'], ['not_configured', 'status.notConfigured'], ['unavailable', 'status.unavailable'], ['partial', 'status.partial'],
	] as const)('does not turn a native %s alarm page into verified zero or empty', async (status, message) => {
		mocks.request.mockResolvedValue(overview(page([], status)));
		render(AodhPage);
		const alarms = screen.getByRole('region', { name: t('aodh.alarms') });
		await within(alarms).findByText(t(message));
		expect(screen.getByText(t('aodh.countsUnknown'))).toBeTruthy();
		expect(screen.queryByText(t('aodh.emptyPage'))).toBeNull();
		expect(screen.getByRole('region', { name: t('aodh.loadedCounts') }).querySelector('dd')).toBeNull();
	});

	it('offers explicit retry for a failed request without fabricating zero', async () => {
		mocks.request.mockRejectedValueOnce(new TelemetryError(503, 'telemetry_unavailable')).mockResolvedValueOnce(page());
		render(AodhPage);
		const alarms = screen.getByRole('region', { name: t('aodh.alarms') });
		await within(alarms).findByText(t('status.unavailable'));
		expect(screen.queryByText(t('aodh.emptyPage'))).toBeNull();
		await fireEvent.click(within(alarms).getByRole('button', { name: t('retry') }));
		await screen.findByText(t('aodh.emptyPage'));
		expect(count(t('aodh.loaded'))).toBe('0');
	});

	it('filters natively, clears old counts during loading and ignores late filter results', async () => {
		const alarmRead = deferred<NativePage<NativeAlarm>>();
		const okRead = deferred<NativePage<NativeAlarm>>();
		mocks.request.mockResolvedValueOnce(overview()).mockReturnValueOnce(alarmRead.promise).mockReturnValueOnce(okRead.promise);
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') });
		const filter = screen.getByRole('combobox', { name: t('aodh.filter') });
		await fireEvent.change(filter, { target: { value: 'alarm' } });
		expect(screen.getByText(t('aodh.countsUnknown'))).toBeTruthy();
		expect(screen.queryByRole('table', { name: t('aodh.alarms') })).toBeNull();
		await fireEvent.change(filter, { target: { value: 'ok' } });
		okRead.resolve(page([alarm(secondId, 'Current OK', 'ok')]));
		await screen.findByRole('button', { name: t('aodh.selectNamed', { name: 'Current OK' }) });
		alarmRead.resolve(page([alarm(firstId, 'Late alarm')])); await settle();
		expect(screen.queryByText('Late alarm')).toBeNull();
		expect(count(t('aodh.ok'))).toBe('1'); expect(count(t('aodh.alarm'))).toBe('0');
		expect(mocks.request.mock.calls[1][0]).toBe('/aodh/alarms?limit=25&state=alarm');
		expect(mocks.request.mock.calls[2][0]).toBe('/aodh/alarms?limit=25&state=ok');
	});

	it('continues short marker pages until explicit empty, supports previous and refreshes the current page', async () => {
		mocks.request.mockResolvedValueOnce(overview()).mockResolvedValueOnce(page([alarm(secondId, 'Second page', 'ok')])).mockResolvedValueOnce(page()).mockResolvedValueOnce(page([alarm(secondId, 'Second page', 'ok')])).mockResolvedValueOnce(overview(page([alarm(thirdId, 'Refreshed page', 'insufficient data')])));
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') });
		await fireEvent.click(screen.getByRole('button', { name: t('next') }));
		await screen.findByText('Second page');
		expect(count(t('aodh.loaded'))).toBe('1');
		expect((screen.getByRole('button', { name: t('next') }) as HTMLButtonElement).disabled).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: t('next') }));
		await screen.findByText(t('aodh.endPage'));
		expect(count(t('aodh.loaded'))).toBe('0');
		expect((screen.getByRole('button', { name: t('next') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('previous') })); await screen.findByText('Second page');
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') })); await screen.findByText('Refreshed page');
		expect(count(t('aodh.loaded'))).toBe('1');
		expect(mocks.request.mock.calls.map(call => call[0])).toEqual(['/aodh?limit=25', `/aodh/alarms?limit=25&marker=${firstId}`, `/aodh/alarms?limit=25&marker=${secondId}`, `/aodh/alarms?limit=25&marker=${firstId}`, `/aodh?limit=25&marker=${firstId}`]);
	});

	it('resets pagination on filter change and rejects an older page result', async () => {
		const oldPage = deferred<NativePage<NativeAlarm>>();
		mocks.request.mockResolvedValueOnce(overview()).mockReturnValueOnce(oldPage.promise).mockResolvedValueOnce(page([alarm(secondId, 'Filtered only', 'insufficient data')]));
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') });
		await fireEvent.click(screen.getByRole('button', { name: t('next') }));
		await fireEvent.change(screen.getByRole('combobox', { name: t('aodh.filter') }), { target: { value: 'insufficient data' } });
		await screen.findByText('Filtered only'); oldPage.resolve(page([alarm(thirdId, 'Late page')])); await settle();
		expect(screen.queryByText('Late page')).toBeNull();
		expect((screen.getByRole('button', { name: t('previous') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.request.mock.calls[2][0]).toBe('/aodh/alarms?limit=25&state=insufficient+data');
	});

	it('keeps alarm details readable when history fails and renders all action URLs as nonlinks', async () => {
		const value = alarm();
		Object.assign(value, { description: 'Known description', state_reason: 'Native state reason', alarm_actions: ['https://receiver.invalid/alarm?secret=private-a'], ok_actions: ['log://'], insufficient_data_actions: ['https://receiver.invalid/missing?secret=private-b'], gnocchi_resources_threshold_rule: { metric: 'cpu', threshold: 0 }, time_constraints: [{ name: 'office', start: '0 9 * * *', duration: 3600 }], unexpected_secret: 'DO NOT RENDER', });
		const response = details(value); response.status = 'partial'; response.history = { status: 'forbidden', error: 'telemetry_native_forbidden', items: [], next_marker: null, truncated: false };
		mocks.request.mockResolvedValueOnce(overview()).mockResolvedValueOnce(response);
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') });
		await fireEvent.click(readAlarm());
		await screen.findByText('Known description');
		expect(screen.getByRole('link', { name: t('aodh.edit') }).getAttribute('href')).toBe(`/admin/monitoring/aodh/settings?alarm=${firstId}`);
		const history = screen.getByRole('region', { name: t('history') });
		expect(within(history).getByText(t('status.forbidden'))).toBeTruthy();
		expect(within(history).queryByText(t('aodh.historyEmpty'))).toBeNull();
		for (const url of [...value.alarm_actions!, ...value.ok_actions!, ...value.insufficient_data_actions!]) {
			expect(screen.getByText(url).tagName).toBe('CODE');
			expect(screen.queryByRole('link', { name: url })).toBeNull();
		}
		expect(screen.getByText(/"threshold": 0/)).toBeTruthy(); expect(screen.getByText(/"duration": 3600/)).toBeTruthy();
		expect(screen.queryByText('DO NOT RENDER')).toBeNull();
		expect(mocks.request.mock.calls.every(call => call.length === 2)).toBe(true);
	});

	it('renders a successful bounded history table separately from details and verified empty history', async () => {
		const response = details(); response.history.truncated = true;
		const emptyHistory = details(); emptyHistory.history.items = [];
		mocks.request.mockResolvedValueOnce(overview()).mockResolvedValueOnce(response).mockResolvedValueOnce(emptyHistory);
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') }); await fireEvent.click(readAlarm());
		const history = await screen.findByRole('table', { name: t('history') });
		expect(history.getAttribute('tabindex')).toBe('0'); expect(within(history).getByText('event-a')).toBeTruthy();
		expect(within(screen.getByRole('region', { name: t('history') })).getByText(t('truncated'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('aodh.detailRetry') })); await screen.findByText(t('aodh.historyEmpty'));
	});

	it('fences late details after selection changes, close and filter changes', async () => {
		const first = deferred<AodhDetail>(); const closing = deferred<AodhDetail>(); const filtering = deferred<AodhDetail>();
		mocks.request.mockResolvedValueOnce(overview(page([alarm(), alarm(secondId, 'Second')]))).mockReturnValueOnce(first.promise).mockResolvedValueOnce(details(alarm(secondId, 'Current second'))).mockReturnValueOnce(closing.promise).mockReturnValueOnce(filtering.promise).mockResolvedValueOnce(page());
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') });
		await fireEvent.click(readAlarm()); await fireEvent.click(readAlarm('Second')); await screen.findByText('Current second');
		first.resolve(details(alarm(firstId, 'Late first details'))); await settle(); expect(screen.queryByText('Late first details')).toBeNull();
		await fireEvent.click(readAlarm()); await fireEvent.click(screen.getByRole('button', { name: t('close') }));
		closing.resolve(details(alarm(firstId, 'Closed detail'))); await settle(); expect(screen.queryByText('Closed detail')).toBeNull();
		await fireEvent.click(readAlarm()); await fireEvent.change(screen.getByRole('combobox', { name: t('aodh.filter') }), { target: { value: 'ok' } });
		filtering.resolve(details(alarm(firstId, 'Filtered detail'))); await screen.findByText(t('aodh.emptyPage')); await settle();
		expect(screen.queryByText('Filtered detail')).toBeNull(); expect(screen.getByText(t('aodh.selectAlarm'))).toBeTruthy();
	});

	it('does not let a late overview overwrite a newer filtered page', async () => {
		const initial = deferred<AodhOverview>();
		mocks.request.mockReturnValueOnce(initial.promise).mockResolvedValueOnce(page([alarm(secondId, 'Current filtered', 'ok')]));
		render(AodhPage);
		await fireEvent.change(screen.getByRole('combobox', { name: t('aodh.filter') }), { target: { value: 'ok' } });
		await screen.findByText('Current filtered'); initial.resolve(overview(page([alarm(firstId, 'Late overview')]))); await settle();
		expect(screen.queryByText('Late overview')).toBeNull(); expect(count(t('aodh.ok'))).toBe('1');
		expect(screen.getByText(/"alarms": true/)).toBeTruthy();
	});

	it('clears private details synchronously on context ABA and rejects the late detail result', async () => {
		const lateDetail = deferred<AodhDetail>();
		const privateAlarm = alarm(); privateAlarm.alarm_actions = ['https://receiver.invalid/private'];
		mocks.request.mockResolvedValueOnce(overview()).mockResolvedValueOnce(details(privateAlarm)).mockReturnValueOnce(lateDetail.promise).mockResolvedValueOnce(overview(page([alarm(secondId, 'Fresh context')])));
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') }); await fireEvent.click(readAlarm());
		await screen.findByText('https://receiver.invalid/private');
		await fireEvent.click(screen.getByRole('button', { name: t('aodh.detailRetry') }));
		auth.update(value => ({ ...value, projectId: 'project-b' })); auth.update(value => ({ ...value, projectId: 'project-a' }));
		await screen.findByText('Fresh context');
		lateDetail.resolve(details(privateAlarm)); await settle();
		expect(screen.queryByText('https://receiver.invalid/private')).toBeNull(); expect(screen.getByText(t('aodh.selectAlarm'))).toBeTruthy();
		expect(mocks.request).toHaveBeenCalledTimes(4);
	});

	it('rejects an old overview across same-tick context ABA', async () => {
		const old = deferred<AodhOverview>();
		mocks.request.mockReturnValueOnce(old.promise).mockResolvedValueOnce(overview(page([alarm(secondId, 'Fresh A after ABA')])));
		render(AodhPage); await waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(1));
		auth.update(value => ({ ...value, token: 'token-b' })); auth.update(value => ({ ...value, token: 'token-a' }));
		await screen.findByText('Fresh A after ABA'); old.resolve(overview(page([alarm(firstId, 'Stale A before ABA')]))); await settle();
		expect(screen.queryByText('Stale A before ABA')).toBeNull(); expect(count(t('aodh.loaded'))).toBe('1');
	});

	it('rejects a late marker page across context ABA', async () => {
		const old = deferred<NativePage<NativeAlarm>>();
		mocks.request.mockResolvedValueOnce(overview()).mockReturnValueOnce(old.promise).mockResolvedValueOnce(overview(page([alarm(secondId, 'New context first page')])));
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') }); await fireEvent.click(screen.getByRole('button', { name: t('next') }));
		auth.update(value => ({ ...value, sessionId: 'session-b' })); auth.update(value => ({ ...value, sessionId: 'session-a' }));
		await screen.findByText('New context first page'); old.resolve(page([alarm(thirdId, 'Stale marker page')])); await settle();
		expect(screen.queryByText('Stale marker page')).toBeNull();
		expect((screen.getByRole('button', { name: t('previous') }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('treats nullable native metadata as unreported without inventing a known state', async () => {
		const value: NativeAlarm = { ...alarm(), state: null, description: null, severity: null, state_reason: null, state_timestamp: null, evaluate_timestamp: null, timestamp: null, project_id: null, user_id: null };
		mocks.request.mockResolvedValueOnce(overview(page([value]))).mockResolvedValueOnce(details(value));
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') });
		expect(count(t('aodh.unknownState'))).toBe('1'); expect(count(t('aodh.alarm'))).toBe('0');
		await fireEvent.click(readAlarm()); await screen.findByRole('link', { name: t('aodh.edit') });
		const selected = screen.getByRole('region', { name: t('aodh.selectedAlarm') });
		const state = within(selected).getByText(t('state'), { selector: 'dt' });
		expect(state.nextElementSibling?.textContent).toBe(t('aodh.notReported'));
	});

	it('clears loaded private fields and stops reads on authority loss', async () => {
		const privateAlarm = alarm(); privateAlarm.ok_actions = ['https://receiver.invalid/private-ok'];
		mocks.request.mockResolvedValueOnce(overview()).mockResolvedValueOnce(details(privateAlarm));
		render(AodhPage); await screen.findByRole('table', { name: t('aodh.alarms') }); await fireEvent.click(readAlarm()); await screen.findByText('https://receiver.invalid/private-ok');
		projectSwitching.set(true); await settle();
		expect(screen.queryByText('https://receiver.invalid/private-ok')).toBeNull(); expect(screen.getByText(t('aodh.authorityRequired'))).toBeTruthy();
		expect(mocks.request).toHaveBeenCalledTimes(2);
	});
});
