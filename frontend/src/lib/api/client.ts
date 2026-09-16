import { browser } from '$app/environment';
import { get } from 'svelte/store';
import { siteConfig } from '$lib/config/site';
import { auth, logoutInProgress } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import {
	getActiveMockupProfile,
	maybeMockBlob,
	maybeMockJson,
	maybeMockK3sStream,
	symbolNoMatch,
} from '$lib/mockup/transport';
import {
	getMockupRevision,
	onMockupRevisionChange,
} from '$lib/mockup/state';
import type { MockupProfileId } from '$lib/mockup/contracts';
export { ApiError } from '$lib/api/errors';

function stripTrailingSlash(value: string): string {
	return value.replace(/\/+$/, '');
}

function browserFallbackBaseUrl(): string {
	if (typeof window === 'undefined') return 'http://localhost:8000';
	return `${window.location.protocol}//${window.location.hostname}:8000`;
}

// 브라우저에서 직접 접근하는 Backend 주소
// afterglow.conf의 [app] frontend_base_url/backend_port 조합에서 런타임 주입
export function getBaseUrl(): string {
	const configured = get(siteConfig).runtime.api_base;
	return stripTrailingSlash(configured || browserFallbackBaseUrl());
}

export function getWebSocketUrl(path: string): string {
	const base = new URL(getBaseUrl() || (typeof window === 'undefined' ? 'http://localhost' : window.location.origin));
	base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
	return new URL(path, base).toString();
}


function formatErrorDetail(body: unknown, fallback: string): string {
	if (!body || typeof body !== 'object') return fallback;
	const detail = (body as { detail?: unknown }).detail;
	if (typeof detail === 'string') return detail;
	if (Array.isArray(detail)) {
		return detail
			.map((item) => {
				if (!item || typeof item !== 'object') return String(item);
				const record = item as { loc?: unknown; msg?: unknown };
				const loc = Array.isArray(record.loc) ? record.loc.join('.') : '';
				const msg = typeof record.msg === 'string' ? record.msg : JSON.stringify(item);
				return loc ? `${loc}: ${msg}` : msg;
			})
			.join('; ');
	}
	if (detail && typeof detail === 'object') return JSON.stringify(detail);
	return JSON.stringify(body);
}

// 동시 다수 요청이 401 받을 때 redirect 중복 호출 방지
let _redirectingTo401 = false;
// /api/admin/ 403 핸들러 중복 호출 방지
let _handling403Admin = false;
// 동시 다수 요청이 토큰 refresh를 중복 호출하지 않도록 직렬화
let _refreshPromise: Promise<string | null> | null = null;
let _sessionRevocationInProgress = false;
const AUTH_PUBLIC_PATHS = new Set(['/', '/login', '/auth/gitlab/callback']);


/**
 * /api/admin/ 경로에서 403 응답 시 isSystemAdmin=false 강등 + /dashboard로 이동.
 * one-shot 가드로 무한 루프 방지.
 */
async function handleAdminForbidden(): Promise<void> {
	if (typeof window === 'undefined') return;
	if (_handling403Admin) return;
	if (!window.location.pathname.startsWith('/admin')) return;
	_handling403Admin = true;
	try {
		const [{ auth }, { goto }] = await Promise.all([
			import('$lib/stores/auth'),
			import('$app/navigation'),
		]);
		auth.update((s) => ({ ...s, isSystemAdmin: false }));
		await goto('/dashboard');
	} catch {
		window.location.href = '/dashboard';
	} finally {
		setTimeout(() => { _handling403Admin = false; }, 5000);
	}
}

/**
 * 401 응답 시 인증 상태 정리 + 로그인 페이지(/login)로 자동 redirect.
 */
async function handleUnauthorized(): Promise<void> {
	if (typeof window === 'undefined') return;
	if (_redirectingTo401 || get(logoutInProgress)) return;

	// Mark synchronously before any import or refresh wait so concurrent 401s
	// cannot run a competing clear-and-redirect sequence.
	_redirectingTo401 = true;
	try {
		if (_refreshPromise) {
			try {
				const recovered = await _refreshPromise;
				if (recovered) return;
			} catch {
				return;
			}
		}

		if (get(logoutInProgress) || AUTH_PUBLIC_PATHS.has(window.location.pathname)) return;
		const [{ clearAuth }, { goto }] = await Promise.all([
			import('$lib/stores/auth'),
			import('$app/navigation'),
		]);
		if (get(logoutInProgress)) return;
		clearAuth();
		await goto('/login', { replaceState: true });
	} catch {
		if (!get(logoutInProgress)) window.location.replace('/login');
	} finally {
		setTimeout(() => { _redirectingTo401 = false; }, 1000);
	}
}

/**
 * refresh 토큰으로 새 access JWT를 발급. 성공하면 새 access token 반환, 401/인증 누락 시 null, 503/429/네트워크 오류 시 ApiError/예외 발생.
 * 동시 호출은 하나의 Promise로 합산(coalescing).
 */
