import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get, writable } from 'svelte/store';
import { tick } from 'svelte';
import { setLocale } from '$lib/i18n/runtime.svelte';
import type { AlarmType, AlarmWrite, AodhDetail, NativeAlarm, NativePage, TelemetryAuthority } from '$lib/api/adminTelemetry';
import type * as TelemetryModule from '$lib/api/adminTelemetry';

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('$lib/api/adminTelemetry', async importOriginal => ({
	...await importOriginal<typeof TelemetryModule>(),
	adminTelemetryRequest: mocks.request,
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'admin-a', sessionId: 'session-a', isSystemAdmin: true }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
}));

import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { TelemetryError } from '$lib/api/adminTelemetry';
import { dialogState } from '$lib/stores/confirm.svelte';
import ConfirmDialog from '$lib/components/ui/ConfirmDialog.svelte';
import Page from './+page.svelte';

const id = '11111111-1111-4111-8111-111111111111';
const otherId = '22222222-2222-4222-8222-222222222222';
const types: AlarmType[] = ['gnocchi_resources_threshold', 'gnocchi_aggregation_by_metrics_threshold', 'gnocchi_aggregation_by_resources_threshold', 'event', 'composite', 'loadbalancer_member_health', 'prometheus'];
const initialAuth = get(auth);
const rule = { metric: 'cpu', query: { and: [{ '=': { project_id: 'project-a' } }, { '>': { vcpus: 2 } }] },
	threshold: 72.25, comparison_operator: 'ge', granularity: 300, evaluation_periods: 4,
	resource_type: 'instance', aggregation_method: '95pct', provider_extension: { nested: [false, null, { exact: 'keep' }] } };
const constraints = [{ name: 'business hours', start: '0 9 * * 1-5', duration: 28800, timezone: 'Asia/Seoul', extension: { keep: [1, 2] } }];
function alarm(type: AlarmType = 'gnocchi_resources_threshold', overrides: Partial<NativeAlarm> = {}): NativeAlarm {
	return { alarm_id: id, name: 'CPU alarm', description: 'Original description', type, enabled: false, repeat_actions: true,
		severity: 'critical', state: 'ok', project_id: 'project-a', user_id: 'admin-a', timestamp: '2026-10-17T00:00:00Z',
		alarm_actions: ['https://private.example.invalid/alarm?secret=original'], ok_actions: ['log://'],
		insufficient_data_actions: ['zaqar://missing-data'], time_constraints: structuredClone(constraints),
		[`${type}_rule`]: structuredClone(rule), ...overrides };
}
function page(items: NativeAlarm[], next_marker: string | null = null, status: NativePage<NativeAlarm>['status'] = 'available'): NativePage<NativeAlarm> {
	return { status, error: null, items, next_marker, truncated: !!next_marker };
}
function detail(value: NativeAlarm | null): AodhDetail {
	return { status: value ? 'available' : 'not_found', error: null, alarm: value,
		history: { status: 'available', error: null, items: [], next_marker: null, truncated: false } };
}
let current: NativeAlarm;
let list: NativePage<NativeAlarm>;
let mutationFailure: Error | null;
let readFailure: Error | null;
const writes = () => mocks.request.mock.calls.filter(call => call[2]?.method && call[2].method !== 'GET');
const button = (name: string) => screen.getByRole('button', { name }) as HTMLButtonElement;
const field = (name: string, role: 'textbox' | 'checkbox' | 'combobox' = 'textbox') => screen.getByRole(role, { name }) as HTMLInputElement | HTMLTextAreaElement;
async function input(name: string, value: string) { await fireEvent.input(field(name), { target: { value } }); }
async function choose() {
	await fireEvent.click(await screen.findByRole('button', { name: 'CPU alarm' }));
	await screen.findByRole('dialog', { name: 'Edit alarm' });
}
function mount() { render(Page); render(ConfirmDialog); }
async function confirm(name: RegExp, action: 'Save alarm' | 'Delete alarm', accept = true) {
	const dialog = await screen.findByRole('dialog', { name });
	await fireEvent.click(within(dialog).getByRole('button', { name: accept ? action : 'Cancel' }));
}

