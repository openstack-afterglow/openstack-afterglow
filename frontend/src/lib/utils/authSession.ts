import type { AuthState } from '$lib/stores/auth';
import type { AuthMeResponse, AvailableDomain, DomainSessionFields, LoginResponse, SessionTokenResponse } from '$lib/types/auth';
import { resolvePostLoginProject, type PostLoginTarget } from './authFlow';

/** A foreign or incomplete identity/working-domain response must never be published. */
export class SessionDomainError extends Error {
	constructor() {
		super('session domain mismatch');
		this.name = 'SessionDomainError';
	}
}

/** Refresh keeps this owner; logout, another login, identity/domain/project changes do not. */
export function sessionScopeKey(state: Pick<AuthState, 'sessionId' | 'userId' | 'identityDomainId' | 'domainId' | 'projectId'>): string {
	return JSON.stringify([state.sessionId ?? null, state.userId ?? null, state.identityDomainId ?? null, state.domainId ?? null, state.projectId ?? null]);
}

export type SessionStateUpdate = Partial<AuthState> & { token: string };

export interface SessionDomain {
	domainId: string;
	domainName: string;
	identityDomainId: string;
	identityDomainName: string;
	isDomainManager: boolean;
	availableDomains: AvailableDomain[];
	canCreateDomain: boolean;
}

type BoundSession = Pick<AuthState, 'domainId' | 'identityDomainId'> & Partial<Pick<AuthState, 'userId' | 'sessionId' | 'token' | 'projectId'>>;

function nonEmpty(value: unknown): string | null {
	if (typeof value !== 'string') return null;
	const trimmed = value.trim();
	return trimmed.length > 0 ? trimmed : null;
}

function availableDomains(data: DomainSessionFields): AvailableDomain[] {
	if (data.available_domains === undefined) return [];
	if (!Array.isArray(data.available_domains)) throw new SessionDomainError();
	const seen = new Set<string>();
	return data.available_domains.map((domain) => {
		const id = nonEmpty(domain?.id);
		const name = nonEmpty(domain?.name);
		if (!id || !name || seen.has(id)) throw new SessionDomainError();
		seen.add(id);
		if (domain.kind !== undefined && !['personal', 'organization', 'legacy'].includes(domain.kind)) throw new SessionDomainError();
		return { id, name, ...(domain.kind ? { kind: domain.kind } : {}) };
	});
}

/** Refresh and rescope retain the immutable credential-home identity. */
export function readSessionDomain(data: DomainSessionFields, expectedIdentityDomainId: string | null): SessionDomain {
	const domainId = nonEmpty(data.domain_id);
	const identityDomainId = nonEmpty(data.identity_domain_id);
	const identityDomainName = nonEmpty(data.identity_domain_name);
	if (!domainId || !identityDomainId || !identityDomainName || (expectedIdentityDomainId !== null && identityDomainId !== expectedIdentityDomainId)) throw new SessionDomainError();
	return {
		domainId,
		domainName: nonEmpty(data.domain_name) ?? domainId,
		identityDomainId,
		identityDomainName,
		isDomainManager: data.is_domain_manager === true,
		availableDomains: availableDomains(data),
		canCreateDomain: data.can_create_domain === true,
	};
}

function boundSessionDomain(data: DomainSessionFields & { user_id?: string }, current: BoundSession): SessionDomain {
	if (!nonEmpty(current.domainId) || !nonEmpty(current.identityDomainId)) throw new SessionDomainError();
	const domain = readSessionDomain(data, current.identityDomainId!);
	if (domain.domainId !== current.domainId || (current.userId && data.user_id !== current.userId)) throw new SessionDomainError();
	return domain;
}

/** Continuations may lose a project, but only explicit rescope may select another. */
function boundSessionProject(data: { project_id?: string | null; project_name?: string | null }, current: BoundSession): Partial<Pick<AuthState, 'projectId' | 'projectName'>> {
	// Older DTOs can omit project metadata; omission is not revocation.
	if (data.project_id === undefined) return {};
	const projectId = data.project_id || null;
	if (projectId && projectId !== current.projectId) throw new SessionDomainError();
	return { projectId, projectName: projectId ? (data.project_name || null) : null };
}

function expiresAtSeconds(value: string | null | undefined): number | null {
	return value ? Math.floor(new Date(value).getTime() / 1000) : null;
}

export interface LoginAuthMapping {
	state: SessionStateUpdate;
	target: PostLoginTarget;
}

// Only the exact, unmodified mapping can establish fresh-login readiness. This
// provenance is one-use and in-memory: copies and restored JSON have no proof.
const mappedLogins = new WeakSet<SessionStateUpdate>();
export function consumeMappedLogin(state: SessionStateUpdate): boolean {
	return mappedLogins.delete(state);
}

// Native refresh/rescope already checks the existing owner. Keep an established
// consumer mounted during that continuation, but do not grant fresh-login proof.
const mappedContinuations = new WeakMap<SessionStateUpdate, string>();
function continuationOwner(current: BoundSession): string {
	return JSON.stringify([current.token ?? null, current.sessionId ?? null, current.userId ?? null,
		current.identityDomainId, current.domainId, current.projectId ?? null]);
}
function mappedContinuation(state: SessionStateUpdate, current: BoundSession): SessionStateUpdate {
	Object.freeze(state);
	mappedContinuations.set(state, continuationOwner(current));
	return state;
}
export function consumeMappedContinuation(state: SessionStateUpdate, current: AuthState): boolean {
	const owner = mappedContinuations.get(state);
	mappedContinuations.delete(state);
	return owner !== undefined && owner === continuationOwner(current);
}

