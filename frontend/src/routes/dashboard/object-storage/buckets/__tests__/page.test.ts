import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { AccountMeta, SwiftContainer } from '$lib/types/objectStorage';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', userId: 'user-a', projectId: 'project', canWrite: true }), authReady: writable(true), canWrite: writable(true), projectSwitching: writable(false), getAuthVerificationEpoch: () => 1 }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({
		active: false,
		intervalSeconds: 30,
		intervalOptions: [15, 30, 60],
	}),
}));

import Page from '../+page.svelte';

describe('bucket loading boundaries', () => {
	it('starts active, trash, and account together and releases each section independently', async () => {
		const active = Promise.withResolvers<SwiftContainer[]>();
		const trash = Promise.withResolvers<SwiftContainer[]>();
		const account = Promise.withResolvers<AccountMeta>();
		mockGet.mockImplementation((path: string) => {
			if (path === '/api/v1/object-storage') return active.promise;
			if (path === '/api/v1/object-storage/trash/containers') return trash.promise;
			if (path === '/api/v1/object-storage/account') return account.promise;
			throw new Error(`unexpected GET ${path}`);
		});

		render(Page);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(3));

		account.resolve({ container_count: 2, object_count: 7, bytes_used: 1024 });
		expect(await screen.findByText('1.0 KiB')).toBeTruthy();
		expect(screen.getByText('휴지통 버킷을 불러오는 중...')).toBeTruthy();

		active.resolve([]);
		await vi.waitFor(() => expect(screen.queryByText('버킷이 없습니다')).toBeNull());
		trash.reject(new Error('trash unavailable'));
		expect(await screen.findByText('trash unavailable')).toBeTruthy();
		expect(screen.getByText('1.0 KiB')).toBeTruthy();
	});
});