beforeEach(() => {
	setLocale('en'); window.history.replaceState({}, '', '/admin/monitoring/aodh/settings');
	auth.set({ ...initialAuth, token: 'token-a', projectId: 'project-a', userId: 'admin-a', sessionId: 'session-a', isSystemAdmin: true });
	authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	current = alarm(); list = page([current]); mutationFailure = null; readFailure = null;
	mocks.request.mockReset();
	mocks.request.mockImplementation(async (path: string, _authority: TelemetryAuthority, options?: { method?: string; body?: AlarmWrite }) => {
		if (options?.method) {
			if (mutationFailure) throw mutationFailure;
			if (options.method === 'DELETE') { list = page([]); return; }
			current = { ...current, ...options.body, alarm_id: options.method === 'POST' ? otherId : current.alarm_id };
			list = page([current]); return current;
		}
		if (readFailure) throw readFailure;
		return path.startsWith('/aodh/alarms?') ? list : detail(current);
	});
});
afterEach(() => { dialogState.reject(); cleanup(); auth.set(initialAuth); setLocale('ko'); });

describe('Aodh settings consumer', () => {
	it.each(types)('roundtrips the complete %s native definition without simplifying nested fields', async type => {
		current = alarm(type); list = page([current]);
		mount(); await choose();
		expect(JSON.parse(field('Rule JSON').value)).toEqual(rule);
		expect(JSON.parse(field('Time constraints JSON').value)).toEqual(constraints);
		expect((field('Enabled', 'checkbox') as HTMLInputElement).checked).toBe(false);
		expect((field('Repeat actions', 'checkbox') as HTMLInputElement).checked).toBe(true);
		await input('Name', 'Renamed alarm'); await input('Description', 'Edited description');
		await fireEvent.click(field('Enabled', 'checkbox')); await fireEvent.click(field('Repeat actions', 'checkbox'));
		await fireEvent.change(field('Severity', 'combobox'), { target: { value: 'moderate' } });
		await fireEvent.click(button('Save alarm'));
		await waitFor(() => expect(writes()).toHaveLength(1));
		expect(writes()[0]).toEqual([`/aodh/alarms/${id}`, { token: 'token-a', projectId: 'project-a' }, { method: 'PUT', body: {
			name: 'Renamed alarm', description: 'Edited description', type, enabled: true, repeat_actions: false, severity: 'moderate',
			alarm_actions: current.alarm_actions, ok_actions: ['log://'], insufficient_data_actions: ['zaqar://missing-data'],
			time_constraints: constraints, [`${type}_rule`]: rule,
		} }]);
		await screen.findByText('Alarm saved.');
		await fireEvent.click(await screen.findByRole('button', { name: 'Renamed alarm' }));
		await screen.findByRole('dialog', { name: 'Edit alarm' });
		expect(field('Name').value).toBe('Renamed alarm'); expect(JSON.parse(field('Rule JSON').value)).toEqual(rule);
	});

	it('honors ?create=1 and creates a guided resource threshold with all three independent action lists', async () => {
		window.history.replaceState({}, '', '?create=1'); mount();
		await screen.findByRole('dialog', { name: 'Create alarm' });
		await input('Name', 'New threshold'); await input('Metric', 'cpu');
		await input('Resource ID', otherId);
		await input('Threshold', '0'); await input('Granularity (seconds)', '300'); await input('Evaluation periods', '3');
		await input('Alarm action URLs', 'https://receiver.example.invalid/a\nhttp://receiver.example.invalid/b');
		await input('OK action URLs', 'log://\nzaqar://recovery');
		await input('Insufficient data action URLs', 'https://receiver.example.invalid/missing');
		await fireEvent.click(button('Save alarm'));
		await waitFor(() => expect(writes()).toHaveLength(1));
		expect(writes()[0][2]).toEqual({ method: 'POST', body: {
			name: 'New threshold', description: '', type: 'gnocchi_resources_threshold', enabled: true, repeat_actions: false, severity: 'low',
			time_constraints: [], alarm_actions: ['https://receiver.example.invalid/a', 'http://receiver.example.invalid/b'],
			ok_actions: ['log://', 'zaqar://recovery'], insufficient_data_actions: ['https://receiver.example.invalid/missing'],
			gnocchi_resources_threshold_rule: { metric: 'cpu', resource_type: 'instance', resource_id: otherId,
				aggregation_method: 'mean', comparison_operator: 'gt', threshold: 0, granularity: 300, evaluation_periods: 3 },
		} });
	});

	it('honors ?alarm=UUID with a fresh detail read and exposes a dashboard link', async () => {
		window.history.replaceState({}, '', `?alarm=${id}`); mount();
		await screen.findByRole('dialog', { name: 'Edit alarm' });
		expect(field('Name').value).toBe('CPU alarm');
		expect(mocks.request).toHaveBeenCalledWith(`/aodh/alarms/${id}`, { token: 'token-a', projectId: 'project-a' });
		await fireEvent.click(button('Cancel'));
		expect(screen.getByRole('link', { name: 'Alarm dashboard' }).getAttribute('href')).toBe('/admin/monitoring/aodh');
		expect(screen.queryByRole('link', { name: /receiver\.example/ })).toBeNull();
	});

	it('pages the native list and selects a detail from the next page', async () => {
		list = page([current], id); mount();
		await screen.findByRole('button', { name: 'CPU alarm' });
		list = page([alarm('event', { alarm_id: otherId, name: 'Second page alarm' })]); current = list.items[0];
		await fireEvent.click(button('Next page'));
		await screen.findByRole('button', { name: 'Second page alarm' });
		expect(mocks.request).toHaveBeenCalledWith(`/aodh/alarms?limit=25&marker=${id}`, expect.anything());
		await fireEvent.click(button('Second page alarm')); await screen.findByRole('dialog', { name: 'Edit alarm' });
		expect(field('Name').value).toBe('Second page alarm');
	});

	it('awaits visible trust confirmation for every state list and submits all supported schemes unchanged', async () => {
		mount(); await choose();
		await input('Alarm action URLs', 'https://receiver.example.invalid/a\nhttp://receiver.example.invalid/b\ntrust+http://receiver.example.invalid/c');
		await input('OK action URLs', 'trust+https://receiver.example.invalid/d\nlog://');
		await input('Insufficient data action URLs', 'zaqar://missing\ntrust+zaqar://missing\ntrust+heat://region/stack/policy');
		await fireEvent.click(button('Save alarm'));
		await screen.findByRole('dialog', { name: /Save these trust actions/ }); expect(writes()).toHaveLength(0);
		await confirm(/Save these trust actions/, 'Save alarm', false); expect(writes()).toHaveLength(0);
		await fireEvent.click(button('Save alarm')); await confirm(/Save these trust actions/, 'Save alarm');
		await waitFor(() => expect(writes()).toHaveLength(1));
		expect(writes()[0][2].body).toMatchObject({
			alarm_actions: ['https://receiver.example.invalid/a', 'http://receiver.example.invalid/b', 'trust+http://receiver.example.invalid/c'],
			ok_actions: ['trust+https://receiver.example.invalid/d', 'log://'],
			insufficient_data_actions: ['zaqar://missing', 'trust+zaqar://missing', 'trust+heat://region/stack/policy'],
		});
	});

	it.each(['OK action URLs', 'Insufficient data action URLs'])('requires trust confirmation when only %s delegates authority', async label => {
		mount(); await choose(); await input(label, 'trust+https://receiver.example.invalid/authority');
		await fireEvent.click(button('Save alarm')); await screen.findByRole('dialog', { name: /Save these trust actions/ });
		expect(writes()).toHaveLength(0); await confirm(/Save these trust actions/, 'Save alarm');
		await waitFor(() => expect(writes()).toHaveLength(1));
	});

	it.each(['mailto:ops@example.invalid', 'smtp://mail.example.invalid', 'javascript:alert(1)', 'trust+https://trust-id:delete@receiver.example.invalid/a'])('rejects unsupported or injected-authority action %s before mutation', async url => {
		mount(); await choose(); await input('Alarm action URLs', url); await fireEvent.click(button('Save alarm'));
		expect(writes()).toHaveLength(0); expect(screen.queryByRole('dialog', { name: /Save these trust actions/ })).toBeNull();
		expect(screen.getAllByText(/Check the JSON object\/array shapes/).length).toBeGreaterThan(0);
	});

	it('awaits deletion confirmation and does not force alarm state or submit a body', async () => {
		mount(); await choose(); await fireEvent.click(button('Delete alarm'));
		await screen.findByRole('dialog', { name: /Delete this native alarm/ }); expect(writes()).toHaveLength(0);
		await confirm(/Delete this native alarm/, 'Delete alarm', false); expect(writes()).toHaveLength(0);
		await fireEvent.click(button('Delete alarm')); await confirm(/Delete this native alarm/, 'Delete alarm');
		await screen.findByText('Alarm deleted.');
		expect(writes()).toEqual([[`/aodh/alarms/${id}`, { token: 'token-a', projectId: 'project-a' }, { method: 'DELETE' }]]);
	});

	it.each(['Save alarm', 'Delete alarm'] as const)('discards a late %s confirmation after synchronous context A → B → A', async action => {
		mount(); await choose();
		if (action === 'Save alarm') await input('Alarm action URLs', 'trust+https://private.example.invalid/delegate');
		await fireEvent.click(button(action));
		const prompt = action === 'Save alarm' ? /Save these trust actions/ : /Delete this native alarm/;
		await screen.findByRole('dialog', { name: prompt });
		auth.update(state => ({ ...state, token: 'token-b', projectId: 'project-b' }));
		auth.update(state => ({ ...state, token: 'token-a', projectId: 'project-a' }));
		await tick();
		expect(screen.queryByDisplayValue(/private\.example/)).toBeNull();
		await confirm(prompt, action); await tick(); expect(writes()).toHaveLength(0);
		expect(screen.queryByRole('dialog', { name: 'Edit alarm' })).toBeNull();
	});

	it.each(['Save alarm', 'Delete alarm'] as const)('rechecks the complete draft fingerprint after awaiting %s confirmation', async action => {
		mount(); await choose(); await input('Alarm action URLs', 'trust+https://receiver.example.invalid/delegate');
		const name = field('Name'); await fireEvent.click(button(action));
		const prompt = action === 'Save alarm' ? /Save these trust actions/ : /Delete this native alarm/;
		await screen.findByRole('dialog', { name: prompt });
		// Simulate an independently arriving draft update even though user controls are disabled.
		await fireEvent.input(name, { target: { value: 'Changed during confirmation' } });
		await confirm(prompt, action); await tick(); expect(writes()).toHaveLength(0);
	});

	it('clears all private data on context change and discards late detail reads rather than replacing a new draft', async () => {
		const pending = Promise.withResolvers<AodhDetail>();
		mocks.request.mockImplementation((path: string) => path.startsWith('/aodh/alarms?') ? Promise.resolve(list) : pending.promise);
		mount(); await fireEvent.click(await screen.findByRole('button', { name: 'CPU alarm' }));
		auth.update(state => ({ ...state, projectId: 'project-b', token: 'token-b' }));
		list = page([]); await tick();
		await fireEvent.click(button('Create alarm')); await screen.findByRole('dialog', { name: 'Create alarm' });
		await input('Name', 'Fresh project draft'); pending.resolve(detail(alarm())); await pending.promise; await tick();
		expect(field('Name').value).toBe('Fresh project draft');
		expect(screen.queryByDisplayValue(/private\.example/)).toBeNull();
	});

	it.each(['Save alarm', 'Delete alarm'] as const)('locks %s after an ambiguous mutation and requires an explicit successful affected-alarm reread', async action => {
		mutationFailure = new TelemetryError(503, 'telemetry_mutation_uncertain', true);
		mount(); await choose(); await fireEvent.click(button(action));
		if (action === 'Delete alarm') await confirm(/Delete this native alarm/, 'Delete alarm');
		await waitFor(() => expect(screen.getAllByText(/The mutation outcome is unknown/).length).toBeGreaterThan(0));
		expect(button('Delete alarm').disabled).toBe(true); expect(writes()).toHaveLength(1);
		await fireEvent.click(button('Save alarm')); await fireEvent.click(button('Delete alarm')); expect(writes()).toHaveLength(1);
		readFailure = new TelemetryError(503, 'telemetry_unavailable');
		const modal = screen.getByRole('dialog', { name: 'Edit alarm' });
		await fireEvent.click(within(modal).getByRole('button', { name: 'Reread affected alarm' }));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Edit alarm' })).toBeNull());
		expect(button('Create alarm').disabled).toBe(true);
		readFailure = null; current = alarm('gnocchi_resources_threshold', { name: 'Provider current value' }); list = page([current]);
		await fireEvent.click(button('Reread affected alarm')); await screen.findByRole('dialog', { name: 'Edit alarm' });
		expect(field('Name').value).toBe('Provider current value'); expect(button('Save alarm').disabled).toBe(false);
		expect(button('Delete alarm').disabled).toBe(false); expect(writes()).toHaveLength(1);
	});

	it('keeps an uncertain create locked through partial list reads and unlocks only a successful explicit list reread', async () => {
		window.history.replaceState({}, '', '?create=1'); mutationFailure = new TelemetryError(503, 'telemetry_unavailable', true);
		mount(); await screen.findByRole('dialog', { name: 'Create alarm' }); await input('Name', 'Uncertain create'); await input('Metric', 'cpu');
		await input('Resource ID', otherId);
		await fireEvent.click(button('Save alarm'));
		await waitFor(() => expect(screen.getAllByText(/The mutation outcome is unknown/).length).toBeGreaterThan(0));
		expect(writes()).toHaveLength(1);
		list = page([], null, 'partial');
		await fireEvent.click(within(screen.getByRole('dialog', { name: 'Create alarm' })).getByRole('button', { name: 'Reread alarms' }));
		await tick(); expect(button('Save alarm').disabled).toBe(true);
		list = page([]); await fireEvent.click(within(screen.getByRole('dialog', { name: 'Create alarm' })).getByRole('button', { name: 'Reread alarms' }));
		await screen.findByText('Native data reread successfully. Review the current alarm before making another change.');
		expect(screen.queryByDisplayValue('Uncertain create')).toBeNull(); expect(button('Create alarm').disabled).toBe(false);
		expect(writes()).toHaveLength(1);
	});

	it('does not replay definitive authorization failures or reinterpret them as success', async () => {
		mutationFailure = new TelemetryError(401, 'telemetry_auth_required'); mount(); await choose(); await fireEvent.click(button('Save alarm'));
		await waitFor(() => expect(screen.getAllByText(/No automatic replay or reauthentication/).length).toBeGreaterThan(0));
		expect(writes()).toHaveLength(1); expect(button('Save alarm').disabled).toBe(false);
		expect(screen.queryByText('Alarm saved.')).toBeNull();
	});

	it.each(['missing', 'unsupported'])('does not turn a %s native rule into an empty editable rule', async kind => {
		current = kind === 'missing' ? alarm() : { ...alarm(), type: 'future-provider-type' as AlarmType };
		if (kind === 'missing') delete current.gnocchi_resources_threshold_rule;
		list = page([current]); mount(); await fireEvent.click(await screen.findByRole('button', { name: 'CPU alarm' }));
		await screen.findByText(/Check the JSON object\/array shapes/);
		expect(screen.queryByRole('dialog', { name: 'Edit alarm' })).toBeNull(); expect(writes()).toHaveLength(0);
	});

	it.each(['partial', 'forbidden', 'unavailable'] as const)('never presents an unverified %s list as confirmed empty', async status => {
		list = page([], null, status); mount();
		await screen.findByText('No verified alarm rows are available. This is not a confirmed empty list.');
		expect(screen.queryByText('No alarms on this page.')).toBeNull();
	});

	it('preserves edited rule and constraint extension fields in the submitted and reread definition', async () => {
		mount(); await choose();
		const editedRule = { ...rule, provider_extension: { keep: [null, true, { exact: 'changed' }] }, threshold: 15.5 };
		const editedConstraints = [{ ...constraints[0], timezone: 'UTC', extension: { keep: [4, 5, 6] } }];
		await input('Rule JSON', JSON.stringify(editedRule)); await input('Time constraints JSON', JSON.stringify(editedConstraints));
		await fireEvent.click(button('Save alarm')); await screen.findByText('Alarm saved.');
		expect(writes()[0][2].body.gnocchi_resources_threshold_rule).toEqual(editedRule);
		expect(writes()[0][2].body.time_constraints).toEqual(editedConstraints);
		await choose(); expect(JSON.parse(field('Rule JSON').value)).toEqual(editedRule);
		expect(JSON.parse(field('Time constraints JSON').value)).toEqual(editedConstraints);
	});

	it('allows native JSON authoring for a new resource alarm without forcing guided-field completion', async () => {
		window.history.replaceState({}, '', '?create=1'); mount();
		await screen.findByRole('dialog', { name: 'Create alarm' }); await fireEvent.click(button('Edit native rule JSON'));
		await input('Name', 'Native JSON alarm'); await input('Rule JSON', JSON.stringify(rule));
		await fireEvent.click(button('Save alarm')); await waitFor(() => expect(writes()).toHaveLength(1));
		expect(writes()[0][2].body.gnocchi_resources_threshold_rule).toEqual(rule);
	});

	it('does not replace a new draft with an older selection response in the same authority context', async () => {
		const pending = Promise.withResolvers<AodhDetail>();
		mocks.request.mockImplementation((path: string) => path.startsWith('/aodh/alarms?') ? Promise.resolve(list) : pending.promise);
		mount(); await fireEvent.click(await screen.findByRole('button', { name: 'CPU alarm' }));
		await fireEvent.click(button('Create alarm')); await screen.findByRole('dialog', { name: 'Create alarm' });
		await input('Name', 'New draft identity'); pending.resolve(detail(alarm())); await pending.promise; await tick();
		expect(field('Name').value).toBe('New draft identity'); expect(screen.queryByDisplayValue(/private\.example/)).toBeNull();
	});

	it('keeps an ambiguous write locked when another alarm is selected or the affected alarm is not readable', async () => {
		list = page([current, alarm('event', { alarm_id: otherId, name: 'Other alarm' })]);
		mutationFailure = new TelemetryError(503, 'telemetry_mutation_uncertain', true); mount(); await choose();
		await fireEvent.click(button('Save alarm'));
		await waitFor(() => expect(screen.getAllByText(/The mutation outcome is unknown/).length).toBeGreaterThan(0));
		await fireEvent.click(button('Cancel'));
		current = alarm('event', { alarm_id: otherId, name: 'Other alarm' }); list = page([current]);
		// Selecting is a read, not an explicit reread of the affected alarm.
		await fireEvent.click(button('Other alarm')); await screen.findByRole('dialog', { name: 'Edit alarm' });
		expect(button('Save alarm').disabled).toBe(true); expect(button('Delete alarm').disabled).toBe(true); expect(writes()).toHaveLength(1);
		await fireEvent.click(button('Cancel')); expect(button('Create alarm').disabled).toBe(true);
		mocks.request.mockResolvedValueOnce(detail(null));
		await fireEvent.click(button('Reread affected alarm')); await tick();
		expect(button('Create alarm').disabled).toBe(true); expect(writes()).toHaveLength(1);
		await fireEvent.click(button('Reread alarms')); await screen.findByText('Native data reread successfully. Review the current alarm before making another change.');
		expect(button('Create alarm').disabled).toBe(false); expect(writes()).toHaveLength(1);
	});

	it.each(['project switch', 'logout', 'revoked administrator'] as const)('clears selected URLs and drafts immediately on %s', async change => {
		mount(); await choose(); expect(field('Alarm action URLs').value).toContain('private.example.invalid');
		if (change === 'project switch') projectSwitching.set(true);
		else if (change === 'logout') logoutInProgress.set(true);
		else auth.update(state => ({ ...state, isSystemAdmin: false }));
		await tick(); expect(screen.queryByRole('dialog', { name: 'Edit alarm' })).toBeNull();
		expect(screen.queryByDisplayValue(/private\.example/)).toBeNull(); expect(button('Create alarm').disabled).toBe(true);
	});

	it.each([
		['Alarm action URLs', 'alarm_actions'], ['OK action URLs', 'ok_actions'], ['Insufficient data action URLs', 'insufficient_data_actions'],
	] as const)('requires explicit confirmation for mixed-case trust in %s without rewriting the native URL', async (label, key) => {
		mount(); await choose(); await input(label, 'TRUST+HTTPS://receiver.example.invalid/authority');
		await fireEvent.click(button('Save alarm')); await screen.findByRole('dialog', { name: /Save these trust actions/ });
		expect(writes()).toHaveLength(0); await confirm(/Save these trust actions/, 'Save alarm');
		await waitFor(() => expect(writes()).toHaveLength(1));
		expect(writes()[0][2].body[key]).toEqual(['TRUST+HTTPS://receiver.example.invalid/authority']);
	});

	it.each([`?alarm=${id}`, '?create=1'])('honors initial %s after authority becomes ready, but never reopens its draft after later context changes', async search => {
		authReady.set(false); window.history.replaceState({}, '', search); mount();
		expect(mocks.request).not.toHaveBeenCalled(); authReady.set(true);
		await screen.findByRole('dialog', { name: search.includes('alarm=') ? 'Edit alarm' : 'Create alarm' });
		auth.update(state => ({ ...state, projectId: 'project-b', token: 'token-b' })); await tick();
		expect(screen.queryByRole('dialog', { name: 'Edit alarm' })).toBeNull();
		expect(screen.queryByRole('dialog', { name: 'Create alarm' })).toBeNull();
		expect(screen.queryByDisplayValue(/private\.example/)).toBeNull();
	});

	it('never unlocks an uncertain mutation using an explicit list read started before that mutation', async () => {
		mount(); await screen.findByRole('button', { name: 'CPU alarm' });
		const pending = Promise.withResolvers<NativePage<NativeAlarm>>();
		mocks.request.mockReturnValueOnce(pending.promise);
		await fireEvent.click(button('Reread alarms')); await choose();
		mutationFailure = new TelemetryError(503, 'telemetry_mutation_uncertain', true);
		await fireEvent.click(button('Save alarm'));
		await waitFor(() => expect(screen.getAllByText(/The mutation outcome is unknown/).length).toBeGreaterThan(0));
		pending.resolve(page([alarm()])); await pending.promise; await tick();
		expect(button('Save alarm').disabled).toBe(true); expect(button('Delete alarm').disabled).toBe(true);
		expect(screen.queryByText('Native data reread successfully. Review the current alarm before making another change.')).toBeNull();
		expect(writes()).toHaveLength(1);
	});
});
