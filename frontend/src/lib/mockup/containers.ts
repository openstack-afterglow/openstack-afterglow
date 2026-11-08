import { ApiError } from '$lib/api/errors';
import type { ContainerListResponse, ZunContainer } from '$lib/types/zunContainer';
import { getMockupState } from './state';

// Explicit synthetic tutorial state: container create, list, start/stop and delete.
// Returns undefined for paths this module does not own so transport can keep its own dispatch.
export function mockContainers(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/containers' && method === 'GET') {
		const response: ContainerListResponse = { items: state.containers, service_available: true, message: '' };
		return response;
	}
	if (path === '/api/v1/containers' && method === 'POST') {
		const payload = (body ?? {}) as { name?: string; image?: string; command?: string | null; memory?: string | null; cpu?: number | null };
		const name = String(payload.name ?? '').trim();
		const image = String(payload.image ?? '').trim();
		if (!name || !image) throw new ApiError(422, 'Container name and image are required.');
		if (state.containers.some((item) => item.name === name)) throw new ApiError(409, 'Container name already exists.');
		const created: ZunContainer = {
			uuid: `mock-container-${state.containers.length + 1}-${name}`,
			name,
			status: 'Created',
			status_reason: null,
			image,
			command: payload.command ?? null,
			cpu: payload.cpu ?? null,
			memory: payload.memory ?? null,
			created_at: '2026-11-08T00:00:00Z',
		};
		state.containers.push(created);
		return created;
	}
	const action = path.match(/^\/api\/v1\/containers\/([^/]+)\/(start|stop)$/);
	if (action && method === 'POST') {
		const item = state.containers.find((entry) => entry.uuid === decodeURIComponent(action[1]));
		if (!item) throw new ApiError(404, 'Container not found.');
		item.status = action[2] === 'start' ? 'Running' : 'Stopped';
		return {};
	}
	const remove = path.match(/^\/api\/v1\/containers\/([^/]+)$/);
	if (remove && method === 'DELETE') {
		const uuid = decodeURIComponent(remove[1]);
		const item = state.containers.find((entry) => entry.uuid === uuid);
		if (!item) throw new ApiError(404, 'Container not found.');
		if (item.status === 'Running') throw new ApiError(409, 'Stop the container before deleting it.');
		state.containers = state.containers.filter((entry) => entry.uuid !== uuid);
		return {};
	}
	return undefined;
}
