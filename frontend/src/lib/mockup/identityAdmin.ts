import { ApiError } from '$lib/api/errors';
import type { ApplicationCredential, ApplicationCredentialIssued, CredentialRole } from '$lib/types/adminCredential';
import type { MockupProfileId } from './contracts';
import { getMockupState } from './state';

const DOMAIN_ID = 'mock-domain';
const ADMIN_USER_ID = 'mock-admin-1';
const ADMIN_PROJECT_ID = 'mock-admin-project';
const DAY_MS = 86_400_000;
// backend MAX_PERSONAL_TOKEN_LIFETIME / default_grant_lifetime / mcp_max_personal_tokens defaults.
const MAX_TOKEN_LIFETIME_MS = 366 * DAY_MS;
const DEFAULT_TOKEN_LIFETIME_MS = 30 * DAY_MS;
const MAX_ACTIVE_PERSONAL_TOKENS = 10;
// Roles carried by the synthetic admin token (admin implies member and reader).
const CONTEXT_ROLES: CredentialRole[] = [
	{ id: 'mock-role-admin', name: 'admin' },
	{ id: 'mock-role-member', name: 'member' },
	{ id: 'mock-role-reader', name: 'reader' },
];
const IDENTIFIER = /^[A-Za-z0-9_.-]{1,128}$/;
const APPLICATION_FIELDS = ['name', 'description', 'role_ids', 'expires_at'];
const CREDENTIALS = '/api/v1/admin/application-credentials';
const TOKENS = '/api/v1/auth/mcp-tokens';

type PersonalToken = ReturnType<typeof getMockupState>['mcpAccess']['personalTokens'][number];

// Synthetic personal MCP key issuance/revocation (tutorial profile) and admin application
// credentials (admin profile). Validation mirrors backend/app/api/identity/mcp_access.py and
// admin_credentials.py. Returns undefined for every path or profile this module does not own.
export function mockIdentityAdmin(
	method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId, requestProjectId?: string,
): unknown | undefined {
	if (profile === 'on') return mockPersonalTokens(method, path, body, requestProjectId);
	if (profile === 'admin') return mockApplicationCredentials(method, path, params, body);
	return undefined;
}

function mockPersonalTokens(method: string, path: string, body: unknown, requestProjectId?: string): unknown | undefined {
	if (path === TOKENS && method === 'POST') return issuePersonalToken(body, requestProjectId);
	const revoke = path.match(/^\/api\/v1\/auth\/mcp-tokens\/([^/]+)$/);
	if (revoke && method === 'DELETE' && revoke[1] !== 'lumen-default' && revoke[1] !== 'verify') {
		const state = getMockupState();
		const id = decodeURIComponent(revoke[1]);
		const record = state.mcpAccess.personalTokens.find((item) => item.id === id && item.status === 'active');
		if (!record) throw new ApiError(404, 'MCP grant was not found');
		record.status = 'revoked';
		record.revoked_at = new Date().toISOString();
		record.is_lumen_default = false;
		for (const [project, selected] of Object.entries(state.mcpAccess.lumenDefaults)) {
			state.mcpAccess.lumenDefaults[project] = selected.filter((item) => item !== id);
		}
		return {};
	}
	return undefined;
}

