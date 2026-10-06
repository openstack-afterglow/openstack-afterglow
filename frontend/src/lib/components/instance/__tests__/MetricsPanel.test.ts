import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE: 'http://localhost:8000' } }));

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet },
}));

vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'test-token', projectId: 'test-project' }),
}));

vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (_fn: unknown, _opts: unknown) => ({
		active: false,
		intervalSeconds: 30,
		intervalOptions: [15, 30, 60],
	}),
}));

import MetricsPanel from '../MetricsPanel.svelte';

// Fake series data
const FAKE_SERIES = [
	{ ts: 1700000000, value: 42.0 },
	{ ts: 1700000030, value: 45.0 },
];

const ALL_METRIC_KEYS = ['cpu', 'memory', 'network_rx', 'network_tx', 'disk_read', 'disk_write', 'gpu_util', 'gpu_mem'];

function makeBatchResponse(series: { ts: number; value: number }[]) {
	const metrics: Record<string, { series: { ts: number; value: number }[]; error: null }> = {};
	for (const k of ALL_METRIC_KEYS) metrics[k] = { series, error: null };
	return { metrics };
}

function mockAllMetrics() {
	mockGet.mockResolvedValue(makeBatchResponse(FAKE_SERIES));
}

beforeEach(() => {
	vi.clearAllMocks();
});

describe('MetricsPanel', () => {
	it('renders 4 base charts for non-GPU instance', async () => {
		mockAllMetrics();

		render(MetricsPanel, { props: { instanceId: 'inst-1', isGpu: false } });

		expect(await screen.findByText('CPU 사용률')).toBeTruthy();
		expect(await screen.findByText('메모리 사용률')).toBeTruthy();
		expect(await screen.findByText('네트워크 I/O')).toBeTruthy();
		expect(await screen.findByText('디스크 I/O')).toBeTruthy();
	});

	it('renders 6 charts for GPU instance', async () => {
		mockAllMetrics();

		render(MetricsPanel, { props: { instanceId: 'inst-gpu', isGpu: true } });

		expect(await screen.findByText('CPU 사용률')).toBeTruthy();
		expect(await screen.findByText('GPU 사용률')).toBeTruthy();
		expect(await screen.findByText('GPU 메모리')).toBeTruthy();
	});

	it('shows empty state when series is empty', async () => {
		mockGet.mockResolvedValue(makeBatchResponse([]));

		render(MetricsPanel, { props: { instanceId: 'inst-1', isGpu: false } });

		const msgs = await screen.findAllByText(/메트릭 없음/);
		expect(msgs.length).toBeGreaterThan(0);
	});

	it('shows error message on API failure', async () => {
		mockGet.mockRejectedValue(new Error('503 Prometheus 연결 불가'));

		render(MetricsPanel, { props: { instanceId: 'inst-1', isGpu: false } });

		const errs = await screen.findAllByText(/Prometheus/);
		expect(errs.length).toBeGreaterThan(0);
	});

	it('range toggle buttons are rendered including 7d', async () => {
		mockAllMetrics();

		render(MetricsPanel, { props: { instanceId: 'inst-1', isGpu: false } });

		expect(await screen.findByText('15분')).toBeTruthy();
		expect(screen.getByText('1시간')).toBeTruthy();
		expect(screen.getByText('6시간')).toBeTruthy();
		expect(screen.getByText('24시간')).toBeTruthy();
		expect(screen.getByText('7일')).toBeTruthy();
	});

	it('shows min/avg/max stats row when summary data is available', async () => {
		mockGet.mockImplementation((url: string) => {
			if (url.includes('metrics-summary')) {
				return Promise.resolve({
					prometheus_available: true,
					stats: {
						cpu: { min: 1.0, avg: 4.5, max: 31.0 },
						memory: { min: 10.0, avg: 15.0, max: 22.0 },
						disk_read: { min: 0, avg: 1024, max: 5000 },
						disk_write: { min: 0, avg: 512, max: 3000 },
					},
					recommendation: null,
				});
			}
			return Promise.resolve(makeBatchResponse(FAKE_SERIES));
		});

		render(MetricsPanel, { props: { instanceId: 'inst-1', isGpu: false } });

		// 차트 카드 하단 통계 행의 "최소" 레이블이 렌더되어야 함
		const minLabels = await screen.findAllByText(/최소/);
		expect(minLabels.length).toBeGreaterThan(0);

		const avgLabels = await screen.findAllByText(/평균/);
		expect(avgLabels.length).toBeGreaterThan(0);
	});

	it('clicking a range button triggers reload', async () => {
		mockAllMetrics();

		render(MetricsPanel, { props: { instanceId: 'inst-1', isGpu: false } });

		await screen.findByText('CPU 사용률');
		const callsBefore = mockGet.mock.calls.length;

		fireEvent.click(screen.getByText('6시간'));

		// after range change, API is called again with new range
		await screen.findByText('CPU 사용률');
		expect(mockGet.mock.calls.length).toBeGreaterThan(callsBefore);
		const urls: string[] = mockGet.mock.calls.map((c: unknown[]) => c[0] as string);
		expect(urls.some(u => u.includes('range=6h'))).toBe(true);
	});

	it('preserves plotted series nodes while a new range replaces their measured data', async () => {
		mockAllMetrics();
		const { container } = render(MetricsPanel, { props: { instanceId: 'inst-1', isGpu: false } });
		await waitFor(() => expect(container.querySelectorAll('polyline').length).toBeGreaterThan(0));
		const plot = container.querySelector('polyline');
		const originalPoints = plot?.getAttribute('points');
		mockGet.mockResolvedValue(makeBatchResponse([
			{ ts: 1700000000, value: 10 }, { ts: 1700000030, value: 80 },
		]));
		await fireEvent.click(screen.getByText('6시간'));
		await waitFor(() => expect(plot?.getAttribute('points')).not.toBe(originalPoints));
		expect(container.querySelector('polyline')).toBe(plot);
	});

	it('does not replay draw-in when a measured series returns after an empty refresh', async () => {
		mockAllMetrics();
		const { container } = render(MetricsPanel, { props: { instanceId: 'inst-1', isGpu: false } });
		await waitFor(() => expect(container.querySelector('polyline')?.classList.contains('motion-draw')).toBe(true));
		const dashed = container.querySelector('polyline[stroke-dasharray]');
		expect(dashed?.getAttribute('stroke-dasharray')).toBe('4 2');
		expect(dashed?.classList.contains('motion-draw')).toBe(false);
		mockGet.mockResolvedValue(makeBatchResponse([]));
		await fireEvent.click(screen.getByText('6시간'));
		await waitFor(() => expect(container.querySelector('polyline')).toBeNull());
		mockAllMetrics();
		await fireEvent.click(screen.getByText('24시간'));
		await waitFor(() => expect(container.querySelector('polyline')).not.toBeNull());
		expect(container.querySelector('polyline')?.classList.contains('motion-draw')).toBe(false);
		expect(container.querySelector('polyline[stroke-dasharray]')?.getAttribute('stroke-dasharray')).toBe('4 2');
	});
});
