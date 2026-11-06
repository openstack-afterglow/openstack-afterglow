import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { Flavor, PagedResponse } from '$lib/types/flavor';
import { t as commonT } from '$lib/i18n/ns/common';
import { t as computeT } from '$lib/i18n/ns/admin-compute';

const mocks = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn(), names: vi.fn(), confirm: vi.fn(), refresh: undefined as (() => Promise<void>) | undefined }));
// The mock factory is hoisted before static imports, so resolve the real error class inside it.
vi.mock('$lib/api/client', async () => ({ api: { get: mocks.get, delete: mocks.delete }, ApiError: (await import('$lib/api/errors')).ApiError }));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { load: mocks.names } }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: (callback: () => Promise<void>) => { mocks.refresh = callback; return { active: false, intervalSeconds: 60, intervalOptions: [30, 60] }; } }));
vi.mock('$lib/components/admin/flavors/FlavorAutomationPanel.svelte', () => ({ default: () => ({}) }));
vi.mock('$lib/components/admin/flavors/FlavorCreateModal.svelte', () => ({ default: () => ({}) }));
vi.mock('$lib/components/admin/flavors/GpuDeviceCatalogModal.svelte', () => ({ default: () => ({}) }));
vi.mock('$lib/components/admin/flavors/FlavorManagePanel.svelte', () => ({ default: () => ({}) }));
import Page from './+page.svelte';

const original = get(auth);
const catalogPath = '/api/v1/admin/flavors?limit=999';
function catalog(name: string): PagedResponse<Flavor> {
	return { items: [{ id: `fixture-${name.toLowerCase().replaceAll(' ', '-')}`, name, vcpus: 2, ram: 4096, disk: 20, is_public: true, description: null, extra_specs: {}, is_gpu: false, gpu_count: 0 }], count: 1, next_marker: null };
}
async function flush() { await tick(); await Promise.resolve(); await tick(); }
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	auth.set({ ...original, token: 'token-a', userId: 'admin', sessionId: 'session-a', projectId: 'project-a', isSystemAdmin: true });
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	mocks.get.mockResolvedValue(catalog('Current flavor')); mocks.names.mockResolvedValue(new Map());
	vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query.includes('min-width'), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); auth.set(original); authReady.set(false); logoutInProgress.set(false); projectSwitching.set(false); initLocale('ko'); vi.unstubAllGlobals(); });

