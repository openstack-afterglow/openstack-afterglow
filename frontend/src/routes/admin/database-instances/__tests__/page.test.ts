import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mockGet,
		delete: vi.fn(),
		post: vi.fn(),
	},
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'admin-token', userId: 'admin-user', projectId: 'admin-project' }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: (force?: boolean) => Promise<void>) => ({
		active: false,
		intervalSeconds: 15,
		intervalOptions: [10, 15, 30, 60],
		refresh: () => callback(true),
	}),
}));

import Page from '../+page.svelte';

beforeEach(() => {
	mockGet.mockReset();
});
afterEach(cleanup);

describe('admin database instances', () => {
	it('renders tenant-created Trove instances with their owning projects', async () => {
		mockGet.mockResolvedValue([{
			id: 'trove-instance-1',
			name: 'customer-mysql',
			status: 'ACTIVE',
			datastore: { type: 'mysql', version: '8.0' },
			flavor_id: 'db.small',
			size: 20,
			created_at: '2026-09-14T01:02:03Z',
			project_id: 'tenant-project-a',
		}]);

		render(Page);

		expect(await screen.findByRole('link', { name: 'customer-mysql' })).toBeTruthy();
		expect(screen.getByRole('cell', { name: 'tenant-project-a' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: '재시작' })).toBeNull();
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
		expect(mockGet).toHaveBeenCalledWith(
			'/api/v1/admin/database-instances',
			'admin-token',
			'admin-project',
			{ refresh: false },
		);
		expect(document.querySelector('iframe')).toBeNull();
		expect(screen.queryByText(/mysqld_exporter/i)).toBeNull();
	});

	it('distinguishes a Trove management failure from an empty inventory', async () => {
		mockGet.mockRejectedValue(new Error('management unavailable'));

		render(Page);

		await screen.findByRole('alert');
		expect(screen.queryByText('DB 인스턴스가 없습니다')).toBeNull();
	});

	it('forces native freshness when the operator explicitly refreshes', async () => {
		mockGet.mockResolvedValue([]);
		render(Page);
		await waitFor(() => expect(mockGet).toHaveBeenCalled());
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await waitFor(() => expect(mockGet).toHaveBeenLastCalledWith('/api/v1/admin/database-instances', 'admin-token', 'admin-project', { refresh: true }));
	});
});