/** Fresh humans use personal or an exact server-verified opt-in workspace. */
export function loginAuthState(data: LoginResponse, opts: { federated: boolean }): LoginAuthMapping {
	const domain = readSessionDomain(data, null);
	const workingDomain = domain.availableDomains.find(row => row.id === domain.domainId);
	const projectlessAdministrator = data.is_system_admin === true && !nonEmpty(data.project_id) && workingDomain !== undefined;
    const initial = data.initial_workspace;
    if (initial && (!['personal', 'remembered'].includes(initial.kind)
        || !nonEmpty(initial.project_id) || initial.project_id !== data.project_id
        || initial.domain_id !== domain.domainId || !workingDomain
        || (initial.kind === 'personal' && workingDomain.kind !== 'personal'))) throw new SessionDomainError();
    if (domain.domainId !== domain.identityDomainId && workingDomain?.kind !== 'personal'
        && !projectlessAdministrator && initial?.kind !== 'remembered') throw new SessionDomainError();
	if (!nonEmpty(data.user_id) || !nonEmpty(data.token)) throw new SessionDomainError();
	const resolution = resolvePostLoginProject(data);
	const state: SessionStateUpdate = Object.freeze({
		token: data.token,
		refreshToken: data.refresh_token ?? null,
		accessExpiresAt: expiresAtSeconds(data.expires_at),
		userId: data.user_id,
		username: data.username,
		projectId: resolution.projectId,
		projectName: resolution.projectId ? (data.project_name || null) : null,
		roles: data.roles ?? [],
		isSystemAdmin: data.is_system_admin === true,
		canWrite: data.can_write,
		federated: opts.federated,
		...domain,
	});
	mappedLogins.add(state);
	return {
		target: resolution.projectId ? '/dashboard' : (domain.availableDomains.length > 1 ? '/select-domain' : '/select-project'),
		state,
	};
}

/** Project rescope cannot change either domain or the authenticated subject. */
export function rescopeAuthState(resp: SessionTokenResponse, current: BoundSession): SessionStateUpdate {
	const domain = boundSessionDomain(resp, current);
	return mappedContinuation({
		token: resp.token,
		refreshToken: resp.refresh_token ?? null,
		accessExpiresAt: expiresAtSeconds(resp.expires_at),
		projectId: resp.project_id || null,
		projectName: resp.project_name || null,
		roles: resp.roles ?? [],
		isSystemAdmin: resp.is_system_admin === true,
		canWrite: resp.can_write,
		...domain,
	}, current);
}

/** Only an explicit authorized target can change the working domain; identity stays fixed. */
export function domainAuthState(resp: SessionTokenResponse, current: AuthState, targetDomainId: string): SessionStateUpdate {
	if (!current.token || !current.userId || !nonEmpty(current.identityDomainId)
		|| !(current.availableDomains ?? []).some((domain) => domain.id === targetDomainId)) throw new SessionDomainError();
	const domain = readSessionDomain(resp, current.identityDomainId!);
	if (resp.user_id !== current.userId || domain.domainId !== targetDomainId || !nonEmpty(resp.token)) throw new SessionDomainError();
	return mappedContinuation({
		token: resp.token,
		refreshToken: resp.refresh_token ?? null,
		accessExpiresAt: expiresAtSeconds(resp.expires_at),
		projectId: resp.project_id || null,
		projectName: resp.project_name || null,
		availableProjects: [],
		roles: resp.roles ?? [],
		isSystemAdmin: resp.is_system_admin === true,
		canWrite: resp.can_write,
		...domain,
	}, current);
}

/** Refresh retains omitted state, but consumes authoritative project revocation. */
export function refreshAuthState(data: SessionTokenResponse, current: BoundSession & Pick<AuthState, 'refreshToken' | 'roles' | 'isSystemAdmin'>): SessionStateUpdate {
	const domain = boundSessionDomain(data, current);
	return mappedContinuation({
		token: data.token,
		refreshToken: data.refresh_token ?? current.refreshToken,
		accessExpiresAt: expiresAtSeconds(data.expires_at),
		roles: data.roles ?? current.roles,
		isSystemAdmin: data.is_system_admin ?? current.isSystemAdmin,
		canWrite: data.can_write,
		...boundSessionProject(data, current),
		...domain,
	}, current);
}

/** Verified metadata is shared by all authentication response paths. */
export function meAuthState(me: AuthMeResponse, current: BoundSession & Pick<AuthState, 'roles'>): Partial<AuthState> {
	const domain = boundSessionDomain(me, current);
	return {
		isSystemAdmin: me.is_system_admin === true,
		roles: me.roles ?? current.roles,
		canWrite: me.can_write,
		federated: me.auth_method === 'federated',
		...boundSessionProject(me, current),
		...domain,
	};
}
