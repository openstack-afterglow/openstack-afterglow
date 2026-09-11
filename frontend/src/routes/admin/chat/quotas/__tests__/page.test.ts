import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
	class ApiError extends Error {
		constructor(message: string, public status: number) {
			super(message);
		}
	}
	return { get: vi.fn(), put: vi.fn(), ApiError };
});

vi.mock('$lib/stores/auth', () => ({
	auth: {
		subscribe(run: (value: { token: string; projectId: string; isSystemAdmin: boolean }) => void) {
			run({ token: 'browser-token', projectId: 'project-1', isSystemAdmin: true });
			return () => {};
		}
	}
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, put: mocks.put },
	ApiError: mocks.ApiError
}));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import QuotaPage from '../+page.svelte';

const users = {
	items: [
		{ id: 'u1', name: 'alice', email: 'a@x', enabled: true },
		{ id: 'u2', name: 'bob', email: 'b@x', enabled: true }
	],
	next_marker: null
};
const quota = {
	user_id: 'u1',
	project_id: null,
	monthly_credit_limit: '5000',
	weekly_credit_limit: null,
	month_credited_cost: '12.5',
	week_credited_cost: '1',
	is_active: true,
	updated_at: null
};

describe('admin user quota page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/users?')) return Promise.resolve(users);
			if (path === '/api/v1/chat/admin/quotas') {
				return Promise.resolve({ default_monthly_credit_limit: '100000', items: [quota] });
			}
			return Promise.resolve({});
		});
		mocks.put.mockResolvedValue({
			...quota,
			user_id: 'u2',
			monthly_credit_limit: '3000',
			weekly_credit_limit: '700',
			month_credited_cost: '0',
			week_credited_cost: '0'
		});
	});

	afterEach(cleanup);

	it('merges Keystone users with Lumen quotas and saves an edit', async () => {
		render(QuotaPage);

		const alice = (await screen.findByText('alice')).closest('tr');
		const bob = screen.getByText('bob').closest('tr');
		expect(alice).not.toBeNull();
		expect(bob).not.toBeNull();
		expect(within(alice!).getByText('5,000')).toBeTruthy();
		expect(within(bob!).getByText('100,000')).toBeTruthy();
		expect(within(bob!).getByText('기본값')).toBeTruthy();

		await fireEvent.click(within(bob!).getByRole('button', { name: '편집' }));
		await fireEvent.input(screen.getByLabelText('월 한도(크레딧)'), { target: { value: '3000' } });
		await fireEvent.input(screen.getByLabelText('주간 한도(크레딧)'), { target: { value: '700' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		await waitFor(() => {
			expect(mocks.put).toHaveBeenCalledWith(
				'/api/v1/chat/admin/quotas/u2',
				{ monthly_credit_limit: '3000', weekly_credit_limit: '700' },
				'browser-token',
				'project-1'
			);
		});
	});

	it('preserves the default monthly cap when only the weekly limit is edited', async () => {
		render(QuotaPage);

		const bob = (await screen.findByText('bob')).closest('tr');
		await fireEvent.click(within(bob!).getByRole('button', { name: '편집' }));
		expect((screen.getByLabelText('월 한도(크레딧)') as HTMLInputElement).value).toBe('100000');

		await fireEvent.input(screen.getByLabelText('주간 한도(크레딧)'), { target: { value: '700' } });
		await fireEvent.click(screen.getByRole('button', { name: '저장' }));

		await waitFor(() => {
			expect(mocks.put).toHaveBeenCalledWith(
				'/api/v1/chat/admin/quotas/u2',
				{ monthly_credit_limit: '100000', weekly_credit_limit: '700' },
				'browser-token',
				'project-1'
			);
		});
	});
});
