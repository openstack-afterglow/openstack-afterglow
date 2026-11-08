import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { Cluster } from '$lib/types/cluster';
import type { DbInstance } from '$lib/types/database';
import { mockDatabaseContainers } from './databaseContainers';
import { getMockupState, resetMockupState } from './state';

const SAMPLE_DB: DbInstance = {
	id: 'mock-trove-instance-1', name: 'sample-customer-mysql', status: 'ACTIVE',
	datastore: { type: 'mysql', version: '8.0' }, flavor_id: '101', flavor_ram: 2048, flavor_vcpus: 2, size: 20,
	created_at: '2026-07-09T00:00:00Z', hostname: 'sample-customer-mysql.internal', ip: '192.0.2.41', ips: ['192.0.2.41'],
	address_map: { private: ['192.0.2.41'] }, volume_used: 4.25,
};
const SAMPLE_CLUSTER: Cluster = {
	id: 'mock-magnum-cluster-1', name: 'sample-magnum-k8s', status: 'CREATE_COMPLETE', status_reason: null,
	cluster_template_id: 'mock-magnum-template-k8s', master_count: 1, node_count: 2, api_address: 'https://192.0.2.70:6443',
	coe_version: 'v1.30.4', keypair: null, create_timeout: null, created_at: '2026-07-09T00:00:00Z', updated_at: null, stack_id: 'mock-magnum-stack-1',
};
const DB_BODY = { name: 'tutorial-db', flavor_id: '101', volume_size: 5, datastore_type: 'mysql', datastore_version: '8.0', nics: [], databases: [], users: [] };
const CLUSTER_BODY = { name: 'tutorial-cluster', cluster_template_id: 'mock-magnum-template-k8s', node_count: 1, master_count: 1 };

function call(method: string, path: string, body: unknown = null): unknown {
	return mockDatabaseContainers(method, path, body);
}

function status(fn: () => unknown): number | undefined {
	try {
		fn();
	} catch (error) {
		return error instanceof ApiError ? error.status : undefined;
	}
	return undefined;
}

beforeEach(() => {
	resetMockupState();
	// Tests own their fixtures so they do not depend on the shared tutorial seed.
	Object.assign(getMockupState(), { dbInstances: [structuredClone(SAMPLE_DB)], magnumClusters: [structuredClone(SAMPLE_CLUSTER)] });
});

