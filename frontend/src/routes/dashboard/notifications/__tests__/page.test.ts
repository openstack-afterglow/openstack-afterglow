import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { AnnouncementUser } from '$lib/types/announcements';

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));

vi.mock('$app/navigation', () => ({
	afterNavigate: (callback: () => void) => { queueMicrotask(callback); },
}));
vi.mock('$app/stores', () => ({
	page: writable({ url: new URL('http://localhost/dashboard/notifications'), data: {} }),
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, post: mockPost },
	ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));

import Page from '../+page.svelte';

describe('notification loading boundaries', () => {
	it('renders announcements before quota and keeps them visible when background read marking fails', async () => {
		const announcements = Promise.withResolvers<AnnouncementUser[]>();
		const quota = Promise.withResolvers<unknown>();
		const readMark = Promise.withResolvers<unknown>();
		mockGet.mockImplementation((path: string) => path.startsWith('/api/v1/announcements')
			? announcements.promise
			: quota.promise);
		mockPost.mockReturnValue(readMark.promise);

		render(Page);
		await vi.waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		announcements.resolve([{
			id: 7,
			created_at: '2026-01-01T00:00:00Z',
			created_by_username: 'admin',
			title: 'Maintenance notice',
			body: 'Scheduled work',
			severity: 'info',
			starts_at: null,
			ends_at: null,
			is_read: false,
		}]);
		expect(await screen.findByText('Maintenance notice')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: /Maintenance notice/ }));
		expect(screen.getByText('admin (관리자)')).toBeTruthy();
		expect(screen.getByText('쿼터 경고를 불러오는 중...')).toBeTruthy();
		expect(screen.queryByText('new')).toBeNull();
		expect(mockPost).toHaveBeenCalledWith('/api/v1/announcements/7/read', {}, 'token', 'project');

		readMark.reject(new Error('read mark unavailable'));
		await Promise.resolve();
		expect(screen.getByText('Maintenance notice')).toBeTruthy();

		quota.resolve({ alerts: [{ severity: 'warning', message: 'Volume quota high', count: 1 }] });
		expect(await screen.findByText('Volume quota high')).toBeTruthy();
	});
});
