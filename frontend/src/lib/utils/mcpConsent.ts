import { isOnboardingToken, takePendingInvitationPath } from './domainLogin';
import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { safeLumenSourcePath } from './lumenSourceNavigation';

const CONSENT_TICKET_KEY = 'afterglow_mcp_oauth_consent_ticket';
const TICKET_PATTERN = /^[A-Za-z0-9_-]{32,128}$/;
const CLAUDE_GATEWAY_AUTH_KEY = 'afterglow_claude_gateway_authorization';
const CLAUDE_GATEWAY_CODE_KEY = 'afterglow_claude_gateway_user_code';
const CLAUDE_GATEWAY_CODE_PATTERN = /^[A-HJ-NP-Z2-9]{4}-?[A-HJ-NP-Z2-9]{4}$/;
const PASSWORD_CREATE_KEY = 'afterglow_password_create_continuation';
const PASSWORD_CREATE_TTL = 15 * 60 * 1000;
const LUMEN_SOURCE_KEY = 'afterglow_lumen_source_continuation';
const LUMEN_SOURCE_TTL = 15 * 60 * 1000;

export function storeLumenSourceContinuation(path: unknown): boolean {
	const source = safeLumenSourcePath(path);
	if (!source) return false;
	try {
		const store = storage();
		if (!store) return false;
		store.setItem(LUMEN_SOURCE_KEY, JSON.stringify({ path: source, expiresAt: Date.now() + LUMEN_SOURCE_TTL }));
		return true;
	} catch { return false; }
}

function takeLumenSourcePath(consume: boolean): string | null {
	try {
		const store = storage();
		const raw = store?.getItem(LUMEN_SOURCE_KEY);
		if (!raw) return null;
		const value = JSON.parse(raw) as Record<string, unknown>;
		if (!value || typeof value.expiresAt !== 'number' || !Number.isFinite(value.expiresAt) || value.expiresAt <= Date.now() || value.expiresAt > Date.now() + LUMEN_SOURCE_TTL) {
			store?.removeItem(LUMEN_SOURCE_KEY);
			return null;
		}
		const path = safeLumenSourcePath(value.path);
		if (consume || !path) store?.removeItem(LUMEN_SOURCE_KEY);
		return path;
	} catch {
		try { storage()?.removeItem(LUMEN_SOURCE_KEY); } catch { /* Storage may be unavailable. */ }
		return null;
	}
}

export function clearPasswordCreateContinuation(): void {
	try { storage()?.removeItem(PASSWORD_CREATE_KEY); } catch { /* No persisted continuation. */ }
}

/** Proof stays tab-local, never in the login URL or a provider return parameter. */
export function storePasswordCreateContinuation(token: string): boolean {
	clearPasswordCreateContinuation();
	if (!isOnboardingToken(token)) return false;
	try {
		const store = storage(); if (!store) return false;
		store.setItem(PASSWORD_CREATE_KEY, JSON.stringify({ token, expiresAt: Date.now() + PASSWORD_CREATE_TTL }));
		return true;
	} catch { return false; }
}

function passwordCreateSession(): string | null {
	const state = get(auth);
	return state.token && state.federated && state.sessionId && state.userId && state.identityDomainId
		? JSON.stringify([state.sessionId, state.userId, state.identityDomainId]) : null;
}

/** Bind presentation freshness before an invitation or workspace picker defers the return. */
function markPasswordCreateFreshSession(): void {
	try {
		const raw = storage()?.getItem(PASSWORD_CREATE_KEY);
		if (!raw) return;
		const value = JSON.parse(raw) as Record<string, unknown>;
		const now = Date.now();
		if (!value || typeof value.token !== 'string' || !isOnboardingToken(value.token)
			|| typeof value.expiresAt !== 'number' || !Number.isFinite(value.expiresAt)
			|| value.expiresAt <= now || value.expiresAt > now + PASSWORD_CREATE_TTL) {
			clearPasswordCreateContinuation(); return;
		}
		storage()?.setItem(PASSWORD_CREATE_KEY, JSON.stringify({ token: value.token, expiresAt: value.expiresAt,
			freshSession: passwordCreateSession(), freshUntil: Math.min(value.expiresAt, now + PASSWORD_CREATE_TTL) }));
	} catch { clearPasswordCreateContinuation(); }
}

