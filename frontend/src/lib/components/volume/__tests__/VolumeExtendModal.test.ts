import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import type { Writable } from 'svelte/store';
import { tick } from 'svelte';
import type { Volume } from '$lib/types/volume';

const { get, post, info, translate } = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), info: vi.fn(), translate: vi.fn((key: string) => key),
}));
vi.mock('$lib/api/client', () => ({ api: { get, post }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'auth-default' }), canWrite: writable(true) }));
vi.mock('$lib/stores/toast', () => ({ toast: { info } }));
vi.mock('$lib/i18n/ns/volume', () => ({ t: translate }));
import { auth, canWrite } from '$lib/stores/auth';
import VolumeExtendModal from '../VolumeExtendModal.svelte';

const available: Volume = { id: 'disk-a', name: 'Data disk', status: 'available', size: 40, attachments: [], volume_type: null };
const attached: Volume = { ...available, status: 'in-use', attachments: [{ server_id: 'server-a' }, { server_id: 'server-b' }] };
function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => { resolve = done; });
	return { promise, resolve };
}
function setup(volume: Volume = available, projectId: string | undefined = 'target-project') {
	const onclose = vi.fn();
	const onsuccess = vi.fn();
	return { ...render(VolumeExtendModal, { volume, projectId, onclose, onsuccess }), onclose, onsuccess };
}
async function submit() { await fireEvent.click(screen.getByRole('button', { name: 'extendModal.extend' })); }

beforeEach(() => {
	vi.clearAllMocks();
	auth.set({ token: 'token', projectId: 'auth-default' } as never);
	(canWrite as Writable<boolean>).set(true);
	get.mockImplementation((path: string) => path.includes('/volumes/')
		? Promise.resolve(available)
		: Promise.resolve({ id: path.split('/').at(-1), project_id: 'target-project', status: 'SHUTOFF' }));
	post.mockResolvedValue({ ...available, status: 'extending' });
});

