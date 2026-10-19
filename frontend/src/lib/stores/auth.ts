import { writable, derived, get } from 'svelte/store';
import { MOCKUP_QUERY_KEY, MOCKUP_STORAGE_KEY, MOCKUP_SESSION_KEY, isMockupProfileId } from '$lib/mockup/contracts';
import type { MockupProfileId } from '$lib/mockup/contracts';
import type { AvailableDomain } from '$lib/types/auth';
import { consumeMappedContinuation, consumeMappedLogin, sessionScopeKey } from '$lib/utils/authSession';

// Ready after an authoritative fresh login mapping or current /auth/me verification.
export const authReady = writable(false);
export const logoutInProgress = writable(false);
// Clears project-private views before rescope starts, not after its response arrives.
export const projectSwitching = writable(false);

// Transient verification failure for this token only; never persisted as credentials.
export const authRecovery = writable<{ token: string; retryAt: number } | null>(null);


export interface Project {
	id: string;
	name: string;
	description?: string;
	domain_name?: string | null;
	last_accessed_at?: string | null;
}

export interface AuthState {
	token: string | null;           // access JWT
	refreshToken: string | null;    // refresh JWT
	accessExpiresAt: number | null; // access JWT 만료 unix timestamp
	userId: string | null;
	username: string | null;
	projectId: string | null;
	projectName: string | null;
	availableProjects: Project[];
	roles: string[];
	isSystemAdmin: boolean;
	canWrite?: boolean;            // verified capability; role names may be hidden
	federated: boolean;             // true = OIDC/외부 로그인 (패스워드 변경 불가)
	domainId: string | null;        // explicit working domain, not credential namespace
	domainName: string | null;
	identityDomainId?: string | null; // immutable Keystone credential namespace
	identityDomainName?: string | null;
	availableDomains?: AvailableDomain[];
	canCreateDomain?: boolean;
	isDomainManager: boolean;       // server-verified manager on this domain's Default
	sessionId?: string;             // client-side logical login session; refresh/rescope keep it
}

const initial: AuthState = {
	token: null,
	refreshToken: null,
	accessExpiresAt: null,
	userId: null,
	username: null,
	projectId: null,
	projectName: null,
	availableProjects: [],
	roles: [],
	isSystemAdmin: false,
	federated: false,
	domainId: null,
	domainName: null,
	identityDomainId: null,
	identityDomainName: null,
	availableDomains: [],
	canCreateDomain: false,
	isDomainManager: false,
};

export type AuthPersistenceMode = 'real' | 'mock';
type MockupQueryProfile = MockupProfileId | 'off' | 'invalid' | null;

export const AUTH_STORAGE_KEY = 'afterglow_auth';
export const AUTH_LOGOUT_EVENT_KEY = 'afterglow_auth_logout';
const AUTH_LOGOUT_SEEN_KEY = 'afterglow_auth_logout_seen';

function readLogoutMarker(): string | null {
	try { return localStorage.getItem(AUTH_LOGOUT_EVENT_KEY); } catch { return null; }
}

function clearSessionMarker(): void {
	const secure = location.protocol === 'https:' ? '; Secure' : '';
	document.cookie = `afterglow_session=; path=/; SameSite=Strict${secure}; max-age=0`;
}

function discardLegacyCredentials(): void {
	// Never import browser-wide credentials. Existing sessions must authenticate again.
	try { localStorage.removeItem(AUTH_STORAGE_KEY); } catch { /* storage may be disabled */ }
}

function hasSessionDomain(state: Partial<AuthState>): boolean {
	return typeof state.domainId === 'string' && state.domainId.trim().length > 0;
}

function loadPersistedAuth(): AuthState {
	if (typeof window === 'undefined') return initial;
	try {
		const raw = sessionStorage.getItem(AUTH_STORAGE_KEY);
		if (raw && sessionStorage.getItem(AUTH_LOGOUT_SEEN_KEY) === readLogoutMarker()) {
			const restored = { ...initial, ...JSON.parse(raw) } as AuthState;
			// Pre-cutover sessions lack the immutable identity binding; authenticate again.
			if (!restored.token || (hasSessionDomain(restored) && typeof restored.identityDomainId === 'string' && restored.identityDomainId.trim())) {
				return { ...restored, isDomainManager: restored.isDomainManager === true };
			}
		}
		sessionStorage.removeItem(AUTH_STORAGE_KEY);
	} catch { /* unavailable storage means an in-memory session */ }
	return initial;
}

function loadMockAuth(): AuthState {
	if (typeof window === 'undefined') return initial;
	try {
		const raw = sessionStorage.getItem(MOCKUP_STORAGE_KEY);
		if (raw) return { ...initial, ...JSON.parse(raw) };
	} catch {
		/* ignore */
	}
	return initial;
}

function readMockupProfile(): MockupProfileId | null {
	if (typeof window === 'undefined') return null;
	try {
		const raw = sessionStorage.getItem(MOCKUP_SESSION_KEY);
		return isMockupProfileId(raw) ? raw : null;
	} catch {
		return null;
	}
}