function takePasswordCreatePath(): string | null {
	try {
		const raw = storage()?.getItem(PASSWORD_CREATE_KEY);
		clearPasswordCreateContinuation();
		if (!raw) return null;
		const value: unknown = JSON.parse(raw);
		if (!value || typeof value !== 'object') return null;
		const { token, expiresAt, freshSession, freshUntil } = value as Record<string, unknown>;
		if (typeof token !== 'string' || !isOnboardingToken(token) || typeof expiresAt !== 'number'
			|| !Number.isFinite(expiresAt) || expiresAt <= Date.now() || expiresAt > Date.now() + PASSWORD_CREATE_TTL) return null;
		const reauthenticated = typeof freshSession === 'string' && freshSession === passwordCreateSession()
			&& typeof freshUntil === 'number' && Number.isFinite(freshUntil)
			&& freshUntil > Date.now() && freshUntil <= expiresAt && freshUntil <= Date.now() + PASSWORD_CREATE_TTL;
		return `/recover/${encodeURIComponent(token)}${reauthenticated ? '?reauthenticated=1' : ''}`;
	} catch { clearPasswordCreateContinuation(); return null; }
}

function storage(): Storage | null {
	if (typeof window === 'undefined') return null;
	return window.sessionStorage;
}

export function storeMcpConsentTicket(ticket: string): boolean {
	if (!TICKET_PATTERN.test(ticket)) return false;
	storage()?.setItem(CONSENT_TICKET_KEY, ticket);
	return true;
}

export function pendingMcpConsentTicket(): string | null {
	const ticket = storage()?.getItem(CONSENT_TICKET_KEY) ?? null;
	return ticket && TICKET_PATTERN.test(ticket) ? ticket : null;
}

export function clearMcpConsentTicket(): void {
	storage()?.removeItem(CONSENT_TICKET_KEY);
}
export function beginClaudeGatewayAuthorization(): void {
	storage()?.setItem(CLAUDE_GATEWAY_AUTH_KEY, '1');
}

export function storeClaudeGatewayUserCode(value: string): boolean {
	const candidate = value.trim().toUpperCase();
	if (!CLAUDE_GATEWAY_CODE_PATTERN.test(candidate)) return false;
	const compact = candidate.replace('-', '');
	storage()?.setItem(CLAUDE_GATEWAY_CODE_KEY, `${compact.slice(0, 4)}-${compact.slice(4)}`);
	return true;
}

export function pendingClaudeGatewayUserCode(): string | null {
	const code = storage()?.getItem(CLAUDE_GATEWAY_CODE_KEY) ?? null;
	return code && CLAUDE_GATEWAY_CODE_PATTERN.test(code) ? code : null;
}

export function clearClaudeGatewayAuthorization(): void {
	storage()?.removeItem(CLAUDE_GATEWAY_AUTH_KEY);
	storage()?.removeItem(CLAUDE_GATEWAY_CODE_KEY);
}

export function hasPendingClaudeGatewayAuthorization(): boolean {
	return storage()?.getItem(CLAUDE_GATEWAY_AUTH_KEY) === '1';
}

export function postAuthDestination(fallback: string): string {
	if (fallback === '/select-project' || fallback === '/select-domain') return fallback;
	const passwordCreate = takePasswordCreatePath();
	if (passwordCreate) return passwordCreate;
	if (pendingMcpConsentTicket()) return '/oauth/mcp/authorize';
	if (hasPendingClaudeGatewayAuthorization()) return '/oauth/claude/authorize';
	const hasProject = Boolean(get(auth).projectId);
	const source = takeLumenSourcePath(hasProject);
	return hasProject ? source ?? fallback : fallback;
}

/** Call only after publishing an exact fresh login; projectless retains intent. */
export function freshLoginDestination(fallback: string): string {
	markPasswordCreateFreshSession();
	if (fallback === '/select-project' || fallback === '/select-domain') return fallback;
	return takePendingInvitationPath() ?? postAuthDestination(fallback);
}
