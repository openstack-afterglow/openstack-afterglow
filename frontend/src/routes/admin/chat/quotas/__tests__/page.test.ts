import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
	class ApiError extends Error {
		constructor(message: string, public status: number) {
			super(message);
		}
	}
	return { get: vi.fn(), put: vi.fn(), delete: vi.fn(), confirm: vi.fn(), ApiError };
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
	api: { get: mocks.get, put: mocks.put, delete: mocks.delete },
	ApiError: mocks.ApiError
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
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
	configured_monthly_credit_limit: '5000',
	configured_weekly_credit_limit: null,
	monthly_limit_source: 'user',
	weekly_limit_source: 'user',
	weekly_bound_by_monthly: true,
	month_credited_cost: '12.5',
	week_credited_cost: '1',
	is_active: true,
	updated_at: null
};
const quotaList = {
	default_monthly_credit_limit: '100000',
	default_weekly_credit_limit: null,
	credit_policy: {
		credit_per_usd: '1000',
		usd_per_credit: '0.0010000000',
		formula: 'credited_cost = raw_cost × margin × credit_per_usd'
	},
	items: [quota]
};
const usageDetail = {
	user_id: 'u1',
	range: '30d',
	period_start: '2026-08-12T00:00:00Z',
	period_end: '2026-09-11T00:00:00Z',
	overview: {
		prompt_tokens: 120,
		completion_tokens: 30,
		total_tokens: 150,
		credited_cost: '12.5',
		raw_cost: '0.0125',
		request_count: 2
	},
	by_model: [
		{
			model_name: 'gpt-5.4',
			provider: 'openai',
			prompt_tokens: 120,
			completion_tokens: 30,
			total_tokens: 150,
			credited_cost: '12.5',
			raw_cost: '0.0125',
			request_count: 2
		}
	],
	by_source: [
		{
			source: 'api',
			prompt_tokens: 120,
			completion_tokens: 30,
			total_tokens: 150,
			credited_cost: '12.5',
			raw_cost: '0.0125',
			request_count: 2
		}
	],
	records: [
		{
			id: 9,
			created_at: '2026-09-10T03:04:05Z',
			model_name: 'gpt-5.4',
			provider: 'openai',
			prompt_tokens: 100,
			completion_tokens: 20,
			total_tokens: 120,
			credited_cost: '10',
			raw_cost: '0.01',
			source: 'api',
			api_key_id: 3,
			pricing_status: 'priced'
		}
	],
	next_before_id: null
};

describe('admin user quota page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.confirm.mockResolvedValue(true);
		mocks.get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/users?')) return Promise.resolve(users);
			if (path === '/api/v1/chat/admin/quotas') return Promise.resolve(quotaList);
			if (path.startsWith('/api/v1/chat/admin/stats/users/u1?')) return Promise.resolve(usageDetail);
			return Promise.resolve({});
		});
		mocks.put.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/quotas/defaults') {
				return Promise.resolve({ default_monthly_credit_limit: '80000' });
			}
			return Promise.resolve({
				...quota,
				user_id: 'u2',
				monthly_credit_limit: '3000',
				weekly_credit_limit: '700',
				configured_monthly_credit_limit: '3000',
				configured_weekly_credit_limit: '700',
				month_credited_cost: '0',
				week_credited_cost: '0'
			});
		});
		mocks.delete.mockResolvedValue({
			...quota,
			configured_monthly_credit_limit: null,
			configured_weekly_credit_limit: null,
			monthly_credit_limit: '100000',
			monthly_limit_source: 'default',
			weekly_limit_source: 'default'
		});
	});

	afterEach(cleanup);

	it('separates the system default from personal quota edits', async () => {
		render(QuotaPage);

		const alice = (await screen.findByText('alice')).closest('tr');
		const bob = screen.getByText('bob').closest('tr');
		expect(alice).not.toBeNull();
		expect(bob).not.toBeNull();
		expect(within(alice!).getByText('5,000')).toBeTruthy();
		expect(within(bob!).getByText('100,000')).toBeTruthy();
		expect(within(bob!).getAllByText('기본값')).toHaveLength(2);
		expect(within(bob!).getByText('월 한도 내 무제한')).toBeTruthy();

		await fireEvent.click(within(bob!).getByRole('button', { name: '편집' }));
		await fireEvent.input(screen.getByLabelText('개인 월 한도(크레딧)'), { target: { value: '3000' } });
		await fireEvent.input(screen.getByLabelText('개인 주간 한도(크레딧)'), { target: { value: '700' } });
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
		expect((screen.getByLabelText('개인 월 한도(크레딧)') as HTMLInputElement).value).toBe('100000');

		await fireEvent.input(screen.getByLabelText('개인 주간 한도(크레딧)'), { target: { value: '700' } });
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

	it('updates the system default independently and resets a personal override', async () => {
		render(QuotaPage);
		await screen.findByText('alice');

		await fireEvent.input(screen.getByLabelText('기본 월 한도(크레딧)'), { target: { value: '80000' } });
		await fireEvent.click(screen.getByRole('button', { name: '기본값 저장' }));
		await waitFor(() => {
			expect(mocks.put).toHaveBeenCalledWith(
				'/api/v1/chat/admin/quotas/defaults',
				{ monthly_credit_limit: '80000' },
				'browser-token',
				'project-1'
			);
		});

		const alice = screen.getByText('alice').closest('tr');
		await fireEvent.click(within(alice!).getByRole('button', { name: '기본값 복원' }));
		await waitFor(() => {
			expect(mocks.delete).toHaveBeenCalledWith(
				'/api/v1/chat/admin/quotas/u1',
				'browser-token',
				'project-1'
			);
		});
	});

	it('opens timestamped per-user model and source usage detail', async () => {
		render(QuotaPage);
		const alice = (await screen.findByText('alice')).closest('tr');

		await fireEvent.click(within(alice!).getByRole('button', { name: '사용량' }));

		expect(await screen.findByRole('dialog', { name: '사용자 사용량 상세' })).toBeTruthy();
		expect((await screen.findAllByText('gpt-5.4')).length).toBeGreaterThanOrEqual(2);
		expect(screen.getAllByText('API').length).toBeGreaterThan(0);
		expect(screen.getAllByText(/key #3/).length).toBeGreaterThan(0);
		expect(screen.getAllByText('150').length).toBeGreaterThan(0);
		expect(mocks.get).toHaveBeenCalledWith(
			expect.stringMatching(/^\/api\/v1\/chat\/admin\/stats\/users\/u1\?range=30d&limit=50/),
			'browser-token',
			'project-1'
		);
	});
});
