import { ApiError } from '$lib/api/errors';
import type { Project } from '$lib/types/project';
import type { Flavor } from '$lib/types/flavor';
import type { AdminNetwork, AdminRouter } from '$lib/types/networks';
import type { TopologyRouter } from '$lib/types/topology';
import type { MockupProfileId } from './contracts';
import { getMockupState } from './state';

const DOMAIN_ID = 'mock-domain';
const CREATED_AT = '2026-11-08T00:00:00Z';
const PROJECTS = '/api/v1/admin/projects';
const FLAVORS = '/api/v1/admin/flavors';

// Explicit synthetic admin state for the projects, flavors, networks and routers administration
// pages: list, create, deletion check and delete. Projects reuse the shared tutorial project list;
// routers and networks reuse state.topology so the admin topology stays consistent.
// Admin profile only; returns undefined for every path this module does not own.
export function mockAdminResources(method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile !== 'admin') return undefined;
	if (path === PROJECTS || path.startsWith(`${PROJECTS}/`)) return mockProjects(method, path, params, body);
	if (path === FLAVORS || /^\/api\/v1\/admin\/flavors\/[^/]+$/.test(path)) return mockFlavors(method, path, body);
	if (path === '/api/v1/admin/all-networks' && method === 'GET') return listNetworks(params);
	if (path === '/api/v1/admin/networks' || /^\/api\/v1\/admin\/networks\/[^/]+$/.test(path)) return mockNetworks(method, path, body);
	if (path === '/api/v1/admin/all-routers' && method === 'GET') return listRouters(params);
	if (path === '/api/v1/admin/routers' || /^\/api\/v1\/admin\/routers\/[^/]+$/.test(path)) return mockRouters(method, path, body);
	return undefined;
}

function requireDomain(params: URLSearchParams): void {
	const domain = params.get('domain_id');
	if (!domain) throw new ApiError(422, 'Select a domain');
	if (domain !== DOMAIN_ID) throw new ApiError(404, 'Domain not found');
}

function projectView(project: { id: string; name: string; description?: string; enabled?: boolean }): Project {
	return { id: project.id, name: project.name, description: project.description ?? '', enabled: project.enabled ?? true, domain_id: DOMAIN_ID, created_at: CREATED_AT };
}

function mockProjects(method: string, path: string, params: URLSearchParams, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === PROJECTS && method === 'GET') {
		requireDomain(params);
		const search = (params.get('search') ?? '').trim().toLowerCase();
		const enabled = params.get('enabled');
		const all = state.projects.map(projectView)
			.filter((item) => !search || item.name.toLowerCase().includes(search))
			.filter((item) => enabled === null || String(item.enabled) === enabled);
		const limit = Math.max(1, Number(params.get('limit')) || 20);
		const marker = params.get('marker');
		const start = marker ? all.findIndex((item) => item.id === marker) + 1 : 0;
		const items = all.slice(start, start + limit);
		return { items, next_marker: start + limit < all.length ? items[items.length - 1].id : null, count: items.length, total: all.length };
	}
	if (path === PROJECTS && method === 'POST') {
		requireDomain(params);
		const payload = (body ?? {}) as { name?: unknown; description?: unknown; enabled?: unknown; domain_id?: unknown };
		const name = typeof payload.name === 'string' ? payload.name.trim() : '';
		const description = typeof payload.description === 'string' ? payload.description : '';
		if (payload.domain_id !== DOMAIN_ID) throw new ApiError(422, 'domain_id must match the selected domain.');
		if (!name || name.length > 64) throw new ApiError(400, 'Project name must be 1-64 characters.');
		if (name.toLowerCase() === 'default') throw new ApiError(409, 'Default is reserved for the domain authority project');
		if (state.projects.some((item) => item.name.toLowerCase() === name.toLowerCase())) throw new ApiError(409, 'Project name already exists in this domain.');
		// Keystone names are unique per domain, so the synthetic ID is unique too.
		const id = `mock-admin-project-${name}`;
		state.projects.push({ id, name, description, domain_name: 'Demo', last_accessed_at: null });
		return projectView({ id, name, description, enabled: payload.enabled !== false });
	}
	const check = path.match(/^\/api\/v1\/admin\/projects\/([^/]+)\/deletion-check$/);
	if (check && method === 'GET') {
		requireDomain(params);
		return deletionCheck(decodeURIComponent(check[1]));
	}
	const item = path.match(/^\/api\/v1\/admin\/projects\/([^/]+)$/);
	if (item && method === 'DELETE') {
		requireDomain(params);
		const id = decodeURIComponent(item[1]);
		const report = deletionCheck(id);
		if (!report.can_delete) throw new ApiError(409, JSON.stringify({ detail: { code: 'project_has_resources', check: report } }));
		state.projects = state.projects.filter((entry) => entry.id !== id);
		return {};
	}
	return undefined;
}

