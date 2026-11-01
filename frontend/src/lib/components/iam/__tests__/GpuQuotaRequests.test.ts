import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth, authReady, projectSwitching, logoutInProgress, setAuth } from '$lib/stores/auth';
import { refreshAuthState } from '$lib/utils/authSession';
import type { ComputePool } from '$lib/api/computePools';
import type { GpuQuotaRequest } from '$lib/api/gpuQuotaRequests';
import { t } from '$lib/i18n/ns/gpu-quota-requests';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
import { ApiError } from '$lib/api/client';
import GpuQuotaRequests from '../GpuQuotaRequests.svelte';
const original = get(auth), gpu = 'CUSTOM_PCI_10DE_2684', companion = 'CUSTOM_PCI_10DE_22BA';
const request = (overrides: Partial<GpuQuotaRequest> = {}): GpuQuotaRequest => ({ id: '11111111111111111111111111111111', domain_id: 'domain-a', project_id: 'project-b', requester_id: 'manager', gpu_profile_name: 'approved-4090', resource_class: gpu, additional: 2, baseline_limit: 2, target_limit: 4, pool_revision: 3, reason: '', status: 'pending', created_at: '2026-10-31T00:00:00Z', reviewer_id: null, reviewed_at: null, note: '', ...overrides });
const pool = (): ComputePool => ({ domain_id: 'domain-a', state: 'active', enabled: true, revision: 3, limits: { [gpu]: 5 }, project_limits: { 'project-b': { [gpu]: 2 } }, usage: {}, available: {}, projects: [{ id: 'project-a', name: 'Same name', enabled: true }, { id: 'project-b', name: 'Same name', enabled: true }, { id: 'disabled', name: 'Disabled', enabled: false }], policy_ready: true, control_scope: 'afterglow', gpu_profiles: [{ name: 'approved-4090', display_name: '4090', resource_class: gpu, resource_requirements: { [gpu]: 1, [companion]: 1 } }] });
const session = () => ({ token: () => 'manager-token', userId: 'manager', domainId: 'domain-a', isCurrent: () => true, canSubmit: () => true });
beforeEach(() => {
	vi.resetAllMocks(); auth.set({ ...original, token: 'token', userId: 'manager', sessionId: 'session-a', identityDomainId: 'domain-a', domainId: 'domain-a', projectId: 'working-project', isSystemAdmin: false });
	authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compute-pool') ? pool() : { items: [], next_cursor: null }));
});
afterEach(() => { cleanup(); auth.set(original); });
async function choose() {
	await screen.findByRole('combobox', { name: t('project') });
	await waitFor(() => expect((screen.getByRole('combobox', { name: t('project') }) as HTMLSelectElement).disabled).toBe(false));
	await fireEvent.change(screen.getByRole('combobox', { name: t('project') }), { target: { value: 'project-b' } });
	await fireEvent.change(screen.getByRole('combobox', { name: t('profile') }), { target: { value: gpu } });
	await fireEvent.input(screen.getByLabelText(t('additional')), { target: { value: '2' } });
}

