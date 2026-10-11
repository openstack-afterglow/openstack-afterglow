import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';

// --- module mocks (must be declared before static imports) ---

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE: 'http://localhost:8000' } }));

// Use vi.hoisted so mockGet is available inside the vi.mock factory (which is hoisted)
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet },
}));

vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'test-token', projectId: 'test-project' }),
}));

vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [15, 30, 60] }),
}));

import ActivityLogTable from '../ActivityLogTable.svelte';
import { auth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/admin-system';
import { t as tc } from '$lib/i18n/ns/common';

// ---------------------------------------------------------------------------

beforeEach(() => {
	vi.clearAllMocks();
	auth.set({ token: 'test-token', projectId: 'test-project' } as never);
});

afterEach(() => {
	vi.useRealTimers();
});

describe('ActivityLogTable', () => {
	it('empty response renders empty message', async () => {
		mockGet.mockResolvedValue([]);

		render(ActivityLogTable, { props: { endpoint: '/api/v1/test/activity', storageKey: 'test' } });

		const msg = await screen.findByText('활동 없음');
		expect(msg).toBeTruthy();
	});

	it('single log row renders action correctly', async () => {
		const now = new Date().toISOString();
		mockGet.mockResolvedValue([
			{
				id: 1,
				action: 'volume.create',
				status: 'success',
				resource_type: 'volume',
				resource_name: 'my-vol',
				resource_id: null,
				created_at: now,
				username: 'user1',
				project_id: 'proj-1',
				user_id: 'u1',
				error_message: null,
				extra: null,
			},
		]);

		render(ActivityLogTable, {
			props: { endpoint: '/api/v1/test/activity', storageKey: 'test', showUser: true },
		});

		const cell = await screen.findByText('volume.create');
		expect(cell).toBeTruthy();
	});

	it('failed status shows error expand button', async () => {
		const now = new Date().toISOString();
		mockGet.mockResolvedValue([
			{
				id: 2,
				action: 'volume.delete',
				status: 'failed',
				resource_type: 'volume',
				resource_name: 'bad-vol',
				resource_id: null,
				created_at: now,
				username: 'user2',
				project_id: 'proj-1',
				user_id: 'u2',
				error_message: 'disk quota exceeded',
				extra: null,
			},
		]);

		render(ActivityLogTable, { props: { endpoint: '/api/v1/test/activity', storageKey: 'test' } });

		const btn = await screen.findByText('상세');
		expect(btn).toBeTruthy();
	});
	it('debounces filters, aborts the superseded request, and ignores its late response', async () => {
		vi.useFakeTimers();
		const first = Promise.withResolvers<unknown[]>();
		const second = Promise.withResolvers<unknown[]>();
		mockGet
			.mockImplementationOnce(() => first.promise)
			.mockImplementationOnce(() => second.promise);
		render(ActivityLogTable, { props: { endpoint: '/api/v1/test/activity', storageKey: 'test' } });

		await vi.advanceTimersByTimeAsync(250);
		expect(mockGet).toHaveBeenCalledOnce();
		const firstSignal = mockGet.mock.calls[0][3].signal as AbortSignal;

		await fireEvent.input(screen.getByPlaceholderText('액션 필터 (예: instance.create)'), {
			target: { value: 'instance.create' },
		});
		await vi.advanceTimersByTimeAsync(249);
		expect(mockGet).toHaveBeenCalledOnce();
		expect(firstSignal.aborted).toBe(true);
		await vi.advanceTimersByTimeAsync(1);
		expect(mockGet).toHaveBeenCalledTimes(2);

		second.resolve([{
			id: 2,
			action: 'instance.create',
			status: 'success',
			resource_type: 'instance',
			resource_name: 'new',
			resource_id: null,
			created_at: new Date().toISOString(),
			username: 'user',
			project_id: 'project',
			user_id: 'user',
			error_message: null,
			extra: null,
		}]);
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.getByText('instance.create')).toBeTruthy();

		first.resolve([{
			id: 1,
			action: 'stale.action',
			status: 'success',
			resource_type: 'instance',
			resource_name: 'stale',
			resource_id: null,
			created_at: new Date().toISOString(),
			username: 'user',
			project_id: 'project',
			user_id: 'user',
			error_message: null,
			extra: null,
		}]);
		await vi.advanceTimersByTimeAsync(0);
		expect(screen.queryByText('stale.action')).toBeNull();
	});

	it.each([10, 15, 20])('shows only %i records and replaces the page instead of appending', async (size) => {
		const rows = Array.from({ length: 43 }, (_, index) => ({
			id: 43 - index, action: 'volume.create', status: 'success', resource_type: 'volume',
			resource_name: `log-${43 - index}`, resource_id: null, created_at: new Date().toISOString(),
			username: 'user', project_id: 'test-project', user_id: 'user', error_message: null, extra: null,
		}));
		mockGet.mockImplementation((path: string) => {
			const params = new URL(path, 'http://localhost').searchParams;
			const cursor = Number(params.get('before_id') ?? '44');
			return Promise.resolve(rows.filter(row => row.id < cursor).slice(0, Number(params.get('limit'))));
		});
		render(ActivityLogTable, { props: { endpoint: '/api/v1/test/activity', storageKey: 'test' } });
		await screen.findByText('log-43');
		await fireEvent.change(screen.getByLabelText(t('activity.pageSize')), { target: { value: String(size) } });
		await screen.findByText(`log-${44 - size}`);
		expect(screen.getAllByText(/^log-\d+$/)).toHaveLength(size);
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.next') }));
		await screen.findByText(`log-${43 - size}`);
		expect(screen.queryByText('log-43')).toBeNull();
		expect(screen.getAllByText(/^log-\d+$/)).toHaveLength(size);
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.previous') }));
		await screen.findByText('log-43');
		expect(screen.getAllByText(/^log-\d+$/)).toHaveLength(size);
	});

	it('keeps the cursor on refresh, resets on filters, and permits previous from an emptied page', async () => {
		const rows = Array.from({ length: 12 }, (_, index) => ({
			id: 12 - index, action: 'volume.create', status: 'success', resource_type: 'volume',
			resource_name: `log-${12 - index}`, created_at: new Date().toISOString(),
		}));
		let emptyLaterPage = false;
		mockGet.mockImplementation((path: string) => {
			const params = new URL(path, 'http://localhost').searchParams;
			if (emptyLaterPage && params.has('before_id')) return Promise.resolve([]);
			return Promise.resolve(rows.filter(row => row.id < Number(params.get('before_id') ?? '13')).slice(0, Number(params.get('limit'))));
		});
		render(ActivityLogTable, { props: { endpoint: '/api/v1/test/activity', storageKey: 'test' } });
		await screen.findByText('log-12');
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.next') }));
		await screen.findByText('log-2');
		expect(screen.getByRole('button', { name: tc('pagination.next') }).hasAttribute('disabled')).toBe(true);
		emptyLaterPage = true;
		await fireEvent.click(screen.getByRole('button', { name: /새로고침/ }));
		await screen.findByText(t('activity.empty'));
		expect(new URL(mockGet.mock.calls.at(-1)![0], 'http://localhost').searchParams.get('before_id')).toBe('3');
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.previous') }));
		await screen.findByText('log-12');
		emptyLaterPage = false;
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.next') }));
		await screen.findByText('log-2');
		await fireEvent.input(screen.getByPlaceholderText(t('activity.actionFilter')), { target: { value: 'volume' } });
		await screen.findByText('log-12');
		expect(new URL(mockGet.mock.calls.at(-1)![0], 'http://localhost').searchParams.has('before_id')).toBe(false);
	});

	it('discards old user rows and a late cursor response after an auth ABA change', async () => {
		const pending = Promise.withResolvers<unknown[]>();
		mockGet.mockResolvedValue(Array.from({ length: 11 }, (_, index) => ({
			id: 20 - index, action: 'volume.create', status: 'success', resource_type: 'volume',
			resource_name: `old-${20 - index}`, created_at: new Date().toISOString(),
		})));
		render(ActivityLogTable, { props: { endpoint: '/api/v1/test/activity', storageKey: 'test' } });
		await screen.findByText('old-20');
		mockGet.mockImplementationOnce(() => pending.promise).mockResolvedValue([]);
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.next') }));
		await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		auth.set({ token: 'other-token', projectId: 'other-project' } as never);
		await waitFor(() => expect(screen.queryByText('old-20')).toBeNull());
		auth.set({ token: 'test-token', projectId: 'test-project' } as never);
		pending.resolve([{ id: 9, action: 'late-action', status: 'success', resource_type: 'volume', created_at: new Date().toISOString() }]);
		await screen.findByText(t('activity.empty'));
		expect(screen.queryByText('late-action')).toBeNull();
	});

});
