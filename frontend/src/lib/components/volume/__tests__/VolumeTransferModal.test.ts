import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable, type Writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), copy: vi.fn() }));
vi.mock('$lib/api/client', () => {
	class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	}
	return { api: mocks, ApiError };
});
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', userId: 'user-a', projectId: 'destination-a', projectName: 'Destination A', canWrite: true }),
	canWrite: writable(true),
	projectSwitching: writable(false),
}));
vi.mock('$lib/i18n/ns/volume', () => ({ t: (key: string) => key }));
import { auth, canWrite, projectSwitching } from '$lib/stores/auth';
import { ApiError } from '$lib/api/client';
import VolumeTransferModal from '../VolumeTransferModal.svelte';

const idA = '11111111-1111-4111-8111-111111111111';
const idB = '22222222-2222-4222-8222-222222222222';
const origin = {
	id: idA, name: 'handoff', volume_id: 'volume-from-source', created_at: null,
	volume_name: 'Source data', size: 12, volume_type: 'ssd', status: 'awaiting-transfer',
	source_project: { id: 'source-project-full-id', name: 'Source project' },
	source_domain: { id: 'source-domain-full-id', name: 'Source domain' },
};
const initialAuth = { token: 'token-a', userId: 'user-a', projectId: 'destination-a', projectName: 'Destination A', canWrite: true };
function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
	return { promise, resolve, reject };
}
function setup(initialMode: 'create' | 'receive' | 'list' = 'receive') {
	const callbacks = { onClose: vi.fn(), onChanged: vi.fn(), onTransferred: vi.fn() };
	return { ...render(VolumeTransferModal, { initialMode, volumeId: initialMode === 'create' ? 'source-volume' : '', ...callbacks }), ...callbacks };
}
async function setId(id: string) {
	await fireEvent.input(screen.getByLabelText('transferModal.idLabel'), { target: { value: id } });
}
async function search(id = idA) {
	await setId(id);
	await fireEvent.click(screen.getByRole('button', { name: 'transferModal.search' }));
}
async function found() { await screen.findByText('Source domain'); }
async function enterKey() {
	await fireEvent.input(screen.getByLabelText('transferModal.authKeyLabel'), { target: { value: 'sender-secret' } });
}
const receiveButton = () => screen.getByRole('button', { name: 'transferModal.receiveTitle' }) as HTMLButtonElement;

beforeEach(() => {
	vi.clearAllMocks();
	auth.set(initialAuth as never);
	(canWrite as Writable<boolean>).set(true);
	projectSwitching.set(false);
	mocks.get.mockResolvedValue(origin);
	mocks.post.mockResolvedValue({ ...origin, auth_key: 'issued-secret' });
	mocks.delete.mockResolvedValue(undefined);
	mocks.copy.mockResolvedValue(undefined);
	Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: mocks.copy } });
});