describe('mockDatabaseContainers database instances', () => {
	it('serves create metadata so the Details tab is complete with its defaults', () => {
		const flavors = call('GET', '/api/v1/database-instances/flavors') as { id: string }[];
		const datastores = call('GET', '/api/v1/database-instances/datastores') as { name: string; versions: { name: string }[] }[];
		expect(flavors[0].id).toBe('101');
		expect(datastores[0]).toMatchObject({ name: 'mysql', versions: [{ name: '8.0' }] });
		expect(call('GET', '/api/v1/database-instances/volume-types')).toEqual([expect.objectContaining({ name: 'ceph-ssd' })]);
		expect(call('GET', '/api/v1/database-instances/configurations')).toEqual([]);
	});

	it('creates an instance, lists it as BUILD then ACTIVE, and deletes it', () => {
		const created = call('POST', '/api/v1/database-instances', DB_BODY) as DbInstance;
		expect(created).toMatchObject({ name: 'tutorial-db', status: 'BUILD', size: 5, flavor_id: '101', datastore: { type: 'mysql', version: '8.0' } });
		expect(created.id).not.toBe(SAMPLE_DB.id);
		const first = call('GET', '/api/v1/database-instances') as DbInstance[];
		expect(first.map((item) => [item.id, item.status])).toEqual([[SAMPLE_DB.id, 'ACTIVE'], [created.id, 'BUILD']]);
		const second = call('GET', '/api/v1/database-instances') as DbInstance[];
		expect(second.find((item) => item.id === created.id)?.status).toBe('ACTIVE');
		expect(call('DELETE', `/api/v1/database-instances/${created.id}`)).toEqual({});
		expect((call('GET', '/api/v1/database-instances') as DbInstance[]).map((item) => item.id)).toEqual([SAMPLE_DB.id]);
	});

	it('accepts a duplicate name like Trove and keeps distinct ids', () => {
		const first = call('POST', '/api/v1/database-instances', DB_BODY) as DbInstance;
		const second = call('POST', '/api/v1/database-instances', DB_BODY) as DbInstance;
		expect(second.id).not.toBe(first.id);
	});

	it('rejects missing fields, out-of-range sizes, unknown flavors, datastores and replica sources', () => {
		expect(status(() => call('POST', '/api/v1/database-instances', { ...DB_BODY, name: '' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/database-instances', { ...DB_BODY, flavor_id: '' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/database-instances', { ...DB_BODY, volume_size: 0 }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/database-instances', { ...DB_BODY, volume_size: 1025 }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/database-instances', { ...DB_BODY, flavor_id: '999' }))).toBe(502);
		expect(status(() => call('POST', '/api/v1/database-instances', { ...DB_BODY, datastore_version: '5.7' }))).toBe(502);
		expect(status(() => call('POST', '/api/v1/database-instances', { ...DB_BODY, replica_of: 'missing' }))).toBe(502);
		expect(getMockupState().dbInstances).toHaveLength(1);
	});

	it('returns 404 for an unknown delete and scopes the admin inventory to the selected project', () => {
		expect(status(() => call('DELETE', '/api/v1/database-instances/missing'))).toBe(404);
		expect(call('GET', '/api/v1/admin/database-instances')).toEqual([
			expect.objectContaining({ id: SAMPLE_DB.id, project_id: getMockupState().selectedProjectId }),
		]);
	});
});

describe('mockDatabaseContainers Magnum clusters', () => {
	it('serves at least one template so the create button can be enabled', () => {
		expect(call('GET', '/api/v1/clusters/templates')).toEqual([expect.objectContaining({ id: 'mock-magnum-template-k8s', coe: 'kubernetes' })]);
	});

	it('creates a cluster, lists it as in progress then complete, and deletes it', () => {
		const created = call('POST', '/api/v1/clusters', { ...CLUSTER_BODY, node_count: 2, keypair: '' }) as Cluster;
		expect(created).toMatchObject({ name: 'tutorial-cluster', status: 'CREATE_IN_PROGRESS', node_count: 2, master_count: 1, keypair: null });
		const first = call('GET', '/api/v1/clusters') as Cluster[];
		expect(first.find((item) => item.id === created.id)?.status).toBe('CREATE_IN_PROGRESS');
		const second = call('GET', '/api/v1/clusters') as Cluster[];
		expect(second.find((item) => item.id === created.id)).toMatchObject({ status: 'CREATE_COMPLETE', api_address: expect.any(String) });
		expect(call('DELETE', `/api/v1/clusters/${created.id}`)).toEqual({});
		expect((call('GET', '/api/v1/clusters') as Cluster[]).map((item) => item.id)).toEqual([SAMPLE_CLUSTER.id]);
	});

	it('accepts a duplicate name like Magnum and keeps distinct ids', () => {
		const first = call('POST', '/api/v1/clusters', CLUSTER_BODY) as Cluster;
		const second = call('POST', '/api/v1/clusters', CLUSTER_BODY) as Cluster;
		expect(second.id).not.toBe(first.id);
	});

	it('rejects invalid names, counts and unknown templates, and 404s an unknown delete', () => {
		expect(status(() => call('POST', '/api/v1/clusters', { ...CLUSTER_BODY, name: '' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/clusters', { ...CLUSTER_BODY, name: '-bad' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/clusters', { ...CLUSTER_BODY, name: 'a'.repeat(64) }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/clusters', { ...CLUSTER_BODY, master_count: 0 }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/clusters', { ...CLUSTER_BODY, node_count: 1.5 }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/clusters', { ...CLUSTER_BODY, cluster_template_id: 'missing' }))).toBe(500);
		expect(getMockupState().magnumClusters).toHaveLength(1);
		expect(status(() => call('DELETE', '/api/v1/clusters/missing'))).toBe(404);
	});

	it('leaves paths it does not own to the transport', () => {
		expect(call('GET', '/api/v1/database-instances/backups')).toBeUndefined();
		expect(call('GET', '/api/v1/k3s/clusters')).toBeUndefined();
		expect(call('GET', '/api/v1/clusters/mock-magnum-cluster-1')).toBeUndefined();
		expect(call('POST', '/api/v1/database-instances/mock-trove-instance-1/restart')).toBeUndefined();
	});
});
