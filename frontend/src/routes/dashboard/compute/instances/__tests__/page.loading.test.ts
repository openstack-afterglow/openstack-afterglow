import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a' }),
	canWrite: writable(true),
}));
vi.mock('$lib/utils/swr.svelte', () => ({
	createSwr: () => ({ swrGet: () => null, swrSet: vi.fn() }),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 10,
		intervalOptions: [10, 15, 30, 60],
		setBoost: vi.fn(),
	}),
}));

import { auth } from '$lib/stores/auth';
import Page from '../+page.svelte';

const instance = (id: string, name: string): Instance => ({
	id,
	name,
	status: 'ACTIVE',
	image_name: 'Ubuntu',
	flavor_name: 'small',
	ip_addresses: [],
	created_at: null,
	union_libraries: [],
	union_strategy: null,
});

describe('instance list loading graph', () => {
	beforeEach(() => {
		mockGet.mockReset();
		auth.update((state) => ({ ...state, token: 'token-a', projectId: 'project-a' }));
	});

	it('starts list and metrics together and releases the page when the list settles', async () => {
		const list = Promise.withResolvers<Instance[]>();
		const metrics = Promise.withResolvers<{
			prometheus_available: boolean;
			instances: Record<string, never>;
		}>();
		mockGet.mockImplementation((path: string) => path.endsWith('metrics-summary-batch')
			? metrics.promise
			: list.promise);

		render(Page);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		expect(mockGet.mock.calls.map((call) => call[0])).toEqual([
			'/api/v1/instances',
			'/api/v1/instances/metrics-summary-batch',
		]);

		list.resolve([]);
		expect(await screen.findByText('인스턴스가 없습니다')).toBeTruthy();
		expect(metrics.promise).toBeInstanceOf(Promise);
	});

	it('keeps a newer project result when the previous list resolves late', async () => {
		const oldList = Promise.withResolvers<Instance[]>();
		const oldMetrics = Promise.withResolvers<unknown>();
		const newList = Promise.withResolvers<Instance[]>();
		const newMetrics = Promise.withResolvers<unknown>();
		const lists = [oldList, newList];
		const metrics = [oldMetrics, newMetrics];
		mockGet.mockImplementation((path: string) => path.endsWith('metrics-summary-batch')
			? metrics.shift()!.promise
			: lists.shift()!.promise);

		render(Page);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		auth.update((state) => ({ ...state, token: 'token-b', projectId: 'project-b' }));
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(4));

		newList.resolve([instance('new-id', 'new-instance')]);
		expect(await screen.findByText('new-instance')).toBeTruthy();
		oldList.resolve([instance('old-id', 'old-instance')]);
		await Promise.resolve();
		expect(screen.queryByText('old-instance')).toBeNull();
	});
});