describe('project GPU increase requests', () => {
	it('offers exact enabled projects and approved primary profiles, with explicit cap baseline', async () => {
		mocks.post.mockResolvedValue(request());
		render(GpuQuotaRequests, { session: session() }); await choose();
		expect(screen.queryByRole('option', { name: /disabled/ })).toBeNull();
		expect(screen.queryByRole('option', { name: new RegExp(companion) })).toBeNull();
		expect(screen.getByText(t('baseline', { limit: '2' }), { exact: false })).toBeTruthy();
		expect(screen.getByText(t('target', { limit: '4' }))).toBeTruthy();
		await fireEvent.input(screen.getByLabelText(t('reason')), { target: { value: 'Training capacity' } });
		await fireEvent.click(screen.getByRole('button', { name: t('submit') }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/iam/gpu-quota-requests', { project_id: 'project-b', resource_class: gpu, additional: 2, reason: 'Training capacity' }, 'manager-token', undefined, expect.objectContaining({ replayOnUnauthorized: false })));
		expect(mocks.put).not.toHaveBeenCalled();
	});
	it('explains inheritance and prevents unlimited, zero, fractional and overflow increases', async () => {
		const snapshot = pool(); snapshot.project_limits = {};
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compute-pool') ? snapshot : { items: [], next_cursor: null }));
		render(GpuQuotaRequests, { session: session() }); await choose();
		expect(screen.getByText(t('inherited'), { exact: false })).toBeTruthy();
		expect(screen.getByText(t('target', { limit: '7' }))).toBeTruthy();
		for (const value of ['0', '-1', '1.5', '2147483647']) {
			await fireEvent.input(screen.getByLabelText(t('additional')), { target: { value } });
			expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(true);
		}
		snapshot.limits[gpu] = -1;
		await fireEvent.click(screen.getByRole('button', { name: t('reload') })); await choose();
		expect(screen.getByText(t('alreadyUnlimited'))).toBeTruthy();
		expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.post).not.toHaveBeenCalled();
	});
	it.each(['unmanaged', 'paused'] as const)('allows ready %s requests but explains manual activation before fulfillment', async state => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compute-pool') ? { ...pool(), state, enabled: false } : { items: [request()], next_cursor: null }));
		render(GpuQuotaRequests, { session: session() });
		await screen.findByText(t('inactiveHelp')); expect(await screen.findByText('approved-4090')).toBeTruthy();
		await choose();
		expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(false);
		mocks.post.mockResolvedValue(request());
		await fireEvent.click(screen.getByRole('button', { name: t('submit') }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
		expect(mocks.put).not.toHaveBeenCalled();
	});
	it('blocks unverified policy submission without hiding durable history', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compute-pool') ? { ...pool(), policy_ready: false } : { items: [request()], next_cursor: null }));
		render(GpuQuotaRequests, { session: session() }); await screen.findByText(t('policyUnavailable'));
		expect(screen.getByText('approved-4090')).toBeTruthy();
		expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.post).not.toHaveBeenCalled();
	});
	it('keeps authorized history independent of unavailable pool evidence', async () => {
		mocks.get.mockImplementation((path: string) => path.endsWith('/compute-pool') ? Promise.reject(new Error('unavailable')) : Promise.resolve({ items: [request()], next_cursor: null }));
		render(GpuQuotaRequests, { session: session() });
		await screen.findByText('approved-4090'); await screen.findByText(t('loadFailed'));
		expect(screen.queryByRole('button', { name: t('submit') })).toBeNull(); expect(screen.queryByText(t('empty'))).toBeNull();
	});
	it('locks an unknown create until successful fresh list and never replays the mutation', async () => {
		mocks.post.mockRejectedValue(new TypeError('lost response'));
		render(GpuQuotaRequests, { session: session() }); await choose();
		await fireEvent.click(screen.getByRole('button', { name: t('submit') })); await screen.findByText(t('unknownOutcome'));
		expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('submit') })); expect(mocks.post).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('reload') }));
		await waitFor(() => expect((screen.getByRole('button', { name: t('submit') }) as HTMLButtonElement).disabled).toBe(false));
	});
	it('rejects a cross-domain list instead of showing empty or foreign history', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/compute-pool') ? pool() : { items: [request({ domain_id: 'foreign' })], next_cursor: null }));
		render(GpuQuotaRequests, { session: session() }); await screen.findByText(t('loadFailed'));
		expect(screen.queryByText('foreign')).toBeNull(); expect(screen.queryByText(t('empty'))).toBeNull();
	});
	it('discloses durable text visibility and denies revoked manager submission without replay', async () => {
		let current = true;
		const manager = { ...session(), isCurrent: () => current, canSubmit: () => current };
		const denied = vi.fn();
		render(GpuQuotaRequests, { session: manager, onDenied: denied }); await choose();
		expect(screen.getByText(t('privacyHelp'))).toBeTruthy();
		current = false;
		await fireEvent.submit(screen.getByRole('button', { name: t('submit') }).closest('form')!);
		expect(mocks.post).not.toHaveBeenCalled();
		current = true; mocks.post.mockRejectedValue(new ApiError(403, 'manager revoked'));
		await fireEvent.submit(screen.getByRole('button', { name: t('submit') }).closest('form')!);
		await waitFor(() => expect(denied).toHaveBeenCalledTimes(1));
		expect(screen.queryByRole('button', { name: t('submit') })).toBeNull();
	});
});

