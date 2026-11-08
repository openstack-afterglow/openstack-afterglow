import { describe, expect, it, beforeEach } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { FileStorage } from '$lib/types/fileStorage';
import type { VolumeSnapshot } from '$lib/types/volume';
import { mockStorageFiles } from './storageFiles';
import { getMockupState, resetMockupState } from './state';

function call(method: string, path: string, body: unknown = null): unknown {
	return mockStorageFiles(method, path, body);
}

function status(fn: () => unknown): number | undefined {
	try {
		fn();
	} catch (error) {
		return error instanceof ApiError ? error.status : undefined;
	}
	return undefined;
}

const shares = () => call('GET', '/api/v1/file-storage') as FileStorage[];
const snapshots = () => call('GET', '/api/v1/volume-snapshots') as VolumeSnapshot[];

beforeEach(() => {
	resetMockupState();
	// Same seed the merged state.ts carries; a no-op once the state fields are merged.
	const state = getMockupState() as unknown as { fileShares?: FileStorage[]; volumeSnapshots?: VolumeSnapshot[] };
	state.fileShares ??= [{
		id: 'mock-share-1', name: 'demo-dataset', status: 'available', size: 200, share_proto: 'CEPHFS',
		export_locations: ['192.0.2.10:6789:/volumes/demo-dataset'], metadata: {}, project_id: 'mock-project', created_at: '2026-07-09T00:00:00Z',
		is_public: false, library_name: null, library_version: null, built_at: null, progress: '100%', user_id: 'mock-user-1', user_name: 'demo-user',
		access_rules_status: 'active', host: 'sample-manila-host', availability_zone: 'nova', share_type_name: 'cephfs', share_network_id: null,
		export_location_details: [{ path: '192.0.2.10:6789:/volumes/demo-dataset', preferred: true, share_instance_id: null }],
	}];
	state.volumeSnapshots ??= [{ id: 'mock-volume-snapshot-1', name: 'root-disk-before-upgrade', status: 'available', volume_id: 'mock-volume-1', size: 80, description: '', created_at: '2026-07-08T20:00:00Z' }];
});

