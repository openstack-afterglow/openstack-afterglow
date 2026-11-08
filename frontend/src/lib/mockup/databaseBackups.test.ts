import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { DbBackup, DbInstance } from '$lib/types/database';
import { mockDatabaseBackups } from './databaseBackups';
import { getMockupState, resetMockupState } from './state';

const SAMPLE_DB: DbInstance = {
	id: 'mock-trove-instance-1', name: 'sample-customer-mysql', status: 'ACTIVE',
	datastore: { type: 'mysql', version: '8.0' }, flavor_id: '101', size: 20, created_at: '2026-07-09T00:00:00Z',
};
const SAMPLE_BACKUP: DbBackup = {
	id: 'mock-trove-backup-1', name: 'sample-customer-mysql-weekly', status: 'COMPLETED', size: 0.42,
	created_at: '2026-07-08T21:00:00Z', instance_id: 'mock-trove-instance-1', datastore: { type: 'mysql', version: '8.0' },
};

function call(method: string, path: string, body: unknown = null): unknown {
	return mockDatabaseBackups(method, path, body);
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
	Object.assign(getMockupState(), { dbInstances: [structuredClone(SAMPLE_DB)], dbBackups: [structuredClone(SAMPLE_BACKUP)] });
});

describe('mock Trove database backups', () => {
	it('serves the instance detail reads the backup panel needs', () => {
		expect(call('GET', '/api/v1/database-instances/mock-trove-instance-1')).toEqual(SAMPLE_DB);
		expect(call('GET', '/api/v1/database-instances/mock-trove-instance-1/databases')).toEqual([]);
		expect(call('GET', '/api/v1/database-instances/mock-trove-instance-1/users')).toEqual([]);
		expect(call('GET', '/api/v1/database-instances/mock-trove-instance-1/backups')).toEqual([SAMPLE_BACKUP]);
		expect(status(() => call('GET', '/api/v1/database-instances/mock-trove-instance-1/auto-backup'))).toBe(404);
		expect(status(() => call('GET', '/api/v1/database-instances/missing'))).toBe(404);
		expect(status(() => call('GET', '/api/v1/database-instances/missing/backups'))).toBe(404);
	});

	it('creates a backup that settles after one listing and deletes only that backup', () => {
		const created = call('POST', '/api/v1/database-instances/mock-trove-instance-1/backups', { name: 'tut-backup', description: '' }) as DbBackup;
		expect(created).toMatchObject({ name: 'tut-backup', status: 'NEW', instance_id: 'mock-trove-instance-1' });
		expect(created.id).not.toBe(SAMPLE_BACKUP.id);
		// Trove rejects deleting an in-progress backup.
		expect(status(() => call('DELETE', `/api/v1/database-instances/backups/${created.id}`))).toBe(500);
		const first = call('GET', '/api/v1/database-instances/mock-trove-instance-1/backups') as DbBackup[];
		expect(first.find((item) => item.id === created.id)?.status).toBe('NEW');
		const all = call('GET', '/api/v1/database-instances/backups') as DbBackup[];
		expect(all.map((item) => [item.id, item.status])).toEqual([[SAMPLE_BACKUP.id, 'COMPLETED'], [created.id, 'COMPLETED']]);
		expect(call('DELETE', `/api/v1/database-instances/backups/${created.id}`)).toEqual({});
		expect(getMockupState().dbBackups).toEqual([SAMPLE_BACKUP]);
		expect(status(() => call('DELETE', `/api/v1/database-instances/backups/${created.id}`))).toBe(404);
	});

	it('rejects invalid names and non-ACTIVE instances like the backend', () => {
		expect(status(() => call('POST', '/api/v1/database-instances/mock-trove-instance-1/backups', { name: '' }))).toBe(422);
		getMockupState().dbInstances[0].status = 'BUILD';
		expect(status(() => call('POST', '/api/v1/database-instances/mock-trove-instance-1/backups', { name: 'tut-backup' }))).toBe(502);
		expect(status(() => call('POST', '/api/v1/database-instances/missing/backups', { name: 'tut-backup' }))).toBe(404);
		expect(getMockupState().dbBackups).toEqual([SAMPLE_BACKUP]);
	});

	it('leaves unrelated paths to the transport', () => {
		expect(call('POST', '/api/v1/database-instances/restore', {})).toBeUndefined();
		expect(call('GET', '/api/v1/clusters')).toBeUndefined();
	});
});
