import { readable } from 'svelte/store';
import { auth, type AuthState } from './auth';

/** The verified working domain is the selected project's domain, not the credential home. */
export function chatDomainKey(actor: AuthState): string | null {
	return actor.token && actor.userId && actor.projectId && actor.domainId
		? JSON.stringify([actor.sessionId, actor.identityDomainId, actor.userId, actor.domainId])
		: null;
}

/** Publish owner changes synchronously, including a batched A → B → A. */
export const chatDomainScope = readable({ key: null as string | null, revision: 0 }, (set) => {
	let key: string | null = null;
	let revision = 0;
	return auth.subscribe((actor) => {
		const next = chatDomainKey(actor);
		if (next === key) return;
		key = next;
		set({ key, revision: ++revision });
	});
});

/** Session storage is account-bound but survives token rotation and same-domain rescope. */
export function chatHistoryStorageOwner(actor: AuthState): string | null {
	return chatDomainKey(actor) ? JSON.stringify([actor.identityDomainId, actor.userId, actor.domainId]) : null;
}