describe('VolumeTransferModal request and secret lifecycle', () => {
	it('invalidates the displayed origin and key immediately on ID edit and does not search implicitly', async () => {
		setup();
		await search();
		await found();
		await enterKey();
		expect(receiveButton().disabled).toBe(false);
		await setId(idB);
		expect(screen.queryByText('Source domain')).toBeNull();
		expect(screen.queryByLabelText('transferModal.authKeyLabel')).toBeNull();
		expect(receiveButton().disabled).toBe(true);
		expect(mocks.get).toHaveBeenCalledTimes(1);
		await fireEvent.click(receiveButton());
		expect(mocks.post).not.toHaveBeenCalled();
	});

	it.each(['success', 'failure'])('ignores a superseded lookup %s without clearing the newer result or key', async (outcome) => {
		const old = deferred<typeof origin>();
		mocks.get.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ ...origin, id: idB, volume_name: 'New data' });
		setup();
		await search();
		await search(idB);
		await screen.findByText('New data');
		await enterKey();
		if (outcome === 'success') old.resolve(origin);
		else old.reject(new ApiError(404, 'old missing'));
		await tick();
		await tick();
		expect(screen.queryByText('Source data')).toBeNull();
		expect(screen.queryByText('transferModal.notFound')).toBeNull();
		expect((screen.getByLabelText('transferModal.authKeyLabel') as HTMLInputElement).value).toBe('sender-secret');
		expect(receiveButton().disabled).toBe(false);
	});

	it.each(['token', 'userId', 'projectId', 'canWrite'] as const)('discards an in-flight lookup across an auth %s ABA transition', async (field) => {
		const pending = deferred<typeof origin>();
		mocks.get.mockReturnValueOnce(pending.promise);
		setup();
		await search();
		auth.set({ ...initialAuth, [field]: field === 'canWrite' ? false : 'other' } as never);
		auth.set(initialAuth as never);
		pending.resolve(origin);
		await tick();
		await tick();
		expect(screen.queryByText('Source domain')).toBeNull();
		expect(screen.queryByLabelText('transferModal.authKeyLabel')).toBeNull();
		expect(screen.getByText('transferModal.scopeChanged')).toBeTruthy();
	});

	it('discards an entered key on write-capability revocation even after restoration', async () => {
		setup();
		await search();
		await found();
		await enterKey();
		(canWrite as Writable<boolean>).set(false);
		(canWrite as Writable<boolean>).set(true);
		await tick();
		expect(screen.queryByLabelText('transferModal.authKeyLabel')).toBeNull();
		expect(screen.queryByText('Source domain')).toBeNull();
		expect(screen.getByText('transferModal.scopeChanged')).toBeTruthy();
	});

	it('discards issued credentials before project rescope starts', async () => {
		setup('create');
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.createTitle' }));
		await screen.findByText('issued-secret');
		projectSwitching.set(true);
		await tick();
		expect(screen.queryByText('issued-secret')).toBeNull();
		expect(screen.queryByRole('button', { name: 'transferModal.copyKey' })).toBeNull();
	});

	it('guards dismissal while receiving and suppresses stale mutation callbacks after scope changes', async () => {
		const pending = deferred<unknown>();
		mocks.post.mockReturnValueOnce(pending.promise);
		const view = setup();
		await search();
		await found();
		await enterKey();
		await fireEvent.click(receiveButton());
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.close' }));
		await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
		expect(view.onClose).not.toHaveBeenCalled();
		auth.set({ ...initialAuth, token: 'rotated-token' } as never);
		pending.resolve({ id: idA });
		await tick();
		await tick();
		expect(view.onTransferred).not.toHaveBeenCalled();
		expect(view.onClose).not.toHaveBeenCalled();
		expect(screen.queryByLabelText('transferModal.authKeyLabel')).toBeNull();
	});

	it('keeps a native wrong-key error inline, clears the attempted secret, and invalidates a consumed transfer', async () => {
		mocks.post.mockRejectedValueOnce(new ApiError(403, 'native key rejected')).mockRejectedValueOnce(new ApiError(404, 'consumed'));
		const view = setup();
		await search();
		await found();
		const key = screen.getByLabelText('transferModal.authKeyLabel') as HTMLInputElement;
		expect(key.type).toBe('password');
		await enterKey();
		await fireEvent.click(receiveButton());
		await screen.findByRole('alert');
		expect(key.value).toBe('');
		expect(receiveButton().disabled).toBe(true);
		expect(view.onTransferred).not.toHaveBeenCalled();
		await enterKey();
		await fireEvent.click(receiveButton());
		await screen.findByText('transferModal.notFound');
		expect(screen.queryByText('Source domain')).toBeNull();
		expect(screen.queryByLabelText('transferModal.authKeyLabel')).toBeNull();
	});

	it('shows an unknown transfer inline without exposing the key control', async () => {
		mocks.get.mockRejectedValueOnce(new ApiError(404, 'missing'));
		setup();
		await search();
		await screen.findByText('transferModal.notFound');
		expect(screen.queryByLabelText('transferModal.authKeyLabel')).toBeNull();
		expect(receiveButton().disabled).toBe(true);
	});

	it('does not publish issuance secrets or refresh callbacks after unmount and reopen', async () => {
		const pending = deferred<{ auth_key: string }>();
		mocks.post.mockReturnValueOnce(pending.promise);
		const old = setup('create');
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.createTitle' }));
		old.unmount();
		setup('create');
		pending.resolve({ auth_key: 'obsolete-secret' });
		await tick();
		await tick();
		expect(screen.queryByText('obsolete-secret')).toBeNull();
		expect(old.onChanged).not.toHaveBeenCalled();
		expect(screen.getByRole('button', { name: 'transferModal.createTitle' })).toBeTruthy();
	});

	it('does not publish an old lookup into a reopened receiving task', async () => {
		const pending = deferred<typeof origin>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const old = setup();
		await search();
		old.unmount();
		setup();
		pending.resolve(origin);
		await tick();
		await tick();
		expect(screen.queryByText('Source domain')).toBeNull();
		expect((screen.getByLabelText('transferModal.idLabel') as HTMLInputElement).value).toBe('');
		expect(receiveButton().disabled).toBe(true);
	});

	it('retains one-time credentials and offers manual recovery after clipboard failure, then discards them on close', async () => {
		mocks.copy.mockRejectedValueOnce(new Error('clipboard denied'));
		const view = setup('create');
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.createTitle' }));
		await screen.findByText('issued-secret');
		expect(view.onChanged).toHaveBeenCalledOnce();
		expect(view.onTransferred).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.copyId' }));
		await screen.findByText('transferModal.copyFailed');
		expect(screen.getByText('issued-secret')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.copyKey' }));
		await screen.findByRole('button', { name: 'transferModal.copied' });
		expect(mocks.copy).toHaveBeenLastCalledWith('issued-secret');
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.close' }));
		expect(view.onClose).toHaveBeenCalledOnce();
		expect(screen.queryByText('issued-secret')).toBeNull();
	});

	it('suppresses pending list publication and cancellation refresh after auth teardown', async () => {
		mocks.get.mockResolvedValueOnce([origin]);
		const pending = deferred<unknown>();
		mocks.delete.mockReturnValueOnce(pending.promise);
		const view = setup('list');
		await screen.findByText(idA);
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.cancelNamed' }));
		auth.set({ ...initialAuth, userId: 'other-user' } as never);
		pending.resolve(undefined);
		await tick();
		await tick();
		expect(view.onChanged).not.toHaveBeenCalled();
		expect(screen.queryByText(idA)).toBeNull();
		expect(screen.getByText('transferModal.scopeChanged')).toBeTruthy();
	});

	it('ignores an own-pending list received after permission revocation', async () => {
		const pending = deferred<unknown>();
		mocks.get.mockReturnValueOnce(pending.promise);
		setup('list');
		await waitFor(() => expect(screen.getByText('transferModal.busy')).toBeTruthy());
		(canWrite as Writable<boolean>).set(false);
		pending.resolve([origin]);
		await tick();
		await tick();
		expect(screen.queryByText(idA)).toBeNull();
		expect(screen.queryByRole('button', { name: 'transferModal.cancelNamed' })).toBeNull();
	});
});
