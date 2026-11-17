import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MOCK_MCP_CONSENT_TICKET, MOCKUP_SESSION_KEY } from '$lib/mockup/contracts';
import type { K3sSseProgressMessage } from '$lib/api/k3sSseStream';
import type { K3sCluster } from '$lib/types/k3s';
import { parseContainerListResponse } from '$lib/types/zunContainer';
import type { UserDashboardSummary } from '$lib/types/userDashboard';
import type { SecretInfo, ContainerInfo, OrderInfo, QuotaInfo } from '$lib/api/secrets';
let fetchMock = vi.fn();

beforeEach(() => {
	vi.resetModules();
	fetchMock = vi.fn(() => {
		throw new Error('mockup transport tests must stay network-free');
	});
	vi.stubGlobal('fetch', fetchMock);
	localStorage.clear();
	sessionStorage.clear();
	sessionStorage.setItem(MOCKUP_SESSION_KEY, 'on');
});

afterEach(() => {
	window.history.replaceState({}, '', '/');
	vi.unstubAllGlobals();
});

interface TutorialMcpConnection {
	id: number;
	name: string;
	scope: 'global' | 'domain' | 'user';
	owner_user_id: string | null;
	owner_domain_id: string | null;
	owner_project_id: string | null;
	config_version: number;
	activation_config_version: number | null;
	activation_generation: number;
	activation_is_active: boolean;
	server_is_active: boolean;
	is_active: boolean;
	auth_connected: boolean;
	has_headers: boolean;
	has_oauth_client: boolean;
	has_oauth_client_secret: boolean;
	implicit_selection: boolean;
	state: string;
	template_key: string | null;
	url: string;
}
interface TutorialMcpEntry {
	id: string;
	registry_name: string;
	name: string;
	featured: boolean;
	access: string;
	state: string;
	unavailable_reason: string | null;
	connections: TutorialMcpConnection[];
	managed: { profile: string; available: boolean; reason: string | null; tools: string[] } | null;
}
interface TutorialMcpSettings {
	entries: TutorialMcpEntry[];
	total: number;
	offset: number;
	limit: number;
	next_offset: number | null;
	domain_id: string;
	can_manage_domain: boolean;
	custom_connections: TutorialMcpConnection[];
}
interface TutorialMcpCreated { created: boolean; server: TutorialMcpConnection }

function setMcpTutorialProfile(profile: 'on' | 'admin') {
	sessionStorage.setItem(MOCKUP_SESSION_KEY, profile);
	const url = new URL(window.location.href);
	url.searchParams.set('tutorial', profile);
	// The live tutorial URL outranks the auth store's module-owned profile.
	window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
}

async function mcpRequest<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
	// Resolve after resetModules: tutorial state belongs to the current transport module.
	const { maybeMockJson } = await import('./transport');
	const response = await maybeMockJson<T>(method, `/api/v1/chat${path}`, body, 'mock-token-tutorial-scoped', 'mock-project-1');
	if (typeof response === 'symbol') throw new Error('Expected a tutorial MCP fixture');
	return response;
}