/** localStorage에 영속화된 인증 상태를 직접 읽는다 (탭 간 race 대비 최신값 확인용). */
function _readPersistedAuth(): { token?: string; refreshToken?: string; accessExpiresAt?: number } | null {
	try {
		if (typeof localStorage === 'undefined') return null;
		const raw = localStorage.getItem('afterglow_auth');
		return raw ? JSON.parse(raw) : null;
	} catch {
		return null;
	}
}
type RefreshSettledFailure =
	| { kind: 'terminal'; accessToken: string | null | undefined; refreshToken: string }
	| { kind: 'retryable'; accessToken: string | null | undefined; refreshToken: string; error: unknown; retryAt: number };

let _refreshSettledFailure: RefreshSettledFailure | null = null;

const DEFAULT_REFRESH_RETRY_COOLDOWN_MS = 5_000;
const MAX_REFRESH_RETRY_COOLDOWN_MS = 60_000;

function computeRetryAt(retryAfterHeader: string | null | undefined, now: number): number {
	if (!retryAfterHeader) {
		return now + DEFAULT_REFRESH_RETRY_COOLDOWN_MS;
	}
	const trimmed = retryAfterHeader.trim();
	let guidanceMs: number | null = null;
	const numericSeconds = Number(trimmed);
	if (!isNaN(numericSeconds) && numericSeconds >= 0) {
		guidanceMs = Math.round(numericSeconds * 1000);
	} else {
		const parsedDate = Date.parse(trimmed);
		if (!isNaN(parsedDate)) {
			guidanceMs = parsedDate - now;
		}
	}

	if (guidanceMs === null || isNaN(guidanceMs)) {
		return now + DEFAULT_REFRESH_RETRY_COOLDOWN_MS;
	}

	const effectiveCooldownMs = Math.min(
		MAX_REFRESH_RETRY_COOLDOWN_MS,
		Math.max(DEFAULT_REFRESH_RETRY_COOLDOWN_MS, guidanceMs)
	);
	return now + effectiveCooldownMs;
}

async function tryRefresh({ allowDuringRevocation = false }: { allowDuringRevocation?: boolean } = {}): Promise<string | null> {
	if (_sessionRevocationInProgress && !allowDuringRevocation) return null;
	if (_refreshPromise) return _refreshPromise;
	_refreshPromise = (async () => {
		const { get } = await import('svelte/store');
		const { auth, setAuth } = await import('$lib/stores/auth');
		const state = get(auth);

		// 다른 탭이 이미 토큰을 회전시켰을 수 있다 — storage 이벤트 전파보다
		// localStorage 직접 읽기가 항상 최신이므로 여기서 한 번 더 확인한다.
		const persisted = _readPersistedAuth();
		if (persisted?.token && persisted.token !== state.token) {
			setAuth({
				token: persisted.token,
				refreshToken: persisted.refreshToken ?? state.refreshToken,
				accessExpiresAt: persisted.accessExpiresAt ?? null,
			});
			_refreshSettledFailure = null;
			return persisted.token;
		}

		const refreshToken = persisted?.refreshToken ?? state.refreshToken;
		if (!refreshToken) return null;

		if (_refreshSettledFailure) {
			if (
				_refreshSettledFailure.accessToken === state.token &&
				_refreshSettledFailure.refreshToken === refreshToken
			) {
				if (_refreshSettledFailure.kind === 'terminal') {
					return null;
				}
				if (Date.now() < _refreshSettledFailure.retryAt) {
					throw _refreshSettledFailure.error;
				}
			}
			_refreshSettledFailure = null;
		}

		let res: Response;
		try {
			res = await fetch(`${getBaseUrl()}/api/v1/auth/refresh`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ refresh_token: refreshToken }),
				signal: AbortSignal.timeout(15_000),
			});
		} catch (err) {
			_refreshSettledFailure = {
				kind: 'retryable',
				accessToken: state.token,
				refreshToken,
				error: err,
				retryAt: Date.now() + DEFAULT_REFRESH_RETRY_COOLDOWN_MS,
			};
			throw err;
		}

		if (!res.ok) {
			// refresh 토큰은 1회용(회전 시 폐기) — 동시에 다른 탭이 회전에 성공해
			// 이쪽이 패배한 경우라면 그 탭의 새 토큰을 채택하고 로그아웃하지 않는다.
			const winner = _readPersistedAuth();
			if (winner?.token && winner.token !== state.token) {
				setAuth({
					token: winner.token,
					refreshToken: winner.refreshToken ?? null,
					accessExpiresAt: winner.accessExpiresAt ?? null,
				});
				_refreshSettledFailure = null;
				return winner.token;
			}
			if (res.status === 401) {
				_refreshSettledFailure = {
					kind: 'terminal',
					accessToken: state.token,
					refreshToken,
				};
				return null;
			}
			let detail = res.statusText;
			try {
				const body = await res.json();
				detail = formatErrorDetail(body, res.statusText);
			} catch {
				detail = await res.text().catch(() => res.statusText);
			}
			const err = new ApiError(res.status, detail);
			const retryAfterHeader = res.headers?.get?.('Retry-After') ?? res.headers?.get?.('retry-after');
			const retryAt = res.status === 429
				? computeRetryAt(retryAfterHeader, Date.now())
				: Date.now() + DEFAULT_REFRESH_RETRY_COOLDOWN_MS;
			_refreshSettledFailure = {
				kind: 'retryable',
				accessToken: state.token,
				refreshToken,
				error: err,
				retryAt,
			};
			throw err;
		}

		const data = await res.json();
		const refreshedToken = data.token as string;
		const currentToken = get(auth).token;
		if (currentToken !== state.token) {
			_refreshSettledFailure = null;
			return currentToken ?? null;
		}
		setAuth({
			token: refreshedToken,
			refreshToken: data.refresh_token ?? refreshToken,
			accessExpiresAt: data.expires_at
				? Math.floor(new Date(data.expires_at).getTime() / 1000)
				: null,
		});
		_refreshSettledFailure = null;
		return refreshedToken;
	})().finally(() => { _refreshPromise = null; });
	return _refreshPromise;
}