describe('mockStorageFiles file shares', () => {
	it('offers one DHSS=False CephFS share type so the wizard creates from its basic step', () => {
		const types = call('GET', '/api/v1/file-storage/types') as { name: string; is_default: boolean; extra_specs: Record<string, string>; supported_protocols: string[] }[];
		expect(types).toHaveLength(1);
		expect(types[0]).toMatchObject({ name: 'cephfs', is_default: true, supported_protocols: ['CEPHFS'] });
		expect(types[0].extra_specs.driver_handles_share_servers.toLowerCase()).not.toBe('true');
	});

	it('creates an available CephFS share like the wizard does, lists it and deletes it by id', () => {
		const seeded = shares().map((item) => item.id);
		const created = call('POST', '/api/v1/file-storage', { name: 'qa-share', size_gb: 10, share_type: 'cephfs', share_proto: 'CEPHFS', metadata: { team: 'qa' } }) as FileStorage;
		expect(created).toMatchObject({ name: 'qa-share', size: 10, share_proto: 'CEPHFS', status: 'available', share_type_name: 'cephfs', metadata: { team: 'qa' } });
		expect(created.export_locations[0]).toContain(created.id);
		expect(shares().map((item) => item.id)).toEqual([...seeded, created.id]);
		expect(call('GET', `/api/v1/file-storage/${created.id}`)).toMatchObject({ id: created.id });
		expect(call('GET', `/api/v1/file-storage/${created.id}/access-rules`)).toEqual([]);
		call('DELETE', `/api/v1/file-storage/${created.id}`);
		expect(shares().map((item) => item.id)).toEqual(seeded);
		expect(status(() => call('DELETE', `/api/v1/file-storage/${created.id}`))).toBe(404);
		expect(status(() => call('GET', `/api/v1/file-storage/${created.id}/access-rules`))).toBe(404);
	});

	it('rejects invalid input like the API model and Manila policy', () => {
		const before = shares().length;
		expect(status(() => call('POST', '/api/v1/file-storage', { name: '', size_gb: 10 }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/file-storage', { name: 'x', size_gb: 0 }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/file-storage', { name: 'x', size_gb: 1.5 }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/file-storage', { name: 'x', size_gb: 10, share_proto: 'SMB' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/file-storage', { name: 'x', size_gb: 10, share_type: 'missing-type' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/file-storage', { name: 'x', size_gb: 10, share_proto: 'NFS' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/file-storage', { name: 'x', size_gb: 10, share_proto: 'NFS', share_network_id: 'mock-sn' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/file-storage', { name: 'x', size_gb: 16384 }))).toBe(413);
		expect(shares()).toHaveLength(before);
	});

	it('allows duplicate names like Manila but gives each share its own id', () => {
		const first = call('POST', '/api/v1/file-storage', { name: 'dup', size_gb: 1 }) as FileStorage;
		const second = call('POST', '/api/v1/file-storage', { name: 'dup', size_gb: 1 }) as FileStorage;
		expect(first.id).not.toBe(second.id);
	});

	it('enforces the share count quota and reports usage', () => {
		const limit = (call('GET', '/api/v1/file-storage/quota') as { shares: { limit: number } }).shares.limit;
		while (shares().length < limit) call('POST', '/api/v1/file-storage', { name: 'fill', size_gb: 1 });
		expect(status(() => call('POST', '/api/v1/file-storage', { name: 'over', size_gb: 1 }))).toBe(413);
		expect(call('GET', '/api/v1/file-storage/quota')).toMatchObject({ shares: { limit, in_use: limit } });
	});

	it('refuses to delete a busy share', () => {
		const created = call('POST', '/api/v1/file-storage', { name: 'busy', size_gb: 1 }) as FileStorage;
		getMockupState().fileShares.find((item) => item.id === created.id)!.status = 'extending';
		expect(status(() => call('DELETE', `/api/v1/file-storage/${created.id}`))).toBe(500);
	});
});

describe('mockStorageFiles volume snapshots', () => {
	it('snapshots an available volume, finishes it on the next list read and deletes it', () => {
		const seeded = snapshots().map((item) => item.id);
		const created = call('POST', '/api/v1/volume-snapshots', { volume_id: 'mock-volume-2', name: 'qa-snap', description: '', force: false }) as VolumeSnapshot;
		expect(created).toMatchObject({ name: 'qa-snap', volume_id: 'mock-volume-2', size: 200, status: 'creating' });
		expect(status(() => call('DELETE', `/api/v1/volume-snapshots/${created.id}`))).toBe(500);
		expect(snapshots().find((item) => item.id === created.id)?.status).toBe('available');
		call('DELETE', `/api/v1/volume-snapshots/${created.id}`);
		expect(snapshots().map((item) => item.id)).toEqual(seeded);
		expect(status(() => call('DELETE', `/api/v1/volume-snapshots/${created.id}`))).toBe(404);
	});

	it('needs force for an in-use volume and rejects missing volumes or names', () => {
		const before = snapshots().length;
		expect(status(() => call('POST', '/api/v1/volume-snapshots', { volume_id: 'mock-volume-1', name: 'root', force: false }))).toBe(400);
		expect(status(() => call('POST', '/api/v1/volume-snapshots', { volume_id: 'missing-volume', name: 'x' }))).toBe(404);
		expect(status(() => call('POST', '/api/v1/volume-snapshots', { volume_id: 'mock-volume-2' }))).toBe(422);
		expect(snapshots()).toHaveLength(before);
		const forced = call('POST', '/api/v1/volume-snapshots', { volume_id: 'mock-volume-1', name: 'root', force: true }) as VolumeSnapshot;
		expect(forced.volume_id).toBe('mock-volume-1');
	});

	it('allows duplicate names like Cinder but gives each snapshot its own id', () => {
		const first = call('POST', '/api/v1/volume-snapshots', { volume_id: 'mock-volume-2', name: 'dup' }) as VolumeSnapshot;
		const second = call('POST', '/api/v1/volume-snapshots', { volume_id: 'mock-volume-2', name: 'dup' }) as VolumeSnapshot;
		expect(first.id).not.toBe(second.id);
	});

	it('returns undefined for paths it does not own', () => {
		expect(call('GET', '/api/v1/volumes')).toBeUndefined();
		expect(call('GET', '/api/v1/share-snapshots')).toBeUndefined();
		expect(call('GET', '/api/v1/volumes/backups')).toBeUndefined();
	});
});
