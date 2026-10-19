import { get } from 'svelte/store';
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import type { TelemetryAuthority } from '$lib/api/adminTelemetry';

export interface TelemetryCapture { authority: TelemetryAuthority; current: () => boolean }
export interface TelemetryContext {
	allowed(): boolean;
	capture(): TelemetryCapture | null;
	dispose(): void;
}

/** One mounted consumer owns every private read, draft and pending confirmation. No shared cache. */
export function createTelemetryContext(onChange: () => void): TelemetryContext {
	let generation = 0;
	let disposed = false;
	const fingerprint = () => {
		const state = get(auth);
		return JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId,
			state.token, state.projectId, state.isSystemAdmin, get(authReady), get(projectSwitching), get(logoutInProgress)]);
	};
	let key = fingerprint();
	const allowed = () => {
		const state = get(auth);
		return !disposed && get(authReady) && !get(projectSwitching) && !get(logoutInProgress)
			&& !!state.token && !!state.userId && state.isSystemAdmin;
	};
	const changed = () => {
		const next = fingerprint();
		if (next === key || disposed) return;
		key = next;
		++generation;
		// Store subscribers run synchronously: A → B → A cannot revive an earlier response.
		onChange();
	};
	const unsubscribers = [auth.subscribe(changed), authReady.subscribe(changed), projectSwitching.subscribe(changed), logoutInProgress.subscribe(changed)];
	return {
		allowed,
		capture(): TelemetryCapture | null {
			if (!allowed()) return null;
			const ticket = generation;
			const state = get(auth);
			return {
				authority: { token: state.token!, projectId: state.projectId ?? '' },
				current: () => allowed() && ticket === generation,
			};
		},
		dispose() {
			if (disposed) return;
			disposed = true;
			++generation;
			for (const unsubscribe of unsubscribers) unsubscribe();
		},
	};
}
