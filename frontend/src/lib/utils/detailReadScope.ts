import { derived, type Readable } from 'svelte/store';
import { authDisplayContext } from '$lib/stores/authDisplayContext';
import { siteConfig } from '$lib/config/site';

/** Synchronous logical-owner/resource/base epochs also fence same-tick ABA transitions. */
export function createDetailReadScope(resourceId: Readable<string>) {
	let previous = '';
	let revision = 0;
	let current: DetailReadScope;
	return derived([resourceId, authDisplayContext, siteConfig], ([id, owner, config]) => {
		const identity = JSON.stringify([id, owner.key, config.runtime.api_base]);
		if (identity !== previous) {
			previous = identity;
			current = { id, revision: ++revision, ready: owner.ready && !!id };
		}
		return current;
	});
}

export type DetailReadScope = { id: string; revision: number; ready: boolean };
