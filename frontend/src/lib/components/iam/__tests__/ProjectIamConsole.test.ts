import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'actor', domainId: 'domain-a', projectId: 'project-a', domainName: 'Domain A', isDomainManager: false, isSystemAdmin: false }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false)
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
import { auth, authReady } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/domain-iam';
import { t as workspaceT } from '$lib/i18n/ns/workspace-selector';
import ProjectIamConsole from '../ProjectIamConsole.svelte';
import DomainIamConsole from '../DomainIamConsole.svelte';
import { projectManagement } from '$lib/stores/projectManagement';

const project = { id: 'project-a', name: 'Project A', domain_id: 'domain-a', description: '', enabled: true };
const user = { id: 'user-a', name: 'Alice', email: 'alice@example.com', enabled: true, domain_id: 'domain-a', protected: false };
const member = { user_id: user.id, username: user.name, email: user.email, is_owner: false, is_manager: false, roles: ['project_reader'], direct_role_ids: ['reader'], effective_role_ids: ['reader'], external_role_ids: [], source: 'direct' };
const capability = { domain_id: 'domain-a', domain_kind: 'organization', is_domain_manager: false, can_create_project: true };
let caps = { ...capability };
let projects = [project];
function fixture(path: string): unknown {
	if (path.includes('/projects/capabilities?')) return caps;
	if (path.includes('/projects?domain_id=') || path === '/api/v1/iam/projects') return { items: projects };
	if (path.includes('/projects/creators?')) return { domain_id: 'domain-a', role: null, users: [] };
	if (path === '/api/v1/iam/users') return { items: [user] };
	if (path.endsWith('/members')) return { items: [member] };
	if (path.endsWith('/assignable-roles')) return { roles: [], is_owner: false, can_manage_owners: false };
	if (path.endsWith('/eligible-users')) return [user];
	if (path.endsWith('/ownership')) return { project_id: path.split('/').at(-2), owner_user_id: 'actor', status: 'unique', owners: [], can_transfer: false, can_delete: false, transfer_operation: null };
	throw new Error(`Unexpected request: ${path}`);
}
beforeEach(() => {
	vi.resetAllMocks(); caps = { ...capability }; projects = [project];
	auth.set({ token: 'token', sessionId: 'session-a', userId: 'actor', domainId: 'domain-a', projectId: project.id, domainName: 'Domain A', isDomainManager: false, isSystemAdmin: false } as never);
	authReady.set(true);
	api.get.mockImplementation(async path => fixture(path));
});
afterEach(cleanup);

