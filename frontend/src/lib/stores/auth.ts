import { writable, derived, get } from 'svelte/store';
import { MOCKUP_QUERY_KEY, MOCKUP_STORAGE_KEY, MOCKUP_SESSION_KEY, isMockupProfileId } from '$lib/mockup/contracts';
import type { MockupProfileId } from '$lib/mockup/contracts';

// /api/auth/me 검증이 성공하면 true. 로그아웃/clearAuth 시 false.
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

function loadPersistedAuth(): AuthState {
	if (typeof window === 'undefined') return initial;
	try {
		const raw = sessionStorage.getItem(AUTH_STORAGE_KEY);
		if (raw && sessionStorage.getItem(AUTH_LOGOUT_SEEN_KEY) === readLogoutMarker()) {
			return { ...initial, ...JSON.parse(raw) };
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

export const auth = writable<AuthState>(initialContext.state);
auth.subscribe((state) => {
	authRecovery.update((failure) => failure?.token === state.token ? failure : null);
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
	persistenceMode = 'mock';
	mockupProfile = profile ?? mockupProfile;
	if (mockupProfile && typeof sessionStorage !== 'undefined') {
		sessionStorage.setItem(MOCKUP_SESSION_KEY, mockupProfile);
	}
	auth.set(snapshot);
	authReady.set(true);
}

export function exitMockAuth(): void {
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
export function setLoginAuth(data: Partial<AuthState> & { token: string }): void {
	if (persistenceMode === 'real' && typeof window !== 'undefined') {
		acknowledgeLogoutMarker(readLogoutMarker());
	}
	authReady.set(false);
	auth.set({ ...initial, ...data });
}

export function setAuth(data: Partial<AuthState> & { token: string }) {
	auth.update((state) => ({
		...state,
		...data
	}));
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

