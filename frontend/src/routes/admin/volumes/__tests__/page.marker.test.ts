import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPrefetch: vi.fn() }));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet, prefetch: mockPrefetch } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/stores/projectNames', async () => {
	const names = writable(new Map<string, string>());
	return { projectNames: Object.assign(names, { load: vi.fn().mockResolvedValue(new Map<string, string>()) }) };
});
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }),
}));
vi.mock('$lib/components/admin/volumes/AdminVolumeTable.svelte', async () => ({
	default: (await import('./_AdminVolumeTableProbe.svelte')).default,
}));

import Page from '../+page.svelte';

describe('admin volume marker generation', () => {
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
			if (path.startsWith('/api/v1/admin/all-volumes')) return pending.shift()!.promise;
			if (path.startsWith('/api/v1/admin/volumes/status-summary')) return Promise.resolve({ total: 0, total_gb: 0, attached_count: 0, attached_gb: 0, available_count: 0, available_gb: 0, statuses: [], domains: [], filtered_total: 0, filtered_gb: 0 });
			return Promise.resolve([]);
		});

		render(Page);
		await vi.waitFor(() => expect(mockGet.mock.calls.some((call) => String(call[0]).includes('limit=20'))).toBe(true));
		await fireEvent.click(screen.getByRole('button', { name: '10' }));
		await vi.waitFor(() => expect(mockGet.mock.calls.some((call) => String(call[0]).includes('limit=10'))).toBe(true));

		newRequest.resolve({
			items: [{ id: 'new-volume', name: 'Newest volume', status: 'available', project_id: 'project' }],
			next_marker: 'new-marker',
		});
		expect(await screen.findByText('Newest volume')).toBeTruthy();
		oldRequest.resolve({
			items: [{ id: 'old-volume', name: 'Stale volume', status: 'available', project_id: 'project' }],
			next_marker: 'old-marker',
		});
		await vi.advanceTimersByTimeAsync(200);

		expect(screen.queryByText('Stale volume')).toBeNull();
		expect(mockPrefetch).toHaveBeenCalledOnce();
		expect(mockPrefetch.mock.calls[0][0]).toBe('/api/v1/admin/all-volumes?limit=10&marker=new-marker');
	});
});
