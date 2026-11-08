import { ApiError } from '$lib/api/errors';
import type { AdminDomain } from '$lib/api/domains';
import type { ManagedRole } from '$lib/components/admin/roles/types';
import { isRetiredRole } from '$lib/utils/roleCatalog';
import type { MockupProfileId } from './contracts';
import { getMockupState, type MockAdminDomain, type MockAdminRole } from './state';

const ROLES = '/api/v1/admin/roles';
const DOMAINS = '/api/v1/admin/domains';
const CORE_NAMES: Record<string, true> = { admin: true, manager: true, member: true, reader: true };
const SYSTEM_NAMES: Record<string, true> = { admin: true, manager: true };
const isCore = (name: string) => CORE_NAMES[name.toLowerCase()] === true;

// Explicit synthetic admin state for the role and domain administration pages, mirroring
// backend/app/api/identity/admin_identity.py (roles) and backend/app/api/identity/domains.py (domains).
// Roles: list, create and delete. Implication edges, metadata edits and presets stay unsupported.
// Domains: list, create and edit of tutorial-created domains. Seed rows are fixtures: deleting a seed
// role or editing a seed domain returns undefined so the transport answers 409 mockup.unsupported.
// Admin profile only; returns undefined for every path this module does not own.
export function mockAdminRolesDomains(method: string, path: string, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile !== 'admin') return undefined;
	// The backend role catalog ignores query parameters such as domain_id and always returns every role.
	if (path === ROLES && method === 'GET') return roleCatalog();
	if (path === ROLES && method === 'POST') return createRole(body);
	const role = path.match(/^\/api\/v1\/admin\/roles\/([^/]+)$/);
	if (role && method === 'DELETE') return deleteRole(decodeURIComponent(role[1]));
	if (path === DOMAINS && method === 'GET') return listDomains();
	if (path === DOMAINS && method === 'POST') return createDomain(body);
	const domain = path.match(/^\/api\/v1\/admin\/domains\/([^/]+)$/);
	if (domain && method === 'PATCH') return updateDomain(decodeURIComponent(domain[1]), body);
	return undefined;
}

// Derived exactly like identity_roles._catalog: flags come from names, links from implication rows.
function roleCatalog(): ManagedRole[] {
	const rows = getMockupState().adminRoles;
	const byId = new Map(rows.map((row) => [row.id, row]));
	const parents = new Map<string, string[]>(rows.map((row) => [row.id, []]));
	for (const row of rows) for (const child of row.implied_role_ids) parents.get(child)?.push(row.id);
	return rows.map((row) => {
		const descendants = new Set<string>();
		const pending = [...row.implied_role_ids];
		while (pending.length) {
			const child = pending.pop()!;
			if (descendants.has(child)) continue;
			descendants.add(child);
			pending.push(...(byId.get(child)?.implied_role_ids ?? []));
		}
		const name = row.name.toLowerCase();
		const retired = isRetiredRole({ name: row.name });
		return {
			id: row.id,
			name: row.name,
			description: row.description,
			domain_id: row.domain_id,
			protected: isCore(name) || name === 'project_owner',
			system_only: [row.id, ...descendants].some((id) => SYSTEM_NAMES[byId.get(id)?.name.toLowerCase() ?? ''] === true),
			retired,
			assignable: !retired && name !== 'admin',
			implied_role_ids: [...row.implied_role_ids].sort(),
			inherited_role_ids: [...descendants].sort(),
			parent_role_ids: [...(parents.get(row.id) ?? [])].sort(),
		};
	});
}

// service_permissions.normalize_role_name: core names fold to lower case, custom names are area_grade.
function normalizeRoleName(value: string): string {
	if (isCore(value)) return value.toLowerCase();
	const parts = value.split('_');
	if (parts.length !== 2) throw new ApiError(422, 'Role names must use the area_grade format.');
	const normalized = parts.map((part) => part.replace(/\s+/g, '-').toLowerCase());
	if (normalized.some((part) => !/^[a-z0-9-]+$/.test(part) || !/[a-z0-9]/.test(part))) {
		throw new ApiError(422, 'Area and grade may contain only letters, digits and hyphens.');
	}
	const result = normalized.join('_');
	if (result.length > 255) throw new ApiError(422, 'Role name exceeds 255 characters.');
	if (isRetiredRole({ name: result })) throw new ApiError(422, 'Retired service roles are not assignable; use standard project roles.');
	return result;
}

