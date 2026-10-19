import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api, confirmDialog } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
	confirmDialog: vi.fn(),
}));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error {} }));
vi.mock('$app/stores', () => ({ page: writable({ data: { mockup: { active: false } } }) }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project', userId: 'me', federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false), setAuth: vi.fn(),
	canManageDomain: writable(false),
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
vi.mock('$lib/stores/servicePermissions', () => ({
	canManageProject: writable(true), projectPermissions: writable({ permissions: { is_owner: true }, loading: false, error: '' }), refreshProjectPermissions: vi.fn(),
}));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: vi.fn().mockResolvedValue(undefined) } }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import ProfileSection from '../ProfileSection.svelte';
import PasswordSection from '../PasswordSection.svelte';
import KeypairsSection from '../KeypairsSection.svelte';
import ProjectsSection from '../ProjectsSection.svelte';
import ProjectSettingsSection from '../ProjectSettingsSection.svelte';
import CreateProjectModal from '../../projects/CreateProjectModal.svelte';
import { auth, authReady, canManageDomain } from '$lib/stores/auth';
import { projectPermissions } from '$lib/stores/servicePermissions';
import type { PermissionState } from '$lib/stores/servicePermissions';
const permissionFixture = projectPermissions as Writable<PermissionState>;

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}

function authorityFixture(path: string) {
	if (path.endsWith('/eligible-users')) return [{ id: 'joined-user', name: 'Joined user', email: 'joined@example.com', domain_id: 'foreign-home', enabled: true }];
	if (path.endsWith('/ownership')) return { project_id: path.split('/').at(-2), owner_user_id: 'me', status: 'unique', owners: [{ user_id: 'me', name: 'Owner', source: 'direct' }], can_transfer: false, can_delete: false, transfer_operation: null };
	return undefined;
}

afterEach(cleanup);
beforeEach(() => {
	vi.resetAllMocks();
	auth.update((state) => ({ ...state, token: 'token', projectId: 'project', userId: 'me', federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false }));
	(canManageDomain as Writable<boolean>).set(false);
	permissionFixture.set({ permissions: { is_owner: true, is_manager: true, can_write: true, service_permissions: {} }, loading: false, error: '' });
	confirmDialog.mockResolvedValue(true);
});

