import { writable, derived } from 'svelte/store';
import { MOCKUP_QUERY_KEY, MOCKUP_STORAGE_KEY, MOCKUP_SESSION_KEY, isMockupProfileId } from '$lib/mockup/contracts';
import type { MockupProfileId } from '$lib/mockup/contracts';

// /api/auth/me 검증이 성공하면 true. 로그아웃/clearAuth 시 false.
export const authReady = writable(false);
export const logoutInProgress = writable(false);

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

function loadAuthFromStorage(key: string): AuthState {
	if (typeof window === 'undefined') return initial;
	try {
		const raw = localStorage.getItem(key);
		if (raw) return { ...initial, ...JSON.parse(raw) };
	} catch { /* ignore */ }
	return initial;
}

function loadPersistedAuth(): AuthState {
	return loadAuthFromStorage('afterglow_auth');
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
	if (resolveInitialMockupProfile()) {
		return { mode: 'mock', state: loadMockAuth() };
	}
	return { mode: 'real', state: loadPersistedAuth() };
}

const initialContext = detectInitialAuthContext();
let persistenceMode: AuthPersistenceMode = initialContext.mode;
let mockupProfile: MockupProfileId | null = initialContext.mode === 'mock' ? readMockupProfile() : null;

export const auth = writable<AuthState>(initialContext.state);
auth.subscribe((state) => {
	authRecovery.update((failure) => failure?.token === state.token ? failure : null);
});
if (initialContext.mode === 'mock' && initialContext.state.token) {
	authReady.set(true);
}

// 자동 영속화
if (typeof window !== 'undefined') {
	auth.subscribe(($auth) => {
		// Fix 5: Secure 속성은 HTTPS에서만 부착 — 비-localhost HTTP 배포에서 쿠키 드롭 방지
		const secure = location.protocol === 'https:' ? '; Secure' : '';
		if (persistenceMode === 'mock') {
			if ($auth.token) {
				const serialized = JSON.stringify($auth);
				if (sessionStorage.getItem(MOCKUP_STORAGE_KEY) !== serialized) {
					sessionStorage.setItem(MOCKUP_STORAGE_KEY, serialized);
				}
			} else {
				sessionStorage.removeItem(MOCKUP_STORAGE_KEY);
			}
			return;
		}
		if ($auth.token) {
			const serialized = JSON.stringify($auth);
			// 동일 값 재기록 방지 — storage 이벤트로 받은 상태를 그대로 되쓰는 왕복 차단
			if (localStorage.getItem('afterglow_auth') !== serialized) {
				localStorage.setItem('afterglow_auth', serialized);
			}
			document.cookie = `afterglow_session=1; path=/; SameSite=Strict${secure}`;
		} else {
			localStorage.removeItem('afterglow_auth');
			document.cookie = `afterglow_session=; path=/; SameSite=Strict${secure}; max-age=0`;
		}
	});

	// 탭 간 세션 동기화: 같은 브라우저의 다른 탭이 토큰을 회전(갱신)하거나 로그아웃하면
	// 즉시 이 탭의 store에 반영한다. refresh 토큰은 1회용(회전 시 즉시 폐기)이므로
	// 동기화가 없으면 두 번째 탭이 폐기된 토큰으로 갱신을 시도하다 세션 전체가 끊긴다.
	// storage 이벤트는 변경을 일으킨 탭 자신에게는 발생하지 않으므로 루프가 생기지 않는다.
	window.addEventListener?.('storage', (e) => {
		if (persistenceMode === 'mock' || e.key !== 'afterglow_auth') return;
		if (e.newValue === null) {
			// 다른 탭에서 로그아웃
			authReady.set(false);
			auth.set(initial);
			return;
		}
		try {
			const incoming = JSON.parse(e.newValue) as Partial<AuthState>;
			if (incoming.token) auth.update((cur) => ({ ...cur, ...incoming }));
		} catch {
			/* 손상된 값 무시 */
		}
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
export const isReader = derived(
	auth,
	($auth) =>
		!$auth.isSystemAdmin &&
		$auth.roles.some((r) => r.toLowerCase() === 'reader') &&
		!$auth.roles.some((r) => ['admin', 'member'].includes(r.toLowerCase()))
);
export const canWrite = derived(
	auth,
	($auth) =>
		$auth.isSystemAdmin === true ||
		$auth.roles.some((r) => ['admin', 'member'].includes(r.toLowerCase()))
);

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
	authReady.set(false);
	auth.set(initial);
}

