import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import type { UsageScheduleInfo } from '$lib/types/instanceUsage';
import UsageScheduleBellHarness from './_UsageScheduleBellHarness.svelte';
import UsageScheduleReminders from '$lib/components/instance/UsageScheduleReminders.svelte';
import { loadUsageSchedules } from '$lib/api/usageSchedules';

const transport = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: transport, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await import('svelte/store');
	// Vitest hoists this factory before static import bindings initialize; load the store inside it.
	return { auth: writable({}), authReady: writable(false), projectSwitching: writable(false) };
});

function schedule(expires: number, overrides: Partial<UsageScheduleInfo> = {}): UsageScheduleInfo {
	return { instance_id: 'vm', starts_at: new Date().toISOString(), expires_at: new Date(expires).toISOString(),
		expiry_action: 'shelve', delete_volumes: false, reason: '', revision: 'a'.repeat(32), state: 'active', source: 'created', last_error: null, ...overrides };
}
beforeEach(() => {
	vi.resetAllMocks();
	initLocale('en');
	auth.set({ token: 'token-a', projectId: 'project-a', userId: 'reader', sessionId: 'session' } as Parameters<typeof auth.set>[0]);
	authReady.set(true); projectSwitching.set(false);
	transport.get.mockResolvedValue({ schedules: [], errors: [] });
});
afterEach(() => cleanup());