/** Refresh the current session through the shared, coalesced refresh flow. */
export function refreshSession(): Promise<string | null> {
	return tryRefresh();
}

/**
 * Fence new refreshes while an explicit logout revokes the freshest token.
 * A refresh already running keeps its normal state transition, so callers can
 * await it and revoke the rotated access token without a mint-after-revoke gap.
 */
export function beginSessionRevocation(): Promise<string | null> {
	const pendingRefresh = _refreshPromise;
	_sessionRevocationInProgress = true;
	return pendingRefresh ?? Promise.resolve(null);
}

export function endSessionRevocation(): void {
	_sessionRevocationInProgress = false;
}

function _buildHeaders(token?: string, projectId?: string, extra?: HeadersInit): Record<string, string> {
	const headers: Record<string, string> = extra instanceof Headers
		? Object.fromEntries(extra.entries())
		: Array.isArray(extra) ? Object.fromEntries(extra) : { ...extra };
	for (const key of Object.keys(headers)) {
		if ((token && key.toLowerCase() === 'authorization') || (projectId && key.toLowerCase() === 'x-project-id')) {
			delete headers[key];
		}
	}
	if (token) {
		headers['Authorization'] = `Bearer ${token}`;
	}
	if (projectId) {
		headers['X-Project-Id'] = projectId;
	}
	return headers;
}

interface AuthRequestOptions {
	suppressAuthRedirect?: boolean;
	allowDuringRevocation?: boolean;
	signal?: AbortSignal | null;
}

function waitForRefresh(refresh: Promise<string | null>, signal?: AbortSignal | null): Promise<string | null> {
	if (!signal) return refresh;
	signal.throwIfAborted();
	return new Promise((resolve, reject) => {
		const abort = () => reject(signal.reason);
		signal.addEventListener('abort', abort, { once: true });
		refresh.then(
			(token) => { signal.removeEventListener('abort', abort); resolve(token); },
			(error) => { signal.removeEventListener('abort', abort); reject(error); },
		);
	});
}

async function withAuthRecovery<T extends { status: number }>(
	send: (token?: string) => Promise<T>,
	token: string | undefined,
	opts: AuthRequestOptions = {},
): Promise<T> {
	opts.signal?.throwIfAborted();
	let requestToken = token;
	if (token && !_sessionRevocationInProgress) {
		const state = get(auth);
		// Background-tab timers can be suspended. The request itself owns this
		// check and waits for rotation before sending a soon-to-expire token.
		if (_refreshPromise || (
			state.token && state.refreshToken && state.accessExpiresAt
			&& state.accessExpiresAt <= Math.floor(Date.now() / 1000) + 120
		)) {
			const freshToken = await waitForRefresh(tryRefresh(), opts.signal);
			opts.signal?.throwIfAborted();
			if (!freshToken) {
				if (!opts.suppressAuthRedirect) void handleUnauthorized();
				throw new ApiError(401, '세션이 만료되었습니다');
			}
			requestToken = freshToken;
		}
	}

	let response = await send(requestToken);
	opts.signal?.throwIfAborted();
	if (response.status === 401 && requestToken) {
		const liveToken = get(auth).token;
		const retryToken = liveToken && liveToken !== requestToken
			? liveToken
			: await waitForRefresh(tryRefresh({ allowDuringRevocation: opts.allowDuringRevocation }), opts.signal);
		opts.signal?.throwIfAborted();
		if (retryToken && retryToken !== requestToken) {
			response = await send(retryToken);
		}
		opts.signal?.throwIfAborted();
	}
	if (response.status === 401 && !opts.suppressAuthRedirect) void handleUnauthorized();
	return response;
}

/** First-party HTTP handshake recovery; callers retain response/body ownership. */
export function fetchWithAuth(
	path: string,
	options: RequestInit = {},
	token?: string,
	projectId?: string,
	reqOpts?: { suppressAuthRedirect?: boolean; baseUrl?: string },
): Promise<Response> {
	const baseUrl = reqOpts?.baseUrl ?? getBaseUrl();
	return withAuthRecovery(
		(currentToken) => fetch(`${baseUrl}${path}`, {
			...options,
			headers: _buildHeaders(currentToken, projectId, options.headers),
		}),
		token,
		{
			signal: options.signal,
			suppressAuthRedirect: reqOpts?.suppressAuthRedirect,
			allowDuringRevocation: path === '/api/v1/auth/logout' || path === '/api/v1/auth/logout-all',
		},
	);
}

