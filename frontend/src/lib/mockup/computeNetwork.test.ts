import { describe, expect, it, beforeEach } from 'vitest';
import { ApiError } from '$lib/api/errors';
import { mockComputeNetwork } from './computeNetwork';
import { getMockupState, resetMockupState } from './state';

type Named = { id?: string; name: string };

function call(method: string, path: string, body: unknown = null): unknown {
	return mockComputeNetwork(method, path, body);
}

function status(fn: () => unknown): number | undefined {
	try {
		fn();
	} catch (error) {
		return error instanceof ApiError ? error.status : undefined;
	}
	return undefined;
}

describe('mockComputeNetwork keypairs', () => {
	beforeEach(() => resetMockupState());

	it('creates a generated keypair with a private key, lists it without secrets and deletes it', () => {
		const before = (call('GET', '/api/v1/keypairs') as Named[]).map((item) => item.name);
		const created = call('POST', '/api/v1/keypairs', { name: 'qa-key', public_key: null }) as { name: string; private_key?: string; fingerprint: string };
		expect(created.private_key).toBeTruthy();
		const listed = call('GET', '/api/v1/keypairs') as Record<string, unknown>[];
		expect(listed.map((item) => item.name)).toEqual([...before, 'qa-key']);
		expect(listed.every((item) => !('private_key' in item))).toBe(true);
		call('DELETE', '/api/v1/keypairs/qa-key');
		expect((call('GET', '/api/v1/keypairs') as Named[]).map((item) => item.name)).toEqual(before);
	});

	it('imports a public key without returning a private key', () => {
		const created = call('POST', '/api/v1/keypairs', { name: 'imported', public_key: 'ssh-ed25519 AAAAC3Nza tutorial@example' }) as { private_key?: string };
		expect(created.private_key).toBeUndefined();
	});

	it('rejects an empty or invalid name, a malformed public key and a duplicate name', () => {
		expect(status(() => call('POST', '/api/v1/keypairs', { name: '  ' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/keypairs', { name: 'bad/name' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/keypairs', { name: 'qa-key', public_key: 'not-a-key' }))).toBe(422);
		call('POST', '/api/v1/keypairs', { name: 'qa-key' });
		expect(status(() => call('POST', '/api/v1/keypairs', { name: 'qa-key' }))).toBe(409);
	});
});

describe('mockComputeNetwork floating IPs', () => {
	beforeEach(() => resetMockupState());

	it('allocates an unused address from the external network and releases it', () => {
		const state = getMockupState();
		const used = new Set(state.topology.floating_ips.map((fip) => fip.floating_ip_address));
		const created = call('POST', '/api/v1/networks/floating-ips', { floating_network_id: 'mock-net-public' }) as { id: string; floating_ip_address: string; status: string; fixed_ip_address: string | null };
		expect(used.has(created.floating_ip_address)).toBe(false);
		expect(created.floating_ip_address.startsWith('203.0.113.')).toBe(true);
		expect([created.status, created.fixed_ip_address]).toEqual(['DOWN', null]);
		expect(state.topology.floating_ips.some((fip) => fip.id === created.id)).toBe(true);
		const second = call('POST', '/api/v1/networks/floating-ips', { floating_network_id: 'mock-net-public' }) as { floating_ip_address: string };
		expect(second.floating_ip_address).not.toBe(created.floating_ip_address);
		call('DELETE', `/api/v1/networks/floating-ips/${created.id}`);
		expect(getMockupState().topology.floating_ips.some((fip) => fip.id === created.id)).toBe(false);
	});

	it('rejects allocation from a non-external network and release of an unknown address', () => {
		expect(status(() => call('POST', '/api/v1/networks/floating-ips', { floating_network_id: 'mock-net-private' }))).toBe(404);
		expect(status(() => call('POST', '/api/v1/networks/floating-ips', {}))).toBe(404);
		expect(status(() => call('DELETE', '/api/v1/networks/floating-ips/missing'))).toBe(404);
	});
});

describe('mockComputeNetwork networks', () => {
	beforeEach(() => resetMockupState());

	it('creates a project network with an optional subnet and deletes it', () => {
		const created = call('POST', '/api/v1/networks', { name: 'qa-net', subnet: { cidr: '10.20.0.0/24', gateway_ip: null, enable_dhcp: true } }) as { id: string; subnets: string[]; cidrs: string[] };
		expect(created.cidrs).toEqual(['10.20.0.0/24']);
		const network = getMockupState().topology.networks.find((item) => item.id === created.id);
		expect(network?.project_id).toBe(getMockupState().selectedProjectId);
		const plain = call('POST', '/api/v1/networks', { name: 'qa-net' }) as { id: string; subnets: string[] };
		expect(plain.id).not.toBe(created.id);
		expect(plain.subnets).toEqual([]);
		call('DELETE', `/api/v1/networks/${created.id}`);
		expect(getMockupState().topology.networks.some((item) => item.id === created.id)).toBe(false);
	});

	it('rejects an empty name, an invalid CIDR, unknown or external networks and networks in use', () => {
		expect(status(() => call('POST', '/api/v1/networks', { name: '' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/networks', { name: 'qa-net', subnet: { cidr: '10.0.0.300/24' } }))).toBe(422);
		expect(status(() => call('DELETE', '/api/v1/networks/missing'))).toBe(404);
		expect(status(() => call('DELETE', '/api/v1/networks/mock-net-public'))).toBe(404);
		expect(status(() => call('DELETE', '/api/v1/networks/mock-net-private'))).toBe(409);
	});
});

describe('mockComputeNetwork security groups', () => {
	beforeEach(() => resetMockupState());

	it('creates a group with default egress rules, tracks quota and deletes it', () => {
		const quota = () => call('GET', '/api/v1/security-groups/quota') as { security_group: { in_use: number } };
		const before = quota().security_group.in_use;
		const created = call('POST', '/api/v1/security-groups', { name: 'qa-web', description: 'tutorial' }) as { id: string; rules: { direction: string }[] };
		expect(created.rules.map((rule) => rule.direction)).toEqual(['egress', 'egress']);
		expect((call('GET', '/api/v1/security-groups') as Named[]).map((group) => group.name)).toContain('qa-web');
		expect(quota().security_group.in_use).toBe(before + 1);
		expect(call('GET', `/api/v1/security-groups/${created.id}/instances`)).toEqual([]);
		call('DELETE', `/api/v1/security-groups/${created.id}`);
		expect((call('GET', '/api/v1/security-groups') as Named[]).some((group) => group.id === created.id)).toBe(false);
		expect(quota().security_group.in_use).toBe(before);
	});

	it('rejects an empty name, a second default group, deleting default and unknown groups', () => {
		expect(status(() => call('POST', '/api/v1/security-groups', { name: '' }))).toBe(422);
		expect(status(() => call('POST', '/api/v1/security-groups', { name: 'default' }))).toBe(409);
		const defaultGroup = (call('GET', '/api/v1/security-groups') as Named[]).find((group) => group.name === 'default');
		expect(status(() => call('DELETE', `/api/v1/security-groups/${defaultGroup?.id}`))).toBe(409);
		expect(status(() => call('DELETE', '/api/v1/security-groups/missing'))).toBe(404);
	});
});

describe('mockComputeNetwork ownership', () => {
	beforeEach(() => resetMockupState());

	it('returns undefined for paths it does not own', () => {
		expect(call('GET', '/api/v1/volumes')).toBeUndefined();
		expect(call('GET', '/api/v1/networks')).toBeUndefined();
		expect(call('GET', '/api/v1/networks/floating-ips')).toBeUndefined();
		expect(call('GET', '/api/v1/instances/mock-instance-1/security-groups')).toBeUndefined();
	});
});
