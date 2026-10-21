import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get, writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), put: vi.fn(), putBlob: vi.fn(), patch: vi.fn(), post: vi.fn() } }));
vi.mock('$lib/api/client', () => ({ api }));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token', userId: 'me', username: 'Alpha', sessionId: 'session', identityDomainId: 'home', domainId: 'personal', projectId: 'project' }),
	authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false),
}));
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { profileImage } from '$lib/stores/profileImage';
import ProfileSection from '../ProfileSection.svelte';
import ProfileImage from '../ProfileImage.svelte';

const original = { kind: 'gravatar', url: 'https://www.gravatar.com/avatar/' + 'a'.repeat(64) + '?s=128&d=404' };
const generated = { kind: 'generated', url: 'data:image/png;base64,YQ==' };
function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (error: Error) => void;
	const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
	return { promise, resolve, reject };
}
beforeEach(() => {
	vi.resetAllMocks();
	auth.update(state => ({ ...state, token: 'token', userId: 'me', username: 'Alpha', sessionId: 'session', identityDomainId: 'home', domainId: 'personal', projectId: 'project' }));
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/image') ? original : { id: 'me', name: 'Alpha', email: 'alpha@example.com', description: '' }));
});
afterEach(cleanup);

describe('profile image controls and shared header renderer', () => {
	it('selects, regenerates and resets a persisted image in every mounted consumer', async () => {
		const header = render(ProfileImage, { name: 'Alpha', label: 'Header profile' });
		render(ProfileSection);
		await waitFor(() => expect(header.container.querySelector('img')?.getAttribute('src')).toBe(original.url));
		expect(header.container.querySelector('img')?.getAttribute('referrerpolicy')).toBe('no-referrer');
		api.put.mockResolvedValueOnce(generated).mockResolvedValueOnce({ ...generated, url: 'data:image/png;base64,Yg==' }).mockResolvedValueOnce(original);
		await fireEvent.click(await screen.findByRole('button', { name: '아바타 생성' }));
		await waitFor(() => expect(header.container.querySelector('img')?.getAttribute('src')).toBe(generated.url));
		expect(screen.getByRole('button', { name: '다른 아바타 생성' }).getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(screen.getByRole('button', { name: '다른 아바타 생성' }));
		await waitFor(() => expect(header.container.querySelector('img')?.getAttribute('src')).toBe('data:image/png;base64,Yg=='));
		await fireEvent.click(screen.getByRole('button', { name: 'Gravatar 사용' }));
		await waitFor(() => expect(header.container.querySelector('img')?.getAttribute('src')).toBe(original.url));
		expect(api.put.mock.calls.map(call => call[1])).toEqual([{ kind: 'generated' }, { kind: 'generated' }, { kind: 'gravatar' }]);
	});

	it('falls back accessibly after failed Gravatar loading and for absent or unsafe URLs', async () => {
		const header = render(ProfileImage, { name: 'Alpha', label: 'Header profile' });
		await waitFor(() => expect(header.container.querySelector('img')).not.toBeNull());
		await fireEvent.error(header.container.querySelector('img')!);
		expect(header.container.querySelector('img')).toBeNull();
		expect(screen.getByRole('img', { name: 'Header profile' }).textContent).toBe('AL');
		api.get.mockResolvedValueOnce({ kind: 'gravatar', url: null });
		await profileImage.refresh();
		expect(header.container.querySelector('img')).toBeNull();
		api.get.mockResolvedValueOnce({ kind: 'upload', url: 'https://attacker.invalid/private' });
		await profileImage.refresh();
		expect(header.container.querySelector('img')).toBeNull();
	});

	it('rejects unsafe and oversized local files before dispatch and uploads raster bytes without replay', async () => {
		const view = render(ProfileSection);
		await screen.findByRole('button', { name: '아바타 생성' });
		await waitFor(() => expect(get(profileImage).loading).toBe(false));
		const input = view.container.querySelector('input[type="file"]') as HTMLInputElement;
		for (const file of [new File(['<svg/>'], 'avatar.svg', { type: 'image/svg+xml' }), new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'huge.png', { type: 'image/png' })]) {
			await fireEvent.change(input, { target: { files: [file] } });
		}
		expect(api.putBlob).not.toHaveBeenCalled();
		const pending = deferred<typeof generated>(); api.putBlob.mockReturnValue(pending.promise);
		const file = new File(['raster'], 'photo.png', { type: 'image/png' });
		await fireEvent.change(input, { target: { files: [file] } });
		expect((screen.getByRole('button', { name: '사진 업로드' }) as HTMLButtonElement).disabled).toBe(true);
		expect(api.putBlob).toHaveBeenCalledWith('/api/v1/profile/image/upload', file, 'token', 'project', { signal: expect.any(AbortSignal), replayOnUnauthorized: false });
		pending.resolve({ ...generated, kind: 'upload' });
		await waitFor(() => expect(screen.getByRole('button', { name: '사진 업로드' }).getAttribute('aria-pressed')).toBe('true'));
	});

	it('retains the saved image and allows retry after native save failure', async () => {
		const header = render(ProfileImage, { name: 'Alpha', label: 'Header profile' }); render(ProfileSection);
		await waitFor(() => expect(header.container.querySelector('img')?.getAttribute('src')).toBe(original.url));
		api.put.mockRejectedValueOnce(new Error('forbidden')).mockResolvedValueOnce(generated);
		await fireEvent.click(screen.getByRole('button', { name: '아바타 생성' }));
		await waitFor(() => expect((screen.getByRole('button', { name: '아바타 생성' }) as HTMLButtonElement).disabled).toBe(false));
		expect(header.container.querySelector('img')?.getAttribute('src')).toBe(original.url);
		await fireEvent.click(screen.getByRole('button', { name: '아바타 생성' }));
		await waitFor(() => expect(header.container.querySelector('img')?.getAttribute('src')).toBe(generated.url));
	});

	it('removes another owner image before their replacement request replies', async () => {
		const header = render(ProfileImage, { name: 'Alpha', label: 'Header profile' });
		await waitFor(() => expect(header.container.querySelector('img')?.getAttribute('src')).toBe(original.url));
		const pending = deferred<typeof original>(); api.get.mockReturnValue(pending.promise);
		auth.update(state => ({ ...state, token: 'other-token', userId: 'other', sessionId: 'other-session' }));
		await waitFor(() => expect(header.container.querySelector('img')).toBeNull());
		expect(get(profileImage).image).toBeNull();
		pending.resolve({ ...generated, kind: 'upload' });
		await waitFor(() => expect(header.container.querySelector('img')?.getAttribute('src')).toBe(generated.url));
	});
});
