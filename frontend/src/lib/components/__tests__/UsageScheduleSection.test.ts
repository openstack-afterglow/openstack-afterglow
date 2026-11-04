import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable, type Writable } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/usage-schedule';
import type { UsageScheduleInfo } from '$lib/types/instanceUsage';
import { calendarMonthAfter, fromLocalDateTime, toLocalDateTime } from '$lib/utils/instanceUsage';

const transport = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), withExperience() { return this; } }));
vi.mock('$lib/api/client', () => ({
	api: transport,
	ApiError: class ApiError extends Error { constructor(_status: number, message: string) { super(message); } },
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'actor-a' }),
}));

import { ApiError } from '$lib/api/client';
import { auth } from '$lib/stores/auth';
import UsageScheduleSection from '../instance/UsageScheduleSection.svelte';

const identity = auth as unknown as Writable<{ token: string | null; projectId: string; userId: string; sessionId?: string }>;
const path = '/api/v1/instances/vm-a/usage-schedule';
const props = { instanceId: 'vm-a', projectId: 'project-a', canWrite: true };
function schedule(overrides: Partial<UsageScheduleInfo> = {}): UsageScheduleInfo {
	return { instance_id: 'vm-a', starts_at: '2099-01-01T10:20:30Z', expires_at: '2099-01-31T10:20:30Z',
		expiry_action: 'shelve', delete_volumes: false, reason: 'Original allocation', revision: 'revision-a',
		state: 'active', source: 'created', last_error: null, ...overrides };
}
function deferred<T>() {
	return Promise.withResolvers<T>();
}
async function ready() {
	await waitFor(() => expect(screen.getByRole<HTMLButtonElement>('button', { name: t('save') }).disabled).toBe(false));
}
async function reason(value: string) {
	await fireEvent.input(screen.getByRole('textbox', { name: t('reason') }), { target: { value } });
}
function saveButton() { return screen.getByRole<HTMLButtonElement>('button', { name: t('save') }); }

beforeEach(() => {
	transport.get.mockReset();
	transport.put.mockReset();
	transport.get.mockResolvedValue(schedule());
	transport.put.mockImplementation(async (_path, payload) => schedule({ ...payload, expires_at: payload.expires_at ?? schedule().expires_at, revision: 'revision-b' }));
	identity.set({ token: 'token-a', projectId: 'project-a', userId: 'actor-a' });
	initLocale('en');
});
afterEach(() => cleanup());