describe('MCP catalog tutorial fixtures', () => {
	beforeEach(() => setMcpTutorialProfile('on'));

	it('pages the whole registry and applies search, featured, access, and state filters before pagination', async () => {
		const first = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?offset=0&limit=12');
		const second = await mcpRequest<TutorialMcpSettings>('GET', `/mcp-settings?offset=${first.next_offset}&limit=12`);
		const entries = [...first.entries, ...second.entries];
		expect(first).toMatchObject({ total: 19, offset: 0, limit: 12, next_offset: 12, domain_id: 'mock-domain', can_manage_domain: false });
		expect(second.next_offset).toBeNull();
		expect(new Set(entries.map(entry => entry.id)).size).toBe(first.total);
		expect(entries.map(entry => entry.registry_name)).toEqual(entries.map(entry => entry.registry_name).toSorted((a, b) => a.localeCompare(b)));
		const featured = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?featured=true&limit=2');
		expect(featured).toMatchObject({ total: 6, next_offset: 2 });
		expect(featured.entries.every(entry => entry.featured)).toBe(true);
		const github = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?q=github&access=oauth&limit=1');
		expect(github.total).toBe(1);
		expect(github.entries[0]).toMatchObject({ id: 'mock-reg-github', access: 'oauth', state: 'not_connected' });
		const absent = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?q=no-matching-server&offset=0&limit=12');
		expect(absent).toMatchObject({ entries: [], total: 0, next_offset: null });
		const unavailable = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?state=managed_unavailable');
		expect(unavailable.entries.map(entry => entry.name)).toEqual(['Markitdown']);
		const forged = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?domain_id=foreign&can_manage_domain=true');
		expect(forged).toMatchObject({ domain_id: 'mock-domain', can_manage_domain: false });
		for (const query of ['offset=-1', 'offset=1.5', 'limit=0', 'limit=101', 'featured=maybe', `q=${'x'.repeat(101)}`]) {
			await expect(mcpRequest('GET', `/mcp-settings?${query}`)).rejects.toMatchObject({ status: 422 });
		}
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('reports actual managed fixture availability without creating remote connections', async () => {
		const page = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?access=managed');
		expect(page.entries.find(entry => entry.name === 'Playwright')).toMatchObject({
			access: 'managed', state: 'managed_available', connections: [],
			managed: { profile: 'playwright', available: true, reason: null, tools: ['browser_navigate', 'browser_snapshot', 'browser_click'] },
		});
		expect(page.entries.find(entry => entry.name === 'Markitdown')).toMatchObject({
			state: 'managed_unavailable', managed: { profile: 'markitdown', available: false, reason: 'profile_not_in_enabled_sandbox_manifest' },
		});
		for (const template of ['playwright', 'markitdown', 'filesystem', 'offline']) {
			await expect(mcpRequest('POST', '/mcp-connections', { template_id: `mock-reg-${template}` })).rejects.toMatchObject({ status: 400 });
		}
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('creates idempotent personal OAuth connections and completes only a matching local authorization round trip', async () => {
		window.history.replaceState({}, '', '/dashboard/chat/tools?tutorial=on');
		const created = await mcpRequest<TutorialMcpCreated>('POST', '/mcp-connections', { template_id: 'mock-reg-github', label: 'Work' });
		expect(created).toMatchObject({ created: true, server: { scope: 'user', owner_user_id: 'mock-user-1', owner_project_id: 'mock-project-1', implicit_selection: false, state: 'needs_auth', config_version: 1 } });
		expect(typeof created.server.id).toBe('number');
		const duplicate = await mcpRequest<TutorialMcpCreated>('POST', '/mcp-connections', { template_id: 'mock-reg-github', label: 'Work' });
		expect(duplicate).toMatchObject({ created: false, server: { id: created.server.id } });
		const id = created.server.id;
		expect(created.server).toMatchObject({ is_active: false, activation_is_active: false, activation_config_version: null });
		const started = await mcpRequest<{ authorization_url: string }>('POST', `/mcp-servers/${id}/oauth/start`, {});
		expect(await mcpRequest('GET', `/mcp-servers/${id}/oauth`)).toMatchObject({ required: true, connected: false });
		const callback = new URL(started.authorization_url, window.location.origin);
		expect(callback.origin).toBe(window.location.origin);
		expect(callback.pathname).toBe('/dashboard/chat/tools');
		expect(callback.searchParams.get('mock_mcp_oauth')).toBeTruthy();
		window.history.replaceState({}, '', started.authorization_url);
		vi.resetModules(); // A real local authorization redirect reloads the fixture transport.
		expect(await mcpRequest('GET', `/mcp-servers/${id}/oauth`)).toMatchObject({ required: true, connected: true });
		const connected = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?q=github');
		expect(connected.entries[0]).toMatchObject({ state: 'personal_connected', connections: [{ id, is_active: true, activation_is_active: false, activation_config_version: null }] });
		expect(window.location.search).not.toContain('mock_mcp_oauth');
		expect(sessionStorage.getItem('afterglow.mockup.mcp-oauth')).toBeNull();
		const changed = await mcpRequest<TutorialMcpConnection>('PATCH', `/mcp-connections/${id}`, { is_active: true });
		expect(changed).toMatchObject({ config_version: 2, activation_config_version: null, is_active: false, auth_connected: false, state: 'needs_auth' });
		await mcpRequest('DELETE', `/mcp-connections/${id}`);
		expect((await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?q=github')).entries[0].connections).toEqual([]);
		await expect(mcpRequest('GET', `/mcp-servers/${id}/oauth`)).rejects.toMatchObject({ status: 404 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('keeps supplied credentials transient and returns only secret-presence metadata', async () => {
		const secret = 'tutorial-do-not-store-header-value';
		await expect(mcpRequest('POST', '/mcp-connections', { template_id: 'mock-reg-brave' })).rejects.toMatchObject({ status: 400 });
		const personal = await mcpRequest<TutorialMcpCreated>('POST', '/mcp-connections', { template_id: 'mock-reg-brave', headers: { Authorization: secret } });
		expect(personal.server).toMatchObject({ scope: 'user', has_headers: true, auth_connected: true, is_active: true, activation_is_active: false, activation_config_version: null });
		expect(personal.server).not.toHaveProperty('headers');
		const updated = await mcpRequest<TutorialMcpConnection>('PATCH', `/mcp-connections/${personal.server.id}`, { headers: { Authorization: 'replacement-secret' } });
		expect(updated).toMatchObject({ config_version: 2, has_headers: true, is_active: true, activation_config_version: null });
		expect(await mcpRequest('PATCH', `/mcp-connections/${personal.server.id}`, { is_active: false })).toMatchObject({ config_version: 3, server_is_active: false, is_active: false });
		expect(await mcpRequest('PATCH', `/mcp-connections/${personal.server.id}`, { is_active: true })).toMatchObject({ config_version: 4, server_is_active: true, is_active: true, activation_config_version: null });
		expect(JSON.stringify(await mcpRequest('GET', '/mcp-settings'))).not.toContain(secret);
		const oauth = await mcpRequest<TutorialMcpCreated>('POST', '/mcp-connections', { template_id: 'mock-reg-github' });
		await mcpRequest('POST', `/mcp-servers/${oauth.server.id}/oauth/start`);
		const persisted = sessionStorage.getItem('afterglow.mockup.mcp-oauth')!;
		expect(persisted).not.toContain(secret);
		expect(persisted).not.toContain('replacement-secret');
		expect(persisted).not.toContain('"headers":');
		expect(localStorage.length).toBe(0);
		await expect(mcpRequest('POST', '/mcp-connections', { template_id: 'mock-reg-github', owner_user_id: 'foreign' })).rejects.toMatchObject({ status: 400 });
		await expect(mcpRequest('POST', '/mcp-connections', { template_id: 'mock-reg-fetch', headers: { Authorization: secret } })).rejects.toMatchObject({ status: 400 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('lets members activate shared connections but never manage or authorize the shared credential', async () => {
		const member = await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings');
		expect(member.can_manage_domain).toBe(false);
		const org = '/domains/mock-domain/mcp-connections';
		expect(await mcpRequest('GET', `${org}?limit=1`)).toMatchObject({ total: 2, next_offset: 1, connections: [{ scope: 'domain', owner_domain_id: 'mock-domain', has_headers: false, auth_connected: true }] });
		const active = await mcpRequest<TutorialMcpConnection>('PATCH', `${org}/101/activation`, { is_active: true, config_version: 1 });
		expect(active).toMatchObject({ is_active: true, state: 'org_connected' });
		for (const [method, path, body] of [
			['POST', org, { template_id: 'mock-reg-github', can_manage_domain: true }],
			['PATCH', `${org}/101`, { name: 'Unauthorized' }],
			['DELETE', `${org}/101`, undefined],
			['POST', '/mcp-servers/101/oauth/start', {}],
			['DELETE', '/mcp-servers/101/oauth', undefined],
		] as const) await expect(mcpRequest(method, path, body)).rejects.toMatchObject({ status: 403 });
		await expect(mcpRequest('GET', '/domains/foreign-domain/mcp-connections')).rejects.toMatchObject({ status: 403 });
		await expect(mcpRequest('PATCH', '/mcp-connections/101', { is_active: false })).rejects.toMatchObject({ status: 404 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('rechecks tutorial manager identity and invalidates every member consent after an organization edit', async () => {
		const org = '/domains/mock-domain/mcp-connections';
		await mcpRequest('PATCH', `${org}/101/activation`, { is_active: true, config_version: 1 });
		setMcpTutorialProfile('admin');
		expect(await mcpRequest('GET', '/mcp-settings')).toMatchObject({ can_manage_domain: true, domain_id: 'mock-domain' });
		const changed = await mcpRequest<TutorialMcpConnection>('PATCH', `${org}/101`, { name: 'Team documents', oauth_client_id: 'fixture-client', oauth_client_secret: 'do-not-persist-oauth-secret' });
		expect(changed).toMatchObject({ config_version: 2, has_oauth_client: true, has_oauth_client_secret: true, auth_connected: false });
		await expect(mcpRequest('PATCH', `${org}/101`, { load_policy: 'preloaded' })).rejects.toMatchObject({ status: 400 });
		setMcpTutorialProfile('on');
		const stale = await mcpRequest<TutorialMcpConnection[]>('GET', '/mcp-servers');
		expect(stale.find(row => row.id === 101)).toMatchObject({ activation_config_version: 1, config_version: 2, is_active: false });
		await expect(mcpRequest('PATCH', `${org}/101/activation`, { is_active: true, config_version: 1 })).rejects.toMatchObject({ status: 409 });
		await mcpRequest('PATCH', `${org}/101/activation`, { is_active: true, config_version: 2 });
		setMcpTutorialProfile('admin');
		const started = await mcpRequest<{ authorization_url: string }>('POST', '/mcp-servers/101/oauth/start', {});
		expect(sessionStorage.getItem('afterglow.mockup.mcp-oauth')).not.toContain('do-not-persist-oauth-secret');
		window.history.replaceState({}, '', started.authorization_url);
		expect(await mcpRequest('GET', '/mcp-servers/101/oauth')).toMatchObject({ connected: true });
		setMcpTutorialProfile('on');
		expect((await mcpRequest<TutorialMcpConnection[]>('GET', '/mcp-servers?active_only=true')).map(row => row.id)).toContain(101);
		setMcpTutorialProfile('admin');
		await mcpRequest('DELETE', '/mcp-servers/101/oauth');
		setMcpTutorialProfile('on');
		expect((await mcpRequest<TutorialMcpConnection[]>('GET', '/mcp-servers')).find(row => row.id === 101)).toMatchObject({ auth_connected: false, activation_is_active: false, is_active: false });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('creates manager-owned organization rows without exposing credentials to members and cascades deletion', async () => {
		setMcpTutorialProfile('admin');
		const org = '/domains/mock-domain/mcp-connections';
		const created = await mcpRequest<TutorialMcpCreated>('POST', org, { template_id: 'mock-reg-stripe', label: 'Billing', headers: { Authorization: 'shared-private-secret' } });
		expect(created.server).toMatchObject({ scope: 'domain', owner_user_id: 'mock-admin-1', owner_domain_id: 'mock-domain', implicit_selection: false, has_headers: true });
		setMcpTutorialProfile('on');
		const members = await mcpRequest<{ connections: TutorialMcpConnection[] }>('GET', org);
		expect(members.connections.find(row => row.id === created.server.id)).toMatchObject({ has_headers: true, auth_connected: true });
		expect(JSON.stringify(members)).not.toContain('shared-private-secret');
		await mcpRequest('PATCH', `${org}/${created.server.id}/activation`, { is_active: true, config_version: 1 });
		setMcpTutorialProfile('admin');
		await mcpRequest('DELETE', `${org}/${created.server.id}`);
		setMcpTutorialProfile('on');
		await expect(mcpRequest('PATCH', `${org}/${created.server.id}/activation`, { is_active: true, config_version: 1 })).rejects.toMatchObject({ status: 404 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('keeps complete owned/global lists independent of gallery pages and rejects cross-owner writes', async () => {
		const created = await mcpRequest<TutorialMcpCreated>('POST', '/mcp-connections', { template_id: 'mock-reg-github' });
		const custom = await mcpRequest<TutorialMcpConnection>('POST', '/mcp-servers', { name: 'Custom remote', transport: 'sse', url: 'https://custom.example.test/mcp' });
		expect((await mcpRequest<TutorialMcpSettings>('GET', '/mcp-settings?limit=1')).custom_connections).toEqual([expect.objectContaining({ id: custom.id, template_key: null })]);
		const all = await mcpRequest<TutorialMcpConnection[]>('GET', '/mcp-servers');
		expect(all.map(row => row.id)).toEqual(expect.arrayContaining([101, 102, 103, created.server.id, custom.id]));
		setMcpTutorialProfile('admin');
		expect((await mcpRequest<TutorialMcpConnection[]>('GET', '/mcp-servers')).map(row => row.id)).not.toContain(created.server.id);
		await expect(mcpRequest('DELETE', `/mcp-connections/${created.server.id}`)).rejects.toMatchObject({ status: 404 });
		setMcpTutorialProfile('on');
		await expect(mcpRequest('PATCH', '/mcp-servers/103', { is_active: false })).rejects.toMatchObject({ status: 403 });
		await expect(mcpRequest('POST', '/mcp-servers', { name: 'Secret custom', url: 'https://custom.example.test/mcp', headers: { Authorization: 'secret' } })).rejects.toMatchObject({ status: 400 });
		await mcpRequest('DELETE', `/mcp-servers/${custom.id}`);
		expect(await mcpRequest('GET', '/custom-tools')).toEqual([]);
		expect(await mcpRequest('GET', '/skills')).toEqual([]);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('keeps featured global installation idempotent, explicit-selection-only, and system-admin-only', async () => {
		await expect(mcpRequest('POST', '/admin/mcp-registry/install-featured', {})).rejects.toMatchObject({ status: 403 });
		setMcpTutorialProfile('admin');
		const registry = await mcpRequest<{ entries: TutorialMcpEntry[] }>('GET', '/admin/mcp-registry');
		expect(Object.keys(registry)).toEqual(['entries']);
		expect(registry.entries).toHaveLength(19);
		expect(registry.entries.find(entry => entry.id === 'mock-reg-offline')).toMatchObject({ access: 'unreachable', unavailable_reason: 'unverified_response' });
		const first = await mcpRequest<{ counts: { created: number; existing: number; skipped: number; failed: number } }>('POST', '/admin/mcp-registry/install-featured', {});
		expect(first.counts).toEqual({ created: 3, existing: 1, skipped: 2, failed: 0 });
		const repeated = await mcpRequest<typeof first>('POST', '/admin/mcp-registry/install-featured', {});
		expect(repeated.counts).toEqual({ created: 0, existing: 4, skipped: 2, failed: 0 });
		const global = await mcpRequest<TutorialMcpConnection[]>('GET', '/admin/mcp-servers');
		expect(global.every(row => row.scope === 'global' && !row.implicit_selection && row.server_is_active)).toBe(true);
		expect((await mcpRequest<TutorialMcpConnection[]>('GET', '/mcp-servers')).every(row => !row.is_active)).toBe(true);
		const brave = global.find(row => row.template_key === 'com.brave/search')!;
		expect(brave).toMatchObject({ has_headers: false, auth_connected: false, state: 'needs_auth' });
		await mcpRequest('PATCH', `/admin/mcp-servers/${brave.id}`, { headers: { Authorization: 'global-secret' }, load_policy: 'preloaded' });
		expect(JSON.stringify(await mcpRequest('GET', '/admin/mcp-servers'))).not.toContain('global-secret');
		expect(await mcpRequest('PATCH', `/admin/mcp-servers/${brave.id}`, { is_active: false })).toMatchObject({ is_active: false, server_is_active: false });
		await mcpRequest('DELETE', `/admin/mcp-servers/${brave.id}`);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('rejects stale, foreign, corrupt, or reset tutorial OAuth approval state', async () => {
		const created = await mcpRequest<TutorialMcpCreated>('POST', '/mcp-connections', { template_id: 'mock-reg-github' });
		const id = created.server.id;
		const stale = await mcpRequest<{ authorization_url: string }>('POST', `/mcp-servers/${id}/oauth/start`);
		await mcpRequest('PATCH', `/mcp-connections/${id}`, { is_active: false });
		window.history.replaceState({}, '', stale.authorization_url);
		expect(await mcpRequest('GET', `/mcp-servers/${id}/oauth`)).toMatchObject({ connected: false });
		window.history.replaceState({}, '', '/');
		const foreign = await mcpRequest<{ authorization_url: string }>('POST', `/mcp-servers/${id}/oauth/start`);
		const callback = new URL(foreign.authorization_url, window.location.origin);
		callback.searchParams.set('tutorial', 'admin');
		window.history.replaceState({}, '', callback.pathname + callback.search);
		expect((await mcpRequest<TutorialMcpConnection[]>('GET', '/mcp-servers')).map(row => row.id)).not.toContain(id);
		setMcpTutorialProfile('on');
		expect(await mcpRequest('GET', `/mcp-servers/${id}/oauth`)).toMatchObject({ connected: false });
		window.history.replaceState({}, '', '/');
		sessionStorage.setItem('afterglow.mockup.mcp-oauth', '{invalid');
		window.history.replaceState({}, '', '/?mock_mcp_oauth=invalid');
		expect(await mcpRequest('GET', `/mcp-servers/${id}/oauth`)).toMatchObject({ connected: false });
		window.history.replaceState({}, '', '/');
		const reset = await mcpRequest<{ authorization_url: string }>('POST', `/mcp-servers/${id}/oauth/start`);
		const { resetMockupState } = await import('./state');
		resetMockupState();
		expect(sessionStorage.getItem('afterglow.mockup.mcp-oauth')).toBeNull();
		window.history.replaceState({}, '', reset.authorization_url);
		await expect(mcpRequest('GET', `/mcp-servers/${id}/oauth`)).rejects.toMatchObject({ status: 404 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('validates configurable templates and owner publication while keeping global consent revision-bound', async () => {
		await expect(mcpRequest('POST', '/mcp-connections', { template_id: 'mock-reg-cloudflare' })).rejects.toMatchObject({ status: 400 });
		await expect(mcpRequest('POST', '/mcp-connections', { template_id: 'mock-reg-cloudflare', variables: { account: 'bad/path' } })).rejects.toMatchObject({ status: 400 });
		await expect(mcpRequest('POST', '/mcp-connections', { template_id: 'unknown-template' })).rejects.toMatchObject({ status: 404 });
		const configured = await mcpRequest<TutorialMcpCreated>('POST', '/mcp-connections', { template_id: 'mock-reg-cloudflare', variables: { account: 'demo-account' }, auth_mode: 'none' });
		expect(configured.server).toMatchObject({ url: 'https://demo-account.mcp.example.test/mcp', is_active: true, activation_config_version: null });
		const disabled = await mcpRequest<TutorialMcpConnection>('PATCH', `/mcp-connections/${configured.server.id}`, { is_active: false });
		expect(disabled).toMatchObject({ state: 'not_connected', is_active: false, server_is_active: false, config_version: 2 });
		const enabled = await mcpRequest<TutorialMcpConnection>('PATCH', `/mcp-connections/${configured.server.id}`, { is_active: true });
		expect(enabled).toMatchObject({ state: 'personal_connected', is_active: true, server_is_active: true, config_version: 3, activation_config_version: null });
		await expect(mcpRequest('PATCH', '/mcp-servers/103/activation', { is_active: true })).rejects.toMatchObject({ status: 400 });
		await expect(mcpRequest('PATCH', '/mcp-servers/103/activation', { is_active: true, config_version: 0 })).rejects.toMatchObject({ status: 409 });
		expect(await mcpRequest('PATCH', '/mcp-servers/103/activation', { is_active: true, config_version: 1 })).toMatchObject({ state: 'global_connected', is_active: true, activation_generation: 1 });
		expect(await mcpRequest('PATCH', '/mcp-servers/103/activation', { is_active: false, config_version: 1 })).toMatchObject({ state: 'not_connected', is_active: false, activation_generation: 2 });
		await expect(mcpRequest('POST', '/mcp-servers', { name: 'Unsafe', url: 'https://user:password@example.test/mcp' })).rejects.toMatchObject({ status: 400 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('revokes personal OAuth credentials and consent instead of reporting a successful connection after disconnect', async () => {
		const personal = await mcpRequest<TutorialMcpCreated>('POST', '/mcp-connections', { template_id: 'mock-reg-notion' });
		const id = personal.server.id;
		const start = await mcpRequest<{ authorization_url: string }>('POST', `/mcp-servers/${id}/oauth/start`);
		window.history.replaceState({}, '', start.authorization_url);
		expect(await mcpRequest('GET', `/mcp-servers/${id}/oauth`)).toMatchObject({ connected: true });
		await mcpRequest('DELETE', `/mcp-servers/${id}/oauth`);
		expect(await mcpRequest('GET', `/mcp-servers/${id}/oauth`)).toMatchObject({ connected: false });
		expect((await mcpRequest<TutorialMcpConnection[]>('GET', '/mcp-servers')).find(row => row.id === id)).toMatchObject({ is_active: false, activation_is_active: false, state: 'needs_auth' });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('supports the existing admin loader, single install, bulk install, and global publishing controls', async () => {
		await expect(mcpRequest('GET', '/admin/custom-tools')).rejects.toMatchObject({ status: 403 });
		setMcpTutorialProfile('admin');
		expect(await mcpRequest('GET', '/admin/custom-tools')).toEqual([]);
		expect(await mcpRequest('GET', '/admin/skills')).toEqual([]);
		const single = await mcpRequest<TutorialMcpCreated>('POST', '/admin/mcp-registry/mock-reg-context7/install');
		expect(single).toMatchObject({ created: true, server: { scope: 'global', implicit_selection: false } });
		const all = await mcpRequest<{ counts: { failed: number }; skipped: { reason: string }[] }>('POST', '/admin/mcp-registry/install-all');
		expect(all.counts.failed).toBe(0);
		expect(all.skipped).toEqual(expect.arrayContaining([expect.objectContaining({ reason: 'configuration_required' }), expect.objectContaining({ reason: 'stdio_only' }), expect.objectContaining({ reason: 'unverified_response' })]));
		const created = await mcpRequest<TutorialMcpConnection>('POST', '/admin/mcp-servers', { name: 'Global remote', url: 'https://global.example.test/mcp', transport: 'http', auth_mode: 'oauth', oauth_client_id: 'fixture-public-client', oauth_client_secret: 'never-save-global-client-secret', oauth_scopes: ['read'], load_policy: 'preloaded' });
		expect(created).toMatchObject({ scope: 'global', is_active: true, has_oauth_client: true, has_oauth_client_secret: true, oauth_scopes: ['read'], load_policy: 'preloaded' });
		expect(JSON.stringify(created)).not.toContain('never-save-global-client-secret');
		expect(await mcpRequest('PATCH', `/admin/mcp-servers/${created.id}`, { is_active: false })).toMatchObject({ is_active: false, server_is_active: false, config_version: 2 });
		await mcpRequest('DELETE', `/admin/mcp-servers/${created.id}`);
		expect(fetchMock).not.toHaveBeenCalled();
	});
});

describe('mockup transport', () => {
	it('provides a selectable tutorial flavor composition preview and saves only valid CPU tuples', async () => {
		const { maybeMockJson } = await import('./transport');
		const token = 'mock-token-tutorial-scoped';
		const project = 'mock-project-1';
		const options = await maybeMockJson<{ variants: { preview: { id: string } | null; regions: { vcpus: { min: number } }[] }[] }>(
			'GET', '/api/v1/flavors/composer-options', undefined, token, project,
		);
		if (typeof options === 'symbol') throw new Error('Expected tutorial composer options');
		expect(options.variants[0]).toMatchObject({ preview: { id: 'composer-preview' }, regions: [{ vcpus: { min: 1 } }] });
		const composition = { vcpus: 4, ram_mb: 8192, gpu_profile_id: null, gpu_count: 0 };
		const saved = await maybeMockJson<{ id: string; composition: typeof composition; vcpus: number; ram: number }>(
			'POST', '/api/v1/flavors/compositions?operation_id=mock-operation', composition, token, project,
		);
		if (typeof saved === 'symbol') throw new Error('Expected saved synthetic flavor');
		expect(saved).toMatchObject({ id: 'mock-flavor-composed-4c-8192m', composition, vcpus: 4, ram: 8192 });
		const history = await maybeMockJson<{ items: { id: string }[] }>('GET', '/api/v1/flavors/compositions', undefined, token, project);
		if (typeof history === 'symbol') throw new Error('Expected synthetic composition history');
		expect(history.items).toEqual([expect.objectContaining({ id: saved.id })]);
		await expect(maybeMockJson('POST', '/api/v1/flavors/compositions', { ...composition, vcpus: 3 }, token, project)).rejects.toMatchObject({ status: 409 });
		expect(fetchMock).not.toHaveBeenCalled();
	});
	it('serves synthetic embedding models and vectors only in tutorial mode', async () => {
		const { maybeMockJson } = await import('./transport');
		const token = 'mock-token-tutorial-scoped';
		const project = 'mock-project-1';
		const models = await maybeMockJson<Array<{ id: number; model_kind: string }>>(
			'GET', '/api/v1/chat/models?model_kind=embedding', undefined, token, project,
		);
		expect(models).toEqual([expect.objectContaining({ id: 42, model_kind: 'embedding' })]);
		const capabilities = await maybeMockJson<{ max_inputs: number }>(
			'GET', '/api/v1/chat/capabilities?model_id=42&model_kind=embedding', undefined, token, project,
		);
		expect(capabilities).toMatchObject({ model_id: 42, max_inputs: 16, supports_dimensions: true });
		const result = await maybeMockJson<{ embeddings: { embedding: number[] }[]; usage: { estimated: boolean } }>(
			'POST', '/api/v1/chat/embeddings', { model_id: 42, input: ['vector'], dimensions: 2 }, token, project,
		);
		expect(result).toMatchObject({ dimensions: 2, embeddings: [{ index: 0, embedding: [1, 0] }], usage: { estimated: true } });
		expect(fetchMock).not.toHaveBeenCalled();
	});


	it('serves native Key Manager metadata arrays without payloads and rejects invalid secret creation', async () => {
		// resetModules must recreate the tutorial singleton for this transport-boundary test.
		const { maybeMockJson } = await import('./transport');
		const token = 'mock-token-tutorial-scoped';
		const project = 'mock-project-1';
		const secrets = await maybeMockJson<SecretInfo[]>('GET', '/api/v1/secrets', undefined, token, project);
		const containers = await maybeMockJson<ContainerInfo[]>('GET', '/api/v1/secret-containers', undefined, token, project);
		const orders = await maybeMockJson<OrderInfo[]>('GET', '/api/v1/secret-orders', undefined, token, project);
		const quota = await maybeMockJson<QuotaInfo>('GET', '/api/v1/secrets/quota/effective', undefined, token, project);
		if (!Array.isArray(secrets) || !Array.isArray(containers) || !Array.isArray(orders)) throw new Error('Expected native Key Manager arrays');
		expect(secrets.length).toBeGreaterThan(0);
		expect(secrets.every(secret => typeof secret.id === 'string' && typeof secret.system_managed === 'boolean')).toBe(true);
		for (const secret of secrets) expect(secret).not.toHaveProperty('payload');
		expect(containers[0].secret_refs).toEqual(expect.arrayContaining([expect.objectContaining({ name: 'api-password', secret_ref: expect.any(String) })]));
		expect(orders.map(order => order.status)).toEqual(['ACTIVE', 'PENDING']);
		expect(quota).toMatchObject({ secrets: 50, orders: 20, containers: 20, consumers: 100, cas: 5 });
		await expect(maybeMockJson('GET', `/api/v1/secrets/${secrets[0].id}/payload`, undefined, token, project)).rejects.toMatchObject({ status: 409 });
		await expect(maybeMockJson('POST', '/api/v1/secrets', {}, token, project)).rejects.toMatchObject({ status: 422 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('uses the native container envelope for inventory and unwraps it for My Resources', async () => {
		// resetModules recreates the mutable tutorial singleton at this transport boundary.
		const { maybeMockJson } = await import('./transport');
		const response = await maybeMockJson('GET', '/api/v1/containers', undefined, 'mock-token-tutorial-scoped', 'mock-project-1');
		expect(parseContainerListResponse(response)).toEqual({ items: [], service_available: true, message: '' });
		const summary = await maybeMockJson<UserDashboardSummary>('GET', '/api/v1/user-dashboard/summary', undefined, 'mock-token-tutorial-scoped', 'mock-project-1');
		if (!summary || typeof summary !== 'object' || !('projects' in summary)) throw new Error('Expected tutorial user-dashboard summary');
		expect(summary.projects.find(project => project.project_id === 'mock-project-1')?.resources.containers).toMatchObject({ state: 'ready', count: 0, items: [] });
		expect(fetchMock).not.toHaveBeenCalled();
	});
	it('serves domain-owned administrator resource totals without the retired project quota monitor', async () => {
		sessionStorage.setItem(MOCKUP_SESSION_KEY, 'admin');
		// Module-boundary test: vi.resetModules recreates the mutable fixture singleton.
		const { maybeMockJson } = await import('./transport');
		const totals = await maybeMockJson('GET', '/api/v1/admin/overview/domains', undefined, 'mock-token-admin-scoped', 'mock-project-1');
		expect(totals).toEqual([expect.objectContaining({
			domain_id: 'mock-domain', domain_name: 'Demo', owner_status: 'known', project_count: 4,
			instances: 49, vcpus: 228, ram_mb: 593920, gpu_instances: 8,
			volumes: 20, volume_gb: 8950, attached_volumes: 14, attached_gb: 7200, available_volumes: 6, available_gb: 1750,
		})]);
		expect(fetchMock).not.toHaveBeenCalled();
	});
	it('serves native-shaped administrator notifications and the existing recent-events read', async () => {
		sessionStorage.setItem(MOCKUP_SESSION_KEY, 'admin');
		// Module-boundary test: resetModules recreates the mutable fixture singleton.
		const { maybeMockJson } = await import('./transport');
		const notices = await maybeMockJson('GET', '/api/v1/admin/notifications', undefined, 'mock-token-admin-scoped', 'mock-project-1');
		expect(notices).toEqual({ notifications: expect.arrayContaining([expect.objectContaining({ type: 'error', severity: 'high', count: 3 })]), total: 3 });
		const events = await maybeMockJson('GET', '/api/v1/admin/events?limit=5', undefined, 'mock-token-admin-scoped', 'mock-project-1');
		expect(events).toEqual(expect.arrayContaining([expect.objectContaining({ id: 1001, status: 'failed', action: 'create', resource_id: 'mock-instance-6' })]));
		expect(fetchMock).not.toHaveBeenCalled();
	});
	it('projects native instance ownership for the project VM metrics picker', async () => {
		// resetModules recreates the transport's mutable tutorial state for each test.
		const { maybeMockJson } = await import('./transport');
		const rows = await maybeMockJson<Array<{ id: string; project_id: string }>>(
			'GET', '/api/v1/instances', undefined, 'mock-token-tutorial-scoped', 'mock-project-1',
		);
		expect(rows).toEqual(expect.any(Array));
		if (!Array.isArray(rows)) throw new Error('Expected the native instance list shape');
		expect(rows.length).toBeGreaterThan(0);
		expect(rows.every((row) => row.project_id === 'mock-project-1')).toBe(true);
		const selected = rows[0];
		const detail = await maybeMockJson('GET', `/api/v1/instances/${selected.id}`, undefined, 'mock-token-tutorial-scoped', 'mock-project-1');
		expect(detail).toMatchObject({ id: selected.id, project_id: 'mock-project-1' });
		expect(fetchMock).not.toHaveBeenCalled();
	});
	it('serves supported JSON reads and applies local instance mutations to later GETs', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockJson } = await import('./transport');
		const instancesBefore = (await maybeMockJson<Array<{ id: string; status: string }>>(
			'GET',
			'/api/v1/instances',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Array<{ id: string; status: string }>;
		const stopped = instancesBefore.find((instance) => instance.status === 'SHUTOFF');

		expect(stopped).toBeTruthy();

		await maybeMockJson(
			'POST',
			`/api/v1/instances/${stopped!.id}/start`,
			{},
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);
		const instancesAfter = (await maybeMockJson<Array<{ id: string; status: string }>>(
			'GET',
			'/api/v1/instances',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Array<{ id: string; status: string }>;

		expect(instancesAfter.find((instance) => instance.id === stopped!.id)?.status).toBe('ACTIVE');
		const consoleTarget = (await maybeMockJson<{ url: string }>(
			'GET',
			`/api/v1/instances/${stopped!.id}/console`,
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as { url: string };

		expect(consoleTarget).toEqual({ url: '/mockup-console.html' });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('returns only authoritative MCP project IDs and names', async () => {
		// Module-boundary test: vi.resetModules recreates the mutable fixture singleton.
		const { maybeMockJson } = await import('./transport');
		const projects = await maybeMockJson('GET', '/api/v1/auth/mcp-projects', undefined, 'mock-token-tutorial-scoped', 'mock-project-1');
		expect(projects).toEqual([
			{ id: 'mock-project-1', name: 'sample-project-alpha' },
			{ id: 'mock-project-2', name: 'sample-project-beta' },
			{ id: 'mock-project-3', name: 'sample-ci-runner' },
		]);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('enriches only an explicit MCP preview with independent tutorial service authority', async () => {
		// vi.resetModules recreates the mutable transport singleton for this module-boundary test.
		const { maybeMockJson } = await import('./transport');
		const preview = await maybeMockJson<Array<{ id: string; can_write: boolean; service_permissions: Record<string, string[]>; service_errors: Record<string, string> }>>(
			'GET', '/api/v1/auth/mcp-projects?preview=true', undefined, 'mock-token-tutorial-scoped', 'mock-project-1',
		);
		if (!Array.isArray(preview)) throw new Error('Expected the tutorial MCP preview fixture');
		expect(preview).toHaveLength(3);
		expect(preview[0]).toMatchObject({
			id: 'mock-project-1', can_write: true, service_errors: {},
			service_permissions: { drover: expect.arrayContaining(['drover-inventory_reader', 'drover-clusters_editor']) },
		});
		expect(preview[0].service_permissions).not.toHaveProperty('lumen');
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('reports managed default and selected personal cloud metadata without an integer tool ID', async () => {
		// Module-boundary test: reset the mutable transport singleton per scenario.
		const { maybeMockJson } = await import('./transport');
		const token = 'mock-token-tutorial-scoped';
		await maybeMockJson('DELETE', '/api/v1/auth/mcp-tokens/lumen-default', undefined, token, 'mock-project-1');
		const builtIn = await maybeMockJson('GET', '/api/v1/chat/cloud-tools', undefined, token, 'mock-project-2');
		expect(builtIn).toMatchObject({ available: true, enabled: false, source: 'lumen', allowed_projects: [], tool_count: 0 });
		await maybeMockJson('POST', '/api/v1/chat/cloud-tools', { access_level: 'read' }, token, 'mock-project-2');
		expect(await maybeMockJson('GET', '/api/v1/chat/cloud-tools', undefined, token, 'mock-project-2')).toMatchObject({ enabled: true, access_level: 'read', allowed_projects: [{ id: 'mock-project-2', name: 'sample-project-beta' }] });
		await maybeMockJson('DELETE', '/api/v1/chat/cloud-tools', undefined, token, 'mock-project-2');
		expect(await maybeMockJson('GET', '/api/v1/chat/cloud-tools', undefined, token, 'mock-project-2')).toMatchObject({ enabled: false, allowed_projects: [] });
		expect(builtIn).not.toHaveProperty('id');
		const issued = await maybeMockJson<{ id: string }>('POST', '/api/v1/auth/mcp-tokens', { name: 'Operations', access_level: 'manage', project_scope: 'all', project_ids: [] }, token, 'mock-project-1') as { id: string };
		await maybeMockJson('PUT', `/api/v1/auth/mcp-tokens/${issued.id}/lumen-default`, {}, token, 'mock-project-1');
		const selected = await maybeMockJson('GET', '/api/v1/chat/cloud-tools', undefined, token, 'mock-project-1');
		expect(selected).toMatchObject({ source: 'personal_token', access_level: 'manage', selection_name: 'Operations', allowed_projects: expect.arrayContaining([{ id: 'mock-project-3', name: 'sample-ci-runner' }]) });
		expect(selected).not.toHaveProperty('id');
		expect(await maybeMockJson('GET', '/api/v1/chat/custom-tools', undefined, token, 'mock-project-1')).toEqual([]);
		expect(await maybeMockJson('GET', '/api/v1/chat/mcp-servers', undefined, token, 'mock-project-1')).toEqual(expect.arrayContaining([
			expect.objectContaining({ id: 101, scope: 'domain', is_active: false }),
			expect.objectContaining({ id: 103, scope: 'global', implicit_selection: false, is_active: false }),
		]));
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('rejects empty selected projects and OAuth access beyond client scopes', async () => {
		// Module-boundary test: fixtures must not retain mutations from another test.
		const { maybeMockJson } = await import('./transport');
		await expect(maybeMockJson('POST', '/api/v1/auth/mcp-tokens', { name: 'Empty', access_level: 'read', project_scope: 'selected', project_ids: [] }, 'mock-token-tutorial-scoped', 'mock-project-1')).rejects.toMatchObject({ status: 400 });
		await expect(maybeMockJson('POST', `/api/v1/auth/mcp-oauth/consents/${MOCK_MCP_CONSENT_TICKET}/approve`, { access_level: 'manage', project_scope: 'all', project_ids: [] }, 'mock-token-tutorial-scoped', 'mock-project-1')).rejects.toMatchObject({ status: 409 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('keeps aborted tutorial issuance out of saved records and accepts scoped no-store mutations locally', async () => {
		// Module-boundary test: recreate the API client and mutable tutorial fixture.
		const { api } = await import('$lib/api/client');
		const token = 'mock-token-tutorial-scoped';
		const project = 'mock-project-1';
		const before = await api.get<Record<string, unknown>[]>('/api/v1/auth/mcp-tokens', token, project, { refresh: true });
		const controller = new AbortController();
		controller.abort();
		const body = { name: 'Scoped tutorial', access_level: 'read', project_scope: 'selected', project_ids: ['mock-project-2'] };
		await expect(api.post('/api/v1/auth/mcp-tokens', body, token, project, { signal: controller.signal, cache: 'no-store', suppressAuthRedirect: true })).rejects.toMatchObject({ name: 'AbortError' });
		expect(await api.get('/api/v1/auth/mcp-tokens', token, project, { refresh: true })).toEqual(before);
		const issued = await api.post<{ id: string; token: string }>('/api/v1/auth/mcp-tokens', body, token, project, { signal: new AbortController().signal, cache: 'no-store', suppressAuthRedirect: true });
		expect(issued.token).toMatch(/^sk-afgl-mock-/);
		const saved = await api.get<Record<string, unknown>[]>('/api/v1/auth/mcp-tokens', token, project, { refresh: true });
		const record = saved.find((item) => item.id === issued.id);
		expect(record).toMatchObject({ project_scope: 'selected', project_ids: ['mock-project-2'], projects: [{ id: 'mock-project-2', name: 'sample-project-beta' }] });
		expect(record).not.toHaveProperty('token');
		await api.put(`/api/v1/auth/mcp-tokens/${issued.id}/lumen-default`, {}, token, project);
		expect(await api.get('/api/v1/chat/cloud-tools', token, project, { refresh: true })).toMatchObject({ project_id: 'mock-project-1', source: 'personal_token', selection_name: 'Scoped tutorial', allowed_projects: [{ id: 'mock-project-2', name: 'sample-project-beta' }] });
		expect(await api.post(`/api/v1/auth/mcp-oauth/consents/${MOCK_MCP_CONSENT_TICKET}/approve`, { access_level: 'read', project_scope: 'all', project_ids: [] }, token, project, { signal: new AbortController().signal, cache: 'no-store', suppressAuthRedirect: true })).toEqual({ redirect_uri: '/dashboard/account?tutorial=on', effective_ongoing: false });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it.each([
		{ lifetime: 'never', expiration: { non_expiring: true }, expectedExpiry: null },
		{ lifetime: 'finite', expiration: { expires_at: '2027-07-09T00:00:00.000Z' }, expectedExpiry: '2027-07-09T00:00:00.000Z' },
	])('preserves $lifetime MCP expiry through the tutorial API consumer', async ({ expiration, expectedExpiry }) => {
		// Module-boundary test: the real API consumer uses fresh local tutorial state.
		const { api } = await import('$lib/api/client');
		const token = 'mock-token-tutorial-scoped';
		const project = 'mock-project-1';
		const approved = await api.post<{ expires_at: string | null }>('/api/v1/chat/cloud-tools', { access_level: 'read' }, token, project);
		expect(approved.expires_at).not.toBeNull();
		const issued = await api.post<{ id: string; token: string; expires_at: string | null; issued_at: string }>(
			'/api/v1/auth/mcp-tokens',
			{ name: 'Tutorial expiry', access_level: 'read', project_scope: 'selected', project_ids: [project], ...expiration },
			token,
			project,
			{ signal: new AbortController().signal, cache: 'no-store', suppressAuthRedirect: true },
		);
		expect(issued.expires_at).toBe(expectedExpiry);
		expect(issued.token).toMatch(/^sk-afgl-mock-/);
		const saved = await api.get<Record<string, unknown>[]>('/api/v1/auth/mcp-tokens', token, project, { refresh: true });
		const record = saved.find((item) => item.id === issued.id);
		expect(record).toMatchObject({ expires_at: expectedExpiry, status: 'active' });
		expect(record).not.toHaveProperty('token');
		await api.put(`/api/v1/auth/mcp-tokens/${issued.id}/lumen-default`, {}, token, project);
		expect(await api.get('/api/v1/chat/cloud-tools', token, project, { refresh: true })).toMatchObject({
			source: 'personal_token', selection_name: 'Tutorial expiry', expires_at: expectedExpiry,
		});
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('models MCP access lifecycle without retaining one-time token plaintext', async () => {
		const { maybeMockJson } = await import('./transport');
		const created = (await maybeMockJson<{
			id: string;
			token: string;
			is_lumen_default: boolean;
			visible_prefix: string;
		}>(
			'POST',
			'/api/v1/auth/mcp-tokens',
			{ name: 'Tutorial client', access_level: 'manage', project_scope: 'selected', project_ids: ['mock-project-1', 'mock-project-2'] },
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as { id: string; token: string; is_lumen_default: boolean; visible_prefix: string };

		expect(created.token).toMatch(/^sk-afgl-mock-/);
		const tokens = (await maybeMockJson<Array<Record<string, unknown>>>(
			'GET',
			'/api/v1/auth/mcp-tokens',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Array<Record<string, unknown>>;
		const createdRecord = tokens.find((record) => record.id === created.id);

		expect(createdRecord).toMatchObject({ visible_prefix: created.visible_prefix, status: 'active', project_scope: 'selected', project_ids: ['mock-project-1', 'mock-project-2'], projects: [{ id: 'mock-project-1', name: 'sample-project-alpha' }, { id: 'mock-project-2', name: 'sample-project-beta' }] });
		expect(createdRecord).not.toHaveProperty('token');

		await maybeMockJson(
			'PUT',
			`/api/v1/auth/mcp-tokens/${created.id}/lumen-default`,
			{},
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);
		await maybeMockJson(
			'DELETE',
			'/api/v1/auth/mcp-oauth/grants/mock-mcp-oauth-grant-desktop',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);
		await maybeMockJson(
			'DELETE',
			`/api/v1/auth/mcp-tokens/${created.id}`,
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);
		const updatedTokens = (await maybeMockJson<Array<Record<string, unknown>>>(
			'GET',
			'/api/v1/auth/mcp-tokens',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Array<Record<string, unknown>>;
		const grants = (await maybeMockJson<Array<Record<string, unknown>>>(
			'GET',
			'/api/v1/auth/mcp-oauth/grants',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Array<Record<string, unknown>>;

		expect(updatedTokens.some((record) => record.id === created.id)).toBe(false);
		expect(grants.some((record) => record.grant_id === 'mock-mcp-oauth-grant-desktop')).toBe(false);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('serves one valid MCP consent ticket and maps either decision to the local return route', async () => {
		const { maybeMockJson } = await import('./transport');
		const consent = await maybeMockJson<{
			client_name: string;
			redirect_uri: string;
			scopes: string[];
		}>(
			'GET',
			`/api/v1/auth/mcp-oauth/consents/${MOCK_MCP_CONSENT_TICKET}`,
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);
		const decision = await maybeMockJson<{ redirect_uri: string }>(
			'POST',
			`/api/v1/auth/mcp-oauth/consents/${MOCK_MCP_CONSENT_TICKET}/approve`,
			{ access_level: 'read', project_scope: 'selected', project_ids: ['mock-project-1'], ongoing: true },
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);

		expect(consent).toEqual(expect.objectContaining({
			client_name: 'Tutorial Desktop MCP',
			redirect_uri: 'http://mock-client.example.test/oauth/callback',
			scopes: ['mcp:read'],
			ongoing_supported: true,
		}));
		expect(decision).toEqual({ redirect_uri: '/dashboard/account?tutorial=on', effective_ongoing: true });
		await expect(
			maybeMockJson(
				'GET',
				'/api/v1/auth/mcp-oauth/consents/not-a-valid-ticket',
				undefined,
				'mock-token-tutorial-scoped',
				'mock-project-1',
			),
		).rejects.toMatchObject({ status: 409 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('publishes and reuses warm API-client data entirely inside mock transport', async () => {
		const { api } = await import('$lib/api/client');
		await api.prefetch<Array<{ id: string; name: string }>>(
			'/api/v1/instances',
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);

		const first = await api.get<Array<{ id: string; name: string }>>(
			'/api/v1/instances',
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);
		first[0].name = 'caller mutation';
		const second = await api.get<Array<{ id: string; name: string }>>(
			'/api/v1/instances',
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);

		expect(second[0].name).not.toBe('caller mutation');
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('serves the direct file-storage catalog with query parameters without network access', async () => {
		const { maybeMockJson } = await import('./transport');
		const catalog = await maybeMockJson<Array<{ id: string; share_proto: string }>>(
			'GET',
			'/api/v1/file-storage?cache=true',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);

		expect(catalog).toEqual(expect.arrayContaining([
			expect.objectContaining({ id: 'mock-share-1', share_proto: 'CEPHFS' }),
		]));
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('streams fake k3s progress and exposes the created cluster on subsequent reads', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockJson, maybeMockK3sStream } = await import('./transport');
		const clustersBefore = (await maybeMockJson<K3sCluster[]>(
			'GET',
			'/api/v1/k3s/clusters',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as K3sCluster[];
		const progress = maybeMockK3sStream(
			'/api/v1/k3s/clusters/async',
			{ name: 'tutorial-created-cluster', agent_count: 2, os_type: 'ubuntu' },
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);
		const messages: K3sSseProgressMessage[] = [];

		expect(progress).not.toBeNull();

		for await (const message of progress!) {
			messages.push(message);
		}

		expect(messages.length).toBeGreaterThan(0);
		expect(messages.at(-1)).toMatchObject({ step: 'completed' });

		const clustersAfter = (await maybeMockJson<K3sCluster[]>(
			'GET',
			'/api/v1/k3s/clusters',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as K3sCluster[];

		expect(clustersAfter).toHaveLength(clustersBefore.length + 1);
		expect(clustersAfter.some((cluster) => cluster.name === 'tutorial-created-cluster')).toBe(true);
	});

	it('serves K3s detail and health contracts, including deleted clusters on request', async () => {
		// Dynamic import reinitializes the mutable mock fixture with the session-scoped profile.
		const { maybeMockJson, maybeMockK3sStream } = await import('./transport');
		const clusters = (await maybeMockJson<K3sCluster[]>('GET', '/api/v1/k3s/clusters')) as K3sCluster[];
		const active = clusters.find((cluster) => cluster.status === 'ACTIVE');

		expect(active).toBeTruthy();
		const detail = await maybeMockJson<K3sCluster>('GET', `/api/v1/k3s/clusters/${active!.id}`);
		const health = (await maybeMockJson<{
			status: string;
			api_server_reachable: boolean;
			healthz_ok: boolean;
			nodes: { ready: boolean; kubelet_version: string | null }[];
			error: string | null;
		}>('GET', `/api/v1/k3s/clusters/${active!.id}/health`)) as {
			status: string;
			api_server_reachable: boolean;
			healthz_ok: boolean;
			nodes: { ready: boolean; kubelet_version: string | null }[];
			error: string | null;
		};

		expect(detail).toMatchObject({ id: active!.id, status: 'ACTIVE' });
		expect(health).toMatchObject({
			status: 'HEALTHY',
			api_server_reachable: true,
			healthz_ok: true,
			error: null,
		});
		expect(health.nodes).toEqual(expect.arrayContaining([expect.objectContaining({ ready: true, kubelet_version: 'v1.30.4+k3s1' })]));

		const deletion = maybeMockK3sStream(`/api/v1/k3s/clusters/${active!.id}/delete-async`, {}, undefined, undefined);
		expect(deletion).not.toBeNull();
		const current = (await maybeMockJson<K3sCluster[]>('GET', '/api/v1/k3s/clusters')) as K3sCluster[];
		const withDeleted = (await maybeMockJson<K3sCluster[]>('GET', '/api/v1/k3s/clusters?include_deleted=true')) as K3sCluster[];

		expect(current.some((cluster) => cluster.id === active!.id)).toBe(false);
		expect(withDeleted).toContainEqual(expect.objectContaining({ id: active!.id, status: 'DELETED' }));
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('keeps the administrator mock fail-closed when project-token mutation is attempted', async () => {
		sessionStorage.clear();
		sessionStorage.setItem(MOCKUP_SESSION_KEY, 'admin');
		vi.resetModules();
		// Dynamic import reloads auth and transport against the administrator tab fixture.
		const { maybeMockJson } = await import('./transport');

		await expect(
			maybeMockJson('POST', '/api/v1/auth/token/project', { project_id: 'mock-project-2' }),
		).rejects.toMatchObject({
			status: 409,
			message: '튜토리얼 모드에서는 이 작업을 아직 지원하지 않습니다.',
		});
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it.each([
		['all-instances', ['mock-instance-6', 'mock-instance-4', 'mock-instance-1'], ['mock-instance-1', 'mock-instance-4', 'mock-instance-6']],
		['all-volumes', ['mock-admin-volume-error', 'mock-admin-volume-in-use', 'mock-admin-volume-available'], ['mock-admin-volume-error', 'mock-admin-volume-in-use', 'mock-admin-volume-available']],
	])('sorts %s before tutorial marker pagination', async (route, newestIds, nameDescIds) => {
		sessionStorage.setItem(MOCKUP_SESSION_KEY, 'admin');
		// resetModules isolates the mutable tutorial singleton for each route.
		const { maybeMockJson } = await import('./transport');
		type Page = { items: { id: string }[]; next_marker: string | null };
		const first = await maybeMockJson<Page>('GET', `/api/v1/admin/${route}?limit=2`) as Page;
		expect(first.items.map(item => item.id)).toEqual(newestIds.slice(0, 2));
		const second = await maybeMockJson<Page>('GET', `/api/v1/admin/${route}?limit=2&marker=${first.next_marker}`) as Page;
		expect([...first.items, ...second.items].map(item => item.id)).toEqual(newestIds);
		const named = await maybeMockJson<Page>('GET', `/api/v1/admin/${route}?limit=1&sort=name_desc`) as Page;
		expect(named.items[0].id).toBe(nameDescIds[0]);
		const nextNamed = await maybeMockJson<Page>('GET', `/api/v1/admin/${route}?limit=2&sort=name_desc&marker=${named.next_marker}`) as Page;
		expect([named.items[0], ...nextNamed.items].map(item => item.id)).toEqual(nameDescIds);
	});

	it('serves every administrator tour contract with filters and no network access', async () => {
		sessionStorage.clear();
		sessionStorage.setItem(MOCKUP_SESSION_KEY, 'admin');
		vi.resetModules();
		// Dynamic import reinitializes the administrator fixture for this contract matrix.
		const { maybeMockJson } = await import('./transport');

		const instances = await maybeMockJson<{ items: Array<{ id: string; status: string }>; count: number }>(
			'GET', '/api/v1/admin/all-instances?status=SHUTOFF&project_id=mock-project-2',
		);
		expect(instances).toMatchObject({ count: 1, items: [{ id: 'mock-instance-4', status: 'SHUTOFF' }] });
		expect(await maybeMockJson('GET', '/api/v1/admin/instances/health')).toMatchObject({ total: 3, gpu_count: 1 });
		expect(await maybeMockJson<Array<unknown>>('GET', '/api/v1/admin/timeseries/instances')).toHaveLength(7);
		expect(await maybeMockJson<Array<unknown>>('GET', '/api/v1/admin/hypervisors')).toHaveLength(3);

		const volumes = await maybeMockJson<{ items: Array<{ id: string; status: string }>; count: number }>(
			'GET', '/api/v1/admin/all-volumes?status=available',
		);
		expect(volumes).toMatchObject({ count: 1, items: [{ id: 'mock-admin-volume-available', status: 'available' }] });
		expect(await maybeMockJson('GET', '/api/v1/admin/volumes/status-summary')).toMatchObject({ total: 3 });
		expect(await maybeMockJson<Array<unknown>>('GET', '/api/v1/admin/timeseries/volumes')).toHaveLength(7);
		expect(await maybeMockJson('GET', '/api/v1/admin/volumes/mock-admin-volume-available')).toMatchObject({ status: 'available' });
		expect(await maybeMockJson('GET', '/api/v1/admin/volumes/mock-admin-volume-error/delete-diagnostics')).toMatchObject({
			root_cause_code: 'backend_present_consistent',
			recovery_available: true,
			backend: { mode: 'inspected', classification: 'consistent', pool: 'volumes' },
			checks: expect.arrayContaining([
				expect.objectContaining({ name: 'auth_preflight', state: 'present' }),
				expect.objectContaining({ name: 'rbd_image_by_name', state: 'present' }),
			]),
		});

		const databases = await maybeMockJson<Array<{ id: string; name: string; project_id: string }>>(
			'GET', '/api/v1/admin/database-instances',
		);
		expect(databases).toEqual([
			expect.objectContaining({ id: 'mock-trove-instance-1', name: 'sample-customer-mysql', project_id: 'mock-project-1' }),
		]);

		expect(await maybeMockJson('GET', '/api/v1/admin/topology')).toMatchObject({ routers: expect.any(Array) });
		expect(await maybeMockJson<Array<unknown>>('GET', '/api/v1/admin/all-containers')).toHaveLength(2);
		expect(await maybeMockJson('GET', '/api/v1/admin/object-storage')).toMatchObject({ items: [expect.objectContaining({ name: 'sample-artifacts', project_id: 'mock-project-1' })], partial: false, unavailable_projects: [] });
		expect(await maybeMockJson('GET', '/api/v1/admin/object-storage?domain_id=mock-domain&project_id=foreign')).toEqual({ items: [], project_count: 0, partial: false, unavailable_projects: [] });
		expect(await maybeMockJson('GET', '/api/v1/admin/containers/mock-container-1')).toMatchObject({ status: 'Running' });
		expect(await maybeMockJson('GET', '/api/v1/admin/containers/mock-container-1/logs')).toMatchObject({ logs: expect.stringContaining('ready') });
		expect(await maybeMockJson<Array<unknown>>('GET', '/api/v1/admin/key-manager/project-quotas')).toHaveLength(2);
		expect(await maybeMockJson('GET', '/api/v1/admin/monitoring/summary')).toMatchObject({ compute: { running_vms: 46 } });
		expect(await maybeMockJson('GET', '/api/v1/admin/services?category=compute')).toMatchObject({ compute: [expect.objectContaining({ binary: 'nova-compute' })] });
		expect(await maybeMockJson('GET', '/api/v1/admin/services?category=network')).toMatchObject({ network: [expect.objectContaining({ alive: true })] });
		expect(await maybeMockJson('GET', '/api/v1/admin/services?category=endpoints')).toMatchObject({ endpoints: [expect.any(Object)] });
		expect(await maybeMockJson('GET', '/api/v1/admin/services?category=storage_pools')).toMatchObject({ storage_pools: [expect.any(Object)] });
		expect(await maybeMockJson('GET', '/api/v1/admin/users?domain_id=mock-domain')).toMatchObject({ count: 4, items: expect.any(Array) });
		expect(await maybeMockJson<Array<unknown>>('GET', '/api/v1/admin/users/activity?domain_id=mock-domain')).toHaveLength(2);
		expect(await maybeMockJson<Array<unknown>>('GET', '/api/v1/admin/projects/names')).toHaveLength(3);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('persists valid tutorial statuses while rejecting administrator resource mutations', async () => {
		sessionStorage.clear();
		sessionStorage.setItem(MOCKUP_SESSION_KEY, 'admin');
		vi.resetModules();
		const { maybeMockJson } = await import('./transport');

		expect(await maybeMockJson('GET', '/api/v1/tutorials/status')).toEqual({ statuses: {} });
		expect(await maybeMockJson('POST', '/api/v1/tutorials/admin-compute/status', { status: 'completed' })).toEqual({
			tour_id: 'admin-compute',
			status: 'completed',
		});
		expect(await maybeMockJson('GET', '/api/v1/tutorials/status')).toEqual({
			statuses: { 'admin-compute': 'completed' },
		});
		await expect(
			maybeMockJson('POST', '/api/v1/admin/instances/mock-instance-1/action', { action: 'stop' }),
		).rejects.toMatchObject({ status: 409 });
		await expect(
			maybeMockJson('DELETE', '/api/v1/admin/volumes/mock-admin-volume-available'),
		).rejects.toMatchObject({ status: 409 });
		await expect(
			maybeMockJson('POST', '/api/v1/tutorials/not-a-tour/status', { status: 'completed' }),
		).rejects.toMatchObject({ status: 409 });
		expect(fetchMock).not.toHaveBeenCalled();
	});
	it('intercepts a query-activated mock before auth hydration can reach fetch', async () => {
		sessionStorage.clear();
		window.history.replaceState({}, '', '/dashboard?tutorial=on');
		vi.resetModules();
		// Dynamic import proves query bootstrap works before auth has a stored mock snapshot.
		const { maybeMockJson } = await import('./transport');
		const instances = await maybeMockJson<Array<{ id: string }>>('GET', '/api/v1/instances');

		expect(instances).toEqual(expect.arrayContaining([expect.objectContaining({ id: 'mock-instance-1' })]));
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('serves an explicit workload namespace through native discovery without issuing credentials', async () => {
		// Dynamic import required: each test resets transport's mutable singleton fixture state.
		const { maybeMockJson } = await import('./transport');
		const clusters = await maybeMockJson<K3sCluster[]>('GET', '/api/v1/k3s/clusters') as K3sCluster[];
		const activeCluster = clusters.find((cluster) => cluster.status === 'ACTIVE');
		expect(activeCluster).toBeTruthy();
		const namespaces = await maybeMockJson<string[]>('GET', `/api/v1/k3s/clusters/${activeCluster!.id}/namespaces?cache=true`);
		expect(namespaces).toEqual(['tutorial-workloads']);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('serves kubeconfig availability through HEAD and blob handlers for active clusters', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockBlob, maybeMockHead, maybeMockJson } = await import('./transport');
		const clusters = (await maybeMockJson<K3sCluster[]>(
			'GET',
			'/api/v1/k3s/clusters',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as K3sCluster[];
		const activeCluster = clusters.find((cluster) => cluster.status === 'ACTIVE');

		expect(activeCluster).toBeTruthy();

		const head = (await maybeMockHead(
			`/api/v1/k3s/clusters/${activeCluster!.id}/kubeconfig?grade=user`,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Response;
		const blob = (await maybeMockBlob(
			'GET',
			`/api/v1/k3s/clusters/${activeCluster!.id}/kubeconfig?grade=editor`,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Blob;
		const ca = (await maybeMockBlob(
			'GET',
			`/api/v1/k3s/clusters/${activeCluster!.id}/ca-certificate`,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Blob;
		const text = await blob.text();

		expect(head.ok).toBe(true);
		expect(text).toContain('apiVersion:');
		expect(text).toContain('kind: Config');
		await expect(ca.text()).resolves.toContain('BEGIN CERTIFICATE');
		expect(fetchMock).not.toHaveBeenCalled();
	});


	it('serves lean dashboard overview contracts without changing full fixtures', async () => {
		// resetModules must recreate the shared mutable state used by both fixtures and transport.
		const { getMockupState } = await import('./state');
		const { maybeMockJson, maybeMockK3sStream } = await import('./transport');
		const fullSummary = await maybeMockJson<{ gpu_used: number }>(
			'GET',
			'/api/v1/dashboard/summary',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		);
		const overviewSummary = (await maybeMockJson<{ recent_instances: unknown[] }>(
			'GET',
			'/api/v1/dashboard/summary?view=overview&recent_limit=12',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as { recent_instances: unknown[] };
		const overviewQuotas = (await maybeMockJson<{ file_storage: unknown; alerts: unknown[] }>(
			'GET',
			'/api/v1/dashboard/quotas?view=overview',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as { file_storage: unknown; alerts: unknown[] };
		const k3sStats = (await maybeMockJson<{ total: number; active: number; available: boolean }>(
			'GET',
			'/api/v1/dashboard/k3s-stats',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as { total: number; active: number; available: boolean };
		const trend = (await maybeMockJson<{ network: { unit: string; data: unknown[] } }>(
			'GET',
			'/api/v1/dashboard/metrics/trend?range=14d&include_network=false',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as { network: { unit: string; data: unknown[] } };

		const snapshot = await maybeMockJson('GET', '/api/v1/dashboard/snapshot?recent_limit=12', undefined, 'mock-token-tutorial-scoped', 'mock-project-1');
		expect(snapshot).toEqual({ summary: { data: overviewSummary, error: null }, quotas: { data: overviewQuotas, error: null } });
		expect(fullSummary).toMatchObject({ gpu_used: expect.any(Number) });
		expect(overviewSummary).toMatchObject({ recent_instances: expect.any(Array) });
		expect(overviewSummary.recent_instances).toHaveLength(8);
		expect(overviewQuotas).toMatchObject({ alerts: expect.any(Array) });
		expect(k3sStats.available).toBe(true);
		expect(k3sStats.total).toBeGreaterThanOrEqual(k3sStats.active);
		expect(trend.network).toMatchObject({ unit: 'KiB/s', data: [] });

		const clusters = (await maybeMockJson<Array<{ id: string; status: string }>>(
			'GET',
			'/api/v1/k3s/clusters',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Array<{ id: string; status: string }>;
		const deleted = clusters.find((cluster) => cluster.status === 'ACTIVE')!;
		const stream = maybeMockK3sStream(
			`/api/v1/k3s/clusters/${deleted.id}/delete-async`,
			{},
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)!;
		for await (const _event of stream) {
			// Exhaust the local mutation stream.
		}
		const afterDelete = (await maybeMockJson<{ total: number; active: number; available: boolean }>(
			'GET',
			'/api/v1/dashboard/k3s-stats',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as { total: number; active: number; available: boolean };
		expect(afterDelete.available).toBe(true);
		expect(afterDelete.total).toBe(k3sStats.total - 1);
		expect(afterDelete.active).toBe(k3sStats.active - 1);
	});
	it('throws the exact 409 mockup error for unsupported mutations on supported pages', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockJson } = await import('./transport');
		const instances = (await maybeMockJson<Array<{ id: string }>>(
			'GET',
			'/api/v1/instances',
			undefined,
			'mock-token-tutorial-scoped',
			'mock-project-1',
		)) as Array<{ id: string }>;

		await expect(
			maybeMockJson(
				'POST',
				`/api/v1/instances/${instances[0]!.id}/floating-ip?port_id=mock-port-1`,
				{},
				'mock-token-tutorial-scoped',
				'mock-project-1',
			),
		).rejects.toMatchObject({
			status: 409,
			message: '튜토리얼 모드에서는 이 작업을 아직 지원하지 않습니다.',
		});
	});

	it('supports the volume tutorial flow: list, create, delete', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockJson } = await import('./transport');
		const list = (await maybeMockJson<Array<{ id: string; status: string }>>(
			'GET', '/api/v1/volumes', undefined, 'mock-token-tutorial-scoped', 'mock-project-1',
		)) as Array<{ id: string; status: string }>;
		expect(list.some((volume) => volume.id === 'mock-volume-1' && volume.status === 'in-use')).toBe(true);

		const created = (await maybeMockJson<{ id: string; name: string; status: string; size: number }>(
			'POST', '/api/v1/volumes', { name: 'tour-volume', size_gb: 20 }, 'mock-token-tutorial-scoped', 'mock-project-1',
		)) as { id: string; name: string; status: string; size: number };
		expect(created.name).toBe('tour-volume');
		expect(created.status).toBe('available');
		expect(created.size).toBe(20);

		const afterCreate = (await maybeMockJson<Array<{ id: string }>>(
			'GET', '/api/v1/volumes', undefined, 'mock-token-tutorial-scoped', 'mock-project-1',
		)) as Array<{ id: string }>;
		expect(afterCreate.some((volume) => volume.id === created.id)).toBe(true);

		await maybeMockJson('DELETE', `/api/v1/volumes/${created.id}`, undefined, 'mock-token-tutorial-scoped', 'mock-project-1');
		const afterDelete = (await maybeMockJson<Array<{ id: string }>>(
			'GET', '/api/v1/volumes', undefined, 'mock-token-tutorial-scoped', 'mock-project-1',
		)) as Array<{ id: string }>;
		expect(afterDelete.some((volume) => volume.id === created.id)).toBe(false);

	});

	it('supports the image detail export tutorial flow', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockJson } = await import('./transport');
		const token = 'mock-token-tutorial-scoped';
		const project = 'mock-project-1';
		const image = (await maybeMockJson<{ id: string; disk_format: string }>(
			'GET',
			'/api/v1/images/fixture-image-ubuntu',
			undefined,
			token,
			project,
		)) as { id: string; disk_format: string; tags: string[]; properties: Record<string, string> };
		expect(image).toMatchObject({
			id: 'fixture-image-ubuntu',
			disk_format: 'qcow2',
			tags: ['ubuntu', 'lts'],
			properties: {},
		});
		expect(
			await maybeMockJson(
				'GET',
				'/api/v1/palimpsest/hub/image-exports?source_image_id=fixture-image-ubuntu&limit=1',
				undefined,
				token,
				project,
			),
		).toEqual([]);

		const queued = (await maybeMockJson<{ id: string; status: string }>(
			'POST',
			'/api/v1/palimpsest/hub/image-exports',
			{ image_id: image.id, disk_format: 'vhdx' },
			token,
			project,
		)) as { id: string; status: string };
		expect(queued).toMatchObject({ id: 'mock-image-export-1', status: 'queued' });

		const complete = await maybeMockJson(
			'GET',
			`/api/v1/palimpsest/hub/image-exports/${queued.id}`,
			undefined,
			token,
			project,
		);
		expect(complete).toMatchObject({ status: 'complete', progress_pct: 100 });
		expect(
			await maybeMockJson(
				'POST',
				`/api/v1/palimpsest/hub/image-exports/${queued.id}/download-token`,
				{},
				token,
				project,
			),
		).toMatchObject({ expires_in: 60 });
	});

	it('serves the VM creation wizard data fixtures', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockJson } = await import('./transport');
		const images = (await maybeMockJson<Array<{ id: string; os_distro: string }>>(
			'GET', '/api/v1/images', undefined, 'mock-token-tutorial-scoped', 'mock-project-1',
		)) as Array<{ id: string; os_distro: string }>;
		expect(images.some((image) => image.id === 'fixture-image-ubuntu' && image.os_distro === 'ubuntu')).toBe(true);

		expect(await maybeMockJson('GET', '/api/v1/libraries', undefined, 'mock-token-tutorial-scoped', 'mock-project-1')).toEqual([]);
		expect(await maybeMockJson('GET', '/api/v1/instances/availability-zones', undefined, 'mock-token-tutorial-scoped', 'mock-project-1')).toEqual([
			{ name: 'nova', available: true },
		]);
		expect(await maybeMockJson('GET', '/api/v1/networks/default', undefined, 'mock-token-tutorial-scoped', 'mock-project-1')).toEqual({
			network_id: 'mock-net-private',
		});
		expect(await maybeMockJson('GET', '/api/v1/dashboard/gpu-available', undefined, 'mock-token-tutorial-scoped', 'mock-project-1')).toEqual({ gpu_types: [] });
		const securityGroups = (await maybeMockJson<Array<{ id: string }>>(
			'GET', '/api/v1/security-groups', undefined, 'mock-token-tutorial-scoped', 'mock-project-1',
		)) as Array<{ id: string }>;
		expect(securityGroups[0]?.id).toBe('mock-sg-default');
	});

	it('streams mocked instance creation progress and appends the instance', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockInstanceCreateStream, maybeMockJson } = await import('./transport');
		const stream = maybeMockInstanceCreateStream('/api/v1/instances/async', {
			name: 'tour-vm',
			flavor_id: 'mock-flavor-cpu4',
			image_id: 'fixture-image-ubuntu',
		});
		expect(stream).not.toBeNull();

		const messages: Array<{ step: string; progress: number; instance_id?: string }> = [];
		for await (const message of stream!) messages.push(message);
		expect(messages.at(-1)?.step).toBe('completed');
		expect(messages.at(-1)?.progress).toBe(100);

		const instances = (await maybeMockJson<Array<{ id: string; name: string; ip_addresses: Array<{ addr: string }> }>>(
			'GET', '/api/v1/instances', undefined, 'mock-token-tutorial-scoped', 'mock-project-1',
		)) as Array<{ id: string; name: string; ip_addresses: Array<{ addr: string }> }>;
		const created = instances.find((instance) => instance.name === 'tour-vm');
		expect(created).toBeTruthy();
		expect(created!.id).toBe(messages.at(-1)?.instance_id);
		// 픽스처 주소 대역(RFC 5737) 준수
		expect(created!.ip_addresses.every((address) => address.addr.startsWith('192.0.2.'))).toBe(true);
	});

	it('names an unnamed tutorial instance tut- and lets its detail page stop then delete only it', async () => {
		// Dynamic import required: transport owns mutable singleton fixture state that each test must reinitialize.
		const { maybeMockInstanceCreateStream, maybeMockJson } = await import('./transport');
		const before = (await maybeMockJson<Array<{ id: string }>>('GET', '/api/v1/instances', undefined, 'mock-token-tutorial-scoped', 'mock-project-1')) as Array<{ id: string }>;
		const stream = maybeMockInstanceCreateStream('/api/v1/instances/async', { name: null, flavor_id: 'mock-flavor-cpu4', image_id: 'fixture-image-ubuntu' });
		let id: string | undefined;
		for await (const message of stream!) id = message.instance_id ?? id;

		type Detail = { id: string; name: string; status: string; project_id?: string };
		const created = (await maybeMockJson<Detail>('GET', `/api/v1/instances/${id}`, undefined, 'mock-token-tutorial-scoped', 'mock-project-1')) as Detail;
		expect(created.name).toBe(`tut-${id}`);
		expect(created.project_id).toBe('mock-project-1');
		expect(created.status).toBe('ACTIVE');

		await maybeMockJson('POST', `/api/v1/instances/${id}/stop`, {}, 'mock-token-tutorial-scoped', 'mock-project-1');
		expect(((await maybeMockJson<Detail>('GET', `/api/v1/instances/${id}`, undefined, 'mock-token-tutorial-scoped', 'mock-project-1')) as Detail).status).toBe('SHUTOFF');
		const volumes = (await maybeMockJson<Array<{ delete_on_termination: boolean }>>('GET', `/api/v1/instances/${id}/volumes`, undefined, 'mock-token-tutorial-scoped', 'mock-project-1')) as Array<{ delete_on_termination: boolean }>;
		expect(volumes.every((volume) => volume.delete_on_termination === false)).toBe(true);

		await maybeMockJson('DELETE', `/api/v1/instances/${id}`, undefined, 'mock-token-tutorial-scoped', 'mock-project-1');
		const after = (await maybeMockJson<Array<{ id: string }>>('GET', '/api/v1/instances', undefined, 'mock-token-tutorial-scoped', 'mock-project-1')) as Array<{ id: string }>;
		expect(after.map((instance) => instance.id)).toEqual(before.map((instance) => instance.id));
		await expect(maybeMockJson('GET', `/api/v1/instances/${id}`, undefined, 'mock-token-tutorial-scoped', 'mock-project-1')).rejects.toMatchObject({ status: 409 });
	});
});
