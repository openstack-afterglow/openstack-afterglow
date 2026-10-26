import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import ProjectMemberRolesModal from '../ProjectMemberRolesModal.svelte';
import type { AssignableProjectRole, ProjectAccessMember } from '$lib/types/project';
const member: ProjectAccessMember = { user_id: 'u', username: 'User', email: '', source: 'direct', is_owner: false, is_manager: true, roles: ['project_admin', 'lumen_user', 'lumen-chat_user'], direct_role_ids: ['admin', 'user'], effective_role_ids: ['admin', 'user', 'chat'], external_role_ids: [] };
const roles: AssignableProjectRole[] = [
	{ id: 'admin', name: 'project_admin', area: 'project', grade: 'admin', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'user', name: 'lumen_user', area: 'lumen', grade: 'user', implied_role_ids: ['chat'], inherited_role_ids: ['chat'] },
	{ id: 'chat', name: 'lumen-chat_user', area: 'lumen', grade: 'user', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'images', name: 'lumen-images_user', description: 'Visual asset generation', area: 'lumen', grade: 'user', implied_role_ids: [], inherited_role_ids: [] },
];
afterEach(cleanup);
const chooseArea = (area: string) => fireEvent.change(screen.getByRole('combobox', { name: '권한 영역' }), { target: { value: area } });
describe('project member direct and inherited roles', () => {
	it.each([true, false])('never grants or strips singleton ownership in the generic editor (existing owner: %s)', async (owns) => {
		const onSave = vi.fn();
		const ownerRole: AssignableProjectRole = { id: 'owner-id', name: 'project_owner', area: 'project', grade: 'owner', implied_role_ids: [], inherited_role_ids: [] };
		const direct = owns ? ['owner-id', 'admin'] : ['admin'];
		render(ProjectMemberRolesModal, { member: { ...member, is_owner: owns, direct_role_ids: direct }, roles: [ownerRole, ...roles], busy: false, error: '', onSave, onClose: vi.fn() });
		const checkbox = screen.getByRole('checkbox', { name: /^project_owner/ }) as HTMLInputElement;
		expect(checkbox.disabled).toBe(true); expect(checkbox.checked).toBe(owns);
		await fireEvent.click(checkbox);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(direct);
	});
	it('selects grade parents and independent leaves without treating inherited roles as direct grants', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, busy: false, error: '', onSave, onClose: vi.fn() });
		await chooseArea('lumen');
		expect((screen.getByRole('checkbox', { name: /^lumen_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^lumen-chat_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^lumen-chat_user/ }) as HTMLInputElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('checkbox', { name: /^lumen-images_user/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['admin', 'user', 'images']);
	});
	it('offers only the server-grantable roles without exposing project admin to nonowners', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles: roles.filter(role => role.name !== 'project_admin'), busy: false, error: '', onSave, onClose: vi.fn() });
		expect(screen.queryByRole('checkbox', { name: /^project_admin/ })).toBeNull();
		await chooseArea('lumen');
		expect((screen.getByRole('checkbox', { name: /^lumen-images_user/ }) as HTMLInputElement).disabled).toBe(false);
	});
	it('filters case-insensitive descriptions and IDs without losing hidden direct selections', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, busy: false, error: '', onSave, onClose: vi.fn() });
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
	it('preserves hidden direct and legacy grants across area navigation and search fallback, then restores the original area', async () => {
		const onSave = vi.fn();
		const catalog: AssignableProjectRole[] = [...roles, { id: 'opaque-id', name: 'lumen-looking', area: 'custom-area', grade: null, implied_role_ids: [], inherited_role_ids: [] }];
		render(ProjectMemberRolesModal, { member: { ...member, direct_role_ids: ['admin', 'user', 'legacy-id'] }, roles: catalog, busy: false, error: '', onSave, onClose: vi.fn() });
		expect(screen.queryByRole('checkbox', { name: /^lumen_user/ })).toBeNull();
		await chooseArea('custom-area');
		await fireEvent.click(screen.getByRole('checkbox', { name: /^lumen-looking/ }));
		await chooseArea('project');
		await fireEvent.click(screen.getByRole('checkbox', { name: /^project_admin/ }));
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: 'OPAQUE-ID' } });
		expect((screen.getByRole('checkbox', { name: /^lumen-looking/ }) as HTMLInputElement).checked).toBe(true);
		expect(screen.queryByRole('checkbox', { name: /^project_admin/ })).toBeNull();
		await fireEvent.input(search, { target: { value: 'user' } });
		expect((screen.getByRole('checkbox', { name: /^lumen_user/ }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.input(search, { target: { value: '' } });
		expect((screen.getByRole('checkbox', { name: /^project_admin/ }) as HTMLInputElement).checked).toBe(false);
		expect(screen.queryByRole('checkbox', { name: /^lumen-looking/ })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['user', 'legacy-id', 'opaque-id']);
	});
	it.each(['group', 'inherited'] as const)('does not offer direct mutation for %s-only membership', async (source) => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...member, source, direct_role_ids: [], external_role_ids: member.effective_role_ids }, roles, busy: false, error: '', onSave, onClose: vi.fn() });
		expect(screen.getAllByRole('checkbox').every(input => (input as HTMLInputElement).disabled)).toBe(true);
		await chooseArea('lumen');
		expect(screen.getAllByRole('checkbox').every(input => (input as HTMLInputElement).disabled)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).not.toHaveBeenCalled();
	});
	it('keeps selections and save guarded while an update is busy', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, busy: true, error: '', onSave, onClose: vi.fn() });
		expect((screen.getByRole('searchbox') as HTMLInputElement).disabled).toBe(true);
		expect(screen.getAllByRole('checkbox').every(input => (input as HTMLInputElement).disabled)).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).not.toHaveBeenCalled();
	});
});

