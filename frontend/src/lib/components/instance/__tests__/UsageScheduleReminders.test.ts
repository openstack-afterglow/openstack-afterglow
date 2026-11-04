import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get as getStore } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import type { UsageScheduleInfo } from '$lib/types/instanceUsage';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get, withExperience: () => ({ get }) }, ApiError: class ApiError extends Error { constructor(_status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', async () => {
	// The hoisted auth mock factory must load its store dependency before static imports initialize.
	const { writable } = await import('svelte/store');
	return { auth: writable({}), authReady: writable(false), projectSwitching: writable(false) };
});
vi.mock('$lib/i18n/ns/usage-schedule', () => ({ t: (key: string, values?: Record<string, string>) => values?.zone ? `${key}:${values.zone}` : key }));
import { ApiError } from '$lib/api/client';
import UsageScheduleReminders from '../UsageScheduleReminders.svelte';

const now = Date.parse('2026-10-29T00:00:00Z');
const day = 86_400_000;
const path = '/api/v1/instances/usage-schedules';
function schedule(overrides: Partial<UsageScheduleInfo> = {}): UsageScheduleInfo {
	return {
		instance_id: 'instance-a', instance_name: 'Scheduled instance', starts_at: '2026-10-01T00:00:00Z',
		expires_at: new Date(now + day).toISOString(), expiry_action: 'shelve', delete_volumes: false,
		reason: '', revision: 'revision-a', source: 'created', state: 'active', last_error: null, ...overrides,
	};
}
interface ScheduleList { schedules: UsageScheduleInfo[]; errors: { instance_id: string; instance_name?: string; message: string }[] }
function result(rows: UsageScheduleInfo[] = []): ScheduleList { return { schedules: rows, errors: [] }; }
function project(id: string) { auth.update(state => ({ ...state, projectId: id })); }
function reminderAlert() { return screen.getByText('Scheduled instance').closest('[role]')!; }

