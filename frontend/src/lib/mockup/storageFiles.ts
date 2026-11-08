import { ApiError } from '$lib/api/errors';
import type { FileStorage } from '$lib/types/fileStorage';
import type { VolumeSnapshot } from '$lib/types/volume';
import { getMockupState } from './state';

const CREATED_AT = '2026-11-08T00:00:00Z';
// One DHSS=False CephFS share type, so the wizard creates directly from its basic step (no share-network step).
const SHARE_TYPES = [{
	id: 'mock-share-type-cephfs',
	name: 'cephfs',
	is_default: true,
	extra_specs: { driver_handles_share_servers: 'False', storage_protocol: 'CEPHFS' },
	supported_protocols: ['CEPHFS'],
}];
// Manila accepts share deletion only from these states.
const SHARE_DELETABLE: Record<string, true> = { available: true, error: true, inactive: true, manage_error: true, unmanage_error: true, extending_error: true, shrinking_error: true, shrinking_possible_data_loss_error: true };
const SNAPSHOT_DELETABLE: Record<string, true> = { available: true, error: true, error_deleting: true };

function nextId(existing: { id: string }[], prefix: string): string {
	let n = existing.length + 1;
	while (existing.some((item) => item.id === `${prefix}-${n}`)) n += 1;
	return `${prefix}-${n}`;
}

function fileStorageQuota(shares: FileStorage[]) {
	const configured = getMockupState().quotas.file_storage;
	return {
		shares: { limit: configured.shares?.limit ?? 12, in_use: shares.length },
		gigabytes: { limit: configured.gigabytes?.limit ?? 4096, in_use: shares.reduce((sum, share) => sum + share.size, 0) },
		share_networks: { limit: configured.share_networks?.limit ?? 12, in_use: 0 },
	};
}