describe('administrator flavor catalog ownership', () => {
	it('waits for restored authentication and loads the verified current scope', async () => {
		authReady.set(false); auth.update(state => ({ ...state, token: null }));
		render(Page); await flush();
		expect(mocks.get).not.toHaveBeenCalled(); expect(mocks.names).not.toHaveBeenCalled();
		auth.update(state => ({ ...state, token: 'ready-token', projectId: 'ready-project' })); authReady.set(true);
		expect(await screen.findByText('Current flavor')).toBeTruthy();
		expect(mocks.get).toHaveBeenCalledWith(catalogPath, 'ready-token', 'ready-project', { refresh: false });
		expect(mocks.names).toHaveBeenCalledWith('ready-token', 'ready-project');
	});
	it('discards same-tick scope ABA responses and waits for renewed root readiness', async () => {
		const old = Promise.withResolvers<PagedResponse<Flavor>>(); const current = Promise.withResolvers<PagedResponse<Flavor>>();
		mocks.get.mockReturnValue(old.promise); render(Page);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		const prior = get(auth); mocks.get.mockReturnValue(current.promise);
		auth.set({ ...prior, projectId: 'project-b' }); auth.set(prior);
		await flush(); old.resolve(catalog('STALE flavor')); await flush();
		expect(screen.queryByText('STALE flavor')).toBeNull();
		authReady.set(true);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		current.resolve(catalog('Fresh flavor'));
		expect(await screen.findByText('Fresh flavor')).toBeTruthy();
	});
	it('accepts only the newest refresh in the same scope', async () => {
		render(Page); await screen.findByText('Current flavor');
		const old = Promise.withResolvers<PagedResponse<Flavor>>(); mocks.get.mockReturnValue(old.promise); void mocks.refresh?.();
		const current = Promise.withResolvers<PagedResponse<Flavor>>(); mocks.get.mockReturnValue(current.promise); void mocks.refresh?.();
		current.resolve(catalog('Newest flavor')); await screen.findByText('Newest flavor');
		old.resolve(catalog('STALE refresh')); await flush();
		expect(screen.queryByText('STALE refresh')).toBeNull(); expect(screen.getByText('Newest flavor')).toBeTruthy();
	});
	it('preserves regex, descending sort and local page when the refreshed array is replaced', async () => {
		const items = Array.from({ length: 21 }, (_, index) => ({
			...catalog('base').items[0], id: `flavor-${index}`, name: `Flavor ${String(index).padStart(2, '0')}`,
		}));
		mocks.get.mockResolvedValue({ items, count: items.length, next_marker: null });
		render(Page); await screen.findByText('Flavor 00');
		const search = screen.getByRole('searchbox') as HTMLInputElement;
		await fireEvent.input(search, { target: { value: '^Flavor ' } });
		const label = computeT('flavors.fields.name');
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: label, direction: commonT('table.none') }) }));
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: label, direction: commonT('table.ascending') }) }));
		await fireEvent.click(screen.getByRole('button', { name: commonT('pagination.next') }));
		await screen.findByText('Flavor 00');
		expect(screen.queryByText('Flavor 20')).toBeNull();
		mocks.get.mockResolvedValue({ items: items.map(row => ({ ...row, description: 'refreshed' })), count: items.length, next_marker: null });
		await mocks.refresh?.(); await flush();
		expect(search.value).toBe('^Flavor ');
		expect(screen.getByText('Flavor 00')).toBeTruthy();
		expect(screen.queryByText('Flavor 20')).toBeNull();
		expect(screen.getByRole('button', { name: commonT('table.sortColumn', { column: label, direction: commonT('table.descending') }) })).toBeTruthy();
	});
	it.each(['logout', 'unverified', 'switching', 'revoked'] as const)('clears observed inventory and rejects late responses after %s', async transition => {
		render(Page); await screen.findByText('Current flavor');
		const pending = Promise.withResolvers<PagedResponse<Flavor>>(); mocks.get.mockReturnValue(pending.promise); void mocks.refresh?.();
		if (transition === 'logout') logoutInProgress.set(true);
		else if (transition === 'unverified') authReady.set(false);
		else if (transition === 'switching') projectSwitching.set(true);
		else auth.update(state => ({ ...state, isSystemAdmin: false }));
		await flush(); pending.resolve(catalog('STALE flavor')); await flush();
		expect(screen.queryByText('Current flavor')).toBeNull(); expect(screen.queryByText('STALE flavor')).toBeNull();
	});
	it('does not delete after authority changes during confirmation', async () => {
		const confirmation = Promise.withResolvers<boolean>(); mocks.confirm.mockReturnValue(confirmation.promise);
		render(Page); await screen.findByText('Current flavor');
		await fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
		const prior = get(auth); auth.set({ ...prior, sessionId: 'session-b' }); auth.set(prior);
		confirmation.resolve(true); await flush();
		expect(mocks.delete).not.toHaveBeenCalled();
	});
	it('ignores a response after unmount', async () => {
		const pending = Promise.withResolvers<PagedResponse<Flavor>>(); mocks.get.mockReturnValue(pending.promise);
		const view = render(Page); await waitFor(() => expect(mocks.get).toHaveBeenCalled()); view.unmount();
		pending.resolve(catalog('Unmounted flavor')); await flush();
		expect(screen.queryByText('Unmounted flavor')).toBeNull();
	});
});
