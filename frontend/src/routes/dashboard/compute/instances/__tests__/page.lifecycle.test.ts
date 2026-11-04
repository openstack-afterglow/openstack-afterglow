import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { derived, get, writable, type Writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn(),
	refresh: undefined as undefined | (() => Promise<void>),
}));
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
	createAutoRefresh: (refresh: () => Promise<void>) => {
		mocks.refresh = refresh;
		return { active: false, intervalSeconds: 10, intervalOptions: [10, 15, 30, 60], setBoost: vi.fn() };
	},
}));

import { auth } from '$lib/stores/auth';
import { page } from '$app/stores';
import { wizardOpen } from '$lib/stores/wizard';
import { sidebarOpen } from '$lib/stores/sidebar';
import { t } from '$lib/i18n/ns/instance';
import { t as commonT } from '$lib/i18n/ns/common';
import Page from '../+page.svelte';
const mockPage = page as unknown as Writable<{ url: URL; data: { mockup?: { active: boolean; profile: string } } }>;

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
		wizardOpen.set(false);
		sidebarOpen.close();
		mockPage.set({ url: new URL('http://localhost/dashboard/compute/instances'), data: {} });
		auth.update((state) => ({ ...state, token: 'token-a', projectId: 'project-a', canWrite: true }));
		mocks.get.mockReset().mockImplementation((path: string) => Promise.resolve(
			path.endsWith('metrics-summary-batch') ? { monitoring_available: false, instances: {} } : rows,
		));
		mocks.post.mockReset().mockResolvedValue({ results: [{ id: 'vm-a', ok: true }, { id: 'vm-b', ok: true }] });
		mocks.delete.mockReset().mockResolvedValue(undefined);
		mocks.confirm.mockReset().mockResolvedValue(true);
	});
	afterEach(() => { wizardOpen.set(false); sidebarOpen.close(); });

	it.each([false, true])('opens the existing VM wizard from the instance page with tutorial=%s', async tutorial => {
		mockPage.set({
			url: new URL(`http://localhost/dashboard/compute/instances${tutorial ? '?tutorial=on' : ''}`),
			data: tutorial ? { mockup: { active: true, profile: 'on' } } : {},
		});
		await mount();
		expect(document.querySelector('[data-tour="instance-list"]')).not.toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('list.createVmAction') }));
		expect(get(wizardOpen)).toBe(true);
		expect(document.querySelector('[data-tour="instance-list"]')).toBeNull();
		expect(get(sidebarOpen)).toBe(false);
		expect(mocks.post).not.toHaveBeenCalled();
		rows = [...rows, instance('vm-created')];
		wizardOpen.set(false);
		await waitFor(() => expect(document.querySelector('[data-tour="instance-list"]')).not.toBeNull());
		expect(await screen.findByRole('button', { name: 'vm-created' })).toBeTruthy();
	});

	it('cycles column sorting across refresh without changing the source snapshot', async () => {
		rows = [
			{ ...instance('vm-a'), created_at: '2026-01-01T00:00:00Z' },
			{ ...instance('vm-c'), created_at: '2026-02-01T00:00:00Z' },
			{ ...instance('vm-b'), created_at: '2026-03-01T00:00:00Z' },
		];
		const { container } = render(Page);
		await screen.findByRole('button', { name: 'vm-a' });
		const order = () => screen.getAllByRole('button', { name: /^vm-[a-d]$/ }).map((button) => button.textContent?.trim());
		const sortName = () => screen.getByRole('button', { name: new RegExp(t('table.sortBy', { label: t('table.name') })) });
		expect(container.querySelector('#project-instance-sort')).toBeNull();
		expect(order()).toEqual(['vm-b', 'vm-c', 'vm-a']);
		await select('vm-a');
		await fireEvent.click(sortName());
		expect(order()).toEqual(['vm-a', 'vm-b', 'vm-c']);
		expect(screen.queryByRole('region', { name: t('list.bulkActions') })).toBeNull();
		await fireEvent.click(sortName());
		expect(order()).toEqual(['vm-c', 'vm-b', 'vm-a']);
		await fireEvent.click(sortName());
		expect(order()).toEqual(['vm-b', 'vm-c', 'vm-a']);
		expect(rows.map((row) => row.id)).toEqual(['vm-a', 'vm-c', 'vm-b']);
		await fireEvent.click(sortName());
		rows = [...rows, { ...instance('vm-d'), created_at: '2025-01-01T00:00:00Z' }];
		await mocks.refresh!();
		await screen.findByRole('button', { name: 'vm-d' });
		expect(order()).toEqual(['vm-a', 'vm-b', 'vm-c', 'vm-d']);
		const controls = screen.getByTestId('instance-pagination-controls');
		expect(controls.contains(screen.getByLabelText(t('list.pageSize')))).toBe(true);
		expect(controls.contains(screen.getByRole('button', { name: commonT('pagination.next') }))).toBe(true);
	});

	it('searches the complete project snapshot by name or UUID and resets display pagination for filters', async () => {
		rows = Array.from({ length: 23 }, (_, index) => ({
			...instance(`00000000-0000-4000-8000-${String(index).padStart(12, '0')}`, index % 2 ? 'ACTIVE' : 'SHUTOFF'),
			name: `vm-${String(index).padStart(2, '0')}`,
		}));
		const { container } = render(Page);
		await screen.findByRole('button', { name: 'vm-00' });
		await fireEvent.change(screen.getByLabelText(t('list.pageSize')), { target: { value: '10' } });
		expect(screen.getAllByRole('button', { name: /^vm-\d\d$/ })).toHaveLength(10);
		await fireEvent.click(screen.getByRole('checkbox', { name: t('row.select', { name: 'vm-00' }) }).closest('label')!);
		expect(bulkDelete()).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: commonT('pagination.next') }));
		expect(screen.queryByRole('button', { name: 'vm-00' })).toBeNull();
		expect(screen.queryByRole('region', { name: t('list.bulkActions') })).toBeNull();
		const search = screen.getByRole('searchbox', { name: t('list.search') });
		await fireEvent.input(search, { target: { value: rows[22].id } });
		expect(screen.getByRole('button', { name: 'vm-22' })).toBeTruthy();
		expect(screen.getByRole('button', { name: commonT('pagination.previous') }).hasAttribute('disabled')).toBe(true);
		await fireEvent.input(search, { target: { value: 'vm-0' } });
		await fireEvent.change(container.querySelector('#project-instance-status')!, { target: { value: 'ACTIVE' } });
		expect(screen.getAllByRole('button', { name: /^vm-\d\d$/ })).toHaveLength(5);
		await fireEvent.input(search, { target: { value: 'missing-resource' } });
		expect(screen.getByText(t('list.filteredEmpty'))).toBeTruthy();
		expect(screen.queryByText(t('list.emptyTitle'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('list.clearFilters') }));
		expect(screen.getAllByRole('button', { name: /^vm-\d\d$/ })).toHaveLength(10);
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('does not describe first-load query failure as an empty project', async () => {
		mocks.get.mockRejectedValue(new Error('unavailable'));
		render(Page);
		await screen.findByRole('alert');
		expect(screen.queryByText(t('list.emptyTitle'))).toBeNull();
		expect(screen.queryByText(t('list.filteredEmpty'))).toBeNull();
		expect(screen.getByRole('button', { name: t('list.retry') })).toBeTruthy();
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
