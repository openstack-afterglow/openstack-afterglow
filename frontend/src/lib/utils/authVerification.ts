import { get } from 'svelte/store';
import { api, ApiError } from '$lib/api/client';
import {
	auth, authReady, authRecovery, logoutInProgress, clearAuth, isMockAuthActive,
	getAuthVerificationEpoch, hasVerifiedAuth, acceptAuthVerification,
} from '$lib/stores/auth';
import type { AuthState } from '$lib/stores/auth';
import type { AuthMeResponse } from '$lib/types/auth';
import { meAuthState } from './authSession';

export interface AuthVerificationController {
	setEnabled(value: boolean): void;
	dispose(): void;
}

/** Root /me verification for restored/unverified credentials, with scope-owned retries. */
export function createAuthVerificationController(): AuthVerificationController {
	let enabled = false;
	let disposed = false;
	let active: { epoch: number; abort: AbortController; timer?: number } | null = null;

	function cancel() {
		if (active?.timer) clearTimeout(active.timer);
		active?.abort.abort();
		active = null;
	}

	function sync() {
		const state = get(auth);
		if (disposed || !enabled || !state.token || isMockAuthActive() || get(logoutInProgress) || hasVerifiedAuth()) {
			cancel();
			return;
		}
		const epoch = getAuthVerificationEpoch();
		if (active?.epoch === epoch) return;
		cancel();
		const request = { epoch, abort: new AbortController(), timer: undefined as number | undefined };
		active = request;
		const current = () => active === request && enabled && !disposed && !request.abort.signal.aborted
			&& epoch === getAuthVerificationEpoch() && !isMockAuthActive() && !get(logoutInProgress);
		void (async () => {
			try {
				// Own the terminal rejection here: even a same-token ABA must not let
				// the client's asynchronous 401 redirect clear a newer login.
				const me = await api.get<AuthMeResponse>('/api/v1/auth/me', state.token!, state.projectId ?? undefined,
					{ refresh: true, signal: request.abort.signal, suppressAuthRedirect: true });
				if (!current()) return;
				let verified: Partial<AuthState>;
				try {
					verified = meAuthState(me, state);
				} catch {
					clearAuth();
					return;
				}
				acceptAuthVerification(epoch, verified);
			} catch (error) {
				if (!current()) return;
				if (error instanceof ApiError && error.status === 401) {
					clearAuth();
					return;
				}
				authReady.set(false);
				if (get(authRecovery)?.token !== state.token) {
					authRecovery.set({ token: state.token!, retryAt: Date.now() + 5000 });
				}
				request.timer = window.setTimeout(() => {
					if (!current()) return;
					active = null;
					sync();
				}, 5000);
			}
		})();
	}

	// Synchronous subscriptions revoke in-flight work even when Svelte batches an
	// A -> B -> A transition into a single render/effect flush.
	const unsubscribeAuth = auth.subscribe(sync);
	const unsubscribeLogout = logoutInProgress.subscribe(sync);
	return {
		setEnabled(value: boolean) { enabled = value; sync(); },
		dispose() {
			disposed = true;
			cancel();
			unsubscribeAuth();
			unsubscribeLogout();
		},
	};
}
