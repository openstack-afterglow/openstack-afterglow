import { ApiError } from '$lib/api/errors';
import type { Cluster, ClusterTemplate } from '$lib/types/cluster';
import type { DbFlavor, DbInstance } from '$lib/types/database';
import { getMockupState } from './state';

// Explicit synthetic tutorial state: Trove database instances and Magnum clusters (create, list, delete).
// Returns undefined for paths this module does not own so transport can keep its own dispatch.
// Neither Trove nor Magnum enforces unique names, so duplicates are accepted and pages track the created id.
const CREATED_AT = '2026-11-08T00:00:00Z';
const CLUSTER_NAME = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$/;

const DB_FLAVORS: (DbFlavor & { disk: number })[] = [
	{ id: '101', name: 'db.small', vcpus: 2, ram: 2048, disk: 0 },
	{ id: '102', name: 'db.medium', vcpus: 4, ram: 4096, disk: 0 },
];
const DB_DATASTORES = [
	{ id: 'mock-datastore-mysql', name: 'mysql', versions: [{ id: 'mock-datastore-mysql-8-0', name: '8.0' }] },
	{ id: 'mock-datastore-postgresql', name: 'postgresql', versions: [{ id: 'mock-datastore-postgresql-16', name: '16' }] },
];
const DB_VOLUME_TYPES = [{ id: 'mock-volume-type-ceph-ssd', name: 'ceph-ssd' }];
const CLUSTER_TEMPLATES: ClusterTemplate[] = [{ id: 'mock-magnum-template-k8s', name: 'k8s-v1.30-fedora-coreos', coe: 'kubernetes' }];

function nextId(existing: string[], prefix: string): string {
	let index = existing.length + 1;
	while (existing.includes(`${prefix}-${index}`)) index++;
	return `${prefix}-${index}`;
}

function requiredText(value: unknown, max: number): string | null {
	return typeof value === 'string' && value.length >= 1 && value.length <= max ? value : null;
}

function positiveInteger(value: unknown): number | null {
	const number = typeof value === 'string' && value.trim() !== '' ? Number(value) : value;
	return typeof number === 'number' && Number.isInteger(number) && number >= 1 ? number : null;
}

function createDbInstance(body: unknown): DbInstance {
	const state = getMockupState();
	const payload = (body ?? {}) as Record<string, unknown>;
	const name = requiredText(payload.name, 255);
	const flavorId = requiredText(payload.flavor_id, 255);
	const datastoreType = requiredText(payload.datastore_type, 255);
	const datastoreVersion = requiredText(payload.datastore_version, 255);
	const volumeSize = positiveInteger(payload.volume_size);
	if (!name || !flavorId || !datastoreType || !datastoreVersion || volumeSize === null || volumeSize > 1024) {
		throw new ApiError(422, 'Name, flavor, datastore, version and a 1-1024 GB volume size are required.');
	}
	const flavor = DB_FLAVORS.find((item) => item.id === flavorId);
	if (!flavor) throw new ApiError(502, `Flavor ${flavorId} could not be found.`);
	const datastore = DB_DATASTORES.find((item) => item.name === datastoreType);
	if (!datastore || !datastore.versions.some((version) => version.name === datastoreVersion)) {
		throw new ApiError(502, `Datastore ${datastoreType} ${datastoreVersion} could not be found.`);
	}
	const replicaOf = payload.replica_of;
	if (replicaOf != null && !state.dbInstances.some((item) => item.id === replicaOf)) {
		throw new ApiError(502, 'The replication source instance could not be found.');
	}
	const created: DbInstance = {
		id: nextId(state.dbInstances.map((item) => item.id), 'mock-trove-instance'),
		name,
		status: 'BUILD',
		datastore: { type: datastoreType, version: datastoreVersion },
		flavor_id: flavor.id as string,
		flavor_ram: flavor.ram,
		flavor_vcpus: flavor.vcpus,
		size: volumeSize,
		created_at: CREATED_AT,
		hostname: '',
		ip: '',
		ips: [],
		address_map: {},
		volume_used: 0,
	};
	state.dbInstances.push(created);
	return { ...created };
}

