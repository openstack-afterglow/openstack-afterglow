import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Cluster } from '$lib/types/cluster';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$app/stores', () => ({
	page: writable({ params: { id: 'cluster-1' }, data: {} }),
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project' }),
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 10,
		intervalOptions: [10, 15, 30, 60],
	}),
}));

import Page from '../+page.svelte';

const cluster: Cluster = {
	id: 'cluster-1',
	name: 'cluster',
	status: 'CREATE_COMPLETE',
	status_reason: null,
	cluster_template_id: 'template-1',
	master_count: 1,
	node_count: 2,
	api_address: null,
	coe_version: null,
	keypair: null,
	create_timeout: null,
	created_at: '2026-01-01T00:00:00Z',
	updated_at: null,
	stack_id: 'stack-1',
};

describe('K3s cluster detail tabs', () => {
	it('defers hidden tabs and remembers a successfully loaded empty tab', async () => {
		const resources = Promise.withResolvers<[]>();
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/clusters/cluster-1') return Promise.resolve(cluster);
			if (path.endsWith('/stack/resources')) return resources.promise;
			throw new Error(`unexpected GET ${path}`);
		});

		render(Page);
		const resourcesTab = await screen.findByRole('tab', { name: '스택 리소스' });
		expect(mockGet).toHaveBeenCalledOnce();

		await fireEvent.focus(resourcesTab);
		await fireEvent.click(resourcesTab);
		expect(mockGet).toHaveBeenCalledTimes(2);
		resources.resolve([]);
		await vi.waitFor(() => expect(screen.getByText('스택 리소스 정보를 불러올 수 없습니다')).toBeTruthy());

		await fireEvent.blur(resourcesTab);
		await fireEvent.focus(resourcesTab);
		expect(mockGet).toHaveBeenCalledTimes(2);
	});
});
