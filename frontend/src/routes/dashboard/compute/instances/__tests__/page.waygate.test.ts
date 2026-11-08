import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { derived, writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, delete: mocks.delete, withExperience() { return this; } },
	ApiError: class extends Error { status = 500; },
}));
vi.mock('$app/stores', () => ({ page: writable({ url: new URL('http://localhost/dashboard/compute/instances'), data: {} }) }));
vi.mock('$lib/stores/auth', () => {
	const auth = writable({ token: 'token-a', projectId: 'project-a', canWrite: true });
	return { auth, canWrite: derived(auth, ($auth) => $auth.canWrite) };
});
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/api/mutations', () => ({ apiMut: (_label: string, dispatch: () => Promise<unknown>) => dispatch() }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('$lib/utils/swr.svelte', () => ({ createSwr: () => ({ swrGet: () => null, swrSet: vi.fn() }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 10, intervalOptions: [10, 15, 30, 60], setBoost: vi.fn() }),
}));

import { t } from '$lib/i18n/ns/instance';
import Page from '../+page.svelte';

const instance = (id: string, waygate_managed?: boolean): Instance => ({
	id, name: id, status: 'SHUTOFF', image_name: 'Ubuntu', flavor_name: 'small', ip_addresses: [],
	created_at: null, union_libraries: [], union_strategy: null, project_id: 'project-a',
	...(waygate_managed === undefined ? {} : { waygate_managed }),
});
let rows: Instance[];

async function mount() {
	render(Page);
	await screen.findByRole('button', { name: 'gateway' });
}
async function select(id: string) {
	await fireEvent.click(screen.getByRole('checkbox', { name: t('row.select', { name: id }) }).closest('label')!);
}
function bulk() {
	return within(screen.getByRole('region', { name: t('list.bulkActions') }));
}
async function openMenu(name: string) {
	await fireEvent.click(screen.getByRole('button', { name: t('rowActions.instanceActions', { name }) }));
}

beforeEach(() => {
	rows = [instance('gateway', true), instance('vm-b', false), instance('legacy')];
	mocks.get.mockReset().mockImplementation((path: string) => Promise.resolve(
		path.endsWith('metrics-summary-batch') ? { monitoring_available: false, instances: {} } : path.endsWith('/volumes') ? [] : rows,
	));
	mocks.post.mockReset().mockResolvedValue({ results: [{ id: 'gateway', ok: true }, { id: 'vm-b', ok: true }] });
	mocks.delete.mockReset().mockResolvedValue(undefined);
	mocks.confirm.mockReset().mockResolvedValue(true);
});

describe('Waygate-managed instances in the project list', () => {
	it('badges gateways and offers only start among stopped-row actions', async () => {
		await mount();
		expect(screen.getAllByTestId('waygate-managed-badge')).toHaveLength(1);
		expect(screen.getByTestId('waygate-managed-badge').textContent).toBe(t('waygate.badge'));
		await openMenu('gateway');
		expect(screen.getByRole('button', { name: t('list.start') })).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('rowActions.shelve') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('rowActions.delete') })).toBeNull();
		expect(screen.getByTestId('waygate-row-note').textContent).toBe(t('waygate.managedNote'));
	});

	it('keeps shelve and delete for ordinary rows, including payloads without the marker', async () => {
		await mount();
		for (const name of ['vm-b', 'legacy']) {
			await openMenu(name);
			expect(screen.getByRole('button', { name: t('rowActions.shelve') })).toBeTruthy();
			expect(screen.getByRole('button', { name: t('rowActions.delete') })).toBeTruthy();
			await fireEvent.click(screen.getByRole('button', { name: t('rowActions.instanceActions', { name }) }));
		}
	});

	it('blocks bulk deletion with a note when the selection contains a gateway but keeps bulk start', async () => {
		await mount();
		await select('vm-b');
		expect(bulk().getByRole('button', { name: t('list.delete') })).toBeTruthy();
		expect(screen.queryByTestId('waygate-bulk-note')).toBeNull();
		await select('gateway');
		await waitFor(() => expect(bulk().queryByRole('button', { name: t('list.delete') })).toBeNull());
		expect(screen.getByTestId('waygate-bulk-note').textContent).toBe(t('list.waygateBulkDeleteBlocked'));
		expect(screen.getByRole('link', { name: t('waygate.openLink') }).getAttribute('href')).toBe('/dashboard/network/waygate');
		await fireEvent.click(bulk().getByRole('button', { name: t('list.start') }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/instances/bulk-action',
			{ action: 'start', instance_ids: ['vm-b', 'gateway'] }, 'token-a', 'project-a'));
		expect(mocks.post).not.toHaveBeenCalledWith('/api/v1/instances/bulk-action', expect.objectContaining({ action: 'delete' }), expect.anything(), expect.anything());
	});
});