describe('header instance usage reminder authority', () => {
	it('shares the bell and dashboard reminder read while either consumer can cancel independently', async () => {
		const pending = Promise.withResolvers<{ schedules: UsageScheduleInfo[]; errors: unknown[] }>();
		transport.get.mockReturnValueOnce(pending.promise);
		const bell = render(UsageScheduleBellHarness);
		const reminders = render(UsageScheduleReminders);
		await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(1));
		const signal = transport.get.mock.calls[0][3].signal as AbortSignal;
		reminders.unmount();
		expect(signal.aborted).toBe(false);
		pending.resolve({ schedules: [schedule(Date.now() + 86400000)], errors: [] });
		await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('1'));
		await fireEvent.click(screen.getByTestId('refresh'));
		await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(2));
		bell.unmount();
	});

	it('cancels the underlying inventory when its last subscriber leaves and never reuses a settled result', async () => {
		transport.get.mockReturnValueOnce(Promise.withResolvers().promise);
		const first = new AbortController();
		const second = new AbortController();
		const a = loadUsageSchedules('token-a', 'project-a', first.signal);
		const b = loadUsageSchedules('token-a', 'project-a', second.signal);
		const rejectedA = expect(a).rejects.toMatchObject({ name: 'AbortError' });
		const rejectedB = expect(b).rejects.toMatchObject({ name: 'AbortError' });
		first.abort();
		expect(transport.get.mock.calls[0][3].signal.aborted).toBe(false);
		second.abort();
		await Promise.all([rejectedA, rejectedB]);
		expect(transport.get.mock.calls[0][3].signal.aborted).toBe(true);
		const signal = new AbortController().signal;
		await loadUsageSchedules('token-a', 'project-a', signal);
		await loadUsageSchedules('token-a', 'project-a', signal);
		expect(transport.get).toHaveBeenCalledTimes(3);
	});

	it('delivers a shared rejection to both consumers without replaying the inventory read', async () => {
		const pending = Promise.withResolvers();
		transport.get.mockReturnValueOnce(pending.promise);
		const a = loadUsageSchedules('token-a', 'project-a', new AbortController().signal);
		const b = loadUsageSchedules('token-a', 'project-a', new AbortController().signal);
		const error = Object.assign(new Error('session rejected'), { status: 401 });
		const results = Promise.allSettled([a, b]);
		pending.reject(error);
		expect(await results).toEqual([{ status: 'rejected', reason: error }, { status: 'rejected', reason: error }]);
		expect(transport.get).toHaveBeenCalledTimes(1);
	});

	it('lights the bell for due schedules with zero unread announcements and reports overdue separately', async () => {
		const now = Date.now();
		transport.get.mockResolvedValue({ schedules: [schedule(now + 2 * 86400000), schedule(now - 1000), schedule(now + 30 * 86400000)], errors: [] });
		const { container } = render(UsageScheduleBellHarness);
		await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('2'));
		expect(screen.getByTestId('overdue').textContent).toBe('1');
		expect(container.querySelector('[data-unread-indicator]')).not.toBeNull();
		expect(transport.get).toHaveBeenCalledWith('/api/v1/instances/usage-schedules', 'token-a', 'project-a', expect.objectContaining({ cache: 'no-store' }));
	});

	it('does not turn failures or partial invalid inventory into a verified zero badge', async () => {
		transport.get.mockRejectedValueOnce(new Error('provider unavailable'));
		const { container } = render(UsageScheduleBellHarness);
		await waitFor(() => expect(screen.getByTestId('failed').textContent).toBe('true'));
		expect(screen.getByTestId('count').textContent).toBe('unknown');
		expect(container.querySelector('[data-unread-indicator]')).not.toBeNull();
		transport.get.mockResolvedValueOnce({ schedules: [], errors: [{ instance_id: 'broken', message: 'incomplete' }] });
		await fireEvent.click(screen.getByTestId('refresh'));
		await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('1'));
		expect(screen.getByTestId('overdue').textContent).toBe('1');
		expect(screen.getByTestId('failed').textContent).toBe('false');
		expect(container.querySelector('[data-unread-indicator]')).not.toBeNull();
	});

	it('ignores an old project request after A→B→A and issues independent no-store reads', async () => {
		const old = Promise.withResolvers<{ schedules: UsageScheduleInfo[]; errors: unknown[] }>();
		transport.get.mockReturnValueOnce(old.promise);
		render(UsageScheduleBellHarness);
		await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(1));
		const signal = transport.get.mock.calls[0][3].signal;
		auth.update(value => ({ ...value, projectId: 'project-b' }));
		auth.update(value => ({ ...value, projectId: 'project-a' }));
		await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(3));
		old.resolve({ schedules: [schedule(Date.now() - 1000)], errors: [] });
		await tick();
		expect(signal.aborted).toBe(true);
		expect(screen.getByTestId('count').textContent).toBe('0');
		expect(screen.getByTestId('overdue').textContent).toBe('0');
	});

	it('keeps a verified count through token refresh and uses the latest credential on explicit refresh', async () => {
		transport.get.mockResolvedValue({ schedules: [schedule(Date.now() + 86400000)], errors: [] });
		render(UsageScheduleBellHarness);
		await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('1'));
		auth.update(value => ({ ...value, token: 'refreshed-token' }));
		await tick();
		expect(transport.get).toHaveBeenCalledTimes(1);
		expect(screen.getByTestId('count').textContent).toBe('1');
		await fireEvent.click(screen.getByTestId('refresh'));
		await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(2));
		expect(transport.get.mock.calls[1][1]).toBe('refreshed-token');
	});

	it.each([
		{ delete_volumes: true }, { revision: '' }, { expires_at: '2026-10-29T12:00:00' },
	] as Partial<UsageScheduleInfo>[])('counts malformed metadata as attention rather than normal or empty: %s', async invalid => {
		transport.get.mockResolvedValue({ schedules: [schedule(Date.now() + 30 * 86400000, invalid)], errors: [] });
		render(UsageScheduleBellHarness);
		await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('1'));
		expect(screen.getByTestId('overdue').textContent).toBe('1');
		expect(screen.getByTestId('failed').textContent).toBe('false');
	});

	it('does not fetch outside authenticated enabled project scope and clears the indicator on scope loss', async () => {
		authReady.set(false);
		const view = render(UsageScheduleBellHarness);
		await tick(); expect(transport.get).not.toHaveBeenCalled();
		authReady.set(true);
		await waitFor(() => expect(transport.get).toHaveBeenCalledTimes(1));
		await view.rerender({ enabled: false });
		expect(screen.getByTestId('count').textContent).toBe('unknown');
		await fireEvent.click(screen.getByTestId('refresh'));
		expect(transport.get).toHaveBeenCalledTimes(1);
	});
});
