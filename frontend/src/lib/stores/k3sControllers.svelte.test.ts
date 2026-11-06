import { beforeEach, describe, expect, it, vi } from 'vitest';
import { writable, type Writable } from 'svelte/store';
import type { K3sCluster, SecretInfo } from '$lib/types/k3s';

const mocks = vi.hoisted(() => ({
	get: vi.fn(), post: vi.fn(), patch: vi.fn(), downloadBlob: vi.fn(), fetchWithAuth: vi.fn(),
	stream: vi.fn(), confirm: vi.fn(), download: vi.fn(), head: vi.fn(),
	attach: vi.fn(), detach: vi.fn(), interfaces: vi.fn(),
	configMaps: vi.fn(), secrets: vi.fn(), createCm: vi.fn(), updateCm: vi.fn(), deleteCm: vi.fn(),
	createSecret: vi.fn(), updateSecret: vi.fn(), deleteSecret: vi.fn(), namespaces: vi.fn(),
	deletePod: vi.fn(), deleteService: vi.fn(), restart: vi.fn(), scale: vi.fn(), log: vi.fn(),
	withExperience: vi.fn(), begin: vi.fn(), state: vi.fn(), applied: vi.fn(), discarded: vi.fn(), record: vi.fn(),
	deployments: vi.fn(), replicasets: vi.fn(), delete: vi.fn(),
	load: vi.fn(),
	track: vi.fn(), handoff: vi.fn(),
}));
vi.mock('$lib/stores/servicePermissions', () => ({ serviceCapabilities: writable<(leaf: string) => boolean>(() => false) }));
vi.mock('$lib/api/client', () => ({ api: mocks, fetchWithAuth: mocks.fetchWithAuth, ApiError: class extends Error { status = 403; } }));
vi.mock('$lib/utils/experience', () => ({
	beginExperienceAction: mocks.begin, beginExperienceLoad: mocks.load, experienceState: mocks.state, experienceApplied: mocks.applied,
	experienceDiscarded: mocks.discarded, recordExperience: mocks.record,
}));
vi.mock('$lib/api/k3sSseStream', () => ({ streamK3sProgress: mocks.stream }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/k3sOperations.svelte', () => ({ k3sOperations: { track: mocks.track, owns: () => true, handoff: mocks.handoff } }));
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
	listServices: vi.fn(), deleteService: mocks.deleteService, listDeployments: mocks.deployments, listReplicaSets: mocks.replicasets,
	restartDeployment: mocks.restart, scaleDeployment: mocks.scale,
}));

