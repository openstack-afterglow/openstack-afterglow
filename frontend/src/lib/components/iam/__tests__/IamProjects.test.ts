import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'actor', domainId: 'domain-a', domainName: 'Domain A', isDomainManager: true, isSystemAdmin: false }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false)
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
import { auth, authReady } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';
import { t as workspaceT } from '$lib/i18n/ns/workspace-selector';
import type { ProjectAccessMember } from '$lib/types/project';
import IamProjects from '../IamProjects.svelte';

const project = { id: 'project-a', name: 'Project A', enabled: true, domain_id: 'domain-a' };
const created = { ...project, id: 'project-new', name: 'New project' };
const user = { id: 'user-a', name: 'Alice', email: 'alice@example.com', enabled: true, domain_id: 'domain-a', protected: false };
const joined = { ...user, id: 'user-b', name: 'Bob' };
const member: ProjectAccessMember = { user_id: user.id, username: user.name, email: user.email, is_owner: false, is_manager: false, roles: ['project_reader'], direct_role_ids: ['reader-role'], effective_role_ids: ['reader-role'], external_role_ids: [], source: 'direct' };
const catalog = { is_owner: false, can_manage_owners: false, roles: [
	{ id: 'reader-role', name: 'project_reader', area: 'project', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'member-role', name: 'project_member', area: 'project', grade: 'member', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'native-admin', name: 'admin', area: 'legacy', grade: 'admin', implied_role_ids: [], inherited_role_ids: [] }
] };
let current = true;
let allowed = true;
let rows = [project];
let members = [member];
const session = { token: () => 'token', userId: 'actor', domainId: 'domain-a', isCurrent: () => current, canSubmit: () => current && allowed };
function fixture(path: string) {
	if (path.includes('/projects/capabilities?')) return { domain_id: 'domain-a', can_create_project: true };
	if (path.includes('/projects/creators?')) return { domain_id: 'domain-a', role: null, users: [] };
	if (path.endsWith('/users')) return { items: [user, joined] };
	if (path.endsWith('/eligible-users')) return [user, joined];
	if (path.endsWith('/ownership')) return { project_id: path.split('/').at(-2), owner_user_id: 'actor', status: 'unique', owners: [{ user_id: 'actor', name: 'Owner', source: 'direct' }], can_transfer: false, can_delete: false, transfer_operation: null };
	if (path.endsWith('/projects') || path.includes('/projects?domain_id=')) return { items: rows };
	if (path.endsWith('/assignable-roles')) return catalog;
	if (path.endsWith('/members')) return { items: members };
	throw new Error(`Unexpected path: ${path}`);
}
afterEach(cleanup);
beforeEach(() => {
	vi.resetAllMocks(); current = true; allowed = true; rows = [project]; members = [member];
	auth.set({ token: 'token', userId: 'actor', domainId: 'domain-a', domainName: 'Domain A', isDomainManager: true, isSystemAdmin: false } as never);
	authReady.set(true);
	api.get.mockImplementation((path: string) => Promise.resolve(fixture(path)));
});
async function openCreate() {
	await fireEvent.click(screen.getByRole('button', { name: workspaceT('newProject') }));
	const input = screen.getByRole('textbox', { name: workspaceT('projectName') }) as HTMLInputElement;
	await waitFor(() => expect(input.disabled).toBe(false));
	await fireEvent.input(input, { target: { value: created.name } });
	return screen.getByRole('button', { name: workspaceT('create') }) as HTMLButtonElement;
}

