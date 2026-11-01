import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get, writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/stores/auth', () => {
	return { auth: writable({ token: 'token', projectId: 'project', userId: 'admin', sessionId: 'session', identityDomainId: 'home', domainId: 'working', isSystemAdmin: true }), authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false) };
});
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get }, ApiError: class extends Error {
	constructor(public status: number, message: string) { super(message); }
} }));

import StatsPage from '$lib/components/admin/chat/AdminChatStatsPage.svelte';
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import { t } from '$lib/i18n/ns/chat-studio';
import { t as usageT } from '$lib/i18n/ns/admin-chat-usage';
import { ApiError } from '$lib/api/client';
import { tick } from 'svelte';

const usage = {
	prompt_tokens: 60, completion_tokens: 40, total_tokens: 100,
	credited_cost: 1, raw_cost: 0.001, request_count: 1, unpriced_requests: 0
};
const response = {
	range: '30d', project_id: null,
	overview: { ...usage, active_users: 20, conversation_count: 20, by_source: [] },
	by_model: [
		{ ...usage, model_name: 'model-a' },
		{ ...usage, model_name: 'model-b', total_tokens: 25 }
	],
	monthly: [], timeseries: [], projects: [],
	by_user: Array.from({ length: 20 }, (_, index) => ({ ...usage, user_id: `user-${index}`, user_name: `User ${index}` }))
};

