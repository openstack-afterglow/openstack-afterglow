import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get } }));
import ChatUsagePanel from '../ChatUsagePanel.svelte';

afterEach(cleanup);
beforeEach(() => { mocks.get.mockReset(); });

describe('chat usage token distribution', () => {
	it('keeps absent and invalid measurements distinct from genuine zero token buckets', async () => {
		mocks.get.mockImplementation((path: string) => {
			if (path.includes('/timeseries?')) return Promise.resolve({ series: [
				{ bucket: '2026-10-01', source: 'api', total_tokens: 50, credited_cost: 1, request_count: 1 },
				{ bucket: '2026-10-02', source: 'web', total_tokens: Number.NaN, credited_cost: 1, request_count: 1 },
				{ bucket: '2026-10-03', source: 'web', total_tokens: 0, credited_cost: 0, request_count: 0 },
			] });
			if (path.endsWith('/keys')) return Promise.resolve({ keys: [] });
			return Promise.resolve({ by_source: [] });
		});
		render(ChatUsagePanel);
		const chart = await screen.findByRole('group', { name: '사용량 추이' });
		const details = chart.querySelector('details')!;
		details.open = true;
		await fireEvent(details, new Event('toggle'));
		const values = [...chart.querySelectorAll('tbody tr')].map(row => [...row.querySelectorAll('td')].map(cell => cell.textContent));
		expect(values).toEqual([['—', '50'], ['—', '—'], ['0', '—']]);
	});
});
