import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { acceptAuthVerification, auth, authReady, clearAuth, getAuthVerificationEpoch, logoutInProgress, projectSwitching, setAuth, setLoginAuth } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import type * as ClientModule from '$lib/api/client';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/workspace-selector';
import { t as tp } from '$lib/i18n/ns/public-entry';
import { storePendingInvitation, takePendingInvitationPath } from '$lib/utils/domainLogin';
import { pendingMcpConsentTicket, storeMcpConsentTicket } from '$lib/utils/mcpConsent';
import { loginAuthState } from '$lib/utils/authSession';
import { workspacePreferenceKey } from '$lib/stores/workspacePreferences';
import type { WorkspaceInventory } from '$lib/stores/workspaceController.svelte';
import type { SessionTokenResponse } from '$lib/types/auth';
import Page from './+page.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), goto: vi.fn(), close: vi.fn() }));
vi.mock('$app/environment', () => ({ browser: true, dev: false, building: false, version: 'test' }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
vi.mock('$app/stores', () => ({ page: { subscribe(run: (value: unknown) => void) { run({ data: { mockup: { active: false } } }); return () => {}; } } }));
vi.mock('$lib/api/client', async (importOriginal) => ({ ...(await importOriginal<typeof ClientModule>()), api: { get: mocks.get, post: mocks.post }, beginSessionRevocation: vi.fn(), endSessionRevocation: vi.fn() }));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: mocks.close } }));

const home = { id: 'home', name: 'Home' };
const team = { id: 'team', name: 'Team' };
const createdDomain = { id: 'created', name: 'Created', description: '', enabled: true, default_project_id: 'created-default' };
const switchResponse: SessionTokenResponse = {
	token: 'team-token', refresh_token: 'team-refresh', user_id: 'alice', username: 'alice',
	identity_domain_id: home.id, identity_domain_name: home.name,
	domain_id: team.id, domain_name: team.name, available_domains: [home, team], can_create_domain: true,
	project_id: 'team-project', project_name: 'Team project', expires_at: null, is_domain_manager: true,
};
function workspace(domain = home) { return { domain, projects: [{ id: `${domain.id}-project`, name: `${domain.name} project` }], default_project_id: `${domain.id}-project`, is_domain_manager: true, can_create_project: true }; }
function browse(domains = [home, team]) {
	mocks.get.mockImplementation(async (path: string) => path === '/api/v1/auth/domains' ? domains
		: path.startsWith('/api/v1/projects/capabilities') ? { domain_id: team.id, can_create_project: true }
		: workspace(domains.find(row => path.includes(`domain_id=${row.id}`)) ?? home));
}

beforeEach(() => {
	vi.resetAllMocks(); initLocale('en'); localStorage.clear(); sessionStorage.clear(); clearAuth(); logoutInProgress.set(false); projectSwitching.set(false);
	setLoginAuth({ token: 'home-token', refreshToken: 'home-refresh', userId: 'alice', username: 'alice', identityDomainId: home.id, identityDomainName: home.name, domainId: home.id, domainName: home.name, projectId: null, availableDomains: [home], canCreateDomain: true, federated: true, isDomainManager: false });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
	browse(); mocks.post.mockResolvedValue(switchResponse); mocks.goto.mockResolvedValue(undefined); mocks.close.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); projectSwitching.set(false); logoutInProgress.set(false); clearAuth(); sessionStorage.clear(); initLocale('ko'); });

async function chooseTeam() {
	await screen.findByRole('button', { name: /^Home project/ });
	await fireEvent.change(screen.getByRole('combobox', { name: t('domain') }), { target: { value: team.id } });
	await screen.findByRole('button', { name: /^Team project/ });
}
async function openCreateDomain() {
	const button = await screen.findByRole('button', { name: t('newDomain') });
	await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
	await fireEvent.click(button);
	await fireEvent.input(screen.getByRole('textbox', { name: t('domainName') }), { target: { value: createdDomain.name } });
	return screen.getByRole('button', { name: t('create') }) as HTMLButtonElement;
}

