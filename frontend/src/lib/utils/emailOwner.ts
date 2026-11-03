import { onMount } from 'svelte';
import { get } from 'svelte/store';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { sessionScopeKey } from '$lib/utils/authSession';

/** Synchronous subscription fencing catches same-tick A→B→A; bearer renewal is not ownership. */
export function createEmailOwner(reset: () => void, admin = true) {
	let mounted = false;
	let epoch = 0;
	function allowed() {
		const state = get(auth);
		return mounted && !!state.token && get(authReady) && !get(logoutInProgress)
			&& !get(projectSwitching) && (!admin || state.isSystemAdmin);
	}
	function capture() {
		if (!allowed()) return null;
		const state = get(auth), ticket = epoch;
		return { token: state.token!, project: state.projectId ?? undefined,
			current: () => allowed() && ticket === epoch };
	}
	onMount(() => {
		mounted = true;
		let previous = '';
		const changed = () => {
			const state = get(auth);
			const next = JSON.stringify([sessionScopeKey(state), !!state.token, state.isSystemAdmin,
				[...state.roles].sort(), get(authReady), get(logoutInProgress), get(projectSwitching)]);
			if (next === previous) return;
			previous = next; epoch++; reset();
		};
		const subscriptions = [auth.subscribe(changed), authReady.subscribe(changed),
			logoutInProgress.subscribe(changed), projectSwitching.subscribe(changed)];
		return () => { mounted = false; epoch++; subscriptions.forEach(unsubscribe => unsubscribe()); reset(); };
	});
	return { capture };
}
