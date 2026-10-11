import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable, type Writable } from 'svelte/store';
import type { AdminNetwork } from '$lib/types/networks';
import type { TsPoint } from '$lib/types/common';
import NetworkTimeseriesProbe from './_NetworkTimeseriesProbe.svelte';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), goto: vi.fn(),
	refresh: undefined as undefined | (() => void),
}));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', userId: 'user', projectId: 'project' }) }));
vi.mock('$app/stores', () => ({ page: writable({ url: new URL('https://example.test/admin/networks'), params: {} }) }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$lib/mockup/transport', () => ({ getActiveMockupProfile: () => null }));
vi.mock('$lib/mockup/state', () => ({ getMockupRevision: () => 0, onMockupRevisionChange: () => () => {} }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (refresh: () => void) => {
		mocks.refresh = refresh;
		return { active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] };
	},
}));
vi.mock('$lib/components/admin/networks/AdminNetworkTimeseries.svelte', () => ({ default: NetworkTimeseriesProbe }));
vi.mock('$lib/i18n/ns/admin-network', () => ({
	t: (key: string, params?: Record<string, unknown>) => {
		const labels: Record<string, string> = {
			'adminNetworkTable.external': '외부', 'adminNetworkTable.shared': '공유', 'adminNetworkTable.internal': '내부',
		};
		if (key === 'networksPage.results') return `${params?.shown} of ${params?.total} networks`;
		return labels[key] ?? key;
	},
}));
vi.mock('$lib/i18n/ns/shared', () => ({ t: (key: string) => key }));

import { auth } from '$lib/stores/auth';
import { page } from '$app/stores';
import { projectNames } from '$lib/stores/projectNames';
import Page from '../+page.svelte';

const route = page as unknown as Writable<{ url: URL; params: Record<string, string> }>;
const ownerId = 'abcd1234-0000-1111-2222-333344445555';
function network(id: string, name: string, external: boolean, shared: boolean): AdminNetwork {
	return { id, name, is_external: external, is_shared: shared, project_id: ownerId, status: 'ACTIVE', subnets: [] };
}
const both = network('11111111-2222-3333-4444-555566667777', 'Production Public', true, true);
const external = network('external-id', 'Provider Only', true, false);
const shared = network('shared-id', 'Tenant Shared', false, true);
const internal = network('internal-id', 'Private Internal', false, false);
const inventory = [both, external, shared, internal];
const history = [{ ts: 1, total: 4 }];

function deferred<T>() { return Promise.withResolvers<T>(); }
function searchInput() { return screen.getByRole('searchbox'); }
function resetButton() { return screen.getByRole('button', { name: 'networksPage.filters.reset' }); }
function rows() { return within(screen.getByRole('table')); }
async function search(value: string) { await fireEvent.input(searchInput(), { target: { value } }); }
async function select(label: string, value: string) { await fireEvent.change(screen.getByLabelText(label), { target: { value } }); }
function installInventory(rows: AdminNetwork[] = inventory) {
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/admin/projects/names') return [{ id: ownerId, name: 'Platform Operations' }];
		if (path.includes('/timeseries/')) return history;
		return rows;
	});
}
async function settle() { await tick(); await tick(); }

