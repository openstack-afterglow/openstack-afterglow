import { ApiError } from '$lib/api/errors';
import { t } from '$lib/i18n/ns/tutorial';
import type { DomainAccountResult } from '$lib/types/auth';
import type { User } from '$lib/types/common';
import type { MockupProfileId } from './contracts';
import { getMockupState } from './state';

const DOMAIN = { id: 'mock-domain', name: 'Demo' };
const ACTOR_ID = 'mock-admin-1';
const CREATE = '/api/v1/admin/users';
const FIELDS: Record<string, true> = { domain_id: true, name: true, email: true, password: true, enabled: true };

// Explicit synthetic admin state for the user administration page: create and delete.
// Listing, stats and activity stay in transport.ts and read state.admin.users, where created users are added.
// The synthetic Demo domain is also the accounts identity domain, so a created user is listed there.
// Passwords are validated and never stored or echoed. Only users created here are deletable.
// Admin profile only; returns undefined for every path this module does not own.
export function mockAdminUsers(method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile !== 'admin') return undefined;
	if (path === CREATE && method === 'POST') return createUser(body);
	const item = path.match(/^\/api\/v1\/admin\/users\/([^/]+)$/);
	if (item && method === 'DELETE') return deleteUser(decodeURIComponent(item[1]), params);
	return undefined;
}

function text(value: unknown, min: number, max: number): value is string {
	return typeof value === 'string' && value.length >= min && value.length <= max;
}

function createUser(body: unknown): DomainAccountResult & Record<string, unknown> {
	const payload = (body ?? {}) as Record<string, unknown>;
	// CreateUserRequest forbids extra fields and enforces the same length bounds.
	if (Object.keys(payload).some((key) => !Object.hasOwn(FIELDS, key)) || !text(payload.name, 1, 255) || !text(payload.email, 3, 255)
		|| !text(payload.password, 12, 1024) || !text(payload.domain_id, 1, Infinity) || (payload.enabled !== undefined && typeof payload.enabled !== 'boolean')) {
		throw new ApiError(422, 'Invalid user request');
	}
	if (payload.domain_id !== DOMAIN.id) throw new ApiError(404, 'Domain not found');
	const email = payload.email.trim();
	const [local, host, ...rest] = email.split('@');
	if (rest.length || !local || !host || /\s/.test(email) || !/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(host)) throw new ApiError(403, 'Email address is invalid');
	const canonical = `${local}@${host.toLowerCase()}`;
	const state = getMockupState();
	if (state.admin.users.some((user) => user.email.toLowerCase() === canonical.toLowerCase())) throw new ApiError(409, 'Email belongs to another account');
	if (state.admin.users.some((user) => user.name === payload.name)) throw new ApiError(409, 'User name already exists');
	// A distinct prefix keeps created IDs from colliding with seed references such as group members.
	let n = state.adminCreatedUserIds.length + 1;
	while (state.admin.users.some((user) => user.id === `mock-tut-user-${n}`)) n += 1;
	const id = `mock-tut-user-${n}`;
	const enabled = payload.enabled !== false;
	// Activity bounds are empty until the new user acts, and the personal project waits for the first sign-in.
	const created: User = { id, name: payload.name, email: canonical, enabled, domain_id: DOMAIN.id, default_project_id: null, created_at: null, first_seen: null, last_seen: null };
	state.admin.users.push(created);
	state.adminCreatedUserIds.push(id);
	return {
		id, name: payload.name, email: canonical, enabled, protected: true,
		user_id: id, domain_id: DOMAIN.id, domain_name: DOMAIN.name,
		personal_project_id: null, personal_project_name: null, personal_domain_id: null, personal_project_deferred: true,
		identity_domain_id: DOMAIN.id, identity_domain_name: DOMAIN.name,
	};
}

function deleteUser(id: string, params: URLSearchParams): Record<string, never> {
	const domain = params.get('domain_id');
	if (!domain) throw new ApiError(422, 'Select a domain');
	if (domain !== DOMAIN.id) throw new ApiError(404, 'Domain not found');
	const state = getMockupState();
	if (!state.admin.users.some((user) => user.id === id && user.domain_id === domain)) throw new ApiError(404, 'identity_not_found');
	if (id === ACTOR_ID) throw new ApiError(409, 'identity_self_delete_forbidden');
	// Seed accounts are never deleted by a tutorial.
	if (!state.adminCreatedUserIds.includes(id)) throw new ApiError(409, t('mockup.unsupported'));
	state.admin.users = state.admin.users.filter((user) => user.id !== id);
	state.adminCreatedUserIds = state.adminCreatedUserIds.filter((entry) => entry !== id);
	return {};
}
