import { render } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import type { AdminQuotasController, FlavorReconcileResponse } from '../adminQuotasController.svelte';
import type { GpuQuota, Quotas, QuotaUpdateResponse } from '$lib/types/quotas';
import Probe from './_AdminQuotasControllerProbe.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), metadata: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, put: mocks.put, delete: mocks.delete },
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { loadMetadata: mocks.metadata } }));

const projects = [
	{ id: 'p-a', name: 'Same name', domain_id: 'd-a' },
	{ id: 'p-b', name: 'Same name', domain_id: 'd-b' },
	{ id: 'p-unknown', name: 'Unknown domain' },
];
const quota: Quotas = { compute: { cores: { limit: 8, in_use: 2 } }, volume: null, network: null, file_storage: null };
const gpu: GpuQuota[] = [{ gpu_type: 'gpu-a', limit: 2, in_use: 1, available: 1 }];
const preview: FlavorReconcileResponse = { project_id: 'p-a', applied: false, status: 'ok', operations: [], errors: [], enforcement_scope: 'project' };
const saved: QuotaUpdateResponse = { status: 'updated', updated: ['compute'], errors: {} };
const initialAuth = get(auth);

async function setup() {
	let controller!: AdminQuotasController;
	const view = render(Probe, {
		source: { token: 'token-a', projectId: 'admin-project' },
		onReady: value => { controller = value; },
	});
	await vi.waitFor(() => expect(controller).toBeDefined());
	await controller.loadProjects();
	return { controller, view };
}