// Admin inventory decides emptiness: instances and volumes owned by the project, and the
// project the synthetic admin token is scoped to is never empty.
function deletionCheck(id: string) {
	const state = getMockupState();
	if (!state.projects.some((item) => item.id === id)) throw new ApiError(404, 'Project not found.');
	const row = (kind: string, service: string, rows: { id: string; name: string }[]) => ({
		kind, service, status: 'ok', count: rows.length, samples: rows.slice(0, 5).map(({ id: sample, name }) => ({ id: sample, name })), reason: null,
	});
	const instances = state.admin.instances.filter((entry) => entry.project_id === id).map(({ id: sample, name }) => ({ id: sample, name }));
	if (id === state.selectedProjectId) instances.push(...state.instances.filter((entry) => !instances.some((known) => known.id === entry.id)).map(({ id: sample, name }) => ({ id: sample, name })));
	const resources = [
		row('instances', 'compute', instances),
		row('volumes', 'volume', state.admin.volumes.filter((entry) => entry.project_id === id).map(({ id: sample, name }) => ({ id: sample, name }))),
		row('routers', 'network', state.topology.routers.filter((entry) => entry.project_id === id).map(({ id: sample, name }) => ({ id: sample, name }))),
		row('child_projects', 'identity', []),
	];
	return { project_id: id, checked_at: CREATED_AT, can_delete: resources.every((entry) => entry.count === 0), resources };
}

function mockFlavors(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === FLAVORS && method === 'GET') return { items: state.adminFlavors, count: state.adminFlavors.length, next_marker: null };
	if (path === FLAVORS && method === 'POST') {
		const payload = (body ?? {}) as Record<string, unknown>;
		const name = typeof payload.name === 'string' ? payload.name.trim() : '';
		const integer = (value: unknown, min: number) => typeof value === 'number' && Number.isInteger(value) && value >= min;
		// The backend reports every Nova refusal as one generic 400.
		if (!name || name.length > 255 || state.adminFlavors.some((item) => item.name === name)
			|| !integer(payload.vcpus, 1) || !integer(payload.ram, 1) || !integer(payload.disk, 0)) {
			throw new ApiError(400, 'Flavor creation failed.');
		}
		let n = state.adminFlavors.length + 1;
		while (state.adminFlavors.some((item) => item.id === `mock-flavor-${n}`)) n += 1;
		const created: Flavor = {
			id: `mock-flavor-${n}`, name, vcpus: payload.vcpus as number, ram: payload.ram as number, disk: payload.disk as number,
			is_public: payload.is_public !== false, description: typeof payload.description === 'string' ? payload.description : null,
			extra_specs: {}, is_gpu: false, gpu_count: 0, gpu_primary_aliases: [], frontend_visible: true,
		};
		state.adminFlavors.push(created);
		return created;
	}
	const item = path.match(/^\/api\/v1\/admin\/flavors\/([^/]+)$/);
	if (item && method === 'DELETE') {
		const id = decodeURIComponent(item[1]);
		const flavor = state.adminFlavors.find((entry) => entry.id === id);
		if (flavor?.extra_specs['afterglow:managed_by']) throw new ApiError(409, 'Managed flavors are changed only by domain compute automation.');
		// Nova deletion ignores a missing flavor.
		state.adminFlavors = state.adminFlavors.filter((entry) => entry.id !== id);
		return {};
	}
	return undefined;
}

function scopedProject(params: URLSearchParams): string | null {
	const domain = params.get('domain_id');
	if (domain && domain !== DOMAIN_ID) throw new ApiError(404, 'inventory_domain_not_found');
	return params.get('project_id');
}

function listNetworks(params: URLSearchParams): AdminNetwork[] {
	const state = getMockupState();
	const project = scopedProject(params);
	return state.topology.networks
		.filter((net) => !project || net.project_id === project)
		.map((net) => ({
			id: net.id, name: net.name, status: net.status, subnets: net.subnet_details.map((subnet) => subnet.id),
			is_external: net.is_external, is_shared: net.is_shared, project_id: net.project_id ?? null,
			project_name: state.projects.find((entry) => entry.id === net.project_id)?.name ?? '',
		}));
}

