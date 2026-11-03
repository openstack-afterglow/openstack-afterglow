import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pendingMcpConsentTicket } from '$lib/utils/mcpConsent';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/public-entry';
import type { McpConsentProject } from '$lib/utils/mcpConsentPermissions';

const { api, auth, projectSwitching, goto, page } = vi.hoisted(() => {
	function store<T>(initial: T) {
		let value = initial;
		const subscribers = new Set<(next: T) => void>();
		return {
			subscribe(run: (next: T) => void) {
				subscribers.add(run);
				run(value);
				return () => subscribers.delete(run);
			},
			set(next: T) {
				value = next;
				for (const run of subscribers) run(value);
			},
		};
	}
	return {
		api: { get: vi.fn(), post: vi.fn() },
		auth: store<{ token: string | null; userId: string | null; projectId: string | null }>({ token: null, userId: null, projectId: null }),
		projectSwitching: store(false),
		goto: vi.fn(),
		page: store({ url: new URL('http://localhost/oauth/mcp/authorize'), data: {} }),
	};
});

vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$app/stores', () => ({ page }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(_status: number, detail: string) { super(detail); } } }));
vi.mock('$lib/stores/auth', () => ({ auth, projectSwitching }));

import Page from '../+page.svelte';

const ticket = 'A'.repeat(43);
const otherTicket = 'B'.repeat(43);
const actor = { token: 'token-a', userId: 'user-a', projectId: 'project-a' };
const details = {
	client_id: 'desktop-client', client_name: 'Desktop MCP',
	redirect_uri: 'https://client.example.test/callback',
	scopes: ['mcp:read'], grant_deadline: '2026-12-31T23:59:59Z',
};
const projects: McpConsentProject[] = [
	{
		id: 'project-a', name: 'Current project', can_write: true,
		service_permissions: {
			drover: ['drover-inventory_reader', 'drover-access_user', 'drover-clusters_editor'],
			palimpsest: ['palimpsest-download_user'],
			waygate: [],
			lumen: ['lumen-inventory_reader', 'lumen-history_reader', 'lumen-chat_user', 'lumen-tools_user'],
		},
		service_errors: {},
	},
	{
		id: 'project-b', name: 'Second project', can_write: false,
		service_permissions: {
			drover: [], palimpsest: ['palimpsest-inventory_reader', 'palimpsest-publish_editor'],
			waygate: ['waygate-inventory_reader', 'waygate-connect_user'], lumen: ['lumen-keys_editor'],
		},
		service_errors: {},
	},
];
const getOptions = { refresh: true, suppressAuthRedirect: true, signal: expect.any(AbortSignal) };
const assign = vi.fn();

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
function setTicket(value: string) {
	page.set({ url: new URL(`http://localhost/oauth/mcp/authorize?ticket=${value}`), data: {} });
}
function defaultGets(scopes = ['mcp:read'], available = projects) {
	api.get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/auth/mcp-projects?preview=true' ? available : { ...details, scopes }));
}
function approveButton() { return screen.getByRole('button', { name: t('mcpConsent.actions.allowRead') }) as HTMLButtonElement; }
function checkbox(id: string) { return screen.getByRole('checkbox', { name: new RegExp(id) }) as HTMLInputElement; }
async function loaded() { await screen.findByRole('combobox', { name: t('mcpConsent.access.label') }); }
function preview() { return within(screen.getByRole('region', { name: t('mcpConsent.preview.title') })); }
function projectPreview(id: string) { return within(preview().getByRole('listitem', { name: new RegExp(id) })); }
async function chooseAccess(access: 'read' | 'manage') {
	await fireEvent.change(screen.getByRole('combobox', { name: t('mcpConsent.access.label') }), { target: { value: access } });
}
async function chooseScope(scope: 'selected' | 'all') {
	await fireEvent.change(screen.getByRole('combobox', { name: t('mcpConsent.projects.label') }), { target: { value: scope } });
}
function expectDecision(decision: 'approve' | 'deny', body: unknown, token: string, projectId: string) {
	expect(api.post).toHaveBeenCalledWith(`/api/v1/auth/mcp-oauth/consents/${ticket}/${decision}`,
		body, token, projectId, { signal: expect.any(AbortSignal), suppressAuthRedirect: true, cache: 'no-store' });
}

