import { ApiError } from '$lib/api/errors';
import type { TopologyLoadBalancer, TopologyRouter } from '$lib/types/topology';
import { getMockupState } from './state';

// Explicit synthetic tutorial state for Octavia load balancers and Neutron routers.
// Both live in state.topology so the topology canvas, network detail and router detail stay consistent.
// Like the native APIs, duplicate names are allowed; identity is the generated id.
// Returns undefined for paths this module does not own so transport can keep its own dispatch.

const LB_NOT_FOUND = 'Load balancer not found.';
const ROUTER_NOT_FOUND = 'Router not found.';

function nextId(existing: { id: string }[], prefix: string): string {
	let n = existing.length + 1;
	while (existing.some((item) => item.id === `${prefix}-${n}`)) n += 1;
	return `${prefix}-${n}`;
}

function nextHost(cidr: string, used: Set<string>, start: number): string | null {
	const prefix = cidr.match(/^(\d+\.\d+\.\d+)\.\d+\/\d+$/)?.[1];
	if (!prefix) return null;
	for (let host = start; host < 255; host += 1) {
		const address = `${prefix}.${host}`;
		if (!used.has(address)) return address;
	}
	return null;
}

function loadBalancers(): TopologyLoadBalancer[] {
	const topology = getMockupState().topology;
	topology.load_balancers ??= [];
	return topology.load_balancers;
}

function lbView(lb: TopologyLoadBalancer & { description?: string }) {
	return {
		id: lb.id,
		name: lb.name,
		description: lb.description ?? '',
		status: lb.provisioning_status,
		provisioning_status: lb.provisioning_status,
		operating_status: lb.operating_status,
		vip_address: lb.vip_address,
		vip_subnet_id: lb.vip_subnet_id,
		vip_network_id: lb.vip_network_id,
		vip_port_id: lb.vip_port_id,
		project_id: lb.project_id,
		tags: [],
	};
}

function poolIds(lb: TopologyLoadBalancer): string[] {
	const ids = [...lb.listeners.map((listener) => listener.default_pool_id), ...lb.members.map((member) => member.pool_id)];
	return [...new Set(ids.filter((id): id is string => Boolean(id)))];
}

// Octavia finishes provisioning asynchronously; the first read after create observes ACTIVE.
function settle(items: TopologyLoadBalancer[]): void {
	for (const lb of items) {
		if (lb.provisioning_status === 'PENDING_CREATE') {
			lb.provisioning_status = 'ACTIVE';
			lb.operating_status = 'ONLINE';
		}
	}
}

function ownedLoadBalancer(id: string): TopologyLoadBalancer {
	const state = getMockupState();
	const lb = loadBalancers().find((item) => item.id === id);
	if (!lb || lb.project_id !== state.selectedProjectId) throw new ApiError(404, LB_NOT_FOUND);
	return lb;
}

function routerView(router: TopologyRouter) {
	return {
		id: router.id,
		name: router.name,
		status: router.status,
		project_id: router.project_id,
		external_gateway_network_id: router.external_gateway_network_id,
		connected_subnet_ids: router.connected_subnet_ids,
	};
}

