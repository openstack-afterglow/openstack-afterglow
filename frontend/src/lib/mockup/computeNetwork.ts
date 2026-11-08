import { ApiError } from '$lib/api/errors';
import type { Keypair } from '$lib/types/keypair';
import type { FloatingIp } from '$lib/types/networks';
import type { SecurityGroup } from '$lib/types/securityGroup';
import { getMockupState } from './state';

// Explicit synthetic tutorial state: SSH keypairs, floating IPs, project networks and security groups.
// Returns undefined for paths this module does not own so transport can keep its own dispatch.
const KEYPAIR_NAME = /^[A-Za-z0-9 _.@-]{1,255}$/;
const PUBLIC_KEY = /^(ssh-rsa|ssh-ed25519|ssh-dss|ecdsa-sha2-\S+)\s+\S+/;
const SECURITY_GROUP_LIMIT = 10;
const SECURITY_GROUP_RULE_LIMIT = 100;

function fingerprint(seed: string): string {
	let hash = 2166136261;
	const bytes: string[] = [];
	for (let index = 0; index < 16; index++) {
		hash = Math.imul(hash ^ seed.charCodeAt(index % seed.length) ^ index, 16777619) >>> 0;
		bytes.push((hash & 0xff).toString(16).padStart(2, '0'));
	}
	return bytes.join(':');
}

function validCidr(value: string): boolean {
	const [address, prefix, ...extra] = value.split('/');
	if (extra.length > 0 || prefix === undefined || !/^[0-9]+$/.test(prefix)) return false;
	if (/^\d{1,3}(\.\d{1,3}){3}$/.test(address)) return address.split('.').every((part) => Number(part) <= 255) && Number(prefix) <= 32;
	return address.includes(':') && /^[0-9a-f:]+$/i.test(address) && Number(prefix) <= 128;
}

export function nextFloatingAddress(networkId: string): string {
	const state = getMockupState();
	const network = state.topology.networks.find((item) => item.id === networkId);
	const cidr = network?.subnet_details.find((subnet) => subnet.ip_version === 4)?.cidr;
	if (!cidr) throw new ApiError(409, 'No IPv4 subnet is available on the external network.');
	const base = cidr.split('/')[0].split('.').slice(0, 3).join('.');
	const used = new Set([
		...state.topology.floating_ips.map((fip) => fip.floating_ip_address),
		...state.topology.routers.flatMap((router) => router.external_gateway_ips ?? []),
	]);
	for (let host = 10; host < 255; host++) {
		const address = `${base}.${host}`;
		if (!used.has(address)) return address;
	}
	throw new ApiError(409, 'No more IP addresses available on the external network.');
}

function keypairs(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/keypairs' && method === 'GET') return state.keypairs.map(({ name, fingerprint, type }) => ({ name, fingerprint, type }));
	if (path === '/api/v1/keypairs' && method === 'POST') {
		const payload = (body ?? {}) as { name?: string; public_key?: string | null };
		const name = String(payload.name ?? '').trim();
		const publicKey = String(payload.public_key ?? '').trim();
		if (!KEYPAIR_NAME.test(name)) throw new ApiError(422, 'Keypair name must use letters, digits, spaces, ".", "_", "-" or "@".');
		if (publicKey && !PUBLIC_KEY.test(publicKey)) throw new ApiError(422, 'Public key is not a valid OpenSSH public key.');
		if (state.keypairs.some((item) => item.name === name)) throw new ApiError(409, 'Keypair name already exists.');
		const created: Keypair = { name, fingerprint: fingerprint(publicKey || name), type: 'ssh', public_key: publicKey || `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5-tutorial-${name.replace(/\s+/g, '-')}` };
		state.keypairs.push(created);
		// Synthetic marker text only: the tutorial never produces a usable credential.
		return publicKey ? created : { ...created, private_key: `tutorial-sample-private-key-for-${created.name}\n(synthetic tutorial data; not a usable SSH key)` };
	}
	const remove = path.match(/^\/api\/v1\/keypairs\/([^/]+)$/);
	if (remove && method === 'DELETE') {
		// Nova deletes with ignore_missing=True, so an absent keypair still succeeds.
		const name = decodeURIComponent(remove[1]);
		state.keypairs = state.keypairs.filter((item) => item.name !== name);
		return {};
	}
	return undefined;
}

function floatingIps(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/networks/floating-ips' && method === 'POST') {
		const networkId = String((body as { floating_network_id?: string } | null)?.floating_network_id ?? '');
		const network = state.topology.networks.find((item) => item.id === networkId);
		if (!network?.is_external) throw new ApiError(404, 'External network not found.');
		const address = nextFloatingAddress(network.id);
		const created: FloatingIp = {
			id: `mock-fip-${address.replace(/\./g, '-')}`,
			floating_ip_address: address,
			status: 'DOWN',
			fixed_ip_address: null,
			port_id: null,
			instance_id: null,
			instance_name: null,
			project_id: state.selectedProjectId,
			router_id: null,
			floating_network_id: network.id,
		};
		state.topology.floating_ips.push(created);
		return created;
	}
	const remove = path.match(/^\/api\/v1\/networks\/floating-ips\/([^/]+)$/);
	if (remove && method === 'DELETE') {
		const id = decodeURIComponent(remove[1]);
		const item = state.topology.floating_ips.find((fip) => fip.id === id);
		if (!item || item.project_id !== state.selectedProjectId) throw new ApiError(404, 'Floating IP not found.');
		state.topology.floating_ips = state.topology.floating_ips.filter((fip) => fip.id !== id);
		return {};
	}
	return undefined;
}

