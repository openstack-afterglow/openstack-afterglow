import { get, writable, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { McpSettingsPage, McpTemplate } from '$lib/api/mcpCatalog';

const { api, translator, language } = vi.hoisted(() => ({ api: { get: vi.fn() }, translator: vi.fn(), language: { current: 'ko' } }));
vi.mock('$lib/api/client', () => ({ api }));
vi.mock('$lib/i18n/ns/mcp-gallery', () => ({ t: translator }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', userId: 'user-a', sessionId: 'session-a', identityDomainId: 'home-a', domainId: 'domain-a', projectId: 'project-a' }),
	authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false),
}));
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable((leaf: string) => leaf === 'lumen-tools_user') }));
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { serviceCapabilities } from '$lib/stores/servicePermissions';
import {
	assertPreparedSandboxTools, managedSandboxIssueMessage, managedSandboxTools, ManagedSandboxSelectionError,
	prepareManagedSandboxTools, refreshManagedSandboxTools, setManagedSandboxTools, toggleManagedSandboxProfile, toggleManagedSandboxTool,
	type ManagedSandboxToolState,
} from '../managedSandboxTools';

const identity = { token: 'token-a', userId: 'user-a', sessionId: 'session-a', identityDomainId: 'home-a', domainId: 'domain-a', projectId: 'project-a' };
// The module mock exposes the writable test seam; production exports a readable.
const permissions = serviceCapabilities as Writable<(leaf: string) => boolean>;
function setIdentity(owner: typeof identity) { auth.update(current => ({ ...current, ...owner })); }
const preferenceKey = (owner = identity) => 'afterglow:managed-sandbox-tools:v1:' + JSON.stringify([owner.userId, owner.identityDomainId, owner.domainId, owner.projectId]);
const stops: Array<() => void> = [];
function entry(profile = 'playwright', tools = ['Browser_Navigate', 'Browser_Click'], available = true): McpTemplate {
	return { id: `registry-${profile}`, name: profile, registry_name: profile, description: '', url: null, transport: null, variables: [], header_hints: [], access: 'managed', featured: true, managed_profile: profile, managed: { profile, available, reason: available ? null : 'runtime_unavailable', tools } };
}
function page(entries = [entry()], next: number | null = null, domain = get(auth).domainId): McpSettingsPage {
	return { entries, total: entries.length, offset: 0, limit: 100, next_offset: next, domain_id: domain, organization_available: false, can_manage_domain: false, custom_connections: [] };
}
function mount(): () => void {
	const stop = managedSandboxTools.subscribe(() => {});
	stops.push(stop);
	return stop;
}
function save(names: unknown) { localStorage.setItem(preferenceKey(), JSON.stringify({ version: 1, selected: names })); }
async function settle() { await refreshManagedSandboxTools(); }

beforeEach(() => {
	localStorage.clear();
	vi.restoreAllMocks();
	api.get.mockReset().mockImplementation(() => Promise.resolve(page()));
	translator.mockReset().mockImplementation((key, values) => `${language.current}:${key}:${values.names ?? ''}`);
	language.current = 'ko';
	setIdentity({ ...identity });
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	permissions.set((leaf: string) => leaf === 'lumen-tools_user');
});
afterEach(() => { for (const stop of stops.splice(0)) stop(); });

