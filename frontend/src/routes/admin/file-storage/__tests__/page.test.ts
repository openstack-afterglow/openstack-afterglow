import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/svelte';
import { auth } from '$lib/stores/auth';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), delete: vi.fn(), post: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error {} }));

import Page from '../+page.svelte';

describe('admin file-storage refresh ownership', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.get.mockResolvedValue([]);
		auth.set({ token: 'token', refreshToken: null, accessExpiresAt: null, userId: 'admin', username: 'admin', projectId: 'project', projectName: 'project', availableProjects: [], roles: ['admin'], isSystemAdmin: true, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false });
	});

	it('starts the explicit list and timeseries round once', async () => {
		render(Page);
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/admin/all-file-storages', 'token', 'project', undefined));
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/admin/all-file-storages')).toHaveLength(1);
		expect(api.get.mock.calls.some(([path]) => String(path).startsWith('/api/v1/admin/timeseries/file_storage?range='))).toBe(true);
	});
});
