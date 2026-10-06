import { t } from '$lib/i18n/ns/admin-identity';
import type { ManagedRole, RoleSort, SortDirection } from './types';

const collator = new Intl.Collator('ko', { numeric: true, sensitivity: 'base' });
const coreRank: Record<string, number | undefined> = { admin: 0, manager: 1, member: 2, reader: 3 };

function privilegeRank(name: string): number | undefined {
	const normalized = name.toLowerCase();
	return Object.hasOwn(coreRank, normalized) ? coreRank[normalized] : undefined;
}

export function matchesRole(role: ManagedRole, query: string): boolean {
	const term = query.trim().toLocaleLowerCase();
	return !term || [role.name, role.id, role.description].some((value) => value.toLocaleLowerCase().includes(term));
}

export function sortRoles(roles: readonly ManagedRole[], key: RoleSort, direction: SortDirection): ManagedRole[] {
	const sign = direction === 'asc' ? 1 : -1;
	return [...roles].sort((a, b) => {
		const comparison = key === 'inheritance'
			? a.inherited_role_ids.length - b.inherited_role_ids.length
			: collator.compare(a[key], b[key]);
		// ID tie-break keeps equal/case-folded names stable across provider reordering.
		return comparison * sign || collator.compare(a.id, b.id) || a.id.localeCompare(b.id);
	});
}

export interface RoleGraph {
	byId: Map<string, ManagedRole>;
	parents: Map<string, Set<string>>;
	reachable: (start: string, upwards?: boolean) => Set<string>;
}

export function buildRoleGraph(roles: readonly ManagedRole[]): RoleGraph {
	const byId = new Map(roles.map((role) => [role.id, role]));
	const parents = new Map(roles.map((role) => [role.id, new Set(role.parent_role_ids)]));
	for (const role of roles) {
		for (const id of role.implied_role_ids) parents.get(id)?.add(role.id);
	}
	function reachable(start: string, upwards = false): Set<string> {
		const result = new Set<string>();
		const pending = [start];
		while (pending.length) {
			const id = pending.pop()!;
			if (result.has(id)) continue;
			result.add(id);
			pending.push(...(upwards ? parents.get(id) ?? [] : byId.get(id)?.implied_role_ids ?? []));
		}
		return result;
	}
	return { byId, parents, reachable };
}


export function edgeDisabledReason(graph: RoleGraph, prior: ManagedRole, candidate: ManagedRole): string | null {
	// Existing unsafe edges must remain removable; only creation is constrained here.
	if (prior.implied_role_ids.includes(candidate.id)) return null;
	if (prior.id === candidate.id) return t('roleValidation.selfInheritance');
	if (candidate.domain_id !== null && prior.domain_id !== candidate.domain_id) return t('roleValidation.crossDomain');
	const descendants = graph.reachable(candidate.id);
	// Include server transitive metadata as a conservative privilege boundary.
	for (const id of candidate.inherited_role_ids) descendants.add(id);
	if (descendants.has(prior.id)) return t('roleValidation.cycle');
	const targets = [...descendants].map((id) => graph.byId.get(id));
	if (targets.some((role) => !role)) return t('roleValidation.missingInherited');
	const targetRanks = targets.flatMap((role) => {
		const rank = privilegeRank(role!.name);
		return rank === undefined ? [] : [rank];
	});
	const priorRank = privilegeRank(prior.name);
	if (priorRank === undefined && (candidate.system_only || targets.some((role) => role!.system_only) || targetRanks.some((rank) => rank < 2))) {
		return t('roleValidation.customSystemOnly');
	}
	for (const id of graph.reachable(prior.id, true)) {
		const ancestor = graph.byId.get(id);
		if (!ancestor) return t('roleValidation.missingAncestor');
		const rank = privilegeRank(ancestor.name);
		if (rank !== undefined && targetRanks.some((targetRank) => targetRank < rank)) {
			return t('roleValidation.higherPrivilege', { name: ancestor.name });
		}
		if (rank !== undefined && rank >= 2 && targets.some((role) => role!.system_only)) {
			return t('roleValidation.ancestorSystemOnly', { name: ancestor.name });
		}
	}
	return null;
}

export function deleteDisabledReason(role: ManagedRole): string | null {
	if (role.protected) return t('roleValidation.protectedDeletion');
	if (role.parent_role_ids.length || role.implied_role_ids.length) return t('roleValidation.linkedDeletion');
	return null;
}

export interface RoleTreeRow {
	key: string;
	role: ManagedRole;
	parent: ManagedRole | null;
	depth: number;
	kind: 'root' | 'edge' | 'shared' | 'cycle' | 'component';
	matches: boolean;
}

/** Expand each role once; shared children still appear under every direct parent. */
export function roleTreeRows(roles: readonly ManagedRole[], query: string, key: RoleSort, direction: SortDirection): RoleTreeRow[] {
	const ordered = sortRoles(roles, key, direction);
	const graph = buildRoleGraph(ordered);
	const visible = new Set<string>();
	for (const role of ordered) {
		if (matchesRole(role, query)) for (const id of graph.reachable(role.id, true)) visible.add(id);
	}
	const position = new Map(ordered.map((role, index) => [role.id, index]));
	const expanded = new Set<string>();
	const rows: RoleTreeRow[] = [];
	function walk(root: ManagedRole, rootless = false) {
		const stack: { role: ManagedRole; parent: ManagedRole | null; depth: number; path: Set<string> }[] = [
			{ role: root, parent: null, depth: 0, path: new Set() }
		];
		while (stack.length) {
			const { role, parent, depth, path } = stack.pop()!;
			if (!visible.has(role.id)) continue;
			const cycle = path.has(role.id);
			const shared = expanded.has(role.id);
			rows.push({ key: parent ? `${parent.id}->${role.id}` : `root:${role.id}`, role, parent, depth,
				kind: cycle ? 'cycle' : shared ? 'shared' : parent ? 'edge' : rootless ? 'component' : 'root', matches: matchesRole(role, query) });
			if (cycle || shared) continue;
			expanded.add(role.id);
			const nextPath = new Set(path).add(role.id);
			const children = [...new Set(role.implied_role_ids)].flatMap((id) => graph.byId.get(id) ? [graph.byId.get(id)!] : [])
				.sort((a, b) => position.get(a.id)! - position.get(b.id)!);
			for (const child of children.reverse()) stack.push({ role: child, parent: role, depth: depth + 1, path: nextPath });
		}
	}
	for (const role of ordered) if (!graph.parents.get(role.id)?.size) walk(role);
	// Components consisting only of cycles have no roots, but must not disappear.
	for (const role of ordered) if (visible.has(role.id) && !expanded.has(role.id)) walk(role, true);
	return rows;
}
