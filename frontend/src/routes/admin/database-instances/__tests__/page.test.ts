import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
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
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 15,
		intervalOptions: [10, 15, 30, 60],
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
		expect(mockGet).toHaveBeenCalledWith(
			'/api/v1/database-instances?all_projects=true',
			'admin-token',
			'admin-project',
		);
		expect(document.querySelector('iframe')).toBeNull();
		expect(screen.queryByText(/mysqld_exporter/i)).toBeNull();
	});

	it('distinguishes a Trove management failure from an empty inventory', async () => {
		mockGet.mockRejectedValue(new Error('management unavailable'));

		render(Page);

		const alert = await screen.findByRole('alert');
		expect(alert.textContent).toContain('Trove DB 인스턴스를 불러오지 못했습니다');
		expect(alert.textContent).toContain('Trove DB 인스턴스 목록 조회에 실패했습니다.');
		expect(screen.queryByText('DB 인스턴스가 없습니다')).toBeNull();
	});
});
