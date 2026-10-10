import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import ProjectMemberRolesModal from '../ProjectMemberRolesModal.svelte';
import type { AssignableProjectRole, ProjectAccessMember } from '$lib/types/project';
const member: ProjectAccessMember = { user_id: 'u', username: 'User', email: '', source: 'direct', is_owner: false, is_manager: true, roles: ['project_admin', 'lumen_user', 'lumen-chat_user'], direct_role_ids: ['admin', 'user'], effective_role_ids: ['admin', 'user', 'chat'], external_role_ids: [] };
const roles: AssignableProjectRole[] = [
	{ id: 'admin', name: 'project_admin', area: 'project', grade: 'admin', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'user', name: 'lumen_user', area: 'lumen', grade: 'user', implied_role_ids: ['chat'], inherited_role_ids: ['chat'] },
	{ id: 'chat', name: 'lumen-chat_user', area: 'lumen-chat', grade: 'user', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'images', name: 'lumen-images_user', description: 'Visual asset generation', area: 'lumen-images', grade: 'user', implied_role_ids: [], inherited_role_ids: [] },
];
afterEach(cleanup);
describe('project member direct and inherited roles', () => {
	it('selects grade parents and independent leaves without treating inherited roles as direct grants', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, isOwner: true, busy: false, error: '', onSave, onClose: vi.fn() });
		expect((screen.getByRole('checkbox', { name: /^lumen_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^lumen-chat_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^lumen-chat_user/ }) as HTMLInputElement).disabled).toBe(true);
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
	it('filters case-insensitive descriptions and IDs without losing hidden direct selections', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, isOwner: true, busy: false, error: '', onSave, onClose: vi.fn() });
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: 'vISUAL' } });
		expect(screen.queryByRole('checkbox', { name: /^project_admin/ })).toBeNull();
		await fireEvent.click(screen.getByRole('checkbox', { name: /^lumen-images_user/ }));
		await fireEvent.input(search, { target: { value: 'no-such-role' } });
		expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
		await fireEvent.input(search, { target: { value: 'USER' } });
		expect((screen.getByRole('checkbox', { name: /^lumen_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^lumen-chat_user/ }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['admin', 'user', 'images']);
	});
	it.each(['group', 'inherited'] as const)('does not offer direct mutation for %s-only membership', async (source) => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...member, source, direct_role_ids: [], external_role_ids: member.effective_role_ids }, roles, isOwner: true, busy: false, error: '', onSave, onClose: vi.fn() });
		expect(screen.getAllByRole('checkbox').every(input => (input as HTMLInputElement).disabled)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).not.toHaveBeenCalled();
	});
	it('keeps selections and save guarded while an update is busy', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, isOwner: true, busy: true, error: '', onSave, onClose: vi.fn() });
		expect((screen.getByRole('searchbox') as HTMLInputElement).disabled).toBe(true);
		expect(screen.getAllByRole('checkbox').every(input => (input as HTMLInputElement).disabled)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).not.toHaveBeenCalled();
	});
});

describe('server-provided transitive and shared descendants', () => {
	const graphRoles: AssignableProjectRole[] = [
		{ id: 'parent-a', name: 'lumen_admin', area: 'lumen', grade: 'admin', implied_role_ids: ['middle'], inherited_role_ids: ['middle', 'leaf'] },
		{ id: 'parent-b', name: 'lumen_user', area: 'lumen', grade: 'user', implied_role_ids: ['middle'], inherited_role_ids: ['middle', 'leaf'] },
		{ id: 'middle', name: 'lumen_reader', area: 'lumen', grade: 'reader', implied_role_ids: ['leaf'], inherited_role_ids: ['leaf'] },
		{ id: 'leaf', name: 'lumen-history_reader', area: 'lumen-history', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] },
		{ id: 'external', name: 'waygate_reader', area: 'waygate', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] },
	];
	const graphMember: ProjectAccessMember = {
		...member, source: 'mixed', roles: graphRoles.map(role => role.name),
		direct_role_ids: ['parent-a', 'parent-b'], effective_role_ids: ['parent-a', 'parent-b', 'middle', 'leaf', 'external'], external_role_ids: ['external'],
	};
	const checkbox = (name: RegExp) => screen.getByRole('checkbox', { name }) as HTMLInputElement;
	it('recomputes shared transitive leaves and retains external inheritance when parents are removed', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: graphMember, roles: graphRoles, isOwner: true, busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox(/^lumen-history_reader/).checked).toBe(true);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(true);
		await fireEvent.click(checkbox(/^lumen_admin/));
		expect(checkbox(/^lumen-history_reader/).checked).toBe(true);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(true);
		await fireEvent.click(checkbox(/^lumen_user/));
		expect(checkbox(/^lumen_reader/).checked).toBe(false);
		expect(checkbox(/^lumen-history_reader/).checked).toBe(false);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(false);
		expect(checkbox(/^waygate_reader/).checked).toBe(true);
		expect(checkbox(/^waygate_reader/).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith([]);
	});

	it('keeps externally inherited descendants checked after removing an overlapping direct parent', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: ['parent-a'], effective_role_ids: ['parent-a', 'middle', 'leaf'], external_role_ids: ['middle', 'leaf'] }, roles: graphRoles, isOwner: true, busy: false, error: '', onSave, onClose: vi.fn() });
		await fireEvent.click(checkbox(/^lumen_admin/));
		expect(checkbox(/^lumen_reader/).checked).toBe(true);
		expect(checkbox(/^lumen_reader/).disabled).toBe(true);
		expect(checkbox(/^lumen-history_reader/).checked).toBe(true);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith([]);
	});
	it('preserves an explicitly direct child after its implying parent is deselected', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: ['parent-a', 'leaf'], effective_role_ids: ['parent-a', 'middle', 'leaf', 'external'] }, roles: graphRoles, isOwner: true, busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(true);
		await fireEvent.click(checkbox(/^lumen_admin/));
		expect(checkbox(/^lumen-history_reader/).checked).toBe(true);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(false);
		expect(checkbox(/^lumen_reader/).checked).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['leaf']);
	});
	it('checks only descendants in the current role-ID graph, not similar role names or grades', async () => {
		const onSave = vi.fn();
		const catalog = graphRoles.map(role => role.id === 'parent-a' ? { ...role, implied_role_ids: [], inherited_role_ids: [] } : role);
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: [], effective_role_ids: [], external_role_ids: [] }, roles: catalog, isOwner: true, busy: false, error: '', onSave, onClose: vi.fn() });
		await fireEvent.click(checkbox(/^lumen_admin/));
		expect(checkbox(/^lumen_reader/).checked).toBe(false);
		expect(checkbox(/^lumen-history_reader/).checked).toBe(false);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['parent-a']);
	});
});