async function request<T>(
	path: string,
	options: RequestInit = {},
	token?: string,
	projectId?: string,
	// Fix 3: caller가 401을 직접 처리하는 경우 전역 로그아웃 리다이렉트를 억제할 수 있음
	reqOpts?: { suppressAuthRedirect?: boolean; baseUrl?: string }
): Promise<T> {
	const method = (options.method ?? 'GET').toString().toUpperCase();
	const requestBaseUrl = reqOpts?.baseUrl ?? getBaseUrl();
	let requestBody: unknown = options.body;
	if (typeof options.body === 'string') {
		try { requestBody = JSON.parse(options.body); } catch { /* non-JSON body */ }
	}
	const mock = await maybeMockJson<T>(method, path, requestBody, token, projectId);
	if (mock !== symbolNoMatch) {
		if (method === 'GET') memoryCache.set(path, { data: mock, timestamp: Date.now() });
		return mock;
	}

	const res = await fetchWithAuth(path, {
		...options,
		headers: { 'Content-Type': 'application/json', ...options.headers },
		credentials: options.credentials ?? 'include',
		signal: options.signal ?? AbortSignal.timeout(30_000),
	}, token, projectId, { ...reqOpts, baseUrl: requestBaseUrl });

	if (!res.ok) {
		let detail = res.statusText;
		try {
			const body = await res.json();
			detail = formatErrorDetail(body, res.statusText);
		} catch {
			detail = await res.text().catch(() => res.statusText);
		}
		if (res.status === 403 && path.includes('/admin')) {
			void handleAdminForbidden();
		}
		throw new ApiError(res.status, detail);
	}

	if (res.status === 204) return undefined as T;
	return res.json();
}

// 브라우저 세션 내 인메모리 캐시 (SWR용)
export const memoryCache = new Map<string, { data: unknown; timestamp: number }>();

export interface PrefetchOptions {
	ttlMs?: number;
	signal?: AbortSignal;
	suppressAuthRedirect?: boolean;
}

export interface PrefetchInvalidation {
	token?: string;
	projectId?: string;
	path?: string;
}

interface RequestScope {
	baseUrl: string;
	token: string | undefined;
	projectId: string | undefined;
	mockProfile: MockupProfileId | null;
	mockRevision: number;
	key: string;
}

interface FamilyMetadata {
	scope: RequestScope;
	logicalUrl: string;
}

interface WarmEntry {
	snapshot: unknown;
	expiresAt: number;
}

interface OrdinaryPending {
	raw: Promise<unknown>;
	joined: boolean;
	snapshotReady: boolean;
	snapshot: unknown;
	cloneFailed: boolean;
	retry: () => Promise<unknown>;
}

const MAX_WARM_ENTRIES = 64;
const MAX_SPECULATIVE_LEADERS = 64;
const DEFAULT_PREFETCH_TTL_MS = 30_000;

const warmEntries = browser ? new Map<string, WarmEntry>() : null;
const ordinaryPending = browser ? new Map<string, OrdinaryPending>() : null;
const sharedSpeculativePending = browser ? new Map<string, Promise<void>>() : null;
const activeSpeculativeLeaders = browser ? new Set<Promise<void>>() : null;
const familyEpochs = browser ? new Map<string, number>() : null;
const familyMetadata = browser ? new Map<string, FamilyMetadata>() : null;
const familyActiveCounts = browser ? new Map<string, number>() : null;

function captureRequestScope(token?: string, projectId?: string): RequestScope {
	const baseUrl = getBaseUrl();
	const mockProfile = getActiveMockupProfile();
	const mockRevision = getMockupRevision();
	return {
		baseUrl,
		token,
		projectId,
		mockProfile,
		mockRevision,
		key: JSON.stringify([baseUrl, token ?? null, projectId ?? null, mockProfile, mockRevision]),
	};
}

function normalizeGetPath(
	path: string,
	scope: RequestScope,
	forceRefresh = false,
): { logicalUrl: string; requestPath: string; refresh: boolean } {
	const url = new URL(path, `${scope.baseUrl}/`);
	const refresh = forceRefresh || url.searchParams.getAll('refresh').includes('true');
	url.searchParams.delete('cache');
	url.searchParams.delete('refresh');
	const logicalQuery = url.searchParams.toString();
	const logicalUrl = `${url.origin}${url.pathname}${logicalQuery ? `?${logicalQuery}` : ''}`;
	url.searchParams.append(refresh ? 'refresh' : 'cache', 'true');
	return {
		logicalUrl,
		requestPath: `${url.pathname}${url.search}`,
		refresh,
	};
}

function registerFamily(scope: RequestScope, logicalUrl: string): string {
	const familyKey = JSON.stringify([scope.key, logicalUrl]);
	familyMetadata?.set(familyKey, { scope, logicalUrl });
	return familyKey;
}

function advanceFamilyEpoch(familyKey: string): number {
	if (!familyEpochs) return 0;
	const next = (familyEpochs.get(familyKey) ?? 0) + 1;
	familyEpochs.set(familyKey, next);
	return next;
}

function pruneFamily(familyKey: string): void {
	if ((familyActiveCounts?.get(familyKey) ?? 0) > 0 || warmEntries?.has(familyKey)) return;
	familyActiveCounts?.delete(familyKey);
	familyEpochs?.delete(familyKey);
	familyMetadata?.delete(familyKey);
}

function retainFamily(familyKey: string): void {
	if (!familyActiveCounts) return;
	familyActiveCounts.set(familyKey, (familyActiveCounts.get(familyKey) ?? 0) + 1);
}

