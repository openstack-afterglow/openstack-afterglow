import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import ProjectMemberRolesModal from '../ProjectMemberRolesModal.svelte';
import type { ProjectAccessMember } from '$lib/types/project';
const member: ProjectAccessMember = { user_id: 'u', username: 'User', email: '', source: 'direct', is_owner: false, is_manager: true, roles: ['project_admin', 'lumen_user', 'lumen-chat_user'], direct_role_ids: ['admin', 'user'], effective_role_ids: ['admin', 'user', 'chat'] };
const roles = [
	{ id: 'admin', name: 'project_admin', area: 'project', grade: 'admin' },
	{ id: 'user', name: 'lumen_user', area: 'lumen', grade: 'user' },
	{ id: 'chat', name: 'lumen-chat_user', area: 'lumen-chat', grade: 'user' },
	{ id: 'images', name: 'lumen-images_user', area: 'lumen-images', grade: 'user' },
];
afterEach(cleanup);
describe('project member direct and inherited roles', () => {
	it('selects grade parents and independent leaves without treating inherited roles as direct grants', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, isOwner: true, busy: false, error: '', onSave, onClose: vi.fn() });
		expect((screen.getByRole('checkbox', { name: /^lumen_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^lumen-chat_user/ }) as HTMLInputElement).checked).toBe(false);
		expect(screen.getByText(/상속됨 \(읽기 전용\)/)).toBeTruthy();
		await fireEvent.click(screen.getByRole('checkbox', { name: /^lumen-images_user/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['admin', 'user', 'images']);
	});
	it('keeps owner/admin grants protected for nonowners while service grants stay editable', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, isOwner: false, busy: false, error: '', onSave, onClose: vi.fn() });
		expect((screen.getByRole('checkbox', { name: /^project_admin/ }) as HTMLInputElement).disabled).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^lumen-images_user/ }) as HTMLInputElement).disabled).toBe(false);
	});
});
