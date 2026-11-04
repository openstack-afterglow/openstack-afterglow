import { render } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import type { AdminQuotasController } from '../adminQuotasController.svelte';
import type { Quotas, QuotaUpdateResponse } from '$lib/types/quotas';
import Probe from './_AdminQuotasControllerProbe.svelte';
import type * as ExperienceModule from '$lib/utils/experience';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), metadata: vi.fn(), withExperience: vi.fn(),
	begin: vi.fn(), state: vi.fn(), applied: vi.fn(), discarded: vi.fn(),
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, put: mocks.put, delete: mocks.delete, withExperience: mocks.withExperience },
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { loadMetadata: mocks.metadata } }));
vi.mock('$lib/utils/experience', async (importOriginal) => ({
	...(await importOriginal<typeof ExperienceModule>()),
	beginExperienceAction: mocks.begin, beginExperienceLoad: mocks.begin, experienceState: mocks.state,
	experienceApplied: mocks.applied, experienceDiscarded: mocks.discarded,
}));

const projects = [
	{ id: 'p-a', name: 'Same name', domain_id: 'd-a' },
	{ id: 'p-b', name: 'Same name', domain_id: 'd-b' },
	{ id: 'p-unknown', name: 'Unknown domain' },
];
const quota: Quotas = { compute: { cores: { limit: 8, in_use: 2 } }, volume: null, network: null, file_storage: null };
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
		mocks.withExperience.mockReturnValue(mocks);
		projectSwitching.set(false); logoutInProgress.set(false);
		auth.set({ ...initialAuth, token: 'token-a', userId: 'admin', projectId: 'admin-project', sessionId: 'session-a', isSystemAdmin: true });
		mocks.metadata.mockResolvedValue({ projects, failed: false });
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/admin/domains') return Promise.resolve({ items: [{ id: 'd-a', name: 'Domain A', enabled: true }, { id: 'd-b', name: 'Domain B', enabled: true }] });
			return Promise.resolve(quota);
		});
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

	it('clears quotas and save feedback synchronously on domain change even for a compatible project', async () => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		await controller.saveSectionQuotas('compute', { cores: 16 });
		expect(controller.quotas).not.toBeNull();
		expect(controller.saveSuccess).toBeTruthy();
		controller.selectedDomainId = 'd-a';
		expect(controller.selectedProjectId).toBe('p-a');
		expect(controller.quotas).toBeNull();
		expect(controller.saveSuccess).toBe('');
		expect(controller.sectionSuccesses).toEqual({});
		expect(controller.sectionErrors).toEqual({});
		expect(controller.saving).toBe(false);
	});

	it('clears old project data before a new quota response arrives', async () => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		const pending = Promise.withResolvers<Quotas>();
		mocks.get.mockReturnValue(pending.promise);
		controller.selectedProjectId = 'p-b';
		expect(controller.quotas).toBeNull();
		const loading = controller.loadQuotas();
		expect(controller.quotaLoading).toBe(true);
		pending.resolve({ ...quota, project_id: 'p-b' });
		await loading;
		expect(controller.quotas?.project_id).toBe('p-b');
	});

	it('passes the passive directory context into metadata and domain request helpers', async () => {
		const experience = { actionId: 'directory' };
		mocks.begin.mockReturnValue(experience);
		const { controller } = await setup();
		expect(mocks.metadata).toHaveBeenCalledWith('token-a', 'admin-project', undefined, false, experience);
		await controller.loadDomains();
		expect(mocks.withExperience).toHaveBeenCalledWith(experience);
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains', 'token-a', 'admin-project');
	});

	it('records stale quota rounds as discarded and applies only the winning assignment', async () => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		const oldExperience = { actionId: 'old' }, currentExperience = { actionId: 'current' };
		mocks.begin.mockReturnValueOnce(oldExperience).mockReturnValueOnce(currentExperience);
		const pending = Promise.withResolvers<Quotas>();
		mocks.get.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(quota);
		const oldLoad = controller.loadQuotas();
		await controller.loadQuotas(); pending.resolve({ ...quota, project_id: 'obsolete-private-id' }); await oldLoad;
		expect(mocks.discarded).toHaveBeenCalledWith(oldExperience, 'stale');
		expect(mocks.applied.mock.calls.filter(call => call[0] === oldExperience)).toEqual([]);
		expect(mocks.applied).toHaveBeenCalledWith(currentExperience, {}, expect.any(Function));
		expect(JSON.stringify([mocks.state.mock.calls, mocks.applied.mock.calls, mocks.discarded.mock.calls])).not.toContain('obsolete-private-id');
	});

	it('carries the save context into readback and records a readback failure as error, not empty success', async () => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a'; await controller.loadQuotas();
		vi.clearAllMocks();
		const experience = { actionId: 'save' };
		mocks.begin.mockReturnValue(experience); mocks.get.mockRejectedValue(new Error('private-native-readback'));
		const result = await controller.saveSectionQuotas('compute', { cores: 17 });
		expect(result.success).toBe(true); expect(result.refreshed).toBe(false);
		expect(mocks.begin).toHaveBeenCalledExactlyOnceWith('admin', 'update', 'resource.detail');
		expect(mocks.withExperience.mock.calls).toEqual([[experience], [experience]]);
		expect(mocks.state).toHaveBeenLastCalledWith(experience, 'error');
		expect(JSON.stringify([mocks.state.mock.calls, mocks.applied.mock.calls])).not.toMatch(/private-native-readback|failed|succeeded/);
	});

	it('rejects late quota and save responses after project A→B→A', async () => {
		const { controller } = await setup();
		const oldQuota = Promise.withResolvers<Quotas>();
		const oldSave = Promise.withResolvers<QuotaUpdateResponse>();
		mocks.get.mockReturnValue(oldQuota.promise);
		mocks.put.mockReturnValue(oldSave.promise);
		controller.selectedProjectId = 'p-a';
		const loading = controller.loadQuotas();
		const saving = controller.saveSectionQuotas('compute', { cores: 16 });
		controller.selectedProjectId = 'p-b';
		controller.selectedProjectId = 'p-a';
		oldQuota.resolve(quota); oldSave.resolve(saved);
		await Promise.all([loading, saving]);
		expect(controller.quotas).toBeNull();
		expect(controller.saveSuccess).toBe('');
		expect(controller.saving).toBe(false);
	});


	it('clears synchronously and rejects late responses across same-tick auth A→B→A', async () => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		const oldQuota = Promise.withResolvers<Quotas>();
		mocks.get.mockReturnValue(oldQuota.promise);
		const loading = controller.loadQuotas();
		const original = get(auth);
		auth.set({ ...original, sessionId: 'session-b', token: 'token-b' });
		expect(controller.quotas).toBeNull();
		expect(controller.selectedProjectId).toBe('');
		expect(controller.projects).toEqual([]);
		auth.set(original);
		controller.selectedProjectId = 'p-a';
		oldQuota.resolve(quota);
		await loading;
		expect(controller.quotas).toBeNull();
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


	it.each([projectSwitching, logoutInProgress])('clears results when a session transition starts', async transition => {
		const { controller } = await setup();
		controller.selectedProjectId = 'p-a';
		await controller.loadQuotas();
		transition.set(true);
		expect(controller.quotas).toBeNull();
		expect(controller.selectedProjectId).toBe('');
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
