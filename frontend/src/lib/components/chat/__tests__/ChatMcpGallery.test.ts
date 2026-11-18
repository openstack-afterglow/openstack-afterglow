import { grantLumen, setVerifiedLumenActor } from './lumenPermissionFixture';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import { auth, projectSwitching, type AuthState } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/mcp-gallery';
import { page as route } from '$app/state';
import type { McpConnection, McpDomainPage, McpSettingsPage, McpTemplate } from '$lib/api/mcpCatalog';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), redirect: vi.fn(), changed: vi.fn()
}));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, post: mocks.post, patch: mocks.patch, delete: mocks.delete }
}));
vi.mock('$app/navigation', () => ({
	pushState: (url: URL) => { document.defaultView!.history.pushState({}, '', url); }
}));

import ChatMcpGallery from '../ChatMcpGallery.svelte';

// These are component/API-boundary fixtures, not native Lumen integration evidence.
const deferred = <T,>() => Promise.withResolvers<T>();

function template(overrides: Partial<McpTemplate> = {}): McpTemplate {
	return {
		id: 'catalog-open', name: 'Public catalog tool', registry_name: 'example/public-tool',
		description: 'A hosted catalog tool', url: 'https://tools.example.test/mcp', transport: 'http',
		variables: [], header_hints: [], access: 'open', featured: false, ...overrides
	};
}
function connection(overrides: Partial<McpConnection> = {}): McpConnection {
	const personal = (overrides.scope ?? 'user') === 'user';
	const published = overrides.server_is_active ?? !personal;
	const connected = overrides.auth_mode === 'oauth' ? overrides.auth_connected === true
		: overrides.auth_mode === 'admin' ? overrides.has_headers === true : true;
	return {
		id: 11, name: 'Personal connection', scope: 'user', owner_user_id: 'user-1',
		owner_project_id: 'project-1', owner_domain_id: 'domain-1',
		url: 'https://tools.example.test/mcp', transport: 'http', auth_mode: 'none',
		is_active: personal && published && connected, server_is_active: published, config_version: 7,
		activation_is_active: personal && published, activation_config_version: null,
		template_key: 'catalog-open', ...overrides
	};
}
function settings(overrides: Partial<McpSettingsPage> = {}): McpSettingsPage {
	return {
		entries: [template()], total: 1, offset: 0, limit: 12, next_offset: null,
		domain_id: 'domain-1', organization_available: true, can_manage_domain: false, custom_connections: [], ...overrides
	};
}

let page: McpSettingsPage;
let featured: McpTemplate[];
let managed: McpTemplate[];
let servers: McpConnection[];
let organization: McpConnection[];

function response(path: string): Promise<unknown> {
	if (path.includes('/mcp-settings?featured=true')) return Promise.resolve(settings({ entries: featured, total: featured.length, limit: 100 }));
	if (path.includes('/mcp-settings?access=managed')) {
		const entries = managed.length ? managed : page.entries.filter((entry) => entry.access === 'managed');
		return Promise.resolve(settings({ entries, total: entries.length, limit: 100 }));
	}
	if (path.includes('/mcp-settings?')) return Promise.resolve(page);
	if (path === '/api/v1/chat/mcp-servers') return Promise.resolve(servers);
	if (path.includes('/mcp-connections?')) return Promise.resolve({ connections: organization, total: organization.length, next_offset: null } satisfies McpDomainPage);
	throw new Error(`Unexpected gallery GET: ${path}`);
}

const identityChanges = [
	['user', { userId: 'user-2' }],
	['project', { projectId: 'project-2' }],
	['working domain', { domainId: 'domain-2' }],
	['identity domain', { identityDomainId: 'identity-2' }],
	['session', { sessionId: 'session-2' }]
] as const;

async function replaceActor(change: Partial<AuthState>) {
	await act(async () => { setVerifiedLumenActor({ ...get(auth), ...change }); });
}
const tabNames = { browse: 'workspace.browse', connected: 'workspace.connected', manage: 'workspace.manage' } as const;
function tab(name: keyof typeof tabNames) {
	return screen.getByRole('tab', { name: new RegExp(`^${t(tabNames[name])}(?: |$)`) });
}
async function selectTab(name: keyof typeof tabNames) {
	if (tab(name).getAttribute('aria-selected') !== 'true') await fireEvent.click(tab(name));
}
async function loaded() {
	await waitFor(() => expect(screen.getByRole('button', { name: t('refresh') }).hasAttribute('disabled')).toBe(false));
}
async function row(name: string): Promise<HTMLElement> {
	await selectTab('connected');
	const element = (await screen.findByText(name, { exact: true })).closest('.connection-row');
	if (!(element instanceof HTMLElement)) throw new Error(`Missing connection row: ${name}`);
	const trigger = within(element).getByRole('button', { name: t('workspace.manageNamed', { name }) });
	if (trigger.getAttribute('aria-expanded') !== 'true') await fireEvent.click(trigger);
	return element.closest('tbody') ?? element;
}
async function expectOrganizationOption(available: boolean) {
	const trigger = screen.getByRole('button', { name: t('workspace.add') });
	await fireEvent.click(trigger);
	expect(!!screen.queryByRole('menuitem', { name: t('connectOrganization') })).toBe(available);
	await fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
}
function card(name: string) { return screen.getByRole('article', { name }); }

