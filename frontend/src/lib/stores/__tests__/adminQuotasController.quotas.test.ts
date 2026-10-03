import { render } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AdminQuotasController } from '../adminQuotasController.svelte';
import type { QuotaUpdateResponse } from '$lib/types/quotas';
import Probe from './_AdminQuotasControllerProbe.svelte';

const mocks = vi.hoisted(() => ({
	get: vi.fn(),
	post: vi.fn(),
	put: vi.fn(),
	delete: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	api: {
		get: mocks.get,
		post: mocks.post,
		put: mocks.put,
		delete: mocks.delete,
	},
	ApiError: class ApiError extends Error {
		status = 500;
		constructor(message: string) {
			super(message);
		}
	},
}));

type QuotaController = AdminQuotasController;

describe('adminQuotasController quotas management', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mocks.post.mockResolvedValue({ operations: [], errors: [] });
		mocks.get.mockImplementation((path: string) => {
			if (path.startsWith('/api/v1/admin/gpu-quotas/')) {
				return Promise.resolve([]);
			}
			if (path.startsWith('/api/v1/admin/quotas/')) {
				return Promise.resolve({
					compute: { instances: { limit: 10, in_use: 2 } },
					volume: { volumes: { limit: 5, in_use: 1 }, snapshots: { limit: 10, in_use: 2 }, gigabytes: { limit: 100, in_use: 20 } },
					network: { floatingip: { limit: 5, in_use: 1 } },
					file_storage: { shares: { limit: 3, in_use: 0 }, gigabytes: { limit: 200, in_use: 10 } },
					errors: {},
				});
			}
			return Promise.resolve({});
		});
	});

	async function setupController(): Promise<QuotaController> {
		let ctrl: QuotaController | null = null;
		render(Probe, {
			source: { token: 'token-1', projectId: 'admin-proj' },
			onReady: (val) => {
				ctrl = val;
			},
		});
		await vi.waitFor(() => expect(ctrl).not.toBeNull());
		return ctrl!;
	}

	it('saveSectionQuotas sends flat Manila keys and preserves status after refetch', async () => {
		const controller = await setupController();
		controller.selectedProjectId = 'target-p1';
		await controller.loadQuotas();

		mocks.put.mockResolvedValueOnce({
			status: 'updated',
			updated: ['file_storage'],
			errors: {},
		});

		const result = await controller.saveSectionQuotas('file_storage', {
			share_gigabytes: 500,
			share_snapshots: 15,
		});

		expect(mocks.put).toHaveBeenCalledWith(
			'/api/v1/admin/quotas/target-p1',
			{
				share_gigabytes: 500,
				share_snapshots: 15,
			},
			'token-1',
			'admin-proj',
		);

		expect(result.success).toBe(true);
		expect(controller.saveSuccess).toBe('저장되었습니다');
		expect(controller.sectionSuccesses.file_storage).toBe('저장되었습니다');
		expect(controller.saveError).toBe('');
	});

	it('saveSectionQuotas for volume sends snapshots directly and succeeds', async () => {
		const controller = await setupController();
		controller.selectedProjectId = 'target-p1';
		await controller.loadQuotas();

		mocks.put.mockResolvedValueOnce({
			status: 'updated',
			updated: ['volume'],
			errors: {},
		});

		const result = await controller.saveSectionQuotas('volume', {
			snapshots: 25,
		});

		expect(mocks.put).toHaveBeenCalledWith(
			'/api/v1/admin/quotas/target-p1',
			{ snapshots: 25 },
			'token-1',
			'admin-proj',
		);
		expect(result.success).toBe(true);
		expect(controller.sectionSuccesses.volume).toBe('저장되었습니다');
	});

	it('reports a provider success even when another provider made the overall response partial', async () => {
		const controller = await setupController();
		controller.selectedProjectId = 'target-p1';
		mocks.put.mockResolvedValueOnce({
			status: 'partial',
			updated: ['compute'],
			errors: { volume: 'Cinder unavailable' },
		});

		const result = await controller.saveSectionQuotas('compute', { cores: 32 });

		expect(result.success).toBe(true);
		expect(controller.sectionSuccesses.compute).toBe('저장되었습니다');
		expect(controller.sectionErrors.compute).toBeUndefined();
		expect(controller.quotas?.compute?.instances?.in_use).toBe(2);
	});

	it('keeps provider write success distinct from a failed quota refetch', async () => {
		const controller = await setupController();
		controller.selectedProjectId = 'target-p1';
		mocks.get.mockImplementation((path: string) =>
			path === '/api/v1/admin/quotas/target-p1'
				? Promise.reject(new Error('read failed'))
				: Promise.resolve([]),
		);
		mocks.put.mockResolvedValueOnce({ status: 'updated', updated: ['compute'], errors: {} });

		const result = await controller.saveSectionQuotas('compute', { cores: 32 });

		expect(result).toMatchObject({ success: true, refreshed: false });
		expect(controller.saveSuccess).toBe('');
		expect(controller.sectionSuccesses.compute).toBeUndefined();
		expect(controller.sectionErrors.compute).toBe('쿼터를 다시 불러올 수 없습니다. 다시 시도해주세요.');
	});

	it('handles partial status and errors without marking success', async () => {
		const controller = await setupController();
		controller.selectedProjectId = 'target-p1';
		await controller.loadQuotas();

		mocks.put.mockResolvedValueOnce({
			status: 'partial',
			updated: [],
			errors: { network: 'Neutron floatingip allocation quota full' },
		});

		const result = await controller.saveSectionQuotas('network', {
			floatingip: 50,
		});

		expect(result.success).toBe(false);
		expect(controller.sectionErrors.network).toBe('Neutron floatingip allocation quota full');
		expect(controller.saveError).toBe('Neutron floatingip allocation quota full');
		expect(controller.sectionSuccesses.network).toBeUndefined();
		expect(controller.saveSuccess).toBe('');
	});

	it('enforces project-switch fence so in-flight responses do not leak into another project', async () => {
		const controller = await setupController();
		controller.selectedProjectId = 'target-p1';

		const { promise: putPromise, resolve: resolvePut } = Promise.withResolvers<QuotaUpdateResponse>();
		mocks.put.mockReturnValueOnce(putPromise);

		// Start saving for project p1
		const saveTask = controller.saveSectionQuotas('compute', { cores: 64 });

		// Switch project while save is in flight
		controller.selectedProjectId = 'target-p2';

		// Resolve the save for p1
		resolvePut({
			status: 'updated',
			updated: ['compute'],
			errors: {},
		});
		await saveTask;

		// Since project was switched to p2, stale response must NOT set success for p2
		expect(controller.sectionSuccesses.compute).toBeUndefined();
		expect(controller.saveSuccess).toBe('');
	});

	it('clears previous errors and success messages when selectedProjectId changes', async () => {
		const controller = await setupController();
		controller.selectedProjectId = 'target-p1';

		mocks.put.mockResolvedValueOnce({
			status: 'updated',
			updated: ['compute'],
			errors: {},
		});
		await controller.saveSectionQuotas('compute', { cores: 32 });
		expect(controller.saveSuccess).toBe('저장되었습니다');

		// Switch project
		controller.selectedProjectId = 'target-p2';

		expect(controller.saveSuccess).toBe('');
		expect(controller.saveError).toBe('');
		expect(controller.sectionSuccesses).toEqual({});
		expect(controller.sectionErrors).toEqual({});
	});
});