function releaseFamily(familyKey: string): void {
	if (!familyActiveCounts) return;
	const remaining = (familyActiveCounts.get(familyKey) ?? 1) - 1;
	if (remaining > 0) familyActiveCounts.set(familyKey, remaining);
	else familyActiveCounts.delete(familyKey);
	pruneFamily(familyKey);
}

function trackFamilyDispatch<T>(familyKey: string, promise: Promise<T>): Promise<T> {
	retainFamily(familyKey);
	return promise.finally(() => releaseFamily(familyKey));
}

function invalidateExactScope(scope: RequestScope): void {
	if (!familyMetadata) return;
	for (const [familyKey, metadata] of familyMetadata) {
		if (metadata.scope.key !== scope.key) continue;
		warmEntries?.delete(familyKey);
		advanceFamilyEpoch(familyKey);
		pruneFamily(familyKey);
	}
}

export function clearPrefetchCache(opts: PrefetchInvalidation = {}): void {
	if (!familyMetadata) return;
	const hasToken = Object.prototype.hasOwnProperty.call(opts, 'token');
	const hasProject = Object.prototype.hasOwnProperty.call(opts, 'projectId');
	const pathLogicalUrl = opts.path
		? normalizeGetPath(opts.path, captureRequestScope(), false).logicalUrl
		: null;
	for (const [familyKey, metadata] of familyMetadata) {
		if (hasToken && metadata.scope.token !== opts.token) continue;
		if (hasProject && metadata.scope.projectId !== opts.projectId) continue;
		if (pathLogicalUrl !== null && metadata.logicalUrl !== pathLogicalUrl) continue;
		warmEntries?.delete(familyKey);
		advanceFamilyEpoch(familyKey);
		pruneFamily(familyKey);
	}
}

function validWarmEntry(familyKey: string): WarmEntry | null {
	const entry = warmEntries?.get(familyKey);
	if (!entry) return null;
	if (entry.expiresAt <= Date.now()) {
		warmEntries?.delete(familyKey);
		return null;
	}
	warmEntries?.delete(familyKey);
	warmEntries?.set(familyKey, entry);
	return entry;
}

function publishWarmEntry(familyKey: string, snapshot: unknown, expiresAt: number): void {
	if (!warmEntries) return;
	warmEntries.delete(familyKey);
	warmEntries.set(familyKey, { snapshot, expiresAt });
	while (warmEntries.size > MAX_WARM_ENTRIES) {
		const oldestKey = warmEntries.keys().next().value as string | undefined;
		if (oldestKey === undefined) break;
		warmEntries.delete(oldestKey);
		pruneFamily(oldestKey);
	}
}

function dispatchJsonGet<T>(
	requestPath: string,
	baseUrl: string,
	token: string | undefined,
	projectId: string | undefined,
	signal: AbortSignal | undefined,
	suppressAuthRedirect: boolean,
): Promise<T> {
	const requestSignal = signal
		? AbortSignal.any([signal, AbortSignal.timeout(30_000)])
		: undefined;
	return request<T>(
		requestPath,
		{ method: 'GET', signal: requestSignal },
		token,
		projectId,
		{ suppressAuthRedirect, baseUrl },
	);
}

function dispatchIndependentOrdinary<T>(
	familyKey: string,
	requestPath: string,
	baseUrl: string,
	token: string | undefined,
	projectId: string | undefined,
	suppressAuthRedirect: boolean,
): Promise<T> {
	advanceFamilyEpoch(familyKey);
	return trackFamilyDispatch(
		familyKey,
		dispatchJsonGet<T>(requestPath, baseUrl, token, projectId, undefined, suppressAuthRedirect),
	);
}

async function resolveOrdinaryLeader<T>(entry: OrdinaryPending): Promise<T> {
	const value = await entry.raw as T;
	if (!entry.joined) return value;
	try {
		if (!entry.snapshotReady) {
			entry.snapshot = structuredClone(value);
			entry.snapshotReady = true;
		}
		return structuredClone(entry.snapshot) as T;
	} catch {
		entry.cloneFailed = true;
		return value;
	}
}

async function resolveOrdinaryWaiter<T>(entry: OrdinaryPending): Promise<T> {
	const value = await entry.raw;
	try {
		if (entry.cloneFailed) throw new DOMException('Result is not cloneable', 'DataCloneError');
		if (!entry.snapshotReady) {
			entry.snapshot = structuredClone(value);
			entry.snapshotReady = true;
		}
		return structuredClone(entry.snapshot) as T;
	} catch {
		return entry.retry() as Promise<T>;
	}
}

