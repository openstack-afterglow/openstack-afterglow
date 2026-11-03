import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import ProjectMemberRolesModal from '../ProjectMemberRolesModal.svelte';
import type { AssignableProjectRole, ProjectAccessMember } from '$lib/types/project';
const member: ProjectAccessMember = { user_id: 'u', username: 'User', email: '', source: 'direct', is_owner: false, is_manager: true, roles: ['project_admin', 'research_user', 'research-chat_user'], direct_role_ids: ['admin', 'user'], direct_roles: [], effective_role_ids: ['admin', 'user', 'chat'], external_role_ids: [] };
const roles: AssignableProjectRole[] = [
	{ id: 'admin', name: 'project_admin', area: 'project', grade: 'admin', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'user', name: 'research_user', area: 'research', grade: 'user', implied_role_ids: ['chat'], inherited_role_ids: ['chat'] },
	{ id: 'chat', name: 'research-chat_user', area: 'research', grade: 'user', implied_role_ids: [], inherited_role_ids: [] },
	{ id: 'images', name: 'research-images_user', description: 'Visual asset generation', area: 'research', grade: 'user', implied_role_ids: [], inherited_role_ids: [] },
];
afterEach(cleanup);
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
		expect((screen.getByRole('checkbox', { name: /^research_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^research-chat_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^research-chat_user/ }) as HTMLInputElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('checkbox', { name: /^research-images_user/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['admin', 'user', 'images']);
	});
	it('offers only the server-grantable roles without exposing project admin to nonowners', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles: roles.filter(role => role.name !== 'project_admin'), busy: false, error: '', onSave, onClose: vi.fn() });
		expect(screen.queryByRole('checkbox', { name: /^project_admin/ })).toBeNull();
		expect((screen.getByRole('checkbox', { name: /^research-images_user/ }) as HTMLInputElement).disabled).toBe(false);
	});
	it('filters case-insensitive descriptions and IDs without losing hidden direct selections', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member, roles, busy: false, error: '', onSave, onClose: vi.fn() });
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: 'vISUAL' } });
		expect(screen.queryByRole('checkbox', { name: /^project_admin/ })).toBeNull();
		await fireEvent.click(screen.getByRole('checkbox', { name: /^research-images_user/ }));
		await fireEvent.input(search, { target: { value: 'no-such-role' } });
		expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
		await fireEvent.input(search, { target: { value: 'USER' } });
		expect((screen.getByRole('checkbox', { name: /^research_user/ }) as HTMLInputElement).checked).toBe(true);
		expect((screen.getByRole('checkbox', { name: /^research-chat_user/ }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['admin', 'user', 'images']);
	});
	it('preserves hidden direct and legacy grants across searches while keeping custom service-prefix roles selectable', async () => {
		const onSave = vi.fn();
		const catalog: AssignableProjectRole[] = [...roles, { id: 'opaque-id', name: 'lumen-looking', area: 'custom-area', grade: null, implied_role_ids: [], inherited_role_ids: [] }];
		render(ProjectMemberRolesModal, { member: { ...member, direct_role_ids: ['admin', 'user', 'legacy-id'] }, roles: catalog, busy: false, error: '', onSave, onClose: vi.fn() });
		await fireEvent.click(screen.getByRole('checkbox', { name: /^lumen-looking/ }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /^project_admin/ }));
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: 'OPAQUE-ID' } });
		expect((screen.getByRole('checkbox', { name: /^lumen-looking/ }) as HTMLInputElement).checked).toBe(true);
		expect(screen.queryByRole('checkbox', { name: /^project_admin/ })).toBeNull();
		await fireEvent.input(search, { target: { value: 'user' } });
		expect((screen.getByRole('checkbox', { name: /^research_user/ }) as HTMLInputElement).checked).toBe(true);
		await fireEvent.input(search, { target: { value: '' } });
		expect((screen.getByRole('checkbox', { name: /^project_admin/ }) as HTMLInputElement).checked).toBe(false);
		expect(screen.queryByRole('checkbox', { name: /^lumen-looking/ })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['user', 'legacy-id', 'opaque-id']);
	});
	it.each(['group', 'inherited'] as const)('does not offer direct mutation for %s-only membership', async (source) => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...member, source, direct_role_ids: [], external_role_ids: member.effective_role_ids }, roles, busy: false, error: '', onSave, onClose: vi.fn() });
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