function createRole(body: unknown): ManagedRole {
	const state = getMockupState();
	const payload = (body ?? {}) as Record<string, unknown>;
	if (Object.keys(payload).some((key) => !['name', 'description', 'domain_id'].includes(key))) throw new ApiError(422, 'Unexpected role field.');
	const rawName = typeof payload.name === 'string' ? payload.name.trim() : '';
	const description = payload.description === undefined ? '' : payload.description;
	const domainId = payload.domain_id ?? null;
	if (!rawName || rawName.length > 255 || typeof description !== 'string' || description.length > 4096) throw new ApiError(422, 'Invalid role metadata.');
	if (domainId !== null && (typeof domainId !== 'string' || !domainId.trim() || domainId.length > 255)) throw new ApiError(422, 'Invalid role domain.');
	const name = normalizeRoleName(rawName);
	const domain = typeof domainId === 'string' ? domainId.trim() : null;
	if (isCore(name)) throw new ApiError(409, 'Reserved core role name');
	if (state.adminRoles.some((row) => row.domain_id === domain && row.name.toLowerCase() === name)) throw new ApiError(409, 'Role name already exists');
	// Keystone refuses a role in an unknown domain; the backend reports it as a rejected role operation.
	if (domain !== null && !state.adminDomains.some((row) => row.id === domain)) throw new ApiError(404, 'Keystone role operation rejected');
	let n = 1;
	while (state.adminRoles.some((row) => row.id === `mock-custom-role-${n}`)) n += 1;
	const created: MockAdminRole = { id: `mock-custom-role-${n}`, name, description: description.trim(), domain_id: domain, implied_role_ids: [], seed: false };
	state.adminRoles.push(created);
	return roleCatalog().find((row) => row.id === created.id)!;
}

function deleteRole(id: string): { status: 'deleted' } | undefined {
	const state = getMockupState();
	const row = roleCatalog().find((item) => item.id === id);
	if (!row) throw new ApiError(404, 'Role not found');
	if (row.protected || row.implied_role_ids.length || row.parent_role_ids.length) throw new ApiError(409, 'Protected or connected roles cannot be deleted');
	// Seed roles stand for catalog entries whose assignments this fixture does not model.
	if (state.adminRoles.find((item) => item.id === id)?.seed) return undefined;
	state.adminRoles = state.adminRoles.filter((item) => item.id !== id);
	return { status: 'deleted' };
}

function publicDomain(row: MockAdminDomain): AdminDomain {
	const { seed: _seed, ...domain } = row;
	return structuredClone(domain);
}

// domains.list_domains sorts by display name, then id.
function listDomains(): { items: AdminDomain[] } {
	const rows = [...getMockupState().adminDomains].sort((a, b) => (a.name === b.name ? (a.id < b.id ? -1 : 1) : a.name < b.name ? -1 : 1));
	return { items: rows.map(publicDomain) };
}

function domainFields(body: unknown, partial: boolean): { name?: string; description?: string; enabled?: boolean } {
	const payload = (body ?? {}) as Record<string, unknown>;
	if (Object.keys(payload).some((key) => !['name', 'description', 'enabled'].includes(key))) throw new ApiError(422, 'domain_invalid_input');
	const fields: { name?: string; description?: string; enabled?: boolean } = {};
	if (payload.name !== undefined && payload.name !== null) {
		const name = typeof payload.name === 'string' ? payload.name.trim() : '';
		if (!name || name.length > 64) throw new ApiError(422, 'domain_invalid_input');
		fields.name = name;
	} else if (!partial) throw new ApiError(422, 'domain_invalid_input');
	if (payload.description !== undefined && payload.description !== null) {
		if (typeof payload.description !== 'string' || payload.description.trim().length > 4096) throw new ApiError(422, 'domain_invalid_input');
		fields.description = payload.description.trim();
	}
	if (payload.enabled !== undefined && payload.enabled !== null) {
		if (typeof payload.enabled !== 'boolean') throw new ApiError(422, 'domain_invalid_input');
		fields.enabled = payload.enabled;
	}
	return fields;
}

// domain_projects.create_domain returns the new organization; display names need not be unique.
function createDomain(body: unknown): AdminDomain {
	const state = getMockupState();
	const fields = domainFields(body, false);
	let n = 1;
	while (state.adminDomains.some((row) => row.id === `mock-org-domain-${n}`)) n += 1;
	const created: MockAdminDomain = { id: `mock-org-domain-${n}`, name: fields.name!, description: fields.description ?? '', enabled: fields.enabled ?? true, kind: 'organization', seed: false };
	state.adminDomains.push(created);
	return publicDomain(created);
}

function updateDomain(id: string, body: unknown): AdminDomain | undefined {
	const row = getMockupState().adminDomains.find((item) => item.id === id);
	if (!row) throw new ApiError(404, 'domain_not_found');
	const fields = domainFields(body, true);
	if (!Object.keys(fields).length) throw new ApiError(422, 'domain_invalid_input');
	// The seed domain holds the tutorial administrator and its fixtures; disabling or renaming it is not modelled.
	if (row.seed) return undefined;
	Object.assign(row, fields);
	return publicDomain(row);
}