function getOrdinary<T>(
	familyKey: string,
	requestPath: string,
	baseUrl: string,
	token: string | undefined,
	projectId: string | undefined,
	signal: AbortSignal | undefined,
	suppressAuthRedirect: boolean,
): Promise<T> {
	if (signal?.aborted) {
		return Promise.reject(new DOMException('The operation was aborted', 'AbortError'));
	}

	if (browser) {
		const warm = validWarmEntry(familyKey);
		if (warm) {
			try {
				return Promise.resolve(structuredClone(warm.snapshot) as T);
			} catch {
				warmEntries?.delete(familyKey);
			}
		}
	}

	if (!browser || signal) {
		advanceFamilyEpoch(familyKey);
		return trackFamilyDispatch(
			familyKey,
			dispatchJsonGet<T>(requestPath, baseUrl, token, projectId, signal, suppressAuthRedirect),
		);
	}

	const pendingKey = JSON.stringify([familyKey, suppressAuthRedirect]);
	const pending = ordinaryPending?.get(pendingKey);
	if (pending) {
		pending.joined = true;
		return resolveOrdinaryWaiter<T>(pending);
	}
	const retryMetadata = familyMetadata?.get(familyKey);

	advanceFamilyEpoch(familyKey);
	const entry: OrdinaryPending = {
		raw: trackFamilyDispatch(
			familyKey,
			dispatchJsonGet<unknown>(requestPath, baseUrl, token, projectId, undefined, suppressAuthRedirect),
		),
		joined: false,
		snapshotReady: false,
		snapshot: undefined,
		cloneFailed: false,
		retry: () => {
			if (retryMetadata) familyMetadata?.set(familyKey, retryMetadata);
			return dispatchIndependentOrdinary(
				familyKey,
				requestPath,
				baseUrl,
				token,
				projectId,
				suppressAuthRedirect,
			);
		},
	};
	ordinaryPending?.set(pendingKey, entry);
	void entry.raw.finally(() => {
		if (ordinaryPending?.get(pendingKey) === entry) ordinaryPending.delete(pendingKey);
	}).catch(() => undefined);
	return resolveOrdinaryLeader<T>(entry);
}

async function prefetchJson<T>(
	path: string,
	token?: string,
	projectId?: string,
	opts: PrefetchOptions = {},
): Promise<void> {
	if (!browser || opts.signal?.aborted) return;
	const scope = captureRequestScope(token, projectId);
	const normalized = normalizeGetPath(path, scope, false);
	if (normalized.refresh) return;
	const familyKey = registerFamily(scope, normalized.logicalUrl);
	if (validWarmEntry(familyKey)) return;

	const ttlMs = opts.ttlMs === undefined || !Number.isFinite(opts.ttlMs)
		? DEFAULT_PREFETCH_TTL_MS
		: Math.max(0, opts.ttlMs);
	const suppressAuthRedirect = opts.suppressAuthRedirect ?? true;
	const canShare = !opts.signal && ttlMs > 0;
	const pendingKey = canShare
		? JSON.stringify([familyKey, suppressAuthRedirect, ttlMs])
		: null;
	if (pendingKey) {
		const pending = sharedSpeculativePending?.get(pendingKey);
		if (pending) return pending;
	}
	if ((activeSpeculativeLeaders?.size ?? 0) >= MAX_SPECULATIVE_LEADERS) {
		pruneFamily(familyKey);
		return;
	}

	const publicationEpoch = advanceFamilyEpoch(familyKey);
	retainFamily(familyKey);
	let leader!: Promise<void>;
	leader = dispatchJsonGet<T>(
		normalized.requestPath,
		scope.baseUrl,
		token,
		projectId,
		opts.signal,
		suppressAuthRedirect,
	).then((value) => {
		if (opts.signal?.aborted || ttlMs === 0 || familyEpochs?.get(familyKey) !== publicationEpoch) return;
		try {
			publishWarmEntry(familyKey, structuredClone(value), Date.now() + ttlMs);
		} catch {
			// Speculative values that cannot be isolated are not reusable.
		}
	}).catch(() => {
		// Speculation never redirects by default and never surfaces failures.
	}).finally(() => {
		activeSpeculativeLeaders?.delete(leader);
		if (pendingKey && sharedSpeculativePending?.get(pendingKey) === leader) {
			sharedSpeculativePending.delete(pendingKey);
		}
		releaseFamily(familyKey);
	});
	activeSpeculativeLeaders?.add(leader);
	if (pendingKey) sharedSpeculativePending?.set(pendingKey, leader);
	return leader;
}

export function beginMutationCacheFence(
	token?: string,
	projectId?: string,
): { baseUrl: string; finish: () => void } {
	const scope = captureRequestScope(token, projectId);
	invalidateExactScope(scope);
	return {
		baseUrl: scope.baseUrl,
		finish: () => invalidateExactScope(scope),
	};
}

async function withMutationInvalidation<T>(
	scope: RequestScope,
	mutation: () => Promise<T>,
): Promise<T> {
	invalidateExactScope(scope);
	try {
		return await mutation();
	} finally {
		invalidateExactScope(scope);
	}
}