describe('managed sandbox preferences and shared availability', () => {
	it('shares one ref-counted loader, defaults to [], and only reads managed settings', async () => {
		const pending = Promise.withResolvers<McpSettingsPage>();
		api.get.mockReturnValue(pending.promise);
		const first = mount();
		const second = mount();
		expect(api.get).toHaveBeenCalledTimes(1);
		expect(get(managedSandboxTools)).toMatchObject({ selected: [], loading: true, issue: null });
		const [path, token, project, options] = api.get.mock.calls[0];
		expect(path).toBe('/api/v1/chat/mcp-settings?access=managed&offset=0&limit=100');
		expect([token, project]).toEqual(['token-a', 'project-a']);
		expect(options).toMatchObject({ cache: 'no-store', refresh: true, replayOnUnauthorized: false });
		first(); expect(options.signal.aborted).toBe(false);
		pending.resolve(page()); await settle();
		expect(get(managedSandboxTools)).toMatchObject({ selected: [], catalogLoaded: true, canSelect: true });
		second(); expect(options.signal.aborted).toBe(false);
		expect(localStorage.length).toBe(0);
	});

	it('loads every page and uses actual managed.profile, not remote IDs or source hints for authority', async () => {
		const unknown = { ...entry('unknown', ['Not_Approved']), managed: null };
		api.get.mockResolvedValueOnce(page([entry()], 100)).mockResolvedValueOnce(page([entry('markitdown', ['Convert_File']), unknown]));
		mount(); await settle();
		expect(api.get.mock.calls.map(call => call[0])).toEqual([
			'/api/v1/chat/mcp-settings?access=managed&offset=0&limit=100',
			'/api/v1/chat/mcp-settings?access=managed&offset=100&limit=100',
		]);
		expect(get(managedSandboxTools).profiles.map(profile => [profile.id, profile.available])).toEqual([['playwright', true], ['markitdown', true], ['unknown', null]]);
		expect(toggleManagedSandboxProfile('registry-playwright', true)).toBe(false);
		expect(toggleManagedSandboxProfile('unknown', true)).toBe(false);
		expect(setManagedSandboxTools(['Not_Approved'])).toBe(false);
		expect(toggleManagedSandboxProfile('markitdown', true)).toBe(true);
		expect(get(managedSandboxTools).selected).toEqual(['Convert_File']);
	});

	it('stores only whitelisted exact-case canonical names and supports profile/tool toggles', async () => {
		mount(); await settle();
		expect(toggleManagedSandboxProfile('playwright', true)).toBe(true);
		expect(toggleManagedSandboxTool('Browser_Click', false)).toBe(true);
		expect(toggleManagedSandboxTool('browser_navigate', true)).toBe(false);
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
		const raw = localStorage.getItem(preferenceKey())!;
		expect(JSON.parse(raw)).toEqual({ version: 1, selected: ['Browser_Navigate'] });
		expect(raw).not.toMatch(/token|session|url|cluster|available|profile|domain|user|project/i);
		expect(preferenceKey()).not.toContain('session-a');
		expect(toggleManagedSandboxProfile('playwright', false)).toBe(true);
		expect(get(managedSandboxTools).selected).toEqual([]);
	});

	it('publishes a new owner and saved intent atomically without a transient empty selection', async () => {
		const next = { ...identity, userId: 'user-b' };
		localStorage.setItem(preferenceKey(next), JSON.stringify({ version: 1, selected: ['Browser_Click'] }));
		const observed: ManagedSandboxToolState[] = [];
		stops.push(managedSandboxTools.subscribe(state => observed.push(state)));
		await settle(); setIdentity(next); await settle();
		const ownerKey = JSON.stringify([next.sessionId, next.userId, next.identityDomainId, next.domainId, next.projectId]);
		const frames = observed.filter(state => state.ownerKey === ownerKey);
		expect(frames.length).toBeGreaterThan(0);
		expect(frames.every(state => state.selected.length === 1 && state.selected[0] === 'Browser_Click')).toBe(true);
	});

	it.each(['userId', 'identityDomainId', 'domainId', 'projectId'] as const)('isolates persistent choices by exact %s', async field => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		setIdentity({ ...identity, [field]: 'other' });
		expect(get(managedSandboxTools).selected).toEqual([]);
		await settle(); setManagedSandboxTools(['Browser_Click']);
		expect(JSON.parse(localStorage.getItem(preferenceKey())!).selected).toEqual(['Browser_Navigate']);
		setIdentity({ ...identity });
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
		await settle();
	});

	it('restores names across login sessions without restoring runtime data or extra persisted fields', async () => {
		localStorage.setItem(preferenceKey(), JSON.stringify({ version: 1, selected: ['Browser_Navigate'], token: 'forged', profiles: [entry('forged')], available: true }));
		mount(); await settle();
		setIdentity({ ...identity, sessionId: 'session-b', token: 'token-b' });
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
		await settle();
		expect(get(managedSandboxTools).profiles.map(profile => profile.id)).toEqual(['playwright']);
		setManagedSandboxTools([]);
		expect(JSON.parse(localStorage.getItem(preferenceKey())!)).toEqual({ version: 1, selected: [] });
	});

	it.each([null, {}, 'Browser_Navigate', [''], ['bad.name'], [' bad'], ['Tool-Name'], ['1Tool'], ['_Tool'], ['x'.repeat(129)], ['Browser_Navigate', 'Browser_Navigate'], [42]].map(names => ({ names })))('blocks invalid saved selection $names until explicit reset', async ({ names }) => {
		save(names); mount(); await settle();
		expect(get(managedSandboxTools)).toMatchObject({ issue: 'invalid_saved', selected: [], storageFailed: false });
		await expect(prepareManagedSandboxTools()).rejects.toMatchObject({ code: 'invalid_saved' });
		expect(setManagedSandboxTools([])).toBe(true);
		expect(get(managedSandboxTools).issue).toBeNull();
	});

	it.each(['{', 'null', '{"version":2,"selected":[]}', '{"version":1}'])('blocks corrupt saved document %s without silently resetting it', async raw => {
		localStorage.setItem(preferenceKey(), raw); mount(); await settle();
		expect(get(managedSandboxTools).issue).toBe('invalid_saved');
		expect(localStorage.getItem(preferenceKey())).toBe(raw);
		await expect(prepareManagedSandboxTools()).rejects.toMatchObject({ code: 'invalid_saved' });
		expect(setManagedSandboxTools([])).toBe(true);
	});

	it('rejects more than 100 names without truncating saved or profile intent', async () => {
		const names = Array.from({ length: 101 }, (_, index) => `Tool_${index}`);
		save(names); api.get.mockResolvedValue(page([entry('large', names)]));
		mount(); await settle();
		expect(get(managedSandboxTools).issue).toBe('too_many');
		await expect(prepareManagedSandboxTools()).rejects.toMatchObject({ code: 'too_many' });
		expect(JSON.parse(localStorage.getItem(preferenceKey())!).selected).toHaveLength(101);
		setManagedSandboxTools([]);
		expect(toggleManagedSandboxProfile('large', true)).toBe(false);
		expect(get(managedSandboxTools).selected).toEqual([]);
		expect(setManagedSandboxTools(names.slice(0, 100))).toBe(true);
		expect(get(managedSandboxTools).selected).toHaveLength(100);
	});

	it('rejects invalid caller values without sanitizing names or changing the last valid preference', async () => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		expect(setManagedSandboxTools(['bad.name'])).toBe(false);
		expect(get(managedSandboxTools)).toMatchObject({ selected: ['Browser_Navigate'], issue: 'invalid_saved' });
		expect(JSON.parse(localStorage.getItem(preferenceKey())!).selected).toEqual(['Browser_Navigate']);
		expect(toggleManagedSandboxTool('', true)).toBe(false);
		setManagedSandboxTools([]); expect(get(managedSandboxTools).issue).toBeNull();
	});

	it('keeps unavailable saved names selected and blocks preparation until explicit removal', async () => {
		save(['Browser_Navigate', 'Gone_Tool']); mount(); await settle();
		expect(get(managedSandboxTools)).toMatchObject({ selected: ['Browser_Navigate', 'Gone_Tool'], unavailable: ['Gone_Tool'], issue: 'unavailable' });
		await expect(prepareManagedSandboxTools()).rejects.toMatchObject({ code: 'unavailable', names: ['Gone_Tool'] });
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate', 'Gone_Tool']);
		expect(toggleManagedSandboxTool('Gone_Tool', false)).toBe(true);
		expect((await prepareManagedSandboxTools()).names).toEqual(['Browser_Navigate']);
	});

	it('never treats false or unknown native availability as permission to add names', async () => {
		api.get.mockResolvedValue(page([entry('offline', ['Offline_Tool'], false), { ...entry('unknown'), managed: null }]));
		mount(); await settle();
		expect(toggleManagedSandboxTool('Offline_Tool', true)).toBe(false);
		expect(toggleManagedSandboxProfile('offline', true)).toBe(false);
		expect(toggleManagedSandboxProfile('unknown', true)).toBe(false);
	});

	it('reports read/write storage failures without claiming names persisted', async () => {
		vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('private storage'); });
		mount(); await settle();
		expect(get(managedSandboxTools)).toMatchObject({ storageFailed: true, issue: 'invalid_saved' });
		vi.restoreAllMocks();
		vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('private storage'); });
		expect(setManagedSandboxTools(['Browser_Navigate'])).toBe(true);
		expect(get(managedSandboxTools)).toMatchObject({ storageFailed: true, selected: ['Browser_Navigate'], issue: null });
		expect(localStorage.getItem(preferenceKey())).toBeNull();
	});
});

