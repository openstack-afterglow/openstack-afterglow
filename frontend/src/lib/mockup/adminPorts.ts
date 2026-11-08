import { ApiError } from '$lib/api/errors';
import type { PortInfo } from '$lib/types/networks';
import type { TopologyNetwork } from '$lib/types/topology';
import type { MockupProfileId } from './contracts';
import { getMockupState } from './state';

const LIST = '/api/v1/admin/all-ports';
const CREATE = '/api/v1/admin/ports';

type MockPort = PortInfo & { device_id: string; mac_address: string; network_id: string };

// Explicit synthetic admin state for the port administration page: list, create and delete.
// Device-owned ports are derived from state.topology (instance NICs, router interfaces and gateways)
// so they match the topology views; ports created here live in state.adminPorts.
// Admin profile only; returns undefined for every path this module does not own.
export function mockAdminPorts(method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile !== 'admin') return undefined;
	if (path === LIST && method === 'GET') return listPorts(params);
	if (path === CREATE && method === 'POST') return createPort(body);
	const item = path.match(/^\/api\/v1\/admin\/ports\/([^/]+)$/);
	if (item && method === 'DELETE') return deletePort(decodeURIComponent(item[1]));
	return undefined;
}

function derivedPorts(): MockPort[] {
	const { topology } = getMockupState();
	const ports: MockPort[] = [];
	for (const instance of topology.instances) {
		for (const nic of instance.ip_addresses) {
			if (nic.type !== 'fixed' || !nic.port_id || !nic.network_id) continue;
			ports.push({
				id: nic.port_id, name: '', status: instance.status === 'ACTIVE' ? 'ACTIVE' : 'DOWN', network_id: nic.network_id,
				device_owner: 'compute:nova', device_id: instance.id, mac_address: nic.mac_addr ?? '',
				fixed_ips: [{ ip_address: nic.addr }], project_id: instance.project_id ?? null,
			});
		}
	}
	for (const router of topology.routers) {
		router.interface_ips.forEach((iface, index) => {
			ports.push({
				id: `mock-port-${router.id}-if-${index + 1}`, name: '', status: 'ACTIVE',
				network_id: topology.networks.find((net) => net.subnet_details.some((subnet) => subnet.id === iface.subnet_id))?.id ?? '',
				device_owner: router.is_distributed ? 'network:router_interface_distributed' : 'network:router_interface', device_id: router.id,
				mac_address: '', fixed_ips: [{ ip_address: iface.ip_address }], project_id: router.project_id,
			});
		});
		if (router.external_gateway_network_id && router.external_gateway_ips.length > 0) {
			ports.push({
				id: `mock-port-${router.id}-gw`, name: '', status: 'ACTIVE', network_id: router.external_gateway_network_id,
				device_owner: 'network:router_gateway', device_id: router.id, mac_address: '',
				fixed_ips: router.external_gateway_ips.map((ip_address) => ({ ip_address })), project_id: null,
			});
		}
	}
	return ports;
}

function listPorts(params: URLSearchParams) {
	const domain = params.get('domain_id');
	if (domain && domain !== 'mock-domain') throw new ApiError(404, 'inventory_domain_not_found');
	const project = params.get('project_id');
	const scoped = [...derivedPorts(), ...(getMockupState().adminPorts as MockPort[])].filter((port) => !project || port.project_id === project);
	const limit = Math.max(1, Math.min(100, Number(params.get('limit')) || 20));
	const marker = params.get('marker');
	const start = marker ? scoped.findIndex((port) => port.id === marker) + 1 : 0;
	const items = scoped.slice(start, start + limit);
	return { items, next_marker: items.length === limit ? items[items.length - 1].id : null, count: items.length };
}

function ipv4ToInt(address: string): number | null {
	const parts = address.split('.');
	if (parts.length !== 4 || parts.some((part) => !/^\d{1,3}$/.test(part) || Number(part) > 255)) return null;
	return parts.reduce((value, part) => value * 256 + Number(part), 0);
}

function intToIpv4(value: number): string {
	return [24, 16, 8, 0].map((shift) => Math.floor(value / 2 ** shift) % 256).join('.');
}

