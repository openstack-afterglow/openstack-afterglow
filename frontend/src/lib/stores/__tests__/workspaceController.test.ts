import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type * as ClientModule from '$lib/api/client';
import { api } from '$lib/api/client';
import { acceptAuthVerification, auth, authReady, clearAuth, getAuthVerificationEpoch, logoutInProgress, projectSwitching, setAuth, setLoginAuth } from '../auth';
import { createWorkspaceController, type WorkspaceInventory } from '../workspaceController.svelte';
import type { AvailableDomain, CreatedDomain } from '$lib/types/auth';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/api/client', async (importOriginal) => ({ ...(await importOriginal<typeof ClientModule>()), api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: vi.fn().mockResolvedValue(undefined) } }));

const home = { id: 'home', name: 'Home' };
const team = { id: 'team', name: 'Team' };
const created: CreatedDomain = { id: 'created', name: 'Created', description: '', enabled: true, default_project_id: 'created-default' };
const inventory: WorkspaceInventory = { domain: home, projects: [{ id: 'project', name: 'Project' }], default_project_id: 'project', is_domain_manager: true, can_create_project: true };
const disposals: (() => void)[] = [];

beforeEach(() => {
	vi.resetAllMocks(); localStorage.clear(); clearAuth(); logoutInProgress.set(false); projectSwitching.set(false);
	setLoginAuth({ token: 'alice-token', userId: 'alice', identityDomainId: home.id, domainId: home.id, projectId: 'project', availableDomains: [home], canCreateDomain: true });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
	vi.mocked(api.get).mockImplementation(async path => path === '/api/v1/auth/domains' ? [home] : inventory);
});
afterEach(() => {
	for (const dispose of disposals.splice(0)) dispose();
	clearAuth(); logoutInProgress.set(false); projectSwitching.set(false);
});

async function mount() {
	const selected = vi.fn();
	const controller = createWorkspaceController(selected);
	const dispose = controller.mount(); disposals.push(dispose);
	await vi.waitFor(() => expect(controller.ready).toBe(true));
	return { controller, selected, dispose };
}

