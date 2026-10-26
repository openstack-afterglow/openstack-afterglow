import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import { initLocale, intlLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/instance';

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE: 'http://localhost:8000' } }));

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet },
}));


vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'test-token', projectId: 'test-project', userId: 'test-user' }),
}));

vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: (_fn: unknown, _opts: unknown) => ({
		active: false,
		intervalSeconds: 30,
		intervalOptions: [15, 30, 60],
	}),
}));

import MetricsPanel from '../MetricsPanel.svelte';
import { auth } from '$lib/stores/auth';

// Fake series data
const FAKE_SERIES = [
	{ ts: 1700000000, value: 42.0 },
	{ ts: 1700000030, value: 45.0 },
];

const ALL_METRIC_KEYS = ['cpu', 'memory', 'network_rx', 'network_tx', 'disk_read', 'disk_write', 'gpu_util', 'gpu_mem'];

interface BatchFixture {
	metrics: Record<string, { series: { ts: number; value: number | null }[]; error: string | null; source: string | null; unit: string; status: string; native_status: string | null }>;
}
function makeBatchResponse(series: { ts: number; value: number | null }[]): BatchFixture {
	const metrics: BatchFixture['metrics'] = {};
	for (const k of ALL_METRIC_KEYS) metrics[k] = { series, error: null, source: 'gnocchi', unit: k.startsWith('network_') || k.startsWith('disk_') ? 'B/s' : '%', status: series.length ? 'available' : 'not_collected', native_status: series.length ? 'available' : 'not_collected' };
	return { metrics };
}

function mockAllMetrics() {
	mockGet.mockResolvedValue(makeBatchResponse(FAKE_SERIES));
}

beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
	auth.update((state) => ({ ...state, token: 'test-token', projectId: 'test-project', userId: 'test-user' }));
});

