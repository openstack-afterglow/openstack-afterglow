import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { auth } from '$lib/stores/auth';

const { get, post, remove, errorToast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), remove: vi.fn(), errorToast: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get, post, delete: remove }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: errorToast } }));
vi.mock('$lib/i18n/ns/instance', () => ({ t: (key: string) => key }));
import { tick } from 'svelte';
import ScopeWrapper from './_StorageAttachmentsScopeWrapper.svelte';

function deferred<T>() {
	let resolve!: (value: T) => void;
	let reject!: (reason: unknown) => void;
	const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
	return { promise, resolve, reject };
}
const key = (name: string) => `storageAttachments.${name}`;
const uuid = '2c3e9ee7-60fd-4bfa-96bd-e981d55132b1';
const catalog = [{ id: 'storage-a', name: 'storage-a', status: 'available', share_proto: 'NFS' }];
const grant = {
	file_storage_id: 'storage-a', name: 'authorized-storage', share_proto: 'NFS', status: 'available',
	access_id: 'rule-a', access_type: 'ip', access_to: '10.0.0.7', access_level: 'rw', state: 'active',
	association_state: 'tracked', managed: true, exports: ['10.0.0.2:/share-a'], share_network_id: null, share_network: null,
};
const cephGrant = { ...grant, share_proto: 'CEPHFS', access_type: 'cephx', access_to: `afterglow-${uuid.replaceAll('-', '')}` };
const secretResponse = { ...cephGrant, secret: { type: 'cephx_key', value: 'scope-transient-secret' } };
async function action(id: string) { await fireEvent.click(screen.getByTestId(id)); }
async function openForm() {
	await fireEvent.click(screen.getByRole('button', { name: key('openGrant') }));
	await screen.findByRole('option', { name: /storage-a/ });
}
async function startGrant() {
	await openForm();
	await fireEvent.change(screen.getByLabelText(key('storageLabel')), { target: { value: 'storage-a' } });
	await fireEvent.change(screen.getByLabelText(key('fixedIpLabel')), { target: { value: '10.0.0.7' } });
	await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
	await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
}
async function revealSecret() {
	get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/file-storage' ? catalog : [cephGrant]));
	post.mockResolvedValue(secretResponse);
	render(ScopeWrapper, { initialInstanceId: uuid });
	await fireEvent.click(await screen.findByRole('button', { name: key('connectionInfo') }));
	await screen.findByText('scope-transient-secret');
}

