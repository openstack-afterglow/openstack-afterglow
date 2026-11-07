import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'actor', domainId: 'domain-a', domainName: 'Domain A', isDomainManager: true, isSystemAdmin: false }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false)
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
import { auth, authReady } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/domain-iam';
import { t as workspaceT } from '$lib/i18n/ns/workspace-selector';
import type { ProjectAccessMember } from '$lib/types/project';
import IamProjects from '../IamProjects.svelte';

const project = { id: 'project-a', name: 'Project A', description: 'First project', enabled: true, domain_id: 'domain-a', created_at: '2026-11-01T00:00:00Z' };
const defaultProject = { ...project, id: 'project-default', name: 'Default', description: '' };
const created = { ...project, id: 'project-new', name: 'New project' };
const user = { id: 'user-a', name: 'Alice', email: 'alice@example.com', enabled: true, domain_id: 'domain-a', protected: false };
const joined = { ...user, id: 'user-b', name: 'Bob' };
const member: ProjectAccessMember = { user_id: user.id, username: user.name, email: user.email, is_owner: false, is_manager: false, roles: ['project_reader'], direct_role_ids: ['reader-role'], direct_roles: [{ id: 'reader-role', name: 'project_reader', inherited_role_ids: [] }], effective_role_ids: ['reader-role'], external_role_ids: [], source: 'direct' };
const catalog = { is_owner: false, can_manage_owners: false, roles: [
	{ id: 'reader-role', name: 'project_reader', area: 'project', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'member-role', name: 'project_member', area: 'project', grade: 'member', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'native-admin', name: 'admin', area: 'legacy', grade: 'admin', implied_role_ids: [], inherited_role_ids: [] }
] };
let current = true;
let allowed = true;
let rows: Array<typeof project> = [project];
let members = [member];
const session = { token: () => 'token', userId: 'actor', domainId: 'domain-a', isCurrent: () => current, canSubmit: () => current && allowed };
function fixture(path: string) {
	if (path.endsWith('/eligible-users')) return [user, joined];
	if (path.endsWith('/ownership')) return { project_id: path.split('/').at(-2), owner_user_id: 'actor', status: 'unique', owners: [{ user_id: 'actor', name: 'Owner', source: 'direct' }], can_transfer: false, can_delete: false, transfer_operation: null };
	if (path.includes('/projects/capabilities?')) return { domain_id: 'domain-a', can_create_project: true };
	if (path === '/api/v1/iam/projects') return { items: rows };
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
const slideOver = () => screen.getAllByRole('dialog').at(-1)!;
async function openCreate() {
	await fireEvent.click(screen.getByRole('button', { name: workspaceT('newProject') }));
	const input = screen.getByRole('textbox', { name: workspaceT('projectName') }) as HTMLInputElement;
	await waitFor(() => expect(input.disabled).toBe(false));
	await fireEvent.input(input, { target: { value: created.name } });
	return screen.getByRole('button', { name: workspaceT('create') }) as HTMLButtonElement;
}

describe('domain manager project table', () => {
	it('lists the domain projects directly with edit, members and remove actions and no project picker', async () => {
		rows = [project, defaultProject];
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		expect(screen.queryByLabelText('프로젝트')).toBeNull();
		expect(screen.queryByText(/project_creator/)).toBeNull();
		const row = screen.getByText('Project A').closest('tr')!;
		for (const label of [t('projectEdit'), t('projectMembers'), t('projectRemove')]) expect(within(row).getByRole('button', { name: label })).toBeTruthy();
		const protectedRow = screen.getByText('Default', { selector: 'span' }).closest('tr')!;
		expect((within(protectedRow).getByRole('button', { name: t('projectEdit') }) as HTMLButtonElement).disabled).toBe(true);
		expect((within(protectedRow).getByRole('button', { name: t('projectRemove') }) as HTMLButtonElement).disabled).toBe(true);
		expect((within(protectedRow).getByRole('button', { name: t('projectMembers') }) as HTMLButtonElement).disabled).toBe(false);
	});
	it('does not show the domain identifier anywhere on the page', async () => {
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		expect(screen.queryByText(/domain-a/)).toBeNull();
	});
	it('edits name and description in a right slide-in and refreshes the table', async () => {
		api.patch.mockImplementation(async () => { rows = [{ ...project, name: 'Renamed' }]; return rows[0]; });
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		await fireEvent.click(screen.getByRole('button', { name: t('projectEdit') }));
		const panel = slideOver();
		expect(within(panel).getByText(t('editProjectTitle', { project: 'Project A' }))).toBeTruthy();
		const name = within(panel).getByRole('textbox', { name: new RegExp(t('name')) }) as HTMLInputElement;
		await fireEvent.input(name, { target: { value: 'Renamed' } });
		await fireEvent.click(within(panel).getByRole('button', { name: t('save') }));
		await waitFor(() => expect(api.patch).toHaveBeenCalledExactlyOnceWith('/api/v1/iam/projects/project-a', { name: 'Renamed', description: 'First project' }, 'token', undefined, { replayOnUnauthorized: false }));
		await waitFor(() => expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/iam/projects')).toHaveLength(2));
	});
	it('removes a project through the deletion flow only after the explicit action', async () => {
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		await fireEvent.click(screen.getByRole('button', { name: t('projectRemove') }));
		expect(screen.getByRole('dialog')).toBeTruthy();
		expect(api.delete).not.toHaveBeenCalled();
	});
});

describe('manager project creation', () => {
	it('creates in the verified IAM domain and refreshes the table with the real result', async () => {
		api.post.mockImplementation(async () => { rows = [project, created]; return created; });
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		await fireEvent.click(await openCreate());
		await screen.findByText('New project');
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/projects', { name: created.name, description: '', domain_id: 'domain-a' }, 'token', undefined, { replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' });
		expect(api.get.mock.calls.filter(([path]) => path === '/api/v1/iam/projects')).toHaveLength(2);
		expect(screen.queryByRole('dialog')).toBeNull();
	});
	it('keeps an unknown native create outcome non-replayable and never refreshes as success', async () => {
		api.post.mockRejectedValue(new TypeError('response lost'));
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
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
		await screen.findByText('Project A');
		await fireEvent.click(await openCreate());
		await screen.findByText(workspaceT('createRejected'));
		expect(screen.queryByText(created.name, { selector: 'td span' })).toBeNull();
	});
	it('fences a stale IAM session immediately before creation even when the modal capability is allowed', async () => {
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		const submit = await openCreate(); current = false;
		await fireEvent.click(submit);
		expect(api.post).not.toHaveBeenCalled();
	});
	it('preserves the creation draft but disables submit while manager authority is being rechecked', async () => {
		const view = render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		const submit = await openCreate();
		await view.rerender({ session, blocked: true, onDenied: vi.fn() });
		expect(submit.disabled).toBe(true);
		expect((screen.getByRole('textbox', { name: workspaceT('projectName') }) as HTMLInputElement).value).toBe(created.name);
		await fireEvent.submit(submit.form!);
		expect(api.post).not.toHaveBeenCalled();
	});
});