function mockNetworks(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	const topology = state.topology;
	if (path === '/api/v1/admin/networks' && method === 'POST') {
		const payload = (body ?? {}) as { name?: unknown; cidr?: unknown; is_external?: unknown; is_shared?: unknown; enable_dhcp?: unknown };
		const name = typeof payload.name === 'string' ? payload.name : '';
		const cidr = typeof payload.cidr === 'string' ? payload.cidr.trim() : '';
		const prefix = cidr.match(/^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}\/(\d{1,2})$/);
		// The backend reports every Neutron refusal as one generic 400.
		if (!name || (cidr && (!prefix || Number(prefix[2]) > 30))) throw new ApiError(400, 'Network creation failed.');
		let n = topology.networks.length + 1;
		while (topology.networks.some((net) => net.id === `mock-admin-net-${n}`)) n += 1;
		const id = `mock-admin-net-${n}`;
		const subnets = prefix
			? [{ id: `${id}-subnet`, name: `${name}-subnet`, cidr, ip_version: 4, gateway_ip: `${prefix[1]}.1`, dhcp_enabled: payload.enable_dhcp !== false }]
			: [];
		const isExternal = payload.is_external === true;
		const isShared = payload.is_shared === true;
		// The admin connection creates the network in the project its token is scoped to.
		topology.networks.push({ id, name, status: 'ACTIVE', is_external: isExternal, is_shared: isShared, project_id: state.selectedProjectId, subnet_details: subnets });
		return { id, name, status: 'ACTIVE', subnets: subnets.map((subnet) => subnet.id), is_external: isExternal, is_shared: isShared, project_id: state.selectedProjectId };
	}
	const item = path.match(/^\/api\/v1\/admin\/networks\/([^/]+)$/);
	if (item && method === 'DELETE') {
		const id = decodeURIComponent(item[1]);
		const network = topology.networks.find((net) => net.id === id);
		// Neutron deletion ignores a missing network.
		if (!network) return {};
		const subnetIds = new Set(network.subnet_details.map((subnet) => subnet.id));
		const inUse = topology.instances.some((instance) => instance.ip_addresses.some((ip) => ip.network_id === id))
			|| topology.routers.some((router) => router.external_gateway_network_id === id || router.connected_subnet_ids.some((subnetId) => subnetIds.has(subnetId)));
		if (inUse) throw new ApiError(400, 'Network deletion failed.');
		topology.networks = topology.networks.filter((net) => net.id !== id);
		return {};
	}
	return undefined;
}

function routerView(router: TopologyRouter): AdminRouter {
	return {
		id: router.id, name: router.name, status: router.status, external_gateway_network_id: router.external_gateway_network_id,
		connected_subnet_ids: router.connected_subnet_ids, project_id: router.project_id,
	};
}

function listRouters(params: URLSearchParams): AdminRouter[] {
	const project = scopedProject(params);
	return getMockupState().topology.routers.filter((router) => !project || router.project_id === project).map(routerView);
}

function mockRouters(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	const topology = state.topology;
	if (path === '/api/v1/admin/routers' && method === 'POST') {
		const payload = (body ?? {}) as { name?: unknown; external_network_id?: unknown };
		if (typeof payload.name !== 'string') throw new ApiError(422, 'name is required.');
		const externalId = payload.external_network_id ?? null;
		if (externalId !== null && typeof externalId !== 'string') throw new ApiError(422, 'external_network_id must be a string.');
		const external = externalId ? topology.networks.find((net) => net.id === externalId && net.is_external) : null;
		const prefix = external?.subnet_details[0]?.cidr.match(/^(\d+\.\d+\.\d+)\.\d+\/\d+$/)?.[1];
		const used = new Set(topology.routers.flatMap((router) => router.external_gateway_ips));
		let host = 200;
		while (prefix && host < 255 && used.has(`${prefix}.${host}`)) host += 1;
		const gatewayIp = prefix && host < 255 ? `${prefix}.${host}` : null;
		if (externalId && (!external || !gatewayIp)) throw new ApiError(400, 'Router creation failed.');
		let n = topology.routers.length + 1;
		while (topology.routers.some((router) => router.id === `mock-admin-router-${n}`)) n += 1;
		// The admin connection creates the router in the project its token is scoped to.
		const created: TopologyRouter = {
			id: `mock-admin-router-${n}`, name: payload.name, status: 'ACTIVE', external_gateway_network_id: external?.id ?? null,
			external_gateway_ips: gatewayIp ? [gatewayIp] : [], interface_ips: [], is_distributed: false, is_ha: false,
			connected_subnet_ids: [], dvr_subnet_ids: [], project_id: state.selectedProjectId, enable_snat: Boolean(external), routes: [],
		};
		topology.routers.push(created);
		const { connected_subnet_ids: _subnets, ...response } = routerView(created);
		return response;
	}
	const item = path.match(/^\/api\/v1\/admin\/routers\/([^/]+)$/);
	if (item && method === 'DELETE') {
		const id = decodeURIComponent(item[1]);
		const router = topology.routers.find((entry) => entry.id === id);
		if (!router) throw new ApiError(404, 'Router deletion failed.');
		// Neutron refuses to delete a router that still has subnet interfaces (RouterInUse).
		if (router.connected_subnet_ids.length > 0) throw new ApiError(409, 'Router deletion failed.');
		topology.routers = topology.routers.filter((entry) => entry.id !== id);
		return {};
	}
	return undefined;
}
