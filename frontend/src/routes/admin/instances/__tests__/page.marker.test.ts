import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { t as commonT } from '$lib/i18n/ns/common';
import { t } from '$lib/i18n/ns/admin-compute';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPrefetch: vi.fn() }));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet, prefetch: mockPrefetch, post: vi.fn() } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 15,
		intervalOptions: [10, 15, 30, 60],
		setBoost: vi.fn(),
	}),
}));
vi.mock('$lib/components/admin/instances/AdminInstanceTable.svelte', async () => ({
	default: (await import('./_AdminInstanceTableProbe.svelte')).default,
}));

import Page from '../+page.svelte';

describe('admin instance marker generation', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
		mockGet.mockReset();
		mockPrefetch.mockReset().mockResolvedValue(undefined);
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('keeps the latest page-size result and schedules only its marker', async () => {
		const oldRequest = Promise.withResolvers<{ items: Array<Record<string, unknown>>; next_marker: string }>();
		const newRequest = Promise.withResolvers<{ items: Array<Record<string, unknown>>; next_marker: string }>();
		const pending = [oldRequest, newRequest];
		mockGet.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/all-instances')) return pending.shift()!.promise;
			if (path === '/api/v1/admin/instances/health') return Promise.resolve({ total: 0, active: 0, error: 0, with_alerts: 0, gpu_count: 0 });
			return Promise.resolve([]);
		});

		render(Page);
		await vi.waitFor(() => expect(mockGet.mock.calls.some((call) => String(call[0]).includes('limit=20'))).toBe(true));
		await fireEvent.change(screen.getByLabelText(t('instances.page.pageSize')), { target: { value: '10' } });
		await vi.waitFor(() => expect(mockGet.mock.calls.some((call) => String(call[0]).includes('limit=10'))).toBe(true));

		newRequest.resolve({
			items: [{ id: 'new-instance', name: 'Newest instance', status: 'ACTIVE', project_id: 'project' }],
			next_marker: 'new-marker',
		});
		expect(await screen.findByText('Newest instance')).toBeTruthy();
		oldRequest.resolve({
			items: [{ id: 'old-instance', name: 'Stale instance', status: 'ACTIVE', project_id: 'project' }],
			next_marker: 'old-marker',
		});
		await vi.advanceTimersByTimeAsync(200);

		expect(screen.queryByText('Stale instance')).toBeNull();
		expect(mockPrefetch).toHaveBeenCalledOnce();
		expect(mockPrefetch.mock.calls[0][0]).toBe('/api/v1/admin/all-instances?limit=10&sort=created_desc&marker=new-marker');
	});

	it('resets the marker on sort changes and discards stale sorted pages and prefetches', async () => {
		const oldSort = Promise.withResolvers<{ items: Array<Record<string, unknown>>; next_marker: string }>();
		const latestSort = Promise.withResolvers<{ items: Array<Record<string, unknown>>; next_marker: string }>();
		mockGet.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/all-instances')) {
				const params = new URL(path, 'https://example.test').searchParams;
				if (params.get('sort') === 'name_asc') return oldSort.promise;
				if (params.get('sort') === 'name_desc') return latestSort.promise;
				return Promise.resolve({
					items: [{ id: 'vm', name: params.has('marker') ? 'Second page instance' : 'First page instance' }],
					next_marker: params.has('marker') ? 'third-page' : 'second-page',
				});
			}
			if (path.endsWith('/health')) return Promise.resolve(null);
			return Promise.resolve([]);
		});

		const { container } = render(Page);
		expect(await screen.findByText('First page instance')).toBeTruthy();
		const selector = container.querySelector<HTMLSelectElement>('#admin-instance-sort')!;
		expect(selector.value).toBe('created_desc');
		await fireEvent.click(screen.getByRole('button', { name: commonT('pagination.next') }));
		expect(await screen.findByText('Second page instance')).toBeTruthy();
		expect(screen.getByText(commonT('pagination.page', { page: 2 }))).toBeTruthy();
		await vi.advanceTimersByTimeAsync(200);
		const prefetched = mockPrefetch.mock.calls.at(-1)!;
		expect(prefetched[0]).toBe('/api/v1/admin/all-instances?limit=20&sort=created_desc&marker=third-page');
		const signal = prefetched[3].signal as AbortSignal;
		expect(signal.aborted).toBe(false);

		await fireEvent.change(selector, { target: { value: 'name_asc' } });
		expect(signal.aborted).toBe(true);
		expect(mockGet.mock.calls.at(-1)![0]).toBe('/api/v1/admin/all-instances?limit=20&sort=name_asc');
		await fireEvent.change(selector, { target: { value: 'name_desc' } });
		latestSort.resolve({ items: [{ id: 'new', name: 'Latest sorted instance' }], next_marker: 'latest-marker' });
		expect(await screen.findByText('Latest sorted instance')).toBeTruthy();
		expect(screen.getByText(commonT('pagination.page', { page: 1 }))).toBeTruthy();
		oldSort.resolve({ items: [{ id: 'stale', name: 'Stale sorted instance' }], next_marker: 'stale-marker' });
		await vi.advanceTimersByTimeAsync(200);
		expect(screen.queryByText('Stale sorted instance')).toBeNull();
		expect(mockPrefetch.mock.calls.at(-1)![0]).toBe('/api/v1/admin/all-instances?limit=20&sort=name_desc&marker=latest-marker');
		const listRequests = () => mockGet.mock.calls.filter(([path]) => String(path).startsWith('/api/v1/admin/all-instances'));
		const beforeRefresh = listRequests().length;
		await fireEvent.click(screen.getByTitle(commonT('autoRefresh.refreshNow')));
		await vi.waitFor(() => expect(listRequests()).toHaveLength(beforeRefresh + 1));
		expect(listRequests().at(-1)![0]).toBe('/api/v1/admin/all-instances?limit=20&sort=name_desc');
		expect(selector.value).toBe('name_desc');
	});
});
