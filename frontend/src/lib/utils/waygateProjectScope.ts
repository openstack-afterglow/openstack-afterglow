import { readable, type Readable } from 'svelte/store';

interface WaygateCredentials {
	token: string | null | undefined;
	projectId: string | null | undefined;
}

export interface WaygateProjectScope {
	readonly token: string;
	readonly projectId: string;
	isCurrent(): boolean;
}

/**
 * Each credential transition creates a new workspace lifetime, even A → B → A
 * in one render tick. Invalidate synchronously, before Svelte tears down the old
 * workspace, so pending confirmations, downloads and mutations cannot resume.
 * Missing credentials never produce a scope (nor an implicit all-project call).
 */
export function createWaygateProjectScope(auth: Readable<WaygateCredentials>) {
	return readable<WaygateProjectScope | null>(null, (set) => {
		let previous: WaygateCredentials | undefined;
		let invalidate = () => {};
		const unsubscribe = auth.subscribe(({ token, projectId }) => {
			if (previous?.token === token && previous?.projectId === projectId) return;
			previous = { token, projectId };
			invalidate();
			if (!token?.trim() || !projectId?.trim()) {
				set(null);
				return;
			}
			let current = true;
			invalidate = () => { current = false; };
			set({ token, projectId, isCurrent: () => current });
		});
		return () => {
			invalidate();
			unsubscribe();
		};
	});
}
