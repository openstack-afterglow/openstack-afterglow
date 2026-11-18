import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as SvelteStore from 'svelte/store';
import { ApiError } from '$lib/api/errors';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { RecoveryAnalysis, RecoveryResult, RecoveryStep } from '$lib/types/adminInstance';
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
	steps: [{ ...reset, status: 'success' }, { ...restart, status: 'success' }],
};

function openModal() {
	const callbacks = { onClose: vi.fn(), onRecovered: vi.fn() };
	render(RecoveryModal, { serverId, serverName, ...callbacks });
	return callbacks;
}

async function confirmAndSubmit() {
	await fireEvent.input(await screen.findByRole('textbox', { name: 'Confirm instance name' }), { target: { value: serverName } });
	await fireEvent.click(screen.getByRole('button', { name: 'Run recovery' }));
}

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
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});

	it('binds confirmation to the reviewed plan and shows confirmed recovery before refreshing', async () => {
		api.post.mockResolvedValue({ ...accepted, recovered: true, observed_status: 'ACTIVE', steps: [accepted.steps[0]] });
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
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRecovered).toHaveBeenCalledTimes(1);
	});

	it('warns about hard restart, blocks duplicate submits and does not report acceptance as recovery', async () => {
		const fingerprint = '2'.repeat(64);
		api.get.mockResolvedValue({ ...plan, server: { ...plan.server, power_state: 4 }, steps: [reset, restart], plan_fingerprint: fingerprint });
		const pending = Promise.withResolvers<RecoveryResult>();
		api.post.mockReturnValue(pending.promise);
		const callbacks = openModal();
		await screen.findByText(/Workloads may be interrupted/);
		expect(screen.getByText('Request a hard guest restart')).toBeTruthy();
		const form = screen.getByRole<HTMLButtonElement>('button', { name: 'Run recovery' }).form!;
		await confirmAndSubmit();
		await fireEvent.submit(form);
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(callbacks.onClose).not.toHaveBeenCalled();
		expect(api.post).toHaveBeenCalledExactlyOnceWith(`${root}/recover`, { plan_fingerprint: fingerprint }, 'test-token', 'current-project', expect.anything());
		pending.resolve(accepted);
		await screen.findByText('Last observed Nova status: REBOOT');
		expect(screen.getByText(/accepted all requests but did not confirm recovery/)).toBeTruthy();
		expect(screen.queryByText('Nova confirmed recovery.')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});

	it('reports a partial failure with the observed status and individual step outcomes', async () => {
		api.get.mockResolvedValue({ ...plan, steps: [reset, restart] });
		api.post.mockResolvedValue({
			...accepted, executed: false, observed_status: 'ERROR',
			steps: [{ ...reset, status: 'failed', detail: 'State reset rejected' }, { ...restart, status: 'skipped' }],
		});
		const callbacks = openModal();
		await confirmAndSubmit();
		await screen.findByText('Last observed Nova status: ERROR');
		expect(screen.getByText(/At least one recovery step was not accepted/)).toBeTruthy();
		expect(screen.getByText('State reset rejected')).toBeTruthy();
		expect(screen.getByText('Skipped')).toBeTruthy();
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});

	it.each([
		{ error: new ApiError(409, 'Recovery plan changed'), expected: /latest safety check blocked recovery/ },
		{ error: new TypeError('Network unavailable'), expected: /recovery outcome is unknown/ },
	])('requires a fresh review after an unsuccessful response ($error.message)', async ({ error, expected }) => {
		api.post.mockRejectedValue(error);
		const callbacks = openModal();
		await confirmAndSubmit();
		await screen.findByText(expected);
		expect(screen.queryByRole('button', { name: 'Run recovery' })).toBeNull();
		expect(screen.queryByText('Nova confirmed recovery.')).toBeNull();
		expect(callbacks.onRecovered).not.toHaveBeenCalled();
	});
});