describe('VolumeExtendModal offline provider expansion', () => {
	it('preflights and extends an available unattached disk in the explicit target scope', async () => {
		const view = setup();
		expect(screen.getByText('extendModal.guestBoundary')).toBeTruthy();
		expect(screen.getByText('extendModal.offlineRequired')).toBeTruthy();
		expect(screen.getByText('extendModal.noShrink')).toBeTruthy();
		await submit();
		await waitFor(() => expect(view.onsuccess).toHaveBeenCalledOnce());
		expect(get).toHaveBeenCalledWith('/api/v1/volumes/disk-a', 'token', 'target-project', { refresh: true });
		expect(get).toHaveBeenCalledTimes(1);
		expect(post).toHaveBeenCalledWith('/api/v1/volumes/disk-a/extend', { new_size: 50 }, 'token', 'target-project');
		expect(translate).toHaveBeenCalledWith('extendModal.accepted', { size: 40, status: 'extending' });
		expect(info).toHaveBeenCalledWith('extendModal.accepted');
	});

	it('verifies every owning multiattach server before extension', async () => {
		get.mockImplementation((path: string) => path.includes('/volumes/') ? Promise.resolve(attached)
			: Promise.resolve({ id: path.split('/').at(-1), project_id: 'target-project', status: 'SHUTOFF' }));
		setup(attached);
		await submit();
		await waitFor(() => expect(post).toHaveBeenCalledOnce());
		expect(get).toHaveBeenCalledWith('/api/v1/instances/server-a', 'token', 'target-project', { refresh: true });
		expect(get).toHaveBeenCalledWith('/api/v1/instances/server-b', 'token', 'target-project', { refresh: true });
	});

	it.each([
		{ id: 'server-a', status: 'ACTIVE', project_id: 'target-project' },
		{ id: 'server-a', status: 'UNKNOWN', project_id: 'target-project' },
		{ id: 'server-a', status: 'SHUTOFF', project_id: 'foreign' },
		{ id: 'server-a', status: 'SHUTOFF' },
		{ id: 'wrong-server', status: 'SHUTOFF', project_id: 'target-project' },
	])('fails closed for attachment ownership or state %j', async (server) => {
		get.mockImplementation((path: string) => Promise.resolve(path.includes('/volumes/') ? attached : server));
		setup(attached);
		await submit();
		await waitFor(() => expect(screen.getAllByText('extendModal.offlineRequired')).toHaveLength(2));
		expect(post).not.toHaveBeenCalled();
	});

	it.each(['40', '39', '50.5', '2147483648', '', '-1'])('rejects shrink/equal/noninteger/out-of-range capacity %s', async (value) => {
		setup();
		await fireEvent.input(screen.getByRole('spinbutton'), { target: { value } });
		expect(screen.getByRole('button', { name: 'extendModal.extend' }).hasAttribute('disabled')).toBe(true);
		await submit();
		expect(get).not.toHaveBeenCalled();
		expect(post).not.toHaveBeenCalled();
	});

	it.each([
		{ ...available, status: 'extending' },
		{ ...available, status: 'error' },
		{ ...available, size: 2147483647 },
		{ ...available, status: 'in-use' },
		{ ...available, attachments: [{ server_id: 'server-a' }] },
	])('rejects an unavailable target %j', (volume) => {
		setup(volume);
		expect(screen.getByRole('button', { name: 'extendModal.extend' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByText('extendModal.targetUnavailable')).toBeTruthy();
	});

	it.each([
		{ ...available, size: 45 },
		{ ...available, status: 'extending' },
		{ ...available, id: 'disk-b' },
	])('does not send from a stale or mismatched authoritative volume %j', async (current) => {
		get.mockResolvedValue(current);
		setup();
		await submit();
		await screen.findByText('extendModal.targetUnavailable');
		expect(post).not.toHaveBeenCalled();
	});

	it('never falls back to auth default when target scope is unavailable', () => {
		const onclose = vi.fn();
		render(VolumeExtendModal, { volume: available, projectId: undefined, onclose, onsuccess: vi.fn() });
		expect(screen.getByRole('button', { name: 'extendModal.extend' }).hasAttribute('disabled')).toBe(true);
		expect(get).not.toHaveBeenCalled();
	});

	it('does not retarget an open modal after a project transition or ABA restoration', async () => {
		const view = setup();
		await view.rerender({ volume: available, projectId: 'other-project', onclose: view.onclose, onsuccess: view.onsuccess });
		await view.rerender({ volume: available, projectId: 'target-project', onclose: view.onclose, onsuccess: view.onsuccess });
		expect(screen.getByRole('button', { name: 'extendModal.extend' }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByText('extendModal.scopeChanged')).toBeTruthy();
		expect(get).not.toHaveBeenCalled();
	});

	it('discards preflight and remains invalidated after write permission is revoked and restored', async () => {
		const pending = deferred<Volume>();
		get.mockReturnValue(pending.promise);
		setup();
		await submit();
		(canWrite as Writable<boolean>).set(false);
		await tick();
		(canWrite as Writable<boolean>).set(true);
		await tick();
		pending.resolve(available);
		await waitFor(() => expect(screen.getByRole('button', { name: 'extendModal.cancel' }).hasAttribute('disabled')).toBe(false));
		expect(post).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: 'extendModal.extend' }).hasAttribute('disabled')).toBe(true);
	});

	it('blocks cancel and Escape while extending and suppresses late success after token change', async () => {
		const pending = deferred<Volume>();
		post.mockReturnValue(pending.promise);
		const view = setup();
		await submit();
		await waitFor(() => expect(post).toHaveBeenCalledOnce());
		await fireEvent.click(screen.getByRole('button', { name: 'extendModal.cancel' }));
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		expect(view.onclose).not.toHaveBeenCalled();
		auth.set({ token: 'other-token', projectId: 'auth-default' } as never);
		await tick();
		pending.resolve({ ...available, status: 'extending' });
		await tick();
		await tick();
		expect(view.onsuccess).not.toHaveBeenCalled();
		expect(info).not.toHaveBeenCalled();
	});
});