function startHomeSession() {
	// Exercise the real fresh-login mapping and readiness boundary, not a copied session shape.
	setLoginAuth(loginAuthState({ ...switchResponse, token: 'home-token', refresh_token: 'home-refresh',
		domain_id: home.id, domain_name: home.name, project_id: 'home-project', project_name: 'Home project',
		is_domain_manager: false }, { federated: true }).state);
}

describe('home-first workspace chooser', () => {
	it.each(['ko', 'en', 'ja', 'zh-CN', 'sw', 'nb', 'ms', 'vi', 'bn'] as const)('keeps account identity outside workspace options and starts at personal in %s', async locale => {
		initLocale(locale);
		const personal = { id: 'personal', name: 'Personal', kind: 'personal' as const };
		const organization = { ...team, kind: 'organization' as const };
		setLoginAuth(loginAuthState({ ...switchResponse, identity_domain_id: 'account-id', identity_domain_name: 'account',
			domain_id: personal.id, domain_name: personal.name, project_id: 'personal-project', project_name: 'Personal project',
			available_domains: [personal, organization], is_domain_manager: false }, { federated: false }).state);
		browse([organization, personal]);
		mocks.post.mockResolvedValueOnce({ ...switchResponse, identity_domain_id: 'account-id', identity_domain_name: 'account', available_domains: [personal, organization] });
		render(Page);
		await screen.findByRole('button', { name: /personal-project$/ });
		expect((screen.getByRole('combobox', { name: t('domain') }) as HTMLSelectElement).value).toBe(personal.id);
		expect(screen.getAllByRole('option').map(option => (option as HTMLOptionElement).value)).toEqual([personal.id, team.id]);
		expect(screen.getByRole('option', { name: new RegExp(t('personal')) })).toBeTruthy();
		await fireEvent.change(screen.getByRole('combobox', { name: t('domain') }), { target: { value: team.id } });
		await fireEvent.click(await screen.findByRole('button', { name: /team-project$/ }));
		await waitFor(() => expect(get(auth).domainId).toBe(team.id));
		expect(get(auth)).toMatchObject({ identityDomainId: 'account-id', projectId: 'team-project' });
	});
	it.each(['empty', 'organization-first'] as const)('initially shows the current home with %s display preferences and no verification fetch', async preferences => {
		startHomeSession();
		if (preferences === 'organization-first') {
			localStorage.setItem(workspacePreferenceKey(home.id, 'alice'), JSON.stringify({
				domains: { home: { hidden: true, order: 1 }, team: { pinned: true, visited: 100, order: 0 } },
				projects: { 'home-project': { hidden: true }, 'team-project': { pinned: true, visited: 100 } },
			}));
		}
		const directory = Promise.withResolvers<(typeof home)[]>();
		const inventory = Promise.withResolvers<WorkspaceInventory>();
		mocks.get.mockImplementation((path: string) => path === '/api/v1/auth/domains' ? directory.promise : inventory.promise);
		render(Page);
		expect(screen.getByText(`${t('activeDomain')}: Home · home`)).toBeTruthy();
		expect(mocks.goto).not.toHaveBeenCalled();
		inventory.resolve(workspace()); await inventory.promise;
		expect(screen.queryByRole('button', { name: /^Home project/ })).toBeNull();
		directory.resolve([team, home]);
		await screen.findByRole('button', { name: /^Home project/ });
		expect((screen.getByRole('combobox', { name: t('domain') }) as HTMLSelectElement).value).toBe(home.id);
		expect(screen.getByRole('button', { name: t('all') }).getAttribute('aria-pressed')).toBe('true');
		expect(mocks.get.mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains', '/api/v1/auth/workspaces?domain_id=home']);
		expect(get(auth)).toMatchObject({ domainId: home.id, projectId: 'home-project' });
		expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it.each((['continue', 'current-project'] as const).flatMap(action =>
		(['normal', 'invitation', 'mcp'] as const).map(intent => [action, intent] as const)
	))('explicit %s resumes %s from the same home without rotating credentials', async (action, intent) => {
		startHomeSession(); const session = get(auth);
		const invitation = 'i'.repeat(32); const ticket = 'm'.repeat(32);
		if (intent === 'invitation') storePendingInvitation(invitation);
		if (intent !== 'normal') storeMcpConsentTicket(ticket);
		render(Page); await screen.findByRole('button', { name: /^Home project/ });
		expect(mocks.goto).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: action === 'continue' ? t('continue') : /^Home project/ }));
		expect(mocks.goto).toHaveBeenCalledExactlyOnceWith(intent === 'invitation' ? `/invitations/${invitation}` : intent === 'mcp' ? '/oauth/mcp/authorize' : '/dashboard');
		expect(get(auth)).toEqual(session); expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.close).not.toHaveBeenCalled();
		expect(takePendingInvitationPath()).toBeNull();
		expect(pendingMcpConsentTicket()).toBe(intent === 'normal' ? null : ticket);
	});

	it('retains invitation and MCP intent through preferences, refresh, and organization browsing until exact project selection', async () => {
		startHomeSession();
		const invitation = 'i'.repeat(32); const ticket = 'm'.repeat(32);
		storePendingInvitation(invitation); storeMcpConsentTicket(ticket);
		render(Page); await screen.findByRole('button', { name: /^Home project/ });
		await fireEvent.click(screen.getByRole('button', { name: t('pinResource', { name: 'Home project', id: 'home-project' }) }));
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await chooseTeam();
		expect(mocks.goto).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
		expect(get(auth).domainId).toBe(home.id); expect(pendingMcpConsentTicket()).toBe(ticket);
		await fireEvent.click(screen.getByRole('button', { name: /^Team project/ }));
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledExactlyOnceWith(`/invitations/${invitation}`));
		expect(get(auth)).toMatchObject({ identityDomainId: home.id, domainId: team.id, projectId: 'team-project' });
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/token/workspace', { domain_id: team.id, project_id: 'team-project' }, 'home-token', undefined, expect.objectContaining({ replayOnUnauthorized: false }));
		expect(takePendingInvitationPath()).toBeNull(); expect(pendingMcpConsentTicket()).toBe(ticket);
	});

	it('waits for root readiness and a new explicit action before resuming MCP consent', async () => {
		startHomeSession(); storeMcpConsentTicket('m'.repeat(32)); authReady.set(false);
		render(Page);
		const proceed = screen.getByRole('button', { name: t('continue') }) as HTMLButtonElement;
		expect(proceed.disabled).toBe(true); expect(mocks.get).not.toHaveBeenCalled();
		await fireEvent.click(proceed); expect(mocks.goto).not.toHaveBeenCalled();
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		await screen.findByRole('button', { name: /^Home project/ });
		expect(mocks.goto).not.toHaveBeenCalled(); expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
		await fireEvent.click(screen.getByRole('button', { name: t('continue') }));
		expect(mocks.goto).toHaveBeenCalledExactlyOnceWith('/oauth/mcp/authorize');
	});

	it.each([
		[false, false, '/select-project'], [true, false, '/dashboard/iam'], [false, true, '/admin'],
	] as const)('preserves projectless navigation for manager=%s system-admin=%s', async (isDomainManager, isSystemAdmin, destination) => {
		setAuth({ token: 'home-token', isDomainManager, isSystemAdmin });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		render(Page); await screen.findByRole('button', { name: /^Home project/ });
		expect(mocks.goto).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('continue') }));
		expect(mocks.goto).toHaveBeenCalledExactlyOnceWith(destination); expect(mocks.post).not.toHaveBeenCalled();
	});
});