beforeEach(() => {
	vi.resetAllMocks();
	vi.useFakeTimers({ toFake: ['Date'] });
	vi.setSystemTime(now);
	initLocale('en');
	auth.set({ token: 'token-a', projectId: 'project-a', userId: 'reader-a', sessionId: 'session-a',
		identityDomainId: 'accounts', domainId: 'personal', roles: ['reader'], canWrite: false,
		isSystemAdmin: false } as Parameters<typeof auth.set>[0]);
	authReady.set(true);
	projectSwitching.set(false);
	get.mockResolvedValue(result());
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('project usage reminders', () => {
	it('waits for authoritative authentication, token and project rather than showing an empty list', async () => {
		authReady.set(false);
		auth.update(state => ({ ...state, token: null, projectId: null }));
		render(UsageScheduleReminders);
		await tick();
		expect(get).not.toHaveBeenCalled();
		expect(screen.getByText('loading')).toBeTruthy();
		expect(screen.queryByText('empty')).toBeNull();
		authReady.set(true);
		project('project-a');
		await tick();
		expect(get).not.toHaveBeenCalled();
		auth.update(state => ({ ...state, token: 'token-a' }));
		await screen.findByText('empty');
		expect(get).toHaveBeenCalledWith(path, 'token-a', 'project-a', expect.objectContaining({ cache: 'no-store', signal: expect.any(AbortSignal) }));
	});

	it('offers a retry after a failed load without announcing an empty project', async () => {
		const pending = Promise.withResolvers<ScheduleList>();
		get.mockReturnValueOnce(pending.promise);
		render(UsageScheduleReminders);
		expect(screen.queryByText('empty')).toBeNull();
		pending.reject(new ApiError(503, 'Native schedule inventory denied'));
		await screen.findByText('Native schedule inventory denied');
		expect(screen.queryByText('empty')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'refresh' }));
		await screen.findByText('empty');
		expect(get).toHaveBeenCalledTimes(2);
	});

	it('keeps partial metadata errors visible with the exact encoded instance link', async () => {
		get.mockResolvedValue({ schedules: [schedule()], errors: [{ instance_id: 'broken/id ?#', instance_name: 'Broken instance', message: 'Native metadata is incomplete' }] });
		render(UsageScheduleReminders);
		await screen.findByText('Native metadata is incomplete');
		const broken = screen.getByText('Broken instance').closest('li')!;
		expect(broken.querySelector('.alert-danger')).toBeTruthy();
		expect(within(broken).getByRole('link', { name: 'manage' }).getAttribute('href')).toBe('/dashboard/compute/instances/broken%2Fid%20%3F%23#usage-schedule');
		expect(screen.getByText('Scheduled instance')).toBeTruthy();
		expect(screen.queryByText('empty')).toBeNull();
	});

	it('renders read-only reminders with a real standalone detail link and no write actions', async () => {
		get.mockResolvedValue(result([schedule()]));
		render(UsageScheduleReminders);
		const link = await screen.findByRole('link', { name: 'manage' });
		expect(link.getAttribute('href')).toBe('/dashboard/compute/instances/instance-a#usage-schedule');
		expect(screen.queryByRole('button', { name: 'save' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'extend' })).toBeNull();
	});

	it.each([
		[7 * day + 1, null, null], [7 * day, 'week', 'warning'],
		[3 * day + 1, 'week', 'warning'], [3 * day, 'threeDays', 'warning'],
		[day + 1, 'threeDays', 'warning'], [day, 'oneDay', 'warning'],
		[1, 'oneDay', 'warning'], [0, 'expired', 'danger'], [-1, 'expired', 'danger'],
	] as const)('uses the exact reminder threshold at %s milliseconds remaining', async (remaining, urgency, tone) => {
		get.mockResolvedValue(result([schedule({ expires_at: new Date(now + remaining).toISOString() })]));
		render(UsageScheduleReminders);
		if (!urgency) {
			await screen.findByText('empty');
			expect(screen.queryByText('Scheduled instance')).toBeNull();
		} else {
			await screen.findByText(urgency);
			expect(reminderAlert().classList.contains(`alert-${tone}`)).toBe(true);
		}
	});

	it.each(['blocked', 'shelve_requested', 'offload_requested', 'stop_requested', 'volume_flags_requested', 'volumes_ready', 'delete_requested', 'unknown'] as const)(
		'shows %s as danger even before the reminder window', async state => {
			get.mockResolvedValue(result([schedule({ state, expires_at: new Date(now + 30 * day).toISOString() })]));
			render(UsageScheduleReminders);
			await screen.findByText('attention');
			expect(reminderAlert().classList.contains('alert-danger')).toBe(true);
		});

	it('does not remind completed schedules unless a native error remains', async () => {
		get.mockResolvedValue(result([schedule({ state: 'complete' }), schedule({ instance_id: 'error-id', instance_name: 'Failed schedule', state: 'complete', last_error: 'Offload could not be confirmed' })]));
		render(UsageScheduleReminders);
		await screen.findByText('Offload could not be confirmed');
		expect(screen.queryByText('Scheduled instance')).toBeNull();
		expect(screen.getByText('Failed schedule').closest('.alert-danger')).toBeTruthy();
	});

	it.each([
		{ expires_at: 'invalid date' }, { state: 'complete', starts_at: 'invalid date' },
		{ expiry_action: 'shelve', delete_volumes: true }, { revision: '' },
	] as Partial<UsageScheduleInfo>[])('never suppresses malformed schedule metadata: %s', async invalid => {
		get.mockResolvedValue(result([schedule(invalid)]));
		render(UsageScheduleReminders);
		await screen.findByText('attention');
		expect(screen.getByText('Scheduled instance').closest('.alert-danger')).toBeTruthy();
		expect(screen.getByRole('link', { name: 'manage' }).getAttribute('href')).toContain('/instance-a#usage-schedule');
		expect(screen.queryByText('empty')).toBeNull();
	});

	it('does not treat a malformed list envelope as an empty project', async () => {
		get.mockResolvedValue({ schedules: [] });
		render(UsageScheduleReminders);
		await screen.findByText('loadFailed');
		expect(screen.queryByText('empty')).toBeNull();
	});

	it('formats the exact expiry in the active locale with seconds and an explicit time zone', async () => {
		initLocale('ja');
		const expires = '2026-10-29T12:34:56Z';
		get.mockResolvedValue(result([schedule({ expires_at: expires })]));
		const { container } = render(UsageScheduleReminders);
		await screen.findByText('Scheduled instance');
		const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
		const expected = new Intl.DateTimeFormat('ja-JP', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: zone, timeZoneName: 'longOffset' }).format(new Date(expires));
		const time = container.querySelector('time')!;
		expect(time.getAttribute('datetime')).toBe(expires);
		expect(time.textContent).toBe(expected);
		expect(screen.getByText(`timezone:${zone}`)).toBeTruthy();
	});
});