function createCluster(body: unknown): Cluster {
	const state = getMockupState();
	const payload = (body ?? {}) as Record<string, unknown>;
	const name = typeof payload.name === 'string' ? payload.name : '';
	if (!CLUSTER_NAME.test(name)) {
		throw new ApiError(422, 'Name must start with a letter or digit and use only letters, digits, hyphens or underscores (max 63).');
	}
	const masterCount = payload.master_count === undefined ? 1 : positiveInteger(payload.master_count);
	const nodeCount = payload.node_count === undefined ? 1 : positiveInteger(payload.node_count);
	if (masterCount === null || nodeCount === null) throw new ApiError(422, 'Master and worker counts must be positive integers.');
	const templateId = typeof payload.cluster_template_id === 'string' ? payload.cluster_template_id : '';
	// The backend reports every Magnum rejection, including an unknown template, as a generic 500.
	if (!CLUSTER_TEMPLATES.some((template) => template.id === templateId)) throw new ApiError(500, 'Cluster creation failed.');
	const id = nextId(state.magnumClusters.map((item) => item.id), 'mock-magnum-cluster');
	const keypair = typeof payload.keypair === 'string' && payload.keypair.trim() ? payload.keypair : null;
	const created: Cluster = {
		id,
		name,
		status: 'CREATE_IN_PROGRESS',
		status_reason: null,
		cluster_template_id: templateId,
		master_count: masterCount,
		node_count: nodeCount,
		api_address: null,
		coe_version: null,
		keypair,
		create_timeout: typeof payload.create_timeout === 'number' ? payload.create_timeout : null,
		created_at: CREATED_AT,
		updated_at: null,
		stack_id: `${id}-stack`,
	};
	state.magnumClusters.push(created);
	return { ...created };
}

export function mockDatabaseContainers(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();

	if (method === 'GET' && path === '/api/v1/database-instances') {
		const snapshot = state.dbInstances.map((item) => ({ ...item }));
		// Provisioning settles after the first listing so a later refresh shows the instance as ACTIVE.
		for (const item of state.dbInstances) if (item.status === 'BUILD') item.status = 'ACTIVE';
		return snapshot;
	}
	if (method === 'GET' && path === '/api/v1/admin/database-instances') {
		return state.dbInstances.map((item) => ({ ...item, project_id: state.selectedProjectId }));
	}
	if (method === 'GET' && path === '/api/v1/database-instances/flavors') return DB_FLAVORS.map((item) => ({ ...item }));
	if (method === 'GET' && path === '/api/v1/database-instances/datastores') return structuredClone(DB_DATASTORES);
	if (method === 'GET' && path === '/api/v1/database-instances/volume-types') return DB_VOLUME_TYPES.map((item) => ({ ...item }));
	if (method === 'GET' && path === '/api/v1/database-instances/configurations') return [];
	if (method === 'POST' && path === '/api/v1/database-instances') return createDbInstance(body);
	const dbInstanceId = path.match(/^\/api\/v1\/database-instances\/([^/]+)$/)?.[1];
	if (method === 'DELETE' && dbInstanceId) {
		const id = decodeURIComponent(dbInstanceId);
		if (!state.dbInstances.some((item) => item.id === id)) throw new ApiError(404, 'Database instance not found.');
		state.dbInstances = state.dbInstances.filter((item) => item.id !== id);
		return {};
	}

	if (method === 'GET' && path === '/api/v1/clusters') {
		const snapshot = state.magnumClusters.map((item) => ({ ...item }));
		for (const item of state.magnumClusters) {
			if (item.status !== 'CREATE_IN_PROGRESS') continue;
			item.status = 'CREATE_COMPLETE';
			item.api_address = 'https://192.0.2.80:6443';
			item.coe_version = 'v1.30.4';
			item.updated_at = CREATED_AT;
		}
		return snapshot;
	}
	if (method === 'GET' && path === '/api/v1/clusters/templates') return CLUSTER_TEMPLATES.map((item) => ({ ...item }));
	if (method === 'POST' && path === '/api/v1/clusters') return createCluster(body);
	const clusterId = path.match(/^\/api\/v1\/clusters\/([^/]+)$/)?.[1];
	if (method === 'DELETE' && clusterId) {
		const id = decodeURIComponent(clusterId);
		if (!state.magnumClusters.some((item) => item.id === id)) throw new ApiError(404, 'Cluster not found.');
		state.magnumClusters = state.magnumClusters.filter((item) => item.id !== id);
		return {};
	}
	return undefined;
}
