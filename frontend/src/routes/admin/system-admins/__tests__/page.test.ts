import { beforeEach, describe, expect, it, vi } from 'vitest';
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
	beforeEach(() => {
		mockGet.mockReset();
	});

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

	it('renders native system authority from the strict count-only policy DTO', async () => {
		mockGet.mockImplementation(async (path: string) => {
			if (path.endsWith('/system-roles')) return [];
			if (path.endsWith('/security-policy')) return { system_admin_count: 2 };
			throw new Error(`unexpected GET ${path}`);
		});

		render(Page);
		const authority = await screen.findByText(/system:all/);
		expect(authority.textContent).toContain('2');
		expect(authority.textContent).toContain('admin');
		expect(screen.queryByText(/호환|Strict 모드/)).toBeNull();
		expect(screen.queryByRole('button', { name: /마이그레이션/ })).toBeNull();
	});

	it('shows lockout recovery for a verified zero without compatibility settings', async () => {
		mockGet.mockImplementation(async (path: string) => {
			if (path.endsWith('/system-roles')) return [];
			if (path.endsWith('/security-policy')) return { system_admin_count: 0 };
			throw new Error(`unexpected GET ${path}`);
		});

		render(Page);
		expect(await screen.findByText('Lockout 위험')).toBeTruthy();
		expect(screen.getByRole('alert').textContent).toContain('system:all');
		expect(screen.getByText('python3 scripts/manage_system_admins.py --os-system-scope grant <user-id>')).toBeTruthy();
		expect(screen.queryByText(/호환/)).toBeNull();
	});

	it('keeps native authority denials visible instead of substituting a zero policy', async () => {
		mockGet.mockImplementation(async (path: string) => {
			if (path.endsWith('/system-roles')) throw new Error('native system-role access denied');
			if (path.endsWith('/security-policy')) throw new Error('native policy access denied');
			throw new Error(`unexpected GET ${path}`);
		});

		render(Page);
		expect(await screen.findByText('native policy access denied')).toBeTruthy();
		expect(await screen.findByText('native system-role access denied')).toBeTruthy();
		expect(screen.queryByText('Lockout 위험')).toBeNull();
		expect(screen.queryByText(/system:all/)).toBeNull();
	});
});
