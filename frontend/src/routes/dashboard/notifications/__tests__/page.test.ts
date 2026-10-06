import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { page } from '$app/stores';
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

const originalScrollIntoView = Element.prototype.scrollIntoView;

function announcement(overrides: Partial<AnnouncementUser> = {}): AnnouncementUser {
	return {
		id: 7,
		created_at: '2026-01-01T00:00:00Z',
		created_by_username: 'admin',
		title: 'Maintenance notice',
		body: 'Scheduled work',
		severity: 'info',
		starts_at: null,
		ends_at: null,
		is_read: false,
		...overrides,
	};
}

afterEach(() => {
	vi.unstubAllGlobals();
	Element.prototype.scrollIntoView = originalScrollIntoView;
	(page as unknown as Writable<{ url: URL; data: object }>).set({ url: new URL('http://localhost/dashboard/notifications'), data: {} });
});

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
		announcements.resolve([announcement()]);
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

	it('jumps to a deep-linked announcement without smooth scrolling when reduced motion is requested', async () => {
		(page as unknown as Writable<{ url: URL; data: object }>).set({ url: new URL('http://localhost/dashboard/notifications?focus=7'), data: {} });
		vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
			matches: query.includes('reduce'), media: query, onchange: null,
			addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(),
			removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
		})));
		const scrollIntoView = vi.fn();
		Element.prototype.scrollIntoView = scrollIntoView;
		mockGet.mockImplementation((path: string) => Promise.resolve(path.startsWith('/api/v1/announcements') ? [announcement()] : { alerts: [] }));
		mockPost.mockResolvedValue({});

		render(Page);

		await vi.waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center', behavior: 'auto' }));
		expect(screen.getByRole('button', { name: /Maintenance notice/ }).getAttribute('aria-expanded')).toBe('true');
	});
});
