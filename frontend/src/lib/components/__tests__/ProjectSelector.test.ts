import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type * as ClientModule from '$lib/api/client';
import ProjectSelector from '../ProjectSelector.svelte';
import CreateProjectModal from '../projects/CreateProjectModal.svelte';
import { api } from '$lib/api/client';
import { acceptAuthVerification, auth, authReady, clearAuth, getAuthVerificationEpoch, logoutInProgress, projectSwitching, setAuth, setLoginAuth } from '$lib/stores/auth';
import { cloudShell } from '$lib/stores/cloudShell.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/workspace-selector';
import { workspacePreferenceKey } from '$lib/stores/workspacePreferences';
import { refreshAuthState } from '$lib/utils/authSession';
import type { SessionTokenResponse } from '$lib/types/auth';
import type { WorkspaceInventory } from '$lib/stores/workspaceController.svelte';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', () => ({ page: { subscribe(run: (value: unknown) => void) { run({ data: { mockup: { active: false } } }); return () => {}; } } }));
vi.mock('$lib/api/client', async (importOriginal) => ({ ...(await importOriginal<typeof ClientModule>()), api: { get: vi.fn(), post: vi.fn() } }));

const home = { id: 'home', name: 'Same name' };
const team = { id: 'team', name: 'Same name' };
const first = { id: 'project-1', name: 'Project' };
const second = { id: 'project-2', name: 'Project' };
function inventory(domain = home) { return { domain, projects: [first, second], default_project_id: first.id, is_domain_manager: true, can_create_project: true }; }
function response(domain = home): SessionTokenResponse { return { token: 'new-token', refresh_token: 'new-refresh', user_id: 'alice', username: 'alice', domain_id: domain.id, domain_name: domain.name, identity_domain_id: home.id, identity_domain_name: home.name, available_domains: [home, team], project_id: second.id, project_name: second.name, expires_at: '2030-01-01T00:00:00Z' }; }
function projectButton(id: string) { return screen.getByRole('button', { name: new RegExp(`^Project.*${id}`) }); }
async function open() {
	await fireEvent.click(screen.getByRole('button', { name: /select a resource/ }));
	await screen.findByRole('button', { name: /^Project.*project-2/ });
}

beforeEach(() => {
	vi.clearAllMocks(); initLocale('en'); localStorage.clear(); clearAuth(); logoutInProgress.set(false); projectSwitching.set(false);
	setLoginAuth({ token: 'original-token', userId: 'alice', domainId: home.id, domainName: home.name, identityDomainId: home.id, identityDomainName: home.name, projectId: first.id, projectName: first.name, availableDomains: [home], canCreateDomain: true, federated: true });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
	vi.mocked(api.get).mockImplementation(async (path) => path === '/api/v1/auth/domains' ? [home, team]
		: path.startsWith('/api/v1/projects/capabilities') ? { domain_id: home.id, can_create_project: true }
		: inventory(path.includes('domain_id=team') ? team : home));
	vi.mocked(api.post).mockResolvedValue(response());
	vi.spyOn(cloudShell, 'close').mockResolvedValue();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); clearAuth(); logoutInProgress.set(false); projectSwitching.set(false); initLocale('ko'); });

