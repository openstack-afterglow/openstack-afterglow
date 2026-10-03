import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({
	mockGet: vi.fn(),
	mockPrefetch: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet, prefetch: mockPrefetch } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 60,
		intervalOptions: [30, 60],
	}),
}));

import Page from '../+page.svelte';

type InventoryPage = {
	items: Array<{ id: string; name: string; description: string; enabled: boolean }>;
	next_marker: string | null;
	count: number;
	total: number;
	domain_ids: string[];
};

describe('admin project inventory', () => {
	beforeEach(() => {
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

		render(Page);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledOnce());
		await fireEvent.click(screen.getByRole('button', { name: '10' }));
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));

		newRequest.resolve({
			items: [{ id: 'new-project', name: 'Newest project', description: '', enabled: true }],
			next_marker: 'new-marker', count: 1, total: 2, domain_ids: [],
		});
		expect(await screen.findByText('Newest project')).toBeTruthy();
		oldRequest.resolve({
			items: [{ id: 'old-project', name: 'Stale project', description: '', enabled: true }],
			next_marker: 'old-marker', count: 1, total: 2, domain_ids: [],
		});
		await vi.advanceTimersByTimeAsync(200);

		expect(screen.queryByText('Stale project')).toBeNull();
	});

	it('resets the page on search and discards an older unfiltered page response', async () => {
		const oldPage = Promise.withResolvers<InventoryPage>();
		const searchPage = Promise.withResolvers<InventoryPage>();
		mockGet.mockReset()
			.mockResolvedValueOnce({ items: [{ id: 'first', name: 'First page', description: '', enabled: true }], next_marker: 'first', count: 1, total: 21, domain_ids: [] })
			.mockReturnValueOnce(oldPage.promise)
			.mockReturnValueOnce(searchPage.promise);
		render(Page);
		await vi.advanceTimersByTimeAsync(0);
		await fireEvent.click(screen.getByRole('button', { name: '다음 →' }));
		await fireEvent.input(screen.getByRole('searchbox', { name: '프로젝트 검색' }), { target: { value: 'match' } });
		await vi.advanceTimersByTimeAsync(250);
		searchPage.resolve({ items: [{ id: 'match', name: 'Search match', description: '', enabled: true }], next_marker: null, count: 1, total: 1, domain_ids: [] });
		expect(await screen.findByText('Search match')).toBeTruthy();
		oldPage.resolve({ items: [{ id: 'late', name: 'Unfiltered late page', description: '', enabled: true }], next_marker: 'late', count: 1, total: 21, domain_ids: [] });
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.queryByText('Unfiltered late page')).toBeNull();
		expect((screen.getByRole('button', { name: '← 이전' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: '다음 →' }) as HTMLButtonElement).disabled).toBe(true);
	});

});