describe('manual admin request review', () => {
	beforeEach(() => auth.update(state => ({ ...state, isSystemAdmin: true })));
	it('loads before selecting any domain and jumps to existing pool editing without quota writes', async () => {
		mocks.get.mockResolvedValue({ items: [request()], next_cursor: null }); const select = vi.fn();
		render(GpuQuotaRequests, { adminMode: true, onSelectDomain: select });
		await screen.findByText('approved-4090'); await fireEvent.click(screen.getByRole('button', { name: t('openDomain') }));
		expect(select).toHaveBeenCalledExactlyOnceWith('domain-a');
		expect(mocks.get).toHaveBeenCalledExactlyOnceWith('/api/v1/admin/gpu-quota-requests?status=pending', 'token', 'working-project', { cache: 'no-store' });
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
	});
	it.each(['fulfilled', 'rejected'] as const)('records only the explicit %s decision, never quota updates', async status => {
		mocks.get.mockResolvedValue({ items: [request()], next_cursor: null }); mocks.post.mockResolvedValue(request({ status, reviewer_id: 'admin', reviewed_at: '2026-10-31T01:00:00Z', note: 'Reviewed manually' }));
		render(GpuQuotaRequests, { adminMode: true }); await screen.findByText('approved-4090');
		await fireEvent.input(screen.getByLabelText(t('note')), { target: { value: 'Reviewed manually' } });
		await fireEvent.click(screen.getByRole('button', { name: t(status === 'fulfilled' ? 'fulfill' : 'reject') }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`/api/v1/admin/gpu-quota-requests/${request().id}/resolve`, { status, note: 'Reviewed manually' }, 'token', 'working-project', expect.objectContaining({ replayOnUnauthorized: false })));
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.get.mock.calls.every(([path]) => !path.includes('/compute-pool'))).toBe(true);
	});
	it('keeps conflicting fulfillment pending and blocks further decisions until reload', async () => {
		mocks.get.mockResolvedValue({ items: [request()], next_cursor: null }); mocks.post.mockRejectedValue(new ApiError(409, 'target not met'));
		render(GpuQuotaRequests, { adminMode: true }); await screen.findByText('approved-4090');
		await fireEvent.click(screen.getByRole('button', { name: t('fulfill') })); await screen.findByText(t('conflict'));
		expect((screen.getByRole('button', { name: t('reject') }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getAllByText(t('pending')).length).toBeGreaterThan(0); expect(mocks.post).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('reload') }));
		await waitFor(() => expect((screen.getByRole('button', { name: t('reject') }) as HTMLButtonElement).disabled).toBe(false));
	});
	it('does not replay an unknown decision and requires a successful list read before continuing', async () => {
		mocks.get.mockResolvedValue({ items: [request()], next_cursor: null }); mocks.post.mockRejectedValue(new TypeError('response lost'));
		render(GpuQuotaRequests, { adminMode: true }); await screen.findByText('approved-4090');
		await fireEvent.click(screen.getByRole('button', { name: t('reject') })); await screen.findByText(t('unknownOutcome'));
		expect((screen.getByRole('button', { name: t('fulfill') }) as HTMLButtonElement).disabled).toBe(true);
		mocks.get.mockRejectedValueOnce(new Error('DB unavailable'));
		await fireEvent.click(screen.getByRole('button', { name: t('reload') })); await screen.findByText(t('loadFailed'));
		expect(screen.getByText(t('reloadRequired'))).toBeTruthy(); expect(mocks.post).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: t('reload') }));
		await waitFor(() => expect((screen.getByRole('button', { name: t('fulfill') }) as HTMLButtonElement).disabled).toBe(false));
		logoutInProgress.set(true);
		await waitFor(() => expect(screen.queryByRole('button', { name: t('fulfill') })).toBeNull());
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});
	it('separates error and empty, paginates 50-item bounded pages without accumulating history', async () => {
		mocks.get.mockRejectedValueOnce(new Error('DB unavailable'));
		render(GpuQuotaRequests, { adminMode: true }); await screen.findByText(t('loadFailed')); expect(screen.queryByText(t('empty'))).toBeNull();
		mocks.get.mockResolvedValueOnce({ items: [request()], next_cursor: 'next-id' });
		await fireEvent.click(screen.getByRole('button', { name: t('reload') })); await screen.findByText('approved-4090');
		mocks.get.mockResolvedValueOnce({ items: [], next_cursor: null });
		await fireEvent.click(screen.getByRole('button', { name: t('next') })); await screen.findByText(t('empty'));
		expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/admin/gpu-quota-requests?status=pending&cursor=next-id', 'token', 'working-project', { cache: 'no-store' });
		expect(screen.queryByText('approved-4090')).toBeNull();
	});
	it('preserves same-session drafts through bearer rotation and discards decision across session ABA', async () => {
		mocks.get.mockResolvedValue({ items: [request()], next_cursor: null }); const pending = Promise.withResolvers<GpuQuotaRequest>(); mocks.post.mockReturnValue(pending.promise);
		render(GpuQuotaRequests, { adminMode: true }); await screen.findByText('approved-4090');
		await fireEvent.input(screen.getByLabelText(t('note')), { target: { value: 'Keep this note' } });
		setAuth(refreshAuthState({ token: 'rotated', user_id: 'manager', username: 'Manager', domain_id: 'domain-a', domain_name: 'A', identity_domain_id: 'domain-a', identity_domain_name: 'A', project_id: 'working-project', project_name: 'Working', expires_at: '2030-01-01T00:00:00Z' }, get(auth)));
		expect((screen.getByLabelText(t('note')) as HTMLTextAreaElement).value).toBe('Keep this note');
		await fireEvent.click(screen.getByRole('button', { name: t('reject') }));
		const prior = get(auth); auth.set({ ...prior, sessionId: 'other' }); auth.set(prior);
		pending.resolve(request({ status: 'rejected' })); await Promise.resolve();
		expect(screen.queryByText(t('decided'))).toBeNull();
	});
	it('discards late queue reads across project scope ABA and hides revoked authority immediately', async () => {
		const pending = Promise.withResolvers<unknown>(); mocks.get.mockReturnValueOnce(pending.promise).mockResolvedValue({ items: [], next_cursor: null });
		render(GpuQuotaRequests, { adminMode: true }); await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		const prior = get(auth); auth.set({ ...prior, projectId: 'other-project' }); auth.set(prior); authReady.set(true);
		pending.resolve({ items: [request()], next_cursor: null }); await screen.findByText(t('empty'));
		expect(screen.queryByText('approved-4090')).toBeNull();
		auth.update(state => ({ ...state, isSystemAdmin: false })); await Promise.resolve();
		expect(screen.queryByRole('button', { name: t('fulfill') })).toBeNull();
	});
});