function uploadWithAuthProgress<T>(
	method: 'POST' | 'PUT',
	path: string,
	body: FormData | Blob,
	onProgress: (event: { loaded: number; total: number }) => void,
	token?: string,
	projectId?: string,
	contentType?: string,
): { promise: Promise<T>; abort: () => void } {
	const scope = captureRequestScope(token, projectId);
	invalidateExactScope(scope);
	const controller = new AbortController();
	let activeXhr: XMLHttpRequest | undefined;
	const promise = withAuthRecovery(
		(currentToken) => new Promise<XMLHttpRequest>((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			activeXhr = xhr;
			xhr.open(method, `${scope.baseUrl}${path}`);
			if (currentToken) xhr.setRequestHeader('Authorization', `Bearer ${currentToken}`);
			if (projectId) xhr.setRequestHeader('X-Project-Id', projectId);
			if (contentType) xhr.setRequestHeader('Content-Type', contentType);
			xhr.timeout = 0;
			xhr.upload.onprogress = (event) => {
				if (event.lengthComputable) onProgress({ loaded: event.loaded, total: event.total });
			};
			xhr.onload = () => resolve(xhr);
			xhr.onerror = () => reject(new Error('네트워크 오류가 발생했습니다'));
			xhr.onabort = () => reject(new ApiError(0, '업로드가 취소되었습니다'));
			xhr.send(body);
		}),
		token,
		{ signal: controller.signal },
	).then((xhr) => {
		if (xhr.status < 200 || xhr.status >= 300) {
			let detail = xhr.statusText;
			try { detail = JSON.parse(xhr.responseText)?.detail || detail; } catch { /* empty */ }
			throw new ApiError(xhr.status, detail);
		}
		if (xhr.status === 204) return undefined as T;
		try { return JSON.parse(xhr.responseText) as T; }
		catch { return undefined as T; }
	}).finally(() => invalidateExactScope(scope));
	return {
		promise,
		abort: () => {
			controller.abort(new ApiError(0, '업로드가 취소되었습니다'));
			activeXhr?.abort();
		},
	};
}

if (browser) {
	let observedScope: RequestScope | null = null;
	let observedToken: string | undefined;
	let observedProjectId: string | undefined;
	const syncObservedScope = () => {
		const next = captureRequestScope(observedToken, observedProjectId);
		if (observedScope && observedScope.key !== next.key) invalidateExactScope(observedScope);
		observedScope = next;
	};
	auth.subscribe((state) => {
		observedToken = state.token ?? undefined;
		observedProjectId = state.projectId ?? undefined;
		syncObservedScope();
	});
	siteConfig.subscribe(syncObservedScope);
	onMockupRevisionChange(syncObservedScope);
}

