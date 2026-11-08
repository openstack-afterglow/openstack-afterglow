import { describe, expect, it, beforeEach } from 'vitest';
import { ApiError } from '$lib/api/errors';
import { mockStorageSecrets } from './storageSecrets';
import { resetMockupState } from './state';

type Secret = { id: string; name: string | null; secret_type: string; system_managed: boolean };
type Backup = { id: string; name: string; volume_id: string; is_incremental: boolean; has_dependent_backups: boolean };

const secrets = () => mockStorageSecrets('GET', '/api/v1/secrets', null) as Secret[];
const backups = () => mockStorageSecrets('GET', '/api/v1/volumes/backups', null) as Backup[];

describe('mockStorageSecrets Key Manager secrets', () => {
	beforeEach(() => resetMockupState());

	it('creates a secret without exposing its payload and deletes it by id', () => {
		const seeded = secrets().length;
		const created = mockStorageSecrets('POST', '/api/v1/secrets', { name: 'qa-db-password', secret_type: 'passphrase', payload: 'hunter2' }) as Secret;
		expect(created).toMatchObject({ name: 'qa-db-password', secret_type: 'passphrase', system_managed: false });
		expect(created).not.toHaveProperty('payload');
		expect(secrets().map((item) => item.id)).toContain(created.id);
		mockStorageSecrets('DELETE', `/api/v1/secrets/${created.id}`, null);
		expect(secrets()).toHaveLength(seeded);
		expect(() => mockStorageSecrets('DELETE', `/api/v1/secrets/${created.id}`, null)).toThrow(ApiError);
	});

	it('allows duplicate names like Barbican but gives each secret its own id', () => {
		const first = mockStorageSecrets('POST', '/api/v1/secrets', { name: 'dup', secret_type: 'opaque' }) as Secret;
		const second = mockStorageSecrets('POST', '/api/v1/secrets', { name: 'dup', secret_type: 'opaque' }) as Secret;
		expect(first.id).not.toBe(second.id);
	});

	it('rejects a missing name, an unknown type and deleting a system-managed secret', () => {
		expect(() => mockStorageSecrets('POST', '/api/v1/secrets', { secret_type: 'passphrase' })).toThrow(ApiError);
		expect(() => mockStorageSecrets('POST', '/api/v1/secrets', { name: 'x', secret_type: 'toString' })).toThrow(ApiError);
		const system = secrets().find((item) => item.system_managed);
		expect(system).toBeDefined();
		expect(() => mockStorageSecrets('DELETE', `/api/v1/secrets/${system!.id}`, null)).toThrow(ApiError);
		expect(secrets().some((item) => item.id === system!.id)).toBe(true);
	});
});

describe('mockStorageSecrets volume backups', () => {
	beforeEach(() => resetMockupState());

	it('creates a backup of an available volume and deletes it by id once it is available', () => {
		const seeded = backups().length;
		const created = mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'mock-volume-2', name: 'qa-backup', description: '', incremental: false, force: false }) as Backup & { status: string };
		expect(created).toMatchObject({ name: 'qa-backup', volume_id: 'mock-volume-2', is_incremental: false, status: 'creating' });
		expect(() => mockStorageSecrets('DELETE', `/api/v1/volumes/backups/${created.id}`, null)).toThrow(ApiError);
		expect(backups().find((item) => item.id === created.id)).toMatchObject({ status: 'available' });
		mockStorageSecrets('DELETE', `/api/v1/volumes/backups/${created.id}`, null);
		expect(backups()).toHaveLength(seeded);
		expect(() => mockStorageSecrets('DELETE', `/api/v1/volumes/backups/${created.id}`, null)).toThrow(ApiError);
	});

	it('requires force for an in-use volume and rejects an unknown volume or missing name', () => {
		expect(() => mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'mock-volume-1', name: 'root', force: false })).toThrow(ApiError);
		expect(mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'mock-volume-1', name: 'root', force: true })).toMatchObject({ volume_id: 'mock-volume-1' });
		expect(() => mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'missing', name: 'x' })).toThrow(ApiError);
		expect(() => mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'mock-volume-2' })).toThrow(ApiError);
	});

	it('needs a full backup before an incremental one and protects backups with dependents', () => {
		expect(() => mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'mock-volume-1', name: 'inc', incremental: true, force: true })).toThrow(ApiError);
		const full = mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'mock-volume-1', name: 'full', force: true }) as Backup;
		expect(() => mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'mock-volume-1', name: 'inc', incremental: true, force: true })).toThrow(ApiError);
		backups();
		mockStorageSecrets('POST', '/api/v1/volumes/backups', { volume_id: 'mock-volume-1', name: 'inc', incremental: true, force: true });
		backups();
		expect(() => mockStorageSecrets('DELETE', `/api/v1/volumes/backups/${full.id}`, null)).toThrow(ApiError);
		expect(backups().some((item) => item.id === full.id)).toBe(true);
	});

	it('returns undefined for paths it does not own', () => {
		expect(mockStorageSecrets('GET', '/api/v1/volumes', null)).toBeUndefined();
		expect(mockStorageSecrets('POST', '/api/v1/secret-containers', {})).toBeUndefined();
		expect(mockStorageSecrets('POST', '/api/v1/volumes/backups/mock-backup-1/restore', {})).toBeUndefined();
	});
});
