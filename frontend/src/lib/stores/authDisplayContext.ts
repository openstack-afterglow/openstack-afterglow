import { derived } from 'svelte/store';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { sessionScopeKey } from '$lib/utils/authSession';

let previousKey = '';
let generation = 0;

/** Display ownership is a logical login/scope, not a rotating access credential. */
export const authDisplayContext = derived([auth, authReady, projectSwitching], ([state, ready, switching]) => {
	const key = JSON.stringify([sessionScopeKey(state), !!state.token, ready, switching,
		state.isSystemAdmin, state.isDomainManager, state.canWrite, [...(state.roles ?? [])].sort()]);
	if (key !== previousKey) {
		previousKey = key;
		generation += 1;
	}
	return {
		key: JSON.stringify([key, generation]),
		project: state.projectId,
		ready: ready && !switching && !!state.token && !!state.projectId,
	};
});