describe('native admin excluded from role choices', () => {
	const nativeRole: AssignableProjectRole = { id: 'native-admin-id', name: 'admin', area: 'legacy', grade: 'admin', implied_role_ids: ['chat'], inherited_role_ids: ['chat'] };
	const customAdmin: AssignableProjectRole = { id: 'custom-admin-id', name: 'research_admin', area: 'research', grade: 'admin', implied_role_ids: [], inherited_role_ids: [] };
	it.each(['admin', 'ADMIN'])('omits %s from choices and search without blocking project/custom admin', async (name) => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...member, direct_role_ids: ['user', 'legacy-id'] }, roles: [{ ...nativeRole, name }, ...roles, customAdmin], busy: false, error: '', onSave, onClose: vi.fn() });
		expect(screen.queryByRole('checkbox', { name: /^admin\b/i })).toBeNull();
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'admin' } });
		expect(screen.queryByRole('checkbox', { name: /^admin\b/i })).toBeNull();
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '' } });
		await fireEvent.click(screen.getByRole('checkbox', { name: /^project_admin/ }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /^research_admin/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['user', 'legacy-id', 'admin', 'custom-admin-id']);
	});
	it.each([true, false])('preserves an existing hidden direct admin while editing other roles (catalog includes admin: %s)', async (includeAdmin) => {
		const onSave = vi.fn();
		const direct = ['native-admin-id', 'admin', 'legacy-id'];
		render(ProjectMemberRolesModal, { member: { ...member, direct_role_ids: direct }, roles: [...(includeAdmin ? [nativeRole] : []), ...roles], busy: false, error: '', onSave, onClose: vi.fn() });
		expect(screen.queryByRole('checkbox', { name: /^admin\b/i })).toBeNull();
		await fireEvent.click(screen.getByRole('checkbox', { name: /^research-images_user/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith([...direct, 'images']);
	});
	it('keeps hidden admin descendants checked after removing an overlapping editable parent', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...member, direct_role_ids: ['native-admin-id', 'user'], direct_roles: [{ id: 'native-admin-id', name: 'admin', inherited_role_ids: ['chat'] }], external_role_ids: [] }, roles, busy: false, error: '', onSave, onClose: vi.fn() });
		await fireEvent.click(screen.getByRole('checkbox', { name: /^research_user/ }));
		expect(screen.getByRole('checkbox', { name: /^research-chat_user/ })).toMatchObject({ checked: true, disabled: true });
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['native-admin-id']);
	});
	it.each(['group', 'inherited', 'mixed'] as const)('never copies %s external admin into direct grants', async (source) => {
		const onSave = vi.fn();
		const direct = source === 'mixed' ? ['user'] : [];
		render(ProjectMemberRolesModal, { member: { ...member, source, direct_role_ids: direct, external_role_ids: ['native-admin-id'] }, roles: [nativeRole, ...roles], busy: false, error: '', onSave, onClose: vi.fn() });
		expect(screen.queryByRole('checkbox', { name: /^admin\b/i })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		if (source === 'mixed') expect(onSave).toHaveBeenCalledWith(direct);
		else expect(onSave).not.toHaveBeenCalled();
	});
});

describe('server-provided transitive and shared descendants', () => {
	const graphRoles: AssignableProjectRole[] = [
		{ id: 'parent-a', name: 'research_admin', area: 'research', grade: 'admin', implied_role_ids: ['middle'], inherited_role_ids: ['middle', 'leaf'] },
		{ id: 'parent-b', name: 'research_user', area: 'research', grade: 'user', implied_role_ids: ['middle'], inherited_role_ids: ['middle', 'leaf'] },
		{ id: 'middle', name: 'research_reader', area: 'research', grade: 'reader', implied_role_ids: ['leaf'], inherited_role_ids: ['leaf'] },
		{ id: 'leaf', name: 'research-history_reader', area: 'research', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] },
		{ id: 'external', name: 'external_reader', area: 'external', grade: 'reader', implied_role_ids: [], inherited_role_ids: [] },
	];
	const graphMember: ProjectAccessMember = {
		...member, source: 'mixed', roles: graphRoles.map(role => role.name),
		direct_role_ids: ['parent-a', 'parent-b'], effective_role_ids: ['parent-a', 'parent-b', 'middle', 'leaf', 'external'], external_role_ids: ['external'],
	};
	const checkbox = (name: RegExp) => screen.getByRole('checkbox', { name }) as HTMLInputElement;
	it('recomputes shared transitive leaves and retains external inheritance when parents are removed', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: graphMember, roles: graphRoles, busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox(/^research-history_reader/).checked).toBe(true);
		expect(checkbox(/^research-history_reader/).disabled).toBe(true);
		await fireEvent.click(checkbox(/^research_admin/));
		expect(checkbox(/^research-history_reader/).checked).toBe(true);
		expect(checkbox(/^research-history_reader/).disabled).toBe(true);
		await fireEvent.click(checkbox(/^research_user/));
		expect(checkbox(/^research_reader/).checked).toBe(false);
		expect(checkbox(/^research-history_reader/).checked).toBe(false);
		expect(checkbox(/^research-history_reader/).disabled).toBe(false);
		expect(checkbox(/^external_reader/).checked).toBe(true);
		expect(checkbox(/^external_reader/).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith([]);
	});

	it('keeps externally inherited descendants checked after removing an overlapping direct parent', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: ['parent-a'], effective_role_ids: ['parent-a', 'middle', 'leaf'], external_role_ids: ['middle', 'leaf'] }, roles: graphRoles, busy: false, error: '', onSave, onClose: vi.fn() });
		await fireEvent.click(checkbox(/^research_admin/));
		expect(checkbox(/^research_reader/).checked).toBe(true);
		expect(checkbox(/^research_reader/).disabled).toBe(true);
		expect(checkbox(/^research-history_reader/).checked).toBe(true);
		expect(checkbox(/^research-history_reader/).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith([]);
	});
	it('preserves an explicitly direct child after its implying parent is deselected', async () => {
		const onSave = vi.fn();
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: ['parent-a', 'leaf'], effective_role_ids: ['parent-a', 'middle', 'leaf', 'external'] }, roles: graphRoles, busy: false, error: '', onSave, onClose: vi.fn() });
		expect(checkbox(/^research-history_reader/).disabled).toBe(true);
		await fireEvent.click(checkbox(/^research_admin/));
		expect(checkbox(/^research-history_reader/).checked).toBe(true);
		expect(checkbox(/^research-history_reader/).disabled).toBe(false);
		expect(checkbox(/^research_reader/).checked).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['leaf']);
	});
	it('checks only descendants in the current role-ID graph, not similar role names or grades', async () => {
		const onSave = vi.fn();
		const catalog = graphRoles.map(role => role.id === 'parent-a' ? { ...role, implied_role_ids: [], inherited_role_ids: [] } : role);
		render(ProjectMemberRolesModal, { member: { ...graphMember, direct_role_ids: [], effective_role_ids: [], external_role_ids: [] }, roles: catalog, busy: false, error: '', onSave, onClose: vi.fn() });
		await fireEvent.click(checkbox(/^research_admin/));
		expect(checkbox(/^research_reader/).checked).toBe(false);
		expect(checkbox(/^research-history_reader/).checked).toBe(false);
		expect(checkbox(/^research-history_reader/).disabled).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['parent-a']);
	});
});

