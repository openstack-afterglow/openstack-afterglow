// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import type * as StoreModule from 'svelte/store';
import { createPrivateViewScope } from '../privateViewScope';

vi.mock('$lib/stores/auth', async () => {
	// Mock factories are hoisted before the ordinary module import boundary.
	const { writable } = await vi.importActual<typeof StoreModule>('svelte/store');
	return {
		auth: writable({ token: 'a', sessionId: 'login', userId: 'u', domainId: 'd', projectId: 'p', roles: ['reader'], isSystemAdmin: false }),
		projectSwitching: writable(false),
		authReady: writable(true),
	};
});
vi.mock('$lib/stores/servicePermissions', async () => {
	const { writable } = await vi.importActual<typeof StoreModule>('svelte/store');
	const permissions = writable({ permissions: null, loading: false, error: '' });
	return { projectPermissions: permissions, observedProjectPermissions: permissions };
});
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { projectPermissions, type PermissionState } from '$lib/stores/servicePermissions';
import type { Writable } from 'svelte/store';

const releases: Array<() => void> = [];
afterEach(() => { releases.splice(0).forEach(stop => stop()); });
const permissions = projectPermissions as Writable<PermissionState>;
const verified = { is_owner: false, is_manager: false, can_write: false, service_permissions: { drover: ['drover-inventory_reader'] } };

describe('logical private workspace lifetime', () => {
	it('baselines initial verified metadata without repeating restored first loads', () => {
		authReady.set(false);
		let revision = -1;
		releases.push(createPrivateViewScope().subscribe(value => { revision = value; }));
		auth.update(state => ({ ...state, canWrite: true, roles: ['member'], isDomainManager: true }));
		expect(revision).toBe(0);
		authReady.set(true);
		expect(revision).toBe(0);
	});
	it('retains the workspace across token rotation and display-only identity updates', () => {
		let revision = -1;
		releases.push(createPrivateViewScope().subscribe(value => { revision = value; }));
		auth.update(state => ({ ...state, token: 'rotated', projectName: 'Renamed project' }));
		expect(revision).toBe(0);
	});
	it('increments synchronously for project ABA before effects flush', () => {
		let revision = -1;
		releases.push(createPrivateViewScope().subscribe(value => { revision = value; }));
		auth.update(state => ({ ...state, projectId: 'b' }));
		auth.update(state => ({ ...state, projectId: 'p' }));
		expect(revision).toBe(2);
	});
	it('invalidates on switching entry even if the same scope later returns', () => {
		projectSwitching.set(false);
		let revision = -1;
		releases.push(createPrivateViewScope().subscribe(value => { revision = value; }));
		projectSwitching.set(true); projectSwitching.set(false);
		expect(revision).toBe(1);
	});
	it('keeps transient permission checks but retires a changed verified grant', () => {
		permissions.set({ permissions: verified, loading: false, error: '' });
		let revision = -1;
		releases.push(createPrivateViewScope().subscribe(value => { revision = value; }));
		permissions.set({ permissions: null, loading: true, error: '' });
		permissions.set({ permissions: { ...verified }, loading: false, error: '' });
		expect(revision).toBe(0);
		permissions.set({ permissions: { ...verified, service_permissions: { drover: [] } }, loading: false, error: '' });
		expect(revision).toBe(1);
	});
	it('retires views when administrator authority or login identity changes', () => {
		let revision = -1;
		releases.push(createPrivateViewScope().subscribe(value => { revision = value; }));
		auth.update(state => ({ ...state, isSystemAdmin: !state.isSystemAdmin }));
		auth.update(state => ({ ...state, sessionId: 'another-login' }));
		expect(revision).toBe(2);
	});
});
