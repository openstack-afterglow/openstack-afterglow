import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import type { AdminInstance } from '$lib/types/adminInstance';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), confirm: vi.fn(),
	refresh: undefined as undefined | (() => void),
}));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post, prefetch: vi.fn() } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', isSystemAdmin: true }),
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('$lib/stores/projectNames', () => ({
	projectNames: Object.assign(writable(new Map<string, string>()), { load: vi.fn() }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (refresh: () => void) => {
		mocks.refresh = refresh;
		return { active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60], setBoost: vi.fn() };
	},
}));

import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/admin-compute';
import { t as instanceT } from '$lib/i18n/ns/instance';
import Page from '../+page.svelte';

const instance = (id: string, status = 'SHUTOFF'): AdminInstance => ({
	id, name: id, status, project_id: 'tenant-a', user_id: 'user-a', flavor: 'small', host: 'compute-a', created_at: null,
});
let rows: AdminInstance[];
async function mount() {
	render(Page);
	await screen.findByRole('button', { name: 'vm-a' });
}
async function select(id: string) {
	await fireEvent.click(screen.getByRole('checkbox', { name: t('instances.table.select', { name: id }) }).closest('label')!);
}
function bulkDelete() {
	return within(screen.getByRole('region', { name: t('instances.bulk.label') })).queryByRole('button', { name: t('instances.bulk.delete') });
}
async function refreshRows(next: AdminInstance[]) {
	rows = next;
	mocks.refresh!();
	await Promise.resolve();
	await tick();
}

describe('administrator instance list lifecycle safety', () => {
	beforeEach(() => {
		vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
		rows = [instance('vm-a'), instance('vm-b')];
		auth.update((state) => ({ ...state, token: 'token-a', projectId: 'project-a', isSystemAdmin: true }));
		mocks.get.mockReset().mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/all-instances')) return Promise.resolve({ items: rows, next_marker: 'next-marker', count: rows.length });
			if (path.endsWith('/health')) return Promise.resolve({ total: rows.length, active: 0, error: 0, with_alerts: 0, gpu_count: 0 });
			return Promise.resolve([]);
		});
		mocks.post.mockReset().mockResolvedValue({ results: [{ id: 'vm-a', ok: true }, { id: 'vm-b', ok: true }] });
		mocks.confirm.mockReset().mockResolvedValue(true);
	});
	afterEach(() => vi.unstubAllGlobals());

	it('exposes deletion only for an all-exact-SHUTOFF selection', async () => {
		await mount();
		await select('vm-a');
		await select('vm-b');
		expect(bulkDelete()).toBeTruthy();
		for (const status of ['ACTIVE', 'BUILD', 'SHELVED', 'SHELVED_OFFLOADED', 'ERROR', 'shutoff', '']) {
			await refreshRows([instance('vm-a'), instance('vm-b', status)]);
			expect(bulkDelete()).toBeNull();
		}
		await refreshRows([instance('vm-a', 'ACTIVE')]);
		expect(bulkDelete()).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('dispatches every selected stopped ID without filtering live rows', async () => {
		await mount();
		await select('vm-a');
		await select('vm-b');
		await fireEvent.click(bulkDelete()!);
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/instances/bulk-action',
			{ action: 'delete', instance_ids: ['vm-a', 'vm-b'] }, 'token-a', 'project-a'));
		expect(mocks.confirm.mock.calls[0][0]).toContain(instanceT('panel.stoppedQuotaWarning'));
	});

	it.each(['live', 'missing', 'selection', 'scope', 'permission', 'filter', 'page', 'target-project'] as const)(
		'blocks a stale delete confirmation after %s changes', async (change) => {
			await mount();
			await select('vm-a');
			await select('vm-b');
			const pending = Promise.withResolvers<boolean>();
			mocks.confirm.mockReturnValue(pending.promise);
			await fireEvent.click(bulkDelete()!);
			if (change === 'live') await refreshRows([instance('vm-a'), instance('vm-b', 'ACTIVE')]);
			else if (change === 'missing') await refreshRows([instance('vm-a')]);
			else if (change === 'target-project') await refreshRows([instance('vm-a'), { ...instance('vm-b'), project_id: 'tenant-b' }]);
			else if (change === 'selection') {
				await select('vm-b');
				await select('vm-b');
			} else if (change === 'scope') {
				auth.update((state) => ({ ...state, projectId: 'project-b' }));
				auth.update((state) => ({ ...state, projectId: 'project-a' }));
			} else if (change === 'permission') auth.update((state) => ({ ...state, isSystemAdmin: false }));
			else if (change === 'filter') {
				await fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'SHUTOFF' } });
			} else await fireEvent.click(screen.getByRole('button', { name: '10' }));
			pending.resolve(true);
			await pending.promise;
			await Promise.resolve();
			expect(mocks.post).not.toHaveBeenCalled();
		},
	);

	it('keeps ACTIVE bulk stop available with the quota warning', async () => {
		rows = [instance('vm-a', 'ACTIVE'), instance('vm-b', 'ACTIVE')];
		await mount();
		await select('vm-a');
		await select('vm-b');
		const overlay = within(screen.getByRole('region', { name: t('instances.bulk.label') }));
		await fireEvent.click(overlay.getByRole('button', { name: t('instances.bulk.stop') }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/instances/bulk-action',
			{ action: 'stop', instance_ids: ['vm-a', 'vm-b'] }, 'token-a', 'project-a'));
		expect(mocks.confirm.mock.calls[0][0]).toContain(instanceT('panel.stoppedQuotaWarning'));
	});
});