describe('admin quota independent domain and project scope', () => {
	beforeEach(() => {
		vi.resetAllMocks();
		projectSwitching.set(false); logoutInProgress.set(false);
		auth.set({ ...initialAuth, token: 'token-a', userId: 'admin', projectId: 'admin-project', sessionId: 'session-a', isSystemAdmin: true });
		mocks.metadata.mockResolvedValue({ projects, failed: false });
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/domains') return Promise.resolve({ items: [{ id: 'd-a', name: 'Domain A', enabled: true }, { id: 'd-b', name: 'Domain B', enabled: true }] });
			if (path.includes('/gpu-quotas/')) return Promise.resolve(gpu);
			return Promise.resolve(quota);
		});
		mocks.post.mockResolvedValue(preview);
		mocks.put.mockResolvedValue(saved);
		mocks.delete.mockResolvedValue(undefined);
	});

	it('starts in all domains and restricts projects by domain_id, never display name', async () => {
		const { controller } = await setup();
		await controller.loadDomains();
		expect(mocks.metadata).toHaveBeenCalledWith('token-a', 'admin-project', undefined);
		expect(controller.selectedDomainId).toBe('');
		expect(controller.domains.map(domain => domain.id)).toEqual(['d-a', 'd-b']);
		expect(controller.projects).toEqual(projects);
		controller.selectedDomainId = 'd-a';
		expect(controller.projects.map(project => project.id)).toEqual(['p-a']);
		controller.selectedProjectId = 'p-b';
		expect(controller.selectedProjectId).toBe('');
		controller.selectedProjectId = 'p-unknown';
		expect(controller.selectedProjectId).toBe('');
		controller.selectedProjectId = 'p-a';
		controller.selectedDomainId = 'd-b';
		expect(controller.selectedProjectId).toBe('');
		expect(controller.projects.map(project => project.id)).toEqual(['p-b']);
		controller.selectedDomainId = '';
		expect(controller.projects).toEqual(projects);
	});

	it('clears quotas, GPU results, reconcile and save feedback synchronously on domain change even for a compatible project', async () => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		await controller.loadGpuQuotas();
		await controller.loadReconcilePreview();
		await controller.saveSectionQuotas('compute', { cores: 16 });
		expect(controller.quotas).not.toBeNull();
		expect(controller.gpuQuotas).toHaveLength(1);
		expect(controller.reconcilePreview).not.toBeNull();
		expect(controller.saveSuccess).toBeTruthy();
		controller.selectedDomainId = 'd-a';
		expect(controller.selectedProjectId).toBe('p-a');
		expect(controller.quotas).toBeNull();
		expect(controller.gpuQuotas).toEqual([]);
		expect(controller.reconcilePreview).toBeNull();
		expect(controller.saveSuccess).toBe('');
		expect(controller.sectionSuccesses).toEqual({});
		expect(controller.sectionErrors).toEqual({});
		expect(controller.gpuQuotaError).toBe('');
		expect(controller.saving).toBe(false);
	});

	it('clears old project data before a new quota response arrives', async () => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		await controller.loadGpuQuotas();
		const pending = Promise.withResolvers<Quotas>();
		mocks.get.mockImplementation((path: string) => path.includes('/gpu-quotas/') ? Promise.resolve([]) : pending.promise);
		controller.selectedProjectId = 'p-b';
		expect(controller.quotas).toBeNull();
		expect(controller.gpuQuotas).toEqual([]);
		expect(controller.reconcilePreview).toBeNull();
		const loading = controller.loadQuotas();
		expect(controller.quotaLoading).toBe(true);
		pending.resolve({ ...quota, project_id: 'p-b' });
		await loading;
		expect(controller.quotas?.project_id).toBe('p-b');
	});

	it('rejects late quota, GPU, reconcile and save responses after project A→B→A', async () => {
		const { controller } = await setup();
		const oldQuota = Promise.withResolvers<Quotas>();
		const oldGpu = Promise.withResolvers<GpuQuota[]>();
		const oldPreview = Promise.withResolvers<FlavorReconcileResponse>();
		const oldSave = Promise.withResolvers<QuotaUpdateResponse>();
		mocks.get.mockImplementation((path: string) => path.includes('/gpu-quotas/') ? oldGpu.promise : oldQuota.promise);
		mocks.post.mockReturnValue(oldPreview.promise);
		mocks.put.mockReturnValue(oldSave.promise);
		controller.selectedProjectId = 'p-a';
		const loading = controller.loadQuotas();
		const reconciling = controller.loadReconcilePreview();
		const saving = controller.saveSectionQuotas('compute', { cores: 16 });
		controller.selectedProjectId = 'p-b';
		controller.selectedProjectId = 'p-a';
		oldQuota.resolve(quota); oldGpu.resolve(gpu); oldPreview.resolve(preview); oldSave.resolve(saved);
		await Promise.all([loading, reconciling, saving]);
		expect(controller.quotas).toBeNull();
		expect(controller.gpuQuotas).toEqual([]);
		expect(controller.reconcilePreview).toBeNull();
		expect(controller.saveSuccess).toBe('');
		expect(controller.saving).toBe(false);
	});

	it('rejects old GPU mutation completions after a domain A→B→A without issuing a new read', async () => {
		const { controller } = await setup();
		const write = Promise.withResolvers<void>();
		const clear = Promise.withResolvers<void>();
		mocks.put.mockReturnValue(write.promise); mocks.delete.mockReturnValue(clear.promise);
		controller.selectedDomainId = 'd-a'; controller.selectedProjectId = 'p-a';
		const writing = controller.setGpuQuota('gpu-a', 3);
		const clearing = controller.deleteGpuQuota('gpu-a');
		controller.selectedDomainId = 'd-b';
		controller.selectedDomainId = 'd-a'; controller.selectedProjectId = 'p-a';
		const calls = mocks.get.mock.calls.length;
		write.resolve(); clear.resolve();
		await Promise.all([writing, clearing]);
		expect(mocks.get).toHaveBeenCalledTimes(calls);
		expect(controller.gpuQuotas).toEqual([]);
		expect(controller.gpuQuotaError).toBe('');
	});

	it('clears synchronously and rejects late responses across same-tick auth A→B→A', async () => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		const oldQuota = Promise.withResolvers<Quotas>();
		const oldGpu = Promise.withResolvers<GpuQuota[]>();
		const oldPreview = Promise.withResolvers<FlavorReconcileResponse>();
		mocks.get.mockImplementation((path: string) => path.includes('/gpu-quotas/') ? oldGpu.promise : oldQuota.promise);
		mocks.post.mockReturnValue(oldPreview.promise);
		const loading = controller.loadQuotas();
		const reconciling = controller.loadReconcilePreview();
		const original = get(auth);
		auth.set({ ...original, sessionId: 'session-b', token: 'token-b' });
		expect(controller.quotas).toBeNull();
		expect(controller.selectedProjectId).toBe('');
		expect(controller.projects).toEqual([]);
		auth.set(original);
		controller.selectedProjectId = 'p-a';
		oldQuota.resolve(quota); oldGpu.resolve(gpu); oldPreview.resolve(preview);
		await Promise.all([loading, reconciling]);
		expect(controller.quotas).toBeNull();
		expect(controller.gpuQuotas).toEqual([]);
		expect(controller.reconcilePreview).toBeNull();
	});

	it('preserves the directory, selected project and loaded quotas during same-session bearer rotation', async () => {
		const { controller } = await setup();
		controller.selectedDomainId = 'd-a'; controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		const revision = controller.scopeRevision;
		auth.update(state => ({ ...state, token: 'refreshed-bearer' }));
		expect(controller.scopeRevision).toBe(revision);
		expect(controller.selectedDomainId).toBe('d-a');
		expect(controller.selectedProjectId).toBe('p-a');
		expect(controller.projects.map(project => project.id)).toEqual(['p-a']);
		expect(controller.quotas).toEqual(quota);
	});

	it('refreshes global GPU defaults after a successful write even when the project scope changes', async () => {
		const { controller } = await setup();
		const write = Promise.withResolvers<void>();
		mocks.put.mockReturnValueOnce(write.promise);
		mocks.get.mockImplementation((path: string) => path === '/api/v1/admin/gpu-quotas/defaults'
			? Promise.resolve([{ gpu_type: 'gpu-a', limit: 5 }]) : Promise.resolve([]));
		controller.selectedProjectId = 'p-a';
		const writing = controller.setGpuDefault('gpu-a', 5);
		controller.selectedDomainId = 'd-b'; controller.selectedProjectId = 'p-b';
		write.resolve(); await writing;
		expect(controller.gpuDefaultMap).toEqual({ 'gpu-a': 5 });
		expect(controller.gpuDefaultSuccess).toBeTruthy();
		expect(mocks.get).not.toHaveBeenCalledWith('/api/v1/admin/gpu-quotas/p-b', expect.anything(), expect.anything());
	});

	it.each([projectSwitching, logoutInProgress])('clears results when a session transition starts', async transition => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		transition.set(true);
		expect(controller.quotas).toBeNull();
		expect(controller.selectedProjectId).toBe('');
		expect(controller.gpuQuotas).toEqual([]);
		transition.set(false);
	});

	it('keeps failed project metadata distinct from a successful empty directory', async () => {
		mocks.metadata.mockResolvedValueOnce({ projects: [], failed: true });
		const { controller } = await setup();
		expect(controller.projects).toEqual([]);
		expect(controller.projectsError).toBeTruthy();
		mocks.metadata.mockResolvedValueOnce({ projects: [], failed: false });
		await controller.loadProjects();
		expect(controller.projectsError).toBe('');
		expect(controller.loading).toBe(false);
	});
});
