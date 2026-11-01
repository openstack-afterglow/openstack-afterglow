import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth, authReady, projectSwitching, logoutInProgress, setAuth } from '$lib/stores/auth';
import { refreshAuthState } from '$lib/utils/authSession';
import type { ComputePool } from '$lib/api/computePools';
import { t } from '$lib/i18n/ns/compute-pools';
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
import { ApiError } from '$lib/api/client';
import ComputePoolPanel from '../ComputePoolPanel.svelte';
const original = get(auth);
const snapshot = (domain_id = 'domain-a', policy_ready = true): ComputePool => ({ domain_id, state: 'active', revision: 3, enabled: true, limits: { CPU: 16, MEMORY_MB: 32768, CUSTOM_PCI_10DE_2236: 2 }, project_limits: { 'project-a': { CPU: 8 } }, usage: { CPU: 10, MEMORY_MB: 8192, CUSTOM_PCI_10DE_2236: 1 }, available: { CPU: 6, MEMORY_MB: 24576, CUSTOM_PCI_10DE_2236: 1 }, projects: [{ id: 'project-a', name: 'Duplicate', enabled: true }, { id: 'project-b', name: 'Duplicate', enabled: true }], policy_ready, control_scope: 'afterglow', gpu_profiles: [] });
beforeEach(() => {
	vi.resetAllMocks(); auth.set({ ...original, token: 'token', sessionId: 'session-a', userId: 'admin', identityDomainId: 'working-domain', identityDomainName: 'Working domain', domainId: 'working-domain', domainName: 'Working domain', projectId: 'working-project', isSystemAdmin: true }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	mocks.get.mockResolvedValue(snapshot());
});
afterEach(() => { cleanup(); auth.set(original); });
async function choose(project: string) { await fireEvent.click(screen.getByRole('button', { name: t('project') })); await fireEvent.click(await screen.findByRole('option', { name: new RegExp(project) })); }

describe('Afterglow domain compute policy', () => {
	it('keeps unknown saved GPU identifiers visible and blocks policy-unready writes', async () => {
		mocks.get.mockResolvedValue(snapshot('domain-a', false));
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true });
		await screen.findByText(t('policyUnavailable'));
		expect(screen.getByRole('heading', { name: 'CUSTOM_PCI_10DE_2236' })).toBeTruthy();
		expect((screen.getByRole('button', { name: t('savePool') }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('checkbox', { name: t('enablePool') }) as HTMLInputElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: t('refresh') }) as HTMLButtonElement).disabled).toBe(false);
		expect(mocks.put).not.toHaveBeenCalled();
	});
	it('uses only approved policy profiles and never fetches the builtin device catalog', async () => {
		const pool = snapshot();
		pool.gpu_profiles = [{ name: '4090', display_name: 'Approved 4090', resource_class: 'CUSTOM_PCI_10DE_2684', resource_requirements: { CUSTOM_PCI_10DE_2684: 1 } }];
		mocks.get.mockResolvedValue(pool); mocks.put.mockResolvedValue({ ...pool, revision: 4 });
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true });
		const input = await screen.findByLabelText(t('poolLimit', { resource: '4090 · Approved 4090 · CUSTOM_PCI_10DE_2684' }));
		expect((input as HTMLInputElement).value).toBe('');
		expect(screen.getByRole('heading', { name: '4090' })).toBeTruthy();
		expect(screen.getByRole('heading', { name: 'CUSTOM_PCI_10DE_2236' })).toBeTruthy();
		expect(mocks.get).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('savePool') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
		expect(mocks.put.mock.calls[0][1].limits).toEqual(pool.limits);
	});
	it('offers only the primary GPU budget while retaining saved companion identifiers for resolution', async () => {
		const pool = snapshot();
		const gpu = 'CUSTOM_PCI_10DE_2684', companion = 'CUSTOM_PCI_10DE_22BA';
		pool.gpu_profiles = [{ name: '4090', display_name: 'Approved 4090', resource_class: gpu, resource_requirements: { [gpu]: 1, [companion]: 1 } }];
		mocks.get.mockResolvedValue(pool);
		const view = render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true });
		await screen.findByLabelText(t('poolLimit', { resource: `4090 · Approved 4090 · ${gpu}` }));
		expect(screen.queryByRole('heading', { name: companion })).toBeNull();
		expect(screen.queryByLabelText(t('poolLimit', { resource: `4090 · Approved 4090 · ${companion}` }))).toBeNull();
		pool.limits[companion] = 0;
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await screen.findByRole('heading', { name: companion });
		expect((screen.getByLabelText(t('poolLimit', { resource: companion })) as HTMLInputElement).value).toBe('0');
		view.unmount();
	});
	it('submits a revisioned optional ceiling for the exact selected UUID without changing working scope', async () => {
		mocks.put.mockResolvedValue({ ...snapshot(), revision: 4 });
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true });
		await screen.findByText(t('policyReady')); await choose('project-b');
		await fireEvent.input(screen.getByLabelText(t('cpu')), { target: { value: '16' } });
		await fireEvent.click(screen.getByRole('button', { name: t('saveCap') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/api/v1/admin/domains/domain-a/compute-pool/projects/project-b', { revision: 3, limits: { CPU: 16 } }, 'token', 'working-project', expect.objectContaining({ replayOnUnauthorized: false })));
		expect(get(auth).domainId).toBe('working-domain'); expect(get(auth).projectId).toBe('working-project');
	});
	it('rejects ceilings above the pool before dispatch', async () => {
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true }); await screen.findByText(t('policyReady')); await choose('project-b');
		await fireEvent.input(screen.getByLabelText(t('cpu')), { target: { value: '17' } });
		expect((screen.getByRole('button', { name: t('saveCap') }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getAllByText(t('invalidCap')).length).toBeGreaterThan(0); expect(mocks.put).not.toHaveBeenCalled();
	});
	it('locks conflicting writes until explicit refresh without replay', async () => {
		mocks.put.mockRejectedValueOnce(new ApiError(409, 'stale revision'));
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true }); await screen.findByText(t('policyReady'));
		await fireEvent.click(screen.getByRole('button', { name: t('savePool') })); await screen.findByText(t('conflict'));
		expect((screen.getByRole('button', { name: t('savePool') }) as HTMLButtonElement).disabled).toBe(true); expect(mocks.put).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await waitFor(() => expect((screen.getByRole('button', { name: t('savePool') }) as HTMLButtonElement).disabled).toBe(false));
	});
	it('rejects a policy response from an unsupported control scope', async () => {
		mocks.get.mockResolvedValue({ ...snapshot(), control_scope: 'native' });
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true }); await screen.findByText(t('policyUnavailable'));
		await fireEvent.click(screen.getByRole('button', { name: t('savePool') })); expect(mocks.put).not.toHaveBeenCalled();
	});
	it('discards late domain results across A→B→A', async () => {
		const old = Promise.withResolvers<ComputePool>(); mocks.get.mockReturnValueOnce(old.promise);
		const view = render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true }); await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		mocks.get.mockImplementation((path: string) => Promise.resolve(snapshot(path.includes('domain-b') ? 'domain-b' : 'domain-a')));
		await view.rerender({ domainId: 'domain-b', adminMode: true }); await screen.findByText('domain-b');
		await view.rerender({ domainId: 'domain-a', adminMode: true }); await screen.findByText('domain-a');
		old.resolve({ ...snapshot(), revision: 999 }); await Promise.resolve();
		expect(screen.queryByText(t('revision', { revision: 999 }))).toBeNull();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains/domain-a/compute-pool', 'token', 'working-project', { cache: 'no-store' });
	});
	it('preserves drafts through token rotation but discards late writes across session ABA', async () => {
		const pending = Promise.withResolvers<ComputePool>(); mocks.put.mockReturnValue(pending.promise);
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true }); await screen.findByText(t('policyReady'));
		const cpu = screen.getByLabelText(t('poolLimit', { resource: t('cpu') })); await fireEvent.input(cpu, { target: { value: '20' } });
		setAuth(refreshAuthState({ token: 'refreshed', user_id: 'admin', username: 'admin', domain_id: 'working-domain', domain_name: 'Working domain', identity_domain_id: 'working-domain', identity_domain_name: 'Working domain', project_id: 'working-project', project_name: 'Working project', expires_at: '2030-01-01T00:00:00Z' }, get(auth)));
		await Promise.resolve(); expect((cpu as HTMLInputElement).value).toBe('20');
		await fireEvent.click(screen.getByRole('button', { name: t('savePool') }));
		const prior = get(auth); auth.set({ ...prior, sessionId: 'other' }); auth.set(prior);
		pending.resolve({ ...snapshot(), revision: 999 }); await Promise.resolve();
		expect(screen.queryByText(t('saved'))).toBeNull(); expect(screen.queryByText(t('revision', { revision: 999 }))).toBeNull();
	});
	it('manager can edit project ceilings but not domain policy', async () => {
		auth.update(state => ({ ...state, isSystemAdmin: false }));
		const session = { token: () => 'manager-token', domainId: 'domain-a', userId: 'manager', isCurrent: () => true, canSubmit: () => true };
		render(ComputePoolPanel, { domainId: 'domain-a', session }); await screen.findByText(t('policyReady'));
		expect(screen.queryByRole('button', { name: t('savePool') })).toBeNull(); expect(screen.queryByLabelText(t('enablePool'))).toBeNull();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/iam/compute-pool', 'manager-token', undefined, { cache: 'no-store' });
	});
	it('keeps paused policies managed and blocks ordinary writes when policy evidence is missing', async () => {
		mocks.get.mockResolvedValue({ ...snapshot('domain-a', false), enabled: false, state: 'paused' });
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true }); await screen.findByText(t('poolState.paused'));
		await choose('project-a');
		expect((screen.getByRole('button', { name: t('saveCap') }) as HTMLButtonElement).disabled).toBe(true); expect(mocks.put).not.toHaveBeenCalled();
	});
	it('keeps explicit server-listed stale-cap recovery available with revision fence', async () => {
		mocks.get.mockResolvedValue({ ...snapshot('domain-a', false), usage: {}, available: {}, stale_project_caps: ['missing-project'], projection_unavailable: true, project_limits: { 'missing-project': { CPU: 4 } } });
		mocks.delete.mockResolvedValue({ ...snapshot(), revision: 4 });
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true }); await screen.findByText('missing-project');
		await fireEvent.click(screen.getByRole('button', { name: t('verifyRemoveCap') }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/api/v1/admin/domains/domain-a/compute-pool/projects/missing-project?revision=3', 'token', 'working-project', expect.objectContaining({ replayOnUnauthorized: false })));
	});
	it('keeps disabled existing projects reachable for cap removal', async () => {
		const pool = snapshot(); pool.projects[0].enabled = false; mocks.get.mockResolvedValue(pool); mocks.delete.mockResolvedValue({ ...pool, revision: 4, project_limits: {} });
		render(ComputePoolPanel, { domainId: 'domain-a', adminMode: true }); await screen.findByText(t('policyReady')); await choose('project-a');
		expect((screen.getByRole('button', { name: t('saveCap') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('removeCap') }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/api/v1/admin/domains/domain-a/compute-pool/projects/project-a?revision=3', 'token', 'working-project', expect.objectContaining({ replayOnUnauthorized: false })));
	});
});
