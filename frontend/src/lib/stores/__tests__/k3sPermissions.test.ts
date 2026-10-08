import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get, writable } from 'svelte/store';
import type { ProjectPermissions } from '../servicePermissions';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));
vi.mock('../auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'user', roles: ['member'], isSystemAdmin: false }),
	authReady: writable(true), projectSwitching: writable(false),
}));
import { auth, authReady, projectSwitching } from '../auth';
import { k3sPermissions } from '../k3sPermissions';
import { projectPermissions } from '../servicePermissions';

const permissions = (leaves: string[]): ProjectPermissions => ({
	is_owner: false, is_manager: false, can_write: true, service_permissions: { drover: leaves },
});
let stop: (() => void) | undefined;
beforeEach(() => {
	vi.resetAllMocks();
	auth.update(state => ({ ...state, token: 'token-a', projectId: 'project-a', roles: ['member'], isSystemAdmin: false }));
	authReady.set(true);
	projectSwitching.set(false);
});
afterEach(() => { stop?.(); stop = undefined; });

async function grant(...leaves: string[]) {
	mocks.get.mockResolvedValue(permissions(leaves));
	stop = k3sPermissions.subscribe(() => {});
	await vi.waitFor(() => expect(get(projectPermissions).loading).toBe(false));
}

describe('native Drover leaves, not OpenStack write roles', () => {
	it('keeps a plain native member without service grants completely unprivileged', async () => {
		await grant();
		expect(get(k3sPermissions)).toEqual({ inventory: false, editClusters: false, administerClusters: false, adminCredentials: false, credentials: false, kubeconfigGrade: null, workloads: false });
	});
	it('allows only the explicit read-only user grade for access_user', async () => {
		await grant('drover-inventory_reader', 'drover-access_user');
		expect(get(k3sPermissions)).toMatchObject({ inventory: true, credentials: true, kubeconfigGrade: 'user', adminCredentials: false, editClusters: false, administerClusters: false, workloads: false });
	});
	it('allows editor create/scale and the namespace-limited editor grade without deletion or full credentials', async () => {
		await grant('drover-inventory_reader', 'drover-access_user', 'drover-clusters_editor', 'drover-workloads_editor');
		expect(get(k3sPermissions)).toMatchObject({ editClusters: true, workloads: true, credentials: true, kubeconfigGrade: 'editor', administerClusters: false, adminCredentials: false });
	});
	it.each([
		['drover-clusters_editor', { editClusters: true, administerClusters: false, credentials: false, kubeconfigGrade: null, workloads: false }],
		['drover-clusters_admin', { editClusters: false, administerClusters: true, credentials: false, kubeconfigGrade: null, workloads: false }],
		['drover-workloads_editor', { editClusters: false, administerClusters: false, credentials: true, kubeconfigGrade: 'editor', workloads: true, adminCredentials: false }],
		['drover-access_admin', { editClusters: false, administerClusters: false, credentials: true, kubeconfigGrade: 'user', workloads: true, adminCredentials: true }],
		['drover_admin', { editClusters: false, administerClusters: false, credentials: false, kubeconfigGrade: null, workloads: false }],
	] as const)('does not invent sibling or removed DAG leaves for %s', async (leaf, expected) => {
		await grant(leaf);
		expect(get(k3sPermissions)).toMatchObject(expected);
	});
	it('denies synchronously while pending, switching, failed or receiving a late previous-project response', async () => {
		const old = Promise.withResolvers<ProjectPermissions>();
		mocks.get.mockReturnValueOnce(old.promise).mockRejectedValueOnce(new Error('scope unavailable'));
		stop = k3sPermissions.subscribe(() => {});
		expect(get(k3sPermissions).credentials).toBe(false);
		auth.update(state => ({ ...state, projectId: 'project-b' }));
		old.resolve(permissions(['drover-access_admin', 'drover-clusters_admin']));
		await vi.waitFor(() => expect(get(projectPermissions).error).toBe('scope unavailable'));
		expect(get(k3sPermissions).credentials).toBe(false);
		expect(get(k3sPermissions).administerClusters).toBe(false);
		projectSwitching.set(true);
		expect(get(k3sPermissions).workloads).toBe(false);
	});
	it('clears existing grants immediately for token refresh and project switching', async () => {
		await grant('drover-access_admin', 'drover-clusters_admin');
		mocks.get.mockReturnValue(Promise.withResolvers<ProjectPermissions>().promise);
		auth.update(state => ({ ...state, token: 'token-b' }));
		expect(get(k3sPermissions).credentials).toBe(false);
		expect(get(k3sPermissions).administerClusters).toBe(false);
		projectSwitching.set(true);
		expect(get(k3sPermissions).workloads).toBe(false);
	});
});