beforeEach(() => {
	vi.clearAllMocks();
	mocks.get.mockReset();
	projectNames.invalidate();
	auth.update((state) => ({ ...state, token: 'token', userId: 'user', projectId: 'project' }));
	route.set({ url: new URL('https://example.test/admin/networks'), params: {} });
	installInventory();
	vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('administrator network inventory', () => {
	it('intersects independent flags without classifying external/shared overlap as internal', async () => {
		render(Page);
		await screen.findByRole('button', { name: both.name });
		await select('외부', 'yes');
		expect(rows().getByRole('button', { name: both.name })).toBeTruthy();
		expect(rows().getByRole('button', { name: external.name })).toBeTruthy();
		await select('공유', 'yes');
		expect(screen.getByText('1 of 4 networks')).toBeTruthy();
		expect(rows().queryByRole('button', { name: external.name })).toBeNull();
		await select('외부', 'no');
		expect(rows().getByRole('button', { name: shared.name })).toBeTruthy();
		await fireEvent.click(resetButton());
		await select('내부', 'yes');
		expect(rows().getByRole('button', { name: internal.name })).toBeTruthy();
		expect(rows().queryByRole('button', { name: both.name })).toBeNull();
		await select('공유', 'yes');
		expect(screen.getByText('networksPage.noMatches')).toBeTruthy();
		expect(screen.getByRole('region', { name: 'networksPage.filters.label' })).toBeTruthy();
		await fireEvent.click(resetButton());
		expect(screen.getByText('4 of 4 networks')).toBeTruthy();
	});

	it('uses normalized case-insensitive AND terms across full identities, owner names and localized flags', async () => {
		render(Page);
		await screen.findAllByText('Platform Operations');
		await search(`  ＰＲＯＤＵＣＴＩＯＮ   operations ${both.id.slice(-12)} ${ownerId.slice(-12)} 외부 공유 `);
		expect(rows().getByRole('button', { name: both.name })).toBeTruthy();
		expect(screen.getByText('1 of 4 networks')).toBeTruthy();
		expect(rows().getByText(ownerId)).toBeTruthy();
		await search('private 내부');
		expect(rows().getByRole('button', { name: internal.name })).toBeTruthy();
		await search('production nonexistent');
		expect(screen.getByText('networksPage.noMatches')).toBeTruthy();
		expect(searchInput()).toHaveProperty('value', 'production nonexistent');
		await fireEvent.click(resetButton());
		expect(rows().getAllByText(ownerId)).toHaveLength(4);
	});

	it('retains controls on successful empty inventory and distinguishes first-load failure from zero', async () => {
		installInventory([]);
		const view = render(Page);
		await screen.findByText('networksPage.empty');
		expect(screen.getByText('0 of 0 networks')).toBeTruthy();
		await search('something');
		expect(screen.getByText('networksPage.noMatches')).toBeTruthy();
		await fireEvent.click(resetButton());
		view.unmount();
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/all-networks') throw new Error('offline');
			return [];
		});
		render(Page);
		await screen.findByText('networksPage.error.loadFailed');
		expect(screen.getByText('networksPage.resultsUnavailable')).toBeTruthy();
		expect(screen.queryByText('0 of 0 networks')).toBeNull();
		expect(screen.queryByText('networksPage.empty')).toBeNull();
		expect(searchInput()).toBeTruthy();
	});

	it('keeps full inventory, filter state and history on failed background refresh and only looks up owners once', async () => {
		render(Page);
		await screen.findByRole('button', { name: both.name });
		await select('외부', 'yes');
		await search('production');
		const refresh = deferred<AdminNetwork[]>();
		mocks.get.mockImplementation((path: string) => path.includes('/timeseries/') ? Promise.reject(new Error('history down')) : refresh.promise);
		mocks.refresh!();
		await settle();
		expect(rows().getByRole('button', { name: both.name })).toBeTruthy();
		expect(searchInput()).toHaveProperty('value', 'production');
		refresh.reject(new Error('inventory down'));
		await screen.findByText('networksPage.error.loadFailed');
		expect(screen.getByText('1 of 4 networks')).toBeTruthy();
		expect(screen.getByLabelText('외부')).toHaveProperty('value', 'yes');
		expect(within(screen.getByLabelText('Network history')).getByText(JSON.stringify(history))).toBeTruthy();
		expect(screen.getByText('networksPage.error.timeseriesFailed')).toBeTruthy();
		await fireEvent.click(resetButton());
		expect(rows().getByRole('button', { name: internal.name })).toBeTruthy();
		expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/projects/names')).toHaveLength(1);
	});

	it('warns on owner directory failure while preserving and searching full owner IDs', async () => {
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/projects/names') throw new Error('directory down');
			return path.includes('/timeseries/') ? history : inventory;
		});
		render(Page);
		await screen.findByText('networksPage.ownerWarningBody');
		expect(rows().getAllByText(ownerId)).toHaveLength(4);
		await search(ownerId.toUpperCase());
		expect(screen.getByText('4 of 4 networks')).toBeTruthy();
		expect(screen.queryByText('Platform Operations')).toBeNull();
	});

	it.each(['token', 'userId', 'projectId', 'route'] as const)('fences old inventory, owner and history responses after %s changes', async (field) => {
		const oldInventory = deferred<AdminNetwork[]>();
		const oldNames = deferred<{ id: string; name: string }[]>();
		const oldHistory = deferred<TsPoint[]>();
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/projects/names') return oldNames.promise;
			return path.includes('/timeseries/') ? oldHistory.promise : oldInventory.promise;
		});
		render(Page);
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(3));
		mocks.get.mockImplementation(async (path: string) => {
			if (path === '/api/v1/admin/projects/names') return [{ id: ownerId, name: 'Current Owner' }];
			return path.includes('/timeseries/') ? [{ ts: 2, total: 9 }] : [internal];
		});
		if (field === 'route') route.set({ url: new URL('https://example.test/admin/networks/other'), params: {} });
		else auth.update((state) => ({ ...state, [field]: `new-${field}` }));
		if (field !== 'route') await screen.findByRole('button', { name: internal.name });
		else await settle();
		oldInventory.resolve([both]);
		oldNames.resolve([{ id: ownerId, name: 'Old Owner' }]);
		oldHistory.resolve([{ ts: 1, total: 123456 }]);
		await settle();
		expect(rows().queryByRole('button', { name: both.name })).toBeNull();
		expect(screen.queryByText('Old Owner')).toBeNull();
		expect(screen.queryByText(JSON.stringify([{ ts: 1, total: 123456 }]))).toBeNull();
		if (field !== 'route') {
			expect(rows().getByText('Current Owner')).toBeTruthy();
			expect(within(screen.getByLabelText('Network history')).getByText(JSON.stringify([{ ts: 2, total: 9 }]))).toBeTruthy();
		}
	});

	it('keeps newest inventory generation and history range when earlier same-scope responses arrive late', async () => {
		render(Page);
		await screen.findByRole('button', { name: both.name });
		const oldInventory = deferred<AdminNetwork[]>();
		const oldHistory = deferred<TsPoint[]>();
		mocks.get.mockImplementation((path: string) => path.includes('/timeseries/') ? oldHistory.promise : oldInventory.promise);
		mocks.refresh!();
		await settle();
		mocks.get.mockImplementation(async (path: string) => path.includes('/timeseries/') ? [{ ts: 3, total: 7 }] : [internal]);
		mocks.refresh!();
		await fireEvent.click(screen.getByRole('button', { name: 'Thirty days' }));
		await settle();
		oldInventory.resolve([external]);
		oldHistory.resolve([{ ts: 1, total: 111111 }]);
		await settle();
		expect(rows().getByRole('button', { name: internal.name })).toBeTruthy();
		expect(rows().queryByRole('button', { name: external.name })).toBeNull();
		expect(screen.getByText('30d')).toBeTruthy();
		expect(screen.queryByText(JSON.stringify([{ ts: 1, total: 111111 }]))).toBeNull();
	});

	it('preserves row navigation and edit mutations, then refreshes the unfiltered inventory', async () => {
		render(Page);
		await screen.findByRole('button', { name: both.name });
		await fireEvent.click(rows().getByRole('button', { name: both.name }));
		expect(mocks.goto).toHaveBeenCalledWith(`/admin/networks/${both.id}`);
		await search('production');
		const row = rows().getByRole('button', { name: both.name }).closest('tr')!;
		await fireEvent.click(within(row).getByRole('button', { name: 'adminNetworkTable.edit' }));
		const dialog = within(screen.getByRole('dialog'));
		await fireEvent.input(dialog.getByLabelText('adminNetworkEditModal.name'), { target: { value: 'Production Renamed' } });
		mocks.put.mockResolvedValue({});
		installInventory([{ ...both, name: 'Production Renamed' }, internal]);
		await fireEvent.click(dialog.getByRole('button', { name: 'adminNetworkEditModal.save' }));
		await screen.findByRole('button', { name: 'Production Renamed' });
		expect(mocks.put).toHaveBeenCalledWith(`/api/v1/admin/networks/${both.id}`, { name: 'Production Renamed', is_shared: true }, 'token', 'project');
		expect(screen.getByText('1 of 2 networks')).toBeTruthy();
		await fireEvent.click(resetButton());
		expect(rows().getByRole('button', { name: internal.name })).toBeTruthy();
	});

	it('ignores late failures after leaving and returning to the same route scope', async () => {
		const oldInventory = deferred<AdminNetwork[]>();
		const oldNames = deferred<{ id: string; name: string }[]>();
		const oldHistory = deferred<TsPoint[]>();
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/projects/names') return oldNames.promise;
			return path.includes('/timeseries/') ? oldHistory.promise : oldInventory.promise;
		});
		render(Page);
		await vi.waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(3));
		route.set({ url: new URL('https://example.test/admin/projects'), params: {} });
		await settle();
		installInventory([internal]);
		route.set({ url: new URL('https://example.test/admin/networks'), params: {} });
		await screen.findByRole('button', { name: internal.name });
		oldInventory.reject(new Error('old list failure'));
		oldHistory.reject(new Error('old history failure'));
		oldNames.reject(new Error('old directory failure'));
		await settle();
		await screen.findByText('networksPage.ownerWarningBody');
		expect(rows().getByRole('button', { name: internal.name })).toBeTruthy();
		expect(screen.queryByText('networksPage.error.loadFailed')).toBeNull();
		expect(screen.queryByText('networksPage.error.timeseriesFailed')).toBeNull();
	});

	it('does not let an old edit response close or overwrite a newly scoped edit dialog', async () => {
		render(Page);
		await screen.findByRole('button', { name: both.name });
		const row = rows().getByRole('button', { name: both.name }).closest('tr')!;
		await fireEvent.click(within(row).getByRole('button', { name: 'adminNetworkTable.edit' }));
		const pending = deferred<object>();
		mocks.put.mockReturnValueOnce(pending.promise);
		await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'adminNetworkEditModal.save' }));
		installInventory([internal]);
		auth.update((state) => ({ ...state, projectId: 'new-project' }));
		await screen.findByRole('button', { name: internal.name });
		const newRow = rows().getByRole('button', { name: internal.name }).closest('tr')!;
		await fireEvent.click(within(newRow).getByRole('button', { name: 'adminNetworkTable.edit' }));
		pending.resolve({});
		await settle();
		expect(within(screen.getByRole('dialog')).getByLabelText('adminNetworkEditModal.name')).toHaveProperty('value', internal.name);
		expect(screen.queryByText('networksPage.error.scopeChanged')).toBeNull();
		expect(mocks.get.mock.calls.filter(([path, , project]) => path === '/api/v1/admin/all-networks' && project === 'new-project')).toHaveLength(1);
	});
});
