import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { t as tc } from '$lib/i18n/ns/common';
import { t as ti } from '$lib/i18n/ns/admin-identity';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({
	mockGet: vi.fn(),
	mockPrefetch: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet, prefetch: mockPrefetch }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
	authReady: writable(true),
	projectSwitching: writable(false),
	logoutInProgress: writable(false),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 60,
		intervalOptions: [30, 60],
	}),
}));

import Page from '$lib/components/admin/projects/AdminProjectsPage.svelte';
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';

type InventoryPage = {
	items: Array<{ id: string; name: string; description: string; enabled: boolean; domain_id: string }>;
	next_marker: string | null;
	count: number;
	total: number;
	domain_ids: string[];
};

describe('admin project inventory', () => {
	beforeEach(() => {
		auth.update(state => ({ ...state, token: 'token', projectId: 'project', userId: 'actor', sessionId: 'session' }));
		authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
		mockGet.mockReset();
		mockPrefetch.mockReset();
		vi.useFakeTimers();
		vi.stubGlobal('matchMedia', vi.fn(() => ({
			matches: false,
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
		})));
		mockGet
			.mockResolvedValueOnce({ items: [], next_marker: 'marker-2', count: 0, total: 0, domain_ids: [] })
			.mockResolvedValueOnce({ items: [], next_marker: null, count: 0, total: 0, domain_ids: [] });
		mockPrefetch.mockResolvedValue(undefined);
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('ignores a late page-size response', async () => {
		const oldRequest = Promise.withResolvers<InventoryPage>();
		const newRequest = Promise.withResolvers<InventoryPage>();
		mockGet.mockReset()
			.mockReturnValueOnce(oldRequest.promise)
			.mockReturnValueOnce(newRequest.promise);
		mockPrefetch.mockReset().mockResolvedValue(undefined);

		render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledOnce());
		await fireEvent.click(screen.getByRole('button', { name: '10' }));
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

		newRequest.resolve({
			items: [{ id: 'new-project', name: 'Newest project', description: '', enabled: true, domain_id: 'domain-a' }],
			next_marker: 'new-marker', count: 1, total: 2, domain_ids: [],
		});
		expect(await screen.findByText('Newest project')).toBeTruthy();
		oldRequest.resolve({
			items: [{ id: 'old-project', name: 'Stale project', description: '', enabled: true, domain_id: 'domain-a' }],
			next_marker: 'old-marker', count: 1, total: 2, domain_ids: [],
		});
		await vi.advanceTimersByTimeAsync(200);

		expect(screen.queryByText('Stale project')).toBeNull();
	});

	it('keeps regex local while a native name header condition resets the marker and fences the older page', async () => {
		const oldPage = Promise.withResolvers<InventoryPage>();
		const searchPage = Promise.withResolvers<InventoryPage>();
		mockGet.mockReset()
			.mockResolvedValueOnce({ items: [{ id: 'first', name: 'First page', description: '', enabled: true, domain_id: 'domain-a' }], next_marker: 'first', count: 1, total: 21, domain_ids: [] })
			.mockReturnValueOnce(oldPage.promise)
			.mockReturnValueOnce(searchPage.promise);
		render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		await fireEvent.input(screen.getByRole('searchbox', { name: tc('table.search') }), { target: { value: '^Search (match|other)$' } });
		expect(mockGet).toHaveBeenCalledTimes(2);
		await fireEvent.click(screen.getByRole('button', { name: tc('table.filterColumn', { column: ti('form.name') }) }));
		await fireEvent.input(screen.getByRole('textbox', { name: tc('table.filterValue') }), { target: { value: 'match' } });
		await fireEvent.click(screen.getByRole('button', { name: tc('table.apply') }));
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		await vi.advanceTimersByTimeAsync(0);
		expect(mockGet.mock.calls[2][0]).toContain('search=match');
		expect(mockGet.mock.calls[2][0]).not.toContain('marker=');
		searchPage.resolve({ items: [{ id: 'match', name: 'Search match', description: '', enabled: true, domain_id: 'domain-a' }], next_marker: null, count: 1, total: 1, domain_ids: [] });
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByRole('link', { name: 'Search match' })).toBeTruthy();
		oldPage.resolve({ items: [{ id: 'late', name: 'Unfiltered late page', description: '', enabled: true, domain_id: 'domain-a' }], next_marker: 'late', count: 1, total: 21, domain_ids: [] });
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.queryByText('Unfiltered late page')).toBeNull();
		expect((screen.getByRole('button', { name: '← 이전' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: '다음 →' }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('includes domain selection in pagination and preserves it in detail links', async () => {
		mockGet.mockReset().mockResolvedValue({ items: [{ id: 'p1', name: 'Scoped project', description: '', enabled: true, domain_id: 'domain-a' }], next_marker: 'p1', count: 1, total: 21 });
		render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
		await vi.advanceTimersByTimeAsync(0);
		expect(mockGet.mock.calls[0][0]).toContain('domain_id=domain-a');
		expect(screen.getByRole('link', { name: 'Scoped project' }).getAttribute('href')).toBe('/admin/projects/p1?domain_id=domain-a');
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		expect(mockGet.mock.calls[1][0]).toContain('domain_id=domain-a');
		expect(mockGet.mock.calls[1][0]).toContain('marker=p1');
	});

	it('rejects foreign list rows without publishing or prefetching that inventory', async () => {
		mockGet.mockReset().mockResolvedValue({ items: [{ id: 'foreign', name: 'Foreign project', description: '', enabled: true, domain_id: 'domain-b' }], next_marker: 'foreign', count: 1, total: 1 });
		render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.queryByText('Foreign project')).toBeNull();
		expect(screen.getByRole('alert')).toBeTruthy();
		expect(mockPrefetch).not.toHaveBeenCalled();
	});

	it.each([false, true])('settles a pending project read across verified bearer renewal (background=%s)', async background => {
		const pending = Promise.withResolvers<InventoryPage>();
		const page = { items: [{ id: 'retained', name: 'Retained project', description: '', enabled: true, domain_id: 'domain-a' }], next_marker: null, count: 1, total: 1, domain_ids: [] };
		mockGet.mockReset();
		if (background) mockGet.mockResolvedValueOnce(page);
		mockGet.mockReturnValueOnce(pending.promise);
		render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
		await vi.advanceTimersByTimeAsync(0);
		if (background) {
			await fireEvent.click(screen.getByRole('button', { name: tc('table.sortColumn', { column: ti('form.name'), direction: tc('table.none') }) }));
			await fireEvent.click(screen.getByRole('button', { name: tc('autoRefresh.refreshNow') }));
		}
		const search = screen.getByRole('searchbox', { name: tc('table.search') }) as HTMLInputElement;
		await fireEvent.input(search, { target: { value: '^Retained project$' } });
		auth.update(state => ({ ...state, token: 'renewed-token' }));
		pending.resolve(page);
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByRole('link', { name: 'Retained project' })).toBeTruthy();
		expect(search.value).toBe('^Retained project$');
		const refresh = screen.getByRole('button', { name: tc('autoRefresh.refreshNow') }) as HTMLButtonElement;
		expect(refresh.disabled).toBe(false);
		if (background) expect(screen.getByRole('button', { name: tc('table.sortColumn', { column: ti('form.name'), direction: tc('table.ascending') }) })).toBeTruthy();
		mockGet.mockResolvedValueOnce(page);
		await fireEvent.click(refresh);
		expect(mockGet.mock.calls.at(-1)?.[1]).toBe('renewed-token');
	});

	it('discards pending private rows after owner ABA rather than accepting equal final owner fields', async () => {
		const pending = Promise.withResolvers<InventoryPage>();
		mockGet.mockReset().mockReturnValueOnce(pending.promise);
		render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
		await vi.advanceTimersByTimeAsync(0);
		auth.update(state => ({ ...state, projectId: 'foreign-project' }));
		auth.update(state => ({ ...state, projectId: 'project' }));
		pending.resolve({ items: [{ id: 'stale-private', name: 'Stale private project', description: '', enabled: true, domain_id: 'domain-a' }], next_marker: null, count: 1, total: 1, domain_ids: [] });
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.queryByRole('link', { name: 'Stale private project' })).toBeNull();
		expect(mockPrefetch).not.toHaveBeenCalled();
	});

	it.each(['canWrite', 'roles'] as const)('keeps the administrative inventory when unrelated consumer %s metadata changes', async field => {
		auth.update(state => ({ ...state, isSystemAdmin: true, canWrite: true, roles: ['admin', 'member'] }));
		mockGet.mockReset().mockResolvedValue({ items: [{ id: 'scoped', name: 'Scoped project', description: '', enabled: true, domain_id: 'domain-a' }], next_marker: null, count: 1, total: 1, domain_ids: [] });
		render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
		await vi.advanceTimersByTimeAsync(0);
		const search = screen.getByRole('searchbox', { name: tc('table.search') }) as HTMLInputElement;
		await fireEvent.input(search, { target: { value: '^Scoped project$' } });
		auth.update(state => field === 'canWrite' ? { ...state, canWrite: undefined } : { ...state, roles: ['admin', 'reader'] });
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByRole('link', { name: 'Scoped project' })).toBeTruthy();
		expect(search.value).toBe('^Scoped project$');
		expect(mockGet).toHaveBeenCalledOnce();
	});

});