describe('Connections workspace', () => {
	it('opens a deep link and moves tab focus without selecting until activation', async () => {
		const url = new URL('/dashboard/chat/settings?section=mcp&connections=manage', document.location.origin);
		route.url.pathname = '/dashboard/chat/settings';
		route.url.search = url.search;
		document.defaultView!.history.replaceState({}, '', url);
		render(ChatMcpGallery);
		const manage = tab('manage'), browse = tab('browse'), connected = tab('connected');
		expect(screen.getByRole('tabpanel').id).toBe(manage.getAttribute('aria-controls'));
		manage.focus();
		await fireEvent.keyDown(manage, { key: 'ArrowRight' });
		expect(document.activeElement).toBe(browse);
		expect(manage.getAttribute('aria-selected')).toBe('true');
		await fireEvent.keyDown(browse, { key: 'End' });
		expect(document.activeElement).toBe(manage);
		await fireEvent.keyDown(manage, { key: 'Home' });
		await fireEvent.keyDown(browse, { key: 'ArrowRight' });
		expect(document.activeElement).toBe(connected);
		await fireEvent.click(connected); // Native button activation for Enter/Space.
		expect(connected.tabIndex).toBe(0);
		expect(manage.tabIndex).toBe(-1);
		expect(document.location.search).toBe('?section=mcp&connections=connected');
		const connectedUrl = document.location.href;
		document.defaultView!.history.replaceState({}, '', url);
		await fireEvent.popState(document.defaultView!);
		expect(manage.getAttribute('aria-selected')).toBe('true');
		document.defaultView!.history.replaceState({}, '', connectedUrl);
		await fireEvent.popState(document.defaultView!);
		expect(connected.getAttribute('aria-selected')).toBe('true');
	});

	it('sends access and debounced q; filters the Connected scope locally', async () => {
		servers = [
			connection({ id: 11, name: 'Connector A', server_is_active: true }),
			connection({ id: 12, name: 'Connector B', auth_mode: 'oauth' }),
			connection({ id: 13, name: 'Connector C', scope: 'global', template_key: null, auth_mode: 'oauth', catalog_error: 'provider-provided text' }),
			connection({ id: 14, name: 'Connector D', scope: 'global', activation_is_active: true, activation_config_version: 1, config_version: 3, catalog_error: 'provider-provided text' }),
			connection({ id: 15, name: 'Connector E', scope: 'global', catalog_error: 'provider-provided text' }),
			connection({ id: 16, name: 'Connector F' })
		];
		render(ChatMcpGallery);
		await loaded();
		await selectTab('connected');
		expect(tab('connected').textContent).toMatch(/6/);
		const expected = ['active', 'needsAuth', 'needsAuth', 'stale', 'workspace.error', 'inactive'] as const;
		const paths = new Set<string>();
		for (const [index, key] of expected.entries()) {
			const row = screen.getByText(servers[index].name).closest('.connection-row')!;
			expect(within(row as HTMLElement).getByText(t(key))).toBeTruthy();
			paths.add(row.querySelector('[data-connection-status] path')!.getAttribute('d')!);
		}
		expect(paths.size).toBe(5);
		expect(document.body.textContent).not.toContain('provider-provided text');
		const requests = mocks.get.mock.calls.length;
		await fireEvent.change(screen.getByLabelText(t('workspace.scopeLabel')), { target: { value: 'global' } });
		expect(tab('connected').textContent).toMatch(/3/);
		expect(mocks.get).toHaveBeenCalledTimes(requests);
		await fireEvent.change(screen.getByLabelText(t('workspace.type')), { target: { value: 'oauth' } });
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'Connector C' }, isComposing: true });
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?offset=0&limit=12&q=Connector+C&access=oauth', 'token-1', 'project-1', expect.anything()));
		expect(tab('connected').textContent).toMatch(/1/);
		expect(screen.getByText('Connector C')).toBeTruthy();
		expect(screen.queryByText('Connector B')).toBeNull();
	});

	it('jumps from a connected catalogue row to its open management detail', async () => {
		servers = [connection({ name: 'Installed tool', tools: [{ name: 'lookup', description: 'Find a record' }], tool_count: 1 })];
		render(ChatMcpGallery);
		await loaded();
		await fireEvent.click(within(card('Public catalog tool')).getByRole('button', { name: t('workspace.manage') }));
		expect(tab('connected').getAttribute('aria-selected')).toBe('true');
		expect(screen.getByText('Find a record', { exact: false })).toBeTruthy();
		expect(document.activeElement?.getAttribute('aria-label')).toBe(t('workspace.manageNamed', { name: 'Installed tool' }));
	});

	it('keeps the total Connected badge while Browse search has no matches', async () => {
		servers = [connection(), connection({ id: 12, scope: 'global', name: 'Admin inventory row' })];
		mocks.get.mockImplementation((path: string) => path.includes('q=absent')
			? Promise.resolve(settings({ entries: [], total: 0 }))
			: response(path));
		render(ChatMcpGallery);
		await loaded();
		expect(tab('connected').textContent).toMatch(/2/);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'absent' } });
		await screen.findByText(t('emptySearch'));
		expect(tab('connected').textContent).toMatch(/2/);
		await selectTab('connected');
		expect(tab('connected').textContent).toMatch(/0/);
		await selectTab('manage');
		expect(tab('connected').textContent).toMatch(/2/);
	});

	it.each([false, true])('allows personal Connect when only an admin-published connection exists (manager=%s)', async (manager) => {
		page = settings({ can_manage_domain: manager });
		servers = [connection({ scope: 'global' })];
		render(ChatMcpGallery);
		await loaded();
		const controls = within(card('Public catalog tool'));
		expect(controls.getByText(t('workspace.shared'))).toBeTruthy();
		expect(controls.queryByRole('button', { name: t('workspace.manage') })).toBeNull();
		await fireEvent.click(controls.getByRole('button', { name: t('workspace.connect') }));
		if (manager) {
			expect(controls.getByRole('menuitem', { name: t('connectOrganization') })).toBeTruthy();
			await fireEvent.click(controls.getByRole('menuitem', { name: t('connectPersonal') }));
		}
		expect(screen.getByRole('heading', { name: t('connectTitle', { name: 'Public catalog tool' }) })).toBeTruthy();
	});
});
function requestSignal(mock: typeof mocks.get, index: number): AbortSignal {
	return mock.mock.calls[index].at(-1).signal as AbortSignal;
}
async function settle(work: () => void) {
	await act(async () => { work(); await tick(); });
}
function expectFixedHeader(name: string) {
	expect(screen.queryByLabelText(t('headerName'))).toBeNull();
	expect((screen.getByLabelText(name) as HTMLInputElement).type).toBe('password');
	expect(screen.queryByRole('button', { name: t('addHeader') })).toBeNull();
	expect(screen.queryByRole('button', { name: t('removeHeader') })).toBeNull();
}

