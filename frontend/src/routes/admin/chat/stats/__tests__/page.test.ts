import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/stores/auth', () => {
	return { auth: writable({ token: 'token', projectId: 'project' }) };
});
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get }, ApiError: class extends Error {} }));

import StatsPage from '../+page.svelte';

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
});
