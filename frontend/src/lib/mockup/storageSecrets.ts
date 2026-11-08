import { ApiError } from '$lib/api/errors';
import type { SecretInfo } from '$lib/api/secrets';
import type { VolumeBackup } from '$lib/types/volume';
import { getMockupState } from './state';

const CREATED_AT = '2026-11-08T00:00:00Z';
// Barbican secret types accepted by the native create call.
const SECRET_TYPES: Record<string, true> = { passphrase: true, certificate: true, symmetric: true, public: true, private: true, opaque: true };

function nextId(existing: { id: string }[], prefix: string): string {
	let n = existing.length + 1;
	while (existing.some((item) => item.id === `${prefix}-${n}`)) n += 1;
	return `${prefix}-${n}`;
}

// Explicit synthetic tutorial state: Key Manager secret create/delete and Cinder volume backup create/delete.
// Payloads are never stored or returned. Returns undefined for paths this module does not own.
export function mockStorageSecrets(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/secrets' && method === 'GET') return state.secrets;
	if (path === '/api/v1/secrets' && method === 'POST') {
		const payload = (body ?? {}) as { name?: unknown; secret_type?: unknown };
		if (typeof payload.name !== 'string') throw new ApiError(422, 'Secret name is required.');
		const secretType = payload.secret_type === undefined ? 'opaque' : String(payload.secret_type);
		if (!Object.hasOwn(SECRET_TYPES, secretType)) throw new ApiError(500, 'Secret creation failed.');
		const created: SecretInfo = {
			id: nextId(state.secrets, 'mock-secret'),
			name: payload.name,
			secret_type: secretType,
			status: 'ACTIVE',
			algorithm: null,
			bit_length: null,
			mode: null,
			created: CREATED_AT,
			expires: null,
			content_types: { default: 'text/plain' },
			system_managed: false,
		};
		state.secrets.push(created);
		return created;
	}
	const secret = path.match(/^\/api\/v1\/secrets\/([^/]+)$/);
	if (secret && method === 'DELETE') {
		const id = decodeURIComponent(secret[1]);
		const item = state.secrets.find((entry) => entry.id === id);
		if (!item) throw new ApiError(404, 'Secret not found.');
		if (item.system_managed) throw new ApiError(403, 'System-managed secrets cannot be deleted.');
		state.secrets = state.secrets.filter((entry) => entry.id !== id);
		return {};
	}

	if (path === '/api/v1/volumes/backups' && method === 'GET') {
		// Like Cinder, a new backup is `creating` in the POST reply; the synthetic one is finished by the next list read.
		for (const entry of state.volumeBackups) if (entry.status === 'creating') entry.status = 'available';
		return state.volumeBackups;
	}
	if (path === '/api/v1/volumes/backups/auto-backup/configs' && method === 'GET') return [];
	if (path === '/api/v1/volumes/backups' && method === 'POST') {
		const payload = (body ?? {}) as { volume_id?: unknown; name?: unknown; description?: unknown; incremental?: unknown; force?: unknown };
		if (typeof payload.volume_id !== 'string' || typeof payload.name !== 'string') throw new ApiError(422, 'Volume and backup name are required.');
		const volume = state.volumes.find((entry) => entry.id === payload.volume_id);
		if (!volume) throw new ApiError(404, 'Volume not found.');
		if (volume.status === 'in-use' && payload.force !== true) throw new ApiError(400, 'Enable force backup to back up an in-use volume.');
		const incremental = payload.incremental === true;
		const parent = state.volumeBackups.find((entry) => entry.volume_id === volume.id && entry.status === 'available');
		if (incremental && !parent) throw new ApiError(400, 'No backups available to do an incremental backup.');
		if (parent && incremental) parent.has_dependent_backups = true;
		const created: VolumeBackup = {
			id: nextId(state.volumeBackups, 'mock-backup'),
			name: payload.name,
			description: typeof payload.description === 'string' && payload.description ? payload.description : null,
			volume_id: volume.id,
			status: 'creating',
			size: volume.size,
			created_at: CREATED_AT,
			is_incremental: incremental,
			has_dependent_backups: false,
		};
		state.volumeBackups.push(created);
		return created;
	}
	const backup = path.match(/^\/api\/v1\/volumes\/backups\/([^/]+)$/);
	if (backup && method === 'DELETE') {
		const id = decodeURIComponent(backup[1]);
		const item = state.volumeBackups.find((entry) => entry.id === id);
		if (!item) throw new ApiError(404, 'Backup not found.');
		if (item.status !== 'available' && item.status !== 'error') throw new ApiError(500, 'Backup deletion failed: the backup must be available or in error.');
		if (item.has_dependent_backups) throw new ApiError(500, 'Backup deletion failed: incremental backups depend on it.');
		state.volumeBackups = state.volumeBackups.filter((entry) => entry.id !== id);
		return {};
	}
	return undefined;
}