describe('native admin removal-only selection', () => {
	const nativeRole: AssignableProjectRole = { id: 'native-admin-id', name: 'admin', area: 'legacy', grade: 'admin', implied_role_ids: ['chat'], inherited_role_ids: ['chat'] };
	const serviceAdmin: AssignableProjectRole = { id: 'service-admin-id', name: 'lumen_admin', area: 'lumen', grade: 'admin', implied_role_ids: [], inherited_role_ids: [] };
	const checkbox = () => screen.getByRole('checkbox', { name: /^admin\b/i }) as HTMLInputElement;
	it.each(['admin', 'ADMIN'])('blocks new %s grants even on synthetic changes without blocking project/service admin roles', async (name) => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...member, direct_role_ids: ['user', 'legacy-id'] }, roles: [{ ...nativeRole, name }, ...roles, serviceAdmin], busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox()).toMatchObject({ checked: false, disabled: true });
		await fireEvent.change(checkbox(), { target: { checked: true } });
		await chooseArea('project');
		const projectAdmin = screen.getByRole('checkbox', { name: /^project_admin/ }) as HTMLInputElement;
		expect(projectAdmin.disabled).toBe(false);
		await fireEvent.click(projectAdmin);
		await chooseArea('lumen');
		const lumenAdmin = screen.getByRole('checkbox', { name: /^lumen_admin/ }) as HTMLInputElement;
		expect(lumenAdmin.disabled).toBe(false);
		await fireEvent.click(lumenAdmin);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['user', 'legacy-id', 'admin', 'service-admin-id']);
	});
	it('preserves an unchanged direct admin, then removes it without permitting re-add in the same draft', async () => {
		const onSave = vi.fn();
		const direct = ['native-admin-id', 'admin', 'legacy-id'];
		render(ProjectMemberRolesModal, { member: { ...member, direct_role_ids: direct }, roles: [nativeRole, ...roles], busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox()).toMatchObject({ checked: true, disabled: false });
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenLastCalledWith(direct);
		await fireEvent.click(checkbox());
		expect(checkbox()).toMatchObject({ checked: false, disabled: true });
		await fireEvent.change(checkbox(), { target: { checked: true } });
		await chooseArea('lumen');
		expect(screen.getByRole('checkbox', { name: /^lumen-chat_user/ })).toMatchObject({ checked: false, disabled: false });
		await chooseArea('legacy');
		expect(checkbox()).toMatchObject({ checked: false, disabled: true });
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenLastCalledWith(['admin', 'legacy-id']);
	});
	it.each(['group', 'inherited', 'mixed'] as const)('does not turn %s external admin into a direct grant or revoke', async (source) => {
		const onSave = vi.fn();
		const direct = source === 'mixed' ? ['user'] : [];
		render(ProjectMemberRolesModal, { member: { ...member, source, direct_role_ids: direct, external_role_ids: ['native-admin-id'] }, roles: [nativeRole, ...roles], busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox()).toMatchObject({ checked: true, disabled: true });
		await fireEvent.change(checkbox(), { target: { checked: false } });
		await fireEvent.change(checkbox(), { target: { checked: true } });
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		if (source === 'mixed') expect(onSave).toHaveBeenCalledWith(direct);
		else expect(onSave).not.toHaveBeenCalled();
	});
	it('removes the direct admin assignment while keeping overlapping external inheritance visible', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...member, source: 'mixed', direct_role_ids: ['native-admin-id', 'user'], external_role_ids: ['native-admin-id'] }, roles: [nativeRole, ...roles], busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox()).toMatchObject({ checked: true, disabled: false });
		await fireEvent.click(checkbox());
		expect(checkbox()).toMatchObject({ checked: true, disabled: true });
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['user']);
	});
});

