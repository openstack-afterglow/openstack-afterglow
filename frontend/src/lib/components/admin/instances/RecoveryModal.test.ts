import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as SvelteStore from 'svelte/store';
import { ApiError } from '$lib/api/errors';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { RecoveryAnalysis, RecoveryObservation, RecoveryResult, RecoveryStep } from '$lib/types/adminInstance';
import RecoveryModal from './RecoveryModal.svelte';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', async () => ({
	api, ApiError: (await vi.importActual<{ ApiError: typeof ApiError }>('$lib/api/errors')).ApiError,
}));
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await vi.importActual<typeof SvelteStore>('svelte/store');
	return { auth: writable({ token: 'test-token', projectId: 'current-project', userId: 'admin-user' }) };
});

const serverId = 'synthetic-server-id';
const serverName = 'Recovery test VM';
const root = `/api/v1/admin/instances/${serverId}`;
const requestedAt = '2026-11-18T13:30:00.123456+00:00';
const statusPath = `${root}/recovery-status?requested_at=2026-11-18T13%3A30%3A00.123456%2B00%3A00`;
const reset: RecoveryStep = { action: 'reset_server_state', description: 'Reset server state' };
const restart: RecoveryStep = { action: 'hard_reboot', description: 'Request reboot' };
const plan: RecoveryAnalysis = {
	server: {
		id: serverId, name: serverName, compute_host: 'compute-source', status: 'ERROR', power_state: 1,
		fault: { message: 'No console available', code: 404, created: '2026-11-18T13:29:41Z' },
	},
	last_error_migration: {
		migration_type: 'live-migration', source_compute: 'compute-source', dest_compute: 'compute-dest',
		created_at: '2026-11-12T09:19:25+00:00', updated_at: '2026-11-12T09:20:05+00:00',
	},
	volumes: [], ports: [],
	checks: [{ key: 'live_migration_rollback', label: 'Native check label', passed: true, detail: 'Rollback event recorded' }],
	scenario: 'live_migration_rolled_back', scenario_description: 'Native description',
	plan_fingerprint: '1'.repeat(64),
	steps: [reset], auto_executable: true, placement_note: null,
};

const accepted: RecoveryResult = {
	executed: true, recovered: false, observed_status: 'REBOOT', scenario: plan.scenario,
	requested_at: requestedAt, observed_task_state: null, observed_fault: null,
	unconfirmed_action: null, observed_acceptance: true, observation_may_recover: true,
	observation_timed_out: false, observation_terminal: false,
	steps: [{ ...restart, status: 'success' }],
};

const rebooting: RecoveryResult = {
	...accepted, observed_status: 'ERROR', observed_task_state: 'reboot_pending_hard', observation_timed_out: true,
};
const recovered: RecoveryObservation = {
	recovered: true, observed_status: 'ACTIVE', observed_task_state: null, observed_fault: null,
	observed_acceptance: true,
	observation_timed_out: false, observation_terminal: true,
};

function openModal() {
	const callbacks = { onClose: vi.fn(), onRefresh: vi.fn(), onRecovered: vi.fn() };
	render(RecoveryModal, { serverId, serverName, ...callbacks });
	return callbacks;
}

async function confirmAndSubmit(useClock = false) {
	const textbox = await screen.findByRole('textbox', { name: 'Confirm instance name' });
	if (useClock) vi.useFakeTimers();
	await fireEvent.input(textbox, { target: { value: serverName } });
	await fireEvent.click(screen.getByRole('button', { name: 'Run recovery' }));
}

afterEach(() => vi.useRealTimers());

beforeEach(() => {
	initLocale('en');
	api.get.mockReset().mockResolvedValue(plan);
	api.post.mockReset();
});