function usedAddresses(): Set<string> {
	const { topology } = getMockupState();
	const used = new Set<string>();
	for (const instance of topology.instances) for (const nic of instance.ip_addresses) used.add(nic.addr);
	for (const router of topology.routers) {
		for (const iface of router.interface_ips) used.add(iface.ip_address);
		for (const ip of router.external_gateway_ips) used.add(ip);
	}
	for (const fip of topology.floating_ips) used.add(fip.floating_ip_address);
	for (const lb of topology.load_balancers ?? []) if (lb.vip_address) used.add(lb.vip_address);
	for (const port of getMockupState().adminPorts) for (const ip of port.fixed_ips) used.add(ip.ip_address);
	for (const network of topology.networks) for (const subnet of network.subnet_details) if (subnet.gateway_ip) used.add(subnet.gateway_ip);
	return used;
}

// Usable host range of an IPv4 subnet (network and broadcast addresses excluded).
function hostRange(cidr: string): [number, number] | null {
	const [address, prefixText] = cidr.split('/');
	const base = ipv4ToInt(address);
	const prefix = Number(prefixText);
	if (base === null || !Number.isInteger(prefix) || prefix < 8 || prefix > 30) return null;
	const size = 2 ** (32 - prefix);
	const network = base - (base % size);
	return [network + 1, network + size - 2];
}

function allocateAddress(network: TopologyNetwork, requested: string | null): string {
	const used = usedAddresses();
	const ranges = network.subnet_details.filter((subnet) => subnet.ip_version === 4).map((subnet) => hostRange(subnet.cidr)).filter((range) => range !== null);
	if (requested) {
		const value = ipv4ToInt(requested);
		// Neutron refuses an address outside the network's subnets or one already in use.
		if (value === null || used.has(requested) || !ranges.some(([first, last]) => value >= first && value <= last)) throw new ApiError(400, 'Port creation failed.');
		return requested;
	}
	for (const [first, last] of ranges) {
		// Leave the low addresses for gateways and DHCP like a default allocation pool.
		for (let value = Math.min(first + 99, last); value <= last; value += 1) {
			const candidate = intToIpv4(value);
			if (!used.has(candidate)) return candidate;
		}
	}
	throw new ApiError(400, 'Port creation failed.');
}

function createPort(body: unknown): MockPort {
	const state = getMockupState();
	const payload = (body ?? {}) as { network_id?: unknown; name?: unknown; project_id?: unknown; fixed_ip?: unknown };
	if (typeof payload.network_id !== 'string') throw new ApiError(422, 'network_id is required.');
	const network = state.topology.networks.find((item) => item.id === payload.network_id);
	// The backend reports every Neutron refusal as one generic 400.
	if (!network) throw new ApiError(400, 'Port creation failed.');
	const fixedIp = typeof payload.fixed_ip === 'string' && payload.fixed_ip ? payload.fixed_ip : null;
	const address = allocateAddress(network, fixedIp);
	let n = state.adminPorts.length + 1;
	while (state.adminPorts.some((port) => port.id === `mock-admin-port-${n}`)) n += 1;
	const created: MockPort = {
		id: `mock-admin-port-${n}`,
		name: typeof payload.name === 'string' ? payload.name : '',
		status: 'DOWN',
		network_id: network.id,
		device_owner: '',
		device_id: '',
		mac_address: `fa:16:3e:00:0a:${n.toString(16).padStart(2, '0').slice(-2)}`,
		fixed_ips: [{ ip_address: address }],
		// Without an explicit owner the admin connection creates the port in its token's project.
		project_id: typeof payload.project_id === 'string' && payload.project_id ? payload.project_id : state.selectedProjectId,
	};
	state.adminPorts.push(created);
	return structuredClone(created);
}

function deletePort(id: string): Record<string, never> {
	const state = getMockupState();
	// Device-owned ports are views of instances and routers; this fixture cannot detach them.
	if (derivedPorts().some((port) => port.id === id)) throw new ApiError(400, 'Port deletion failed.');
	// Neutron deletion ignores a missing port.
	state.adminPorts = state.adminPorts.filter((port) => port.id !== id);
	return {};
}