describe('managed sandbox owner and preparation fences', () => {
	it('fresh-prepares exact frozen names and shares concurrent preparation without allocating', async () => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		const pending = Promise.withResolvers<McpSettingsPage>(); api.get.mockReturnValue(pending.promise);
		const first = prepareManagedSandboxTools();
		const second = prepareManagedSandboxTools();
		expect(first).toBe(second); expect(api.get).toHaveBeenCalledTimes(2);
		expect(get(managedSandboxTools).preparing).toBe(true);
		pending.resolve(page()); const frame = await first;
		expect(frame.names).toEqual(['Browser_Navigate']);
		expect(Object.isFrozen(frame)).toBe(true); expect(Object.isFrozen(frame.names)).toBe(true);
		expect(() => assertPreparedSandboxTools(frame)).not.toThrow();
		expect(get(managedSandboxTools).preparing).toBe(false);
		expect(api.get.mock.calls.every(call => call[0].startsWith('/api/v1/chat/mcp-settings?access=managed&'))).toBe(true);
	});

	it('rechecks changed native availability, never silently downgrading selection', async () => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		api.get.mockResolvedValue(page([entry('playwright', ['Browser_Navigate'], false)]));
		await expect(prepareManagedSandboxTools()).rejects.toMatchObject({ code: 'unavailable', names: ['Browser_Navigate'] });
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
		expect(toggleManagedSandboxTool('Browser_Navigate', false)).toBe(true);
	});

	it('permits empty text preparation with no resource read despite failed catalog or permission', async () => {
		api.get.mockRejectedValue(new Error('PRIVATE_UPSTREAM_ERROR'));
		mount(); await settle(); const reads = api.get.mock.calls.length;
		const frame = await prepareManagedSandboxTools();
		expect(frame.names).toEqual([]); expect(api.get).toHaveBeenCalledTimes(reads);
		expect(get(managedSandboxTools)).toMatchObject({ catalogError: true, issue: null });
		expect(() => assertPreparedSandboxTools(frame)).not.toThrow();
		permissions.set(() => false);
		const deniedEmpty = await prepareManagedSandboxTools();
		expect(() => assertPreparedSandboxTools(deniedEmpty)).not.toThrow();
		expect(api.get).toHaveBeenCalledTimes(reads);
	});

	it('does not read a catalog without tools permission, but can remove saved choices', async () => {
		save(['Browser_Navigate']); permissions.set(() => false);
		mount(); expect(api.get).not.toHaveBeenCalled();
		expect(get(managedSandboxTools)).toMatchObject({ selected: ['Browser_Navigate'], canSelect: false, issue: 'permission' });
		await expect(prepareManagedSandboxTools()).rejects.toMatchObject({ code: 'permission' });
		expect(toggleManagedSandboxTool('Browser_Navigate', false)).toBe(true);
		expect((await prepareManagedSandboxTools()).names).toEqual([]);
	});

	it('revokes settled authority synchronously while preserving removable profile choices', async () => {
		mount(); await settle(); toggleManagedSandboxProfile('playwright', true);
		const frame = await prepareManagedSandboxTools();
		permissions.set(() => false);
		expect(get(managedSandboxTools)).toMatchObject({ selected: ['Browser_Navigate', 'Browser_Click'], canSelect: false, issue: 'permission' });
		expect(() => assertPreparedSandboxTools(frame)).toThrow(ManagedSandboxSelectionError);
		expect(toggleManagedSandboxTool('Other', true)).toBe(false);
		expect(toggleManagedSandboxProfile('playwright', false)).toBe(true);
		expect(get(managedSandboxTools).selected).toEqual([]);
	});

	it.each(['userId', 'projectId', 'identityDomainId', 'domainId', 'sessionId'] as const)('discards late availability across %s ABA', async field => {
		const pending = Promise.withResolvers<McpSettingsPage>(); api.get.mockReturnValueOnce(pending.promise);
		mount(); const signal = api.get.mock.calls[0][3].signal;
		setIdentity({ ...identity, [field]: 'other' }); setIdentity({ ...identity });
		expect(signal.aborted).toBe(true);
		await settle(); pending.resolve(page([entry('stale', ['Stale_Tool'])]));
		await Promise.resolve(); await Promise.resolve();
		expect(get(managedSandboxTools).profiles.map(profile => profile.id)).toEqual(['playwright']);
	});

	it.each(['userId', 'projectId', 'identityDomainId', 'domainId', 'sessionId'] as const)('rejects pending preparation across %s ABA even if transport ignores abort', async field => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		const pending = Promise.withResolvers<McpSettingsPage>(); api.get.mockReturnValueOnce(pending.promise);
		const prepared = prepareManagedSandboxTools();
		const rejected = expect(prepared).rejects.toMatchObject({ code: 'owner_changed' });
		setIdentity({ ...identity, [field]: 'other' }); setIdentity({ ...identity });
		await rejected; await settle(); pending.resolve(page());
		expect(get(managedSandboxTools).preparing).toBe(false);
	});

	it.each(['ready', 'switch', 'logout', 'permission'] as const)('fences requests and frozen frames across %s loss/restoration', async loss => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		const frame = await prepareManagedSandboxTools();
		const pending = Promise.withResolvers<McpSettingsPage>(); api.get.mockReturnValueOnce(pending.promise);
		const prepared = prepareManagedSandboxTools();
		const rejected = expect(prepared).rejects.toBeInstanceOf(ManagedSandboxSelectionError);
		const signal = api.get.mock.calls.at(-1)![3].signal;
		if (loss === 'ready') { authReady.set(false); authReady.set(true); }
		if (loss === 'switch') { projectSwitching.set(true); projectSwitching.set(false); }
		if (loss === 'logout') { logoutInProgress.set(true); logoutInProgress.set(false); }
		if (loss === 'permission') { permissions.set(() => false); permissions.set(() => true); }
		expect(signal.aborted).toBe(true); await rejected; await settle();
		expect(() => assertPreparedSandboxTools(frame)).toThrow(ManagedSandboxSelectionError);
		pending.resolve(page([entry('stale', ['Stale_Tool'])]));
	});

	it('rejects pending and settled preparation on selection changes, including selection ABA', async () => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		const frame = await prepareManagedSandboxTools();
		const pending = Promise.withResolvers<McpSettingsPage>(); api.get.mockReturnValueOnce(pending.promise);
		const prepared = prepareManagedSandboxTools();
		const rejected = expect(prepared).rejects.toMatchObject({ code: 'selection_changed' });
		setManagedSandboxTools([]); setManagedSandboxTools(['Browser_Navigate']);
		await rejected; expect(() => assertPreparedSandboxTools(frame)).toThrow(ManagedSandboxSelectionError);
		pending.resolve(page());
	});

	it('keeps settled selection and pending preparation through same-owner token renewal', async () => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		const frame = await prepareManagedSandboxTools(); const count = api.get.mock.calls.length;
		setIdentity({ ...identity, token: 'renewed-token' });
		expect(api.get).toHaveBeenCalledTimes(count);
		expect(get(managedSandboxTools).selected).toEqual(['Browser_Navigate']);
		expect(() => assertPreparedSandboxTools(frame)).not.toThrow();
		const pending = Promise.withResolvers<McpSettingsPage>(); api.get.mockReturnValueOnce(pending.promise);
		const prepared = prepareManagedSandboxTools();
		expect(api.get.mock.calls.at(-1)![1]).toBe('renewed-token');
		setIdentity({ ...identity, token: 'renewed-again' }); pending.resolve(page());
		expect((await prepared).names).toEqual(['Browser_Navigate']);
	});

	it('uses renewed credentials for later pages without accepting a different owner', async () => {
		const pending = Promise.withResolvers<McpSettingsPage>(); api.get.mockReturnValueOnce(pending.promise);
		mount(); setIdentity({ ...identity, token: 'renewed-token' });
		pending.resolve(page([entry()], 100)); await settle();
		expect(api.get.mock.calls[1][1]).toBe('renewed-token');
	});

	it('cancels only after last subscriber leaves and clears private memory on remount', async () => {
		const first = mount(); const second = mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		const pending = Promise.withResolvers<McpSettingsPage>(); api.get.mockReturnValueOnce(pending.promise);
		const prepared = prepareManagedSandboxTools();
		const rejected = expect(prepared).rejects.toMatchObject({ code: 'owner_changed' });
		const signal = api.get.mock.calls.at(-1)![3].signal;
		first(); expect(signal.aborted).toBe(false);
		second(); expect(signal.aborted).toBe(true); await rejected;
		expect(setManagedSandboxTools([])).toBe(false);
		mount(); expect(get(managedSandboxTools)).toMatchObject({ profiles: [], selected: ['Browser_Navigate'], preparing: false, loading: true });
		await settle(); pending.resolve(page([entry('stale', ['Stale_Tool'])]));
		expect(get(managedSandboxTools).profiles.map(profile => profile.id)).toEqual(['playwright']);
	});

	it.each(['sessionId', 'userId', 'identityDomainId', 'domainId', 'projectId'] as const)('refuses incomplete verified %s ownership', async field => {
		setIdentity({ ...identity, [field]: '' }); mount();
		expect(get(managedSandboxTools).ownerKey).toBeNull();
		expect(api.get).not.toHaveBeenCalled(); expect(setManagedSandboxTools([])).toBe(false);
		await expect(prepareManagedSandboxTools()).rejects.toMatchObject({ code: 'owner_changed' });
	});

	it.each(['unavailable', 'failure'] as const)('rejects old frames after catalog readiness %s ABA', async change => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']);
		const frame = await prepareManagedSandboxTools();
		if (change === 'unavailable') api.get.mockResolvedValue(page([entry('playwright', ['Browser_Navigate'], false)]));
		else api.get.mockRejectedValue(new Error('PRIVATE_UPSTREAM_ERROR'));
		await settle();
		api.get.mockResolvedValue(page()); await settle();
		expect(get(managedSandboxTools).issue).toBeNull();
		expect(() => assertPreparedSandboxTools(frame)).toThrow(ManagedSandboxSelectionError);
		const fresh = await prepareManagedSandboxTools();
		expect(() => assertPreparedSandboxTools(fresh)).not.toThrow();
	});

	it('invalidates frames when refreshed availability fails or no longer approves the names', async () => {
		mount(); await settle(); setManagedSandboxTools(['Browser_Navigate']); const frame = await prepareManagedSandboxTools();
		api.get.mockResolvedValue(page([entry('playwright', ['Browser_Navigate'], false)])); await settle();
		expect(() => assertPreparedSandboxTools(frame)).toThrow(ManagedSandboxSelectionError);
		api.get.mockRejectedValue(new Error('PRIVATE_UPSTREAM_ERROR')); await settle();
		expect(() => assertPreparedSandboxTools(frame)).toThrow(ManagedSandboxSelectionError);
		expect(get(managedSandboxTools).issue).toBe('catalog_failed');
		await expect(prepareManagedSandboxTools()).rejects.toMatchObject({ code: 'catalog_failed' });
	});

	it.each(['pagination', 'domain', 'names'] as const)('fails closed on malformed catalog %s', async malformed => {
		api.get.mockResolvedValue(malformed === 'pagination' ? page([entry()], 0) : malformed === 'domain' ? page([entry()], null, 'foreign-domain') : page([entry('bad', ['bad.name'])]));
		save(['Browser_Navigate']); mount(); await settle();
		expect(get(managedSandboxTools)).toMatchObject({ issue: 'catalog_failed', canSelect: false, selected: ['Browser_Navigate'] });
	});

	it('translates sanitized issue keys at use time, not import or catalog-read time', async () => {
		mount(); await settle(); expect(translator).not.toHaveBeenCalled();
		expect(managedSandboxIssueMessage('permission')).toBe('ko:selectionIssue.permission:');
		language.current = 'en';
		expect(managedSandboxIssueMessage('unavailable', ['Browser_Navigate', 'Gone_Tool'])).toBe('en:selectionIssue.unavailable:Browser_Navigate, Gone_Tool');
		expect(translator).toHaveBeenLastCalledWith('selectionIssue.unavailable', { names: 'Browser_Navigate, Gone_Tool' });
	});

	it('does not expose writable state or accept forged prepared frames', async () => {
		mount(); await settle(); const state: ManagedSandboxToolState = get(managedSandboxTools);
		expect('set' in managedSandboxTools).toBe(false); expect(Object.isFrozen(state.selected)).toBe(true);
		const frame = await prepareManagedSandboxTools();
		expect(() => assertPreparedSandboxTools({ ...frame })).toThrow(ManagedSandboxSelectionError);
	});
});
