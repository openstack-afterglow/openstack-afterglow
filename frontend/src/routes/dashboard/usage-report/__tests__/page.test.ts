import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { get, writable } from 'svelte/store';
import { siteConfig } from '$lib/config/site';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock('$lib/api/client', () => ({ api: { get: mockGet } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project', projectName: 'Project One' }),
	authReady: writable(true),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 300, intervalOptions: [60, 300] }),
}));

import Page from '../+page.svelte';

const trend = (overrides: Record<string, unknown> = {}) => ({
	current_pct: 28.1,
	slope_per_day: 0.57,
	projected_pct: 41.4,
	days_to_limit: null,
	trend_available: true,
	series: [30, 30, 32, 32, 34, 36, 36],
	...overrides,
});

function report(overrides: { quota?: Record<string, unknown>; forecast?: Record<string, unknown> } = {}) {
	return {
		range: '30d',
		start: '2026-08-27',
		end: '2026-09-26',
		stats: { instance_hours: 1440, vcpu_hours: 8640, ram_gb_hours: 51840, gpu_hours: 720, active_instances: 2, total_instances: 2 },
		flavor_hours: [
			{ flavor: 'cpu.4c_8g', instance_count: 1, usage_hours: 720, vcpus: 4, ram_mb: 8192, gpu_count: 0, vcpu_hours: 2880, gpu_hours: 0 },
			{ flavor: 'gpu.8c_64g_a10', instance_count: 1, usage_hours: 720, vcpus: 8, ram_mb: 65536, gpu_count: 1, vcpu_hours: 5760, gpu_hours: 720 },
		],
		instance_usage: [
			{
				instance_id: 'aaaaaaaa-1111-2222-3333-444444444444',
				name: 'train-01',
				flavor: 'gpu.8c_64g_a10',
				state: 'active',
				hours: 720,
				started_at: '2026-06-10T00:00:00+00:00',
				ended_at: null,
				vcpus: 8,
				memory_mb: 65536,
				gpu_count: 1,
			},
		],
		quota: {
			compute_available: true,
			storage_available: true,
			instances: { limit: 30, in_use: 8 },
			vcpus: { limit: 128, in_use: 36 },
			ram_mb: { limit: 262144, in_use: 86016 },
			volume_gb: { limit: 8000, in_use: 1250 },
			volumes: { limit: 60, in_use: 14 },
			gpu: [{ gpu_type: 'A10', in_use: 1, limit: 2 }],
			gpu_available: true,
			...overrides.quota,
		},
		forecast: {
			window_days: 7,
			horizon_days: 30,
			vcpus: trend({ days_to_limit: 12 }),
			ram_mb: trend({ current_pct: 32.8, slope_per_day: 1024, projected_pct: 44.5, series: [73728, 86016] }),
			volume_gb: trend({ current_pct: 15.6, slope_per_day: null, projected_pct: null, trend_available: false, series: [] }),
			gpu: { A10: trend({ current_pct: 50, slope_per_day: 0, projected_pct: 50, series: [1, 1, 1, 1, 1, 1, 1] }) },
			...overrides.forecast,
		},
	};
}

const QUOTAS = {
	compute: { instances: { limit: 30, in_use: 8 }, cores: { limit: 128, in_use: 36 }, ram: { limit: 262144, in_use: 86016 } },
	storage: { volumes: { limit: 60, in_use: 14 }, gigabytes: { limit: 8000, in_use: 1250 } },
	network: { floatingip: { limit: 16, in_use: 3 }, router: { limit: 10, in_use: 2 } },
	file_storage: { shares: { limit: 12, in_use: 4 }, gigabytes: { limit: 4096, in_use: 780 } },
};

function mockSources(usageReport: unknown, quotas: Promise<unknown>) {
	mockGet.mockImplementation((path: string) => {
		if (path.startsWith('/api/v1/dashboard/usage-report')) return Promise.resolve(usageReport);
		if (path === '/api/v1/dashboard/quotas') return quotas;
		return Promise.reject(new Error('chat unavailable'));
	});
}

describe('usage report page', () => {
	const initialSiteConfig = get(siteConfig);

	beforeEach(() => {
		mockGet.mockReset();
		siteConfig.update((config) => ({ ...config, services: { ...config.services, manila: true, swift: false, trove: false } }));
	});

	afterEach(() => {
		siteConfig.set(initialSiteConfig);
	});

	it('renders real flavors, GPU forecast rows and the project resource inventory', async () => {
		mockSources(report(), Promise.resolve(QUOTAS));

		render(Page);

		expect((await screen.findAllByText('gpu.8c_64g_a10')).length).toBeGreaterThan(0);
		expect(screen.getByText('GPU ×1')).toBeTruthy();
		expect(screen.getByText('GPU A10')).toBeTruthy();
		expect(screen.getByText(/약 12일 후 한도 도달/)).toBeTruthy();
		expect(screen.getByText('쿼터 임박')).toBeTruthy();
		expect(screen.queryByText('unknown')).toBeNull();

		const router = await screen.findByText('라우터');
		expect(router.parentElement?.textContent?.replace(/\s+/g, '')).toContain('2/10');
		expect(screen.getByText('공유')).toBeTruthy();
		// Absent optional quota keys are omitted rather than rendered as empty bars.
		expect(screen.queryByText('스냅샷')).toBeNull();
		expect(mockGet).toHaveBeenCalledWith('/api/v1/dashboard/quotas', 'token', 'project');
	});

	it('keeps the report visible when the resource inventory fails', async () => {
		mockSources(report(), Promise.reject(new Error('quota unavailable')));

		render(Page);

		expect(await screen.findByText('cpu.4c_8g')).toBeTruthy();
		expect(await screen.findByText(/프로젝트 리소스 현황을 불러오지 못했습니다/)).toBeTruthy();
	});

	it('labels unlimited quotas and resources without a trend', async () => {
		mockSources(
			report({ quota: { vcpus: { limit: -1, in_use: 36 } }, forecast: { vcpus: trend({ current_pct: null, projected_pct: null }) } }),
			Promise.resolve(QUOTAS),
		);

		render(Page);

		expect(await screen.findByText('무제한')).toBeTruthy();
		expect(screen.getByText('추세 데이터 없음')).toBeTruthy();
		expect(screen.queryByText('쿼터 임박')).toBeNull();
	});
});
