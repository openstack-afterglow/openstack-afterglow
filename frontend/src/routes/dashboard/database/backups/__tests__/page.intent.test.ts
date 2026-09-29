import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({
	mockGet: vi.fn(),
	mockPrefetch: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mockGet,
		prefetch: mockPrefetch,
		post: vi.fn(),
		delete: vi.fn(),
	},
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 15,
		intervalOptions: [10, 15, 30, 60],
	}),
}));

import Page from '../+page.svelte';

describe('database backup restore intent', () => {
	beforeEach(() => {
		mockGet.mockReset();
		mockPrefetch.mockReset().mockResolvedValue(undefined);
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/database-instances/backups') {
				return Promise.resolve([{
					id: 'backup-1',
					name: 'daily-backup',
					status: 'COMPLETED',
					size: 10,
					created_at: '2026-01-01T00:00:00Z',
				}]);
			}
			if (path === '/api/v1/database-instances') return Promise.resolve([]);
			if (path === '/api/v1/database-instances/flavors') return Promise.resolve([]);
			throw new Error(`unexpected GET ${path}`);
		});
	});

	it('does not load restore flavors initially, then prefetches on intent and loads on click', async () => {
		render(Page);
		const restore = await screen.findByRole('button', { name: '복원' });
		expect(mockGet).toHaveBeenCalledTimes(2);
		expect(mockGet.mock.calls.some((call) => call[0].endsWith('/flavors'))).toBe(false);

		await fireEvent.pointerEnter(restore);
		expect(mockPrefetch).toHaveBeenCalledWith(
			'/api/v1/database-instances/flavors',
			'token',
			'project',
		);

		await fireEvent.click(restore);
		await vi.waitFor(() => expect(mockGet.mock.calls.some((call) => call[0].endsWith('/flavors'))).toBe(true));
	});
});
