import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/svelte';
import { auth } from '$lib/stores/auth';

const { api, memoryCache } = vi.hoisted(() => ({
	api: { get: vi.fn(), delete: vi.fn(), post: vi.fn() },
	memoryCache: { get: vi.fn(), set: vi.fn() },
}));
vi.mock('$lib/api/client', () => ({ api, memoryCache, ApiError: class ApiError extends Error {} }));

import Page from '../+page.svelte';

describe('dashboard file-storage refresh ownership', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.get.mockImplementation((path: string) => {
			if (path === '/api/v1/file-storage') return Promise.resolve([]);
			if (path === '/api/v1/file-storage/quota') return Promise.resolve(null);
			return Promise.resolve([]);
		});
		auth.set({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'user', username: 'user', projectId: 'project', projectName: 'project', availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false });
	});

	it('issues one explicit list and quota round on mount', async () => {
		render(Page);
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/file-storage', 'token', 'project', undefined));
		expect(api.get).toHaveBeenCalledWith('/api/v1/file-storage/quota', 'token', 'project');
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/file-storage')).toHaveLength(1);
	});
});