describe('separate organization IAM surfaces', () => {
	it('uses fresh project capabilities and generic current-project APIs without user directory or delegation reads for creator-only users', async () => {
		render(ProjectIamConsole);
		await screen.findByText('Alice');
		expect(screen.getByRole('heading', { name: t('projectsTitle') })).toBeTruthy();
		expect(screen.getByRole('button', { name: workspaceT('newProject') })).toBeTruthy();
		expect(screen.queryByText(t('projectCreators'))).toBeNull();
		expect(screen.queryByRole('button', { name: t('invitations') })).toBeNull();
		expect(api.get.mock.calls.some(([path]) => path.startsWith('/api/v1/iam/') || path.includes('/creators'))).toBe(false);
		expect(api.get.mock.calls.some(([path]) => path === '/api/v1/projects/project-a/members')).toBe(true);
		expect(api.get).toHaveBeenCalledWith('/api/v1/projects/capabilities?domain_id=domain-a', 'token', undefined, { cache: 'no-store', suppressAuthRedirect: true });
	});
	it('revalidates on entry before mounting consumers when navigation retains an old manager capability', async () => {
		caps = { ...caps, is_domain_manager: true };
		auth.update(state => ({ ...state, isDomainManager: true }));
		let managerVerified = false;
		const keepNavigationMounted = projectManagement.subscribe(state => { managerVerified = !state.checking && state.capability?.is_domain_manager === true; });
		let unmount: (() => void) | undefined;
		try {
			await waitFor(() => expect(managerVerified).toBe(true));
			caps = { ...caps, is_domain_manager: false };
			const entry = Promise.withResolvers<unknown>();
			api.get.mockClear();
			api.get.mockImplementation(path => path.includes('/capabilities?') ? entry.promise : Promise.resolve(fixture(path)));
			unmount = render(ProjectIamConsole).unmount;
			await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
			expect(screen.queryByText('Alice')).toBeNull();
			expect(api.get.mock.calls.some(([path]) => path.startsWith('/api/v1/iam/') || path.includes('/creators'))).toBe(false);
			entry.resolve(caps);
			await screen.findByText('Alice');
			expect(api.get.mock.calls.some(([path]) => path === '/api/v1/projects/project-a/members')).toBe(true);
			expect(api.get.mock.calls.some(([path]) => path.startsWith('/api/v1/iam/') || path.includes('/creators'))).toBe(false);
			expect(screen.queryByText(t('projectCreators'))).toBeNull();
		} finally { unmount?.(); keepNavigationMounted(); }
	});
	it('does not query or show the user console to a creator-only identity', async () => {
		render(DomainIamConsole);
		await screen.findByText(t('denied'));
		expect(api.get).not.toHaveBeenCalled();
	});
	it('allows fresh managers to retain IAM project APIs and creator delegation without login or recovery queries', async () => {
		caps = { ...caps, is_domain_manager: true };
		render(ProjectIamConsole);
		await screen.findByText(t('projectCreators'));
		await screen.findByText('Alice');
		expect(api.get.mock.calls.some(([path]) => path === '/api/v1/iam/projects')).toBe(true);
		expect(api.get.mock.calls.some(([path]) => path.includes('/projects/creators?'))).toBe(true);
		expect(api.get.mock.calls.some(([path]) => /login-policy|providers|operations|invitations/.test(path))).toBe(false);
	});
	it.each(['personal', 'denied', 'foreign', 'system-only'])('rejects %s capabilities without querying project or user inventories', async kind => {
		if (kind === 'personal') caps = { ...caps, domain_kind: 'personal' };
		if (kind === 'denied' || kind === 'system-only') caps = { ...caps, can_create_project: false };
		if (kind === 'foreign') caps = { ...caps, domain_id: 'foreign' };
		if (kind === 'system-only') auth.update(state => ({ ...state, isSystemAdmin: true }));
		render(ProjectIamConsole);
		await screen.findByText(t(kind === 'foreign' ? 'loadFailed' : 'projectsDenied'));
		expect(api.get).toHaveBeenCalledTimes(2);
	});
	it('requires an explicit workspace switch before reading another authorized project', async () => {
		projects = [project, { ...project, id: 'other', name: 'Other project' }];
		render(ProjectIamConsole); await screen.findByText('Alice');
		await fireEvent.change(screen.getByLabelText(t('project')), { target: { value: 'other' } });
		await screen.findByText(t('switchProjectHelp'));
		expect(screen.getByRole('button', { name: /리소스 선택/ }).getAttribute('aria-haspopup')).toBe('dialog');
		expect(api.get.mock.calls.some(([path]) => path.startsWith('/api/v1/projects/other/'))).toBe(false);
		expect(screen.queryByText('Alice')).toBeNull();
	});
	it('selects the created UUID but does not change the current session or read noncurrent project details', async () => {
		api.post.mockImplementation(async () => { const row = { ...project, id: 'new-project', name: 'Created project' }; projects.push(row); return row; });
		render(ProjectIamConsole); await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: workspaceT('newProject') }));
		const input = screen.getByRole('textbox', { name: workspaceT('projectName') });
		await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false));
		await fireEvent.input(input, { target: { value: 'Created project' } });
		await fireEvent.click(screen.getByRole('button', { name: workspaceT('create') }));
		await waitFor(() => expect((screen.getByLabelText(t('project')) as HTMLSelectElement).value).toBe('new-project'));
		expect(api.get.mock.calls.some(([path]) => path.startsWith('/api/v1/projects/new-project/'))).toBe(false);
		expect(api.post).toHaveBeenCalledTimes(1);
		expect(screen.getByText(t('switchProjectHelp'))).toBeTruthy();
	});
	it('preserves the creation draft but blocks submission during a focus check, then clears it on server revocation', async () => {
		render(ProjectIamConsole); await screen.findByText('Alice');
		await fireEvent.click(screen.getByRole('button', { name: workspaceT('newProject') }));
		const input = screen.getByRole('textbox', { name: workspaceT('projectName') }) as HTMLInputElement;
		await waitFor(() => expect(input.disabled).toBe(false));
		await fireEvent.input(input, { target: { value: 'Private draft' } });
		const pending = Promise.withResolvers<unknown>();
		api.get.mockImplementation(path => path.includes('/capabilities?') ? pending.promise : Promise.resolve(fixture(path)));
		await fireEvent.focus(window);
		expect(input.value).toBe('Private draft');
		expect((screen.getByRole('button', { name: workspaceT('create') }) as HTMLButtonElement).disabled).toBe(true);
		pending.resolve({ ...caps, can_create_project: false });
		await screen.findByText(t('projectsDenied'));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByText('Alice')).toBeNull();
		expect(api.post).not.toHaveBeenCalled();
	});
	it('fences A to B to A capability results and removes drafts immediately on logout', async () => {
		const old = Promise.withResolvers<unknown>(); let initial = true;
		api.get.mockImplementation(async path => {
			if (path.includes('/capabilities?') && initial) return old.promise;
			return fixture(path);
		});
		render(ProjectIamConsole);
		await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
		initial = false;
		auth.update(state => ({ ...state, domainId: 'domain-b' }));
		auth.update(state => ({ ...state, domainId: 'domain-a' }));
		old.resolve({ ...caps, can_create_project: false });
		await screen.findByText('Alice');
		await waitFor(() => expect(screen.getByText('Alice')).toBeTruthy());
		await fireEvent.click(screen.getByRole('button', { name: workspaceT('newProject') }));
		authReady.set(false);
		await screen.findByText(t('projectsDenied'));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByText('Alice')).toBeNull();
	});
});