describe('instance recovery dialog', () => {
	it('separates current fault and historical migration, including independent timestamps', async () => {
		openModal();
		const dialog = screen.getByRole('dialog', { name: 'Instance recovery analysis' });
		const fault = await within(dialog).findByRole('region', { name: 'Current Nova fault' });
		const migration = within(dialog).getByRole('region', { name: 'Last failed migration' });
		expect(within(fault).getByText('No console available')).toBeTruthy();
		expect(within(fault).getByText('404')).toBeTruthy();
		expect(fault.querySelector('time')?.dateTime).toBe(plan.server.fault?.created);
		expect(within(migration).queryByText('No console available')).toBeNull();
		for (const field of ['live-migration', 'compute-source', 'compute-dest']) {
			expect(within(migration).getByText(field)).toBeTruthy();
		}
		expect([...migration.querySelectorAll('time')].map(time => time.dateTime)).toEqual([
			plan.last_error_migration?.created_at, plan.last_error_migration?.updated_at,
		]);
		expect(api.get).toHaveBeenCalledWith(`${root}/recovery-analysis`, 'test-token', 'current-project', expect.objectContaining({ cache: 'no-store' }));
	});

	it('does not offer mutation when automatic recovery is blocked', async () => {
		api.get.mockResolvedValue({
			...plan, scenario: 'manual_review', auto_executable: false, steps: [{ action: 'manual', description: 'Manual review' }],
			checks: [{ ...plan.checks[0], passed: false, detail: 'Rollback event unavailable' }],
		});
		const callbacks = openModal();
		await screen.findByText('Manual review is required');
		expect(screen.getByText('Not passed')).toBeTruthy();
		expect(screen.getByText('Rollback event unavailable')).toBeTruthy();
		expect(screen.queryByRole('textbox')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Run recovery' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(api.post).not.toHaveBeenCalled();
		expect(callbacks.onClose).toHaveBeenCalledTimes(1);
		expect(callbacks.onRefresh).not.toHaveBeenCalled();
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});

	it('binds confirmation to the reviewed plan and shows confirmed recovery before refreshing', async () => {
		api.post.mockResolvedValue({ ...accepted, ...recovered, steps: [{ ...reset, status: 'success' }] });
		const callbacks = openModal();
		await screen.findByText(/without rebooting the guest/);
		expect(screen.queryByText('Request a hard guest restart')).toBeNull();
		expect(screen.getByText(/Type “Recovery test VM” exactly/)).toBeTruthy();
		const textbox = screen.getByRole('textbox', { name: 'Confirm instance name' });
		const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Run recovery' });
		expect(button.disabled).toBe(true);
		await fireEvent.input(textbox, { target: { value: serverName.toLowerCase() } });
		expect(button.disabled).toBe(true);
		await fireEvent.submit(button.form!);
		expect(api.post).not.toHaveBeenCalled();
		await confirmAndSubmit();
		await screen.findByText('Last observed Nova status: ACTIVE');
		expect(screen.getByText('Nova confirmed recovery.')).toBeTruthy();
		expect(api.post).toHaveBeenCalledExactlyOnceWith(`${root}/recover`, { plan_fingerprint: plan.plan_fingerprint }, 'test-token', 'current-project', expect.objectContaining({ timeoutMs: 120_000, replayOnUnauthorized: false }));
		expect(callbacks.onRefresh).not.toHaveBeenCalled();
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
		expect(callbacks.onRecovered).toHaveBeenCalledTimes(1);
	});

	it('warns about hard restart, blocks duplicate submits and does not report acceptance as recovery', async () => {
		const fingerprint = '2'.repeat(64);
		api.get.mockResolvedValue({ ...plan, server: { ...plan.server, power_state: 4 }, steps: [restart], plan_fingerprint: fingerprint });
		const pending = Promise.withResolvers<RecoveryResult>();
		api.post.mockReturnValue(pending.promise);
		const callbacks = openModal();
		await screen.findByText('This plan requests a hard restart of the guest. Workloads may be interrupted.');
		const steps = screen.getByRole('heading', { name: 'Recommended recovery steps' }).closest('section')!;
		expect(within(steps).getAllByRole('listitem').map(item => item.textContent)).toEqual(['Request a hard guest restart']);
		const form = screen.getByRole<HTMLButtonElement>('button', { name: 'Run recovery' }).form!;
		await confirmAndSubmit(true);
		await fireEvent.submit(form);
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(callbacks.onClose).not.toHaveBeenCalled();
		expect(api.post).toHaveBeenCalledExactlyOnceWith(`${root}/recover`, { plan_fingerprint: fingerprint }, 'test-token', 'current-project', expect.anything());
		pending.resolve(accepted);
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByText('Last observed Nova status: REBOOT')).toBeTruthy();
		expect(screen.getByText(/accepted all requests but did not confirm recovery/)).toBeTruthy();
		expect(screen.queryByText('Nova confirmed recovery.')).toBeNull();
		await vi.advanceTimersByTimeAsync(12_000);
		expect(api.get).toHaveBeenCalledTimes(1);
		expect(callbacks.onRefresh).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});

	it('keeps known evidence through UNKNOWN and polls nonterminal ERROR until Nova confirms recovery', async () => {
		api.post.mockResolvedValue(rebooting);
		api.get.mockResolvedValueOnce(plan)
			.mockResolvedValueOnce({ ...recovered, recovered: false, observed_status: 'UNKNOWN', observation_terminal: false })
			.mockResolvedValueOnce({ ...recovered, recovered: false, observed_status: 'ERROR', observation_terminal: false })
			.mockResolvedValueOnce(recovered);
		const callbacks = openModal();
		await confirmAndSubmit(true);
		expect(screen.getByText('Last observed Nova status: ERROR')).toBeTruthy();
		expect(screen.getByText('Last observed Nova task state: reboot_pending_hard')).toBeTruthy();
		expect(screen.getByText(/still reports a reboot task/)).toBeTruthy();
		expect(screen.queryByText('No console available')).toBeNull();
		expect(screen.getByRole('region', { name: 'Current Nova fault' }).querySelector('time')).toBeNull();
		await vi.advanceTimersByTimeAsync(4_000);
		expect(api.get).toHaveBeenLastCalledWith(statusPath, 'test-token', 'current-project',
			expect.objectContaining({ signal: expect.any(AbortSignal), cache: 'no-store' }));
		expect(screen.getByText('Last observed Nova task state: reboot_pending_hard')).toBeTruthy();
		expect(screen.queryByText('Last observed Nova status: UNKNOWN')).toBeNull();
		await vi.advanceTimersByTimeAsync(4_000);
		expect(screen.getByText('Last observed Nova status: ERROR')).toBeTruthy();
		expect(screen.queryByText(/reboot_pending_hard/)).toBeNull();
		expect(screen.queryByText(/The instance did not recover/)).toBeNull();
		await vi.advanceTimersByTimeAsync(4_000);
		expect(screen.getByText('Last observed Nova status: ACTIVE')).toBeTruthy();
		expect(screen.getByText('Nova confirmed recovery.')).toBeTruthy();
		expect(screen.getByText('Request a hard guest restart')).toBeTruthy();
		expect(screen.queryByText('Still checking Nova status.')).toBeNull();
		await vi.advanceTimersByTimeAsync(60_000);
		expect(api.get).toHaveBeenCalledTimes(4);
		expect(api.post).toHaveBeenCalledTimes(1);
		expect(callbacks.onRefresh).not.toHaveBeenCalled();
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
		expect(callbacks.onRecovered).toHaveBeenCalledTimes(1);
	});

	it.each([true, false])('latches acceptance of an unconfirmed request without retrying it (may recover: %s)', async mayRecover => {
		const unconfirmedAction = mayRecover ? 'hard_reboot' : 'reset_server_state';
		api.post.mockResolvedValue({
			...accepted, executed: false, observed_status: 'ERROR', unconfirmed_action: unconfirmedAction,
			observed_acceptance: false, observation_may_recover: mayRecover,
			steps: mayRecover ? [{ ...restart, status: 'unconfirmed' }]
				: [{ ...reset, status: 'unconfirmed' }, { ...restart, status: 'skipped' }],
		});
		api.get.mockResolvedValueOnce(plan)
			.mockResolvedValueOnce({ ...recovered, recovered: false, observed_status: 'ERROR', observation_terminal: false, observed_acceptance: false })
			.mockResolvedValueOnce({ ...recovered, recovered: false, observed_status: 'REBOOT', observation_terminal: false })
			.mockResolvedValueOnce(recovered);
		const callbacks = openModal();
		await confirmAndSubmit(true);
		expect(screen.getByText('Acceptance unconfirmed')).toBeTruthy();
		expect(screen.getByText(/will not be sent again automatically/)).toBeTruthy();
		expect(screen.queryByText(/The instance did not recover/)).toBeNull();
		const pollPath = `${statusPath}&unconfirmed_action=${unconfirmedAction}&observation_may_recover=${mayRecover}`;
		await vi.advanceTimersByTimeAsync(8_000);
		expect(api.get.mock.calls.slice(1).map(call => call[0])).toEqual([pollPath, pollPath]);
		expect(screen.getByText('Last observed Nova status: REBOOT')).toBeTruthy();
		await vi.advanceTimersByTimeAsync(4_000);
		expect(api.get).toHaveBeenLastCalledWith(mayRecover ? statusPath : `${statusPath}&observation_may_recover=false`,
			'test-token', 'current-project', expect.anything());
		expect(screen.getByText('Last observed Nova status: ACTIVE')).toBeTruthy();
		expect(Boolean(screen.queryByText('Nova confirmed recovery.'))).toBe(mayRecover);
		expect(api.post).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
		expect(callbacks.onRecovered).toHaveBeenCalledTimes(mayRecover ? 1 : 0);
	});

	it.each(['post', 'status'])('stops at terminal ERROR from %s and displays only the fresh fault', async source => {
		const fault = { message: 'Domain start failed', created: '2026-11-18T13:31:00Z', code: 500 };
		const terminal: RecoveryObservation = {
			...recovered, recovered: false, observed_status: 'ERROR', observed_fault: fault,
		};
		api.post.mockResolvedValue(source === 'post' ? { ...accepted, ...terminal } : rebooting);
		api.get.mockResolvedValueOnce(plan).mockResolvedValueOnce(terminal);
		const callbacks = openModal();
		await confirmAndSubmit(true);
		await vi.advanceTimersByTimeAsync(60_000);
		const region = screen.getByRole('region', { name: 'Current Nova fault' });
		expect(within(region).getByText(fault.message)).toBeTruthy();
		expect(within(region).getByText('500')).toBeTruthy();
		expect(region.querySelector('time')?.dateTime).toBe(fault.created);
		expect(screen.getByText(/ERROR with no task in progress/)).toBeTruthy();
		expect(screen.queryByText('No console available')).toBeNull();
		expect(screen.queryByText('Nova confirmed recovery.')).toBeNull();
		expect(api.get).toHaveBeenCalledTimes(source === 'post' ? 1 : 2);
		expect(api.post).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});

	it.each(['close', 'deadline'])('aborts an in-flight status GET at %s and ignores its late result', async stopAt => {
		const pending = Promise.withResolvers<RecoveryObservation>();
		api.post.mockResolvedValue(rebooting);
		api.get.mockResolvedValueOnce(plan).mockReturnValueOnce(pending.promise);
		const callbacks = openModal();
		await confirmAndSubmit(true);
		await vi.advanceTimersByTimeAsync(4_000);
		const signal: AbortSignal = api.get.mock.calls[1][3].signal;
		expect(signal.aborted).toBe(false);
		if (stopAt === 'close') {
			await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
			expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
		} else {
			await vi.advanceTimersByTimeAsync(56_000);
			expect(screen.getByText(/still reports a reboot task/)).toBeTruthy();
			expect(screen.queryByText('Still checking Nova status.')).toBeNull();
		}
		expect(signal.aborted).toBe(true);
		pending.resolve(recovered);
		await vi.advanceTimersByTimeAsync(60_000);
		expect(screen.queryByText('Nova confirmed recovery.')).toBeNull();
		expect(api.get).toHaveBeenCalledTimes(2);
		expect(api.post).toHaveBeenCalledTimes(1);
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});

	it('reports a partial failure with the observed status and individual step outcomes', async () => {
		api.get.mockResolvedValue({ ...plan, scenario: 'generic_error', steps: [reset, restart] });
		api.post.mockResolvedValue({
			...accepted, executed: false, observed_status: 'ERROR',
			scenario: 'generic_error',
			steps: [{ ...reset, status: 'failed', detail: 'State reset rejected' }, { ...restart, status: 'skipped' }],
		});
		const callbacks = openModal();
		await confirmAndSubmit();
		await screen.findByText('Last observed Nova status: ERROR');
		expect(screen.getByText(/At least one recovery step was not accepted/)).toBeTruthy();
		expect(screen.getByText('State reset rejected')).toBeTruthy();
		expect(screen.getByText('Skipped')).toBeTruthy();
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRefresh).toHaveBeenCalledTimes(1);
	});

	it.each([
		{ error: new ApiError(409, 'Still active', 'RECOVERY_IN_PROGRESS'), expected: /Recovery is already in progress/ },
		{ error: new ApiError(409, 'Safety failure', 'RECOVERY_BLOCKED'), expected: /Recovery was blocked/ },
		{ error: new ApiError(409, 'Evidence changed', 'RECOVERY_PLAN_CHANGED'), expected: /reviewed recovery plan changed/ },
		{ error: new ApiError(409, 'Lost lease', 'RECOVERY_LOCK_LOST'), expected: /Recovery was blocked/ },
		{ error: new ApiError(409, 'Conflict'), expected: /Recovery was blocked/ },
		{ error: new ApiError(503, 'Unavailable'), expected: /This request did not change anything/ },
		{ error: new TypeError('Network unavailable'), expected: /recovery outcome is unknown/ },
	])('requires a fresh review after an unsuccessful response ($error.message)', async ({ error, expected }) => {
		api.post.mockRejectedValue(error);
		const callbacks = openModal();
		await confirmAndSubmit();
		await screen.findByText(expected);
		expect(screen.queryByRole('button', { name: 'Run recovery' })).toBeNull();
		expect(screen.queryByText('Nova confirmed recovery.')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRefresh).toHaveBeenCalledTimes(error instanceof TypeError ? 1 : 0);
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});
});