function issuePersonalToken(body: unknown, requestProjectId?: string): PersonalToken & { token: string } {
	const state = getMockupState();
	const payload = (body ?? {}) as Record<string, unknown>;
	const rawName = payload.name;
	if (typeof rawName !== 'string' || rawName.length < 1 || rawName.length > 100) throw new ApiError(422, 'name must be 1 to 100 characters');
	const name = rawName.trim();
	if (!name || [...name].some((char) => char.charCodeAt(0) < 32)) throw new ApiError(400, 'token name must contain 1 to 100 printable characters');
	const accessLevel = payload.access_level;
	if (accessLevel !== 'read' && accessLevel !== 'manage') throw new ApiError(422, 'access_level must be read or manage');
	const nonExpiring = payload.non_expiring ?? false;
	if (typeof nonExpiring !== 'boolean') throw new ApiError(422, 'non_expiring must be a boolean');
	const rawExpiry = payload.expires_at ?? null;
	if (nonExpiring && rawExpiry !== null) throw new ApiError(422, 'non-expiring tokens cannot also specify an expiry');
	const scope = payload.project_scope ?? 'current';
	if (scope !== 'current' && scope !== 'selected' && scope !== 'all') throw new ApiError(422, 'project scope must be current, selected or all');
	const rawIds = payload.project_ids ?? null;
	if (rawIds !== null && (!Array.isArray(rawIds) || rawIds.some((id) => typeof id !== 'string'))) throw new ApiError(422, 'project_ids must be a list of strings');
	const ids = (rawIds ?? []) as string[];

	const now = Date.now();
	let expiresAt: string | null = null;
	if (!nonExpiring) {
		let deadline = now + DEFAULT_TOKEN_LIFETIME_MS;
		if (rawExpiry !== null) {
			if (typeof rawExpiry !== 'string' || Number.isNaN(Date.parse(rawExpiry))) throw new ApiError(422, 'expires_at must be a datetime');
			if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(rawExpiry)) throw new ApiError(400, 'token expiry must include a timezone');
			deadline = Date.parse(rawExpiry);
		}
		if (deadline <= now) throw new ApiError(400, 'token expiry must be in the future');
		if (deadline > now + MAX_TOKEN_LIFETIME_MS) throw new ApiError(400, 'token expiry may not exceed 366 days');
		expiresAt = new Date(deadline).toISOString();
	}

	const ownerId = requestProjectId ?? state.selectedProjectId;
	const owner = state.projects.find((project) => project.id === ownerId);
	if (!owner) throw new ApiError(400, 'scoped connection does not match the MCP grant owner');
	const byId = new Map(state.projects.map((project) => [project.id, project]));
	let approved: { id: string; name: string }[];
	if (scope === 'current') {
		if (ids.length && (ids.length !== 1 || ids[0] !== owner.id)) throw new ApiError(400, 'current scope only allows the current project');
		approved = [owner];
	} else if (scope === 'all') {
		if (ids.length) throw new ApiError(400, 'all scope cannot include selected project IDs');
		approved = state.projects;
	} else {
		if (!ids.length || new Set(ids).size !== ids.length) throw new ApiError(400, 'selected scope requires unique project IDs');
		if (ids.some((id) => !byId.has(id))) throw new ApiError(400, 'selected project is not an enabled caller membership');
		approved = ids.map((id) => byId.get(id)!);
	}
	if (approved.some((project) => project.name.trim().toLowerCase() === 'default')) throw new ApiError(400, "MCP cannot connect to a domain's Default project");
	// Every synthetic tutorial membership is writable, so manage never fails the role check here.
	if (state.mcpAccess.personalTokens.filter((item) => item.status === 'active' && item.owner_project_id === owner.id).length >= MAX_ACTIVE_PERSONAL_TOKENS) {
		throw new ApiError(409, 'the project already has the maximum number of active MCP personal tokens');
	}

	const id = `mock-mcp-token-${nextSuffix(state.mcpAccess.personalTokens.map((item) => item.id), 'mock-mcp-token-')}`;
	// Same synthetic secret shape the tutorial transport has always issued.
	const token = `sk-afgl-mock-${id}`;
	const record: PersonalToken = {
		id,
		grant_id: `mock-mcp-grant-${id}`,
		name,
		owner_project_id: owner.id,
		owner_project_name: owner.name,
		source: 'personal_token',
		access_level: accessLevel,
		project_scope: scope,
		project_ids: approved.map((project) => project.id),
		projects: approved.map((project) => ({ id: project.id, name: project.name })),
		status: 'active',
		visible_prefix: token.slice(0, 20),
		issued_at: new Date(now).toISOString(),
		expires_at: expiresAt,
		last_used_at: null,
		revoked_at: null,
		is_lumen_default: false,
		client_observations: [],
	};
	state.mcpAccess.personalTokens.unshift(record);
	return { ...record, token };
}

