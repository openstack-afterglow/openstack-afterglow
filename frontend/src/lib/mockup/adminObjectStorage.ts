import { ApiError } from '$lib/api/errors';
import type { SwiftContainer } from '$lib/types/common';
import { buildMockAuth } from './auth';
import type { MockupProfileId } from './contracts';
import { getMockupState } from './state';

const INVENTORY = '/api/v1/admin/object-storage';
const BUCKETS = '/api/v1/object-storage';

// Explicit synthetic admin state for the object storage administration page: inventory, create and soft delete.
// The inventory lists two Swift accounts: the sample tenant project (state.objectContainers/objectTrash, shared with
// the tenant bucket pages) and the administrator's own auth project (state.adminObjectContainers).
// The page creates and deletes only in the administrator's auth project, so only that account accepts mutations.
// Like the backend with include_deleted=true, soft-deleted buckets stay listed with is_deleted.
// Admin profile only; returns undefined for every path this module does not own.
export function mockAdminObjectStorage(method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId, requestProjectId?: string): unknown | undefined {
	if (profile !== 'admin') return undefined;
	const state = getMockupState();
	const admin = buildMockAuth('admin', '/admin');
	if (path === INVENTORY && method === 'GET') {
		const domain = params.get('domain_id');
		if (domain && domain !== 'mock-domain') throw new ApiError(404, 'inventory_domain_not_found');
		const tenant = { project_id: state.selectedProjectId, project_name: state.projects.find((item) => item.id === state.selectedProjectId)?.name ?? '' };
		const accounts: { project_id: string; items: SwiftContainer[] }[] = [
			{
				project_id: tenant.project_id,
				items: [
					...state.objectContainers.map((item) => ({ ...item, ...tenant })),
					...state.objectTrash.map((item) => ({ ...item, ...tenant, is_deleted: true })),
				],
			},
			{ project_id: admin.projectId!, items: state.adminObjectContainers.map((item) => ({ ...item })) },
		];
		const project = params.get('project_id');
		const scoped = accounts.filter((account) => !project || account.project_id === project);
		return { items: scoped.flatMap((account) => account.items), project_count: scoped.length, partial: false, unavailable_projects: [] };
	}
	const deleted = path.match(/^\/api\/v1\/object-storage\/([^/]+)$/);
	if (!((path === BUCKETS && method === 'POST') || (deleted && method === 'DELETE'))) return undefined;
	// Bucket mutations act in the project the request is scoped to (the token project when unscoped).
	if ((requestProjectId ?? admin.projectId) !== admin.projectId) throw new ApiError(404, 'Bucket not found.');
	const live = state.adminObjectContainers;
	if (method === 'POST') {
		const name = String((body as { name?: string } | null)?.name ?? '').trim();
		if (!name) throw new ApiError(422, 'Bucket name is required.');
		if (live.some((item) => item.name === name)) throw new ApiError(409, 'Bucket already exists.');
		const created: SwiftContainer = { name, count: 0, bytes: 0, project_id: admin.projectId!, project_name: admin.projectName! };
		live.push(created);
		return { name, count: 0, bytes: 0 };
	}
	const name = decodeURIComponent(deleted![1]);
	const item = live.find((entry) => entry.name === name && !entry.is_deleted);
	if (!item) throw new ApiError(404, 'Bucket not found.');
	item.is_deleted = true;
	item.deleted_at = Math.floor(Date.now() / 1000);
	return {};
}
