import { ApiError } from '$lib/api/errors';
import type { MockupProfileId } from './contracts';
import type { Project } from '$lib/types/project';
import { getMockupState } from './state';

const DOMAIN_ID = 'mock-domain';
const CREATED_AT = '2026-11-08T00:00:00Z';

// Explicit synthetic tutorial state for the domain project console: capability, list, create,
// deletion check and delete over the shared tutorial project list. Tutorial profile only;
// returns undefined for paths this module does not own.
export function mockIdentity(method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile !== 'on') return undefined;
	const state = getMockupState();
	if (path === '/api/v1/projects/capabilities' && method === 'GET') {
		if ((params.get('domain_id') ?? DOMAIN_ID) !== DOMAIN_ID) throw new ApiError(404, 'Domain not found');
		return { domain_id: DOMAIN_ID, domain_kind: 'organization', is_domain_manager: true, can_create_project: true };
	}
	if (path === '/api/v1/iam/projects' && method === 'GET') {
		const items: Project[] = state.projects.map(({ id, name, description }) => ({ id, name, description: description ?? '', enabled: true, domain_id: DOMAIN_ID, created_at: CREATED_AT }));
		return { items };
	}
	if (path === '/api/v1/projects' && method === 'POST') {
		const payload = (body ?? {}) as { name?: unknown; description?: unknown; domain_id?: unknown };
		const name = typeof payload.name === 'string' ? payload.name.trim() : '';
		const description = typeof payload.description === 'string' ? payload.description : '';
		if ((payload.domain_id ?? DOMAIN_ID) !== DOMAIN_ID) throw new ApiError(403, 'Domain project creation capability required');
		if (!name || name.length > 255) throw new ApiError(422, 'Project name is required.');
		if (name.toLowerCase() === 'default') throw new ApiError(409, 'Default is reserved for the domain authority project');
		if (state.projects.some((item) => item.name.toLowerCase() === name.toLowerCase())) throw new ApiError(409, 'Project name already exists in this domain.');
		// Names are unique per domain, so the synthetic ID is unique too.
		const id = `mock-iam-project-${name}`;
		state.projects.push({ id, name, description, domain_name: 'Demo', last_accessed_at: null });
		return { id, name, description, enabled: true, domain_id: DOMAIN_ID, created_at: CREATED_AT } satisfies Project;
	}
	const check = path.match(/^\/api\/v1\/projects\/([^/]+)\/deletion-check$/);
	if (check && method === 'GET') return deletionCheck(decodeURIComponent(check[1]));
	const remove = path.match(/^\/api\/v1\/projects\/([^/]+)$/);
	if (remove && method === 'DELETE') {
		const id = decodeURIComponent(remove[1]);
		if (!deletionCheck(id).can_delete) throw new ApiError(409, 'Project still owns resources or child projects');
		state.projects = state.projects.filter((item) => item.id !== id);
		return {};
	}
	return undefined;
}

// Synthetic inventory lives only in the selected project, matching the tutorial resource fixtures.
function deletionCheck(id: string) {
	const state = getMockupState();
	if (!state.projects.some((item) => item.id === id)) throw new ApiError(404, 'Project not found.');
	const selected = id === state.selectedProjectId;
	const row = (kind: string, service: string, rows: { id: string; name: string }[]) => ({
		kind, service, status: 'ok', count: rows.length, samples: rows.slice(0, 5).map(({ id: sample, name }) => ({ id: sample, name })), reason: null,
	});
	const resources = [
		row('instances', 'compute', selected ? state.instances : []),
		row('volumes', 'volume', selected ? state.volumes : []),
		row('child_projects', 'identity', []),
	];
	return { project_id: id, checked_at: CREATED_AT, can_delete: resources.every((item) => item.count === 0), resources };
}