// Explicit synthetic tutorial state: Manila file share create/delete and Cinder volume snapshot create/delete.
// Returns undefined for paths this module does not own.
export function mockStorageFiles(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/file-storage' && method === 'GET') return state.fileShares;
	if (path === '/api/v1/file-storage/types' && method === 'GET') return SHARE_TYPES;
	if (path === '/api/v1/file-storage/quota' && method === 'GET') return fileStorageQuota(state.fileShares);
	if (path === '/api/v1/file-storage' && method === 'POST') {
		const payload = (body ?? {}) as { name?: unknown; size_gb?: unknown; share_type?: unknown; share_proto?: unknown; share_network_id?: unknown; metadata?: unknown };
		if (typeof payload.name !== 'string' || payload.name.length < 1 || payload.name.length > 255) throw new ApiError(422, 'File storage name must be 1 to 255 characters.');
		if (typeof payload.size_gb !== 'number' || !Number.isInteger(payload.size_gb) || payload.size_gb < 1 || payload.size_gb > 16384) throw new ApiError(422, 'Size must be an integer from 1 to 16384 GB.');
		const proto = payload.share_proto === undefined ? 'CEPHFS' : payload.share_proto;
		if (proto !== 'CEPHFS' && proto !== 'NFS') throw new ApiError(422, 'Protocol must be CEPHFS or NFS.');
		const typeName = payload.share_type === undefined ? '' : payload.share_type;
		if (typeof typeName !== 'string') throw new ApiError(422, 'Share type must be a string.');
		const shareType = typeName ? SHARE_TYPES.find((item) => item.id === typeName || item.name === typeName) : SHARE_TYPES.find((item) => item.is_default);
		if (!shareType) throw new ApiError(422, 'The selected share type is not available.');
		// The synthetic project has no tenant share network, so an NFS share cannot be created.
		if (proto === 'NFS') throw new ApiError(422, payload.share_network_id ? 'The selected share network is not available.' : 'An NFS share needs a tenant share network.');
		const quota = fileStorageQuota(state.fileShares);
		if (quota.shares.in_use + 1 > quota.shares.limit) throw new ApiError(413, 'Share quota exceeded.');
		if (quota.gigabytes.in_use + payload.size_gb > quota.gigabytes.limit) throw new ApiError(413, 'Share gigabytes quota exceeded.');
		const metadata: Record<string, string> = {};
		if (payload.metadata && typeof payload.metadata === 'object') {
			for (const [key, value] of Object.entries(payload.metadata as Record<string, unknown>)) metadata[key] = String(value);
		}
		const id = nextId(state.fileShares, 'mock-share');
		const exportPath = `192.0.2.10:6789:/volumes/_nogroup/${id}`;
		// The real create call waits for Manila to report the share available before replying.
		const created: FileStorage = {
			id, name: payload.name, status: 'available', size: payload.size_gb, share_proto: proto,
			export_locations: [exportPath], metadata, project_id: state.selectedProjectId,
			created_at: CREATED_AT, is_public: false, library_name: null, library_version: null, built_at: null,
			progress: '100%', user_id: 'mock-user-1', user_name: 'demo-user', access_rules_status: 'active',
			host: null, availability_zone: 'nova', share_type_name: shareType.name, share_network_id: null,
			export_location_details: [{ path: exportPath, preferred: true, share_instance_id: null }],
		};
		state.fileShares.push(created);
		return created;
	}
	const shareRules = path.match(/^\/api\/v1\/file-storage\/([^/]+)\/access-rules$/);
	if (shareRules && method === 'GET') {
		const id = decodeURIComponent(shareRules[1]);
		if (!state.fileShares.some((entry) => entry.id === id)) throw new ApiError(404, 'File storage not found.');
		return [];
	}
	const share = path.match(/^\/api\/v1\/file-storage\/([^/]+)$/);
	if (share && (method === 'GET' || method === 'DELETE')) {
		const id = decodeURIComponent(share[1]);
		const item = state.fileShares.find((entry) => entry.id === id);
		if (!item) throw new ApiError(404, 'File storage not found.');
		if (method === 'GET') return item;
		if (!Object.hasOwn(SHARE_DELETABLE, item.status)) throw new ApiError(500, 'File storage deletion failed: the share is busy.');
		state.fileShares = state.fileShares.filter((entry) => entry.id !== id);
		return {};
	}

	if (path === '/api/v1/volume-snapshots' && method === 'GET') {
		// Like Cinder, a new snapshot is `creating` in the POST reply; the synthetic one is finished by the next list read.
		for (const entry of state.volumeSnapshots) if (entry.status === 'creating') entry.status = 'available';
		return state.volumeSnapshots;
	}
	if (path === '/api/v1/volume-snapshots' && method === 'POST') {
		const payload = (body ?? {}) as { volume_id?: unknown; name?: unknown; description?: unknown; force?: unknown };
		if (typeof payload.volume_id !== 'string' || typeof payload.name !== 'string') throw new ApiError(422, 'Volume and snapshot name are required.');
		const volume = state.volumes.find((entry) => entry.id === payload.volume_id);
		if (!volume) throw new ApiError(404, 'Volume not found.');
		if (volume.status === 'in-use' && payload.force !== true) throw new ApiError(400, 'Invalid volume: the volume is in use. Turn on force snapshot to snapshot an attached volume.');
		if (volume.status !== 'available' && volume.status !== 'in-use') throw new ApiError(400, `Invalid volume: status must be available, but current status is: ${volume.status}.`);
		const created: VolumeSnapshot = {
			id: nextId(state.volumeSnapshots, 'mock-volume-snapshot'),
			name: payload.name,
			status: 'creating',
			volume_id: volume.id,
			size: volume.size,
			description: typeof payload.description === 'string' ? payload.description : '',
			created_at: CREATED_AT,
			project_id: state.selectedProjectId,
		};
		state.volumeSnapshots.push(created);
		return created;
	}
	const snapshot = path.match(/^\/api\/v1\/volume-snapshots\/([^/]+)$/);
	if (snapshot && method === 'DELETE') {
		const id = decodeURIComponent(snapshot[1]);
		const item = state.volumeSnapshots.find((entry) => entry.id === id);
		if (!item) throw new ApiError(404, 'Snapshot not found.');
		if (!Object.hasOwn(SNAPSHOT_DELETABLE, item.status)) throw new ApiError(500, 'Snapshot deletion failed: the snapshot must be available or in error.');
		state.volumeSnapshots = state.volumeSnapshots.filter((entry) => entry.id !== id);
		return {};
	}
	return undefined;
}