describe('manager project creation and access', () => {
	it('creates in the verified IAM domain without a creator preset and refreshes/selects the real result', async () => {
		api.post.mockImplementation(async () => { rows = [project, created]; return created; });
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText(/project_creator 기본 역할이 없습니다/);
		await fireEvent.click(await openCreate());
		await waitFor(() => expect((screen.getByLabelText('프로젝트') as HTMLSelectElement).value).toBe(created.id));
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/projects', { name: created.name, description: '', domain_id: 'domain-a' }, 'token', undefined, { replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' });
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/iam/projects')).toHaveLength(2);
		expect(api.get.mock.calls.some(([path]) => path === '/api/v1/iam/projects/project-new/members')).toBe(true);
		expect(screen.queryByRole('dialog')).toBeNull();
	});
	it('keeps an unknown native create outcome non-replayable and never refreshes as success', async () => {
		api.post.mockRejectedValue(new TypeError('response lost'));
		render(IamProjects, { session, onDenied: vi.fn() });
		const submit = await openCreate(); await fireEvent.click(submit);
		await screen.findByText(workspaceT('createUncertain'));
		expect(submit.disabled).toBe(true);
		await fireEvent.submit(submit.form!);
		expect(api.post).toHaveBeenCalledOnce();
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/iam/projects')).toHaveLength(1);
	});
	it('reports a native rejection without pretending that a project was created', async () => {
		api.post.mockRejectedValue(new ApiError(403, 'Native denied'));
		render(IamProjects, { session, onDenied: vi.fn() });
		await fireEvent.click(await openCreate());
		await screen.findByText(workspaceT('createRejected'));
		expect(screen.queryByRole('option', { name: created.name })).toBeNull();
	});
	it('fences a stale IAM session immediately before creation even when the modal capability is allowed', async () => {
		render(IamProjects, { session, onDenied: vi.fn() });
		const submit = await openCreate(); current = false;
		await fireEvent.click(submit);
		expect(api.post).not.toHaveBeenCalled();
	});
	it('preserves the creation draft but disables submit while manager authority is being rechecked', async () => {
		const view = render(IamProjects, { session, onDenied: vi.fn() });
		const submit = await openCreate();
		await view.rerender({ session, blocked: true, onDenied: vi.fn() });
		expect(submit.disabled).toBe(true);
		expect((screen.getByRole('textbox', { name: workspaceT('projectName') }) as HTMLInputElement).value).toBe(created.name);
		await fireEvent.submit(submit.form!);
		expect(api.post).not.toHaveBeenCalled();
	});
	it('adds safe direct roles to a joined user without offering a new native admin grant', async () => {
		api.put.mockResolvedValue({});
		render(IamProjects, { session, onDenied: vi.fn() }); await screen.findByText('Alice');
		await fireEvent.change(screen.getByLabelText('사용자'), { target: { value: joined.id } });
		await fireEvent.click(screen.getByRole('button', { name: '사용자 역할 할당' }));
		const dialog = screen.getByRole('dialog');
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: /project_member/ }));
		await fireEvent.click(within(dialog).getByRole('button', { name: /^legacy/ }));
		expect((within(dialog).getByRole('checkbox', { name: /^admin/ }) as HTMLInputElement).disabled).toBe(true);
		await fireEvent.click(within(dialog).getByRole('button', { name: '역할 저장' }));
		expect(api.put).toHaveBeenCalledExactlyOnceWith('/api/v1/iam/projects/project-a/members/user-b/roles', { role_ids: ['member-role'] }, 'token', undefined, { replayOnUnauthorized: false });
	});
	it.each(['group', 'inherited'] as const)('never exposes %s authority as a directly removable member', async source => {
		members = [{ ...member, source, direct_role_ids: [], external_role_ids: ['reader-role'] }];
		render(IamProjects, { session, onDenied: vi.fn() }); await screen.findByText('Alice');
		expect((screen.getByRole('button', { name: '역할 편집' }) as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('button', { name: '멤버 제거' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.delete).not.toHaveBeenCalled();
	});
	it('adds a direct grant beside group access without editing or removing the inherited role', async () => {
		members = [{ ...member, source: 'group', direct_role_ids: [], external_role_ids: ['reader-role'] }];
		api.put.mockResolvedValue({});
		render(IamProjects, { session, onDenied: vi.fn() }); await screen.findByText('Alice');
		await fireEvent.change(screen.getByLabelText('사용자'), { target: { value: user.id } });
		await fireEvent.click(screen.getByRole('button', { name: '사용자 역할 할당' }));
		const dialog = screen.getByRole('dialog');
		const inherited = within(dialog).getByRole('checkbox', { name: /project_reader/ }) as HTMLInputElement;
		expect(inherited.checked).toBe(true); expect(inherited.disabled).toBe(true);
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: /project_member/ }));
		await fireEvent.click(within(dialog).getByRole('button', { name: '역할 저장' }));
		expect(api.put).toHaveBeenCalledExactlyOnceWith('/api/v1/iam/projects/project-a/members/user-a/roles', { role_ids: ['member-role'] }, 'token', undefined, { replayOnUnauthorized: false });
		expect(api.delete).not.toHaveBeenCalled();
	});
	it('uses only generic current-project membership and ownership APIs for a creator-only project owner', async () => {
		auth.update(state => ({ ...state, projectId: project.id, isDomainManager: false }));
		api.put.mockResolvedValue({});
		render(IamProjects, { session, domainManager: false, onDenied: vi.fn() });
		await screen.findByText('Alice');
		expect(api.get.mock.calls.some(([path]) => path.startsWith('/api/v1/iam/') || path.includes('/creators'))).toBe(false);
		expect(screen.queryByText('프로젝트 생성 권한 위임')).toBeNull();
		await fireEvent.change(screen.getByLabelText('사용자'), { target: { value: joined.id } });
		await fireEvent.click(screen.getByRole('button', { name: '사용자 역할 할당' }));
		const dialog = screen.getByRole('dialog');
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: /project_member/ }));
		await fireEvent.click(within(dialog).getByRole('button', { name: '역할 저장' }));
		expect(api.put).toHaveBeenCalledExactlyOnceWith('/api/v1/projects/project-a/members/user-b/roles', { role_ids: ['member-role'] }, 'token', undefined, { replayOnUnauthorized: false });
	});
});
