import { derived, get, writable } from 'svelte/store';
import { api } from '$lib/api/client';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { sessionScopeKey } from '$lib/utils/authSession';

export interface ProfileImage { kind: 'gravatar' | 'generated' | 'upload'; url: string | null }
interface ImageState { image: ProfileImage | null; loading: boolean; busy: boolean; failed: boolean }
const empty = (): ImageState => ({ image: null, loading: false, busy: false, failed: false });

/** One in-memory display snapshot; no localStorage, credentials or user-image URLs survive logout. */
export function createProfileImageStore() {
	let generation = 0;
	let active = false;
	let boundary = '';
	let controller: AbortController | null = null;
	let value = empty();
	let publish: (next: ImageState) => void = () => {};
	const set = (next: ImageState) => { value = next; publish(next); };
	const allowed = () => active && !!get(auth).token && get(authReady) && !get(logoutInProgress) && !get(projectSwitching);
	const current = (revision: number) => revision === generation && allowed();
	async function load() {
		if (!allowed() || value.busy) return;
		const revision = ++generation;
		controller?.abort(); controller = new AbortController();
		const owner = get(auth);
		set({ ...value, loading: true, failed: false });
		try {
			const image = await api.get<ProfileImage>('/api/v1/profile/image', owner.token!, owner.projectId ?? undefined, { cache: 'no-store', signal: controller.signal });
			if (current(revision)) set({ image, loading: false, busy: false, failed: false });
		} catch { if (current(revision)) set({ ...empty(), failed: true }); }
	}
	const state = writable<ImageState>(empty(), (update) => {
		publish = update; active = true; boundary = '';
		const unsubscribe = derived([auth, authReady, logoutInProgress, projectSwitching], ([owner, ready, logout, switching]) =>
			JSON.stringify([sessionScopeKey(owner), !!owner.token, ready, logout, switching])).subscribe(key => {
			if (key === boundary) return;
			boundary = key; generation++; controller?.abort(); set(empty());
			if (allowed()) void load();
		});
		return () => { active = false; generation++; controller?.abort(); value = empty(); update(value); publish = () => {}; unsubscribe(); };
	});
	async function save(kind: 'gravatar' | 'generated' | 'upload', file?: File): Promise<boolean> {
		if (!allowed() || value.loading || value.busy) return false;
		const revision = ++generation;
		const owner = get(auth);
		controller?.abort(); controller = new AbortController();
		set({ ...value, busy: true, failed: false });
		try {
			const opts = { signal: controller.signal, replayOnUnauthorized: false };
			const image = kind === 'upload'
				? await api.putBlob<ProfileImage>('/api/v1/profile/image/upload', file!, owner.token!, owner.projectId ?? undefined, opts)
				: await api.put<ProfileImage>('/api/v1/profile/image', { kind }, owner.token!, owner.projectId ?? undefined, opts);
			if (!current(revision)) return false;
			set({ image, loading: false, busy: false, failed: false });
			return true;
		} finally { if (current(revision)) set({ ...value, busy: false }); }
	}
	return { subscribe: state.subscribe, save, refresh: load };
}

export const profileImage = createProfileImageStore();
