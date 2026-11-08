import { ApiError } from '$lib/api/errors';
import type { FloatingIp } from '$lib/types/networks';
import type { MockupProfileId } from './contracts';
import { nextFloatingAddress } from './computeNetwork';
import { getMockupState } from './state';

const LIST = '/api/v1/admin/all-floating-ips';
const CREATE = '/api/v1/admin/floating-ips';

// Explicit synthetic admin state for the floating IP administration page: list, create and delete.
// Floating IPs live in state.topology.floating_ips so the project pages and topology stay consistent.
// Admin profile only; returns undefined for every path this module does not own.
export function mockAdminFloatingIps(method: string, path: string, params: URLSearchParams, body: unknown, profile: MockupProfileId): unknown | undefined {
	if (profile !== 'admin') return undefined;
	const state = getMockupState();
	if (path === LIST && method === 'GET') {
		const domain = params.get('domain_id');
		if (domain && domain !== 'mock-domain') throw new ApiError(404, 'inventory_domain_not_found');
		const project = params.get('project_id');
		return state.topology.floating_ips.filter((fip) => !project || fip.project_id === project);
	}
	if (path === CREATE && method === 'POST') {
		const networkId = (body as { floating_network_id?: unknown } | null)?.floating_network_id;
		if (typeof networkId !== 'string') throw new ApiError(422, 'floating_network_id is required.');
		const network = state.topology.networks.find((item) => item.id === networkId && item.is_external);
		// The backend reports every Neutron refusal as one generic 400.
		if (!network) throw new ApiError(400, 'Floating IP creation failed.');
		let address: string;
		try { address = nextFloatingAddress(network.id); } catch { throw new ApiError(400, 'Floating IP creation failed.'); }
		// The admin connection allocates the address in the project its token is scoped to.
		const created: FloatingIp = {
			id: `mock-admin-fip-${address.replace(/\./g, '-')}`, floating_ip_address: address, status: 'DOWN', fixed_ip_address: null,
			port_id: null, instance_id: null, instance_name: null, project_id: state.selectedProjectId, router_id: null, floating_network_id: network.id,
		};
		state.topology.floating_ips.push(created);
		const { id, floating_ip_address, fixed_ip_address, status, port_id, project_id } = created;
		return { id, floating_ip_address, fixed_ip_address, status, port_id, project_id };
	}
	const item = path.match(/^\/api\/v1\/admin\/floating-ips\/([^/]+)$/);
	if (item && method === 'DELETE') {
		const id = decodeURIComponent(item[1]);
		// Neutron deletion ignores a missing floating IP and releases an associated one.
		state.topology.floating_ips = state.topology.floating_ips.filter((fip) => fip.id !== id);
		return {};
	}
	return undefined;
}