beforeEach(() => {
	vi.resetAllMocks();
	route.url.pathname = '/';
	route.url.search = '';
	document.defaultView!.history.replaceState({}, '', '/');
	initLocale('ko');
	setVerifiedLumenActor({
		token: 'token-1', refreshToken: null, accessExpiresAt: null,
		userId: 'user-1', username: 'tester', projectId: 'project-1', projectName: 'Project',
		availableProjects: [], roles: [], isSystemAdmin: false, federated: false,
		domainId: 'domain-1', domainName: 'Domain', identityDomainId: 'identity-1',
		identityDomainName: 'Identity', isDomainManager: false, sessionId: 'session-1'
	});
	grantLumen('lumen-mcp_editor', 'lumen-resources_admin');
	page = settings(); featured = []; managed = []; servers = []; organization = [];
	mocks.get.mockImplementation(response);
	mocks.post.mockResolvedValue({ created: true, server: connection() });
	mocks.patch.mockResolvedValue({});
	mocks.delete.mockResolvedValue(undefined);
	mocks.changed.mockResolvedValue(undefined);
	// jsdom's Location.assign is non-configurable; preserve all other Window APIs.
	const realWindow = window;
	const location = {
		origin: realWindow.location.origin, href: realWindow.location.href,
		pathname: realWindow.location.pathname, search: '', assign: mocks.redirect
	};
	vi.stubGlobal('window', new Proxy(realWindow, {
		get(target, key) {
			return key === 'location' ? location : Reflect.get(target, key, target);
		}
	}));
});

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
});

describe('ChatMcpGallery ownership', () => {
	it.each(identityChanges)('discards a stale settings read after changing %s', async (_kind, change) => {
		const oldPage = deferred<McpSettingsPage>();
		mocks.get.mockImplementation((path: string) => path === '/api/v1/chat/mcp-settings?offset=0&limit=12' && mocks.get.mock.calls.filter(([value]) => value === path).length === 1 ? oldPage.promise : response(path));
		render(ChatMcpGallery);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(4));
		const signal = requestSignal(mocks.get, 0);
		page = settings({ entries: [template({ id: 'current', name: 'Current owner catalog' })] });
		await replaceActor(change);
		await screen.findByRole('article', { name: 'Current owner catalog' });
		expect(signal.aborted).toBe(true);
		const count = mocks.get.mock.calls.length;
		await settle(() => oldPage.resolve(settings({ entries: [template({ name: 'Old owner catalog' })], can_manage_domain: true })));
		expect(screen.queryByRole('article', { name: 'Old owner catalog' })).toBeNull();
		expect(screen.queryByText(t('managerHelp'))).toBeNull();
		await expectOrganizationOption(false);
		expect(mocks.get).toHaveBeenCalledTimes(count);
	});

	it('discards a stale organization page after project ownership changes', async () => {
		const oldDomain = deferred<McpDomainPage>();
		mocks.get.mockImplementation((path: string, _token: string, projectId: string) => path.includes('/domains/') && projectId === 'project-1' ? oldDomain.promise : response(path));
		render(ChatMcpGallery);
		await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(expect.stringContaining('/domains/domain-1/'), 'token-1', 'project-1', expect.anything()));
		const signal = requestSignal(mocks.get, 4);
		await replaceActor({ projectId: 'project-2' });
		await loaded();
		await settle(() => oldDomain.resolve({ connections: [connection({ scope: 'domain', name: 'Old organization secret-free row' })], total: 1, next_offset: null }));
		expect(signal.aborted).toBe(true);
		expect(screen.queryByText('Old organization secret-free row')).toBeNull();
	});

	it.each(identityChanges)('suppresses pending activation completion after changing %s', async (_kind, change) => {
		servers = [connection()];
		const pending = deferred<unknown>();
		mocks.patch.mockReturnValue(pending.promise);
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await loaded();
		await fireEvent.click(within(await row('Personal connection')).getByRole('button', { name: t('activate') }));
		expect(mocks.patch).toHaveBeenCalledTimes(1);
		const signal = requestSignal(mocks.patch, 0);
		servers = [];
		await replaceActor(change);
		await loaded();
		const count = mocks.get.mock.calls.length;
		await settle(() => pending.resolve({}));
		expect(signal.aborted).toBe(true);
		expect(mocks.changed).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenCalledTimes(count);
		expect(screen.queryByText('Personal connection')).toBeNull();
	});

	it('clears the editor and ignores a pending create failure during project switching', async () => {
		const pending = deferred<unknown>();
		mocks.post.mockReturnValue(pending.promise);
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await loaded();
		await fireEvent.click(within(card('Public catalog tool')).getByRole('button', { name: t('workspace.connect') }));
		await fireEvent.input(screen.getByLabelText(t('label')), { target: { value: 'Old project draft' } });
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		const signal = requestSignal(mocks.post, 0);
		await act(async () => { projectSwitching.set(true); });
		await settle(() => pending.reject(new Error('Old project rejected secret-value')));
		expect(signal.aborted).toBe(true);
		expect(screen.queryByLabelText(t('label'))).toBeNull();
		expect(screen.queryByRole('article')).toBeNull();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(mocks.changed).not.toHaveBeenCalled();
	});

	it('does not reload or notify when write permission disappears during activation', async () => {
		servers = [connection()];
		const pending = deferred<unknown>();
		mocks.patch.mockReturnValue(pending.promise);
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await loaded();
		await fireEvent.click(within(await row('Personal connection')).getByRole('button', { name: t('activate') }));
		grantLumen();
		await tick();
		const count = mocks.get.mock.calls.length;
		await settle(() => pending.resolve({}));
		expect(mocks.changed).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenCalledTimes(count);
	});
});

