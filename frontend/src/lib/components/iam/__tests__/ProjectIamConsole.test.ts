import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), withExperience() { return this; } } }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'actor', domainId: 'domain-a', projectId: 'project-a', domainName: 'Domain A', isDomainManager: true, isSystemAdmin: false }),
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
const manager = { domain_id: 'domain-a', domain_kind: 'organization', is_domain_manager: true, can_create_project: true };
let caps = { ...manager };
let projects = [project];
function fixture(path: string): unknown {
	if (path.includes('/projects/capabilities?')) return caps;
	if (path === '/api/v1/iam/projects') return { items: projects };
	throw new Error(`Unexpected request: ${path}`);
}
beforeEach(() => {
	vi.resetAllMocks(); caps = { ...manager }; projects = [project];
	auth.set({ token: 'token', sessionId: 'session-a', userId: 'actor', domainId: 'domain-a', projectId: project.id, domainName: 'Domain A', isDomainManager: true, isSystemAdmin: false } as never);
	authReady.set(true);
	api.get.mockImplementation(async path => fixture(path));
});
afterEach(cleanup);

describe('domain manager IAM surfaces', () => {
	it('shows the project table to a fresh manager without domain identifiers, creator delegation or login queries', async () => {
		render(ProjectIamConsole);
		await screen.findByText('Project A');
		expect(screen.getByRole('heading', { name: t('projectsTitle') })).toBeTruthy();
		expect(screen.getByRole('button', { name: workspaceT('newProject') })).toBeTruthy();
		expect(screen.queryByText(/domain-a/)).toBeNull();
		expect(screen.queryByText(/project_creator/)).toBeNull();
		expect(api.get.mock.calls.some(([path]) => path === '/api/v1/iam/projects')).toBe(true);
		expect(api.get.mock.calls.some(([path]) => /creators|login-policy|providers|operations|invitations|users/.test(path))).toBe(false);
		expect(api.get).toHaveBeenCalledWith('/api/v1/projects/capabilities?domain_id=domain-a', 'token', undefined, { cache: 'no-store', suppressAuthRedirect: true });
	});
	it('revalidates on entry before mounting the table when navigation retains an old manager capability', async () => {
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
			expect(screen.queryByText('Project A')).toBeNull();
			entry.resolve(caps);
			await screen.findByText(t('projectsDenied'));
			expect(api.get.mock.calls.some(([path]) => path.startsWith('/api/v1/iam/'))).toBe(false);
		} finally { unmount?.(); keepNavigationMounted(); }
	});
	it('does not query or show the user console to a non-manager identity', async () => {
		caps = { ...caps, is_domain_manager: false };
		auth.update(state => ({ ...state, isDomainManager: false }));
		render(DomainIamConsole);
		await screen.findByText(t('denied'));
		expect(api.get).not.toHaveBeenCalled();
	});
	it('does not show the domain identity card or identity-domain column on the user console', async () => {
		api.get.mockImplementation(async path => {
			if (path === '/api/v1/iam/context') return { domain_id: 'domain-a', domain_name: 'Domain A', is_domain_manager: true, is_system_admin: false };
			if (path === '/api/v1/iam/users') return { items: [{ id: 'user-a', name: 'Alice', email: 'alice@example.com', enabled: true, domain_id: 'home-x', protected: false }] };
			return fixture(path);
		});
		render(DomainIamConsole);
		await screen.findByText('Alice');
		expect(screen.queryByText(/home-x/)).toBeNull();
		expect(screen.queryByText(/domain-a/)).toBeNull();
		expect(screen.queryByText(t('identityDomain'))).toBeNull();
	});
	it.each(['personal', 'creator-only', 'foreign', 'system-only'])('rejects %s capabilities without querying the project inventory', async kind => {
		if (kind === 'personal') caps = { ...caps, domain_kind: 'personal' };
		if (kind === 'creator-only' || kind === 'system-only') caps = { ...caps, is_domain_manager: false, can_create_project: kind === 'creator-only' };
		if (kind === 'foreign') caps = { ...caps, domain_id: 'foreign' };
		if (kind === 'system-only') auth.update(state => ({ ...state, isSystemAdmin: true }));
		render(ProjectIamConsole);
		await screen.findByText(t(kind === 'foreign' ? 'loadFailed' : 'projectsDenied'));
		expect(api.get.mock.calls.some(([path]) => path === '/api/v1/iam/projects')).toBe(false);
	});
	it('preserves the creation draft but blocks submission during a focus check, then clears it on server revocation', async () => {
		render(ProjectIamConsole); await screen.findByText('Project A');
		await fireEvent.click(screen.getByRole('button', { name: workspaceT('newProject') }));
		const input = screen.getByRole('textbox', { name: workspaceT('projectName') }) as HTMLInputElement;
		await waitFor(() => expect(input.disabled).toBe(false));
		await fireEvent.input(input, { target: { value: 'Private draft' } });
		const pending = Promise.withResolvers<unknown>();
		api.get.mockImplementation(path => path.includes('/capabilities?') ? pending.promise : Promise.resolve(fixture(path)));
		await fireEvent.focus(window);
		expect(input.value).toBe('Private draft');
		expect((screen.getByRole('button', { name: workspaceT('create') }) as HTMLButtonElement).disabled).toBe(true);
		pending.resolve({ ...caps, is_domain_manager: false });
		await screen.findByText(t('projectsDenied'));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByText('Project A')).toBeNull();
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
		old.resolve({ ...caps, is_domain_manager: false });
		await screen.findByText('Project A');
		await fireEvent.click(screen.getByRole('button', { name: workspaceT('newProject') }));
		authReady.set(false);
		await screen.findByText(t('projectsDenied'));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByText('Project A')).toBeNull();
	});
});
