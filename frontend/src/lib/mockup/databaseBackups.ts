import { ApiError } from '$lib/api/errors';
import type { DbBackup, DbInstance } from '$lib/types/database';
import { getMockupState } from './state';

// Explicit synthetic tutorial state: Trove instance detail reads and database backups (create, list, delete).
// Returns undefined for paths this module does not own so transport can keep its own dispatch.
// Trove does not enforce unique backup names, so the detail controller tracks the created id.
const CREATED_AT = '2026-11-08T00:00:00Z';
const SETTLED: Record<string, true> = { COMPLETED: true, FAILED: true, ERROR: true };

function nextId(existing: string[], prefix: string): string {
	let index = existing.length + 1;
	while (existing.includes(`${prefix}-${index}`)) index++;
	return `${prefix}-${index}`;
}

function ownedInstance(id: string): DbInstance {
	const instance = getMockupState().dbInstances.find((item) => item.id === id);
	if (!instance) throw new ApiError(404, 'Database instance not found.');
	return instance;
}

// A new backup reads NEW once, then settles so the next refresh shows it COMPLETED.
// The tour's delete step waits for that, which exercises the engine's settle wait.
function listBackups(instanceId?: string): DbBackup[] {
	const state = getMockupState();
	const rows = state.dbBackups.filter((item) => instanceId === undefined || item.instance_id === instanceId);
	const snapshot = rows.map((item) => structuredClone(item));
	for (const item of rows) if (item.status === 'NEW') item.status = 'COMPLETED';
	return snapshot;
}

function createBackup(instanceId: string, body: unknown): DbBackup {
	const state = getMockupState();
	const instance = ownedInstance(instanceId);
	const payload = (body ?? {}) as Record<string, unknown>;
	const name = typeof payload.name === 'string' && payload.name.length >= 1 && payload.name.length <= 255 ? payload.name : null;
	if (!name) throw new ApiError(422, 'A backup name of 1-255 characters is required.');
	if (instance.status !== 'ACTIVE') throw new ApiError(502, 'Trove accepts backups only for ACTIVE instances.');
	const created: DbBackup = {
		id: nextId(state.dbBackups.map((item) => item.id), 'mock-trove-backup'),
		name,
		description: typeof payload.description === 'string' ? payload.description : '',
		status: 'NEW',
		instance_id: instance.id,
		size: 0,
		created_at: CREATED_AT,
		datastore: { ...instance.datastore },
	};
	state.dbBackups.push(created);
	return structuredClone(created);
}

export function mockDatabaseBackups(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();

	if (method === 'GET' && path === '/api/v1/database-instances/backups') return listBackups();
	const backupId = path.match(/^\/api\/v1\/database-instances\/backups\/([^/]+)$/)?.[1];
	if (method === 'DELETE' && backupId) {
		const id = decodeURIComponent(backupId);
		const backup = state.dbBackups.find((item) => item.id === id);
		if (!backup) throw new ApiError(404, 'Backup not found.');
		// Trove rejects deleting an in-progress backup; the backend reports that as a generic 500.
		if (!SETTLED[backup.status]) throw new ApiError(500, 'Backup deletion failed.');
		state.dbBackups = state.dbBackups.filter((item) => item.id !== id);
		return {};
	}

	const detail = path.match(/^\/api\/v1\/database-instances\/([^/]+)(?:\/(databases|users|backups|auto-backup))?$/);
	if (!detail) return undefined;
	const instanceId = decodeURIComponent(detail[1]);
	const child = detail[2];
	if (method === 'GET' && !child) return structuredClone(ownedInstance(instanceId));
	if (method === 'GET' && (child === 'databases' || child === 'users')) {
		ownedInstance(instanceId);
		return [];
	}
	if (method === 'GET' && child === 'backups') {
		ownedInstance(instanceId);
		return listBackups(instanceId);
	}
	if (method === 'POST' && child === 'backups') return createBackup(instanceId, body);
	if (method === 'GET' && child === 'auto-backup') {
		ownedInstance(instanceId);
		throw new ApiError(404, 'No automatic backup schedule is configured.');
	}
	return undefined;
}
