import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet, delete: vi.fn() } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 30,
		intervalOptions: [15, 30, 60],
	}),
}));

import Page from '../+page.svelte';

describe('system administrator loading boundaries', () => {
	it('releases the administrator shell while policy remains isolated and retryable', async () => {
		const admins = Promise.withResolvers<Array<{ user_id: string; name: string; email: string; enabled: boolean }>>();
		const policy = Promise.withResolvers<unknown>();
		mockGet.mockImplementation((path: string) => {
			if (path.endsWith('/system-roles')) return admins.promise;
			if (path.endsWith('/security-policy')) return policy.promise;
			throw new Error(`unexpected GET ${path}`);
		});

		render(Page);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		admins.resolve([{ user_id: 'user-1', name: 'Alice', email: 'alice@example.test', enabled: true }]);
		expect(await screen.findByText('Alice')).toBeTruthy();
		const loadingPolicy = screen.getByRole('status');
		expect(loadingPolicy.textContent).toContain('보안 정책을 불러오는 중...');
		expect(loadingPolicy.querySelector('[role="status"]')).toBeNull();

		policy.reject(new Error('policy unavailable'));
		expect(await screen.findByText('policy unavailable')).toBeTruthy();
		expect(screen.getByText('Alice')).toBeTruthy();
	});
});
