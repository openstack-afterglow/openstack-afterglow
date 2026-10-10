import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api, confirmDialog } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
	confirmDialog: vi.fn(),
}));
vi.mock('$lib/api/client', () => ({ api, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', projectId: 'project', userId: 'me', federated: false }),
	authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false), setAuth: vi.fn(),
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
import { auth } from '$lib/stores/auth';
import { projectPermissions } from '$lib/stores/servicePermissions';
import type { PermissionState } from '$lib/stores/servicePermissions';
const permissionFixture = projectPermissions as Writable<PermissionState>;

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}

afterEach(cleanup);
beforeEach(() => {
	vi.resetAllMocks();
	auth.update((state) => ({ ...state, token: 'token', projectId: 'project', userId: 'me', federated: false }));
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

	it('disables project switching while pending and recovers after failure', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/auth/projects'
			? [{ id: 'other', name: 'Other project' }] : { default_project_id: '' }));
		const pending = deferred<unknown>();
		api.post.mockReturnValue(pending.promise);
		render(ProjectsSection);
		const project = await screen.findByRole('button', { name: 'Other project' }) as HTMLButtonElement;
		await fireEvent.click(project);
		expect(project.disabled).toBe(true);
		pending.reject(new Error('failed'));
		await waitFor(() => expect(project.disabled).toBe(false));
		expect(screen.getByRole('button', { name: 'Other project' })).toBe(project);
	});

	it('re-enables profile saving after a rejected update without losing edits', async () => {
		api.get.mockResolvedValue({ id: 'me', name: 'Original', email: '', description: '' });
		const pending = deferred<unknown>();
		api.patch.mockReturnValue(pending.promise);
		render(ProfileSection);
		const name = await screen.findByPlaceholderText('이름 입력') as HTMLInputElement;
		await fireEvent.input(name, { target: { value: 'Changed' } });
		const save = screen.getByRole('button', { name: '저장' }) as HTMLButtonElement;
		await fireEvent.click(save);
		expect(save.disabled).toBe(true);
		pending.reject(new Error('failed'));
		await waitFor(() => expect(save.disabled).toBe(false));
		expect(name.value).toBe('Changed');
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
		api.post.mockReturnValue(pending.promise);
		render(CreateProjectModal, { onClose: vi.fn(), onSuccess: vi.fn() });
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
		api.get.mockImplementation((path: string) => path.endsWith('/assignable-roles') ? Promise.resolve({ is_owner: true, roles: [{ id: 'member', name: 'project_member', area: 'project', grade: 'member', implied_role_ids: [], inherited_role_ids: [] }, { id: 'admin', name: 'project_admin', area: 'project', grade: 'admin', implied_role_ids: ['member'], inherited_role_ids: ['member'] }] }) : ++loads === 1 ? Promise.resolve({ items: [member] }) : refresh.promise);
		api.put.mockResolvedValue({});
		render(ProjectSettingsSection);
		const originalRow = (await screen.findByText('Other')).closest('tr');
		await fireEvent.click(screen.getByRole('button', { name: '역할 편집' }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /project_admin/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/v1/projects/project/members/other/roles', { role_ids: ['member', 'admin'] }, 'token', 'project'));
		expect((screen.getByRole('button', { name: '역할 편집' }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.getByText('Other').closest('tr')).toBe(originalRow);
		refresh.resolve({ items: [{ ...member, is_manager: true }] });
		await waitFor(() => expect((screen.getByRole('button', { name: '역할 편집' }) as HTMLButtonElement).disabled).toBe(false));
		expect(screen.getByText('Other').closest('tr')).toBe(originalRow);
	});

	it('re-enables role saving after a rejected mutation and keeps selected grants', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/assignable-roles') ? { is_owner: true, roles: [{ id: 'chat', name: 'lumen-chat_user', area: 'lumen-chat', grade: 'user', implied_role_ids: [], inherited_role_ids: [] }] } : { items: [{ user_id: 'other', username: 'Other', source: 'direct', is_manager: false, roles: [], direct_role_ids: [], effective_role_ids: [], external_role_ids: [] }] }));
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

	it('blocks duplicate invitation cancellation and recovers after failure', async () => {
		api.get.mockImplementation((path: string) => Promise.resolve({ items: path.endsWith('/invitations')
			? [{ id: 1, invited_email: 'invitee@example.test', keystone_role: 'member', status: 'pending', expires_at: '2026-10-07T00:00:00Z' }] : [] }));
		const pending = deferred<unknown>();
		api.delete.mockReturnValue(pending.promise);
		render(ProjectSettingsSection);
		await fireEvent.click(screen.getByRole('button', { name: '초대' }));
		const cancel = await screen.findByRole('button', { name: '취소' }) as HTMLButtonElement;
		const originalRow = screen.getByText('invitee@example.test').closest('tr');
		await fireEvent.click(cancel);
		expect(cancel.disabled).toBe(true);
		await fireEvent.click(cancel);
		expect(api.delete).toHaveBeenCalledTimes(1);
		pending.reject(new Error('failed'));
		await waitFor(() => expect(cancel.disabled).toBe(false));
		expect(screen.getByText('invitee@example.test').closest('tr')).toBe(originalRow);
	});

	it('removes old member and invitation actions before the next project replies', async () => {
		const member = { user_id: 'alpha-user', username: 'Alpha member', email: '', source: 'direct', is_manager: false };
		const invitation = { id: 1, invited_email: 'alpha@example.test', keystone_role: 'member', status: 'pending', expires_at: '2026-11-07T00:00:00Z' };
		const members = deferred<{ items: typeof member[] }>();
		const invitations = deferred<{ items: typeof invitation[] }>();
		api.get.mockImplementation((path: string) => {
			if (path.endsWith('/assignable-roles')) return Promise.resolve({ is_owner: true, roles: [] });
			if (path.includes('/other/')) return path.endsWith('/invitations') ? invitations.promise : members.promise;
			return Promise.resolve({ items: path.endsWith('/invitations') ? [invitation] : [member] });
		});
		render(ProjectSettingsSection);
		await screen.findByText('Alpha member');
		await fireEvent.click(screen.getByRole('button', { name: '초대' }));
		await screen.findByText('alpha@example.test');
		auth.update((state) => ({ ...state, projectId: 'other' }));
		await waitFor(() => expect(screen.queryByText('alpha@example.test')).toBeNull());
		await fireEvent.click(screen.getByRole('button', { name: /^멤버/ }));
		expect(screen.queryByText('Alpha member')).toBeNull();
		expect(screen.queryByRole('button', { name: '역할 편집' })).toBeNull();
		members.resolve({ items: [{ ...member, user_id: 'beta-user', username: 'Beta member' }] });
		invitations.resolve({ items: [{ ...invitation, id: 2, invited_email: 'beta@example.test' }] });
		await screen.findByText('Beta member');
		await fireEvent.click(screen.getByRole('button', { name: '초대' }));
		await screen.findByText('beta@example.test');
		expect(screen.queryByText('alpha@example.test')).toBeNull();
	});

	it('requires removal confirmation and never offers group-grant mutations', async () => {
		const direct = { user_id: 'direct', username: 'Direct user', email: '', source: 'direct', is_manager: false, is_owner: false, roles: ['project_member'], direct_role_ids: ['member'], effective_role_ids: ['member'], external_role_ids: [] };
		const group = { ...direct, user_id: 'group', username: 'Group user', source: 'group', direct_role_ids: [], external_role_ids: ['member'], group_name: 'Team' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/assignable-roles') ? { is_owner: true, roles: [{ id: 'member', name: 'project_member', area: 'project', grade: 'member', implied_role_ids: [], inherited_role_ids: [] }] } : { items: [direct, group] }));
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
		await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/v1/projects/project/members/direct', 'token', 'project'));
	});

	it('uses permissions API ownership and never offers administrator removal to a nonowner', async () => {
		permissionFixture.set({ permissions: { is_owner: false, is_manager: true, can_write: true, service_permissions: {} }, loading: false, error: '' });
		const member = { user_id: 'admin', username: 'Project admin', email: '', source: 'direct', is_manager: true, is_owner: false, roles: ['project_admin'], direct_role_ids: ['admin'], effective_role_ids: ['admin'], external_role_ids: [] };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/assignable-roles') ? { is_owner: false, roles: [{ id: 'chat', name: 'lumen-chat_user', area: 'lumen', grade: 'user', implied_role_ids: [], inherited_role_ids: [] }] } : { items: [member] }));
		render(ProjectSettingsSection); await screen.findByText('Project admin');
		expect(screen.queryByRole('button', { name: '멤버 제거' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '역할 편집' }));
		expect(screen.queryByRole('checkbox', { name: /^project_admin/ })).toBeNull();
		expect((screen.getByRole('checkbox', { name: /^lumen-chat_user/ }) as HTMLInputElement).disabled).toBe(false);
	});
});
