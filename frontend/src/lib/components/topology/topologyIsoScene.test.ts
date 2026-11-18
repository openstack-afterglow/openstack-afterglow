import { describe, expect, it } from 'vitest';
import { makeFixture, mkNet, P, OTHER } from './canvas/__tests__/fixtures';
import { topologyIsoScene, topologyPlatformId } from './topologyIsoScene';
import type { TopologyData } from '$lib/types/topology';

const empty: TopologyData = { networks: [], routers: [], instances: [], floating_ips: [] };

describe('topology isometric adapter', () => {
	it('packs a multi-homed workload onto one slab and connects all extra networks', () => {
		const data = makeFixture();
		data.instances.find(({ id }) => id === 'vm-db-01')!.is_database = true;
		const { nodes, platforms, edges } = topologyIsoScene(data, P);
		const db = nodes.find(({ id }) => id === 'vm-db-01')!;
		const slab = platforms.find(({ id }) => id === db.platformId)!;
		expect(db.kind).toBe('database');
		expect(db.sublabel).toBe('10.10.2.31');
		expect(slab).toMatchObject({ label: 'app-net', sublabel: '10.10.2.0/24' });
		expect(db.x).toBeGreaterThan(slab.x);
		expect(db.x).toBeLessThan(slab.x + slab.w);
		expect(edges.filter(({ from }) => from === db.id).map(({ to }) => to)).toEqual(['network:net-mgmt', 'network:net-web']);
	});

	it('bridges the reported external gateway to the router and its tenant networks', () => {
		const { nodes, platforms, edges } = topologyIsoScene(makeFixture(), P);
		const gateway = platforms.find(({ id }) => id === 'network:net-pub')!;
		expect(gateway).toMatchObject({ tone: 'gateway', style: 'slab', y: 0 });
		expect(nodes.find(({ id }) => id === 'rtr-edge')?.y).toBeGreaterThan(gateway.y);
		expect(edges).toEqual(expect.arrayContaining([
			expect.objectContaining({ from: gateway.id, to: 'rtr-edge', label: '203.0.113.10' }),
			expect.objectContaining({ from: 'rtr-edge', to: 'network:net-web', label: '10.10.1.1' }),
			expect.objectContaining({ from: 'rtr-edge', to: 'network:net-app', label: '10.10.2.1' }),
		]));
	});

	it('preserves load balancer VIPs and links to VM and address-only members', () => {
		const data = makeFixture();
		data.load_balancers![0].members.push({ id: 'm3', address: '10.10.1.97', protocol_port: 8081, status: 'OFFLINE', subnet_id: 'sn-web', pool_id: 'pool-web', server_id: null });
		const { nodes, edges } = topologyIsoScene(data, P);
		expect(nodes).toEqual(expect.arrayContaining([
			expect.objectContaining({ id: 'lb-web', kind: 'loadbalancer', platformId: 'network:net-web', sublabel: '10.10.1.100' }),
			expect.objectContaining({ id: 'member:lb-web:m3', kind: 'port', label: '10.10.1.97', interactive: false }),
		]));
		expect(edges).toEqual(expect.arrayContaining([
			expect.objectContaining({ from: 'lb-web', to: 'vm-web-01', directed: true, label: '8080' }),
			expect.objectContaining({ from: 'lb-web', to: 'member:lb-web:m3', inactive: true, label: '8081' }),
		]));
	});

	it('preserves attached floating IPs from port association and does not guess a detached owner', () => {
		const data = makeFixture();
		data.floating_ips[0].instance_id = null;
		data.floating_ips.push({ id: 'free', port_id: null, fixed_ip_address: null, floating_ip_address: '203.0.113.200', floating_network_id: 'net-pub', status: 'DOWN' });
		const { nodes, edges } = topologyIsoScene(data, P);
		expect(nodes.find(({ id }) => id === 'vm-web-01')?.badges).toEqual([{ text: '203.0.113.101', tone: 'external' }]);
		expect(edges.find(({ id }) => id === 'fip:fip-1')).toMatchObject({ from: 'network:net-pub', to: 'vm-web-01', label: '203.0.113.101' });
		expect(nodes.find(({ id }) => id === 'fip:free')).toMatchObject({ platformId: 'network:net-pub', status: 'off', interactive: false });
		expect(edges.some(({ id }) => id === 'fip:free')).toBe(false);
	});

	it('retains shared networks from other projects but excludes other private resources', () => {
		const data = makeFixture();
		data.networks.find(({ id }) => id === 'net-transit')!.project_id = OTHER;
		const { platforms, nodes, edges } = topologyIsoScene(data, P);
		expect(platforms.find(({ id }) => id === 'network:net-transit')).toMatchObject({ tone: 'shared' });
		expect(platforms.some(({ id }) => id === 'network:net-other')).toBe(false);
		expect(nodes.map(({ id }) => id)).not.toContain('rtr-other');
		expect(nodes.map(({ id }) => id)).not.toContain('vm-other-01');
		expect(edges.some(({ from, to }) => from === 'rtr-other' || to === 'rtr-other')).toBe(false);
	});

	it('returns an empty scene without synthetic nodes', () => {
		expect(topologyIsoScene(empty, P)).toEqual({ nodes: [], platforms: [], edges: [] });
	});

	it.each([
		['10.1.0.2', '10.1.0.0/24', '10.1.0.0/24', null],
		['10.2.0.2', '10.1.0.0/24', '10.2.0.0/24', 'second'],
		['2001:db8:abcd::9', '2001:db8:abce::/64', '2001:db8:abcd::/64', 'second'],
	])('requires unique CIDR evidence for same-named networks containing %s', (addr, first, second, resolved) => {
		const data: TopologyData = {
			...empty,
			networks: [mkNet('primary', 'primary', '192.0.2.0/24', '', { project: P }), mkNet('first', 'duplicate', first, '', { project: P }), mkNet('second', 'duplicate', second, '', { project: P })],
			instances: [{ id: 'vm', name: 'vm', status: 'ACTIVE', network_names: ['primary', 'duplicate'], ip_addresses: [
				{ network_id: 'primary', addr: '192.0.2.4', network_name: 'primary', type: 'fixed' },
				{ addr, network_name: 'duplicate', type: 'fixed' },
			] }],
		};
		const scene = topologyIsoScene(data, P, { unresolvedAddress: (value) => `${value} · unresolved` });
		if (resolved) expect(scene.edges).toMatchObject([{ from: 'vm', to: topologyPlatformId(resolved), label: addr }]);
		else {
			expect(scene.edges).toHaveLength(0);
			expect(scene.nodes[0]).toMatchObject({ platformId: 'network:primary', badges: [{ text: `${addr} · unresolved`, tone: 'neutral' }] });
		}
	});
});
