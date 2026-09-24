// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';

const { mockFetch } = vi.hoisted(() => ({ mockFetch: vi.fn() }));

vi.mock('$app/environment', () => ({ browser: false }));
vi.mock('$lib/config/site', async () => {
	const { writable } = await import('svelte/store');
	return {
		siteConfig: writable({ runtime: { api_base: 'http://localhost:8000' } }),
	};
});
vi.mock('$lib/stores/auth', async () => {
	const { writable } = await import('svelte/store');
	return {
		auth: writable({ token: null, refreshToken: null, accessExpiresAt: null, projectId: null }),
		logoutInProgress: writable(false),
		getMockupProfile: () => null,
		isMockAuthActive: () => false,
		setAuth: vi.fn(),
		clearAuth: vi.fn(),
	};
});
vi.stubGlobal('fetch', mockFetch);

describe('SSR prefetch', () => {
	it('is a no-op and allocates no browser request work', async () => {
		const { api } = await import('../client');

		await expect(api.prefetch('/api/v1/items')).resolves.toBeUndefined();

		expect(mockFetch).not.toHaveBeenCalled();
	});
});