describe('mounted workspace reads', () => {
	it.each(['directory', 'workspace'] as const)('starts both initial reads and coalesces refresh while %s completes first', async firstResponse => {
		const directory = Promise.withResolvers<AvailableDomain[]>();
		const workspace = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : workspace.promise);
		const controller = createWorkspaceController(vi.fn()); disposals.push(controller.mount());
		const refreshing = controller.refresh();
		expect(controller.refresh(home.id)).toBe(refreshing);
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains', '/api/v1/auth/workspaces?domain_id=home']);
		const signals = vi.mocked(api.get).mock.calls.map(call => call[3]!.signal!);
		expect(signals.every(signal => !signal.aborted)).toBe(true);
		if (firstResponse === 'directory') { directory.resolve([home]); await directory.promise; }
		else { workspace.resolve(inventory); await workspace.promise; }
		expect(controller.loading).toBe(true); expect(controller.ready).toBe(false); expect(controller.inventory).toBeNull();
		await controller.select('project'); expect(api.post).not.toHaveBeenCalled();
		expect(controller.refresh()).toBe(refreshing);
		directory.resolve([home]); workspace.resolve(inventory); await refreshing;
		expect(controller.ready).toBe(true); expect(controller.inventory).toEqual(inventory);
		expect(signals.every(signal => !signal.aborted)).toBe(true);
		vi.mocked(api.get).mockImplementation(async path => path === '/api/v1/auth/domains' ? [home] : inventory);
		vi.mocked(api.get).mockClear();
		await controller.refresh();
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains', '/api/v1/auth/workspaces?domain_id=home']);
	});

	it('browses only the listed target workspace and coalesces that target without caching completed inventory', async () => {
		vi.mocked(api.get).mockImplementation(async path => path === '/api/v1/auth/domains' ? [home, team] : inventory);
		const { controller } = await mount();
		const workspace = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockClear().mockReturnValue(workspace.promise);
		const browsing = controller.selectDomain(team.id);
		expect(controller.selectDomain(team.id)).toBe(browsing);
		expect(controller.inventory).toBeNull(); expect(controller.ready).toBe(false);
		expect(controller.domains).toEqual([home, team]);
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/workspaces?domain_id=team']);
		workspace.resolve({ ...inventory, domain: team }); await browsing;
		expect(controller.domainId).toBe(team.id); expect(controller.inventory?.domain).toEqual(team);
		expect(get(auth).domainId).toBe(home.id); expect(api.post).not.toHaveBeenCalled();
		vi.mocked(api.get).mockClear().mockResolvedValue(inventory);
		await controller.selectDomain(home.id);
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/workspaces?domain_id=home']);
	});

	it('upgrades a browse to an explicit directory refresh and discards the superseded workspace', async () => {
		vi.mocked(api.get).mockImplementation(async path => path === '/api/v1/auth/domains' ? [home, team] : inventory);
		const { controller } = await mount();
		const stale = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockReturnValueOnce(stale.promise);
		const browsing = controller.selectDomain(team.id);
		const signal = vi.mocked(api.get).mock.lastCall![3]!.signal!;
		vi.mocked(api.get).mockClear().mockImplementation(async path => path === '/api/v1/auth/domains' ? [home] : inventory);
		await controller.refresh();
		expect(signal.aborted).toBe(true);
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains', '/api/v1/auth/workspaces?domain_id=team', '/api/v1/auth/workspaces?domain_id=home']);
		stale.resolve({ ...inventory, domain: team }); await browsing;
		expect(controller.domainId).toBe(home.id); expect(controller.inventory).toEqual(inventory); expect(controller.ready).toBe(true);
	});

	it.each(['failed', 'empty', 'fallback'] as const)('does not publish speculative inventory when the fresh directory is %s', async outcome => {
		const { controller } = await mount();
		const directory = Promise.withResolvers<AvailableDomain[]>();
		const workspace = Promise.withResolvers<WorkspaceInventory>();
		const fallback = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : path.endsWith('=team') ? fallback.promise : workspace.promise);
		const refreshing = controller.refresh();
		workspace.resolve(inventory); await workspace.promise;
		expect(controller.inventory).toBeNull(); expect(controller.ready).toBe(false);
		await controller.select('project'); expect(api.post).not.toHaveBeenCalled();
		if (outcome === 'failed') directory.reject(new Error('revoked directory'));
		else directory.resolve(outcome === 'empty' ? [] : [team]);
		if (outcome === 'fallback') {
			await vi.waitFor(() => expect(controller.domainId).toBe(team.id));
			expect(controller.inventory).toBeNull(); expect(controller.ready).toBe(false);
			expect(controller.refresh()).toBe(refreshing);
			expect(controller.refresh(team.id)).toBe(refreshing);
			fallback.resolve({ ...inventory, domain: team });
		}
		await refreshing;
		if (outcome === 'fallback') expect(controller.inventory?.domain.id).toBe(team.id);
		else {
			expect(controller.inventory).toBeNull(); expect(controller.domains).toEqual([]);
			expect(controller.ready).toBe(outcome === 'empty');
			if (outcome === 'failed') expect(controller.error).toBe('loadFailed');
			const calls = vi.mocked(api.get).mock.calls.length;
			await controller.selectDomain(home.id);
			expect(api.get).toHaveBeenCalledTimes(calls);
			await controller.select('project'); expect(api.post).not.toHaveBeenCalled();
		}
	});

	it('ignores a failed unlisted speculation and waits for the authorized fallback', async () => {
		const directory = Promise.withResolvers<AvailableDomain[]>();
		const fallback = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : path.endsWith('=home') ? Promise.reject(new Error('not a member')) : fallback.promise);
		const controller = createWorkspaceController(vi.fn()); disposals.push(controller.mount());
		const refreshing = controller.refresh(); directory.resolve([team]);
		await vi.waitFor(() => expect(controller.domainId).toBe(team.id));
		expect(controller.error).toBe(''); expect(controller.ready).toBe(false);
		fallback.resolve({ ...inventory, domain: team }); await refreshing;
		expect(controller.ready).toBe(true); expect(controller.inventory?.domain).toEqual(team);
	});

	it('waits for a fresh directory when no target is known, then reads only its first listed domain', async () => {
		setLoginAuth({ ...get(auth), token: 'unscoped-token', domainId: null, projectId: null });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		const directory = Promise.withResolvers<AvailableDomain[]>();
		const workspace = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : workspace.promise);
		const controller = createWorkspaceController(vi.fn()); disposals.push(controller.mount());
		const refreshing = controller.refresh();
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains']);
		directory.resolve([team, home]);
		await vi.waitFor(() => expect(controller.domainId).toBe(team.id));
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains', '/api/v1/auth/workspaces?domain_id=team']);
		workspace.resolve({ ...inventory, domain: team }); await refreshing;
		expect(controller.ready).toBe(true); expect(controller.inventory?.domain).toEqual(team);
	});

	it.each((['login', 'scope', 'aba', 'unmount'] as const).flatMap(kind => [[kind, 'directory'] as const, [kind, 'workspace'] as const]))('ignores late %s-owner %s completion', async (kind, pendingResponse) => {
		const directory = Promise.withResolvers<AvailableDomain[]>();
		const workspace = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : workspace.promise);
		const controller = createWorkspaceController(vi.fn()); const dispose = controller.mount(); disposals.push(dispose);
		const old = controller.refresh(); const signals = vi.mocked(api.get).mock.calls.map(call => call[3]!.signal!);
		if (pendingResponse === 'workspace') { directory.resolve([home]); await directory.promise; }
		const previous = get(auth);
		vi.mocked(api.get).mockImplementation(async path => path === '/api/v1/auth/domains' ? [team] : { ...inventory, domain: team });
		if (kind === 'unmount') dispose();
		else {
			if (kind === 'login') setLoginAuth({ ...previous, token: 'next-login' });
			else if (kind === 'scope') setAuth({ token: 'team-token', domainId: team.id });
			else { setAuth({ token: 'other', domainId: team.id }); setAuth({ ...previous, token: previous.token! }); }
			expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
			await vi.waitFor(() => expect(controller.ready).toBe(true));
		}
		expect(signals.every(signal => signal.aborted)).toBe(true);
		directory.resolve([home]); workspace.resolve(inventory); await old;
		if (kind === 'unmount') { expect(controller.ready).toBe(false); expect(controller.inventory).toBeNull(); expect(controller.domains).toEqual([]); }
		else { expect(controller.ready).toBe(true); expect(controller.domainId).toBe(team.id); expect(controller.inventory?.domain).toEqual(team); expect(controller.domains).toEqual([team]); }
	});
});