function networks(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	const topology = state.topology;
	if (path === '/api/v1/networks' && method === 'POST') {
		const payload = (body ?? {}) as { name?: string; subnet?: { name?: string; cidr?: string; gateway_ip?: string | null; enable_dhcp?: boolean } | null };
		const name = String(payload.name ?? '');
		// Mirrors CreateNetworkRequest.name: Field(min_length=1, max_length=255).
		if (name.length < 1 || name.length > 255) throw new ApiError(422, 'Network name must be 1-255 characters.');
		const cidr = payload.subnet ? String(payload.subnet.cidr ?? '').trim() : '';
		if (payload.subnet && !validCidr(cidr)) throw new ApiError(422, 'Subnet CIDR is invalid.');
		let index = topology.networks.length + 1;
		while (topology.networks.some((item) => item.id === `mock-net-${index}`)) index++;
		const id = `mock-net-${index}`;
		const subnets = payload.subnet
			? [{ id: `${id}-subnet`, name: payload.subnet.name || `${name}-subnet`, cidr, ip_version: cidr.includes(':') ? 6 : 4, gateway_ip: payload.subnet.gateway_ip ?? null, dhcp_enabled: payload.subnet.enable_dhcp ?? true }]
			: [];
		topology.networks.push({ id, name, status: 'ACTIVE', is_external: false, is_shared: false, project_id: state.selectedProjectId, subnet_details: subnets });
		return { id, name, status: 'ACTIVE', subnets: subnets.map((item) => item.id), cidrs: subnets.map((item) => item.cidr), is_external: false, is_shared: false, project_id: state.selectedProjectId };
	}
	const remove = path.match(/^\/api\/v1\/networks\/([^/]+)$/);
	if (remove && method === 'DELETE' && !['floating-ips', 'default', 'topology'].includes(remove[1])) {
		const id = decodeURIComponent(remove[1]);
		const network = topology.networks.find((item) => item.id === id);
		if (!network || network.project_id !== state.selectedProjectId) throw new ApiError(404, 'Network not found.');
		const subnetIds = new Set(network.subnet_details.map((subnet) => subnet.id));
		const inUse = topology.instances.some((instance) => instance.ip_addresses.some((ip) => ip.network_id === id))
			|| topology.routers.some((router) => router.connected_subnet_ids.some((subnetId) => subnetIds.has(subnetId)));
		if (inUse) throw new ApiError(409, 'Network is in use by ports.');
		topology.networks = topology.networks.filter((item) => item.id !== id);
		return {};
	}
	return undefined;
}

function securityGroups(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/security-groups' && method === 'GET') return state.securityGroups;
	if (path === '/api/v1/security-groups/quota' && method === 'GET') {
		return {
			security_group: { limit: SECURITY_GROUP_LIMIT, in_use: state.securityGroups.length },
			security_group_rule: { limit: SECURITY_GROUP_RULE_LIMIT, in_use: state.securityGroups.reduce((sum, group) => sum + group.rules.length, 0) },
		};
	}
	if (path === '/api/v1/security-groups' && method === 'POST') {
		const payload = (body ?? {}) as { name?: string; description?: string };
		const name = String(payload.name ?? '').trim();
		if (!name) throw new ApiError(422, 'Security group name is required.');
		if (name === 'default') throw new ApiError(409, 'Default security group already exists.');
		if (state.securityGroups.length >= SECURITY_GROUP_LIMIT) throw new ApiError(409, 'Security group quota exceeded.');
		let index = state.securityGroups.length + 1;
		while (state.securityGroups.some((group) => group.id === `mock-sg-${index}`)) index++;
		const id = `mock-sg-${index}`;
		// Neutron seeds every new group with allow-all egress rules for both IP versions.
		const created: SecurityGroup = {
			id,
			name,
			description: String(payload.description ?? ''),
			rules: [
				{ id: `${id}-egress-v4`, direction: 'egress', protocol: null, port_range_min: null, port_range_max: null, remote_ip_prefix: '0.0.0.0/0', remote_group_id: null, ethertype: 'IPv4' },
				{ id: `${id}-egress-v6`, direction: 'egress', protocol: null, port_range_min: null, port_range_max: null, remote_ip_prefix: '::/0', remote_group_id: null, ethertype: 'IPv6' },
			],
		};
		state.securityGroups.push(created);
		return created;
	}
	const instances = path.match(/^\/api\/v1\/security-groups\/([^/]+)\/instances$/);
	if (instances && method === 'GET') {
		const group = state.securityGroups.find((item) => item.id === decodeURIComponent(instances[1]));
		if (!group) throw new ApiError(404, 'Security group not found.');
		return group.name === 'default' ? state.instances.slice(0, 1).map(({ id, name, status }) => ({ id, name, status })) : [];
	}
	const remove = path.match(/^\/api\/v1\/security-groups\/([^/]+)$/);
	if (remove && method === 'DELETE') {
		const id = decodeURIComponent(remove[1]);
		const group = state.securityGroups.find((item) => item.id === id);
		if (!group) throw new ApiError(404, 'Security group not found.');
		if (group.name === 'default') throw new ApiError(409, 'The default security group cannot be deleted.');
		state.securityGroups = state.securityGroups.filter((item) => item.id !== id);
		return {};
	}
	return undefined;
}

export function mockComputeNetwork(method: string, path: string, body: unknown): unknown | undefined {
	return keypairs(method, path, body)
		?? floatingIps(method, path, body)
		?? networks(method, path, body)
		?? securityGroups(method, path, body);
}