describe('server-provided transitive and shared descendants', () => {
	const graphRoles: AssignableProjectRole[] = [
		{ id: 'parent-a', name: 'lumen_admin', area: 'lumen', grade: 'admin', implied_role_ids: ['middle'], inherited_role_ids: ['middle', 'leaf'] },
		{ id: 'parent-b', name: 'lumen_user', area: 'lumen', grade: 'user', implied_role_ids: ['middle'], inherited_role_ids: ['middle', 'leaf'] },
		{ id: 'middle', name: 'lumen_reader', area: 'lumen', grade: 'reader', implied_role_ids: ['leaf'], inherited_role_ids: ['leaf'] },
		{ id: 'leaf', name: 'lumen-history_reader', area: 'lumen', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] },
		{ id: 'external', name: 'waygate_reader', area: 'waygate', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] },
	];
	const graphMember: ProjectAccessMember = {
		...member, source: 'mixed', roles: graphRoles.map(role => role.name),
		direct_role_ids: ['parent-a', 'parent-b'], effective_role_ids: ['parent-a', 'parent-b', 'middle', 'leaf', 'external'], external_role_ids: ['external'],
	};
	const checkbox = (name: RegExp) => screen.getByRole('checkbox', { name }) as HTMLInputElement;
	it('recomputes shared transitive leaves and retains external inheritance when parents are removed', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: graphMember, roles: graphRoles, busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox(/^lumen-history_reader/).checked).toBe(true);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(true);
		await fireEvent.click(checkbox(/^lumen_admin/));
		expect(checkbox(/^lumen-history_reader/).checked).toBe(true);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(true);
		await fireEvent.click(checkbox(/^lumen_user/));
		expect(checkbox(/^lumen_reader/).checked).toBe(false);
		expect(checkbox(/^lumen-history_reader/).checked).toBe(false);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(false);
		await chooseArea('waygate');
		expect(checkbox(/^waygate_reader/).checked).toBe(true);
		expect(checkbox(/^waygate_reader/).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith([]);
	});

	it('keeps externally inherited descendants checked after removing an overlapping direct parent', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: ['parent-a'], effective_role_ids: ['parent-a', 'middle', 'leaf'], external_role_ids: ['middle', 'leaf'] }, roles: graphRoles, busy: false, error: '', onSave, onClose: vi.fn() });
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
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: ['parent-a', 'leaf'], effective_role_ids: ['parent-a', 'middle', 'leaf', 'external'] }, roles: graphRoles, busy: false, error: '', onSave, onClose: vi.fn() });
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
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: [], effective_role_ids: [], external_role_ids: [] }, roles: catalog, busy: false, error: '', onSave, onClose: vi.fn() });
		await fireEvent.click(checkbox(/^lumen_admin/));
		expect(checkbox(/^lumen_reader/).checked).toBe(false);
		expect(checkbox(/^lumen-history_reader/).checked).toBe(false);
		expect(checkbox(/^lumen-history_reader/).disabled).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['parent-a']);
	});
});