import { serviceCapabilities } from '$lib/stores/servicePermissions';
import { ApiError } from '$lib/api/client';
import { createK3sClusterListController } from './k3sClusterListController.svelte';
import { createK3sClusterDetailController } from './k3sClusterDetailController.svelte';
import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
import { createK3sProgress } from './k3sProgress.svelte';
import { createContainerDetailController } from './containerDetailController.svelte';

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
function setup(adminMode = false, selectedProjectId = 'project-a') {
	let token = 'token-a';
	let projectId = selectedProjectId;
	const opts = { token: () => token, projectId: () => projectId, userId: () => 'user-a' };
	return {
		list: createK3sClusterListController(opts),
		detail: createK3sClusterDetailController({ ...opts, clusterId: () => 'c', adminMode: () => adminMode }),
		switchScope: () => { token = 'token-b'; projectId = 'project-b'; },
		refreshToken: () => { token = 'token-a2'; },
	};
}
beforeEach(() => {
	vi.resetAllMocks();
	mocks.withExperience.mockReturnValue(mocks);
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
	it('retains regex and column state over refresh and section remount, but clears actual owner reset', async () => {
		const { detail, refreshToken } = setup();
		await detail.loadCluster();
		const retained = detail.tableState('inventory');
		retained.search = '^demo$';
		const columns: TableColumn<K3sCluster>[] = [
			{ key: 'name', label: 'Name', value: row => row.name },
			{ key: 'status', label: 'Status', value: row => row.status },
		];
		const view = createTableView({ rows: () => detail.cluster ? [detail.cluster] : [], columns: () => columns, search: () => retained.search, state: retained.state });
		view.setFilter('status', ['ACTIVE', 'BUILD']);
		view.toggleSort('name');
		view.toggleSort('name');
		refreshToken();
		await detail.loadCluster();
		expect(view.rows.map(row => row.name)).toEqual(['demo']);
		expect(detail.tableState('inventory')).toBe(retained);
		const remounted = createTableView({ rows: () => detail.cluster ? [detail.cluster] : [], columns: () => columns, search: () => retained.search, state: retained.state });
		expect(remounted.sort).toEqual({ key: 'name', direction: 'desc' });
		expect(remounted.selected('status')).toEqual(['ACTIVE', 'BUILD']);
		retained.search = '[';
		await detail.loadCluster();
		expect(remounted.error).toBe(true);
		expect(remounted.rows).toEqual([]);
		detail.reset();
		expect(detail.tableState('inventory')).not.toBe(retained);
		expect(detail.tableState('inventory')).toEqual({ search: '', state: { sort: null, filters: {} } });
	});
	it.each([true, false].flatMap(isNew => ['reset', 'namespace-aba', 'revocation'].map(transition => ({ isNew, transition }))))('does not publish a late Secret mutation (create=$isNew) after $transition', async ({ isNew, transition }) => {
		grant('drover-workloads_editor');
		const { detail } = setup(true, 'resource-project');
		await detail.loadCluster();
		detail.selectedNamespace = 'private';
		const before: SecretInfo = { name: 'credentials', namespace: 'private', type: 'Opaque', data: { value: 'before' }, labels: {}, annotations: {}, created_at: '' };
		mocks.secrets.mockResolvedValue([before]);
		await detail.loadSecrets();
		const pending = Promise.withResolvers<SecretInfo>();
		(isNew ? mocks.createSecret : mocks.updateSecret).mockReturnValueOnce(pending.promise);
		const saving = detail.saveSecret('credentials', 'Opaque', { value: 'stale-private-value' }, isNew);
		if (transition === 'reset') { detail.reset(); await detail.loadCluster(); detail.selectedNamespace = 'private'; await detail.loadSecrets(); }
		else if (transition === 'namespace-aba') { detail.selectedNamespace = 'other'; detail.selectedNamespace = 'private'; await detail.loadSecrets(); }
		else grant();
		const current = [...detail.secrets];
		pending.resolve({ ...before, data: { value: 'stale-private-value' } });
		await saving;
		expect(detail.secrets).toEqual(current);
	});
	it.each(['secret', 'configmap'].flatMap(resource => ['reset', 'namespace-aba', 'revocation', 'project'].map(transition => ({ resource, transition }))))('does not retarget a confirmed $resource deletion after $transition', async ({ resource, transition }) => {
		grant('drover-workloads_editor');
		const { detail, switchScope } = setup(true, 'resource-project');
		await detail.loadCluster();
		detail.selectedNamespace = 'private';
		const pending = Promise.withResolvers<boolean>();
		mocks.confirm.mockReturnValueOnce(pending.promise);
		const deleting = resource === 'secret' ? detail.deleteSecretItem('credentials') : detail.deleteCm('settings');
		if (transition === 'reset') { detail.reset(); await detail.loadCluster(); detail.selectedNamespace = 'private'; }
		else if (transition === 'namespace-aba') { detail.selectedNamespace = 'other'; detail.selectedNamespace = 'private'; }
		else if (transition === 'project') switchScope();
		else grant();
		pending.resolve(true);
		await deleting;
		expect(resource === 'secret' ? mocks.deleteSecret : mocks.deleteCm).not.toHaveBeenCalled();
	});
	it.each(['secret', 'configmap'])('keeps %s deletion confirmation and its exact original target in the controller', async resource => {
		grant('drover-workloads_editor');
		const { detail } = setup(true, 'resource-project');
		await detail.loadCluster();
		detail.selectedNamespace = 'private';
		if (resource === 'secret') await detail.deleteSecretItem('credentials');
		else await detail.deleteCm('settings');
		expect(mocks.confirm).toHaveBeenCalledOnce();
		expect(resource === 'secret' ? mocks.deleteSecret : mocks.deleteCm).toHaveBeenCalledWith('c', 'private', resource === 'secret' ? 'credentials' : 'settings', 'token-a', 'resource-project', undefined);
	});
	it('does not disclose a late private Secret after the selected session scope resets on the same resource project', async () => {
		grant('drover-workloads_editor');
		const { detail } = setup(true, 'resource-project');
		await detail.loadCluster();
		detail.selectedNamespace = 'private';
		const old = Promise.withResolvers<SecretInfo[]>();
		mocks.secrets.mockReturnValueOnce(old.promise);
		const loading = detail.loadSecrets();
		detail.reset();
		await detail.loadCluster();
		detail.selectedNamespace = 'private';
		old.resolve([{ name: 'old-owner-secret', namespace: 'private', type: 'Opaque', data: { value: 'private' }, labels: {}, annotations: {}, created_at: '' }]);
		await loading;
		expect(detail.secrets).toEqual([]);
	});
	it('does not republish administrator detail after a reset even when the same resource scope is selected again', async () => {
		const { detail } = setup(true, 'resource-project');
		const old = Promise.withResolvers<K3sCluster>();
		mocks.get.mockReturnValueOnce(old.promise);
		const loading = detail.loadCluster();
		detail.reset();
		await detail.loadCluster();
		old.resolve({ ...cluster, name: 'stale-owner-resource' });
		await loading;
		expect(detail.cluster?.name).toBe('demo');
	});
	it('uses the administrator resource project for secondary calls and graded credentials without impersonating its owner', async () => {
		grant('drover-inventory_reader', 'drover-clusters_editor', 'drover-clusters_admin', 'drover-workloads_editor', 'drover-access_admin');
		const { detail } = setup(true, 'resource-project');
		await detail.loadCluster();
		await detail.loadHealth();
		await detail.triggerHealthCheck();
		mocks.namespaces.mockResolvedValue(['private']);
		await detail.loadNamespaces();
		await detail.loadConfigMaps();
		await detail.loadSecrets();
		await detail.attachInterface('server', 'net');
		detail.incrementScale();
		await detail.applyScale();
		await detail.checkKubeconfig();
		await detail.downloadKubeconfig();
		expect(detail.projectId).toBe('resource-project');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/k3s-clusters/c', 'token-a', 'resource-project');
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/k3s/clusters/c/health', 'token-a', 'resource-project');
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/k3s/clusters/c/health/check', {}, 'token-a', 'resource-project');
		expect(mocks.namespaces).toHaveBeenCalledWith('c', 'token-a', 'resource-project', undefined);
		expect(mocks.configMaps).toHaveBeenCalledWith('c', 'private', 'token-a', 'resource-project', undefined);
		expect(mocks.secrets).toHaveBeenCalledWith('c', 'private', 'token-a', 'resource-project', undefined);
		expect(mocks.attach).toHaveBeenCalledWith('c', 'server', 'net', 'token-a', 'resource-project', undefined);
		expect(mocks.patch).toHaveBeenCalledWith('/api/v1/admin/k3s-clusters/c/scale', { agent_count: 2 }, 'token-a', 'resource-project');
		expect(mocks.downloadBlob).toHaveBeenLastCalledWith('/api/v1/k3s/clusters/c/kubeconfig?grade=editor', 'token-a', 'resource-project');
		mocks.confirm.mockClear();
		await detail.downloadKubeconfig(true);
		expect(mocks.confirm).toHaveBeenCalledOnce();
		expect(mocks.downloadBlob).toHaveBeenLastCalledWith('/api/v1/k3s/clusters/c/kubeconfig?grade=admin', 'token-a', 'resource-project');
		await detail.deleteCluster();
		expect(mocks.stream).toHaveBeenCalledWith('/api/v1/admin/k3s-clusters/c/delete-async', { method: 'POST', token: 'token-a', projectId: 'resource-project', experience: undefined });
	});
	it('discards same-target credentials and confirmations after the panel generation is reset', async () => {
		grant('drover-access_admin', 'drover-clusters_admin');
		const { detail } = setup(true, 'resource-project');
		await detail.loadCluster();
		const pending = Promise.withResolvers<{ blob: Blob }>();
		mocks.downloadBlob.mockReturnValueOnce(pending.promise);
		const downloading = detail.downloadKubeconfig();
		detail.reset();
		await detail.loadCluster();
		pending.resolve({ blob: new Blob(['stale-credential']) });
		await downloading;
		expect(mocks.download).not.toHaveBeenCalled();
		const confirmation = Promise.withResolvers<boolean>();
		mocks.confirm.mockReturnValueOnce(confirmation.promise);
		const deleting = detail.deleteCluster();
		detail.reset();
		await detail.loadCluster();
		confirmation.resolve(true);
		await deleting;
		expect(mocks.stream).not.toHaveBeenCalled();
	});
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
		expect(mocks.fetchWithAuth).toHaveBeenCalledWith(`/api/v1/k3s/clusters/c/kubeconfig?grade=${grade}`, { method: 'HEAD' }, 'token-a', 'project-a', { experience: undefined });
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
		expect(mocks.detach).toHaveBeenCalledWith('c', 'server', 'port', 'token-a', 'project-a', undefined);
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
	it.each([[undefined, true], [true, true], [false, false]])('sends Stampede choice %s explicitly as %s', async (choice, expected) => {
		grant('drover-clusters_editor');
		const { list } = setup();
		await list.createCluster({ ...form, stampede_enabled: choice });
		expect(mocks.stream.mock.calls[0][1].body.stampede_enabled).toBe(expected);
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
		expect(mocks.createCm).toHaveBeenCalledWith('c', 'backend-private-namespace', { name: 'settings', data: { key: 'value' } }, 'token-a', 'project-a', undefined);
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
		expect(mocks.configMaps).toHaveBeenCalledWith('c', 'dw-private', 'token-a', 'project-a', undefined);
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

describe('K3s semantic owner observations', () => {
	it('propagates creation context into the stream and follow-up inventory without treating admission as readiness', async () => {
		grant('drover-clusters_editor');
		const context = { actionId: 'creation-observation' };
		mocks.begin.mockReturnValue(context);
		mocks.stream.mockImplementation(async function* () {
			yield { step: 'waiting_callback', progress: 95, message: 'private log', cluster_id: 'private-id' };
		});
		const { list } = setup();
		await list.createCluster(form);
		expect(mocks.stream.mock.calls[0][1].experience).toBe(context);
		expect(mocks.withExperience).toHaveBeenCalledWith(context);
		expect(mocks.record).not.toHaveBeenCalled();
		// A clean handoff stream is not transport loss or resource availability.
		expect(mocks.state.mock.calls.some(([ctx, state]) => ctx === context && state === 'ready')).toBe(false);
		expect(JSON.stringify([mocks.state.mock.calls, mocks.record.mock.calls])).not.toContain('private');
	});

	it('reports only finite progress transitions and keeps unknown frames out of replay', () => {
		const context = { actionId: 'stream-observation' };
		const progress = createK3sProgress();
		progress.begin('create', 'private initial message', context as never);
		progress.apply({ step: 'private-runtime-key', progress: 43, message: 'private log', error: 'private error' }, context as never);
		expect(mocks.applied).not.toHaveBeenCalled();
		progress.apply({ step: 'security_group', progress: 50, message: 'private log' }, context as never);
		progress.apply({ step: 'security_group', progress: 60, message: 'more private log' }, context as never);
		expect(mocks.applied).toHaveBeenCalledOnce();
		expect(mocks.state).toHaveBeenLastCalledWith(context, 'loading', 1);
		progress.end(context as never);
		expect(JSON.stringify([mocks.state.mock.calls, mocks.record.mock.calls])).not.toContain('private');
	});

	it('discards a response only when the existing cluster generation guard prevented its assignment', async () => {
		const context = { actionId: 'old-read' };
		mocks.load.mockReturnValue(context);
		const { detail } = setup();
		const pending = Promise.withResolvers<K3sCluster>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const loading = detail.loadCluster();
		detail.reset();
		pending.resolve(cluster);
		await loading;
		expect(detail.cluster).toBeNull();
		expect(mocks.discarded).toHaveBeenCalledWith(context, 'stale');
		expect(mocks.applied).not.toHaveBeenCalled();
	});

	it('retains the actual late health assignment while withholding its DOM claim after reset', async () => {
		const context = { actionId: 'health-read' };
		mocks.load.mockReturnValue(context);
		const { detail } = setup();
		await detail.loadCluster();
		mocks.applied.mockClear();
		const pending = Promise.withResolvers<null>();
		mocks.get.mockReturnValueOnce(pending.promise);
		const loading = detail.loadHealth();
		detail.reset();
		pending.resolve(null);
		await loading;
		expect(mocks.applied).toHaveBeenCalledOnce();
		expect(mocks.applied.mock.calls[0][2]()).toBe(false);
	});

	it('observes credential download lifecycle without claiming source-owned DOM application', async () => {
		grant('drover-access_user');
		const context = { actionId: 'credential-export' };
		mocks.begin.mockReturnValue(context);
		const { detail } = setup();
		await detail.loadCluster();
		mocks.applied.mockClear();
		await detail.downloadKubeconfig();
		expect(mocks.withExperience).toHaveBeenLastCalledWith(context);
		expect(mocks.download).toHaveBeenCalledOnce();
		expect(mocks.state).toHaveBeenLastCalledWith(context, 'ready');
		expect(mocks.applied).not.toHaveBeenCalled();
	});
});

describe('Explicit cloud follow-up observations', () => {
	it('passes one workload observation into both deployment fan-out reads', async () => {
		const context = { actionId: 'fan-out' };
		mocks.load.mockReturnValue(context);
		mocks.deployments.mockResolvedValue([]);
		mocks.replicasets.mockResolvedValue([]);
		const { detail } = setup();
		detail.selectedNamespace = 'private-namespace';
		await detail.loadDeployments();
		expect(mocks.deployments).toHaveBeenCalledWith('c', 'private-namespace', 'token-a', 'project-a', context);
		expect(mocks.replicasets).toHaveBeenCalledWith('c', 'private-namespace', 'token-a', 'project-a', context);
		expect(mocks.applied).toHaveBeenCalledOnce();
		expect(JSON.stringify(mocks.state.mock.calls)).not.toContain('private-namespace');
	});

	it('preserves the container action context through its actual readback assignment', async () => {
		const context = { actionId: 'container-start' };
		mocks.begin.mockReturnValue(context);
		mocks.get.mockResolvedValue({ id: 'private-id', name: 'private-name', status: 'Running' });
		const detail = createContainerDetailController({
			containerId: () => 'private-id', adminMode: () => false,
			token: () => 'token-a', projectId: () => 'project-a',
		});
		await detail.handleAction('start');
		expect(mocks.begin).toHaveBeenCalledOnce();
		expect(mocks.withExperience.mock.calls).toEqual([[context], [context]]);
		expect(detail.container?.status).toBe('Running');
		expect(mocks.applied).toHaveBeenCalledOnce();
		expect(JSON.stringify(mocks.state.mock.calls)).not.toContain('private');
	});

	it('records actual overlapping container writes rather than inventing a product stale-result guard', async () => {
		mocks.begin.mockReturnValue({ actionId: 'container-read' });
		const old = Promise.withResolvers<{ logs: string }>();
		mocks.get.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ logs: 'new private content' });
		const detail = createContainerDetailController({
			containerId: () => 'private-id', adminMode: () => false,
			token: () => 'token-a', projectId: () => 'project-a',
		});
		const first = detail.fetchLogs();
		await detail.fetchLogs();
		old.resolve({ logs: 'old private content' });
		await first;
		expect(detail.logs).toBe('old private content');
		expect(mocks.applied).toHaveBeenCalledTimes(2);
		expect(mocks.applied.mock.calls.every(call => call.length === 2)).toBe(true);
		expect(mocks.discarded).not.toHaveBeenCalled();
		expect(JSON.stringify(mocks.state.mock.calls)).not.toContain('private');
	});
});

it('uses passive source loads for polling and reserves action context for manual refresh', async () => {
	const passive = { spanId: 'passive-owner' };
	const manual = { actionId: 'manual-refresh' };
	mocks.load.mockReturnValue(passive);
	mocks.begin.mockReturnValue(manual);
	const { list, detail } = setup();
	const container = createContainerDetailController({
		containerId: () => 'container', adminMode: () => false,
		token: () => 'token-a', projectId: () => 'project-a',
	});
	await list.fetchClusters();
	await detail.loadCluster();
	await container.fetchContainer();
	expect(mocks.begin).not.toHaveBeenCalled();
	expect(mocks.load).toHaveBeenCalledTimes(3);
	await container.fetchContainer(true);
	expect(mocks.begin).toHaveBeenCalledWith('container', 'refresh', 'resource.detail');
	expect(mocks.withExperience).toHaveBeenLastCalledWith(manual);
});

it('passes availability-read context in authenticated request options, never in RequestInit', async () => {
	grant('drover-access_user');
	const context = { spanId: 'availability-read' };
	mocks.load.mockReturnValue(context);
	const { detail } = setup();
	await detail.loadCluster();
	await detail.checkKubeconfig();
	expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
		'/api/v1/k3s/clusters/c/kubeconfig?grade=user',
		{ method: 'HEAD' }, 'token-a', 'project-a', { experience: context },
	);
});

describe('Drover truthful admission outcomes', () => {
	it.each([
		[409, undefined, false],
		[503, undefined, false],
		[409, 'drover_pre_admission_refused', true],
		[503, 'drover_pre_admission_refused', true],
	] as const)('requires an authoritative refusal marker, not HTTP %s alone (%s)', async (status, code, terminal) => {
		grant('drover-clusters_editor');
		const failure = Object.assign(new ApiError(status, 'Provider refusal', code), { status, code, message: 'Provider refusal' });
		mocks.stream.mockImplementation(async function* () { throw failure; });
		const { list } = setup();
		await list.createCluster(form);
		const progress = mocks.track.mock.calls[0][0];
		expect(progress.isTerminal).toBe(terminal);
		expect(progress.error).toContain('Provider refusal');
		expect(mocks.handoff).toHaveBeenCalledWith(progress);
	});

	it('formats native quota counts and administrator recovery without fabricating missing availability', async () => {
		grant('drover-clusters_editor');
		const quota = { project_id: 'project-a', resource: 'security_group_rule', required: 7, available: 2, limit: 10, used: 8, reserved: 0 };
		const failure = Object.assign(new ApiError(409, 'Rule budget exhausted', 'drover_pre_admission_refused'), {
			code: 'drover_pre_admission_refused', reason: 'security_group_quota_exceeded', quota,
		});
		mocks.stream.mockImplementation(async function* () { throw failure; });
		const { list } = setup();
		await list.createCluster(form);
		const progress = mocks.track.mock.calls[0][0];
		expect(progress.isTerminal).toBe(true);
		expect(progress.error).toContain('보안 그룹 규칙');
		expect(progress.error).toContain('필요 7개, 사용 가능 2개');
		expect(progress.error).toContain('관리자');
	});

	it.each(['security_group_quota_unavailable', 'security_group_quota_exceeded'])('keeps missing counts out of the localized %s refusal', async reason => {
		grant('drover-clusters_editor');
		const failure = Object.assign(new ApiError(503, 'Native quota refusal', 'drover_pre_admission_refused'), {
			code: 'drover_pre_admission_refused', reason, quota: undefined, message: 'Native quota refusal',
		});
		mocks.stream.mockImplementation(async function* () { throw failure; });
		const { list } = setup();
		await list.createCluster(form);
		const progress = mocks.track.mock.calls[0][0];
		expect(progress.isTerminal).toBe(true);
		expect(progress.error).not.toMatch(/필요 \d|사용 가능 \d/);
		if (reason === 'security_group_quota_unavailable') expect(progress.error).toContain('Neutron 조회 권한');
		else expect(progress.error).toBe('Native quota refusal');
	});
});
