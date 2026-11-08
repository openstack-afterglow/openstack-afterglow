import { ApiError } from '$lib/api/errors';
import type { SwiftContainer } from '$lib/types/objectStorage';
import { getMockupState } from './state';

// Explicit synthetic tutorial state: bucket create, soft delete to trash, restore and purge.
// Returns undefined for paths this module does not own so transport can keep its own dispatch.
export function mockObjectStorage(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/object-storage/account' && method === 'GET') {
		const bytes = state.objectContainers.reduce((sum, item) => sum + item.bytes, 0);
		const objects = state.objectContainers.reduce((sum, item) => sum + item.count, 0);
		return { container_count: state.objectContainers.length, object_count: objects, bytes_used: bytes };
	}
	if (path === '/api/v1/object-storage' && method === 'GET') return state.objectContainers;
	if (path === '/api/v1/object-storage' && method === 'POST') {
		const name = String((body as { name?: string } | null)?.name ?? '').trim();
		if (!name) throw new ApiError(422, 'Bucket name is required.');
		if (state.objectContainers.some((item) => item.name === name) || state.objectTrash.some((item) => item.name === name)) {
			throw new ApiError(409, 'Bucket already exists.');
		}
		const created: SwiftContainer = { name, count: 0, bytes: 0 };
		state.objectContainers.push(created);
		return created;
	}
	if (path === '/api/v1/object-storage/trash/containers' && method === 'GET') return state.objectTrash;

	const restore = path.match(/^\/api\/v1\/object-storage\/trash\/containers\/([^/]+)\/restore$/);
	if (restore && method === 'POST') {
		const name = decodeURIComponent(restore[1]);
		const item = state.objectTrash.find((entry) => entry.name === name);
		if (!item) throw new ApiError(404, 'Bucket is not in trash.');
		state.objectTrash = state.objectTrash.filter((entry) => entry.name !== name);
		state.objectContainers.push(item);
		return {};
	}

	const trashPurge = path.match(/^\/api\/v1\/object-storage\/trash\/containers\/([^/]+)$/);
	if (trashPurge && method === 'DELETE') {
		const name = decodeURIComponent(trashPurge[1]);
		state.objectTrash = state.objectTrash.filter((entry) => entry.name !== name);
		return {};
	}

	const bucket = path.match(/^\/api\/v1\/object-storage\/([^/]+)$/);
	if (bucket && method === 'DELETE') {
		const name = decodeURIComponent(bucket[1]);
		const item = state.objectContainers.find((entry) => entry.name === name);
		if (!item) throw new ApiError(404, 'Bucket not found.');
		state.objectContainers = state.objectContainers.filter((entry) => entry.name !== name);
		state.objectTrash.push(item);
		return {};
	}
	return undefined;
}
