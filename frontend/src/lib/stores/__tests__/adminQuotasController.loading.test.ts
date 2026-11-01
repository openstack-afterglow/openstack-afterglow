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
	it('loads native project quotas without legacy GPU requests and fences stale rounds', async () => {
		const oldQuota = Promise.withResolvers<unknown>();
		const newQuota = Promise.withResolvers<unknown>();
		const quotas = [oldQuota, newQuota];
		mockGet.mockImplementation(() => quotas.shift()!.promise);
		let controller: Controller | null = null;
		render(Probe, {
			source: { token: 'token', projectId: 'admin-project' },
			onReady: (value) => { controller = value; },
		});
		await vi.waitFor(() => expect(controller).not.toBeNull());
		controller!.selectedProjectId = 'target-project';

		void controller!.loadQuotas();
		expect(mockGet).toHaveBeenCalledTimes(1);
		const latest = controller!.loadQuotas();
		expect(mockGet).toHaveBeenCalledTimes(2);

		newQuota.resolve({ marker: 'new' });
		await vi.waitFor(() => expect(screen.getByTestId('quota-value').textContent).toContain('new'));
		expect(screen.getByTestId('quota-loading').textContent).toBe('ready');
		await latest;

		oldQuota.resolve({ marker: 'old' });
		await Promise.resolve();
		expect(screen.getByTestId('quota-value').textContent).toContain('new');
	});

});
