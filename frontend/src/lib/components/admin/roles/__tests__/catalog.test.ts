import { describe, expect, it } from 'vitest';
import { buildRoleGraph, deleteDisabledReason, edgeDisabledReason, roleTreeRows, sortRoles } from '../catalog';
import type { ManagedRole } from '../types';

function role(id: string, changes: Partial<ManagedRole> = {}): ManagedRole {
	return { id, name: id, description: '', domain_id: null, protected: false, system_only: false,
		implied_role_ids: [], inherited_role_ids: [], parent_role_ids: [], ...changes };
}

describe('role catalog boundaries', () => {
	it('renders every diamond edge while expanding shared descendants only once', () => {
		const roles = [role('root', { implied_role_ids: ['left', 'right'] }),
			role('left', { implied_role_ids: ['shared'] }), role('right', { implied_role_ids: ['shared'] }),
			role('shared', { implied_role_ids: ['leaf'] }), role('leaf'), role('isolated')];
		const rows = roleTreeRows(roles, '', 'name', 'asc');
		expect(rows.filter((row) => row.role.id === 'shared').map((row) => row.parent?.id).sort()).toEqual(['left', 'right']);
		expect(rows.filter((row) => row.role.id === 'shared' && row.kind === 'shared')).toHaveLength(1);
		expect(rows.filter((row) => row.parent?.id === 'shared' && row.role.id === 'leaf')).toHaveLength(1);
		expect(rows.find((row) => row.role.id === 'isolated')?.kind).toBe('root');
		expect(new Set(rows.map((row) => row.key)).size).toBe(rows.length);
	});

	it('keeps both parent paths when searching a shared descendant by description', () => {
		const roles = [role('a', { implied_role_ids: ['c'] }), role('b', { implied_role_ids: ['c'] }),
			role('c', { description: 'needle' }), role('unrelated')];
		const rows = roleTreeRows(roles, 'NEEDLE', 'name', 'desc');
		expect(rows.filter((row) => row.role.id === 'c').map((row) => row.parent?.id).sort()).toEqual(['a', 'b']);
		expect(rows.some((row) => row.role.id === 'unrelated')).toBe(false);
		expect(rows.filter((row) => !row.matches).map((row) => row.role.id).sort()).toEqual(['a', 'b']);
	});

	it('shows rootless cyclic components without recurring forever or hiding isolated nodes', () => {
		const roles = [role('a', { implied_role_ids: ['b'] }), role('b', { implied_role_ids: ['a'] }), role('alone')];
		const rows = roleTreeRows(roles, '', 'name', 'asc');
		expect(rows).toHaveLength(4);
		expect(rows.filter((row) => row.kind === 'cycle')).toHaveLength(1);
		expect(new Set(rows.map((row) => row.role.id))).toEqual(new Set(['a', 'b', 'alone']));
	});

	it('sorts naturally and deterministically without mutating provider order', () => {
		const roles = [role('id10', { name: 'Role 10' }), role('id2', { name: 'role 2' }), role('id1', { name: 'ROLE 2' })];
		expect(sortRoles(roles, 'name', 'asc').map((item) => item.id)).toEqual(['id1', 'id2', 'id10']);
		expect(sortRoles([...roles].reverse(), 'name', 'asc').map((item) => item.id)).toEqual(['id1', 'id2', 'id10']);
		expect(sortRoles(roles, 'name', 'desc').map((item) => item.id)).toEqual(['id10', 'id1', 'id2']);
		expect(sortRoles(roles, 'id', 'desc').map((item) => item.id)).toEqual(['id10', 'id2', 'id1']);
		expect(roles.map((item) => item.id)).toEqual(['id10', 'id2', 'id1']);
	});

	it('orders by effective inheritance count rather than direct edge count', () => {
		const roles = [role('two', { implied_role_ids: ['one'], inherited_role_ids: ['one', 'leaf'] }),
			role('one', { implied_role_ids: ['leaf'], inherited_role_ids: ['leaf'] }), role('leaf')];
		expect(sortRoles(roles, 'inheritance', 'desc').map((item) => item.id)).toEqual(['two', 'one', 'leaf']);
	});

	it('blocks privilege elevation through aliases and through an existing low-privilege ancestor', () => {
		const admin = role('a', { name: 'ADMIN', system_only: true });
		const manager = role('m', { name: 'manager', system_only: true });
		const member = role('u', { name: 'member', implied_role_ids: ['custom'] });
		const reader = role('r', { name: 'reader' });
		const custom = role('custom');
		const alias = role('alias', { implied_role_ids: ['a'], inherited_role_ids: ['a'], system_only: true });
		const memberAlias = role('member-alias', { implied_role_ids: ['u'], inherited_role_ids: ['u'] });
		const roles = [admin, manager, member, reader, custom, alias, memberAlias];
		const graph = buildRoleGraph(roles);
		expect(edgeDisabledReason(graph, manager, alias)).toContain('높은');
		expect(edgeDisabledReason(graph, custom, alias)).toContain('시스템 전용');
		expect(edgeDisabledReason(graph, reader, memberAlias)).toContain('높은');
		expect(edgeDisabledReason(graph, custom, manager)).toBeTruthy();
		expect(edgeDisabledReason(graph, admin, manager)).toBeNull();
		expect(edgeDisabledReason(graph, member, reader)).toBeNull();
		// member -> custom already exists; adding a target that implies manager elevates member.
		const hiddenAlias = role('hidden', { implied_role_ids: ['m'], inherited_role_ids: ['m'] });
		expect(edgeDisabledReason(buildRoleGraph([...roles, hiddenAlias]), custom, hiddenAlias)).toBeTruthy();
	});

	it('allows removing unsafe existing edges while blocking cycles, self and domain mismatches on creation', () => {
		const a = role('a', { implied_role_ids: ['b'] });
		const b = role('b');
		const scoped = role('scoped', { domain_id: 'domain' });
		const graph = buildRoleGraph([a, b, scoped]);
		expect(edgeDisabledReason(graph, a, a)).toContain('자기 자신');
		expect(edgeDisabledReason(graph, b, a)).toContain('순환');
		expect(edgeDisabledReason(graph, a, scoped)).toContain('도메인');
		const transitiveCycle = role('metadata-cycle', { inherited_role_ids: ['a'] });
		expect(edgeDisabledReason(buildRoleGraph([a, b, transitiveCycle]), a, transitiveCycle)).toContain('순환');
		const unsafe = role('reader', { implied_role_ids: ['admin'] });
		const admin = role('admin', { system_only: true });
		expect(edgeDisabledReason(buildRoleGraph([unsafe, admin]), unsafe, admin)).toBeNull();
	});

	it('fails closed when privilege context is incomplete and distinguishes known delete blockers', () => {
		const source = role('source', { parent_role_ids: ['missing-parent'] });
		const target = role('target');
		expect(edgeDisabledReason(buildRoleGraph([source, target]), source, target)).toContain('확인할 수 없습니다');
		const incomplete = role('incomplete', { inherited_role_ids: ['unknown'] });
		expect(edgeDisabledReason(buildRoleGraph([source, incomplete]), source, incomplete)).toContain('확인할 수 없습니다');
		expect(deleteDisabledReason(role('protected', { protected: true }))).toBeTruthy();
		expect(deleteDisabledReason(role('linked', { parent_role_ids: ['source'] }))).toBeTruthy();
		expect(deleteDisabledReason(target)).toBeNull();
	});
});
