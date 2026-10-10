import { beforeEach, describe, expect, it, vi } from 'vitest';
import { writable, type Writable } from 'svelte/store';
import type { K3sCluster } from '$lib/types/k3s';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), patch: vi.fn(), downloadBlob: vi.fn(), fetchWithAuth: vi.fn(),
	stream: vi.fn(), confirm: vi.fn(), download: vi.fn(), head: vi.fn(),
	attach: vi.fn(), detach: vi.fn(), interfaces: vi.fn(),
	configMaps: vi.fn(), secrets: vi.fn(), createCm: vi.fn(), updateCm: vi.fn(), deleteCm: vi.fn(),
	createSecret: vi.fn(), updateSecret: vi.fn(), deleteSecret: vi.fn(), namespaces: vi.fn(),
	deletePod: vi.fn(), deleteService: vi.fn(), restart: vi.fn(), scale: vi.fn(), log: vi.fn(),
}));
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));
vi.mock('$lib/api/client', () => ({ api: mocks, fetchWithAuth: mocks.fetchWithAuth, ApiError: class extends Error { status = 403; } }));
vi.mock('$lib/api/k3sSseStream', () => ({ streamK3sProgress: mocks.stream }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/utils/downloadBlob', () => ({ downloadBlobAs: mocks.download }));
vi.mock('$lib/mockup/transport', () => ({ maybeMockHead: mocks.head, symbolNoMatch: Symbol.for('no-match') }));
vi.mock('$lib/api/k3s', () => ({ listNodeInterfaces: mocks.interfaces, attachNodeInterface: mocks.attach, detachNodeInterface: mocks.detach }));
vi.mock('$lib/api/k3sResources', () => ({
	listNamespaces: mocks.namespaces, listConfigMaps: mocks.configMaps, listSecrets: mocks.secrets,
	createConfigMap: mocks.createCm, updateConfigMap: mocks.updateCm, deleteConfigMap: mocks.deleteCm,
	createSecret: mocks.createSecret, updateSecret: mocks.updateSecret, deleteSecret: mocks.deleteSecret,
}));
vi.mock('$lib/api/k3sWorkloads', () => ({
	listPods: vi.fn(), deletePod: mocks.deletePod, getPodLog: mocks.log,
	listServices: vi.fn(), deleteService: mocks.deleteService, listDeployments: vi.fn(), listReplicaSets: vi.fn(),
	restartDeployment: mocks.restart, scaleDeployment: mocks.scale,
}));

import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { createK3sClusterListController } from './k3sClusterListController.svelte';
import { createK3sClusterDetailController } from './k3sClusterDetailController.svelte';
import { createK3sProgress } from './k3sProgress.svelte';

const cluster: K3sCluster = {
	id: 'c', name: 'demo', status: 'ACTIVE', status_reason: null, server_vm_id: 'server',
	agent_vm_ids: ['agent'], agent_count: 1, api_address: null, server_ip: null,
	network_id: null, key_name: null, k3s_version: null, created_at: null, updated_at: null,
	deleted_at: null, deleted_by_user_id: null, deleted_reason: null,
};
const form = { name: 'demo', agent_count: 1, agent_flavor_id: '', network_id: '', key_name: 'unsafe-host-key', os_type: 'ubuntu', master_count: 1 };
function grant(...leaves: string[]) {
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set(leaf => leaves.includes(leaf));
}
function setup(adminMode = false) {
	let token = 'token-a';
	let projectId = 'project-a';
	const opts = { token: () => token, projectId: () => projectId, userId: () => 'user-a' };
	return {
		list: createK3sClusterListController({ ...opts, progress: createK3sProgress() }),
		detail: createK3sClusterDetailController({ ...opts, clusterId: () => 'c', adminMode: () => adminMode }),
		switchScope: () => { token = 'token-b'; projectId = 'project-b'; },
		refreshToken: () => { token = 'token-a2'; },
	};
}
beforeEach(() => {
	vi.resetAllMocks();
	grant();
	mocks.get.mockImplementation(async (path: string) => path.endsWith('/c') ? cluster : []);
	mocks.confirm.mockResolvedValue(true);
	mocks.downloadBlob.mockResolvedValue({ blob: new Blob(['backend-issued-config']) });
	mocks.head.mockResolvedValue(Symbol.for('no-match'));
	mocks.fetchWithAuth.mockResolvedValue({ ok: true });
	mocks.stream.mockImplementation(async function* () {});
	mocks.interfaces.mockResolvedValue([]);
});

describe('Drover handlers independently enforce current exact leaves', () => {
	it('never starts a privileged native request for a plain member without service leaves', async () => {
		const { list, detail } = setup();
		await detail.loadCluster();
		list.showModal = true;
		expect(list.showModal).toBe(false);
		await list.createCluster(form);
		await list.deleteCluster('c', 'demo');
		await list.downloadKubeconfig('c', 'demo');
		await detail.checkKubeconfig();
		await detail.downloadKubeconfig();
		detail.incrementScale();
		await detail.applyScale();
		await detail.deleteCluster();
		detail.openShell();
		await detail.attachInterface('server', 'net');
		await detail.detachInterface('server', 'port');
		await detail.loadConfigMaps();
		await detail.loadSecrets();
		await detail.saveConfigMap('settings', {}, true);
		await detail.saveSecret('credentials', 'Opaque', {}, true);
		await detail.removePod('pod');
		await detail.removeSvc('service');
		await detail.scaleDeploymentTo('deployment', 2);
		expect(detail.shellOpen).toBe(false);
		for (const request of [mocks.stream, mocks.patch, mocks.downloadBlob, mocks.head, mocks.fetchWithAuth, mocks.attach, mocks.detach, mocks.configMaps, mocks.secrets, mocks.createCm, mocks.createSecret, mocks.deletePod, mocks.deleteService, mocks.scale, mocks.confirm]) expect(request).not.toHaveBeenCalled();
	});
	it('downloads backend-issued user credentials without fabricating a config or admitting create/shell', async () => {
		grant('drover-access_user');
		const { list, detail } = setup();
		await detail.loadCluster();
		await list.downloadKubeconfig('c', 'demo');
		await detail.downloadKubeconfig();
		await list.createCluster(form);
		detail.openShell();
		expect(mocks.downloadBlob).toHaveBeenNthCalledWith(1, '/api/v1/k3s/clusters/c/kubeconfig?grade=user', 'token-a', 'project-a');
		expect(mocks.downloadBlob).toHaveBeenNthCalledWith(2, '/api/v1/k3s/clusters/c/kubeconfig?grade=user', 'token-a', 'project-a');
		expect(mocks.download.mock.calls[0][0]).toBe((await mocks.downloadBlob.mock.results[0].value).blob);
		expect(detail.shellOpen).toBe(false);
		expect(mocks.stream).not.toHaveBeenCalled();
	});
	it.each([
		[['drover-workloads_editor'], 'editor'],
		[['drover-access_user', 'drover-workloads_editor'], 'editor'],
		[['drover-access_admin'], 'user'],
		[['drover-access_user', 'drover-access_admin'], 'user'],
	] as const)('names the least-privilege native grade for %j instead of relying on a server default', async (leaves, grade) => {
		grant(...leaves);
		const { detail } = setup();
		await detail.loadCluster();
		await detail.checkKubeconfig();
		await detail.downloadKubeconfig();
		expect(mocks.fetchWithAuth).toHaveBeenCalledWith(`/api/v1/k3s/clusters/c/kubeconfig?grade=${grade}`, { method: 'HEAD' }, 'token-a', 'project-a');
		expect(mocks.downloadBlob).toHaveBeenCalledWith(`/api/v1/k3s/clusters/c/kubeconfig?grade=${grade}`, 'token-a', 'project-a');
		expect(mocks.confirm).not.toHaveBeenCalled();
	});
	it('requests the irrevocable admin certificate only through the confirmed explicit action', async () => {
		const { detail } = setup();
		grant('drover-workloads_editor');
		await detail.loadCluster();
		await detail.downloadKubeconfig(true);
		expect(mocks.confirm).not.toHaveBeenCalled();
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
		grant('drover-access_admin');
		mocks.confirm.mockResolvedValueOnce(false);
		await detail.downloadKubeconfig(true);
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
		const confirm = Promise.withResolvers<boolean>();
		mocks.confirm.mockReturnValueOnce(confirm.promise);
		const revoked = detail.downloadKubeconfig(true);
		grant('drover-access_user');
		confirm.resolve(true);
		await revoked;
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
		grant('drover-access_admin');
		await detail.downloadKubeconfig(true);
		expect(mocks.downloadBlob).toHaveBeenCalledWith('/api/v1/k3s/clusters/c/kubeconfig?grade=admin', 'token-a', 'project-a');
	});
	it('publishes a credential across an access-token refresh but never into a different project', async () => {
		grant('drover-access_user');
		const { list, refreshToken, switchScope } = setup();
		const refreshed = Promise.withResolvers<{ blob: Blob }>();
		mocks.downloadBlob.mockReturnValueOnce(refreshed.promise);
		const first = list.downloadKubeconfig('c', 'demo');
		refreshToken();
		refreshed.resolve({ blob: new Blob(['issued']) });
		await first;
		expect(mocks.download).toHaveBeenCalledOnce();
		grant('drover-access_user');
		const stale = Promise.withResolvers<{ blob: Blob }>();
		mocks.downloadBlob.mockReturnValueOnce(stale.promise);
		const second = list.downloadKubeconfig('c', 'demo');
		switchScope();
		stale.resolve({ blob: new Blob(['old-project']) });
		await second;
		expect(mocks.download).toHaveBeenCalledOnce();
	});
	it('lets a cluster editor create without SSH injection and scale, but never delete or download admin credentials', async () => {
		grant('drover-clusters_editor');
		const { list, detail } = setup();
		await detail.loadCluster();
		await list.createCluster(form);
		const [path, request] = mocks.stream.mock.calls[0];
		expect(path).toBe('/api/v1/k3s/clusters/async');
		expect(request.body).not.toHaveProperty('key_name');
		detail.incrementScale();
		await detail.applyScale();
		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/k3s/clusters/c/scale', { agent_count: 2 }, 'token-a', 'project-a');
		await detail.deleteCluster();
		await list.deleteCluster('c', 'demo');
		await detail.downloadKubeconfig();
		expect(mocks.stream).toHaveBeenCalledTimes(1);
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
	});
	it('does not expand a cluster administrator leaf into access-admin or cluster editor', async () => {
		grant('drover-clusters_admin');
		const { list, detail } = setup();
		await detail.loadCluster();
		await list.createCluster(form);
		await detail.downloadKubeconfig();
		await detail.attachInterface('server', 'net');
		await detail.detachInterface('server', 'port');
		expect(mocks.detach).toHaveBeenCalledWith('c', 'server', 'port', 'token-a', 'project-a');
		expect(mocks.attach).not.toHaveBeenCalled();
		expect(mocks.stream).not.toHaveBeenCalled();
		expect(mocks.downloadBlob).not.toHaveBeenCalled();
	});
	it('allows node SSH key installation only with explicit access-admin plus create authority', async () => {
		grant('drover-clusters_editor', 'drover-access_admin');
		const { list } = setup();
		await list.createCluster(form);
		expect(mocks.stream.mock.calls[0][1].body.key_name).toBe('unsafe-host-key');
	});
	it('uses workloads_editor or access_admin for resource reads/edits, never cluster editor alone', async () => {
		const { detail } = setup();
		detail.selectedNamespace = 'backend-private-namespace';
		grant('drover-clusters_editor', 'drover-clusters_admin', 'drover-access_user');
		await detail.loadConfigMaps();
		await detail.loadSecrets();
		await detail.saveConfigMap('settings', {}, true);
		await detail.saveSecret('credentials', 'Opaque', {}, true);
		expect(mocks.configMaps).not.toHaveBeenCalled();
		expect(mocks.secrets).not.toHaveBeenCalled();
		expect(mocks.createCm).not.toHaveBeenCalled();
		expect(mocks.createSecret).not.toHaveBeenCalled();
		grant('drover-workloads_editor');
		mocks.createCm.mockResolvedValue({ name: 'settings' });
		mocks.createSecret.mockResolvedValue({ name: 'credentials' });
		await detail.saveConfigMap('settings', { key: 'value' }, true);
		await detail.saveSecret('credentials', 'Opaque', { key: 'value' }, true);
		await detail.saveSecret('tls', 'kubernetes.io/tls', {}, true);
		expect(mocks.createCm).toHaveBeenCalledWith('c', 'backend-private-namespace', { name: 'settings', data: { key: 'value' } }, 'token-a', 'project-a');
		expect(mocks.createSecret).toHaveBeenCalledTimes(1);
		grant('drover-access_admin');
		await detail.saveSecret('tls', 'kubernetes.io/tls', {}, true);
		expect(mocks.createSecret).toHaveBeenCalledTimes(2);
	});
	it('never sends resource requests before the backend returns a usable namespace', async () => {
		grant('drover-workloads_editor');
		const { detail } = setup();
		await detail.loadConfigMaps();
		await detail.saveConfigMap('settings', {}, true);
		await detail.removePod('pod');
		expect(mocks.configMaps).not.toHaveBeenCalled();
		expect(mocks.createCm).not.toHaveBeenCalled();
		expect(mocks.deletePod).not.toHaveBeenCalled();
		mocks.namespaces.mockResolvedValue(['dw-private']);
		await detail.loadNamespaces();
		expect(detail.selectedNamespace).toBe('dw-private');
		await detail.loadConfigMaps();
		expect(mocks.configMaps).toHaveBeenCalledWith('c', 'dw-private', 'token-a', 'project-a');
	});
	it.each(['drover-workloads_editor', 'drover-access_admin'])('allows shell with %s but does not imply cluster mutations', leaf => {
		grant(leaf);
		const { detail } = setup();
		detail.openShell();
		expect(detail.shellOpen).toBe(true);
		detail.incrementScale();
		expect(detail.scalingTarget).toBeNull();
	});
	it('rechecks downgrade after destructive confirmation and refuses a changed project even if newly granted', async () => {
		grant('drover-clusters_admin', 'drover-clusters_editor');
		const { list, detail, switchScope } = setup();
		await detail.loadCluster();
		const confirm = Promise.withResolvers<boolean>();
		mocks.confirm.mockReturnValueOnce(confirm.promise);
		const deleting = list.deleteCluster('c', 'demo');
		grant();
		confirm.resolve(true);
		await deleting;
		expect(mocks.stream).not.toHaveBeenCalled();
		grant('drover-clusters_editor');
		detail.incrementScale();
		mocks.confirm.mockImplementationOnce(async () => { switchScope(); return true; });
		await detail.applyScale();
		expect(mocks.patch).not.toHaveBeenCalled();
	});
	it('discards a downloaded credential that finishes after scope change', async () => {
		grant('drover-access_user');
		const { list, switchScope } = setup();
		const response = Promise.withResolvers<{ blob: Blob }>();
		mocks.downloadBlob.mockReturnValueOnce(response.promise);
		const downloading = list.downloadKubeconfig('c', 'demo');
		switchScope();
		response.resolve({ blob: new Blob(['old-private-config']) });
		await downloading;
		expect(mocks.download).not.toHaveBeenCalled();
	});
	it.each(['list', 'detail'] as const)('discards a late %s credential after its exact grade is revoked', async surface => {
		grant('drover-workloads_editor');
		const controllers = setup();
		await controllers.detail.loadCluster();
		const response = Promise.withResolvers<{ blob: Blob }>();
		mocks.downloadBlob.mockReturnValueOnce(response.promise);
		const downloading = surface === 'list' ? controllers.list.downloadKubeconfig('c', 'demo') : controllers.detail.downloadKubeconfig();
		// A remaining user-grade grant cannot authorize a previously requested editor credential.
		grant('drover-access_user');
		response.resolve({ blob: new Blob(['editor-private-config']) });
		await downloading;
		expect(mocks.download).not.toHaveBeenCalled();
	});
});
