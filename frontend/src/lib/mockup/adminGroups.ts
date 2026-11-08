import { ApiError } from '$lib/api/errors';
import type { Group, GroupMember } from '$lib/types/adminGroup';
import type { MockupProfileId } from './contracts';
import { getMockupState, type MockAdminGroup } from './state';

const DOMAIN_ID = 'mock-domain';
const ROOT = '/api/v1/admin/groups';
// The synthetic clock shared with the other administrator fixtures.
const NOW = '2026-07-09T00:00:00Z';

// Explicit synthetic admin state for the identity groups page: list, create, delete and read members,
// mirroring backend/app/api/identity/admin_identity.py. Seed groups are fixtures and cannot be deleted
// (the transport answers 409 mockup.unsupported); membership writes and candidates stay unsupported.
// Admin profile only; returns undefined for every path this module does not own.
export function mockAdminGroups(method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile !== 'admin') return undefined;
	if (path === ROOT && method === 'GET') return listGroups(selectedDomain(params.get('domain_id')));
	if (path === ROOT && method === 'POST') return createGroup(body);
	const item = path.match(/^\/api\/v1\/admin\/groups\/([^/]+)$/);
	if (item && method === 'DELETE') return deleteGroup(decodeURIComponent(item[1]), params);
	const users = path.match(/^\/api\/v1\/admin\/groups\/([^/]+)\/users$/);
	if (users && method === 'GET') return listMembers(decodeURIComponent(users[1]), params);
	return undefined;
}

// FastAPI rejects a missing or empty domain_id; an unknown domain is identity_domain_not_found.
function selectedDomain(value: unknown): string {
	if (typeof value !== 'string' || !value) throw new ApiError(422, 'domain_id is required.');
	if (value !== DOMAIN_ID) throw new ApiError(404, 'identity_domain_not_found');
	return value;
}

function publicGroup({ id, name, description, domain_id, created_at }: MockAdminGroup): Group {
	return { id, name, description, domain_id, created_at };
}

// Newest verified creation date first, like the backend listing.
function listGroups(domainId: string): Group[] {
	return getMockupState().adminGroups
		.filter((group) => group.domain_id === domainId)
		.sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
		.map(publicGroup);
}

function findGroup(id: string, params: URLSearchParams): MockAdminGroup {
	const domainId = selectedDomain(params.get('domain_id'));
	const group = getMockupState().adminGroups.find((item) => item.id === id && item.domain_id === domainId);
	if (!group) throw new ApiError(404, 'identity_not_found');
	return group;
}

function createGroup(body: unknown): Omit<Group, 'created_at'> {
	const state = getMockupState();
	const payload = (body ?? {}) as { name?: unknown; description?: unknown; domain_id?: unknown };
	if (typeof payload.name !== 'string') throw new ApiError(422, 'name is required.');
	const domainId = selectedDomain(payload.domain_id);
	// Keystone refuses an empty or duplicate group name in one domain; the backend reports both generically.
	if (!payload.name.trim()) throw new ApiError(400, 'identity_native_invalid');
	if (state.adminGroups.some((group) => group.domain_id === domainId && group.name === payload.name)) throw new ApiError(409, 'identity_native_invalid');
	let n = 1;
	while (state.adminGroups.some((group) => group.id === `mock-created-group-${n}`)) n += 1;
	const created: MockAdminGroup = {
		id: `mock-created-group-${n}`,
		name: payload.name,
		description: typeof payload.description === 'string' ? payload.description : '',
		domain_id: domainId,
		created_at: NOW,
		member_ids: [],
		seed: false,
	};
	// Prepended so a group created at the shared synthetic instant still lists first.
	state.adminGroups.unshift(created);
	return { id: created.id, name: created.name, description: created.description, domain_id: created.domain_id };
}

function deleteGroup(id: string, params: URLSearchParams): Record<string, never> | undefined {
	const group = findGroup(id, params);
	if (group.seed) return undefined;
	const state = getMockupState();
	state.adminGroups = state.adminGroups.filter((item) => item.id !== id);
	return {};
}

function listMembers(id: string, params: URLSearchParams): GroupMember[] {
	const group = findGroup(id, params);
	return getMockupState().admin.users
		.filter((user) => group.member_ids.includes(user.id))
		.map((user) => ({
			id: user.id,
			name: user.name ?? '',
			email: user.email ?? '',
			enabled: user.enabled ?? true,
			domain_id: user.domain_id ?? null,
			identity_read_only: user.domain_id !== group.domain_id,
		}));
}