export const api = {
	get: <T>(
		path: string,
		token?: string,
		projectId?: string,
		opts?: { refresh?: boolean; signal?: AbortSignal; suppressAuthRedirect?: boolean }
	): Promise<T> => {
		if (opts?.signal?.aborted) {
			return Promise.reject(new DOMException('The operation was aborted', 'AbortError'));
		}
		const scope = captureRequestScope(token, projectId);
		const normalized = normalizeGetPath(path, scope, opts?.refresh);
		const familyKey = registerFamily(scope, normalized.logicalUrl);
		const suppressAuthRedirect = opts?.suppressAuthRedirect ?? false;
		if (normalized.refresh) {
			warmEntries?.delete(familyKey);
			advanceFamilyEpoch(familyKey);
			return trackFamilyDispatch(
				familyKey,
				dispatchJsonGet(
					normalized.requestPath,
					scope.baseUrl,
					token,
					projectId,
					opts?.signal,
					suppressAuthRedirect,
				),
			);
		}
		return getOrdinary(
			familyKey,
			normalized.requestPath,
			scope.baseUrl,
			token,
			projectId,
			opts?.signal,
			suppressAuthRedirect,
		);
	},
	prefetch: prefetchJson,
	clearPrefetchCache,
	post: <T>(path: string, body: unknown, token?: string, projectId?: string) => {
		const scope = captureRequestScope(token, projectId);
		return withMutationInvalidation(scope, () =>
			request<T>(path, { method: 'POST', body: JSON.stringify(body) }, token, projectId, { baseUrl: scope.baseUrl })
		);
	},
	put: <T>(path: string, body: unknown, token?: string, projectId?: string) => {
		const scope = captureRequestScope(token, projectId);
		return withMutationInvalidation(scope, () =>
			request<T>(path, { method: 'PUT', body: JSON.stringify(body) }, token, projectId, { baseUrl: scope.baseUrl })
		);
	},
	patch: <T>(path: string, body: unknown, token?: string, projectId?: string) => {
		const scope = captureRequestScope(token, projectId);
		return withMutationInvalidation(scope, () =>
			request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }, token, projectId, { baseUrl: scope.baseUrl })
		);
	},
	delete: <T>(path: string, token?: string, projectId?: string) => {
		const scope = captureRequestScope(token, projectId);
		return withMutationInvalidation(scope, () =>
			request<T>(path, { method: 'DELETE' }, token, projectId, { baseUrl: scope.baseUrl })
		);
	},

	upload: <T>(path: string, formData: FormData, token?: string, projectId?: string): Promise<T> => {
		const scope = captureRequestScope(token, projectId);
		return withMutationInvalidation(scope, async () => {
			const res = await fetchWithAuth(path, {
				method: 'POST',
				body: formData,
				signal: AbortSignal.timeout(300_000),
			}, token, projectId, { baseUrl: scope.baseUrl });
			if (!res.ok) {
				let detail = res.statusText;
				try {
					const body = await res.json();
					detail = formatErrorDetail(body, res.statusText);
				} catch {
					detail = await res.text().catch(() => res.statusText);
				}
				throw new ApiError(res.status, detail);
			}
			if (res.status === 204) return undefined as T;
			return res.json();
		});
	},

	uploadWithProgress: <T>(
		path: string,
		formData: FormData,
		onProgress: (event: { loaded: number; total: number }) => void,
		token?: string,
		projectId?: string,
	): { promise: Promise<T>; abort: () => void } =>
		uploadWithAuthProgress<T>('POST', path, formData, onProgress, token, projectId),

	putWithProgress: <T>(
		path: string,
		blob: Blob,
		contentType: string,
		onProgress: (event: { loaded: number; total: number }) => void,
		token?: string,
		projectId?: string,
	): { promise: Promise<T>; abort: () => void } =>
		uploadWithAuthProgress<T>('PUT', path, blob, onProgress, token, projectId, contentType || 'application/octet-stream'),

	/** 절대 URL에 PUT (RGW presigned 등). 인증 헤더·Content-Type 미부착, ETag 반환.
	 * presigned upload_part는 X-Amz-SignedHeaders=host 만 서명하므로 Content-Type을 보내면
	 * RGW가 서명 불일치로 403을 반환할 수 있다. 호출자는 MIME 타입 없는 Blob을 전달해야 한다. */
	putAbsoluteWithProgress(
		url: string,
		body: Blob,
		onProgress: (p: { loaded: number; total: number }) => void,
		signal?: AbortSignal,
	): Promise<{ etag: string }> {
		const currentAuth = get(auth);
		const scope = captureRequestScope(
			currentAuth.token ?? undefined,
			currentAuth.projectId ?? undefined,
		);
		invalidateExactScope(scope);
		return new Promise<{ etag: string }>((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			xhr.open('PUT', url, true);
			xhr.upload.onprogress = (e) => {
				if (e.lengthComputable) onProgress({ loaded: e.loaded, total: e.total });
			};
			xhr.onload = () => {
				if (xhr.status >= 200 && xhr.status < 300) {
					resolve({ etag: xhr.getResponseHeader('ETag') || '' });
				} else {
					const body = xhr.responseText?.slice(0, 400) || '';
					console.error('[S3 PUT] HTTP error', { status: xhr.status, body });
					reject(new ApiError(xhr.status, `PUT failed: ${xhr.status}`));
				}
			};
			xhr.onerror = () => {
				console.error('[S3 PUT] onerror (network failure)', {
					status: xhr.status,
					readyState: xhr.readyState,
					url: url.split('?')[0],
				});
				reject(new ApiError(0, '네트워크 오류가 발생했습니다'));
			};
			xhr.onabort = () => reject(new ApiError(0, '업로드가 취소되었습니다'));
			signal?.addEventListener('abort', () => xhr.abort());
			xhr.send(body);
		}).finally(() => invalidateExactScope(scope));
	},

	downloadBlob: async (path: string, token?: string, projectId?: string): Promise<{ blob: Blob; filename: string }> => {
		const mock = await maybeMockBlob('GET', path, token, projectId);
		if (mock !== symbolNoMatch) return { blob: mock, filename: 'afterglow-mockup-kubeconfig.yaml' };
		const res = await fetchWithAuth(path, {
			method: 'GET',
			signal: AbortSignal.timeout(300_000),
		}, token, projectId);
		if (!res.ok) {
			let detail = res.statusText;
			try { detail = (await res.json())?.detail || detail; } catch { /* empty */ }
			throw new ApiError(res.status, detail);
		}
		const disposition = res.headers.get('Content-Disposition') || '';
		const match = disposition.match(/filename="?([^"]+)"?/);
		const filename = match ? decodeURIComponent(match[1]) : 'download';
		const blob = await res.blob();
		return { blob, filename };
	},

	/**
	 * SSE (Server-Sent Events) 요청
	 * @param path API 경로
	 * @param body 요청 본문
	 * @param token 인증 토큰
	 * @param projectId 프로젝트 ID
	 * @param onMessage 각 메시지 수신 시 호출되는 콜백
	 * @param onError 에러 발생 시 호출되는 콜백
	 */
	postSse: <T>(
		path: string,
		body: unknown,
		token?: string,
		projectId?: string,
		onMessage?: (data: T) => void,
		onError?: (error: Error) => void
	): void => {
		const scope = captureRequestScope(token, projectId);
		invalidateExactScope(scope);
		const mockStream = maybeMockK3sStream(path, body, token, projectId);
		if (mockStream) {
			(async () => {
				try {
					for await (const message of mockStream) onMessage?.(message as T);
				} catch (err) {
					onError?.(err instanceof Error ? err : new Error(String(err)));
				}
				finally {
					invalidateExactScope(scope);
				}
			})();
			return;
		}

		// fetch로 POST 요청 후 스트림 처리
		fetchWithAuth(path, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
			body: JSON.stringify(body)
		}, token, projectId, { baseUrl: scope.baseUrl }).then(async (response) => {
			if (!response.ok) {
				const text = await response.text();
				throw new ApiError(response.status, text || response.statusText);
			}

			const reader = response.body?.getReader();
			if (!reader) throw new Error('No response body');

			const decoder = new TextDecoder();
			let buffer = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;

				buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split('\n');
				buffer = lines.pop() || '';

				for (const line of lines) {
					if (line.startsWith('data: ')) {
						try {
							const data = JSON.parse(line.slice(6)) as T;
							onMessage?.(data);
						} catch {
							// JSON 파싱 실패 시 무시
						}
					}
				}
			}
		}).catch((err) => {
			onError?.(err instanceof Error ? err : new Error(String(err)));
		}).finally(() => {
			invalidateExactScope(scope);
		});
	}
};