function mockApplicationCredentials(method: string, path: string, params: URLSearchParams, body: unknown): unknown | undefined {
	if (path !== CREDENTIALS && !path.startsWith(`${CREDENTIALS}/`)) return undefined;
	const item = path.slice(CREDENTIALS.length + 1);
	const supported = (path === CREDENTIALS && (method === 'GET' || method === 'POST'))
		|| (item === 'context' && method === 'GET')
		|| (item && item !== 'context' && !item.includes('/') && (method === 'GET' || method === 'DELETE'));
	if (!supported) return undefined;
	requireDomain(params.get('domain_id'));
	if (item === 'context') return creationContext();
	if (path === CREDENTIALS && method === 'POST') return createApplication(body);

	const state = getMockupState();
	const userId = params.get('user_id') || ADMIN_USER_ID;
	if (!IDENTIFIER.test(userId)) throw credentialError(422, 'credential_invalid_input');
	if (!state.admin.users.some((user) => user.id === userId && user.domain_id === DOMAIN_ID)) throw credentialError(403, 'credential_scope_denied');
	if (path === CREDENTIALS) return { items: state.adminApplicationCredentials.filter((entry) => entry.user_id === userId) };

	const id = decodeURIComponent(item);
	if (!IDENTIFIER.test(id)) throw credentialError(422, 'credential_invalid_input');
	const existing = state.adminApplicationCredentials.find((entry) => entry.id === id && entry.user_id === userId);
	if (!existing) throw credentialError(404, 'credential_not_found');
	if (method === 'DELETE') {
		state.adminApplicationCredentials = state.adminApplicationCredentials.filter((entry) => entry !== existing);
		return {};
	}
	return existing;
}

function requireDomain(domainId: string | null) {
	if (!domainId || !IDENTIFIER.test(domainId)) throw credentialError(422, 'credential_invalid_input');
	if (domainId !== DOMAIN_ID) throw credentialError(404, 'credential_not_found');
}

function creationContext() {
	const state = getMockupState();
	// Keystone issues application credentials only to the signed-in user and its token project.
	if (!state.admin.users.some((user) => user.id === ADMIN_USER_ID && user.domain_id === DOMAIN_ID)) throw credentialError(403, 'credential_scope_denied');
	return { domain_id: DOMAIN_ID, user_id: ADMIN_USER_ID, project_id: ADMIN_PROJECT_ID, roles: CONTEXT_ROLES.map((role) => ({ ...role })) };
}

function createApplication(body: unknown): ApplicationCredentialIssued {
	const state = getMockupState();
	if (!body || typeof body !== 'object' || Array.isArray(body)) throw credentialError(422, 'credential_invalid_input');
	const input = body as Record<string, unknown>;
	if (Object.keys(input).some((key) => !APPLICATION_FIELDS.includes(key))) throw credentialError(422, 'credential_invalid_input');
	const { name, description = '', role_ids: roleIds, expires_at: expiresAt = null } = input;
	if (typeof name !== 'string' || name.length < 1 || name.length > 255) throw credentialError(422, 'credential_invalid_input');
	if (typeof description !== 'string' || description.length > 4096) throw credentialError(422, 'credential_invalid_input');
	if (!Array.isArray(roleIds) || roleIds.length < 1 || roleIds.length > 128 || roleIds.some((id) => typeof id !== 'string' || !IDENTIFIER.test(id))) {
		throw credentialError(422, 'credential_invalid_input');
	}
	if (expiresAt !== null && (typeof expiresAt !== 'string' || Number.isNaN(Date.parse(expiresAt))
		|| !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(expiresAt) || Date.parse(expiresAt) <= Date.now())) {
		throw credentialError(422, 'credential_invalid_input');
	}
	const context = creationContext();
	const requested = [...new Set(roleIds as string[])];
	if (requested.some((id) => !context.roles.some((role) => role.id === id))) throw credentialError(403, 'credential_scope_denied');
	// Keystone application credential names are unique per user.
	if (state.adminApplicationCredentials.some((entry) => entry.user_id === context.user_id && entry.name === name)) throw credentialError(409, 'credential_conflict');
	const id = `mock-app-cred-${nextSuffix(state.adminApplicationCredentials.map((entry) => entry.id), 'mock-app-cred-')}`;
	const created: ApplicationCredential = {
		id,
		domain_id: DOMAIN_ID,
		user_id: context.user_id,
		name,
		description,
		project_id: context.project_id,
		expires_at: expiresAt === null ? null : new Date(Date.parse(expiresAt)).toISOString(),
		unrestricted: false,
		roles: requested.map((roleId) => ({ ...context.roles.find((role) => role.id === roleId)! })),
	};
	state.adminApplicationCredentials.push(created);
	return { ...created, secret: `mock-app-cred-secret-${id.slice('mock-app-cred-'.length)}-tutorial` };
}

function credentialError(status: number, code: string): ApiError {
	return new ApiError(status, code, code);
}

function nextSuffix(ids: string[], prefix: string): number {
	return Math.max(0, ...ids.filter((id) => id.startsWith(prefix)).map((id) => Number(id.slice(prefix.length))).filter(Number.isInteger)) + 1;
}