describe('authorized workspace selector', () => {
	it('keeps immutable account-home identity out of the administrator user resource chooser', async () => {
		setAuth({ token: 'original-token', identityDomainId: 'private-accounts-home', identityDomainName: 'Private account identity', isSystemAdmin: true });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), { isSystemAdmin: true })).toBe(true);
		render(ProjectSelector); await open();
		const dialog = screen.getByRole('dialog', { name: t('title') });
		expect(dialog.textContent).not.toContain('private-accounts-home');
		expect(dialog.textContent).not.toContain('Private account identity');
		expect(within(dialog).getByRole('combobox', { name: t('domain') })).toBeTruthy();
		expect(within(dialog).getByRole('button', { name: /^Project.*project-2/ })).toBeTruthy();
	});

	it('selects a server-authorized target for a projectless zero-role administrator without a client membership check or project rescope', async () => {
		setAuth({ token: 'original-token', projectId: null, projectName: null, roles: [], availableProjects: [], isSystemAdmin: true });
		expect(acceptAuthVerification(getAuthVerificationEpoch(), { isSystemAdmin: true })).toBe(true);
		vi.mocked(api.post).mockResolvedValue({ ...response(), roles: [], is_system_admin: true });
		render(ProjectSelector); await open();
		await fireEvent.click(projectButton(second.id));
		await waitFor(() => expect(get(auth).projectId).toBe(second.id));
		expect(api.post).toHaveBeenCalledOnce();
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/token/workspace', { domain_id: home.id, project_id: second.id }, 'original-token', undefined, expect.objectContaining({ replayOnUnauthorized: false, cache: 'no-store' }));
		expect(get(auth)).toMatchObject({ userId: 'alice', projectId: second.id, roles: [], isSystemAdmin: true, availableProjects: [] });
	});

	it('can select another authorized workspace after refresh revokes the current project', async () => {
		const previous = get(auth);
		setAuth(refreshAuthState({ ...response(), token: 'projectless-token', project_id: '', project_name: '', roles: [] }, previous));
		expect(get(auth)).toMatchObject({ projectId: null, projectName: null, roles: [], userId: previous.userId,
			domainId: home.id, identityDomainId: home.id, sessionId: previous.sessionId, federated: true });
		expect(get(authReady)).toBe(true);
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		vi.mocked(api.get).mockImplementation(async path => path === '/api/v1/auth/domains' ? [home, team]
			: { ...inventory(), projects: [second] });
		render(ProjectSelector); await open();
		expect(screen.queryByText(first.id)).toBeNull();
		await fireEvent.click(projectButton(second.id));
		await waitFor(() => expect(get(auth).projectId).toBe(second.id));
		expect(api.post).toHaveBeenCalledOnce();
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/token/workspace', { domain_id: home.id, project_id: second.id },
			'projectless-token', undefined, expect.objectContaining({ replayOnUnauthorized: false, cache: 'no-store' }));
		expect(get(auth)).toMatchObject({ projectName: second.name, userId: previous.userId, domainId: home.id,
			identityDomainId: home.id, sessionId: previous.sessionId, federated: true });
	});
	it('does not expose cached project inventory before fresh authorization succeeds', async () => {
		localStorage.setItem('afterglow.projects.alice', JSON.stringify({ data: [second], ts: Date.now(), domainId: home.id }));
		vi.mocked(api.get).mockReturnValue(Promise.withResolvers<never>().promise);
		render(ProjectSelector);
		await fireEvent.click(screen.getByRole('button', { name: /select a resource/ }));
		expect(screen.queryByText(second.id)).toBeNull();
		expect((screen.getByRole('button', { name: t('newProject') }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.post).not.toHaveBeenCalled();
	});

	it('overlaps initial reads, coalesces footer refresh, and waits for both authorities before showing actions', async () => {
		const directory = Promise.withResolvers<(typeof home)[]>();
		const workspace = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : workspace.promise);
		render(ProjectSelector);
		await fireEvent.click(screen.getByRole('button', { name: /select a resource/ }));
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/domains', '/api/v1/auth/workspaces?domain_id=home']);
		workspace.resolve(inventory()); await workspace.promise;
		expect(screen.queryByText(second.id)).toBeNull();
		expect((screen.getByRole('button', { name: t('newProject') }) as HTMLButtonElement).disabled).toBe(true);
		directory.resolve([home, team]);
		await screen.findByRole('button', { name: /^Project.*project-2/ });
		expect((screen.getByRole('button', { name: t('newProject') }) as HTMLButtonElement).disabled).toBe(false);
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each(['failed', 'revoked'] as const)('keeps actions closed when workspace succeeds but refreshed directory is %s', async outcome => {
		render(ProjectSelector); await open();
		const directory = Promise.withResolvers<(typeof home)[]>();
		const workspace = Promise.withResolvers<WorkspaceInventory>();
		vi.mocked(api.get).mockImplementation(path => path === '/api/v1/auth/domains' ? directory.promise : workspace.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		workspace.resolve(inventory()); await workspace.promise;
		expect(screen.queryByText(second.id)).toBeNull();
		if (outcome === 'failed') { directory.reject(new Error('directory unavailable')); await screen.findByText(t('loadFailed')); }
		else { directory.resolve([]); await screen.findByText(t('empty')); }
		expect(screen.queryByText(second.id)).toBeNull();
		expect(screen.queryByRole('button', { name: t('useDomain') })).toBeNull();
		expect((screen.getByRole('button', { name: t('newProject') }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('combobox', { name: t('domain') }) as HTMLSelectElement).disabled).toBe(true);
		expect(api.post).not.toHaveBeenCalled();
	});

	it('browses by domain ID without a scope mutation, then atomically selects an exact project', async () => {
		const sessionId = get(auth).sessionId;
		vi.mocked(api.post).mockResolvedValue(response(team));
		render(ProjectSelector); await open();
		vi.mocked(api.get).mockClear();
		await fireEvent.change(screen.getByRole('combobox', { name: t('domain') }), { target: { value: team.id } });
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/auth/workspaces?domain_id=team', 'original-token', undefined, expect.objectContaining({ refresh: true, signal: expect.any(AbortSignal) })));
		await screen.findByRole('button', { name: /^Project.*project-2/ });
		expect(get(auth).domainId).toBe(home.id); expect(get(auth).projectId).toBe(first.id); expect(api.post).not.toHaveBeenCalled();
		expect(vi.mocked(api.get).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/workspaces?domain_id=team']);
		await fireEvent.click(projectButton(second.id));
		await waitFor(() => expect(get(auth).domainId).toBe(team.id));
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/token/workspace', { domain_id: team.id, project_id: second.id }, 'original-token', undefined, expect.objectContaining({ replayOnUnauthorized: false, cache: 'no-store' }));
		expect(api.post).toHaveBeenCalledOnce();
		expect(get(auth)).toMatchObject({ projectId: second.id, identityDomainId: home.id, sessionId, federated: true });
		expect(cloudShell.close).toHaveBeenCalledWith('project-switch', { keepDock: false });
		expect(vi.mocked(cloudShell.close).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.post).mock.invocationCallOrder[0]);
	});

	it.each(['logout', 'aba', 'unmount'] as const)('cancels publication and releases the switch lock after %s', async (kind) => {
		const previous = get(auth); const pending = Promise.withResolvers<SessionTokenResponse>();
		vi.mocked(api.post).mockReturnValue(pending.promise);
		const rendered = render(ProjectSelector); await open(); await fireEvent.click(projectButton(second.id));
		await waitFor(() => expect(get(projectSwitching)).toBe(true));
		if (kind === 'unmount') rendered.unmount();
		else if (kind === 'logout') { logoutInProgress.set(true); clearAuth(); }
		else { setAuth({ token: 'other', domainId: team.id }); setAuth({ ...previous, token: previous.token! }); }
		pending.resolve(response());
		await waitFor(() => expect(get(projectSwitching)).toBe(false));
		expect(get(auth).projectId).toBe(kind === 'logout' ? null : first.id);
	});

	it('permits same-session access-token rotation while a switch is pending', async () => {
		const sessionId = get(auth).sessionId;
		const pending = Promise.withResolvers<SessionTokenResponse>(); vi.mocked(api.post).mockReturnValue(pending.promise);
		render(ProjectSelector); await open(); await fireEvent.click(projectButton(second.id));
		await waitFor(() => expect(get(projectSwitching)).toBe(true));
		const refreshed: SessionTokenResponse = {
			...response(), token: 'refreshed-token', refresh_token: 'refreshed-refresh',
			project_id: first.id, project_name: first.name, available_domains: [home], can_create_domain: true,
		};
		setAuth(refreshAuthState(refreshed, get(auth)));
		expect(get(auth)).toMatchObject({ token: refreshed.token, projectId: first.id, domainId: home.id, identityDomainId: home.id, sessionId, federated: true });
		expect(get(authReady)).toBe(true);
		pending.resolve(response()); await waitFor(() => expect(get(auth).projectId).toBe(second.id));
		expect(get(auth)).toMatchObject({ token: 'new-token', domainId: home.id, identityDomainId: home.id, sessionId, federated: true });
	});

	it('recovers hidden UUID preferences only from authorized inventory and disables actions after refresh failure', async () => {
		localStorage.setItem(workspacePreferenceKey(home.id, 'alice'), JSON.stringify({ domains: {}, projects: { [second.id]: { hidden: true, pinned: true }, foreign: { pinned: true } } }));
		render(ProjectSelector);
		await fireEvent.click(screen.getByRole('button', { name: /select a resource/ }));
		await screen.findByRole('button', { name: /^Project.*project-1/ });
		expect(screen.queryByText(second.id)).toBeNull(); expect(screen.queryByText('foreign')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('displaySettings') }));
		await fireEvent.click(screen.getByRole('button', { name: t('showResource', { name: second.name, id: second.id }) }));
		await fireEvent.click(screen.getByRole('button', { name: t('displaySettings') }));
		expect(projectButton(second.id)).toBeTruthy();
		vi.mocked(api.get).mockRejectedValue(new Error('unavailable'));
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') })); await screen.findByText(t('loadFailed'));
		expect(screen.queryByText(second.id)).toBeNull(); expect((screen.getByRole('button', { name: t('newProject') }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('reopens a recent resource list without a loading gap and refreshes it explicitly', async () => {
		render(ProjectSelector); await open();
		await fireEvent.click(screen.getByRole('button', { name: t('close') }));
		await waitFor(() => expect(screen.queryByRole('dialog', { name: t('title') })).toBeNull());
		vi.mocked(api.get).mockClear().mockImplementation(async path => path === '/api/v1/auth/domains' ? [home] : { ...inventory(), projects: [first] });
		await open();
		expect(projectButton(second.id)).toBeTruthy();
		expect(api.get).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await waitFor(() => expect(screen.queryByText(second.id)).toBeNull());
		expect(projectButton(first.id)).toBeTruthy();
	});

	it('keeps keyboard focus in the bounded dialog and restores the trigger on close', async () => {
		render(ProjectSelector); const trigger = screen.getByRole('button', { name: /select a resource/ }); trigger.focus(); await open();
		const dialog = screen.getByRole('dialog', { name: t('title') });
		projectButton(second.id).focus(); await fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
		expect(dialog.contains(document.activeElement)).toBe(true);
		await fireEvent.click(within(dialog).getByRole('button', { name: t('close') }));
		await waitFor(() => expect(document.activeElement).toBe(trigger));
	});

	it.each(['escape', 'backdrop', 'navigation'] as const)('keeps an accepted domain create mounted during %s and fences uncertain replay until fresh inventory', async (action) => {
		const pending = Promise.withResolvers<unknown>();
		vi.mocked(api.post).mockReturnValueOnce(pending.promise);
		render(ProjectSelector); await open();
		const dialog = screen.getByRole('dialog', { name: t('title') });
		await fireEvent.click(screen.getByRole('button', { name: t('newDomain') }));
		await fireEvent.input(screen.getByRole('textbox', { name: t('domainName') }), { target: { value: 'New domain' } });
		const submit = screen.getByRole('button', { name: t('create') }) as HTMLButtonElement;
		submit.form!.requestSubmit(submit);
		await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/auth/domains', { name: 'New domain' }, 'original-token', undefined, expect.objectContaining({ replayOnUnauthorized: false, cache: 'no-store', signal: expect.any(AbortSignal) })));
		const signal = vi.mocked(api.post).mock.calls[0][4]!.signal!;
		const backdrop = dialog.firstElementChild as HTMLButtonElement;
		const settings = screen.getByText(t('projectSettings')).closest('a')!;
		await waitFor(() => expect(backdrop.disabled).toBe(true));
		expect(settings.getAttribute('href')).toBeNull();
		if (action === 'escape') await fireEvent.keyDown(document, { key: 'Escape' });
		else if (action === 'backdrop') await fireEvent.click(backdrop);
		else expect(await fireEvent.click(settings)).toBe(false);
		(screen.getByRole('button', { name: t('close') }) as HTMLButtonElement).click();
		(screen.getByRole('button', { name: t('cancel') }) as HTMLButtonElement).click();
		expect(screen.getByRole('dialog', { name: t('title') })).toBe(dialog);
		expect(signal.aborted).toBe(false);
		expect(api.post).toHaveBeenCalledOnce();

		pending.reject(new TypeError('response lost after native acceptance'));
		await screen.findByText(t('createUncertain'));
		expect(submit.disabled).toBe(true);
		await fireEvent.submit(submit.form!);
		expect(api.post).toHaveBeenCalledOnce();
		vi.mocked(api.get).mockRejectedValueOnce(new Error('inventory unavailable'));
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await screen.findByText(t('loadFailed'));
		expect(submit.disabled).toBe(true);
		await fireEvent.submit(submit.form!);
		expect(api.post).toHaveBeenCalledOnce();
		const freshInventory = Promise.withResolvers<unknown>();
		vi.mocked(api.get).mockImplementation(async path => path === '/api/v1/auth/domains' ? [home, team] : freshInventory.promise);
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/auth/workspaces?domain_id=home', 'original-token', undefined, expect.objectContaining({ refresh: true })));
		expect(submit.disabled).toBe(true);
		freshInventory.resolve(inventory());
		await waitFor(() => expect(submit.disabled).toBe(false));
		expect(api.post).toHaveBeenCalledOnce();
		expect(get(auth).projectId).toBe(first.id);
	});

	it('locks both modal layers during nested project creation and refreshes before another create', async () => {
		const pending = Promise.withResolvers<{ id: string; name: string }>();
		vi.mocked(api.post).mockReturnValueOnce(pending.promise);
		render(ProjectSelector); await open();
		const outer = screen.getByRole('dialog', { name: t('title') });
		await fireEvent.click(screen.getByRole('button', { name: t('newProject') }));
		const inner = screen.getByRole('dialog', { name: t('newProject') });
		const input = within(inner).getByRole('textbox', { name: t('projectName') }) as HTMLInputElement;
		await waitFor(() => expect(input.disabled).toBe(false));
		await fireEvent.input(input, { target: { value: 'New project' } });
		await fireEvent.click(within(inner).getByRole('button', { name: t('create') }));
		await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/projects', { name: 'New project', description: '', domain_id: home.id }, 'original-token', undefined, expect.objectContaining({ replayOnUnauthorized: false })));
		const signal = vi.mocked(api.post).mock.calls[0][4]!.signal!;
		expect((outer.firstElementChild as HTMLButtonElement).disabled).toBe(true);
		expect((inner.firstElementChild as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.keyDown(document, { key: 'Escape' });
		await fireEvent.click(inner.firstElementChild!);
		await fireEvent.click(outer.firstElementChild!);
		(within(inner).getByRole('button', { name: t('cancel') }) as HTMLButtonElement).click();
		expect(inner.isConnected).toBe(true); expect(outer.isConnected).toBe(true);
		expect(signal.aborted).toBe(false); expect(api.post).toHaveBeenCalledOnce();
		pending.reject(new TypeError('response lost'));
		await screen.findByText(t('createUncertain'));
		await fireEvent.submit(within(inner).getByRole('button', { name: t('create') }).closest('form')!);
		expect(api.post).toHaveBeenCalledOnce();
		const fresh = Promise.withResolvers<unknown>();
		vi.mocked(api.get).mockImplementation(async path => path === '/api/v1/auth/domains' ? [home, team] : fresh.promise);
		await fireEvent.click(within(inner).getByRole('button', { name: t('cancel') }));
		await waitFor(() => expect(inner.isConnected).toBe(false));
		const create = screen.getByRole('button', { name: t('newProject') }) as HTMLButtonElement;
		expect(create.disabled).toBe(true);
		fresh.resolve(inventory());
		await waitFor(() => expect(create.disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: t('close') }));
		await waitFor(() => expect(outer.isConnected).toBe(false));
	});

	it('recognizes a definitive native-create rejection without replaying it', async () => {
		vi.mocked(api.post).mockRejectedValueOnce(new ApiError(409, 'name conflict'));
		render(ProjectSelector); await open();
		await fireEvent.click(screen.getByRole('button', { name: t('newDomain') }));
		await fireEvent.input(screen.getByRole('textbox', { name: t('domainName') }), { target: { value: 'Conflicting name' } });
		const submit = screen.getByRole('button', { name: t('create') }) as HTMLButtonElement;
		await fireEvent.click(submit);
		await screen.findByText(t('createRejected'));
		expect(submit.disabled).toBe(false); expect(api.post).toHaveBeenCalledOnce();
	});

	it.each(['login', 'aba', 'unmount'] as const)('does not publish a late nested project create after %s', async (kind) => {
		const pending = Promise.withResolvers<{ id: string; name: string }>();
		vi.mocked(api.post).mockReturnValueOnce(pending.promise);
		const onSuccess = vi.fn(); const onClose = vi.fn();
		const rendered = render(CreateProjectModal, { domainId: home.id, domainName: home.name, onClose, onSuccess });
		const input = screen.getByRole('textbox', { name: t('projectName') }) as HTMLInputElement;
		await waitFor(() => expect(input.disabled).toBe(false));
		await fireEvent.input(input, { target: { value: 'Late project' } });
		await fireEvent.click(screen.getByRole('button', { name: t('create') }));
		await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
		const signal = vi.mocked(api.post).mock.calls[0][4]!.signal!;
		const previous = get(auth);
		if (kind === 'unmount') rendered.unmount();
		else if (kind === 'login') {
			setLoginAuth({ ...previous, token: 'bob-token', userId: 'bob' });
			expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		}
		else { setAuth({ token: 'other', domainId: team.id }); setAuth({ ...previous, token: previous.token! }); }
		expect(signal.aborted).toBe(true);
		pending.resolve({ id: 'late-project', name: 'Late project' });
		await pending.promise;
		expect(onSuccess).not.toHaveBeenCalled(); expect(api.post).toHaveBeenCalledOnce();
		expect(get(auth).projectId).toBe(first.id);
		if (kind !== 'unmount') expect(onClose).toHaveBeenCalled();
	});
});