function mockLoadBalancers(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/loadbalancers' && method === 'GET') {
		const items = loadBalancers().filter((lb) => lb.project_id === state.selectedProjectId);
		settle(items);
		return items.map(lbView);
	}
	if (path === '/api/v1/loadbalancers' && method === 'POST') {
		const payload = (body ?? {}) as { name?: unknown; vip_subnet_id?: unknown; description?: unknown };
		if (typeof payload.name !== 'string' || typeof payload.vip_subnet_id !== 'string') {
			throw new ApiError(422, 'name and vip_subnet_id are required.');
		}
		const subnetId = payload.vip_subnet_id;
		const network = state.topology.networks.find((item) => !item.is_external
			&& (item.project_id === state.selectedProjectId || item.is_shared)
			&& item.subnet_details.some((subnet) => subnet.id === subnetId));
		const subnet = network?.subnet_details.find((item) => item.id === subnetId);
		const items = loadBalancers();
		const vip = subnet?.cidr ? nextHost(subnet.cidr, new Set(items.map((lb) => lb.vip_address ?? '')), 80) : null;
		if (!network || !subnet || !vip) throw new ApiError(500, 'Load balancer creation failed.');
		const id = nextId(items, 'mock-lb');
		const created: TopologyLoadBalancer & { description: string } = {
			id,
			name: payload.name,
			description: typeof payload.description === 'string' ? payload.description : '',
			vip_address: vip,
			vip_port_id: `${id}-vip-port`,
			vip_subnet_id: subnet.id,
			vip_network_id: network.id,
			provisioning_status: 'PENDING_CREATE',
			operating_status: 'OFFLINE',
			project_id: state.selectedProjectId,
			listeners: [],
			members: [],
		};
		items.push(created);
		return lbView(created);
	}
	const child = path.match(/^\/api\/v1\/loadbalancers\/([^/]+)\/(listeners|pools)$/);
	if (child && method === 'GET') {
		const lb = ownedLoadBalancer(decodeURIComponent(child[1]));
		if (child[2] === 'listeners') {
			return lb.listeners.map((listener) => ({ id: listener.id, name: listener.name, protocol: listener.protocol, protocol_port: listener.protocol_port, status: 'ACTIVE', default_pool_id: listener.default_pool_id }));
		}
		return poolIds(lb).map((id) => ({ id, name: id, protocol: lb.listeners.find((listener) => listener.default_pool_id === id)?.protocol ?? 'TCP', lb_algorithm: 'ROUND_ROBIN', status: 'ACTIVE' }));
	}
	const members = path.match(/^\/api\/v1\/loadbalancers\/([^/]+)\/pools\/([^/]+)\/members$/);
	if (members && method === 'GET') {
		const lb = ownedLoadBalancer(decodeURIComponent(members[1]));
		const poolId = decodeURIComponent(members[2]);
		if (!poolIds(lb).includes(poolId)) throw new ApiError(404, 'Pool not found.');
		return lb.members.filter((member) => member.pool_id === poolId).map((member) => ({ id: member.id, address: member.address, protocol_port: member.protocol_port, weight: 1, status: member.status }));
	}
	const item = path.match(/^\/api\/v1\/loadbalancers\/([^/]+)$/);
	if (item && method === 'GET') {
		const lb = ownedLoadBalancer(decodeURIComponent(item[1]));
		settle([lb]);
		return lbView(lb);
	}
	if (item && method === 'DELETE') {
		const lb = ownedLoadBalancer(decodeURIComponent(item[1]));
		// Octavia keeps a load balancer immutable while it is still provisioning.
		if (lb.provisioning_status.startsWith('PENDING_')) throw new ApiError(500, 'Load balancer deletion failed.');
		const topology = state.topology;
		topology.load_balancers = loadBalancers().filter((entry) => entry.id !== lb.id);
		return {};
	}
	return undefined;
}

function mockRouters(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	const topology = state.topology;
	if (path === '/api/v1/routers' && method === 'GET') return topology.routers.map(routerView);
	if (path === '/api/v1/routers' && method === 'POST') {
		const payload = (body ?? {}) as { name?: unknown; external_network_id?: unknown };
		if (typeof payload.name !== 'string') throw new ApiError(422, 'name is required.');
		const externalId = payload.external_network_id ?? null;
		if (externalId !== null && typeof externalId !== 'string') throw new ApiError(422, 'external_network_id must be a string.');
		const external = externalId ? topology.networks.find((net) => net.id === externalId && net.is_external) : null;
		const externalSubnet = external?.subnet_details[0];
		const usedGatewayIps = new Set(topology.routers.flatMap((router) => router.external_gateway_ips));
		const gatewayIp = externalSubnet?.cidr ? nextHost(externalSubnet.cidr, usedGatewayIps, 200) : null;
		if (externalId && (!external || !gatewayIp)) throw new ApiError(500, 'Router creation failed.');
		const created: TopologyRouter = {
			id: nextId(topology.routers, 'mock-router'),
			name: payload.name,
			status: 'ACTIVE',
			external_gateway_network_id: external?.id ?? null,
			external_gateway_ips: gatewayIp ? [gatewayIp] : [],
			interface_ips: [],
			is_distributed: false,
			is_ha: false,
			connected_subnet_ids: [],
			dvr_subnet_ids: [],
			project_id: state.selectedProjectId,
			enable_snat: Boolean(external),
			routes: [],
		};
		topology.routers.push(created);
		return routerView(created);
	}
	const item = path.match(/^\/api\/v1\/routers\/([^/]+)$/);
	if (item && method === 'DELETE') {
		const id = decodeURIComponent(item[1]);
		const router = topology.routers.find((entry) => entry.id === id);
		if (!router || router.project_id !== state.selectedProjectId) throw new ApiError(404, ROUTER_NOT_FOUND);
		// Neutron refuses to delete a router that still has subnet interfaces (RouterInUse).
		if (router.connected_subnet_ids.length > 0) throw new ApiError(500, 'Router deletion failed.');
		topology.routers = topology.routers.filter((entry) => entry.id !== id);
		return {};
	}
	return undefined;
}

export function mockNetworkLbRouter(method: string, path: string, body: unknown): unknown | undefined {
	if (path === '/api/v1/loadbalancers' || path.startsWith('/api/v1/loadbalancers/')) return mockLoadBalancers(method, path, body);
	if (path === '/api/v1/routers' || path.startsWith('/api/v1/routers/')) return mockRouters(method, path, body);
	return undefined;
}