describe('account controls follow real pending work', () => {
	it('disables keypair creation while pending and allows retry after failure', async () => {
		api.get.mockResolvedValue([]);
		const pending = deferred<unknown>();
		api.post.mockReturnValue(pending.promise);
		render(KeypairsSection);
		await fireEvent.click(screen.getByRole('button', { name: '+ 키페어 생성' }));
		await fireEvent.input(screen.getByPlaceholderText('my-keypair'), { target: { value: 'new-key' } });
		const create = screen.getByRole('button', { name: '생성' }) as HTMLButtonElement;
		await fireEvent.click(create);
		expect(create.disabled).toBe(true);
		pending.reject(new Error('failed'));
		await waitFor(() => expect(create.disabled).toBe(false));
		expect((screen.getByPlaceholderText('my-keypair') as HTMLInputElement).value).toBe('new-key');
		api.post.mockResolvedValueOnce({ name: 'new-key' });
		await fireEvent.click(create);
		await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
	});


	it('re-enables profile saving after a rejected update without losing edits', async () => {
		api.get.mockResolvedValue({ id: 'me', name: 'Original', email: '', description: '' });
		const pending = deferred<unknown>();
		api.patch.mockReturnValue(pending.promise);
		render(ProfileSection);
		const name = await screen.findByLabelText('이름 (닉네임)') as HTMLInputElement;
		await fireEvent.input(name, { target: { value: 'Changed' } });
		const save = screen.getByRole('button', { name: '저장' }) as HTMLButtonElement;
		await fireEvent.click(save);
		expect(save.disabled).toBe(true);
		pending.reject(new Error('failed'));
		await waitFor(() => expect(save.disabled).toBe(false));
		expect(name.value).toBe('Changed');
	});

	it('begins verified email change with current-password proof without PATCHing the email', async () => {
		api.get.mockResolvedValue({ id: 'me', name: 'Original', email: 'old@example.com', description: '' });
		api.post.mockResolvedValue({ accepted: true });
		render(ProfileSection);
		await fireEvent.input(await screen.findByLabelText(/^새 이메일/), { target: { value: 'new@example.com' } });
		const password = screen.getByLabelText(/^현재 비밀번호/) as HTMLInputElement;
		await fireEvent.input(password, { target: { value: 'original-password' } });
		await fireEvent.click(screen.getByRole('button', { name: '이메일 변경 확인 요청' }));
		await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/auth/email/changes', { email: 'new@example.com', current_password: 'original-password' }, 'token', undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false }));
		expect(password.value).toBe('');
		expect(api.patch).not.toHaveBeenCalled();
		expect(await screen.findByText('새 이메일로 확인 링크를 보냈습니다. 받은편지함에서 승인하세요. 아직 계정 이메일은 변경되지 않았습니다.')).toBeTruthy();
		expect(screen.getByText('이메일: old@example.com')).toBeTruthy();
	});

	it('discards email-change confirmation across same-tick verification loss and clears the password', async () => {
		api.get.mockResolvedValue({ id: 'me', name: 'Original', email: 'old@example.com', description: '' });
		const pending = deferred<unknown>(); api.post.mockReturnValue(pending.promise);
		render(ProfileSection);
		await fireEvent.input(await screen.findByLabelText(/^새 이메일/), { target: { value: 'new@example.com' } });
		const password = screen.getByLabelText(/^현재 비밀번호/) as HTMLInputElement;
		await fireEvent.input(password, { target: { value: 'original-password' } });
		await fireEvent.click(screen.getByRole('button', { name: '이메일 변경 확인 요청' }));
		(authReady as Writable<boolean>).set(false); (authReady as Writable<boolean>).set(true);
		pending.resolve({ accepted: true });
		await waitFor(() => expect(password.value).toBe(''));
		expect(screen.queryByText('새 이메일로 확인 링크를 보냈습니다. 받은편지함에서 승인하세요. 아직 계정 이메일은 변경되지 않았습니다.')).toBeNull();
	});

	it('disables password submission only for valid work and clears fields on success', async () => {
		const pending = deferred<unknown>();
		api.post.mockReturnValue(pending.promise);
		render(PasswordSection);
		const change = screen.getByRole('button', { name: '패스워드 변경' }) as HTMLButtonElement;
		await fireEvent.click(change);
		expect(change.disabled).toBe(false);
		expect(api.post).not.toHaveBeenCalled();
		const currentPassword = screen.getByLabelText('현재 패스워드') as HTMLInputElement;
		const newPassword = screen.getByLabelText('새 패스워드') as HTMLInputElement;
		const confirmation = screen.getByLabelText('새 패스워드 확인') as HTMLInputElement;
		await fireEvent.input(currentPassword, { target: { value: 'current-password' } });
		await fireEvent.input(newPassword, { target: { value: 'new-password' } });
		await fireEvent.input(confirmation, { target: { value: 'new-password' } });
		await fireEvent.click(change);
		expect(change.disabled).toBe(true);
		pending.resolve({});
		await waitFor(() => expect(change.disabled).toBe(false));
		expect(currentPassword.value).toBe('');
		expect(newPassword.value).toBe('');
		expect(confirmation.value).toBe('');
	});

	it('disables keypair deletion until the request and refresh settle', async () => {
		api.get.mockResolvedValueOnce([{ name: 'ssh-key', fingerprint: 'fp', type: 'ssh' }]);
		const pending = deferred<unknown>();
		const refresh = deferred<unknown[]>();
		api.get.mockReturnValueOnce(refresh.promise);
		api.delete.mockReturnValue(pending.promise);
		render(KeypairsSection);
		const remove = await screen.findByRole('button', { name: '삭제' }) as HTMLButtonElement;
		await fireEvent.click(remove);
		await waitFor(() => expect(remove.disabled).toBe(true));
		expect(screen.getByText('ssh-key')).toBeTruthy();
		pending.resolve({});
		await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
		expect(remove.disabled).toBe(true);
		expect(screen.getByText('ssh-key')).toBeTruthy();
		refresh.resolve([]);
		await waitFor(() => expect(screen.queryByText('ssh-key')).toBeNull());
		expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
	});

	it('blocks duplicate default-project updates and recovers after failure', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/auth/projects'
			? [{ id: 'project', name: 'Project' }] : { default_project_id: '' }));
		const pending = deferred<unknown>();
		api.patch.mockReturnValue(pending.promise);
		render(ProjectsSection);
		const setDefault = await screen.findByRole('button', { name: '기본 설정' }) as HTMLButtonElement;
		await fireEvent.click(setDefault);
		expect(setDefault.disabled).toBe(true);
		await fireEvent.click(setDefault);
		expect(api.patch).toHaveBeenCalledTimes(1);
		pending.reject(new Error('failed'));
		await waitFor(() => expect(setDefault.disabled).toBe(false));
		expect(screen.getByRole('button', { name: '기본 설정' })).toBe(setDefault);
	});

	it('blocks duplicate project creation and re-enables submission after completion', async () => {
		const pending = deferred<{ id: string; name: string; description: string }>();
		api.get.mockResolvedValue({ domain_id: 'domain-1', can_create_project: true });
		api.post.mockReturnValue(pending.promise);
		render(CreateProjectModal, { onClose: vi.fn(), onSuccess: vi.fn() });
		await waitFor(() => expect((screen.getByLabelText(/프로젝트 이름/) as HTMLInputElement).disabled).toBe(false));
		await fireEvent.input(screen.getByLabelText(/프로젝트 이름/), { target: { value: 'New Project' } });
		const create = screen.getByRole('button', { name: '생성' }) as HTMLButtonElement;
		await fireEvent.click(create);
		expect(create.disabled).toBe(true);
		await fireEvent.click(create);
		expect(api.post).toHaveBeenCalledTimes(1);
		pending.resolve({ id: 'new', name: 'New Project', description: '' });
		await waitFor(() => expect(create.disabled).toBe(false));
	});

	it('keeps member rows mounted during a direct-role update refresh', async () => {
		const member = { user_id: 'other', username: 'Other', email: '', source: 'direct', is_manager: false, is_owner: false, roles: ['project_member'], direct_role_ids: ['member'], effective_role_ids: ['member'], external_role_ids: [] };
		const refresh = deferred<{ items: typeof member[] }>();
		let loads = 0;
		api.get.mockImplementation((path: string) => authorityFixture(path) ? Promise.resolve(authorityFixture(path)) : path.endsWith('/assignable-roles') ? Promise.resolve({ is_owner: true, can_manage_owners: false, roles: [{ id: 'member', name: 'project_member', area: 'project', grade: 'member', implied_role_ids: [], inherited_role_ids: [] }, { id: 'admin', name: 'project_admin', area: 'project', grade: 'admin', implied_role_ids: ['member'], inherited_role_ids: ['member'] }] }) : ++loads === 1 ? Promise.resolve({ items: [member] }) : refresh.promise);
		api.put.mockResolvedValue({});
		render(ProjectSettingsSection);
		const originalRow = (await screen.findByText('Other')).closest('tr');
		await fireEvent.click(screen.getByRole('button', { name: '역할 편집' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /project_admin/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/v1/projects/project/members/other/roles', { role_ids: ['member', 'admin'] }, 'token', 'project', { replayOnUnauthorized: false }));
		expect((screen.getByRole('button', { name: '역할 편집' }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getByText('Other').closest('tr')).toBe(originalRow);
		refresh.resolve({ items: [{ ...member, is_manager: true }] });
		await waitFor(() => expect((screen.getByRole('button', { name: '역할 편집' }) as HTMLButtonElement).disabled).toBe(false));
		expect(screen.getByText('Other').closest('tr')).toBe(originalRow);
	});

	it('re-enables role saving after a rejected mutation and keeps selected grants', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(authorityFixture(path) ?? (path.endsWith('/assignable-roles') ? { is_owner: true, can_manage_owners: true, roles: [{ id: 'chat', name: 'lumen-chat_user', area: 'lumen', grade: 'user', implied_role_ids: [], inherited_role_ids: [] }] } : { items: [{ user_id: 'other', username: 'Other', source: 'direct', is_manager: false, roles: [], direct_role_ids: [], effective_role_ids: [], external_role_ids: [] }] })));
		const pending = deferred<unknown>(); api.put.mockReturnValue(pending.promise);
		render(ProjectSettingsSection);
		await fireEvent.click(await screen.findByRole('button', { name: '역할 편집' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /lumen-chat_user/ }));
		const save = screen.getByRole('button', { name: '역할 저장' }) as HTMLButtonElement;
		await fireEvent.click(save); expect(save.disabled).toBe(true);
		await fireEvent.click(save); expect(api.put).toHaveBeenCalledTimes(1);
		pending.reject(new Error('failed'));
		await waitFor(() => expect(save.disabled).toBe(false));
		expect((screen.getByRole('checkbox', { name: /lumen-chat_user/ }) as HTMLInputElement).checked).toBe(true);
	});


	it('removes old member actions before the next project replies', async () => {
		const member = { user_id: 'alpha-user', username: 'Alpha member', email: '', source: 'direct', is_manager: false, is_owner: false, roles: [], direct_role_ids: [], effective_role_ids: [], external_role_ids: [] };
		const members = deferred<{ items: typeof member[] }>();
		api.get.mockImplementation((path: string) => {
			const authority = authorityFixture(path); if (authority) return Promise.resolve(authority);
			if (path.endsWith('/assignable-roles')) return Promise.resolve({ is_owner: true, can_manage_owners: true, roles: [] });
			if (path.includes('/other/')) return members.promise;
			return Promise.resolve({ items: [member] });
		});
		render(ProjectSettingsSection);
		await screen.findByText('Alpha member');
		auth.update((state) => ({ ...state, projectId: 'other' }));
		await waitFor(() => expect(screen.queryByText('Alpha member')).toBeNull());
		expect(screen.queryByRole('button', { name: '역할 편집' })).toBeNull();
		members.resolve({ items: [{ ...member, user_id: 'beta-user', username: 'Beta member' }] });
		await screen.findByText('Beta member');
		expect(screen.queryByText('Alpha member')).toBeNull();
	});

	it('requires removal confirmation and never offers group-grant mutations', async () => {
		const direct = { user_id: 'direct', username: 'Direct user', email: '', source: 'direct', is_manager: false, is_owner: false, roles: ['project_member'], direct_role_ids: ['member'], effective_role_ids: ['member'], external_role_ids: [] };
		const group = { ...direct, user_id: 'group', username: 'Group user', source: 'group', direct_role_ids: [], external_role_ids: ['member'], group_name: 'Team' };
		api.get.mockImplementation((path: string) => Promise.resolve(authorityFixture(path) ?? (path.endsWith('/assignable-roles') ? { is_owner: true, can_manage_owners: true, roles: [{ id: 'member', name: 'project_member', area: 'project', grade: 'member', implied_role_ids: [], inherited_role_ids: [] }] } : { items: [direct, group] })));
		const decision = deferred<boolean>(); confirmDialog.mockReturnValueOnce(decision.promise);
		api.delete.mockResolvedValue({}); render(ProjectSettingsSection);
		await screen.findByText('Group user');
		expect(screen.getAllByRole('button', { name: '역할 편집' })).toHaveLength(1);
		expect(screen.getAllByRole('button', { name: '멤버 제거' })).toHaveLength(1);
		await fireEvent.click(screen.getByRole('button', { name: '멤버 제거' }));
		expect(api.delete).not.toHaveBeenCalled();
		decision.resolve(false);
		await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
		expect(api.delete).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: '멤버 제거' }));
		await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/v1/projects/project/members/direct', 'token', 'project', { replayOnUnauthorized: false }));
	});

	it('uses permissions API ownership and never offers administrator removal to a nonowner', async () => {
		permissionFixture.set({ permissions: { is_owner: false, is_manager: true, can_write: true, service_permissions: {} }, loading: false, error: '' });
		const member = { user_id: 'admin', username: 'Project admin', email: '', source: 'direct', is_manager: true, is_owner: false, roles: ['project_admin'], direct_role_ids: ['admin'], effective_role_ids: ['admin'], external_role_ids: [] };
		api.get.mockImplementation((path: string) => Promise.resolve(authorityFixture(path) ?? (path.endsWith('/assignable-roles') ? { is_owner: false, can_manage_owners: false, roles: [{ id: 'chat', name: 'lumen-chat_user', area: 'lumen', grade: 'user', implied_role_ids: [], inherited_role_ids: [] }] } : { items: [member] })));
		render(ProjectSettingsSection); await screen.findByText('Project admin');
		expect(screen.queryByRole('button', { name: '멤버 제거' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '역할 편집' }));
		expect(screen.queryByRole('checkbox', { name: /^project_admin/ })).toBeNull();
		expect((screen.getByRole('checkbox', { name: /^lumen-chat_user/ }) as HTMLInputElement).disabled).toBe(false);
	});
	it('links verified domain managers to IAM invitations rather than calling retired project invitation APIs', async () => {
		(canManageDomain as Writable<boolean>).set(true);
		api.get.mockImplementation((path: string) => Promise.resolve(authorityFixture(path) ?? (path.endsWith('/assignable-roles') ? { roles: [], is_owner: false, can_manage_owners: false } : { items: [] })));
		render(ProjectSettingsSection);
		expect(screen.getByRole('link', { name: '이메일 초대' }).getAttribute('href')).toBe('/dashboard/iam');
		await waitFor(() => expect(api.get).toHaveBeenCalledTimes(5));
		expect(screen.queryByPlaceholderText('user@example.com')).toBeNull();
	});
	it('adds joined users with a foreign home identity through the existing role editor', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(authorityFixture(path) ?? (path.endsWith('/assignable-roles') ? { is_owner: true, can_manage_owners: true, roles: [{ id: 'reader-id', name: 'project_reader', area: 'project', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] }] } : { items: [] })));
		api.put.mockResolvedValue({});
		render(ProjectSettingsSection);
		await screen.findByRole('option', { name: 'Joined user · joined@example.com' });
		await fireEvent.change(screen.getByLabelText('사용자'), { target: { value: 'joined-user' } });
		await fireEvent.click(screen.getByRole('button', { name: '사용자 역할 할당' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /^project_reader/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(api.put).toHaveBeenCalledWith('/api/v1/projects/project/members/joined-user/roles', { role_ids: ['reader-id'] }, 'token', 'project', { replayOnUnauthorized: false });
	});
});
