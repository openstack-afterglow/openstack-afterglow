import { goto } from '$app/navigation';
import { tick } from 'svelte';
import { get, readonly, writable } from 'svelte/store';
import { api, beginSessionRevocation, endSessionRevocation } from '$lib/api/client';
import { AUTH_STORAGE_KEY, auth, clearAuth, exitMockAuth, isMockAuthActive, logoutInProgress } from '$lib/stores/auth';
import { cloudShell } from '$lib/stores/cloudShell.svelte';
import { MOCKUP_SESSION_KEY, MOCKUP_STORAGE_KEY } from '$lib/mockup/contracts';
import { sessionScopeKey } from './authSession';

export type LogoutStep = 'pending' | 'active' | 'done' | 'warning';
export interface LogoutProgress {
	phase: 'idle' | 'running' | 'complete';
	all: boolean;
	shell: LogoutStep;
	server: LogoutStep;
	local: LogoutStep;
	serverNotRequired: boolean;
	loginHref: string;
}

const progress = writable<LogoutProgress>({
	phase: 'idle', all: false, shell: 'pending', server: 'pending', local: 'pending',
	serverNotRequired: false, loginHref: '/login',
});
export const logoutProgress = readonly(progress);
let inFlight: Promise<void> | null = null;
let completed: Promise<void> | null = null;
let completedOwner: string | null = null;

/** Give the committed route a paint, without delaying cleanup in a background tab. */
async function paintLogoutPage(): Promise<void> {
	await tick();
	if (document.visibilityState === 'hidden') return;
	const { promise, resolve } = Promise.withResolvers<void>();
	let frame: number;
	const finish = () => {
		cancelAnimationFrame(frame);
		document.removeEventListener('visibilitychange', visibility);
		resolve();
	};
	const visibility = () => { if (document.visibilityState === 'hidden') finish(); };
	document.addEventListener('visibilitychange', visibility);
	frame = requestAnimationFrame(() => { frame = requestAnimationFrame(finish); });
	await promise;
}

function clearLocalCredentials(mock: boolean): boolean {
	let confirmed = true;
	const attempt = (action: () => void) => { try { action(); } catch { confirmed = false; } };
	// Clear the tutorial snapshot before exiting: exitMockAuth may restore a separate real login.
	attempt(() => clearAuth());
	if (mock) {
		attempt(() => exitMockAuth());
		attempt(() => {
			if (sessionStorage.getItem(MOCKUP_STORAGE_KEY) || sessionStorage.getItem(MOCKUP_SESSION_KEY)
				|| localStorage.getItem(MOCKUP_STORAGE_KEY) || isMockAuthActive()) confirmed = false;
		});
	} else {
		// The auth subscriber is best-effort; explicitly remove and verify persisted credentials too.
		attempt(() => sessionStorage.removeItem(AUTH_STORAGE_KEY));
		attempt(() => localStorage.removeItem(AUTH_STORAGE_KEY));
		attempt(() => {
			const secure = location.protocol === 'https:' ? '; Secure' : '';
			document.cookie = `afterglow_session=; path=/; SameSite=Strict${secure}; max-age=0`;
			if (get(auth).token || sessionStorage.getItem(AUTH_STORAGE_KEY) || localStorage.getItem(AUTH_STORAGE_KEY)
				|| document.cookie.split(';').some(cookie => cookie.trim().startsWith('afterglow_session='))) confirmed = false;
		});
	}
	return confirmed;
}

function beginLogout(all: boolean, navigate: boolean): Promise<void> {
	if (inFlight) return inFlight;
	const state = get(auth);
	const mock = isMockAuthActive();
	const owner = sessionScopeKey(state);
	const ownsSession = () => isMockAuthActive() === mock && sessionScopeKey(get(auth)) === owner;
	logoutInProgress.set(true);
	const pendingRefresh = beginSessionRevocation();
	// Attach immediately: navigation/render may outlast a rejected refresh.
	const settledRefresh = pendingRefresh.catch(() => null);
	progress.set({ phase: 'running', all, shell: 'pending', server: 'pending', local: 'pending',
		serverNotRequired: false, loginHref: mock ? '/login?tutorial=off' : '/login' });
	const result = Promise.withResolvers<void>();
	inFlight = result.promise;
	completed = null;
	// Navigation starts synchronously, before waiting for shell, refresh or server cleanup.
	const navigation = navigate ? goto('/logout', { replaceState: true }).catch(() => undefined) : Promise.resolve();
	void (async () => {
		try {
			await navigation;
			await paintLogoutPage();
			progress.update(value => ({ ...value, shell: 'active' }));
			try {
				if (!ownsSession()) throw new Error('Logout session replaced');
				await cloudShell.close('logout', { keepDock: false });
				progress.update(value => ({ ...value, shell: 'done' }));
			} catch {
				progress.update(value => ({ ...value, shell: 'warning' }));
			}
			progress.update(value => ({ ...value, server: 'active' }));
			await settledRefresh;
			const current = get(auth);
			if (!ownsSession()) {
				progress.update(value => ({ ...value, server: 'warning' }));
			} else if (mock || !current.token) {
				progress.update(value => ({ ...value, server: 'done', serverNotRequired: true }));
			} else {
				try {
					await api.post(all ? '/api/v1/auth/logout-all' : '/api/v1/auth/logout', {}, current.token,
						current.projectId ?? undefined, { suppressAuthRedirect: true });
					progress.update(value => ({ ...value, server: 'done' }));
				} catch {
					progress.update(value => ({ ...value, server: 'warning' }));
				}
			}
		} catch {
			progress.update(value => ({ ...value, shell: value.shell === 'done' ? 'done' : 'warning', server: 'warning' }));
		} finally {
			// Never discard a rotated refresh credential, or a later unrelated login.
			await settledRefresh;
			progress.update(value => ({ ...value, local: 'active' }));
			const cleared = ownsSession() && clearLocalCredentials(mock);
			progress.update(value => ({ ...value, local: cleared ? 'done' : 'warning', phase: 'complete' }));
			endSessionRevocation();
			logoutInProgress.set(false);
			completed = result.promise;
			completedOwner = sessionScopeKey(get(auth));
			inFlight = null;
			result.resolve();
		}
	})();
	return result.promise;
}

/** Explicit actions always show the logout page before awaiting any cleanup. */
export function startLogout({ all = false }: { all?: boolean } = {}): Promise<void> {
	if (inFlight) return inFlight;
	if (completed && !get(auth).token) {
		void goto('/logout', { replaceState: true }).catch(() => undefined);
		return completed;
	}
	return beginLogout(all, true);
}

/** Direct route access starts once; locale/component remounts retain the settled result. */
export function ensureLogoutStarted(): Promise<void> {
	if (inFlight) return inFlight;
	if (completed && completedOwner === sessionScopeKey(get(auth))) return completed;
	return beginLogout(false, false);
}