describe('retired service assignment preservation', () => {
	it('omits retired and nonassignable choices while saving existing direct IDs and a legitimate custom service-prefix role', async () => {
		const onSave = vi.fn();
		const catalog: AssignableProjectRole[] = [
			...roles,
			{ ...roles[0], id: 'retired', name: 'lumen_user', retired: false, assignable: true },
			{ ...roles[0], id: 'flag-retired', name: 'operator_old', retired: true },
			{ ...roles[0], id: 'not-assignable', name: 'operator_hidden', assignable: false },
			{ ...roles[0], id: 'custom', name: 'lumen-custom_admin' },
			{ ...roles[0], id: 'native-member', name: 'member', area: null, grade: null },
			{ ...roles[0], id: 'native-reader', name: 'reader', area: null, grade: null }
		];
		render(ProjectMemberRolesModal, {
			member: { ...member, roles: ['lumen_user'], direct_role_ids: ['retired', 'legacy-unknown'] },
			roles: catalog, busy: false, error: '', onSave, onClose: vi.fn()
		});
		expect(screen.queryByRole('combobox')).toBeNull();
		for (const name of ['lumen_user', 'operator_old', 'operator_hidden']) expect(screen.queryByRole('checkbox', { name: new RegExp(`^${name}`) })).toBeNull();
		await fireEvent.click(screen.getByRole('checkbox', { name: /^lumen-custom_admin/ }));
		await fireEvent.click(screen.getByRole('checkbox', { name: /^member\b/ }));
		await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
		expect(onSave).toHaveBeenCalledWith(['retired', 'legacy-unknown', 'custom', 'native-member']);
	});
});

it('projects the returned standard project-to-native role graph without assigning inherited member or reader IDs', async () => {
	const onSave = vi.fn();
	const catalog: AssignableProjectRole[] = [
		{ ...roles[0], id: 'project-member', name: 'project_member', grade: 'member', implied_role_ids: ['project-reader', 'native-member'], inherited_role_ids: ['project-reader', 'native-member', 'native-reader'] },
		{ ...roles[0], id: 'project-reader', name: 'project_reader', grade: 'reader', implied_role_ids: ['native-reader'], inherited_role_ids: ['native-reader'] },
		{ ...roles[0], id: 'native-member', name: 'member', area: null, grade: null },
		{ ...roles[0], id: 'native-reader', name: 'reader', area: null, grade: null }
	];
	render(ProjectMemberRolesModal, { member: { ...member, direct_role_ids: [], roles: [], effective_role_ids: [] }, roles: catalog, busy: false, error: '', onSave, onClose: vi.fn() });
	await fireEvent.click(screen.getByRole('checkbox', { name: /^project_member/ }));
	for (const name of [/^project_reader/, /^member\b/, /^reader\b/]) expect(screen.getByRole('checkbox', { name })).toMatchObject({ checked: true, disabled: true });
	await fireEvent.click(screen.getByRole('button', { name: '역할 저장' }));
	expect(onSave).toHaveBeenCalledWith(['project-member']);
});
