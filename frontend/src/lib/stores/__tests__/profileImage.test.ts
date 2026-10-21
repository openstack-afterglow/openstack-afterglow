import { get, writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), put: vi.fn(), putBlob: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-A', userId: 'A', username: 'Alpha', sessionId: 'session-A', identityDomainId: 'home', domainId: 'personal', projectId: 'project-A' }),
	authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false),
}));
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { createProfileImageStore, type ProfileImage } from '../profileImage';

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (error: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
const original = { kind: 'gravatar' as const, url: 'https://www.gravatar.com/avatar/' + 'a'.repeat(64) + '?s=128&d=404' };
const generated = { kind: 'generated' as const, url: 'data:image/png;base64,YQ==' };
const stops: Array<() => void> = [];
beforeEach(() => {
	vi.resetAllMocks();
	auth.update(state => ({ ...state, token: 'token-A', userId: 'A', username: 'Alpha', sessionId: 'session-A', identityDomainId: 'home', domainId: 'personal', projectId: 'project-A' }));
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	api.get.mockResolvedValue(original);
});
afterEach(() => { for (const stop of stops.splice(0)) stop(); });

function mount() {
	const store = createProfileImageStore();
	stops.push(store.subscribe(() => {}));
	return store;
}

describe('profile image logical owner lifecycle', () => {
	it('loads once with no-store and publishes a persisted selection to every consumer', async () => {
		const store = mount();
		await vi.waitFor(() => expect(get(store).image).toEqual(original));
		expect(api.get).toHaveBeenCalledWith('/api/v1/profile/image', 'token-A', 'project-A', { cache: 'no-store', signal: expect.any(AbortSignal) });
		let headerImage = get(store).image;
		stops.push(store.subscribe(state => { headerImage = state.image; }));
		api.put.mockResolvedValue(generated);
		expect(await store.save('generated')).toBe(true);
		expect(headerImage).toEqual(generated);
		expect(api.put).toHaveBeenCalledWith('/api/v1/profile/image', { kind: 'generated' }, 'token-A', 'project-A', { signal: expect.any(AbortSignal), replayOnUnauthorized: false });
		auth.update(state => ({ ...state, token: 'refreshed-token-A' }));
		expect(get(store).image).toEqual(generated);
		expect(api.get).toHaveBeenCalledOnce();
	});

	it('clears synchronously and discards an A-to-B-to-A late read', async () => {
		const first = deferred<typeof original>(); const second = deferred<typeof original>(); const third = deferred<ProfileImage>();
		api.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(third.promise);
		const store = mount();
		auth.update(state => ({ ...state, userId: 'B', sessionId: 'session-B', token: 'token-B' }));
		expect(get(store).image).toBeNull();
		auth.update(state => ({ ...state, userId: 'A', sessionId: 'session-A2', token: 'token-A2' }));
		first.resolve(original); second.resolve(original);
		await Promise.resolve(); await Promise.resolve();
		expect(get(store).image).toBeNull();
		third.resolve(generated);
		await vi.waitFor(() => expect(get(store).image).toEqual(generated));
	});

	it.each(['logout', 'verification', 'scope'] as const)('fences a pending save across %s loss and restoration', async (loss) => {
		const store = mount();
		await vi.waitFor(() => expect(get(store).image).toEqual(original));
		const pending = deferred<typeof generated>(); const refresh = deferred<typeof original>();
		api.put.mockReturnValue(pending.promise); api.get.mockReturnValue(refresh.promise);
		const saved = store.save('generated');
		if (loss === 'logout') { logoutInProgress.set(true); logoutInProgress.set(false); }
		if (loss === 'verification') { authReady.set(false); authReady.set(true); }
		if (loss === 'scope') { projectSwitching.set(true); projectSwitching.set(false); }
		expect(get(store).image).toBeNull();
		pending.resolve(generated);
		expect(await saved).toBe(false);
		expect(get(store).image).toBeNull();
		refresh.resolve(original);
		await vi.waitFor(() => expect(get(store).image).toEqual(original));
	});

	it('does not resurrect an unmounted request after a new subscription', async () => {
		const pending = deferred<typeof original>();
		api.get.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(generated);
		const store = createProfileImageStore();
		const stop = store.subscribe(() => {}); stop();
		stops.push(store.subscribe(() => {}));
		await vi.waitFor(() => expect(get(store).image).toEqual(generated));
		pending.resolve(original); await Promise.resolve(); await Promise.resolve();
		expect(get(store).image).toEqual(generated);
	});

	it('uploads raw bytes without credential replay and keeps the old image after a rejected save', async () => {
		const store = mount();
		await vi.waitFor(() => expect(get(store).image).toEqual(original));
		const file = new File(['bytes'], 'photo.png', { type: 'image/png' });
		api.putBlob.mockRejectedValueOnce(new Error('denied'));
		await expect(store.save('upload', file)).rejects.toThrow('denied');
		expect(get(store).busy).toBe(false);
		expect(get(store).image).toEqual(original);
		api.putBlob.mockResolvedValue({ ...generated, kind: 'upload' });
		expect(await store.save('upload', file)).toBe(true);
		expect(api.putBlob).toHaveBeenLastCalledWith('/api/v1/profile/image/upload', file, 'token-A', 'project-A', { signal: expect.any(AbortSignal), replayOnUnauthorized: false });
	});

	it('does not dispatch while unverified or logged out and clears snapshots on project changes', async () => {
		const store = mount();
		await vi.waitFor(() => expect(get(store).image).toEqual(original));
		auth.update(state => ({ ...state, projectId: 'project-B' }));
		expect(get(store).image).toBeNull();
		await vi.waitFor(() => expect(get(store).image).toEqual(original));
		authReady.set(false);
		expect(get(store).image).toBeNull();
		expect(await store.save('generated')).toBe(false);
		auth.update(state => ({ ...state, token: null, userId: null }));
		expect(await store.save('gravatar')).toBe(false);
		expect(api.put).not.toHaveBeenCalled();
	});
});