describe('usage schedule detail with its real controller and fields', () => {
	it('scrolls a delayed reminder anchor once on mount, never again on schedule refresh', async () => {
		const originalScroll = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollIntoView');
		const scroll = vi.fn();
		const originalUrl = window.location.href;
		Object.defineProperty(Element.prototype, 'scrollIntoView', { configurable: true, value: scroll });
		window.history.replaceState(null, '', '#usage-schedule');
		try {
			render(UsageScheduleSection, props);
			await ready();
			expect(scroll).toHaveBeenCalledTimes(1);
			expect(scroll).toHaveBeenCalledWith({ block: 'start', behavior: 'instant' });
			await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
			await ready();
			expect(scroll).toHaveBeenCalledTimes(1);
		} finally {
			window.history.replaceState(null, '', originalUrl);
			if (originalScroll) Object.defineProperty(Element.prototype, 'scrollIntoView', originalScroll);
			else Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
		}
	});

	it('reads freshly, preserves exact UTC revision payload and never opts into volume deletion by default', async () => {
		const onUpdated = vi.fn();
		render(UsageScheduleSection, { ...props, onUpdated });
		await ready();
		expect(transport.get).toHaveBeenCalledWith(path, 'token-a', 'project-a', { signal: expect.any(AbortSignal), cache: 'no-store' });
		expect(document.querySelector('#usage-schedule')).toBeTruthy();
		expect(screen.getByText(t('sourceCreated'))).toBeTruthy();
		expect(screen.getByText(t('noResume'))).toBeTruthy();
		expect(screen.queryByRole('checkbox')).toBeNull();
		expect(transport.put).not.toHaveBeenCalled();
		await fireEvent.click(saveButton());
		await screen.findByText(t('saved'));
		expect(transport.put).toHaveBeenCalledWith(path, {
			expires_at: null, expiry_action: 'shelve', delete_volumes: false, reason: '', revision: 'revision-a',
		}, 'token-a', 'project-a', { signal: expect.any(AbortSignal), replayOnUnauthorized: false });
		expect(onUpdated).toHaveBeenCalledTimes(1);
	});

	it('changes a calendar-month draft without saving, then requires a reason and uses the current revision', async () => {
		render(UsageScheduleSection, props);
		await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('extend') }));
		const expires = document.querySelector<HTMLInputElement>('#usage-schedule-edit-expires')!;
		expect(expires.value).toBe(toLocalDateTime(calendarMonthAfter(new Date(schedule().expires_at)).toISOString()));
		expect(saveButton().disabled).toBe(true);
		expect(screen.getByText(t('reasonRequired'))).toBeTruthy();
		expect(transport.put).not.toHaveBeenCalled();
		await reason('  Experiment continuation  ');
		expect(saveButton().disabled).toBe(false);
		await fireEvent.click(saveButton());
		await screen.findByText(t('saved'));
		expect(transport.put.mock.calls[0][1]).toMatchObject({ expires_at: fromLocalDateTime(expires.value), reason: 'Experiment continuation', revision: 'revision-a', delete_volumes: false });
		await fireEvent.click(saveButton());
		await waitFor(() => expect(transport.put).toHaveBeenCalledTimes(2));
		expect(transport.put.mock.calls[1][1].revision).toBe('revision-b');
	});

	it('does not compound the extension shortcut beyond one month from the effective expiry', async () => {
		render(UsageScheduleSection, props);
		await ready();
		const button = screen.getByRole('button', { name: t('extend') });
		await fireEvent.click(button);
		await fireEvent.click(button);
		expect(document.querySelector<HTMLInputElement>('#usage-schedule-edit-expires')!.value)
			.toBe(toLocalDateTime(calendarMonthAfter(new Date(schedule().expires_at)).toISOString()));
		expect(screen.getByText(t('reasonFollowup'))).toBeTruthy();
	});

	it('shortens an active future deadline but refuses dates before enrollment or over the extension cap', async () => {
		render(UsageScheduleSection, props);
		await ready();
		const input = document.querySelector<HTMLInputElement>('#usage-schedule-edit-expires')!;
		await fireEvent.input(input, { target: { value: toLocalDateTime('2099-01-15T10:20:00Z') } });
		expect(saveButton().disabled).toBe(false);
		await fireEvent.click(saveButton());
		await screen.findByText(t('saved'));
		expect(transport.put.mock.calls[0][1].expires_at).toBe(fromLocalDateTime(input.value));
		await fireEvent.input(input, { target: { value: toLocalDateTime('2099-01-01T10:19:00Z') } });
		expect(saveButton().disabled).toBe(true);
		expect(screen.getByText(t('beforeStart'))).toBeTruthy();
		await fireEvent.input(input, { target: { value: toLocalDateTime('2099-04-01T10:20:00Z') } });
		expect(screen.getByText(t('extensionLimit'))).toBeTruthy();
		await fireEvent.submit(screen.getByRole('form', { name: t('edit') }));
		expect(transport.put).toHaveBeenCalledTimes(1);
	});

	it('shows a pending request separately without changing effective expiry or announcing save success', async () => {
		transport.put.mockImplementationOnce(async (_path, payload) => ({
			status: 'pending', schedule: schedule(),
			request: { id: 'request-a', instance_id: 'vm-a', project_id: 'project-a', expires_at: payload.expires_at,
				status: 'pending', reason: payload.reason },
		}));
		const onUpdated = vi.fn();
		render(UsageScheduleSection, { ...props, onUpdated });
		await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('extend') }));
		await reason('Continue research');
		await fireEvent.click(saveButton());
		await screen.findByText(t('pendingSubmitted'), { exact: false });
		expect(screen.getByText(t('pendingWarning'), { exact: false })).toBeTruthy();
		expect(screen.queryByText(t('saved'))).toBeNull();
		expect(document.querySelector<HTMLInputElement>('#usage-schedule-edit-expires')!.value).toBe(toLocalDateTime(schedule().expires_at));
		expect(document.querySelector(`time[datetime=\"${schedule().expires_at}\"]`)).toBeTruthy();
		expect(screen.getByRole('link', { name: t('reviewTitle') }).getAttribute('href')).toBe('/dashboard/usage#usage-extension-review');
		expect(onUpdated).not.toHaveBeenCalled();
	});

	it('keeps overlong multibyte reasons visible and refuses extension submission', async () => {
		render(UsageScheduleSection, props);
		await ready();
		await fireEvent.click(screen.getByRole('button', { name: t('extend') }));
		await reason('한'.repeat(86));
		expect(screen.getByText(t('reasonInvalid'))).toBeTruthy();
		expect(saveButton().disabled).toBe(true);
		await fireEvent.submit(screen.getByRole('form', { name: t('edit') }));
		expect(transport.put).not.toHaveBeenCalled();
	});

	it('requires explicit attached-volume consent and clears it when the action changes', async () => {
		render(UsageScheduleSection, props);
		await ready();
		const action = screen.getByRole('combobox', { name: t('action') });
		await fireEvent.change(action, { target: { value: 'delete' } });
		const consent = screen.getByRole<HTMLInputElement>('checkbox', { name: t('deleteVolumes') });
		expect(consent.checked).toBe(false);
		expect(screen.getByText(t('destructive'))).toBeTruthy();
		await fireEvent.click(consent);
		await fireEvent.click(saveButton());
		await screen.findByText(t('saved'));
		expect(transport.put.mock.calls[0][1]).toMatchObject({ expiry_action: 'delete', delete_volumes: true });
		await fireEvent.change(action, { target: { value: 'shelve' } });
		await fireEvent.change(action, { target: { value: 'delete' } });
		expect(screen.getByRole<HTMLInputElement>('checkbox', { name: t('deleteVolumes') }).checked).toBe(false);
	});

	it.each(['active', 'blocked', 'complete'] as const)('submits a revision-fenced extension from %s without a power action', async state => {
		transport.get.mockResolvedValue(schedule({ state, source: 'adopted' }));
		render(UsageScheduleSection, props);
		await screen.findByText(t(`state.${state}`));
		if (state === 'complete' || state === 'blocked') {
			expect(saveButton().disabled).toBe(true);
			await fireEvent.submit(screen.getByRole('form', { name: t('edit') }));
			expect(transport.put).not.toHaveBeenCalled();
			await fireEvent.click(screen.getByRole('button', { name: t('extend') }));
			expect(saveButton().disabled).toBe(true);
			await reason('Resume the project allocation');
		}
		await ready();
		await fireEvent.click(saveButton());
		await waitFor(() => expect(transport.put).toHaveBeenCalledTimes(1));
		const [requestPath, payload, , , options] = transport.put.mock.calls[0];
		expect(requestPath).toBe(path);
		expect(payload.revision).toBe('revision-a');
		expect(options.replayOnUnauthorized).toBe(false);
		if (state !== 'active') {
			expect(Date.parse(payload.expires_at)).toBeGreaterThan(Date.parse(schedule().expires_at));
			expect(payload.reason).toBe('Resume the project allocation');
		}
	});

	it.each(['shelve_requested', 'offload_requested', 'stop_requested', 'volume_flags_requested', 'volumes_ready', 'delete_requested', 'unknown'] as const)(
		'keeps %s evidence visible and disables writes', async state => {
			transport.get.mockResolvedValue(schedule({ state, last_error: 'Native attachment ownership is unverified.' }));
			render(UsageScheduleSection, props);
			await screen.findByText(t(`state.${state}`));
			expect(screen.getByText('Native attachment ownership is unverified.')).toBeTruthy();
			expect(saveButton().disabled).toBe(true);
			expect(screen.getByRole<HTMLSelectElement>('combobox', { name: t('action') }).disabled).toBe(true);
			await fireEvent.submit(screen.getByRole('form', { name: t('edit') }));
			expect(transport.put).not.toHaveBeenCalled();
		},
	);

	it('shows full existing schedule details to readers without mutation controls', async () => {
		const longReason = '長い理由'.repeat(20);
		transport.get.mockResolvedValue(schedule({ reason: longReason, expiry_action: 'delete', delete_volumes: true }));
		render(UsageScheduleSection, { ...props, canWrite: false });
		await screen.findByText(longReason);
		expect(screen.getByText(t('readonly'))).toBeTruthy();
		expect(screen.getByText(t('delete'))).toBeTruthy();
		expect(document.querySelectorAll('time')).toHaveLength(2);
		expect(screen.queryByRole('form')).toBeNull();
		expect(screen.queryByRole('button', { name: t('save') })).toBeNull();
		expect(screen.queryByRole('checkbox')).toBeNull();
		expect(transport.put).not.toHaveBeenCalled();
	});

	it('distinguishes enrollment grace from native read failure and offers an explicit fresh retry', async () => {
		transport.get.mockRejectedValueOnce(new ApiError(409, 'Native metadata is malformed.'));
		transport.get.mockResolvedValueOnce(null);
		render(UsageScheduleSection, props);
		await screen.findByText('Native metadata is malformed.');
		expect(screen.queryByText(t('none'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await screen.findByText(t('none'));
		expect(screen.queryByRole('form')).toBeNull();
		expect(transport.put).not.toHaveBeenCalled();
	});

	it('preserves a failed mutation draft but requires a fresh read before any explicit retry', async () => {
		transport.put.mockRejectedValueOnce(new ApiError(502, 'Native result is uncertain.'));
		render(UsageScheduleSection, props);
		await ready();
		await reason('Keep this explanation');
		await fireEvent.click(saveButton());
		await screen.findByText('Native result is uncertain.');
		expect(screen.getByRole<HTMLInputElement>('textbox', { name: t('reason') }).value).toBe('Keep this explanation');
		expect(saveButton().disabled).toBe(true);
		await fireEvent.submit(screen.getByRole('form', { name: t('edit') }));
		expect(transport.put).toHaveBeenCalledTimes(1);
		transport.get.mockResolvedValueOnce(schedule({ revision: 'fresh-revision' }));
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await ready();
		expect(screen.getByRole<HTMLInputElement>('textbox', { name: t('reason') }).value).toBe('Keep this explanation');
		await fireEvent.click(saveButton());
		await screen.findByText(t('saved'));
		expect(transport.put.mock.calls[1][1].revision).toBe('fresh-revision');
		expect(transport.put.mock.calls[1][1].reason).toBe('Keep this explanation');
	});

	it('rejects a mismatched native schedule rather than displaying another instance', async () => {
		transport.get.mockResolvedValueOnce(schedule({ instance_id: 'vm-other', reason: 'Private other schedule' }));
		render(UsageScheduleSection, props);
		await screen.findByText(t('loadFailed'));
		expect(screen.queryByText('Private other schedule')).toBeNull();
		expect(screen.queryByRole('form')).toBeNull();
	});

	it('uses the administrator API and authenticated header project, not the target owner as credential scope', async () => {
		render(UsageScheduleSection, { ...props, projectId: 'native-owner', adminMode: true });
		await ready();
		expect(transport.get).toHaveBeenCalledWith('/api/v1/admin/instances/vm-a/usage-schedule', 'token-a', 'project-a', expect.objectContaining({ cache: 'no-store' }));
		await fireEvent.click(saveButton());
		await screen.findByText(t('saved'));
		expect(transport.put.mock.calls[0][0]).toBe('/api/v1/admin/instances/vm-a/usage-schedule');
		expect(transport.put.mock.calls[0][3]).toBe('project-a');
	});

	it('discards A→B→A old reads and never rejoins the original pending lookup', async () => {
		const old = deferred<UsageScheduleInfo>();
		transport.get.mockReturnValueOnce(old.promise);
		const view = render(UsageScheduleSection, props);
		await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(1));
		transport.get.mockResolvedValueOnce(schedule({ instance_id: 'vm-b', reason: 'B schedule' }));
		await view.rerender({ ...props, instanceId: 'vm-b' });
		await screen.findByText('B schedule');
		transport.get.mockResolvedValueOnce(schedule({ reason: 'Fresh A schedule' }));
		await view.rerender(props);
		await screen.findByText('Fresh A schedule');
		old.resolve(schedule({ reason: 'Stale private A' }));
		await tick();
		expect(screen.queryByText('Stale private A')).toBeNull();
		expect(transport.get.mock.calls.filter(([url]) => url === path)).toHaveLength(2);
		expect(transport.get.mock.calls.every(([, , , options]) => options.cache === 'no-store')).toBe(true);
	});

	it('preserves draft and pending mutation across token-only refresh without aborting its request', async () => {
		const pending = deferred<UsageScheduleInfo>();
		transport.put.mockReturnValueOnce(pending.promise);
		const onUpdated = vi.fn();
		render(UsageScheduleSection, { ...props, onUpdated });
		await ready();
		await reason('Keep my draft during refresh');
		identity.update(value => ({ ...value, token: 'refreshed-token' }));
		await tick();
		expect(screen.getByRole<HTMLInputElement>('textbox', { name: t('reason') }).value).toBe('Keep my draft during refresh');
		expect(transport.get).toHaveBeenCalledTimes(1);
		await fireEvent.click(saveButton());
		await waitFor(() => expect(transport.put).toHaveBeenCalledTimes(1));
		expect(transport.put.mock.calls[0][2]).toBe('refreshed-token');
		const signal = transport.put.mock.calls[0][4].signal;
		identity.update(value => ({ ...value, token: 'refreshed-again' }));
		await tick();
		expect(signal.aborted).toBe(false);
		pending.resolve(schedule({ revision: 'new-revision' }));
		await screen.findByText(t('saved'));
		expect(onUpdated).toHaveBeenCalledTimes(1);
		expect(saveButton().disabled).toBe(false);
	});

	it.each(['session', 'actor', 'headerProject', 'targetProject', 'adminMode', 'permission'] as const)(
		'clears drafts and suppresses pending save results across %s replacement and ABA', async scope => {
			const pending = deferred<UsageScheduleInfo>();
			const onUpdated = vi.fn();
			transport.put.mockReturnValueOnce(pending.promise);
			const view = render(UsageScheduleSection, { ...props, onUpdated });
			await ready();
			await reason('Private old draft');
			await fireEvent.click(saveButton());
			await waitFor(() => expect(transport.put).toHaveBeenCalledTimes(1));
			if (scope === 'session') identity.update(value => ({ ...value, sessionId: 'another-session' }));
			if (scope === 'actor') identity.update(value => ({ ...value, userId: 'actor-b' }));
			if (scope === 'headerProject') identity.update(value => ({ ...value, projectId: 'project-b' }));
			if (scope === 'targetProject') await view.rerender({ ...props, projectId: 'project-b', onUpdated });
			if (scope === 'adminMode') await view.rerender({ ...props, adminMode: true, onUpdated });
			if (scope === 'permission') await view.rerender({ ...props, canWrite: false, onUpdated });
			await tick();
			identity.set({ token: 'token-a', projectId: 'project-a', userId: 'actor-a' });
			await view.rerender({ ...props, adminMode: false, onUpdated });
			await ready();
			expect(screen.getByRole<HTMLInputElement>('textbox', { name: t('reason') }).value).toBe('');
			pending.resolve(schedule({ reason: 'Stale mutation receipt', revision: 'old-write' }));
			await tick();
			expect(screen.queryByText('Stale mutation receipt')).toBeNull();
			expect(screen.queryByText(t('saved'))).toBeNull();
			expect(onUpdated).not.toHaveBeenCalled();
		},
	);

	it('notices same-tick session ABA and refetches instead of publishing an old result', async () => {
		const old = deferred<UsageScheduleInfo>();
		transport.get.mockReturnValueOnce(old.promise);
		render(UsageScheduleSection, props);
		await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(1));
		identity.update(value => ({ ...value, sessionId: 'session-b' }));
		identity.update(value => ({ ...value, sessionId: undefined }));
		await ready();
		old.resolve(schedule({ reason: 'Before token ABA' }));
		await tick();
		expect(screen.queryByText('Before token ABA')).toBeNull();
		expect(transport.get).toHaveBeenCalledTimes(2);
	});

	it.each(['ko', 'en', 'ja', 'zh-CN', 'bn', 'ms', 'nb', 'sw', 'vi'] as const)('renders localized reader states in %s', async locale => {
		initLocale(locale);
		render(UsageScheduleSection, { ...props, canWrite: false });
		await screen.findByText(t('readonly'));
		expect(screen.getByRole('heading', { name: t('title') })).toBeTruthy();
		expect(screen.getByText(t('state.active'))).toBeTruthy();
		expect(screen.getByText(t('noResume'))).toBeTruthy();
	});
});
