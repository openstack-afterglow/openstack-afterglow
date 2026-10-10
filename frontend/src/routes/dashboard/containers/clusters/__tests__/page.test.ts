import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';

const { mockGet, mockPrefetch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPrefetch: vi.fn() }));

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, prefetch: mockPrefetch, post: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }), canWrite: writable(true) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [10, 15, 30, 60] }),
}));

import { canWrite } from '$lib/stores/auth';
import Page from '../+page.svelte';

describe('cluster create catalog intent', () => {
	beforeEach(() => { vi.clearAllMocks(); (canWrite as Writable<boolean>).set(true); });
	it('keeps templates deferred until intent and uses the same path on click', async () => {
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/clusters') return Promise.resolve([]);
			if (path === '/api/v1/clusters/templates') return Promise.resolve([]);
			throw new Error(`unexpected GET ${path}`);
		});
		mockPrefetch.mockResolvedValue(undefined);

		render(Page);
		const create = await screen.findByRole('button', { name: '+ 클러스터 생성' });
		expect(mockGet).toHaveBeenCalledOnce();

		await fireEvent.pointerEnter(create);
		expect(mockPrefetch).toHaveBeenCalledWith('/api/v1/clusters/templates', 'token', 'project');
		expect(mockGet).toHaveBeenCalledOnce();

		await fireEvent.click(create);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		expect(mockGet.mock.calls[1][0]).toBe('/api/v1/clusters/templates');
	});
	it('denies ordinary cluster writes with canWrite=false rather than substituting a service role', async () => {
		(canWrite as Writable<boolean>).set(false);
		mockGet.mockResolvedValue([]);
		render(Page);
		const create = await screen.findByRole('button', { name: '+ 클러스터 생성' }) as HTMLButtonElement;
		expect(create.disabled).toBe(true);
		await fireEvent.pointerEnter(create);
		await fireEvent.click(create);
		expect(mockPrefetch).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(mockGet.mock.calls.map(call => call[0])).toEqual(['/api/v1/clusters']);
	});
});
