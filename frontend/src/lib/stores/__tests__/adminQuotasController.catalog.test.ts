import { render } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GpuQuota } from '$lib/types/quotas';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mocks.get,
		post: mocks.post,
		put: vi.fn(),
		delete: vi.fn(),
	},
	ApiError: class ApiError extends Error { status = 500; },
}));

import Probe from './_AdminQuotasControllerProbe.svelte';
interface QuotaCatalogController {
	selectedProjectId: string;
	readonly gpuQuotaRows: GpuQuota[];
	loadGpuAliases: () => Promise<void>;
	loadGpuDefaults: () => Promise<void>;
	loadGpuQuotas: () => Promise<void>;
}

describe('admin GPU quota catalog', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.post.mockResolvedValue({ operations: [], errors: [] });
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/gpu-aliases') {
				return Promise.resolve({ aliases: ['GTX1080TI', 'RTX3090', 'RTX4090'] });
			}
			if (path === '/api/v1/admin/gpu-quotas/defaults') {
				return Promise.resolve([
					{ gpu_type: 'GTX1080TI', limit: -1 },
					{ gpu_type: 'RTX3090', limit: 0 },
				]);
			}
			if (path === '/api/v1/admin/gpu-quotas/target-project') {
				return Promise.resolve([
					{ gpu_type: 'GTX1080TI', limit: 0, in_use: 0, available: 0 },
					{ gpu_type: 'RTX3060', limit: 2, in_use: 1, available: 1 },
				]);
			}
			throw new Error(`Unexpected request: ${path}`);
		});
	});

	it('offers every cluster alias even when the selected project has no stored quota or usage', async () => {
		let controller: QuotaCatalogController | null = null;
		render(Probe, {
			source: { token: 'token', projectId: 'admin-project' },
			onReady: (value) => { controller = value; },
		});
		await vi.waitFor(() => expect(controller).not.toBeNull());
		controller!.selectedProjectId = 'target-project';

		await Promise.all([
			controller!.loadGpuAliases(),
			controller!.loadGpuDefaults(),
			controller!.loadGpuQuotas(),
		]);

		expect(controller!.gpuQuotaRows).toEqual([
			{ gpu_type: 'GTX1080TI', limit: 0, in_use: 0, available: 0 },
			{ gpu_type: 'RTX3060', limit: 2, in_use: 1, available: 1 },
			{ gpu_type: 'RTX3090', limit: 0, in_use: 0, available: 0 },
			{ gpu_type: 'RTX4090', limit: 0, in_use: 0, available: 0 },
		]);
	});
});