describe('MetricsPanel', () => {
	it('uses explicit admin metrics paths while preserving caller-native telemetry project', async () => {
		mockAllMetrics();
		render(MetricsPanel, { instanceId: 'foreign-vm', projectId: 'foreign-project', adminMode: true });
		await waitFor(() => expect(mockGet.mock.calls.some(([path]) => path.startsWith('/api/v1/admin/instances/foreign-vm/metrics-batch?'))).toBe(true));
		expect(mockGet).toHaveBeenCalledWith('/api/v1/admin/instances/foreign-vm/metrics-summary?range=1h', 'test-token', 'test-project');
		expect(mockGet.mock.calls.every(([path, , project]) => path.startsWith('/api/v1/admin/') && project === 'test-project')).toBe(true);
	});
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
					monitoring_available: true,
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


	it('exposes independently timed measurements with explicit gaps and byte-rate units', async () => {
		const batch = makeBatchResponse(FAKE_SERIES);
		batch.metrics.network_rx.series = [
			{ ts: 1700000000, value: 1024 },
			{ ts: 1700000060, value: null },
			{ ts: 1700000090, value: 2048 },
		];
		batch.metrics.network_tx.series = [
			{ ts: 1700000030, value: 512 },
			{ ts: 1700000090, value: 768 },
		];
		mockGet.mockResolvedValue(batch);
		render(MetricsPanel, { props: { instanceId: 'inst-1' } });
		const chart = await screen.findByRole('group', { name: '네트워크 I/O' });
		const details = chart.querySelector('details')!;
		details.open = true;
		await fireEvent(details, new Event('toggle'));
		const values = [...chart.querySelectorAll('tbody tr')].map(row => [...row.querySelectorAll('td')].map(cell => cell.textContent));
		expect(values).toEqual([
			['1.0KB/s', '—'], ['—', '512B/s'], ['—', '—'], ['2.0KB/s', '768B/s'],
		]);
	});

	it('keeps full localized dates in metric details when the same clock time occurs on different days', async () => {
		const samples = [{ ts: 1700000000, value: 0 }, { ts: 1700086400, value: 10 }];
		mockGet.mockResolvedValue(makeBatchResponse(samples));
		render(MetricsPanel, { props: { instanceId: 'inst-1' } });
		const chart = await screen.findByRole('group', { name: t('metrics.cpuUsage') });
		const details = chart.querySelector('details')!;
		details.open = true;
		await fireEvent(details, new Event('toggle'));
		const timestamps = within(chart).getAllByRole('rowheader').map(cell => cell.textContent);
		expect(timestamps).toEqual(samples.map(sample => new Date(sample.ts * 1000).toLocaleString(intlLocale())));
		expect(new Set(timestamps).size).toBe(2);
	});

	it('distinguishes native zero, fallback, uncollected and native capacity units', async () => {
		const batch = makeBatchResponse([{ ts: 1700000000, value: 0 }]);
		batch.metrics.memory = { series: [], error: null, source: 'gnocchi', unit: '%', status: 'not_collected', native_status: 'not_collected' };
		batch.metrics.disk_read = { ...batch.metrics.disk_read, source: 'libvirt', native_status: 'forbidden' };
		batch.metrics.memory_resident = { ...batch.metrics.cpu, series: [{ ts: 1700000000, value: 512 }], unit: 'MiB' };
		batch.metrics.disk_allocation = { ...batch.metrics.cpu, series: [{ ts: 1700000000, value: 8192 }], unit: 'B' };
		mockGet.mockImplementation((url: string) => Promise.resolve(url.includes('metrics-summary') ? { monitoring_available: true, stats: {} } : batch));
		render(MetricsPanel, { props: { instanceId: 'inst-1' } });
		expect(await screen.findAllByText(/gnocchi · 사용 가능/)).not.toHaveLength(0);
		expect(await screen.findByText(/libvirt · Exporter 대체 소스.*Gnocchi: 권한 없음/)).toBeTruthy();
		expect(screen.getByText(/gnocchi · 미수집 · %/)).toBeTruthy();
		expect(screen.queryByRole('group', { name: t('metrics.memoryUsage') })).toBeNull();
		const cpu = await screen.findByRole('group', { name: t('metrics.cpuUsage') });
		const cpuData = cpu.querySelector('details')!;
		cpuData.open = true;
		await fireEvent(cpuData, new Event('toggle'));
		expect(within(cpu).getAllByText('0.0%').length).toBeGreaterThan(0);
		await fireEvent.click(screen.getByRole('button', { name: t('metrics.nativeMeasurements') }));
		for (const [label, value] of [[t('metrics.memoryResident'), '512.0 MiB'], [t('metrics.diskAllocation'), '8192.0 B']]) {
			const chart = await screen.findByRole('group', { name: label });
			const data = chart.querySelector('details')!;
			data.open = true;
			await fireEvent(data, new Event('toggle'));
			expect(within(chart).getByRole('cell', { name: value })).toBeTruthy();
		}
		expect(screen.queryByText('8192.0 B/s')).toBeNull();
		expect(screen.getAllByText(/Gnocchi: 미수집/).length).toBeGreaterThan(0);
	});

	it('keeps a readable empty native meter uncollected when fallback monitoring is offline', async () => {
		const batch = makeBatchResponse([]);
		batch.metrics.memory.error = 'prometheus_unavailable';
		mockGet.mockResolvedValue(batch);
		render(MetricsPanel, { props: { instanceId: 'inst-1' } });
		expect(await screen.findAllByText(/gnocchi · 미수집/)).not.toHaveLength(0);
		expect(screen.queryByText('prometheus_unavailable')).toBeNull();
		expect(screen.getAllByText(t('metrics.empty')).length).toBeGreaterThan(0);
	});

	it.each(['instance', 'project', 'identity', 'token', 'projectAba', 'range'] as const)('discards late chart and summary after %s context changes', async (context) => {
		const oldBatch = Promise.withResolvers<BatchFixture>();
		const oldSummary = Promise.withResolvers<unknown>();
		let previous = true;
		const current = makeBatchResponse([{ ts: 1700000000, value: 22.7 }]);
		current.metrics.cpu.source = 'current-source';
		mockGet.mockImplementation((url: string) => {
			if (previous) return url.includes('metrics-summary') ? oldSummary.promise : oldBatch.promise;
			return Promise.resolve(url.includes('metrics-summary') ? { monitoring_available: true, stats: {} } : current);
		});
		const view = render(MetricsPanel, { props: { instanceId: 'inst-1' } });
		await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2));
		previous = false;
		if (context === 'instance') await view.rerender({ instanceId: 'inst-2' });
		else if (context === 'range') await fireEvent.click(screen.getByText('6시간'));
		else if (context === 'token') auth.update((state) => ({ ...state, token: 'new-token' }));
		else if (context === 'projectAba') {
			auth.update((state) => ({ ...state, projectId: 'project-b' }));
			auth.update((state) => ({ ...state, projectId: 'test-project' }));
		}
		else auth.update((state) => ({ ...state, ...(context === 'project' ? { projectId: 'project-b' } : { userId: 'user-b' }) }));
		expect(await screen.findByText(/current-source/)).toBeTruthy();
		const stale = makeBatchResponse([{ ts: 1700000000, value: 91.3 }]);
		stale.metrics.cpu.source = 'old-private-source';
		oldBatch.resolve(stale);
		oldSummary.resolve({ monitoring_available: true, stats: { cpu: { min: 91.3, avg: 91.3, max: 91.3, source: 'old-private-summary', unit: '%' } } });
		await tick();
		await tick();
		expect(screen.queryByText(/old-private/)).toBeNull();
		expect(screen.queryByText('91.3%')).toBeNull();
		expect(screen.getByText(/current-source/)).toBeTruthy();
	});
});