function readMockupQuery(): MockupQueryProfile {
	if (typeof window === 'undefined' || typeof window.location?.search !== 'string') return null;
	const params = new URLSearchParams(window.location.search);
	if (!params.has(MOCKUP_QUERY_KEY)) return null;
	const value = params.get(MOCKUP_QUERY_KEY);
	if (value === 'off' || isMockupProfileId(value)) return value;
	return 'invalid';
}

function resolveInitialMockupProfile(): MockupProfileId | null {
	const queryProfile = readMockupQuery();
	if (queryProfile === 'off' || queryProfile === 'invalid') {
		sessionStorage.removeItem(MOCKUP_STORAGE_KEY);
		sessionStorage.removeItem(MOCKUP_SESSION_KEY);
		return null;
	}
	if (queryProfile) {
		if (readMockupProfile() !== queryProfile) {
			sessionStorage.removeItem(MOCKUP_STORAGE_KEY);
		}
		sessionStorage.setItem(MOCKUP_SESSION_KEY, queryProfile);
		return queryProfile;
	}
	return readMockupProfile();
}

export function detectInitialAuthContext(): { mode: AuthPersistenceMode; state: AuthState } {
	if (typeof window !== 'undefined') discardLegacyCredentials();
	if (resolveInitialMockupProfile()) {
		return { mode: 'mock', state: loadMockAuth() };
	}
	return { mode: 'real', state: loadPersistedAuth() };
}

const initialContext = detectInitialAuthContext();
let persistenceMode: AuthPersistenceMode = initialContext.mode;
let mockupProfile: MockupProfileId | null = initialContext.mode === 'mock' ? readMockupProfile() : null;

function readAcknowledgedLogoutMarker(): string | null {
	try { return sessionStorage.getItem(AUTH_LOGOUT_SEEN_KEY); } catch { return null; }
}

// This is the session boundary's acknowledgement, never a routine store update's.
let acknowledgedLogoutMarker = readAcknowledgedLogoutMarker();
function acknowledgeLogoutMarker(marker: string | null): void {
	acknowledgedLogoutMarker = marker;
	try {
		if (marker === null) sessionStorage.removeItem(AUTH_LOGOUT_SEEN_KEY);
		else sessionStorage.setItem(AUTH_LOGOUT_SEEN_KEY, marker);
	} catch { /* retain the acknowledgement for the current in-memory session */ }
}

// Never persisted. The generation also fences same-token/scope A -> B -> A work.
let verificationEpoch = 0;
let verifiedEpoch: number | null = null;
let verificationKey = '';
let pendingVerifiedLogin: AuthState | null = null;
let pendingReadyContinuation: AuthState | null = null;

function invalidateVerification(preserveReadiness = false): void {
	verificationEpoch += 1;
	verifiedEpoch = null;
	if (!preserveReadiness) authReady.set(false);
	authRecovery.set(null);
}

export function getAuthVerificationEpoch(): number {
	return verificationEpoch;
}

export function hasVerifiedAuth(): boolean {
	return persistenceMode === 'real' && verifiedEpoch === verificationEpoch;
}

/** Publish /me metadata only while its exact logical session/token/scope is current. */
export function acceptAuthVerification(epoch: number, verified: Partial<AuthState>): boolean {
	if (epoch !== verificationEpoch || persistenceMode !== 'real' || !get(auth).token) return false;
	verifiedEpoch = epoch;
	auth.update((state) => ({ ...state, ...verified }));
	authRecovery.set(null);
	authReady.set(true);
	return true;
}

export const auth = writable<AuthState>(initialContext.state);
auth.subscribe((state) => {
	const key = JSON.stringify([persistenceMode, state.token, sessionScopeKey(state)]);
	if (key !== verificationKey) {
		verificationKey = key;
		invalidateVerification(state === pendingReadyContinuation);
	}
	if (state === pendingReadyContinuation) pendingReadyContinuation = null;
	if (state === pendingVerifiedLogin) {
		pendingVerifiedLogin = null;
		verifiedEpoch = verificationEpoch;
		authReady.set(true);
	}
});
if (initialContext.mode === 'mock' && initialContext.state.token) {
	authReady.set(true);
}