describe('workspace create request ownership', () => {
	it.each(['directory', 'workspace'] as const)('holds an uncertain create fence through browse, failure, and refresh when %s completes first', async firstResponse => {
		const { controller } = await mount();
		const accepted = Promise.withResolvers<CreatedDomain>();
		vi.mocked(api.post).mockReturnValueOnce(accepted.promise);
		const mutation = controller.createDomain('Created', '');
		expect(controller.busy).toBe(true);
		expect(await controller.createDomain('Duplicate', '')).toBe(false);
		const initialReads = vi.mocked(api.get).mock.calls.length;
		await controller.refresh();
		expect(api.get).toHaveBeenCalledTimes(initialReads); expect(api.post).toHaveBeenCalledOnce();
		accepted.reject(new TypeError('native create accepted, response lost'));
		expect(await mutation).toBe(false);
		expect(controller.busy).toBe(false); expect(controller.uncertain).toBe(true);
		expect(await controller.createDomain('Duplicate', '')).toBe(false);
		await controller.selectDomain(home.id);
		expect(controller.ready).toBe(true); expect(controller.uncertain).toBe(true);
		expect(await controller.createDomain('Duplicate', '')).toBe(false);

		vi.mocked(api.get).mockRejectedValueOnce(new Error('unavailable'));
		await controller.refresh();
		expect(controller.uncertain).toBe(true); expect(controller.ready).toBe(false);
		expect(await controller.createDomain('Duplicate', '')).toBe(false);
		const directory = Promise.withResolvers<AvailableDomain[]>();
		const fresh = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : fresh.promise);
		const refreshing = controller.refresh();
		if (firstResponse === 'directory') { directory.resolve([home]); await directory.promise; }
		else { fresh.resolve(inventory); await fresh.promise; }
		expect(controller.uncertain).toBe(true); expect(controller.ready).toBe(false);
		expect(await controller.createDomain('Duplicate', '')).toBe(false);
		directory.resolve([home]); fresh.resolve(inventory); await refreshing;
		expect(controller.uncertain).toBe(false); expect(controller.ready).toBe(true);
		expect(api.post).toHaveBeenCalledOnce();
	});

	it('refreshes the created domain against a new directory before completing without switching scope', async () => {
		const { controller, selected } = await mount();
		const directory = Promise.withResolvers<AvailableDomain[]>();
		const workspace = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.post).mockResolvedValueOnce(created);
		vi.mocked(api.get).mockClear().mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : workspace.promise);
		const creating = controller.createDomain(' Created ', '');
		await vi.waitFor(() => expect(controller.loading).toBe(true));
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains', '/api/v1/auth/workspaces?domain_id=created']);
		workspace.resolve({ ...inventory, domain: created }); await workspace.promise;
		expect(controller.inventory).toBeNull(); expect(controller.ready).toBe(false);
		directory.resolve([home, created]); expect(await creating).toBe(true);
		expect(controller.inventory?.domain.id).toBe(created.id); expect(controller.ready).toBe(true);
		expect(api.post).toHaveBeenCalledOnce(); expect(selected).not.toHaveBeenCalled();
		expect(get(auth).domainId).toBe(home.id); expect(get(auth).projectId).toBe('project');
	});

	it.each(['login', 'aba', 'unmount'] as const)('discards accepted create completion after %s without touching a new request owner', async kind => {
		const { controller, selected, dispose } = await mount();
		const old = Promise.withResolvers<CreatedDomain>();
		const next = Promise.withResolvers<CreatedDomain>();
		vi.mocked(api.post).mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
		const oldMutation = controller.createDomain('Old actor domain', '');
		const signal = vi.mocked(api.post).mock.calls[0][4]!.signal!;
		const previous = get(auth);
		if (kind === 'unmount') dispose();
		else if (kind === 'login') setLoginAuth({ ...previous, token: 'bob-token', userId: 'bob' });
		else { setAuth({ token: 'other', domainId: 'other' }); setAuth({ ...previous, token: previous.token! }); }
		if (kind !== 'unmount') {
			expect(get(authReady)).toBe(false);
			expect(signal.aborted).toBe(true);
			expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		}
		expect(signal.aborted).toBe(true);
		let nextMutation: Promise<boolean> | undefined;
		if (kind !== 'unmount') {
			await vi.waitFor(() => expect(controller.ready).toBe(true));
			nextMutation = controller.createDomain('New owner domain', '');
			expect(controller.busy).toBe(true);
		}
		const reads = vi.mocked(api.get).mock.calls.length;
		old.resolve(created); expect(await oldMutation).toBe(false);
		expect(api.get).toHaveBeenCalledTimes(reads); expect(selected).not.toHaveBeenCalled();
		expect(get(auth).domainId).toBe(home.id); expect(get(auth).projectId).toBe('project');
		if (nextMutation) {
			expect(controller.busy).toBe(true); expect(controller.inventory).toEqual(inventory);
			next.reject(new ApiError(409, 'rejected'));
			expect(await nextMutation).toBe(false);
			expect(controller.busy).toBe(false); expect(controller.error).toBe('createRejected');
			expect(controller.uncertain).toBe(false);
		} else expect(controller.inventory).toBeNull();
	});
});