describe('chat admin statistics activity', () => {
	beforeEach(() => {
		auth.set({ token: 'token', projectId: 'project', userId: 'admin', sessionId: 'session', identityDomainId: 'home', domainId: 'working', isSystemAdmin: true } as never);
		authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
		setAdminInventoryScope('', '');
		mocks.get.mockReset();
		mocks.get.mockImplementation((path: string) => {
			if (path.includes('/timeseries?')) return Promise.resolve({ series: [] });
			return Promise.resolve(response);
		});
	});
	afterEach(cleanup);

	it('keeps overview, chart, and pagination activity tied to their requests', async () => {
		const overview = Promise.withResolvers<unknown>();
		const chart = Promise.withResolvers<unknown>();
		const more = Promise.withResolvers<unknown>();
		mocks.get.mockImplementation((path: string) => {
			if (path.includes('/timeseries?')) return chart.promise;
			if (path.includes('/stats/users?')) return more.promise;
			return overview.promise;
		});
		render(StatsPage);
		expect((await screen.findByRole('status')).textContent).toContain('불러오는 중…');
		expect(screen.queryByText('사용량 데이터가 없습니다')).toBeNull();
		overview.resolve(response);
		await screen.findByRole('meter', { name: 'model-a 상대 토큰 사용량' });
		await waitFor(() => expect(screen.getByRole('status').textContent).toContain('1시간 사용량을 불러오는 중…'));
		chart.resolve({ series: [] });
		await screen.findByText('표시할 1시간 데이터가 없습니다.');
		expect(screen.queryByRole('status')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: '더보기' }));
		const busy = screen.getByRole('button', { name: '불러오는 중…' });
		expect(busy.getAttribute('aria-busy')).toBe('true');
		expect((busy as HTMLButtonElement).disabled).toBe(true);
		expect(busy.textContent).toContain('불러오는 중…');
		more.resolve({ users: [{ ...usage, user_id: 'next-user', user_name: 'Next User' }] });
		await screen.findByText('Next User (next-use)');
		expect(screen.queryByRole('status')).toBeNull();
		expect(screen.queryByRole('button', { name: '불러오는 중…' })).toBeNull();
	});

	it('names relative token meters and preserves the actual token count', async () => {
		render(StatsPage);
		const a = await screen.findByRole('meter', { name: 'model-a 상대 토큰 사용량' });
		const b = screen.getByRole('meter', { name: 'model-b 상대 토큰 사용량' });
		expect(a.getAttribute('aria-valuenow')).toBe('100');
		expect(b.getAttribute('aria-valuenow')).toBe('25');
		expect(b.getAttribute('aria-valuetext')).toBe('25 토큰');
	});

	it('stacks measured token sources without inventing zero-valued missing buckets', async () => {
		const now = new Date();
		const bucket = `${now.toISOString().slice(0, 10)} ${now.toISOString().slice(11, 13)}:00:00`;
		mocks.get.mockImplementation((path: string) => path.includes('/timeseries?')
			? Promise.resolve({ series: [
				{ ...usage, bucket, source: 'web' },
				{ ...usage, bucket, source: 'api', prompt_tokens: 20, completion_tokens: 10, total_tokens: 30 },
			] })
			: Promise.resolve(response));
		render(StatsPage);
		const summary = await screen.findByText('차트 데이터 보기');
		const details = summary.closest('details')!;
		details.open = true;
		await fireEvent(details, new Event('toggle'));
		const rows = [...details.querySelectorAll('tbody tr')];
		expect([...rows.at(-1)!.querySelectorAll('td')].map(cell => cell.textContent)).toEqual(['80', '50']);
		expect([...rows.at(-2)!.querySelectorAll('td')].map(cell => cell.textContent)).toEqual(['—', '—']);
	});

	it('sends the independent domain and project intersection on overview, chart and user pages', async () => {
		setAdminInventoryScope('domain-a', 'project-a');
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/stats/users?') ? { users: [] } : path.includes('/timeseries?') ? { series: [] } : response));
		render(StatsPage);
		await screen.findByText('User 0 (user-0)');
		await fireEvent.click(screen.getByRole('button', { name: '더보기' }));
		for (const segment of ['/stats?', '/stats/users?', '/stats/timeseries?']) {
			const call = mocks.get.mock.calls.find(([path]) => path.includes(segment));
			expect(call).toBeTruthy();
			const url = new URL(call![0], 'https://test.invalid');
			expect(url.searchParams.get('domain_id')).toBe('domain-a');
			expect(url.searchParams.get('project_id')).toBe('project-a');
			expect(call!.slice(1)).toEqual(['token', 'project']);
		}
	});

	it.each(['range', 'scope', 'auth'] as const)('drops pending user pages and resets offsets after %s ABA', async kind => {
		const old = Promise.withResolvers<unknown>();
		let firstMore = true;
		mocks.get.mockImplementation((path: string) => {
			if (path.includes('/stats/users?')) { if (firstMore) { firstMore = false; return old.promise; } return Promise.resolve({ users: [] }); }
			return Promise.resolve(path.includes('/timeseries?') ? { series: [] } : response);
		});
		render(StatsPage);
		await screen.findByText('User 0 (user-0)');
		await fireEvent.click(screen.getByRole('button', { name: '더보기' }));
		if (kind === 'range') {
			screen.getByRole('button', { name: t('adminStats.range90Days') }).click();
			screen.getByRole('button', { name: t('adminStats.range30Days') }).click();
		} else if (kind === 'scope') { setAdminInventoryScope('other', ''); setAdminInventoryScope('', ''); }
		else { auth.update(state => ({ ...state, projectId: 'other' })); auth.update(state => ({ ...state, projectId: 'project' })); }
		await tick();
		await screen.findByRole('button', { name: '더보기' });
		old.resolve({ users: [{ ...usage, user_id: 'old-user', user_name: 'Stale user' }] });
		await tick(); await tick();
		expect(screen.queryByText(/Stale user/)).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '더보기' }));
		const pages = mocks.get.mock.calls.filter(([path]) => path.includes('/stats/users?'));
		expect(pages).toHaveLength(2);
		expect(pages.every(([path]) => new URL(path, 'https://test.invalid').searchParams.get('offset') === '20')).toBe(true);
	});

	it.each(['sessionId', 'userId', 'identityDomainId', 'domainId', 'projectId', 'token'] as const)('does not publish an old overview after %s ABA', async key => {
		const old = Promise.withResolvers<unknown>();
		mocks.get.mockImplementation((path: string) => path.includes('/timeseries?') ? Promise.resolve({ series: [] }) : old.promise);
		render(StatsPage);
		await waitFor(() => expect(mocks.get).toHaveBeenCalled());
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/timeseries?') ? { series: [] } : { ...response, by_user: [] }));
		let previous: unknown;
		auth.update(state => { previous = state[key]; return { ...state, [key]: 'changed' }; });
		auth.update(state => ({ ...state, [key]: previous }));
		await tick(); await tick();
		old.resolve(response); await tick(); await tick();
		expect(screen.queryByText('User 0 (user-0)')).toBeNull();
	});

	it('clears private rows on authority loss and distinguishes denial from verified empty usage', async () => {
		render(StatsPage); await screen.findByText('User 0 (user-0)');
		auth.update(state => ({ ...state, isSystemAdmin: false }));
		await tick();
		expect(screen.queryByText('User 0 (user-0)')).toBeNull();
		expect(screen.queryByText(t('adminStats.emptyTitle'))).toBeNull();
		const count = mocks.get.mock.calls.length;
		projectSwitching.set(true); await tick();
		expect(mocks.get.mock.calls).toHaveLength(count);
	});

	it.each([403, 503])('keeps native HTTP %s separate from platform authority and verified empty usage', async status => {
		const detail = 'native policy detail <script>not executable</script>\nsecond line';
		mocks.get.mockRejectedValue(new ApiError(status, detail));
		render(StatsPage);
		const notice = await screen.findByTestId('lumen-stats-failure');
		expect(notice.dataset.status).toBe(String(status));
		expect(notice.textContent).toContain(usageT(status === 403 ? 'stats.deniedTitle' : 'stats.unavailableTitle'));
		if (status === 403) expect(notice.textContent).toContain('system:admin');
		else {
			expect(notice.textContent).not.toContain('system:admin');
			expect(notice.textContent).not.toContain(usageT('stats.scopeRecovery'));
		}
		expect(notice.querySelector('pre')?.textContent).toBe(`HTTP ${status}\n${detail}`);
		expect(notice.querySelector('script')).toBeNull();
		expect(screen.queryByText(t('adminStats.emptyTitle'))).toBeNull();
		expect(get(auth).isSystemAdmin).toBe(true);
		expect(get(auth).token).toBe('token');
		expect(screen.getByTestId('lumen-stats-scope').textContent).toContain('project');
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/timeseries?') ? { series: [] } : response));
		await fireEvent.click(screen.getByRole('button', { name: usageT('stats.refresh') }));
		await screen.findByText('User 0 (user-0)');
		expect(screen.queryByTestId('lumen-stats-failure')).toBeNull();
	});


	it('retains successful overview, charts and user rows when the next user page fails and retries only that page', async () => {
		render(StatsPage);
		await screen.findByText('User 0 (user-0)');
		mocks.get.mockImplementation((path: string) => path.includes('/stats/users?')
			? Promise.reject(new ApiError(503, 'user page unavailable')) : Promise.resolve(response));
		await fireEvent.click(screen.getByRole('button', { name: t('adminStats.loadMore') }));
		await screen.findByTestId('lumen-stats-user-page-error');
		expect(screen.getByText('User 0 (user-0)')).toBeTruthy();
		expect(screen.getByRole('meter', { name: 'model-a 상대 토큰 사용량' })).toBeTruthy();
		const overviewCalls = mocks.get.mock.calls.filter(([path]) => path.includes('/stats?')).length;
		mocks.get.mockImplementation((path: string) => path.includes('/stats/users?')
			? Promise.resolve({ users: [{ ...usage, user_id: 'next-user', user_name: 'Next User' }] }) : Promise.resolve(response));
		await fireEvent.click(screen.getByRole('button', { name: usageT('stats.refresh') }));
		await screen.findByText('Next User (next-use)');
		expect(screen.getByText('User 0 (user-0)')).toBeTruthy();
		expect(screen.queryByTestId('lumen-stats-user-page-error')).toBeNull();
		expect(mocks.get.mock.calls.filter(([path]) => path.includes('/stats?'))).toHaveLength(overviewCalls);
		const pages = mocks.get.mock.calls.filter(([path]) => path.includes('/stats/users?'));
		expect(pages).toHaveLength(2);
		expect(pages.every(([path]) => new URL(path, 'https://test.invalid').searchParams.get('offset') === '20')).toBe(true);
	});

	it('keeps a newer model chart when the earlier chart finishes late', async () => {
		render(StatsPage); await screen.findByText('User 0 (user-0)');
		const old = Promise.withResolvers<unknown>();
		mocks.get.mockImplementation((path: string) => path.includes('model_name=model-a') ? old.promise : Promise.resolve({ series: [] }));
		await fireEvent.change(screen.getByLabelText(t('adminStats.selectModel')), { target: { value: 'model-a' } });
		await fireEvent.change(screen.getByLabelText(t('adminStats.selectModel')), { target: { value: 'model-b' } });
		await screen.findByText(t('adminStats.chartEmpty', { granularity: t('adminStats.bucketHour') }));
		old.reject(new Error('obsolete chart')); await tick(); await tick();
		expect(screen.queryByText(t('adminStats.timeSeriesLoadFailed'))).toBeNull();
	});
	it.each(['scope', 'range'] as const)('drops a pending overview after independent %s ABA', async kind => {
		const old = Promise.withResolvers<unknown>();
		mocks.get.mockImplementation((path: string) => path.includes('/timeseries?') ? Promise.resolve({ series: [] }) : old.promise);
		render(StatsPage); await waitFor(() => expect(mocks.get).toHaveBeenCalled());
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/timeseries?') ? { series: [] } : { ...response, by_user: [] }));
		if (kind === 'scope') { setAdminInventoryScope('other', ''); setAdminInventoryScope('', ''); }
		else { screen.getByRole('button', { name: t('adminStats.range90Days') }).click(); screen.getByRole('button', { name: t('adminStats.range30Days') }).click(); }
		await tick(); await tick(); old.resolve(response); await tick(); await tick();
		expect(screen.queryByText('User 0 (user-0)')).toBeNull();
	});
	it.each(['scope', 'range', 'auth'] as const)('drops a pending timeseries failure after %s ABA', async kind => {
		const old = Promise.withResolvers<unknown>(); let first = true;
		mocks.get.mockImplementation((path: string) => {
			if (path.includes('/timeseries?')) { if (first) { first = false; return old.promise; } return Promise.resolve({ series: [] }); }
			return Promise.resolve(response);
		});
		render(StatsPage); await screen.findByText('User 0 (user-0)');
		if (kind === 'scope') { setAdminInventoryScope('other', ''); setAdminInventoryScope('', ''); }
		else if (kind === 'range') { screen.getByRole('button', { name: t('adminStats.range90Days') }).click(); screen.getByRole('button', { name: t('adminStats.range30Days') }).click(); }
		else { auth.update(state => ({ ...state, projectId: 'other' })); auth.update(state => ({ ...state, projectId: 'project' })); }
		await screen.findByText(t('adminStats.chartEmpty', { granularity: t('adminStats.bucketHour') }));
		old.reject(new Error('obsolete chart')); await tick(); await tick();
		expect(screen.queryByText(t('adminStats.timeSeriesLoadFailed'))).toBeNull();
	});
});
