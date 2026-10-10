import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';

const { mockGet, refreshCallbacks } = vi.hoisted(() => ({ mockGet: vi.fn(), refreshCallbacks: [] as Array<() => unknown> }));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project', projectName: 'Project One' }),
	authReady: writable(true),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (callback: () => unknown) => {
		refreshCallbacks.push(callback);
		return { active: true, intervalSeconds: 30, intervalOptions: [30, 60] };
	},
}));

import Page from '../+page.svelte';

interface RecentActionFixture {
	id: number;
	created_at: string;
	action: string;
	resource_type: string;
	resource_name: string;
	status: string;
	user_id: string;
	error_message: string | null;
}

function action(id: number, resourceName: string, status = 'success'): RecentActionFixture {
	return {
		id,
		created_at: '2026-10-06T09:15:00Z',
		action: 'instance.create',
		resource_type: 'instance',
		resource_name: resourceName,
		status,
		user_id: 'user',
		error_message: null,
	};
}

function activity(kpi: { total: number; success: number; failed: number }, actions: RecentActionFixture[]) {
	const hours = Array(24).fill(0);
	hours[9] = kpi.total;
	return {
		range: '7d',
		kpi: { ...kpi, last_24h: kpi.total, unique_users: 1 },
		hour_distribution: hours,
		recent_actions: actions,
		db_status: 'ok',
	};
}

function statText(label: string): string {
	return screen.getByText(label).parentElement?.textContent?.replace(/\s+/g, '') ?? '';
}

describe('activity auto-refresh', () => {
	beforeEach(() => {
		mockGet.mockReset();
		refreshCallbacks.length = 0;
	});

	it('keeps existing audit rows in place and publishes the refreshed totals', async () => {
		mockGet.mockResolvedValueOnce(activity({ total: 4, success: 3, failed: 1 }, [action(2, 'vm-beta', 'failed'), action(1, 'vm-alpha')]));
		render(Page);
		const alphaRow = (await screen.findByText('vm-alpha')).closest('tr');
		const betaRow = screen.getByText('vm-beta').closest('tr');
		expect(statText('성공률')).toContain('75%');
		expect(statText('실패한 작업')).toContain('1/4');

		mockGet.mockResolvedValueOnce(activity({ total: 5, success: 4, failed: 1 }, [action(3, 'vm-gamma'), action(2, 'vm-beta', 'failed'), action(1, 'vm-alpha')]));
		await refreshCallbacks.at(-1)?.();
		await tick();

		expect(screen.getByText('vm-gamma')).toBeTruthy();
		// Keyed rows survive the poll: a new entry is added above them instead of every row being repainted.
		expect(screen.getByText('vm-alpha').closest('tr')).toBe(alphaRow);
		expect(screen.getByText('vm-beta').closest('tr')).toBe(betaRow);
		const rows = screen.getAllByRole('row').slice(1).map((row) => row.textContent ?? '');
		expect(rows.map((text) => text.match(/vm-\w+/)?.[0])).toEqual(['vm-gamma', 'vm-beta', 'vm-alpha']);
		expect(statText('성공률')).toContain('80%');
		expect(statText('실패한 작업')).toContain('1/5');
	});

	it('shows no success rate before any task has run', async () => {
		mockGet.mockResolvedValueOnce(activity({ total: 0, success: 0, failed: 0 }, []));
		render(Page);
		expect(await screen.findByText('로그 없음')).toBeTruthy();
		expect(statText('성공률')).toContain('—%');
	});
});
