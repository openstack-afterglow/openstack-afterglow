import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as ClientModule from '$lib/api/client';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), baseUrl: 'http://localhost:8000' }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/api/client', async importOriginal => ({ ...(await importOriginal<typeof ClientModule>()), api: mocks, getBaseUrl: () => mocks.baseUrl }));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: vi.fn().mockResolvedValue(undefined) } }));
const key = 'afterglow_workspace_display_v1';
const home = { id: 'home', name: 'Home' };
const inventory = { domain: home, projects: [{ id: 'project', name: 'Project' }], default_project_id: 'project', is_domain_manager: true, can_create_project: true };
const disposals: (() => void)[] = [];

beforeEach(() => {
	vi.resetModules(); vi.resetAllMocks(); mocks.baseUrl = 'http://localhost:8000'; sessionStorage.clear(); localStorage.clear();
	mocks.get.mockImplementation(async (path: string) => path === '/api/v1/auth/domains' ? [home] : inventory);
});
afterEach(() => { for (const dispose of disposals.splice(0)) dispose(); vi.restoreAllMocks(); });
// Dynamic imports intentionally recreate the module-loading boundary of a full tab reload.
// Static imports would retain the in-memory snapshots and skip the persistence bootstrap.

async function populate() {
	const session = await import('../auth');
	session.setLoginAuth({ token: 'synthetic-access', userId: 'alice', identityDomainId: home.id, domainId: home.id, projectId: 'project', availableDomains: [home], canCreateDomain: true });
	expect(session.acceptAuthVerification(session.getAuthVerificationEpoch(), {})).toBe(true);
	const module = await import('../workspaceController.svelte');
	const controller = module.createWorkspaceController(vi.fn()); const dispose = controller.mount();
	await vi.waitFor(() => expect(controller.ready).toBe(true)); dispose();
	return { session, persisted: sessionStorage.getItem(key)! };
}

async function reload() {
	vi.resetModules(); mocks.get.mockClear();
	const session = await import('../auth');
	const module = await import('../workspaceController.svelte');
	const controller = module.createWorkspaceController(vi.fn()); disposals.push(controller.mount());
	return { session, controller };
}

describe('tab-local workspace display persistence', () => {
	it('restores only after current /me verification, synchronously and without directory requests', async () => {
		const { persisted } = await populate();
		const { session, controller } = await reload();
		expect(get(session.authReady)).toBe(false); expect(controller.ready).toBe(false); expect(controller.inventory).toBeNull();
		expect(mocks.get).not.toHaveBeenCalled(); expect(sessionStorage.getItem(key)).toBe(persisted);
		expect(session.acceptAuthVerification(session.getAuthVerificationEpoch(), {})).toBe(true);
		expect(controller.ready).toBe(true); expect(controller.loading).toBe(false); expect(controller.inventory).toEqual(inventory);
		expect(mocks.get).not.toHaveBeenCalled(); expect(sessionStorage.getItem(key)).toBe(persisted);
	});

	it.each(['same', 'different'] as const)('qualifies the %s configured cloud after reload bootstrap, not the temporary fallback URL', async cloud => {
		mocks.baseUrl = 'http://api.test';
		const { initSiteConfig } = await import('$lib/config/site');
		initSiteConfig({ runtime: { api_base: mocks.baseUrl } });
		const { persisted } = await populate();
		mocks.baseUrl = 'http://localhost:8000';
		const { session, controller } = await reload();
		expect(sessionStorage.getItem(key)).toBe(persisted);
		expect(controller.ready).toBe(false); expect(mocks.get).not.toHaveBeenCalled();
		mocks.baseUrl = cloud === 'same' ? 'http://api.test' : 'http://other-api.test';
		const restoredConfig = await import('$lib/config/site');
		restoredConfig.initSiteConfig({ runtime: { api_base: mocks.baseUrl } });
		// Config bootstrap alone must neither render nor destroy a matching saved display.
		expect(sessionStorage.getItem(key)).toBe(persisted); expect(controller.ready).toBe(false);
		mocks.get.mockImplementation(() => new Promise(() => {}));
		expect(session.acceptAuthVerification(session.getAuthVerificationEpoch(), {})).toBe(true);
		if (cloud === 'same') {
			expect(controller.ready).toBe(true); expect(controller.inventory).toEqual(inventory);
			expect(mocks.get).not.toHaveBeenCalled(); expect(sessionStorage.getItem(key)).toBe(persisted);
		} else {
			expect(controller.inventory).toBeNull(); expect(controller.ready).toBe(false);
			expect(mocks.get).toHaveBeenCalledTimes(2); expect(sessionStorage.getItem(key)).toBeNull();
		}
	});

	it.each(['owner', 'invalid rows', 'duplicate workspace', 'expiry', 'oversized'] as const)('rejects %s persisted data before rendering', async corruption => {
		const { persisted } = await populate(); const saved = JSON.parse(persisted);
		if (corruption === 'owner') saved.owner = 'foreign-login';
		else if (corruption === 'invalid rows') saved.directory.rows = [{ id: 'home', name: null }];
		else if (corruption === 'duplicate workspace') saved.workspaces.push(saved.workspaces[0]);
		else if (corruption === 'expiry') saved.directory.expiresAt = Date.now() + 600_000;
		else saved.extra = 'x'.repeat(512_001);
		sessionStorage.setItem(key, JSON.stringify(saved));
		const { session, controller } = await reload();
		mocks.get.mockImplementation(() => new Promise(() => {}));
		expect(session.acceptAuthVerification(session.getAuthVerificationEpoch(), {})).toBe(true);
		expect(controller.inventory).toBeNull(); expect(controller.ready).toBe(false); expect(sessionStorage.getItem(key)).toBeNull();
		expect(mocks.get).toHaveBeenCalledTimes(2);
	});

	it('purges reload storage when verified authority differs, including role ABA before readiness', async () => {
		await populate();
		const { session, controller } = await reload();
		mocks.get.mockImplementation(() => new Promise(() => {}));
		const original = get(session.auth);
		session.auth.update(state => ({ ...state, roles: ['reader'] }));
		expect(sessionStorage.getItem(key)).toBeNull();
		session.auth.set(original);
		expect(session.acceptAuthVerification(session.getAuthVerificationEpoch(), {})).toBe(true);
		expect(controller.inventory).toBeNull(); expect(controller.ready).toBe(false); expect(mocks.get).toHaveBeenCalledTimes(2);
	});
});