describe('existing workspace navigation', () => {
	it('reopens at the committed organization without resetting to home or automatically continuing', async () => {
		startHomeSession();
		const rendered = render(Page); await chooseTeam();
		await fireEvent.click(screen.getByRole('button', { name: /^Team project/ }));
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/dashboard'));
		rendered.unmount(); mocks.get.mockClear(); mocks.goto.mockClear(); mocks.post.mockClear();
		render(Page); await screen.findByRole('button', { name: /^Team project/ });
		expect((screen.getByRole('combobox', { name: t('domain') }) as HTMLSelectElement).value).toBe(team.id);
		expect(mocks.get.mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains', '/api/v1/auth/workspaces?domain_id=team']);
		expect(get(auth)).toMatchObject({ identityDomainId: home.id, domainId: team.id, projectId: 'team-project' });
		expect(mocks.goto).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('continue') }));
		expect(mocks.goto).toHaveBeenCalledExactlyOnceWith('/dashboard'); expect(mocks.post).not.toHaveBeenCalled();
	});
});

describe('shared domain and project continuation', () => {
	it('continues without mutation, resuming retained invitation before MCP consent', async () => {
		const invitation = 'i'.repeat(32); storePendingInvitation(invitation); storeMcpConsentTicket('m'.repeat(32));
		render(Page); await screen.findByRole('button', { name: /^Home project/ });
		await fireEvent.click(screen.getByRole('button', { name: t('continue') }));
		expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.goto).toHaveBeenCalledWith(`/invitations/${invitation}`);
		expect(takePendingInvitationPath()).toBeNull(); expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});
	it('commits an exact domain/project once while preserving logical login and provider', async () => {
		const sessionId = get(auth).sessionId; const pending = Promise.withResolvers<SessionTokenResponse>(); mocks.post.mockReturnValueOnce(pending.promise);
		render(Page); await chooseTeam(); expect(get(auth).domainId).toBe(home.id);
		await fireEvent.click(screen.getByRole('button', { name: /^Team project/ }));
		expect(get(projectSwitching)).toBe(true); expect(mocks.close).toHaveBeenCalledWith('project-switch', { keepDock: false });
		pending.resolve(switchResponse); await waitFor(() => expect(get(auth).domainId).toBe(team.id));
		expect(get(auth)).toMatchObject({ identityDomainId: home.id, projectId: 'team-project', federated: true, sessionId });
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/token/workspace', { domain_id: team.id, project_id: 'team-project' }, 'home-token', undefined, expect.objectContaining({ replayOnUnauthorized: false, cache: 'no-store' }));
		expect(mocks.goto).toHaveBeenCalledWith('/dashboard');
	});
	it('allows a manager to explicitly continue through the domain endpoint', async () => {
		render(Page); await chooseTeam(); await fireEvent.click(screen.getByRole('button', { name: t('useDomain') }));
		await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/dashboard'));
		expect(mocks.post.mock.calls[0][0]).toBe('/api/v1/auth/token/domain');
	});
	it.each(['subject', 'identity', 'target', 'project'] as const)('rejects a response with a foreign %s', async (kind) => {
		mocks.post.mockResolvedValueOnce({ ...switchResponse, ...(kind === 'subject' ? { user_id: 'other' } : kind === 'identity' ? { identity_domain_id: team.id } : kind === 'target' ? { domain_id: home.id } : { project_id: 'foreign' }) });
		render(Page); await chooseTeam(); await fireEvent.click(screen.getByRole('button', { name: /^Team project/ }));
		await screen.findByText(t('switchFailed')); expect(get(auth).token).toBe('home-token'); expect(mocks.goto).not.toHaveBeenCalled();
	});
	it.each(['login', 'aba', 'unmount'] as const)('discards a late switch after %s', async (kind) => {
		storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
		const previous = get(auth); const pending = Promise.withResolvers<SessionTokenResponse>(); mocks.post.mockReturnValueOnce(pending.promise);
		const rendered = render(Page); await chooseTeam(); await fireEvent.click(screen.getByRole('button', { name: /^Team project/ }));
		if (kind === 'unmount') rendered.unmount();
		else if (kind === 'login') setLoginAuth({ ...previous, token: 'new-login' });
		else { setAuth({ token: 'other', domainId: 'other' }); setAuth({ ...previous, token: previous.token! }); }
		pending.resolve(switchResponse); await waitFor(() => expect(get(projectSwitching)).toBe(false));
		expect(get(auth).domainId).toBe(home.id); expect(mocks.goto).not.toHaveBeenCalled();
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`); expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});
	it('uses fresh memberships and refuses a revoked target while its switch is pending', async () => {
		setAuth({ token: 'home-token', availableDomains: [home, team] });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		const pending = Promise.withResolvers<SessionTokenResponse>(); mocks.post.mockReturnValueOnce(pending.promise);
		render(Page); await chooseTeam(); expect(get(auth).availableDomains).toEqual([home, team]);
		await fireEvent.click(screen.getByRole('button', { name: /^Team project/ })); setAuth({ token: 'home-token', availableDomains: [home] });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		pending.resolve(switchResponse); await waitFor(() => expect(get(projectSwitching)).toBe(false));
		expect(get(auth).domainId).toBe(home.id); expect(mocks.goto).not.toHaveBeenCalled();
	});
});

describe('explicit creation in the browsed domain', () => {
	it('creates a domain with native form submission, then browses it without switching the session', async () => {
		mocks.post.mockImplementation(async () => { browse([home, team, createdDomain]); return createdDomain; });
		render(Page); const submit = await openCreateDomain(); expect(submit.type).toBe('submit'); submit.form!.requestSubmit(submit);
		await screen.findByRole('button', { name: /^Created project/ });
		expect(get(auth).domainId).toBe(home.id); expect(get(auth).isDomainManager).toBe(false); expect(mocks.goto).not.toHaveBeenCalled();
		expect(mocks.post).toHaveBeenCalledOnce();
	});
	it('does not offer domain creation without the verified policy capability', async () => {
		setAuth({ token: 'home-token', canCreateDomain: false, isSystemAdmin: true });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		render(Page); await screen.findByRole('button', { name: /^Home project/ });
		expect(screen.queryByRole('button', { name: t('newDomain') })).toBeNull();
	});
	it('does not replay an uncertain domain creation', async () => {
		mocks.post.mockRejectedValueOnce(new TypeError('network failed')); render(Page); const submit = await openCreateDomain(); submit.form!.requestSubmit(submit);
		await screen.findByText(t('createUncertain')); expect(submit.disabled).toBe(true); await fireEvent.click(submit); expect(mocks.post).toHaveBeenCalledOnce();
	});
	it('allows corrected input after definitive rejection', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(409, 'rejected')).mockImplementationOnce(async () => { browse([home, team, createdDomain]); return createdDomain; });
		render(Page); const submit = await openCreateDomain(); submit.form!.requestSubmit(submit); await screen.findByText(t('createRejected'));
		await waitFor(() => expect(submit.disabled).toBe(false)); submit.form!.requestSubmit(submit); await screen.findByRole('button', { name: /^Created project/ });
	});
	it('creates a project in the browsed domain and refreshes inventory without session mutation', async () => {
		mocks.post.mockResolvedValueOnce({ id: 'new-project', name: 'New project' }); render(Page); await chooseTeam();
		await fireEvent.click(screen.getByRole('button', { name: t('newProject') }));
		const input = await screen.findByRole('textbox', { name: t('projectName') });
		await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
		await fireEvent.input(input, { target: { value: 'New project' } });
		await fireEvent.click(screen.getByRole('button', { name: t('create') }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/projects', { name: 'New project', description: '', domain_id: team.id }, 'home-token', undefined, expect.objectContaining({ replayOnUnauthorized: false })));
		expect(get(auth).domainId).toBe(home.id); expect(mocks.goto).not.toHaveBeenCalled();
	});

	it('allows an unnamed personal project but requires an organization project name', async () => {
		const personal = { id: 'personal', name: 'Personal', kind: 'personal' as const };
		const organization = { ...team, kind: 'organization' as const };
		setLoginAuth(loginAuthState({ ...switchResponse, identity_domain_id: 'account-id', identity_domain_name: 'account', domain_id: personal.id,
			domain_name: personal.name, project_id: 'personal-project', project_name: 'Personal project', available_domains: [personal, organization] }, { federated: false }).state);
		mocks.get.mockImplementation(async path => path === '/api/v1/auth/domains' ? [personal, organization]
			: path.startsWith('/api/v1/projects/capabilities') ? { domain_id: path.includes('personal') ? personal.id : organization.id, domain_kind: path.includes('personal') ? 'personal' : 'organization', can_create_project: true }
			: workspace(path.includes('personal') ? personal : organization));
		mocks.post.mockResolvedValueOnce({ id: 'extra-project', name: 'alice-e9b278' });
		render(Page); await screen.findByRole('button', { name: /^Personal project/ });
		await fireEvent.click(screen.getByRole('button', { name: t('newProject') }));
		await screen.findByText(t('personalProjectNameHelp'));
		expect(screen.queryByRole('textbox', { name: t('projectName') })).toBeNull();
		await waitFor(() => expect((screen.getByRole('button', { name: t('create') }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: t('create') }));
		await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/projects', { domain_id: personal.id, description: '' }, 'team-token', undefined, expect.objectContaining({ replayOnUnauthorized: false })));
		await screen.findByRole('button', { name: /^Personal project/ });
		await fireEvent.change(screen.getByRole('combobox', { name: t('domain') }), { target: { value: organization.id } });
		await screen.findByRole('button', { name: /^Team project/ });
		await fireEvent.click(screen.getByRole('button', { name: t('newProject') }));
		const orgName = screen.getByRole('textbox', { name: t('projectName') }) as HTMLInputElement;
		await waitFor(() => expect(orgName.disabled).toBe(false));
		expect(orgName.required).toBe(true);
		expect((screen.getByRole('button', { name: t('create') }) as HTMLButtonElement).disabled).toBe(true);
		expect(mocks.post).toHaveBeenCalledOnce();
	});

	it.each(['domain', 'project'] as const)('blocks continuation and logout during an accepted %s create, then releases controls', async (kind) => {
		const pending = Promise.withResolvers<unknown>();
		mocks.post.mockReturnValueOnce(pending.promise);
		const invitation = 'i'.repeat(32); storePendingInvitation(invitation); storeMcpConsentTicket('m'.repeat(32));
		render(Page);
		if (kind === 'domain') {
			const submit = await openCreateDomain(); submit.form!.requestSubmit(submit);
		} else {
			await chooseTeam();
			await fireEvent.click(screen.getByRole('button', { name: t('newProject') }));
			const input = screen.getByRole('textbox', { name: t('projectName') }) as HTMLInputElement;
			await waitFor(() => expect(input.disabled).toBe(false));
			await fireEvent.input(input, { target: { value: 'New project' } });
			await fireEvent.click(screen.getByRole('button', { name: t('create') }));
		}
		await waitFor(() => expect(mocks.post).toHaveBeenCalledOnce());
		const signal = mocks.post.mock.calls[0][4].signal as AbortSignal;
		const proceed = screen.getByRole('button', { name: t('continue') }) as HTMLButtonElement;
		const logout = screen.getByRole('button', { name: tp('selectProject.logout') }) as HTMLButtonElement;
		const close = screen.getByRole('button', { name: t('close') }) as HTMLButtonElement;
		await waitFor(() => expect(proceed.disabled).toBe(true));
		expect(logout.disabled).toBe(true); expect(close.disabled).toBe(true);
		await fireEvent.click(proceed); await fireEvent.click(logout); await fireEvent.click(close);
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(mocks.goto).not.toHaveBeenCalled(); expect(mocks.close).not.toHaveBeenCalled();
		expect(get(logoutInProgress)).toBe(false); expect(get(auth).token).toBe('home-token');
		expect(signal.aborted).toBe(false); expect(mocks.post).toHaveBeenCalledOnce();
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
		if (kind === 'domain') { browse([home, team, createdDomain]); pending.resolve(createdDomain); }
		else pending.resolve({ id: 'new-project', name: 'New project' });
		await waitFor(() => expect(proceed.disabled).toBe(false));
		expect(logout.disabled).toBe(false);
		await fireEvent.click(proceed);
		expect(mocks.goto).toHaveBeenCalledWith(`/invitations/${invitation}`);
		expect(takePendingInvitationPath()).toBeNull(); expect(mocks.post).toHaveBeenCalledOnce();
	});
});