const transitions = ['token', 'user', 'project', 'logout', 'switching', 'ticket', 'aba', 'token-aba', 'project-aba', 'ticket-aba', 'switch-aba'] as const;
type Transition = typeof transitions[number];
function transition(kind: Transition) {
	if (kind === 'token') auth.set({ ...actor, token: 'token-b' });
	else if (kind === 'user') auth.set({ ...actor, userId: 'user-b' });
	else if (kind === 'project') auth.set({ ...actor, projectId: 'project-b' });
	else if (kind === 'logout') auth.set({ token: null, userId: null, projectId: null });
	else if (kind === 'switching') projectSwitching.set(true);
	else if (kind === 'ticket') setTicket(otherTicket);
	else if (kind === 'ticket-aba') { setTicket(otherTicket); setTicket(ticket); }
	else if (kind === 'switch-aba') { projectSwitching.set(true); projectSwitching.set(false); }
	else if (kind === 'token-aba') { auth.set({ ...actor, token: 'token-b' }); auth.set(actor); }
	else if (kind === 'project-aba') { auth.set({ ...actor, projectId: 'project-b' }); auth.set(actor); }
	else {
		auth.set({ ...actor, userId: 'user-b' });
		auth.set(actor);
	}
}

describe('MCP OAuth consent route', () => {
	beforeEach(() => {
		vi.resetAllMocks();
		initLocale('ko');
		sessionStorage.clear();
		auth.set(actor);
		projectSwitching.set(false);
		setTicket(ticket);
		defaultGets();
		api.post.mockResolvedValue({ redirect_uri: 'https://client.example.test/approved' });
		// jsdom's Location.assign is non-configurable. Preserve the real Window for
		// DOM APIs and storage while observing only this route's external redirect.
		const realWindow = window;
		vi.stubGlobal('window', new Proxy(realWindow, {
			get(target, key) {
				return key === 'location' ? { assign } : Reflect.get(target, key, target);
			},
		}));
	});
	afterEach(() => {
		cleanup();
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
		sessionStorage.clear();
		initLocale('ko');
	});

	it('scrubs the ticket and loads fresh authoritative consent and project metadata', async () => {
		const replaceState = vi.spyOn(history, 'replaceState');
		render(Page);
		await loaded();
		expect(pendingMcpConsentTicket()).toBe(ticket);
		expect(replaceState).toHaveBeenCalledWith(null, '', '/oauth/mcp/authorize');
		expect(api.get).toHaveBeenCalledWith(`/api/v1/auth/mcp-oauth/consents/${ticket}`, actor.token, actor.projectId, getOptions);
		expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects?preview=true', actor.token, actor.projectId, getOptions);
		expect(checkbox('project-a').checked).toBe(true);
		expect(checkbox('project-b').checked).toBe(false);
		expect(goto).not.toHaveBeenCalled();
	});

	it.each(['login', 'select-project'])('preserves the ticket before the %s redirect', async (destination) => {
		auth.set(destination === 'login' ? { token: null, userId: null, projectId: null } : { ...actor, projectId: null });
		render(Page);
		await waitFor(() => expect(goto).toHaveBeenCalledWith(`/${destination}`));
		expect(pendingMcpConsentTicket()).toBe(ticket);
		expect(api.get).not.toHaveBeenCalled();
		auth.set(actor);
		await loaded();
		expect(api.get).toHaveBeenCalledTimes(2);
	});

	it('rejects malformed query tickets without fetching metadata', async () => {
		setTicket('invalid');
		render(Page);
		await screen.findByText(t('mcpConsent.error.invalidRequest'));
		expect(pendingMcpConsentTicket()).toBeNull();
		expect(api.get).not.toHaveBeenCalled();
	});

	it.each(['ko', 'en', 'ja', 'zh-CN', 'bn', 'ms', 'nb', 'sw', 'vi'] as const)('labels the choices in %s and disables unrequested manage access', async (locale) => {
		initLocale(locale);
		render(Page);
		await loaded();
		expect((screen.getByRole('option', { name: t('mcpConsent.access.manage') }) as HTMLOptionElement).disabled).toBe(true);
		expect(screen.getByText(t('mcpConsent.access.manageUnavailable'))).toBeTruthy();
		expect((screen.getByRole('combobox', { name: t('mcpConsent.access.label') }) as HTMLSelectElement).value).toBe('read');
		expect(screen.getByRole('combobox', { name: t('mcpConsent.projects.label') })).toBeTruthy();
		expect(projectPreview('project-a').getByText(t('mcpConsent.preview.cloud.read'))).toBeTruthy();
		expect(projectPreview('project-a').getByText(t('mcpConsent.preview.service.denied'))).toBeTruthy();
		expect(projectPreview('project-a').getByText(t('mcpConsent.permission.droverAccess'))).toBeTruthy();
		expect(projectPreview('project-a').queryByText(t('mcpConsent.permission.lumenChat'))).toBeNull();
		await fireEvent.click(approveButton());
		expectDecision('approve', {
			access_level: 'read', project_scope: 'selected', project_ids: ['project-a'],
		}, actor.token, actor.projectId);
	});

	it('narrows a write request to read with the explicitly selected projects', async () => {
		defaultGets(['mcp:read', 'mcp:write']);
		render(Page);
		await loaded();
		expect((screen.getByRole('option', { name: t('mcpConsent.access.manage') }) as HTMLOptionElement).disabled).toBe(false);
		await fireEvent.click(checkbox('project-a'));
		expect(approveButton().disabled).toBe(true);
		await fireEvent.click(approveButton());
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.click(checkbox('project-b'));
		await fireEvent.click(approveButton());
		expectDecision('approve', {
			access_level: 'read', project_scope: 'selected', project_ids: ['project-b'],
		}, actor.token, actor.projectId);
		await waitFor(() => expect(assign).toHaveBeenCalledWith('https://client.example.test/approved'));
		expect(pendingMcpConsentTicket()).toBeNull();
	});

	it.each(['read', 'manage'] as const)('sends explicit %s access and no IDs for all-project approval', async (access) => {
		defaultGets(access === 'manage' ? ['mcp:read', 'mcp:write'] : ['mcp:read']);
		render(Page);
		await loaded();
		await fireEvent.change(screen.getByRole('combobox', { name: t('mcpConsent.access.label') }), { target: { value: access } });
		await fireEvent.change(screen.getByRole('combobox', { name: t('mcpConsent.projects.label') }), { target: { value: 'all' } });
		expect(screen.queryByRole('checkbox')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t(access === 'manage' ? 'mcpConsent.actions.allowManage' : 'mcpConsent.actions.allowRead') }));
		expectDecision('approve', {
			access_level: access, project_scope: 'all', project_ids: [],
		}, actor.token, actor.projectId);
	});

	it('previews all mixed projects with independent native service leaves without granting on selection', async () => {
		defaultGets(['mcp:read', 'mcp:write']);
		render(Page);
		await loaded();
		expect(preview().queryByRole('listitem', { name: /project-b/ })).toBeNull();
		await chooseAccess('manage');
		await chooseScope('all');
		expect(projectPreview('project-a').getByText(t('mcpConsent.preview.cloud.manage'))).toBeTruthy();
		expect(projectPreview('project-b').getByText(t('mcpConsent.preview.cloud.read'))).toBeTruthy();
		expect(projectPreview('project-a').getByText('drover-clusters_editor')).toBeTruthy();
		expect(projectPreview('project-a').getByText('lumen-chat_user')).toBeTruthy();
		expect(projectPreview('project-b').getByText('palimpsest-publish_editor')).toBeTruthy();
		expect(projectPreview('project-b').getByText('lumen-keys_editor')).toBeTruthy();
		expect(projectPreview('project-b').getByText(t('mcpConsent.permission.lumenKeys'))).toBeTruthy();
		for (const name of ['Drover', 'Palimpsest', 'Waygate', 'Lumen']) {
			expect(projectPreview('project-a').getByText(name)).toBeTruthy();
			expect(projectPreview('project-b').getByText(name)).toBeTruthy();
		}
		expect(preview().queryByText('waygate-clients_editor')).toBeNull();
		expect(screen.getByText(t('mcpConsent.manage.body'))).toBeTruthy();
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('mcpConsent.actions.allowManage') }));
		expectDecision('approve', { access_level: 'manage', project_scope: 'all', project_ids: [] }, actor.token, actor.projectId);
	});

	it('immediately attenuates every project and service when manage changes to read', async () => {
		defaultGets(['mcp:read', 'mcp:write']);
		render(Page);
		await loaded();
		await chooseScope('all');
		await chooseAccess('manage');
		expect(preview().getByText('lumen-tools_user')).toBeTruthy();
		await chooseAccess('read');
		expect(preview().getAllByText(t('mcpConsent.preview.cloud.read'))).toHaveLength(2);
		expect(preview().queryByText(t('mcpConsent.preview.cloud.manage'))).toBeNull();
		for (const leaf of ['drover-clusters_editor', 'palimpsest-publish_editor', 'lumen-chat_user', 'lumen-tools_user', 'lumen-keys_editor']) {
			expect(preview().queryByText(leaf)).toBeNull();
		}
		for (const leaf of ['drover-inventory_reader', 'drover-access_user', 'palimpsest-download_user', 'waygate-connect_user', 'lumen-history_reader']) {
			expect(preview().getByText(leaf)).toBeTruthy();
		}
		expect(projectPreview('project-b').getByText(t('mcpConsent.preview.service.attenuated'))).toBeTruthy();
		expect(api.post).not.toHaveBeenCalled();
		await fireEvent.click(approveButton());
		expectDecision('approve', { access_level: 'read', project_scope: 'all', project_ids: [] }, actor.token, actor.projectId);
	});

	it('updates selected preview and refuses selected manage readers without losing the explicit selection', async () => {
		defaultGets(['mcp:read', 'mcp:write']);
		render(Page);
		await loaded();
		await chooseAccess('manage');
		await fireEvent.click(checkbox('project-b'));
		expect(projectPreview('project-b').getByText(t('mcpConsent.preview.cloud.read'))).toBeTruthy();
		const manage = () => screen.getByRole('button', { name: t('mcpConsent.actions.allowManage') }) as HTMLButtonElement;
		expect(manage().disabled).toBe(true);
		expect(screen.getByText(t('mcpConsent.preview.selectedReadOnly'))).toBeTruthy();
		await fireEvent.click(manage());
		expect(api.post).not.toHaveBeenCalled();
		await chooseScope('all');
		expect(manage().disabled).toBe(false);
		await chooseScope('selected');
		expect(manage().disabled).toBe(true);
		expect(checkbox('project-b').checked).toBe(true);
		await fireEvent.click(checkbox('project-b'));
		expect(preview().queryByRole('listitem', { name: /project-b/ })).toBeNull();
		expect(manage().disabled).toBe(false);
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each(['missing', 'error'] as const)('never presents %s native service metadata as allowed or verified denial', async (kind) => {
		defaultGets(['mcp:read', 'mcp:write'], [{
			...projects[0],
			service_permissions: kind === 'missing' ? undefined : projects[0].service_permissions,
			service_errors: kind === 'missing' ? undefined : { drover: 'permission_check_unavailable' },
		}]);
		render(Page);
		await loaded();
		await chooseAccess('manage');
		expect(projectPreview('project-a').getAllByText(t('mcpConsent.preview.service.unavailable'))).toHaveLength(kind === 'missing' ? 4 : 1);
		expect(preview().queryByText('drover-clusters_editor')).toBeNull();
		expect(preview().queryByText('permission_check_unavailable')).toBeNull();
		if (kind === 'error') expect(preview().getByText('lumen-chat_user')).toBeTruthy();
		else expect(preview().queryByText(t('mcpConsent.preview.service.denied'))).toBeNull();
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each([undefined, null])('keeps unavailable cloud metadata %s unknown in read and manage mode', async (canWrite) => {
		defaultGets(['mcp:read', 'mcp:write'], [{ ...projects[0], can_write: canWrite }]);
		render(Page);
		await loaded();
		await chooseAccess('manage');
		await chooseScope('all');
		expect(projectPreview('project-a').getByText(t('mcpConsent.preview.cloud.unknown'))).toBeTruthy();
		expect(preview().queryByText(t('mcpConsent.preview.cloud.manage'))).toBeNull();
		expect(screen.getByText(t('mcpConsent.preview.unknownWrite'))).toBeTruthy();
		const manage = screen.getByRole('button', { name: t('mcpConsent.actions.allowManage') }) as HTMLButtonElement;
		expect(manage.disabled).toBe(true);
		await fireEvent.click(manage);
		expect(api.post).not.toHaveBeenCalled();
		await chooseAccess('read');
		expect(projectPreview('project-a').getByText(t('mcpConsent.preview.cloud.unknown'))).toBeTruthy();
		expect(approveButton().disabled).toBe(false);
	});

	it('cannot elevate a read request by forcing the disabled manage option', async () => {
		render(Page);
		await loaded();
		await fireEvent.change(screen.getByRole('combobox', { name: t('mcpConsent.access.label') }), { target: { value: 'manage' } });
		await fireEvent.click(approveButton());
		expect(api.post.mock.calls[0][1].access_level).toBe('read');
	});

	it('blocks duplicate decisions while approval is pending', async () => {
		const decision = deferred<{ redirect_uri: string }>();
		api.post.mockReturnValueOnce(decision.promise);
		render(Page);
		await loaded();
		await fireEvent.click(approveButton());
		await fireEvent.click(approveButton());
		await fireEvent.click(screen.getByRole('button', { name: t('mcpConsent.actions.deny') }));
		expect(api.post).toHaveBeenCalledTimes(1);
		await act(async () => decision.resolve({ redirect_uri: 'https://client.example.test/approved' }));
	});

	it('restores explicit selection when switching back from all projects', async () => {
		render(Page);
		await loaded();
		await fireEvent.click(checkbox('project-b'));
		const scope = screen.getByRole('combobox', { name: t('mcpConsent.projects.label') });
		await fireEvent.change(scope, { target: { value: 'all' } });
		await fireEvent.change(scope, { target: { value: 'selected' } });
		expect(checkbox('project-a').checked).toBe(true);
		expect(checkbox('project-b').checked).toBe(true);
		await fireEvent.click(approveButton());
		expect(api.post.mock.calls[0][1].project_ids).toEqual(['project-a', 'project-b']);
	});

	it.each([{ available: [] }, { available: [projects[1]] }])('never uses a current project missing from the authoritative list $available', async ({ available }) => {
		defaultGets(['mcp:read'], available);
		render(Page);
		await loaded();
		expect(approveButton().disabled).toBe(true);
		await fireEvent.click(approveButton());
		expect(api.post).not.toHaveBeenCalled();
	});

	it('denies with the unchanged empty body even with an empty selection', async () => {
		defaultGets(['mcp:read'], []);
		render(Page);
		await loaded();
		await fireEvent.click(screen.getByRole('button', { name: t('mcpConsent.actions.deny') }));
		expectDecision('deny', {}, actor.token, actor.projectId);
	});

	it.each(transitions)('discards both old metadata responses after %s', async (kind) => {
		const oldDetails = deferred<typeof details>();
		const oldProjects = deferred<typeof projects>();
		api.get.mockImplementationOnce(() => oldDetails.promise).mockImplementationOnce(() => oldProjects.promise);
		render(Page);
		await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
		await act(() => transition(kind));
		if (kind !== 'logout' && kind !== 'switching') await loaded();
		await act(async () => {
			oldDetails.resolve({ ...details, client_name: 'Old owner client' });
			oldProjects.resolve([{ id: 'old-project', name: 'Old owner project' }]);
		});
		expect(screen.queryByText('Old owner client')).toBeNull();
		expect(screen.queryByText('Old owner project')).toBeNull();
		expect(api.post).not.toHaveBeenCalled();
		if (kind === 'project') {
			expect(checkbox('project-a').checked).toBe(false);
			expect(checkbox('project-b').checked).toBe(true);
		}
	});

	it('discards an old load failure without clearing the replacement ticket or selection', async () => {
		const old = deferred<typeof details>();
		api.get.mockImplementationOnce(() => old.promise);
		render(Page);
		await act(() => setTicket(otherTicket));
		await loaded();
		await act(async () => old.reject(new Error('old failure')));
		expect(screen.queryByText(t('mcpConsent.error.loadFailed'))).toBeNull();
		expect(approveButton().disabled).toBe(false);
		expect(pendingMcpConsentTicket()).toBe(otherTicket);
	});

	it.each(['consent', 'projects'])('clears old selection after a %s reload failure and retries fresh', async (endpoint) => {
		defaultGets(['mcp:read', 'mcp:write']);
		render(Page);
		await loaded();
		await fireEvent.click(checkbox('project-b'));
		await fireEvent.change(screen.getByRole('combobox', { name: t('mcpConsent.access.label') }), { target: { value: 'manage' } });
		api.get.mockImplementation((path: string) => (path === '/api/v1/auth/mcp-projects?preview=true') === (endpoint === 'projects')
			? Promise.reject(new Error('reload failed')) : Promise.resolve(path === '/api/v1/auth/mcp-projects?preview=true' ? projects : details));
		await act(() => { projectSwitching.set(true); projectSwitching.set(false); });
		await screen.findByText(t('mcpConsent.error.loadFailed'));
		expect(screen.queryByRole('checkbox')).toBeNull();
		expect(screen.queryByRole('button', { name: t('mcpConsent.actions.allowManage') })).toBeNull();
		defaultGets();
		await fireEvent.click(screen.getByRole('button', { name: t('mcpConsent.actions.retry') }));
		await loaded();
		expect(checkbox('project-a').checked).toBe(true);
		expect(checkbox('project-b').checked).toBe(false);
		expect((screen.getByRole('combobox', { name: t('mcpConsent.access.label') }) as HTMLSelectElement).value).toBe('read');
	});

	it.each(transitions)('never redirects or consumes the ticket for an old decision after %s', async (kind) => {
		const decision = deferred<{ redirect_uri: string }>();
		api.post.mockReturnValueOnce(decision.promise);
		render(Page);
		await loaded();
		await fireEvent.click(approveButton());
		await act(() => transition(kind));
		await act(async () => decision.resolve({ redirect_uri: 'https://old-owner.example.test' }));
		expect(assign).not.toHaveBeenCalled();
		expect(pendingMcpConsentTicket()).toBe(kind === 'ticket' ? otherTicket : ticket);
		if (kind !== 'logout' && kind !== 'switching') {
			await loaded();
			await fireEvent.click(approveButton());
			const request = api.post.mock.calls[1];
			expect(request[0]).toContain(kind === 'ticket' ? otherTicket : ticket);
			expect(request[1]).toEqual({ access_level: 'read', project_scope: 'selected', project_ids: [kind === 'project' ? 'project-b' : 'project-a'] });
			expect(request[2]).toBe(kind === 'token' ? 'token-b' : actor.token);
			expect(request[3]).toBe(kind === 'project' ? 'project-b' : actor.projectId);
		}
	});

	it.each(['success', 'failure'])('does not finish a replacement decision when an old decision returns %s', async (outcome) => {
		const old = deferred<{ redirect_uri: string }>();
		const current = deferred<{ redirect_uri: string }>();
		api.post.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
		render(Page);
		await loaded();
		await fireEvent.click(approveButton());
		await act(() => transition('aba'));
		await loaded();
		await fireEvent.click(approveButton());
		await act(async () => {
			if (outcome === 'success') old.resolve({ redirect_uri: 'https://old.example.test' });
			else old.reject(new Error('old decision failed'));
		});
		expect(assign).not.toHaveBeenCalled();
		expect(approveButton().disabled).toBe(true);
		expect(screen.queryByText(t('mcpConsent.error.approveFailed'))).toBeNull();
		await act(async () => current.resolve({ redirect_uri: 'https://current.example.test' }));
		expect(assign).toHaveBeenCalledWith('https://current.example.test');
	});

	it('invalidates in-flight work on unmount', async () => {
		const decision = deferred<{ redirect_uri: string }>();
		api.post.mockReturnValueOnce(decision.promise);
		const rendered = render(Page);
		await loaded();
		await fireEvent.click(approveButton());
		rendered.unmount();
		await act(async () => decision.resolve({ redirect_uri: 'https://late.example.test' }));
		expect(assign).not.toHaveBeenCalled();
		expect(pendingMcpConsentTicket()).toBe(ticket);
	});
});
