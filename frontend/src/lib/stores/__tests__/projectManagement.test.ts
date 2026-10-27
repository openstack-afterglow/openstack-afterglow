import { get, writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/svelte';
const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api }));
vi.mock('../auth', () => ({
	auth: writable({ token: 'token-a', sessionId: 'login-a', userId: 'user', identityDomainId: 'home', domainId: 'domain', projectId: null, isDomainManager: false, isSystemAdmin: false }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false)
}));
import { auth, authReady, projectSwitching, logoutInProgress } from '../auth';
import { canManageOrganizationProjects, projectManagement, refreshProjectManagement } from '../projectManagement';
const caps = { domain_id: 'domain', domain_kind: 'organization', is_domain_manager: false, can_create_project: true };
let stop: (() => void) | null = null;
beforeEach(() => {
	vi.resetAllMocks();
	auth.set({ token: 'token-a', sessionId: 'login-a', userId: 'user', identityDomainId: 'home', domainId: 'domain', projectId: null, isDomainManager: false, isSystemAdmin: false } as never);
	authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
	api.get.mockResolvedValue(caps);
});
afterEach(() => { stop?.(); stop = null; });

describe('fresh organization project capability', () => {
	it('permits creators without synthesizing manager or inferring role names', async () => {
		stop = canManageOrganizationProjects.subscribe(() => {});
		await waitFor(() => expect(get(canManageOrganizationProjects)).toBe(true));
		expect(get(projectManagement).capability?.is_domain_manager).toBe(false);
		expect(api.get).toHaveBeenCalledExactlyOnceWith('/api/v1/projects/capabilities?domain_id=domain', 'token-a', undefined, { cache: 'no-store', suppressAuthRedirect: true });
	});
	it.each(['personal', 'false', 'malformed', 'foreign'])('fails closed for %s authority', async kind => {
		api.get.mockResolvedValue({ ...caps, ...(kind === 'personal' ? { domain_kind: 'personal' } : kind === 'false' ? { can_create_project: false } : kind === 'foreign' ? { domain_id: 'other' } : { is_domain_manager: undefined }) });
		stop = canManageOrganizationProjects.subscribe(() => {});
		await waitFor(() => expect(get(projectManagement).checking).toBe(false));
		expect(get(canManageOrganizationProjects)).toBe(false);
	});
	it('blocks on focus verification, uses rotated access credentials, and fences immediate logout', async () => {
		stop = canManageOrganizationProjects.subscribe(() => {});
		await waitFor(() => expect(get(canManageOrganizationProjects)).toBe(true));
		auth.update(state => ({ ...state, token: 'rotated-token' }));
		expect(api.get).toHaveBeenCalledTimes(1);
		const pending = Promise.withResolvers<unknown>(); api.get.mockReturnValue(pending.promise);
		const refreshing = refreshProjectManagement();
		expect(get(canManageOrganizationProjects)).toBe(false);
		expect(api.get.mock.calls.at(-1)?.[1]).toBe('rotated-token');
		logoutInProgress.set(true);
		expect(get(projectManagement).scope).toBeNull();
		pending.resolve(caps); await refreshing;
		expect(get(canManageOrganizationProjects)).toBe(false);
	});
	it('discards old capability reads after same-tick A to B to A transitions', async () => {
		const pending = Promise.withResolvers<unknown>();
		api.get.mockReturnValueOnce(pending.promise).mockResolvedValue(caps);
		stop = canManageOrganizationProjects.subscribe(() => {});
		auth.update(state => ({ ...state, domainId: 'other' }));
		auth.update(state => ({ ...state, domainId: 'domain' }));
		await waitFor(() => expect(get(canManageOrganizationProjects)).toBe(true));
		pending.resolve({ ...caps, can_create_project: false });
		await Promise.resolve();
		expect(get(canManageOrganizationProjects)).toBe(true);
		expect(api.get).toHaveBeenCalledTimes(3);
	});
});
