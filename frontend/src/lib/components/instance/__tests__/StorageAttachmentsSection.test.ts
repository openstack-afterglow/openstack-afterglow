import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { auth } from '$lib/stores/auth';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

const { controllerRef, get, post, remove, errorToast } = vi.hoisted(() => ({
	controllerRef: { current: undefined as unknown },
	get: vi.fn(), post: vi.fn(), remove: vi.fn(), errorToast: vi.fn(),
}));
vi.mock('$lib/stores/instanceDetailController.svelte', () => ({ useInstanceDetailController: () => controllerRef.current }));
vi.mock('$lib/api/client', () => ({ api: { get, post, delete: remove }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: errorToast } }));
vi.mock('$lib/i18n/ns/instance', () => ({ t: (key: string) => key }));

import StorageAttachmentsSection from '../StorageAttachmentsSection.svelte';
const key = (name: string) => `storageAttachments.${name}`;
const uuid = '2c3e9ee7-60fd-4bfa-96bd-e981d55132b1';
const nfs = { id: 'storage-a', name: 'storage-a', status: 'available', share_proto: 'NFS' };
const ceph = { ...nfs, id: 'ceph-a', name: 'ceph-a', share_proto: 'CEPHFS' };
const grant = {
	file_storage_id: 'storage-a', name: 'storage-a', share_proto: 'NFS', status: 'available',
	access_id: 'rule-a', access_type: 'ip', access_to: '10.0.0.7', access_level: 'ro', state: 'active', managed: true, association_state: 'tracked',
	exports: ['10.0.0.2:/share-a', '10.0.0.3:/share-a'], share_network_id: 'share-net-a',
	share_network: { id: 'share-net-a', name: 'private-share-network', neutron_net_id: 'network-a', neutron_subnet_id: 'subnet-a' },
};
function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>(res => { resolve = res; });
	return { promise, resolve };
}
function renderSection(instanceId?: string, projectId?: string, fixedAddresses = ['10.0.0.7', '10.0.0.8']) {
	controllerRef.current = {
		instanceId, effectiveProjectId: projectId,
		instance: instanceId ? { id: instanceId, name: 'mutable-server-name', os_type: 'windows' } : null,
		fixedIpsList: fixedAddresses.map(addr => ({ addr, type: 'fixed' })),
		floatingIpsList: [{ addr: '203.0.113.7', type: 'floating' }],
	} as InstanceDetailController;
	return render(StorageAttachmentsSection);
}
async function openStorage(id = 'storage-a') {
	await fireEvent.click(screen.getByRole('button', { name: key('openGrant') }));
	await screen.findByRole('option', { name: new RegExp(id) });
	await fireEvent.change(screen.getByLabelText(key('storageLabel')), { target: { value: id } });
}
async function selectNfs() {
	await openStorage();
	await fireEvent.change(screen.getByLabelText(key('fixedIpLabel')), { target: { value: '10.0.0.7' } });
}

