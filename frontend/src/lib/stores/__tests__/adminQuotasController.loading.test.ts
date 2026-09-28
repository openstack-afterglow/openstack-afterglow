import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import type { createAdminQuotasController } from '../adminQuotasController.svelte';

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mockGet, put: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error { status = 500; },
}));

import Probe from './_AdminQuotasControllerProbe.svelte';
type Controller = ReturnType<typeof createAdminQuotasController>;

describe('admin quota loading graph', () => {
	it('starts project and GPU quotas together, releases them independently, and fences stale rounds', async () => {
		const oldQuota = Promise.withResolvers<unknown>();
		const oldGpu = Promise.withResolvers<unknown[]>();
		const newQuota = Promise.withResolvers<unknown>();
		const newGpu = Promise.withResolvers<unknown[]>();
		const quotas = [oldQuota, newQuota];
		const gpu = [oldGpu, newGpu];
		mockGet.mockImplementation((path: string) => path.includes('/gpu-quotas/')
			? gpu.shift()!.promise
			: quotas.shift()!.promise);
		let controller: Controller | null = null;
		render(Probe, {
			source: { token: 'token', projectId: 'admin-project' },
			onReady: (value) => { controller = value; },
		});
		await vi.waitFor(() => expect(controller).not.toBeNull());
		controller!.selectedProjectId = 'target-project';

		void controller!.loadQuotas();
		expect(mockGet).toHaveBeenCalledTimes(2);
		const latest = controller!.loadQuotas();
		expect(mockGet).toHaveBeenCalledTimes(4);

		newQuota.resolve({ marker: 'new' });
		await vi.waitFor(() => expect(screen.getByTestId('quota-value').textContent).toContain('new'));
		expect(screen.getByTestId('quota-loading').textContent).toBe('ready');
		expect(screen.getByTestId('gpu-loading').textContent).toBe('loading');
		newGpu.resolve([{ gpu_type: 'gpu-a', limit: 1 }]);
		await latest;
		await vi.waitFor(() => expect(screen.getByTestId('gpu-count').textContent).toBe('1'));

		oldQuota.resolve({ marker: 'old' });
		oldGpu.resolve([]);
		await Promise.resolve();
		expect(screen.getByTestId('quota-value').textContent).toContain('new');
	});
	it('lets a newer background GPU round settle an older foreground loading state', async () => {
		const foregroundGpu = Promise.withResolvers<unknown[]>();
		const backgroundGpu = Promise.withResolvers<unknown[]>();
		mockGet.mockReset()
			.mockReturnValueOnce(foregroundGpu.promise)
			.mockReturnValueOnce(backgroundGpu.promise);
		let controller: Controller | null = null;
		render(Probe, {
			source: { token: 'token', projectId: 'admin-project' },
			onReady: (value) => { controller = value; },
		});
		await vi.waitFor(() => expect(controller).not.toBeNull());
		controller!.selectedProjectId = 'target-project';

		const foreground = controller!.loadGpuQuotas();
		expect(controller!.gpuQuotaLoading).toBe(true);
		const background = controller!.loadGpuQuotas({ background: true });

		foregroundGpu.resolve([{ gpu_type: 'old-gpu', limit: 1 }]);
		await foreground;
		expect(controller!.gpuQuotaLoading).toBe(true);
		backgroundGpu.resolve([{ gpu_type: 'new-gpu', limit: 2 }]);
		await background;

		await vi.waitFor(() => expect(screen.getByTestId('gpu-loading').textContent).toBe('ready'));
		expect(controller!.gpuQuotas).toHaveLength(1);
	});

});