describe('project members slide-in', () => {
	it('adds safe direct roles to a joined user without offering a new native admin grant', async () => {
		api.put.mockResolvedValue({});
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		await fireEvent.click(screen.getByRole('button', { name: t('projectMembers') }));
		const panel = slideOver();
		expect(within(panel).getByText(t('membersTitle', { project: 'Project A' }))).toBeTruthy();
		await within(panel).findByText('Alice');
		await fireEvent.change(within(panel).getByLabelText('사용자'), { target: { value: joined.id } });
		await fireEvent.click(within(panel).getByRole('button', { name: '사용자 역할 할당' }));
		const dialog = slideOver();
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: /project_member/ }));
		expect(within(dialog).queryByRole('button', { name: /^legacy/ })).toBeNull();
		expect(within(dialog).queryByRole('checkbox', { name: /^admin\b/i })).toBeNull();
		await fireEvent.click(within(dialog).getByRole('button', { name: '역할 저장' }));
		expect(api.put).toHaveBeenCalledExactlyOnceWith('/api/v1/iam/projects/project-a/members/user-b/roles', { role_ids: ['member-role'] }, 'token', undefined, { replayOnUnauthorized: false });
	});
	it.each(['group', 'inherited'] as const)('edits only direct grants beside %s authority and never removes it', async source => {
		members = [{ ...member, source, direct_role_ids: [], direct_roles: [], external_role_ids: ['reader-role'] }];
		api.put.mockResolvedValue({});
		render(IamProjects, { session, onDenied: vi.fn() });
		await screen.findByText('Project A');
		await fireEvent.click(screen.getByRole('button', { name: t('projectMembers') }));
		const panel = slideOver();
		await within(panel).findByText('Alice');
		expect((within(panel).getByRole('button', { name: '멤버 제거' }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(within(panel).getByRole('button', { name: '역할 편집' }));
		const dialog = slideOver();
		const inherited = within(dialog).getByRole('checkbox', { name: /project_reader/ }) as HTMLInputElement;
		expect(inherited.checked).toBe(true); expect(inherited.disabled).toBe(true);
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: /project_member/ }));
		await fireEvent.click(within(dialog).getByRole('button', { name: '역할 저장' }));
		expect(api.put).toHaveBeenCalledExactlyOnceWith('/api/v1/iam/projects/project-a/members/user-a/roles', { role_ids: ['member-role'] }, 'token', undefined, { replayOnUnauthorized: false });
		expect(api.delete).not.toHaveBeenCalled();
	});
});