describe('StorageAttachmentsSection authorization boundaries', () => {
	beforeEach(() => {
		vi.resetAllMocks();
		auth.update(state => ({ ...state, token: null, canWrite: true, isSystemAdmin: false, roles: ['member'] }));
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/file-storage' ? [nfs, ceph] : []));
		post.mockResolvedValue(grant);
		remove.mockResolvedValue(undefined);
	});

	it('waits for both scope primitives and does not preload the project catalog', async () => {
		renderSection('instance-a');
		await Promise.resolve();
		expect(get).not.toHaveBeenCalled();
		renderSection('instance-a', 'project-a');
		await waitFor(() => expect(get).toHaveBeenCalledWith('/api/v1/instances/instance-a/storage-attachments', undefined, 'project-a'));
		expect(get).not.toHaveBeenCalledWith('/api/v1/file-storage', undefined, 'project-a');
	});

	it('loads the catalog only when the authorization form opens', async () => {
		renderSection('instance-a', 'project-a');
		await openStorage();
		expect(get).toHaveBeenCalledWith('/api/v1/file-storage', undefined, 'project-a');
	});

	it('requires an explicit exact fixed IP and sends no mountpoint or commands, including on Windows', async () => {
		renderSection('instance-a', 'project-a');
		await openStorage();
		expect(screen.getByRole('button', { name: key('grant') }).hasAttribute('disabled')).toBe(true);
		expect(screen.queryByRole('textbox')).toBeNull();
		expect(screen.queryByPlaceholderText('/mnt/mydata')).toBeNull();
		expect(screen.queryByRole('option', { name: '203.0.113.7' })).toBeNull();
		expect(screen.getByRole('option', { name: '10.0.0.7' })).toBeTruthy();
		expect(screen.getByRole('option', { name: '10.0.0.8' })).toBeTruthy();
		await fireEvent.change(screen.getByLabelText(key('fixedIpLabel')), { target: { value: '10.0.0.8' } });
		await fireEvent.click(screen.getByRole('checkbox', { name: key('readOnly') }));
		await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
		await waitFor(() => expect(post).toHaveBeenCalledWith('/api/v1/instances/instance-a/storage-attachments', {
			file_storage_id: 'storage-a', fixed_ip: '10.0.0.8', read_only: true,
		}, undefined, 'project-a'));
		expect(screen.getByText(key('manualConnection'))).toBeTruthy();
		expect(screen.queryByText(/mount |sudo |keyring|\/mnt\//i)).toBeNull();
	});

	it.each(['10.0.0.0/24', '203.0.113.7', '10.0.0.99'])('rejects a non-current exact target %s', async target => {
		renderSection('instance-a', 'project-a');
		await openStorage();
		await fireEvent.change(screen.getByLabelText(key('fixedIpLabel')), { target: { value: target } });
		await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
		expect(post).not.toHaveBeenCalled();
	});

	it('cannot grant NFS access without a current fixed IP', async () => {
		renderSection('instance-a', 'project-a', []);
		await openStorage();
		expect(screen.getByText(key('noFixedIps'))).toBeTruthy();
		expect(screen.getByRole('button', { name: key('grant') }).hasAttribute('disabled')).toBe(true);
	});

	it('uses the deterministic UUID-bound Ceph identity and omits fixed_ip', async () => {
		renderSection(uuid, 'project-a');
		await openStorage('ceph-a');
		expect(screen.getByText(`afterglow-${uuid.replaceAll('-', '')}`)).toBeTruthy();
		expect(screen.queryByText('mutable-server-name')).toBeNull();
		expect(screen.queryByLabelText(key('fixedIpLabel'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
		await waitFor(() => expect(post).toHaveBeenCalledWith(`/api/v1/instances/${uuid}/storage-attachments`, {
			file_storage_id: 'ceph-a', read_only: false,
		}, undefined, 'project-a'));
	});

	it('does not authorize a Ceph identity for an invalid instance UUID', async () => {
		renderSection('instance-a', 'project-a');
		await openStorage('ceph-a');
		expect(screen.getByRole('button', { name: key('grant') }).hasAttribute('disabled')).toBe(true);
	});

	it('excludes unsupported, unavailable and already recorded shares', async () => {
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/file-storage'
			? [nfs, ceph, { ...nfs, id: 'smb', share_proto: 'CIFS' }, { ...nfs, id: 'busy', status: 'creating' }]
			: [grant]));
		renderSection('instance-a', 'project-a');
		await screen.findByText('storage-a');
		await openStorage('ceph-a');
		expect(screen.queryByRole('option', { name: /storage-a|smb|busy/ })).toBeNull();
	});

	it('shows access type, exact target, level, rule state, exports and share network', async () => {
		get.mockResolvedValue([grant]);
		renderSection('instance-a', 'project-a');
		await screen.findByText('storage-a');
		for (const text of ['ip', '10.0.0.7', key('readOnly'), '10.0.0.2:/share-a', '10.0.0.3:/share-a', 'private-share-network', 'network-a', 'subnet-a', key('ruleActive')]) {
			expect(screen.getByText(text)).toBeTruthy();
		}
		expect(screen.getByText(key('ruleState'))).toBeTruthy();
	});

	it.each(['new', 'queued_to_apply', 'applying', 'queued_to_deny', 'denying'])('shows %s as pending, not active despite share available', async state => {
		get.mockResolvedValue([{ ...grant, state }]);
		renderSection('instance-a', 'project-a');
		await screen.findByText(key('rulePending'));
		expect(screen.queryByText(key('ruleActive'))).toBeNull();
		expect(screen.queryByText('available')).toBeNull();
	});

	it.each(['error', 'missing', 'unknown', 'untracked'])('does not claim active access for %s', async state => {
		get.mockResolvedValue([{ ...grant, state, access_level: 'rw', exports: [], share_network: null, share_network_id: null }]);
		renderSection('instance-a', 'project-a');
		await screen.findByText(key('ruleInactive'));
		expect(screen.getByText(key('readWrite'))).toBeTruthy();
		expect(screen.getByText(key('noExports'))).toBeTruthy();
		expect(screen.getByText(key('noShareNetwork'))).toBeTruthy();
	});

	it.each(['mismatch', 'unknown'])('keeps provider state inspectable but hides writes for %s association', async association_state => {
		get.mockResolvedValue([{ ...grant, share_proto: 'CEPHFS', association_state }]);
		renderSection(uuid, 'project-a');
		await screen.findByText(key(association_state === 'mismatch' ? 'associationMismatch' : 'associationUnknown'));
		expect(screen.getByText(key('ruleState'))).toBeTruthy();
		expect(screen.queryByText(key('ruleActive'))).toBeNull();
		expect(screen.queryByRole('button', { name: key('revoke') })).toBeNull();
		expect(screen.queryByRole('button', { name: key('connectionInfo') })).toBeNull();
	});

	it('shows list errors rather than claiming the authorization list is empty', async () => {
		get.mockRejectedValue(new Error('failed'));
		renderSection('instance-a', 'project-a');
		await screen.findByText(key('loadFailed'));
		expect(screen.queryByText(key('empty'))).toBeNull();
	});

	it('retries a failed catalog only after reopening', async () => {
		get.mockImplementation((path: string) => path === '/api/v1/file-storage' ? Promise.reject(new Error('failed')) : Promise.resolve([]));
		renderSection('instance-a', 'project-a');
		await fireEvent.click(screen.getByRole('button', { name: key('openGrant') }));
		await screen.findByText(new RegExp(key('catalogRetry')));
		await fireEvent.click(screen.getByRole('button', { name: key('close') }));
		get.mockImplementation((path: string) => Promise.resolve(path === '/api/v1/file-storage' ? [nfs] : []));
		await openStorage();
		expect(get.mock.calls.filter(([path]) => path === '/api/v1/file-storage')).toHaveLength(2);
	});

	it('keeps the grant busy until its post-mutation reload settles', async () => {
		const reload = deferred<unknown[]>();
		get.mockResolvedValueOnce([]).mockResolvedValueOnce([nfs]).mockReturnValueOnce(reload.promise);
		renderSection('instance-a', 'project-a');
		await selectNfs();
		await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
		await screen.findByText(key('connectionDetails'));
		await fireEvent.click(screen.getByRole('button', { name: key('openGrant') }));
		expect(screen.getByRole('button', { name: key('granting') }).hasAttribute('disabled')).toBe(true);
		reload.resolve([]);
		await waitFor(() => expect(screen.getByRole('button', { name: key('grant') })).toBeTruthy());
		await fireEvent.change(screen.getByLabelText(key('storageLabel')), { target: { value: 'storage-a' } });
		await fireEvent.change(screen.getByLabelText(key('fixedIpLabel')), { target: { value: '10.0.0.7' } });
		expect(screen.getByRole('button', { name: key('grant') }).hasAttribute('disabled')).toBe(false);
	});

	it('hides all write and secret actions for a reader, while keeping authorization inspection', async () => {
		auth.update(state => ({ ...state, canWrite: false, roles: ['reader'] }));
		get.mockResolvedValue([{ ...grant, share_proto: 'CEPHFS', access_type: 'cephx' }]);
		renderSection(uuid, 'project-a');
		await screen.findByText('storage-a');
		for (const action of ['openGrant', 'grant', 'revoke', 'connectionInfo']) expect(screen.queryByRole('button', { name: key(action) })).toBeNull();
		expect(post).not.toHaveBeenCalled();
		expect(remove).not.toHaveBeenCalled();
	});

	it('does not expose revoke or secret retrieval for preexisting unmanaged access', async () => {
		get.mockResolvedValue([{ ...grant, managed: false, share_proto: 'CEPHFS' }]);
		renderSection(uuid, 'project-a');
		await screen.findByText(key('unmanaged'));
		expect(screen.queryByRole('button', { name: key('revoke') })).toBeNull();
		expect(screen.queryByRole('button', { name: key('connectionInfo') })).toBeNull();
	});

	it('revokes only the selected managed association with the current project', async () => {
		get.mockResolvedValueOnce([grant]).mockResolvedValueOnce([]);
		renderSection('instance-a', 'project-a');
		await fireEvent.click(await screen.findByRole('button', { name: key('revoke') }));
		await waitFor(() => expect(remove).toHaveBeenCalledWith('/api/v1/instances/instance-a/storage-attachments/storage-a', undefined, 'project-a'));
		await screen.findByText(key('empty'));
	});

	it('ignores secrets and legacy commands from GET and never automatically fetches a key', async () => {
		get.mockResolvedValue([{ ...grant, share_proto: 'CEPHFS', secret: { type: 'cephx_key', value: 'get-secret' }, access_key: 'raw-key', mount_command: 'sudo mount legacy' }]);
		renderSection(uuid, 'project-a');
		await screen.findByText('storage-a');
		expect(screen.queryByText(/get-secret|raw-key|sudo mount/)).toBeNull();
		expect(post).not.toHaveBeenCalled();
	});

	it('retrieves a Ceph secret only through an explicit scoped POST and clears it on reopen', async () => {
		const cephGrant = { ...grant, share_proto: 'CEPHFS', access_type: 'cephx', access_to: `afterglow-${uuid.replaceAll('-', '')}` };
		get.mockResolvedValue([cephGrant]);
		post.mockResolvedValue({ ...cephGrant, secret: { type: 'cephx_key', value: 'explicit-transient-key' } });
		renderSection(uuid, 'project-a');
		await fireEvent.click(await screen.findByRole('button', { name: key('connectionInfo') }));
		await screen.findByText('explicit-transient-key');
		expect(post).toHaveBeenCalledWith(`/api/v1/instances/${uuid}/storage-attachments/storage-a/connection-info`, {}, undefined, 'project-a');
		expect(screen.getByText(key('transientSecret'))).toBeTruthy();
		expect(screen.getByText(key('transientSecretHelp'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: key('openGrant') }));
		expect(screen.queryByText('explicit-transient-key')).toBeNull();
		expect(screen.queryByText(key('connectionDetails'))).toBeNull();
	});

	it('labels an optional newly granted Ceph secret transient and clears it on close', async () => {
		post.mockResolvedValue({ ...grant, share_proto: 'CEPHFS', secret: { type: 'cephx_key', value: 'grant-secret' } });
		renderSection(uuid, 'project-a');
		await openStorage('ceph-a');
		await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
		await screen.findByText('grant-secret');
		expect(screen.getByText(key('transientSecret'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: key('close') }));
		expect(screen.queryByText('grant-secret')).toBeNull();
	});

	it('keeps a pending revoke association visible and refreshes its actual rule state', async () => {
		get.mockResolvedValueOnce([grant]).mockResolvedValueOnce([{ ...grant, state: 'denying' }]);
		remove.mockRejectedValue(new Error('provider revoke pending'));
		renderSection('instance-a', 'project-a');
		await fireEvent.click(await screen.findByRole('button', { name: key('revoke') }));
		await screen.findByText(key('rulePending'));
		expect(screen.getByText('storage-a')).toBeTruthy();
		expect(screen.queryByText(key('empty'))).toBeNull();
		expect(errorToast).toHaveBeenCalledWith(key('revokeFailed'));
	});

	it('shows a pending grant without inventing a Ceph key or polling for one', async () => {
		post.mockResolvedValue({ ...grant, share_proto: 'CEPHFS', state: 'new' });
		renderSection(uuid, 'project-a');
		await openStorage('ceph-a');
		await fireEvent.click(screen.getByRole('button', { name: key('grant') }));
		await screen.findByText(key('connectionDetails'));
		expect(screen.getByText(key('rulePending'))).toBeTruthy();
		expect(screen.queryByText(key('transientSecret'))).toBeNull();
		expect(post).toHaveBeenCalledTimes(1);
	});

	it('reports an explicit connection-info failure without showing a secret', async () => {
		get.mockResolvedValue([{ ...grant, share_proto: 'CEPHFS', state: 'applying' }]);
		post.mockRejectedValue(new Error('rule pending'));
		renderSection(uuid, 'project-a');
		await fireEvent.click(await screen.findByRole('button', { name: key('connectionInfo') }));
		await waitFor(() => expect(errorToast).toHaveBeenCalledWith(key('connectionFailed')));
		expect(screen.queryByText(key('transientSecret'))).toBeNull();
		expect(screen.getByText(key('rulePending'))).toBeTruthy();
	});
});
