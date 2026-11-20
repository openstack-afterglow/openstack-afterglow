import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

type UsageSnapshot = { data: Record<string, unknown>[] };
const mocks = vi.hoisted(() => ({ get: vi.fn(), charts: [] as { data: Record<string, unknown>[] }[] }));
vi.mock('$lib/components/charts/runtime', () => ({
	mountChart: (_element: unknown, spec: UsageSnapshot) => {
		mocks.charts.push(spec);
		return { update: (next: UsageSnapshot) => { mocks.charts.push(next); }, destroy: () => undefined };
	},
}));
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
		const { container } = render(ChatUsagePanel);
		const chart = await screen.findByRole('group', { name: '사용량 추이' });
		expect(screen.getByRole('heading', { level: 3, name: '사용량 추이' })).toBeTruthy();
		expect(container.querySelector('.rounded-lg.border')).toBeNull();
		expect(chart.querySelector('details')).toBeNull();
		await waitFor(() => expect(mocks.charts.at(-1)).toBeDefined());
		const spec = mocks.charts.at(-1);
		expect(spec?.data.map(row => [row.web ?? null, row.api ?? null])).toEqual([[null, 50], [null, null], [0, null]]);
		const selectedBucket = screen.getByRole('button', { pressed: true });
		expect(selectedBucket.className).toContain('--color-surface-selected');
		const nextBucket = screen.getAllByRole('button', { pressed: false })[0];
		await fireEvent.click(nextBucket);
		expect(nextBucket.getAttribute('aria-pressed')).toBe('true');
		expect(selectedBucket.getAttribute('aria-pressed')).toBe('false');
	});
});