// Credentials survive reloads in this tab, but never enter browser-wide storage.
if (typeof window !== 'undefined') {
	auth.subscribe(($auth) => {
		const key = persistenceMode === 'mock' ? MOCKUP_STORAGE_KEY : AUTH_STORAGE_KEY;
		try {
			if ($auth.token) {
				sessionStorage.setItem(key, JSON.stringify($auth));
			} else {
				sessionStorage.removeItem(key);
			}
		} catch { /* keep the current in-memory session if storage is unavailable */ }
		if (persistenceMode === 'mock') return;
		const secure = location.protocol === 'https:' ? '; Secure' : '';
		// A newly opened logged-out tab must not delete another tab's SSR marker.
		if ($auth.token) document.cookie = `afterglow_session=1; path=/; SameSite=Strict${secure}`;
	});

	// Only secret-free revocation is shared. Tokens and project state remain tab-local.
	window.addEventListener?.('storage', (e: StorageEvent) => {
		if (e.storageArea && e.storageArea !== localStorage) return;
		if (e.key !== AUTH_LOGOUT_EVENT_KEY || !e.newValue) return;
		// Events are queued. An older event must not revoke a new login that
		// already acknowledged a later marker, and refresh cannot acknowledge either.
		const latestMarker = readLogoutMarker();
		if (latestMarker !== null && e.newValue !== latestMarker) return;
		if (acknowledgedLogoutMarker === e.newValue) return;
		acknowledgeLogoutMarker(e.newValue);
		try { sessionStorage.removeItem(AUTH_STORAGE_KEY); } catch { /* clear memory below */ }
		if (persistenceMode === 'mock') return;
		clearSessionMarker();
		authReady.set(false);
		auth.set(initial);
	});
}

export function enterMockAuth(snapshot: AuthState, profile?: MockupProfileId): void {
	invalidateVerification();
	persistenceMode = 'mock';
	mockupProfile = profile ?? mockupProfile;
	if (mockupProfile && typeof sessionStorage !== 'undefined') {
		sessionStorage.setItem(MOCKUP_SESSION_KEY, mockupProfile);
	}
	auth.set(snapshot);
	authReady.set(true);
}

export function exitMockAuth(): void {
	invalidateVerification();
	if (typeof localStorage !== 'undefined') {
		// Clean a legacy cross-tab snapshot left by older mockup builds.
		localStorage.removeItem(MOCKUP_STORAGE_KEY);
	}
	if (typeof sessionStorage !== 'undefined') {
		sessionStorage.removeItem(MOCKUP_STORAGE_KEY);
		sessionStorage.removeItem(MOCKUP_SESSION_KEY);
	}
	mockupProfile = null;
	persistenceMode = 'real';
	auth.set(loadPersistedAuth());
	authReady.set(false);
}

export function isMockAuthActive(): boolean {
	return persistenceMode === 'mock';
}

export function getMockupProfile(): MockupProfileId | null {
	return mockupProfile;
}

export const isLoggedIn = derived(auth, ($auth) => $auth.token !== null);
export const isAdmin = derived(auth, ($auth) => $auth.isSystemAdmin === true);
// Display gate only: the IAM API re-validates domain-manager authority on every request.
export const canManageDomain = derived(
	auth,
	($auth) => $auth.isDomainManager === true && hasSessionDomain($auth),
);
export const canWrite = derived(
	auth,
	($auth) =>
		$auth.isSystemAdmin === true ||
		($auth.canWrite ?? $auth.roles.some((r) => ['admin', 'member'].includes(r.toLowerCase())))
);
export const isReader = derived(
	[auth, canWrite],
	([$auth, $canWrite]) => !$canWrite && $auth.roles.some((r) => r.toLowerCase() === 'reader')
);

// Use only after password/OIDC authentication succeeds, not for refresh/rescope.
// Each login starts a new logical session; refresh and rescope keep its sessionId.
export function setLoginAuth(data: Partial<AuthState> & { token: string }): void {
	if (persistenceMode === 'real' && typeof window !== 'undefined') {
		acknowledgeLogoutMarker(readLogoutMarker());
	}
	invalidateVerification();
	const mapped = consumeMappedLogin(data);
	const state = { ...initial, ...data, sessionId: crypto.randomUUID() };
	pendingVerifiedLogin = mapped && persistenceMode === 'real' ? state : null;
	auth.set(state);
}

export function setAuth(data: Partial<AuthState> & { token: string }) {
	const previous = get(auth);
	const continuation = consumeMappedContinuation(data, previous);
	const state = { ...previous, ...data };
	// Keep existing consumers through a validated native continuation. Its new
	// token still requires /me; raw, copied or stale updates cannot retain readiness.
	pendingReadyContinuation = continuation && persistenceMode === 'real' && get(authReady)
		&& !!previous.token && !!data.token ? state : null;
	invalidateVerification(pendingReadyContinuation !== null);
	auth.set(state);
}

export function setProject(projectId: string, projectName: string) {
	auth.update((state) => ({
		...state,
		projectId,
		projectName
	}));
}

export function setAvailableProjects(projects: Project[]) {
	auth.update((state) => ({
		...state,
		availableProjects: projects
	}));
}

export function clearAuth() {
	pendingVerifiedLogin = null;
	pendingReadyContinuation = null;
	invalidateVerification();
	if (persistenceMode === 'real' && typeof window !== 'undefined' && get(auth).token) {
		try {
			// Random event id only: no identity, access token or refresh token.
			const marker = crypto.randomUUID();
			localStorage.setItem(AUTH_LOGOUT_EVENT_KEY, marker);
			acknowledgeLogoutMarker(marker);
		} catch { /* local logout still succeeds when storage is unavailable */ }
		clearSessionMarker();
	}
	authReady.set(false);
	auth.set(initial);
}