describe('ChatMcpGallery authority and visibility', () => {
	it('uses server member authority despite a misleading auth-store manager flag', async () => {
		auth.update((actor) => ({ ...actor, isDomainManager: true }));
		organization = [connection({ id: 21, scope: 'domain', name: 'Organization OAuth', auth_mode: 'oauth', auth_connected: true })];
		render(ChatMcpGallery);
		await loaded();
		await expectOrganizationOption(false);
		const controls = within(await row('Organization OAuth'));
		expect(controls.getByRole('button', { name: t('activate') })).toBeTruthy();
		for (const name of [t('edit'), t('delete'), t('reconnect'), t('revokeOAuth')]) expect(controls.queryByRole('button', { name })).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('uses server manager authority even when the auth-store manager flag is false', async () => {
		page = settings({ can_manage_domain: true });
		organization = [connection({ id: 21, scope: 'domain', name: 'Organization OAuth', auth_mode: 'oauth' })];
		render(ChatMcpGallery);
		await loaded();
		await expectOrganizationOption(true);
		await selectTab('manage');
		expect(screen.getByText(t('managerHelp'))).toBeTruthy();
		const controls = within(await row('Organization OAuth'));
		expect(controls.getByRole('button', { name: t('edit') })).toBeTruthy();
		expect(controls.getByRole('button', { name: t('delete') })).toBeTruthy();
		expect(controls.getByRole('button', { name: t('connectOAuth') })).toBeTruthy();
	});

	it('hides foreign-domain, foreign-user and foreign-project rows from every returned collection', async () => {
		const foreignDomain = connection({ id: 31, scope: 'domain', name: 'Foreign domain', owner_domain_id: 'domain-elsewhere' });
		const foreignUser = connection({ id: 32, name: 'Foreign user', owner_user_id: 'user-elsewhere' });
		const foreignProject = connection({ id: 33, name: 'Foreign project', owner_project_id: 'project-elsewhere' });
		servers = [foreignDomain, foreignUser, foreignProject, connection()];
		organization = [foreignDomain, connection({ id: 34, scope: 'domain', name: 'Our organization' })];
		page = settings({ custom_connections: [foreignDomain, foreignUser, foreignProject] });
		render(ChatMcpGallery);
		await loaded();
		await selectTab('connected');
		expect(screen.getByText('Personal connection')).toBeTruthy();
		expect(screen.getByText('Our organization')).toBeTruthy();
		for (const name of ['Foreign domain', 'Foreign user', 'Foreign project']) expect(screen.queryByText(name)).toBeNull();
	});

	it('sends organization activation consent for the exact current config_version', async () => {
		organization = [connection({ id: 21, scope: 'domain', name: 'Changed organization tool', config_version: 19, activation_is_active: true, activation_config_version: 18 })];
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await loaded();
		const controls = within(await row('Changed organization tool'));
		expect(controls.getByText(t('stale'))).toBeTruthy();
		await fireEvent.click(controls.getByRole('button', { name: t('activate') }));
		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/chat/domains/domain-1/mcp-connections/21/activation', { is_active: true, config_version: 19 }, 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
		await waitFor(() => expect(mocks.changed).toHaveBeenCalledTimes(1));
	});

	it.each([
		['catalog', 'catalog-open', '/api/v1/chat/mcp-connections/11'],
		['custom', null, '/api/v1/chat/mcp-servers/11']
	] as const)('updates a personal %s connection without an activation or config_version body', async (_kind, templateKey, path) => {
		servers = [connection({ is_active: true, server_is_active: true, config_version: 23, template_key: templateKey })];
		render(ChatMcpGallery);
		await loaded();
		await fireEvent.click(within(await row('Personal connection')).getByRole('button', { name: t('deactivate') }));
		expect(mocks.patch).toHaveBeenCalledWith(path, { is_active: false }, 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
	});

	it.each([
		['none', true, 'active'],
		['oauth', false, 'needsAuth']
	] as const)('renders published personal %s metadata as %s/%s without stale activation consent', async (authMode, connected, state) => {
		servers = [connection({ server_is_active: true, auth_mode: authMode, auth_connected: connected })];
		render(ChatMcpGallery);
		await loaded();
		const personal = within(await row('Personal connection'));
		expect(personal.getByText(t(state))).toBeTruthy();
		expect(personal.queryByText(t('stale'))).toBeNull();
		expect(mocks.patch).not.toHaveBeenCalled();
	});
});

describe('ChatMcpGallery secrets and OAuth', () => {
	it('clears a write-only secret draft while POST is pending and never echoes raw server errors', async () => {
		page = settings({ entries: [template({ access: 'credentials', header_hints: [{ name: 'Authorization', description: 'API token', secret: true }] })] });
		const pending = deferred<unknown>();
		mocks.post.mockReturnValue(pending.promise);
		render(ChatMcpGallery);
		await loaded();
		await fireEvent.click(within(card('Public catalog tool')).getByRole('button', { name: t('workspace.connect') }));
		const secret = screen.getByLabelText('Authorization') as HTMLInputElement;
		expect(secret.type).toBe('password');
		expect(secret.autocomplete).toBe('new-password');
		expectFixedHeader('Authorization');
		await fireEvent.input(secret, { target: { value: 'Bearer write-only-secret' } });
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/mcp-connections', expect.objectContaining({ template_id: 'catalog-open', auth_mode: 'admin', headers: { Authorization: 'Bearer write-only-secret' } }), 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
		expect(screen.queryByLabelText('Authorization')).toBeNull();
		expect(screen.queryByDisplayValue('Bearer write-only-secret')).toBeNull();
		await settle(() => pending.reject(new Error('upstream headers Authorization=Bearer write-only-secret')));
		expect(within(card('Public catalog tool')).getByRole('alert').textContent).toContain(t('actionFailed'));
		expect(document.body.textContent).not.toContain('write-only-secret');
		expect(document.body.textContent).not.toContain('upstream headers');
		await fireEvent.click(within(card('Public catalog tool')).getByRole('button', { name: t('workspace.connect') }));
		expect((screen.getByLabelText('Authorization') as HTMLInputElement).value).toBe('');
	});

	it.each(['user', 'domain'] as const)('edits declared %s credential values without freeform header names or unsupported PATCH keys', async (scope) => {
		const entry = template({ access: 'credentials', header_hints: [{ name: 'Authorization', description: 'API token', secret: true }] });
		page = settings({ entries: [entry], can_manage_domain: scope === 'domain' });
		const saved = connection({ scope, name: 'Saved credentials', auth_mode: 'admin', has_headers: true, server_is_active: true });
		if (scope === 'domain') organization = [saved];
		else servers = [saved];
		render(ChatMcpGallery);
		await loaded();
		await selectTab('manage');
		expect(screen.getByText(t(scope === 'domain' ? 'managerHelp' : 'memberHelp'))).toBeTruthy();
		await fireEvent.click(within(await row(saved.name)).getByRole('button', { name: t('edit') }));
		const value = await screen.findByLabelText('Authorization') as HTMLInputElement;
		expectFixedHeader('Authorization');
		expect(value.value).toBe('');
		await fireEvent.input(value, { target: { value: 'Bearer replacement-value' } });
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		expect(mocks.patch).toHaveBeenCalledWith(
			scope === 'domain' ? '/api/v1/chat/domains/domain-1/mcp-connections/11' : '/api/v1/chat/mcp-connections/11',
			scope === 'domain'
				? { name: saved.name, url: saved.url, auth_mode: 'admin', is_active: true, headers: { Authorization: 'Bearer replacement-value' } }
				: { headers: { Authorization: 'Bearer replacement-value' } },
			'token-1', 'project-1', { signal: expect.any(AbortSignal) }
		);
		expect(screen.queryByDisplayValue('Bearer replacement-value')).toBeNull();
		expect(mocks.get.mock.calls.some(([path]) => path === '/api/v1/chat/mcp-settings?offset=0&limit=100')).toBe(false);
	});

	it('paginates exact template ids before editing a credential connection absent from the current catalog page', async () => {
		const saved = connection({ name: 'Off-page credentials', template_key: 'catalog-offpage', auth_mode: 'admin', has_headers: true, server_is_active: true });
		servers = [saved];
		const other = template({
			id: 'catalog-wrong', registry_name: 'catalog-offpage', access: 'credentials',
			header_hints: [{ name: 'X-Wrong', description: 'Not this template', secret: true }]
		});
		const exact = template({
			id: 'catalog-offpage', registry_name: 'example/exact-template', access: 'credentials',
			header_hints: [{ name: 'Authorization', description: 'API token', secret: true }]
		});
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/mcp-settings?offset=0&limit=100') return Promise.resolve(settings({ entries: [other], total: 101, limit: 100, next_offset: 100 }));
			if (path === '/api/v1/chat/mcp-settings?offset=100&limit=100') return Promise.resolve(settings({ entries: [exact], total: 101, offset: 100, limit: 100 }));
			return response(path);
		});
		render(ChatMcpGallery);
		await loaded();
		await fireEvent.click(within(await row(saved.name)).getByRole('button', { name: t('edit') }));
		const value = await screen.findByLabelText('Authorization') as HTMLInputElement;
		expectFixedHeader('Authorization');
		expect(screen.queryByText('X-Wrong', { exact: true })).toBeNull();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?offset=0&limit=100', 'token-1', 'project-1', expect.objectContaining({ refresh: true, signal: expect.any(AbortSignal) }));
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?offset=100&limit=100', 'token-1', 'project-1', expect.objectContaining({ refresh: true, signal: expect.any(AbortSignal) }));
		await fireEvent.input(value, { target: { value: 'Bearer exact-template-value' } });
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/chat/mcp-connections/11', { headers: { Authorization: 'Bearer exact-template-value' } }, 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
	});

	it('creates an organization connection using only the live settings domain', async () => {
		page = settings({ domain_id: 'live-domain', can_manage_domain: true });
		render(ChatMcpGallery);
		await loaded();
		const choices = within(card('Public catalog tool'));
		await fireEvent.click(choices.getByRole('button', { name: t('workspace.connect') }));
		await fireEvent.click(choices.getByRole('menuitem', { name: t('connectOrganization') }));
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/domains/live-domain/mcp-connections', expect.objectContaining({ template_id: 'catalog-open', auth_mode: 'none' }), 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
	});

	it('redirects only to the returned HTTPS OAuth authorization URL', async () => {
		servers = [connection({ auth_mode: 'oauth' })];
		const url = 'https://identity.example.test/authorize?state=opaque&client_id=public-client';
		mocks.post.mockResolvedValue({ authorization_url: url });
		render(ChatMcpGallery);
		await loaded();
		await fireEvent.click(within(await row('Personal connection')).getByRole('button', { name: t('connectOAuth') }));
		await waitFor(() => expect(mocks.redirect).toHaveBeenCalledWith(url));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/mcp-servers/11/oauth/start', undefined, 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
	});

	it.each(['http://identity.example.test/authorize', 'javascript:alert(1)', '/relative/authorize'])('rejects unsafe OAuth destination %s without echoing it', async (url) => {
		servers = [connection({ auth_mode: 'oauth' })];
		mocks.post.mockResolvedValue({ authorization_url: url });
		render(ChatMcpGallery);
		await loaded();
		await fireEvent.click(within(await row('Personal connection')).getByRole('button', { name: t('connectOAuth') }));
		await screen.findByRole('alert');
		expect(mocks.redirect).not.toHaveBeenCalled();
		expect(document.body.textContent).not.toContain(url);
	});

	it('suppresses pending OAuth redirect when write permission is revoked', async () => {
		servers = [connection({ auth_mode: 'oauth' })];
		const pending = deferred<{ authorization_url: string }>();
		mocks.post.mockReturnValue(pending.promise);
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await loaded();
		await fireEvent.click(within(await row('Personal connection')).getByRole('button', { name: t('connectOAuth') }));
		grantLumen();
		await tick();
		const count = mocks.get.mock.calls.length;
		await settle(() => pending.resolve({ authorization_url: 'https://identity.example.test/revoked-owner' }));
		expect(mocks.redirect).not.toHaveBeenCalled();
		expect(mocks.changed).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenCalledTimes(count);
	});

	it('suppresses pending shared OAuth redirect when fresh settings revoke domain management', async () => {
		page = settings({ can_manage_domain: true });
		organization = [connection({ id: 21, scope: 'domain', name: 'Organization OAuth', auth_mode: 'oauth' })];
		const pending = deferred<{ authorization_url: string }>();
		mocks.post.mockReturnValue(pending.promise);
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await loaded();
		await expectOrganizationOption(true);
		await fireEvent.click(within(await row('Organization OAuth')).getByRole('button', { name: t('connectOAuth') }));
		page = settings({ can_manage_domain: false });
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await loaded();
		const count = mocks.get.mock.calls.length;
		await settle(() => pending.resolve({ authorization_url: 'https://identity.example.test/old-manager' }));
		expect(mocks.redirect).not.toHaveBeenCalled();
		expect(mocks.changed).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenCalledTimes(count);
		expect(within(await row('Organization OAuth')).queryByRole('button', { name: t('connectOAuth') })).toBeNull();
	});

	it.each(identityChanges)('suppresses pending OAuth redirect after changing %s', async (_kind, change) => {
		servers = [connection({ auth_mode: 'oauth' })];
		const pending = deferred<{ authorization_url: string }>();
		mocks.post.mockReturnValue(pending.promise);
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await loaded();
		await fireEvent.click(within(await row('Personal connection')).getByRole('button', { name: t('connectOAuth') }));
		const signal = requestSignal(mocks.post, 0);
		servers = [];
		await replaceActor(change);
		await loaded();
		const count = mocks.get.mock.calls.length;
		await settle(() => pending.resolve({ authorization_url: 'https://identity.example.test/old-owner' }));
		expect(signal.aborted).toBe(true);
		expect(mocks.redirect).not.toHaveBeenCalled();
		expect(mocks.changed).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenCalledTimes(count);
	});

	it.each(['delete', 'revokeOAuth'] as const)('suppresses pending organization %s completion after a domain change', async (operation) => {
		page = settings({ can_manage_domain: true });
		organization = [connection({ id: 21, scope: 'domain', name: 'Organization OAuth', auth_mode: 'oauth', auth_connected: true })];
		const pending = deferred<unknown>();
		mocks.delete.mockReturnValue(pending.promise);
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await loaded();
		await expectOrganizationOption(true);
		await fireEvent.click(within(await row('Organization OAuth')).getByRole('button', { name: t(operation) }));
		expect(mocks.delete).not.toHaveBeenCalled();
		const confirm = within(await row('Organization OAuth')).getAllByRole('button', { name: t(operation) }).at(-1)!;
		await fireEvent.click(confirm);
		expect(mocks.delete).toHaveBeenCalledWith(
			operation === 'delete' ? '/api/v1/chat/domains/domain-1/mcp-connections/21' : '/api/v1/chat/mcp-servers/21/oauth',
			'token-1', 'project-1', { signal: expect.any(AbortSignal) }
		);
		const signal = requestSignal(mocks.delete, 0);
		page = settings({ domain_id: 'domain-2' });
		organization = [];
		await replaceActor({ domainId: 'domain-2' });
		await loaded();
		const count = mocks.get.mock.calls.length;
		await settle(() => pending.resolve(undefined));
		expect(signal.aborted).toBe(true);
		expect(mocks.changed).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenCalledTimes(count);
		expect(screen.queryByText('Organization OAuth')).toBeNull();
	});
});

describe('ChatMcpGallery catalog browsing and row feedback', () => {
	it.each([
		['profile_not_in_enabled_sandbox_manifest', 'profileMissing'],
		['execution_protocol_v2_unavailable', 'protocolMissing']
	] as const)('shows managed availability reason %s without connect actions', async (reason, key) => {
		grantLumen('lumen-mcp_editor', 'lumen-resources_admin', 'lumen-tools_user');
		page = settings({ entries: [template({ name: 'Managed Playwright', access: 'managed', managed: { profile: 'playwright', available: false, reason, tools: ['browser_navigate'] } })] });
		render(ChatMcpGallery);
		await loaded();
		const managed = within(card('Managed Playwright'));
		expect(managed.getByText(t('builtIn'))).toBeTruthy();
		expect(managed.getByText(t(key))).toBeTruthy();
		expect(managed.queryByRole('button', { name: t('workspace.connect') })).toBeNull();
		expect(managed.queryByRole('button', { name: t('workspace.manage') })).toBeNull();
		expect(managed.getByRole('checkbox', { name: t('selectionProfile', { name: 'Managed Playwright' }) }).hasAttribute('disabled')).toBe(true);
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it('excludes built-in tools from the full catalogue total and hides its section for the managed filter', async () => {
		managed = [template({ id: 'managed-01', access: 'managed', name: 'Built-in example' })];
		page = settings({ entries: [template(), ...managed], total: 2 });
		mocks.get.mockImplementation((path: string) => path.includes('q=missing')
			? Promise.resolve(settings({ entries: [], total: 0 }))
			: response(path));
		render(ChatMcpGallery);
		await loaded();
		expect(screen.getByRole('heading', { name: `${t('browse')} (1)` })).toBeTruthy();
		await fireEvent.change(screen.getByLabelText(t('workspace.type')), { target: { value: 'managed' } });
		await loaded();
		expect(card('Built-in example')).toBeTruthy();
		expect(screen.queryByRole('heading', { name: new RegExp(t('browse')) })).toBeNull();
		expect(screen.queryByRole('button', { name: t('workspace.more') })).toBeNull();
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'missing' } });
		await screen.findByText(t('emptySearch'));
		expect(screen.queryByRole('article', { name: 'Built-in example' })).toBeNull();
		expect(screen.queryByRole('button', { name: t('workspace.more') })).toBeNull();
	});

	it('requests q and next_offset while keeping featured catalog results independent', async () => {
		featured = [template({ id: 'featured-only', name: 'Featured default tool', featured: true })];
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/mcp-settings?offset=0&limit=12&q=remote+tool') return Promise.resolve(settings({ entries: [template({ name: 'Search page one' })], total: 13, next_offset: 12 }));
			if (path === '/api/v1/chat/mcp-settings?offset=12&limit=12&q=remote+tool') return Promise.resolve(settings({ entries: [template({ id: 'page-two', name: 'Search page two' })], total: 13, offset: 12 }));
			if (path === '/api/v1/chat/mcp-settings?offset=0&limit=24&q=remote+tool') return Promise.resolve(settings({ entries: [template({ name: 'Search page one' }), template({ id: 'page-two', name: 'Search page two' })], total: 13 }));
			return response(path);
		});
		render(ChatMcpGallery);
		await loaded();
		expect(screen.getByRole('heading', { name: t('featured') })).toBeTruthy();
		expect(card('Featured default tool')).toBeTruthy();
		await fireEvent.input(screen.getByRole('searchbox', { name: t('search') }), { target: { value: '  remote tool  ' } });
		expect(mocks.get.mock.calls.some(([path]) => path.includes('q=remote+tool'))).toBe(false);
		await screen.findByRole('article', { name: 'Search page one' });
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?offset=0&limit=12&q=remote+tool', 'token-1', 'project-1', expect.objectContaining({ refresh: true, signal: expect.any(AbortSignal) }));
		await fireEvent.click(screen.getByRole('button', { name: t('workspace.more') }));
		await screen.findByRole('article', { name: 'Search page two' });
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?offset=12&limit=12&q=remote+tool', 'token-1', 'project-1', expect.anything());
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?featured=true&offset=0&limit=100', 'token-1', 'project-1', expect.anything());
		expect(card('Featured default tool')).toBeTruthy();
		expect(card('Search page one')).toBeTruthy();
		expect(screen.queryByRole('button', { name: t('workspace.more') })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await loaded();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?offset=0&limit=24&q=remote+tool', 'token-1', 'project-1', expect.anything());
		expect(card('Search page two')).toBeTruthy();
		await replaceActor({ projectId: 'project-2' });
		await loaded();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?offset=0&limit=12', 'token-1', 'project-2', expect.anything());
	});

	it('keeps each failed mutation error and pending state scoped to its own connection', async () => {
		servers = [connection(), connection({ id: 12, name: 'Second connection' })];
		const first = deferred<unknown>(), second = deferred<unknown>();
		mocks.patch.mockImplementation((path: string) => path.endsWith('/11') ? first.promise : second.promise);
		render(ChatMcpGallery);
		await loaded();
		await fireEvent.click(within(await row('Personal connection')).getByRole('button', { name: t('activate') }));
		expect(within(await row('Personal connection')).getByRole('button', { name: t('activate') }).hasAttribute('disabled')).toBe(true);
		expect(within(await row('Second connection')).getByRole('button', { name: t('activate') }).hasAttribute('disabled')).toBe(false);
		await settle(() => first.reject(new Error('first row private failure')));
		expect(within(await row('Personal connection')).getByRole('alert').textContent).toContain(t('actionFailed'));
		expect(within(await row('Second connection')).queryByRole('alert')).toBeNull();
		await fireEvent.click(within(await row('Second connection')).getByRole('button', { name: t('activate') }));
		await settle(() => second.reject(new Error('second row private failure')));
		expect(within(await row('Personal connection')).getByRole('alert')).toBeTruthy();
		expect(within(await row('Second connection')).getByRole('alert')).toBeTruthy();
		expect(document.body.textContent).not.toContain('private failure');
		expect(within(await row('Personal connection')).getByText(t('inactive'))).toBeTruthy();
		expect(within(await row('Personal connection')).queryByText(t('workspace.error'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await loaded();
		expect(within(await row('Personal connection')).queryByRole('alert')).toBeNull();
		expect(within(await row('Second connection')).queryByRole('alert')).toBeNull();
		expect(within(await row('Personal connection')).getByText(t('inactive'))).toBeTruthy();
	});

	it('installs featured global templates without silently activating them', async () => {
		auth.update((actor) => ({ ...actor, isSystemAdmin: true }));
		const entry = template({ id: 'featured-admin', name: 'Administrator featured tool', featured: true });
		mocks.get.mockImplementation((path: string) => path === '/api/v1/chat/admin/mcp-registry' ? Promise.resolve({ entries: [entry] }) : response(path));
		mocks.post.mockResolvedValue({ counts: { created: 2, existing: 1, skipped: 3, failed: 0 } });
		render(ChatMcpGallery, { admin: true, onChanged: mocks.changed });
		await waitFor(() => expect(screen.getAllByRole('article', { name: entry.name })).toHaveLength(2));
		await fireEvent.click(screen.getByRole('button', { name: t('installFeatured') }));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/admin/mcp-registry/install-featured', undefined, 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
		await screen.findByText(t('installSummary', { created: 2, existing: 1, skipped: 3, failed: 0 }));
		await waitFor(() => expect(mocks.changed).toHaveBeenCalledTimes(1));
		expect(mocks.patch).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/chat/mcp-settings?access=managed&offset=0&limit=100', 'token-1', 'project-1', expect.objectContaining({ refresh: true, signal: expect.any(AbortSignal) }));
		expect(mocks.get.mock.calls.every(([path]) => path === '/api/v1/chat/admin/mcp-registry' || path === '/api/v1/chat/mcp-settings?access=managed&offset=0&limit=100')).toBe(true);
	});

	it('uses actual managed settings availability instead of the administrator registry placeholder', async () => {
		auth.update((actor) => ({ ...actor, isSystemAdmin: true }));
		const entry = template({
			id: 'managed-admin', name: 'Managed administrator tool', access: 'managed',
			managed: { profile: 'playwright', available: true, reason: null, tools: ['outdated_tool'] }
		});
		managed = [{
			...entry,
			managed: { profile: 'playwright', available: false, reason: 'profile_not_in_enabled_sandbox_manifest', tools: ['browser_navigate'] }
		}];
		mocks.get.mockImplementation((path: string) => path === '/api/v1/chat/admin/mcp-registry' ? Promise.resolve({ entries: [entry] }) : response(path));
		render(ChatMcpGallery, { admin: true });
		const managedCard = within(await screen.findByRole('article', { name: entry.name }));
		expect(managedCard.getByText(t('profileMissing'))).toBeTruthy();
		expect(managedCard.getByText('browser_navigate')).toBeTruthy();
		expect(managedCard.queryByText(t('managedAvailable'))).toBeNull();
		expect(managedCard.queryByText('outdated_tool')).toBeNull();
		expect(managedCard.queryByRole('button')).toBeNull();
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it.each([403, 503])('keeps administrator remote installs available when managed settings returns %s', async (status) => {
		auth.update((actor) => ({ ...actor, isSystemAdmin: true }));
		const remote = template({ id: 'remote-admin', name: 'Remote administrator tool' });
		const staleManaged = template({
			id: 'managed-admin', name: 'Unknown managed tool', access: 'managed',
			managed: { profile: 'playwright', available: true, reason: null, tools: ['stale_registry_tool'] }
		});
		mocks.get.mockImplementation((path: string) => {
			if (path === '/api/v1/chat/admin/mcp-registry') return Promise.resolve({ entries: [remote, staleManaged] });
			if (path.includes('/mcp-settings?access=managed')) return Promise.reject(Object.assign(new Error('Managed status unavailable'), { status }));
			return response(path);
		});
		render(ChatMcpGallery, { admin: true, onChanged: mocks.changed });
		const remoteCard = within(await screen.findByRole('article', { name: remote.name }));
		expect(remoteCard.getByRole('button', { name: t('install') }).hasAttribute('disabled')).toBe(false);
		const unknown = within(card(staleManaged.name));
		expect(unknown.getByText(t('managedUnknown'))).toBeTruthy();
		expect(unknown.queryByText(t('managedAvailable'))).toBeNull();
		expect(unknown.queryByText('stale_registry_tool')).toBeNull();
		expect(unknown.queryByRole('button')).toBeNull();
		expect(screen.queryByText(t('loadFailed'))).toBeNull();
		await fireEvent.click(remoteCard.getByRole('button', { name: t('install') }));
		await fireEvent.click(screen.getByRole('button', { name: t('save') }));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/chat/admin/mcp-registry/remote-admin/install', expect.objectContaining({ auth_mode: 'none' }), 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
		await waitFor(() => expect(mocks.changed).toHaveBeenCalledTimes(1));
		expect(screen.queryByText(t('loadFailed'))).toBeNull();
	});

	it.each([403, 503, null])('keeps personal, global and catalog controls usable without organization rows after %s', async (status) => {
		auth.update((actor) => ({ ...actor, isDomainManager: true }));
		page = status === null
			? settings({ organization_available: false, domain_id: null, can_manage_domain: false })
			: settings({ can_manage_domain: true });
		servers = [
			connection({ name: 'Personal survivor' }),
			connection({ id: 12, scope: 'global', name: 'Global survivor' })
		];
		mocks.get.mockImplementation((path: string) => path.includes('/domains/domain-1/mcp-connections?')
			? Promise.reject(Object.assign(new Error('Organization lookup unavailable'), { status }))
			: response(path));
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await screen.findByText(t('organizationUnavailable'));
		expect(card('Public catalog tool')).toBeTruthy();
		expect(within(card('Public catalog tool')).getByRole('button', { name: t('workspace.manage') })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('workspace.add') }));
		await fireEvent.click(screen.getByRole('menuitem', { name: t('connectPersonal') }));
		expect(within(card('Public catalog tool')).getByRole('button', { name: t('workspace.connect') }).hasAttribute('disabled')).toBe(false);
		expect(within(await row('Global survivor')).getByRole('button', { name: t('activate') }).hasAttribute('disabled')).toBe(false);
		await expectOrganizationOption(false);
		expect(screen.queryByText(t('managerHelp'))).toBeNull();
		expect(screen.queryByText(t('loadFailed'))).toBeNull();
		const unavailable = within(screen.getByRole('region', { name: t('organization') }));
		expect(unavailable.queryByText(t('emptyConnections'))).toBeNull();
		expect(unavailable.queryByRole('button')).toBeNull();
		await fireEvent.click(within(await row('Personal survivor')).getByRole('button', { name: t('activate') }));
		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/chat/mcp-connections/11', { is_active: true }, 'token-1', 'project-1', { signal: expect.any(AbortSignal) });
		await waitFor(() => expect(mocks.changed).toHaveBeenCalledTimes(1));
		expect(screen.getByText(t('organizationUnavailable'))).toBeTruthy();
		expect(screen.queryByText(t('loadFailed'))).toBeNull();
		expect(mocks.get.mock.calls.some(([path]) => path.includes('/domains/'))).toBe(status !== null);
	});

	it.each([403, 503, null])('preserves independently returned organization use without management authority after %s', async (status) => {
		auth.update((actor) => ({ ...actor, isDomainManager: true }));
		page = status === null
			? settings({ organization_available: false, domain_id: null, can_manage_domain: false })
			: settings({ can_manage_domain: true });
		const nativeDomain = status === null ? 'native-org/one' : 'domain-1';
		const shared = connection({
			id: 21, scope: 'domain', owner_domain_id: nativeDomain, name: 'Independently visible organization tool',
			auth_mode: 'oauth', auth_connected: true, config_version: 29,
			activation_is_active: true, activation_config_version: 28
		});
		servers = [
			shared,
			connection({ id: 22, scope: 'domain', owner_domain_id: null, name: 'Missing organization owner' })
		];
		mocks.get.mockImplementation((path: string) => path.includes('/domains/domain-1/mcp-connections?')
			? Promise.reject(Object.assign(new Error('Organization management lookup unavailable'), { status }))
			: response(path));
		render(ChatMcpGallery, { onChanged: mocks.changed });
		await screen.findByText(t('organizationManagementUnavailable'));
		const controls = within(await row(shared.name));
		expect(controls.getByText(t('stale'))).toBeTruthy();
		expect(controls.getByRole('button', { name: t('activate') }).hasAttribute('disabled')).toBe(false);
		for (const name of [t('edit'), t('delete'), t('reconnect'), t('revokeOAuth')]) expect(controls.queryByRole('button', { name })).toBeNull();
		await expectOrganizationOption(false);
		expect(screen.queryByText(t('managerHelp'))).toBeNull();
		expect(screen.queryByText('Missing organization owner')).toBeNull();
		expect(within(screen.getByRole('region', { name: t('organization') })).queryByText(t('emptyConnections'))).toBeNull();
		expect(screen.queryByText(t('loadFailed'))).toBeNull();
		await fireEvent.click(controls.getByRole('button', { name: t('activate') }));
		expect(mocks.patch).toHaveBeenCalledWith(
			`/api/v1/chat/domains/${encodeURIComponent(nativeDomain)}/mcp-connections/21/activation`,
			{ is_active: true, config_version: 29 }, 'token-1', 'project-1', { signal: expect.any(AbortSignal) }
		);
		await waitFor(() => expect(mocks.changed).toHaveBeenCalledTimes(1));
		expect(screen.getByText(shared.name)).toBeTruthy();
		expect(screen.getByText(t('organizationManagementUnavailable'))).toBeTruthy();
	});
});