describe('StorageAttachmentsSection reactive scope ownership', () => {
	beforeEach(() => {
		vi.resetAllMocks();
		auth.update(state => ({ ...state, token: null, canWrite: true, isSystemAdmin: false, roles: ['member'] }));
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/file-storage' ? catalog : []));
		post.mockResolvedValue(grant);
		remove.mockResolvedValue(undefined);
	});

	it('retains a loaded project catalog across same-project missing and instance transitions', async () => {
		render(ScopeWrapper);
		await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/instances/instance-a/storage-attachments', undefined, 'project-a'));
		await openForm();
		expect(get.mock.calls.filter(([path]) => path === '/api/v1/file-storage')).toHaveLength(1);
		await action('clear-instance');
		await action('set-instance-b');
		await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/instances/instance-b/storage-attachments', undefined, 'project-a'));
		await openForm();
		expect(get.mock.calls.filter(([path]) => path === '/api/v1/file-storage')).toHaveLength(1);
	});

	it('discards stale A-to-B-to-A attachment completions', async () => {
		const firstA = deferred<unknown[]>();
		const b = deferred<unknown[]>();
		const finalA = deferred<unknown[]>();
		get.mockImplementation((path: string) => {
			if (path.includes('/instances/instance-a/')) return get.mock.calls.filter(([called]) => called === path).length === 1 ? firstA.promise : finalA.promise;
			if (path.includes('/instances/instance-b/')) return b.promise;
			return Promise.resolve(catalog);
		});
		render(ScopeWrapper);
		await action('set-instance-b');
		await action('set-instance-a');
		firstA.resolve([{ ...grant, name: 'stale-a' }]);
		b.resolve([{ ...grant, name: 'stale-b' }]);
		finalA.resolve([]);
		await screen.findByText(key('empty'));
		expect(screen.queryByText('stale-a')).toBeNull();
		expect(screen.queryByText('stale-b')).toBeNull();
	});

	it('discards stale project A-to-B-to-A catalog responses and reloads the final scope', async () => {
		const firstA = deferred<unknown[]>();
		const b = deferred<unknown[]>();
		let aCalls = 0;
		get.mockImplementation((path: string, _token: unknown, project: string) => {
			if (path !== '/api/v1/file-storage') return Promise.resolve([]);
			if (project === 'project-b') return b.promise;
			return ++aCalls === 1 ? firstA.promise : Promise.resolve(catalog);
		});
		render(ScopeWrapper);
		await fireEvent.click(screen.getByRole('button', { name: key('openGrant') }));
		await action('set-project-b');
		await fireEvent.click(screen.getByRole('button', { name: key('openGrant') }));
		await action('set-project-a');
		await openForm();
		firstA.resolve([{ ...catalog[0], id: 'stale-a', name: 'stale-a' }]);
		b.resolve([{ ...catalog[0], id: 'stale-b', name: 'stale-b' }]);
		await Promise.resolve();
		expect(screen.queryByRole('option', { name: /stale-a|stale-b/ })).toBeNull();
		expect(screen.getByRole('option', { name: /storage-a/ })).toBeTruthy();
		expect(aCalls).toBe(2);
	});

	it.each(['set-instance-b', 'set-project-b', 'clear-project', 'clear-instance'])('suppresses a late grant result after %s', async transition => {
		const mutation = deferred<unknown>();
		post.mockReturnValue(mutation.promise);
		render(ScopeWrapper);
		await startGrant();
		await action(transition);
		const readsBeforeCompletion = get.mock.calls.length;
		mutation.resolve(secretResponse);
		await mutation.promise;
		await Promise.resolve();
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
		expect(screen.queryByText(key('connectionDetails'))).toBeNull();
		expect(get).toHaveBeenCalledTimes(readsBeforeCompletion);
		expect(errorToast).not.toHaveBeenCalled();
	});

	it('suppresses a grant result after leaving and returning to the original instance', async () => {
		const mutation = deferred<unknown>();
		post.mockReturnValue(mutation.promise);
		render(ScopeWrapper);
		await startGrant();
		await action('set-instance-b');
		await action('set-instance-a');
		const reads = get.mock.calls.length;
		mutation.resolve(secretResponse);
		await mutation.promise;
		await Promise.resolve();
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
		expect(get).toHaveBeenCalledTimes(reads);
	});

	it('suppresses stale grant errors rather than notifying the new scope', async () => {
		const mutation = deferred<unknown>();
		post.mockReturnValue(mutation.promise);
		render(ScopeWrapper);
		await startGrant();
		await action('set-project-b');
		mutation.reject(new Error('old project failure'));
		await mutation.promise.catch(() => undefined);
		expect(errorToast).not.toHaveBeenCalled();
	});

	it('rechecks permission synchronously at the grant boundary before reactive hiding', async () => {
		render(ScopeWrapper);
		await openForm();
		await fireEvent.change(screen.getByLabelText(key('storageLabel')), { target: { value: 'storage-a' } });
		await fireEvent.change(screen.getByLabelText(key('fixedIpLabel')), { target: { value: '10.0.0.7' } });
		const button = screen.getByRole('button', { name: key('grant') });
		auth.update(state => ({ ...state, canWrite: false, roles: ['reader'] }));
		button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(post).not.toHaveBeenCalled();
	});

	it('rechecks permission synchronously at revoke and explicit connection-info boundaries', async () => {
		get.mockResolvedValue([cephGrant]);
		render(ScopeWrapper, { initialInstanceId: uuid });
		const revoke = await screen.findByRole('button', { name: key('revoke') });
		const info = screen.getByRole('button', { name: key('connectionInfo') });
		auth.update(state => ({ ...state, canWrite: false, roles: ['reader'] }));
		revoke.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		info.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(remove).not.toHaveBeenCalled();
		expect(post).not.toHaveBeenCalled();
	});

	it('invalidates an in-flight grant on permission loss even when permission returns', async () => {
		const mutation = deferred<unknown>();
		post.mockReturnValue(mutation.promise);
		render(ScopeWrapper);
		await startGrant();
		await action('lose-permission');
		expect(screen.queryByRole('button', { name: key('openGrant') })).toBeNull();
		await action('restore-permission');
		mutation.resolve(secretResponse);
		await mutation.promise;
		await Promise.resolve();
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
		expect(screen.queryByText(key('connectionDetails'))).toBeNull();
	});

	it('rejects a selected fixed IP removed from the current controller instance', async () => {
		render(ScopeWrapper);
		await openForm();
		await fireEvent.change(screen.getByLabelText(key('storageLabel')), { target: { value: 'storage-a' } });
		await fireEvent.change(screen.getByLabelText(key('fixedIpLabel')), { target: { value: '10.0.0.7' } });
		await action('change-fixed-ip');
		await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
		expect(post).not.toHaveBeenCalled();
		expect(screen.getByRole('option', { name: '10.0.0.9' })).toBeTruthy();
		expect(screen.queryByRole('option', { name: '10.0.0.7' })).toBeNull();
	});

	it('disables a grant while the controller instance payload belongs to another target', async () => {
		render(ScopeWrapper);
		await openForm();
		await fireEvent.change(screen.getByLabelText(key('storageLabel')), { target: { value: 'storage-a' } });
		await fireEvent.change(screen.getByLabelText(key('fixedIpLabel')), { target: { value: '10.0.0.7' } });
		await action('mismatch-target');
		await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
		expect(post).not.toHaveBeenCalled();
	});

	it.each(['set-instance-b', 'set-project-b', 'clear-project', 'lose-permission', 'mismatch-target'])('clears a disclosed secret and details on %s', async transition => {
		await revealSecret();
		await action(transition);
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
		expect(screen.queryByText(key('connectionDetails'))).toBeNull();
		if (transition === 'lose-permission') await action('restore-permission');
		if (transition === 'mismatch-target') await action('restore-target');
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
	});

	it.each(['set-instance-b', 'set-project-b', 'lose-permission'])('suppresses a late explicit secret response after %s', async transition => {
		const mutation = deferred<unknown>();
		get.mockResolvedValue([cephGrant]);
		post.mockReturnValue(mutation.promise);
		render(ScopeWrapper, { initialInstanceId: uuid });
		await fireEvent.click(await screen.findByRole('button', { name: key('connectionInfo') }));
		await action(transition);
		if (transition === 'lose-permission') await action('restore-permission');
		mutation.resolve(secretResponse);
		await mutation.promise;
		await Promise.resolve();
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
		expect(screen.queryByText(key('connectionDetails'))).toBeNull();
	});

	it('suppresses late explicit secret results when the form reopens', async () => {
		const mutation = deferred<unknown>();
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/file-storage' ? catalog : [cephGrant]));
		post.mockReturnValue(mutation.promise);
		render(ScopeWrapper, { initialInstanceId: uuid });
		await fireEvent.click(await screen.findByRole('button', { name: key('connectionInfo') }));
		await fireEvent.click(screen.getByRole('button', { name: key('openGrant') }));
		mutation.resolve(secretResponse);
		await mutation.promise;
		await Promise.resolve();
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
		expect(screen.queryByText(key('connectionDetails'))).toBeNull();
	});

	it('suppresses stale revoke completions without reloading the new scope', async () => {
		const mutation = deferred<void>();
		get.mockResolvedValue([grant]);
		remove.mockReturnValue(mutation.promise);
		render(ScopeWrapper);
		await fireEvent.click(await screen.findByRole('button', { name: key('revoke') }));
		await action('set-project-b');
		const reads = get.mock.calls.length;
		mutation.resolve(undefined);
		await mutation.promise;
		await Promise.resolve();
		expect(get).toHaveBeenCalledTimes(reads);
		expect(errorToast).not.toHaveBeenCalled();
	});

	it('does not leave the new scope busy when an old revoke fails', async () => {
		const mutation = deferred<void>();
		get.mockResolvedValue([grant]);
		remove.mockReturnValueOnce(mutation.promise);
		render(ScopeWrapper);
		await fireEvent.click(await screen.findByRole('button', { name: key('revoke') }));
		await action('set-instance-b');
		const currentRevoke = await screen.findByRole('button', { name: key('revoke') });
		expect(currentRevoke.hasAttribute('disabled')).toBe(false);
		mutation.reject(new Error('stale revoke'));
		await mutation.promise.catch(() => undefined);
		expect(errorToast).not.toHaveBeenCalled();
		expect(currentRevoke.hasAttribute('disabled')).toBe(false);
	});
	it('clears visible credentials after a same-project actor transition', async () => {
		await revealSecret();
		auth.update(state => ({ ...state, token: 'different-actor-token' }));
		await tick();
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
		expect(screen.queryByText(key('connectionDetails'))).toBeNull();
	});

	it('discards a pending secret response after actor transition and restoration', async () => {
		const mutation = deferred<unknown>();
		get.mockResolvedValue([cephGrant]);
		post.mockReturnValue(mutation.promise);
		render(ScopeWrapper, { initialInstanceId: uuid });
		await fireEvent.click(await screen.findByRole('button', { name: key('connectionInfo') }));
		auth.update(state => ({ ...state, token: 'different-actor-token' }));
		await tick();
		auth.update(state => ({ ...state, token: null }));
		await tick();
		mutation.resolve(secretResponse);
		await mutation.promise;
		await tick();
		expect(screen.queryByText('scope-transient-secret')).toBeNull();
		expect(screen.queryByText(key('connectionDetails'))).toBeNull();
	});

});