describe('reminder request ownership and freshness', () => {
	it('preserves settled rows and a pending read through token rotation and sends the latest token next time', async () => {
		get.mockResolvedValueOnce(result([schedule()]));
		render(UsageScheduleReminders);
		await screen.findByText('Scheduled instance');
		const pending = Promise.withResolvers<ScheduleList>();
		get.mockReturnValueOnce(pending.promise);
		await fireEvent.click(screen.getByRole('button', { name: 'refresh' }));
		auth.update(state => ({ ...state, token: 'refreshed-token' }));
		await tick();
		expect(screen.getByText('Scheduled instance')).toBeTruthy();
		expect(get).toHaveBeenCalledTimes(2);
		expect(get.mock.calls[1][3].signal.aborted).toBe(false);
		pending.resolve(result([schedule({ instance_name: 'Fresh scheduled instance' })]));
		await screen.findByText('Fresh scheduled instance');
		await fireEvent.click(screen.getByRole('button', { name: 'refresh' }));
		await screen.findByText('empty');
		expect(get.mock.calls[2][1]).toBe('refreshed-token');
	});

	it('clears loaded rows immediately on project changes while the next inventory is pending', async () => {
		const next = Promise.withResolvers<ScheduleList>();
		get.mockResolvedValueOnce(result([schedule()])).mockReturnValueOnce(next.promise);
		render(UsageScheduleReminders);
		await screen.findByText('Scheduled instance');
		project('project-b');
		await tick();
		expect(screen.queryByText('Scheduled instance')).toBeNull();
		expect(screen.queryByText('empty')).toBeNull();
		next.resolve(result());
		await screen.findByText('empty');
	});

	it('starts independent no-store requests and rejects same-tick project A → B → A completions', async () => {
		const firstA = Promise.withResolvers<ScheduleList>();
		const b = Promise.withResolvers<ScheduleList>();
		const finalA = Promise.withResolvers<ScheduleList>();
		get.mockReturnValueOnce(firstA.promise).mockReturnValueOnce(b.promise).mockReturnValueOnce(finalA.promise);
		render(UsageScheduleReminders);
		await tick();
		project('project-b');
		project('project-a');
		expect(get).toHaveBeenCalledTimes(3);
		for (const call of get.mock.calls) expect(call[3].cache).toBe('no-store');
		expect(get.mock.calls[0][3].signal.aborted).toBe(true);
		expect(get.mock.calls[1][3].signal.aborted).toBe(true);
		firstA.resolve(result([schedule({ instance_name: 'Stale A' })]));
		b.resolve(result([schedule({ instance_name: 'Stale B' })]));
		await tick();
		expect(screen.queryByText('Stale A')).toBeNull();
		expect(screen.queryByText('Stale B')).toBeNull();
		finalA.resolve(result([schedule({ instance_name: 'Fresh A' })]));
		await screen.findByText('Fresh A');
	});

	it.each(['userId', 'sessionId', 'identityDomainId', 'domainId', 'isSystemAdmin'] as const)(
		'discards same-tick %s ABA responses and stale failures', async field => {
			const old = Promise.withResolvers<ScheduleList>();
			get.mockReturnValueOnce(old.promise).mockResolvedValue(result());
			render(UsageScheduleReminders);
			await tick();
			const previous = getStore(auth);
			auth.update(state => ({ ...state, [field]: field === 'isSystemAdmin' ? true : 'scope-b' }));
			auth.set(previous);
			old.reject(new ApiError(503, 'Stale private error'));
			await screen.findByText('empty');
			expect(get).toHaveBeenCalledTimes(3);
			expect(screen.queryByText('Stale private error')).toBeNull();
		});

	it.each(['readiness', 'switching'] as const)('invalidates in-flight requests on transient %s changes', async transition => {
		const old = Promise.withResolvers<ScheduleList>();
		get.mockReturnValueOnce(old.promise).mockResolvedValue(result());
		render(UsageScheduleReminders);
		await tick();
		if (transition === 'readiness') { authReady.set(false); authReady.set(true); }
		else { projectSwitching.set(true); projectSwitching.set(false); }
		old.resolve(result([schedule({ instance_name: 'Stale readiness' })]));
		await screen.findByText('empty');
		expect(get).toHaveBeenCalledTimes(2);
		expect(screen.queryByText('Stale readiness')).toBeNull();
	});

	it('clears rows on logout and prevents a late request from publishing', async () => {
		const old = Promise.withResolvers<ScheduleList>();
		get.mockReturnValueOnce(old.promise);
		render(UsageScheduleReminders);
		await tick();
		auth.update(state => ({ ...state, token: null }));
		old.resolve(result([schedule()]));
		await tick();
		expect(screen.queryByText('Scheduled instance')).toBeNull();
		expect(screen.queryByText('empty')).toBeNull();
		expect(screen.getByRole('button', { name: 'refresh' }).hasAttribute('disabled')).toBe(true);
	});

	it('retains a verified empty reminder result while a focus refresh is pending', async () => {
		const next = Promise.withResolvers<ScheduleList>();
		get.mockResolvedValueOnce(result()).mockReturnValueOnce(next.promise);
		render(UsageScheduleReminders);
		const empty = await screen.findByText('empty');
		window.dispatchEvent(new Event('focus'));
		await tick();
		expect(get).toHaveBeenCalledTimes(2);
		expect(screen.getByText('empty')).toBe(empty);
		expect(screen.queryByText('loading')).toBeNull();
		next.reject(new ApiError(503, 'Native inventory unavailable'));
		await screen.findByText('Native inventory unavailable');
		expect(screen.queryByText('empty')).toBeNull();
	});

	it('refreshes on focus without overlapping requests and advances reminder urgency', async () => {
		const next = Promise.withResolvers<ScheduleList>();
		get.mockResolvedValueOnce(result([schedule({ expires_at: new Date(now + day + 1).toISOString() })])).mockReturnValueOnce(next.promise);
		render(UsageScheduleReminders);
		await screen.findByText('threeDays');
		vi.setSystemTime(now + 2);
		window.dispatchEvent(new Event('focus'));
		window.dispatchEvent(new Event('focus'));
		await screen.findByText('oneDay');
		expect(get).toHaveBeenCalledTimes(2);
		next.resolve(result());
		await screen.findByText('empty');
	});

	it('updates reminder thresholds on the freshness interval and cancels it on unmount', async () => {
		vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
		get.mockResolvedValue(result([schedule({ expires_at: new Date(now + day + 1).toISOString() })]));
		const { unmount } = render(UsageScheduleReminders);
		await tick();
		await tick();
		expect(screen.getByText('threeDays')).toBeTruthy();
		await vi.advanceTimersByTimeAsync(60_000);
		await tick();
		expect(screen.getByText('oneDay')).toBeTruthy();
		unmount();
		const calls = get.mock.calls.length;
		await vi.advanceTimersByTimeAsync(120_000);
		expect(get).toHaveBeenCalledTimes(calls);
	});

	it('cleans up the timer, focus listener and outstanding request on unmount', async () => {
		const clearTimer = vi.spyOn(window, 'clearInterval');
		const removeListener = vi.spyOn(window, 'removeEventListener');
		const pending = Promise.withResolvers<ScheduleList>();
		get.mockReturnValue(pending.promise);
		const { unmount } = render(UsageScheduleReminders);
		await tick();
		const signal = get.mock.calls[0][3].signal as AbortSignal;
		unmount();
		expect(signal.aborted).toBe(true);
		expect(clearTimer).toHaveBeenCalled();
		expect(removeListener).toHaveBeenCalledWith('focus', expect.any(Function));
		window.dispatchEvent(new Event('focus'));
		expect(get).toHaveBeenCalledTimes(1);
		pending.resolve(result([schedule()]));
		await tick();
		expect(screen.queryByText('Scheduled instance')).toBeNull();
		clearTimer.mockRestore();
		removeListener.mockRestore();
	});
});
