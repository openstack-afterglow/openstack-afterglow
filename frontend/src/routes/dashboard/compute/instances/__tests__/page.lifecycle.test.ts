import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { derived, writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn(),
	refresh: undefined as undefined | (() => Promise<void>),
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, delete: mocks.delete },
	ApiError: class extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token-a', projectId: 'project-a', canWrite: true });
	return { auth, canWrite: derived(auth, ($auth) => $auth.canWrite) };
});
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/api/mutations', () => ({ apiMut: (_label: string, dispatch: () => Promise<unknown>) => dispatch() }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('$lib/utils/swr.svelte', () => ({ createSwr: () => ({ swrGet: () => null, swrSet: vi.fn() }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (refresh: () => Promise<void>) => {
		mocks.refresh = refresh;
		return { active: false, intervalSeconds: 10, intervalOptions: [10, 15, 30, 60], setBoost: vi.fn() };
	},
}));

import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/instance';
import Page from '../+page.svelte';

const instance = (id: string, status = 'SHUTOFF'): Instance => ({
	id, name: id, status, image_name: 'Ubuntu', flavor_name: 'small', ip_addresses: [],
	created_at: null, union_libraries: [], union_strategy: null, project_id: 'project-a',
});
let rows: Instance[];
async function mount() {
	render(Page);
	await screen.findByRole('button', { name: 'vm-a' });
}
async function select(id: string) {
	await fireEvent.click(screen.getByRole('checkbox', { name: t('row.select', { name: id }) }).closest('label')!);
}
function bulkDelete() {
	return within(screen.getByRole('region', { name: t('list.bulkActions') })).queryByRole('button', { name: t('list.delete') });
}
async function openAction(kind: 'delete' | 'shelve' | 'stop') {
	await fireEvent.click(screen.getByRole('button', { name: t('rowActions.instanceActions', { name: 'vm-a' }) }));
	await fireEvent.click(screen.getByRole('button', { name: kind === 'stop' ? t('list.stop') : t(`rowActions.${kind}`) }));
}
async function pendingConfirmation() {
	const pending = Promise.withResolvers<boolean>();
	mocks.confirm.mockReturnValue(pending.promise);
	return pending;
}
async function settle(pending: { resolve(value: boolean): void }) {
	pending.resolve(true);
	await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
}

describe('consumer instance list lifecycle safety', () => {
	beforeEach(() => {
		rows = [instance('vm-a'), instance('vm-b')];
		auth.update((state) => ({ ...state, token: 'token-a', projectId: 'project-a', canWrite: true }));
		mocks.get.mockReset().mockImplementation((path: string) => Promise.resolve(
			path.endsWith('metrics-summary-batch') ? { monitoring_available: false, instances: {} } : rows,
		));
		mocks.post.mockReset().mockResolvedValue({ results: [{ id: 'vm-a', ok: true }, { id: 'vm-b', ok: true }] });
		mocks.delete.mockReset().mockResolvedValue(undefined);
		mocks.confirm.mockReset().mockResolvedValue(true);
	});

	it('never offers deletion for mixed, missing or non-exact stopped selections', async () => {
		rows[1] = instance('vm-b', 'ACTIVE');
		await mount();
		await select('vm-a');
		expect(bulkDelete()).toBeTruthy();
		await select('vm-b');
		expect(bulkDelete()).toBeNull();
		for (const status of ['BUILD', 'SHELVED', 'SHELVED_OFFLOADED', 'ERROR', 'shutoff', '']) {
			rows = [instance('vm-a'), instance('vm-b', status)];
			await mocks.refresh!();
			await waitFor(() => expect(bulkDelete()).toBeNull());
		}
		rows = [instance('vm-a', 'ACTIVE')];
		await mocks.refresh!();
		await waitFor(() => expect(bulkDelete()).toBeNull());
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('deletes the entire exact stopped selection without filtering', async () => {
		await mount();
		await select('vm-a');
		await select('vm-b');
		await fireEvent.click(bulkDelete()!);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/instances/bulk-action',
			{ action: 'delete', instance_ids: ['vm-a', 'vm-b'] }, 'token-a', 'project-a'));
		expect(mocks.confirm.mock.calls[0][0]).toContain(t('panel.stoppedQuotaWarning'));
	});

	it.each(['live', 'missing', 'selection', 'scope', 'permission'] as const)(
		'blocks a bulk confirmation after %s changes', async (change) => {
			await mount();
			await select('vm-a');
			await select('vm-b');
			const pending = await pendingConfirmation();
			await fireEvent.click(bulkDelete()!);
			if (change === 'live' || change === 'missing') {
				rows = change === 'live' ? [instance('vm-a'), instance('vm-b', 'ACTIVE')] : [instance('vm-a')];
				await mocks.refresh!();
			} else if (change === 'selection') {
				await select('vm-b');
				await select('vm-b');
			} else if (change === 'scope') {
				auth.update((state) => ({ ...state, projectId: 'project-b' }));
				auth.update((state) => ({ ...state, projectId: 'project-a' }));
			} else auth.update((state) => ({ ...state, canWrite: false }));
			pending.resolve(true);
			await waitFor(() => expect(mocks.confirm).toHaveBeenCalledOnce());
			await Promise.resolve();
			expect(mocks.post).not.toHaveBeenCalled();
		},
	);

	it.each(['delete', 'shelve'] as const)('blocks individual %s when the target becomes live', async (kind) => {
		await mount();
		const pending = await pendingConfirmation();
		await openAction(kind);
		rows = [instance('vm-a', 'ACTIVE'), instance('vm-b')];
		await mocks.refresh!();
		await settle(pending);
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it.each(['delete', 'shelve'] as const)('blocks individual %s after scope or permission changes', async (kind) => {
		await mount();
		const pending = await pendingConfirmation();
		await openAction(kind);
		auth.update((state) => ({ ...state, projectId: 'project-b', canWrite: false }));
		await settle(pending);
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('preserves ACTIVE stop and appends the stopped quota warning', async () => {
		rows[0] = instance('vm-a', 'ACTIVE');
		await mount();
		await openAction('stop');
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/instances/vm-a/stop', {}, 'token-a', 'project-a'));
		expect(mocks.confirm.mock.calls[0][0]).toContain(t('panel.stoppedQuotaWarning'));
	});
});
