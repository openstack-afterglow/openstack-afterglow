import { describe, expect, it } from 'vitest';
import { t } from '$lib/i18n/ns/instance';
import type { PortInfo } from '$lib/types/networks';
import type { SecurityGroupRule } from '$lib/types/securityGroup';
import { buildInstanceIsoScene } from '../instanceIsoScene';

const instance = { id: 'vm', name: 'build-worker', status: 'ACTIVE' };
const first: PortInfo = {
	id: 'port-a', network_id: 'lan', name: 'uplink', device_owner: 'compute:nova', project_id: 'p',
	fixed_ips: [{ ip_address: '192.0.2.4' }, { ip_address: '2001:db8::4' }], status: 'ACTIVE',
};
const second: PortInfo = { ...first, id: 'port-b', network_id: 'data', status: 'DOWN', fixed_ips: [{ ip_address: '198.51.100.20' }] };
const rule = (id: string, overrides: Partial<SecurityGroupRule> = {}): SecurityGroupRule => ({
	id, direction: 'ingress', ethertype: 'IPv4', protocol: 'tcp', port_range_min: 22, port_range_max: 22,
	remote_group_id: null, remote_ip_prefix: '0.0.0.0/0', ...overrides,
});
const groups = [
	{ id: 'ssh', name: 'SSH', rules: [rule('22')] },
	{ id: 'infra', name: 'infra', rules: [
		rule('24', { port_range_min: 23, port_range_max: 24 }),
		rule('tls', { remote_group_id: 'trusted', remote_ip_prefix: null, port_range_min: 443, port_range_max: 443 }),
		rule('icmp6', { ethertype: 'IPv6', protocol: 'ipv6-icmp', port_range_min: -1, port_range_max: -1, remote_ip_prefix: '2001:db8::/32' }),
		rule('out', { direction: 'egress', protocol: null, port_range_min: null, port_range_max: null, remote_ip_prefix: null }),
	] },
	{ id: 'trusted', name: 'trusted-clients', rules: [rule('unapplied', { port_range_min: 12345, port_range_max: 12345 })] },
];
const input = {
	instance, ports: [first, second], networks: [{ id: 'lan', name: 'front-net' }, { id: 'data', name: 'data-net' }, { id: 'unattached', name: 'unused' }],
	floatingIps: [
		{ id: 'fip', port_id: first.id, status: 'ACTIVE', fixed_ip_address: '192.0.2.4', floating_ip_address: '203.0.113.9' },
		{ id: 'other', port_id: 'not-this-vm', status: 'ACTIVE', fixed_ip_address: null, floating_ip_address: '203.0.113.10' },
	],
	policy: { groups, groupIds: ['ssh', 'infra', 'ssh'] },
	waygateLocked: true,
};

describe('buildInstanceIsoScene', () => {
	it('shows the instance boundary, all observed ports and only port-associated floating IPs', () => {
		const { scene, details } = buildInstanceIsoScene(input);
		expect(scene.platforms.map(platform => platform.id)).toEqual(['policy', 'network:lan', 'network:data']);
		expect(scene.platforms[0]).toMatchObject({ style: 'zone', sublabel: 'infra, SSH' });
		expect(scene.nodes[0]).toMatchObject({ id: 'instance:vm', platformId: 'policy', badges: [{ text: t('network.iso.managed') }] });
		expect(scene.nodes.find(node => node.id === 'port:port-a')).toMatchObject({ sublabel: '192.0.2.4, 2001:db8::4', platformId: 'network:lan', status: 'ok' });
		expect(scene.nodes.find(node => node.id === 'port:port-b')).toMatchObject({ platformId: 'network:data', status: 'off' });
		expect(scene.edges).toContainEqual(expect.objectContaining({ from: 'port:port-a', to: 'floating:external', label: '203.0.113.9' }));
		expect(scene.edges.some(edge => edge.label === '203.0.113.10')).toBe(false);
		expect(details.get('network:data')).toMatchObject({ kind: 'network', ports: [second] });
		expect(buildInstanceIsoScene({ ...input, ports: [second, first] }).scene).toEqual(scene);
	});

	it('shows open internet SSH, a remote group, IPv6 and egress-all using the saved rule union', () => {
		const { scene, details } = buildInstanceIsoScene(input);
		const ingress = scene.edges.filter(edge => edge.kind === 'ingress');
		expect(ingress).toHaveLength(3);
		const internet = ingress.find(edge => edge.label === 'TCP 22–24')!;
		expect(internet).toMatchObject({ directed: true, to: 'instance:vm' });
		expect(scene.nodes.find(node => node.id === internet.from)).toMatchObject({ kind: 'internet', label: t('network.iso.internet'), sublabel: '0.0.0.0/0' });
		expect(scene.nodes.find(node => node.id === ingress.find(edge => edge.label === 'TCP 443')?.from)).toMatchObject({ kind: 'security-group', label: 'trusted-clients' });
		expect(scene.nodes.find(node => node.label === '2001:db8::/32')?.kind).toBe('cidr');
		const egress = scene.edges.find(edge => edge.kind === 'egress')!;
		expect(egress).toMatchObject({ from: 'instance:vm', label: t('securityGroupUnion.any') });
		expect(details.get(egress.to)).toMatchObject({ kind: 'rules', rules: [{ ethertype: 'IPv4', protocol: null, remote: { value: '0.0.0.0/0' } }] });
	});

	it('collapses long egress lists into a count without losing inspector rules', () => {
		const rules = Array.from({ length: 4 }, (_, i) => rule(`out-${i}`, { direction: 'egress', remote_ip_prefix: `192.0.2.${i}/32` }));
		const { scene, details } = buildInstanceIsoScene({ ...input, policy: { groups: [{ id: 'x', name: 'x', rules }], groupIds: ['x'] } });
		expect(scene.edges.filter(edge => edge.kind === 'egress')).toEqual([expect.objectContaining({ to: 'egress', label: t('network.iso.rulesCount', { count: 4 }) })]);
		expect(details.get('egress')).toMatchObject({ kind: 'rules', rules: rules.map(() => expect.anything()) });
	});

	it('separates observed no groups from unknown and incomplete snapshots', () => {
		const empty = buildInstanceIsoScene({ ...input, policy: { groups, groupIds: [] } });
		const unknown = buildInstanceIsoScene({ ...input, policy: null });
		const missing = buildInstanceIsoScene({ ...input, policy: { groups, groupIds: ['ssh', 'missing'] } });
		expect(empty.policyKnown).toBe(true);
		expect(empty.scene.platforms[0].sublabel).toBe(t('network.none'));
		for (const result of [unknown, missing]) {
			expect(result.policyKnown).toBe(false);
			expect(result.scene.platforms[0].sublabel).toBe(t('network.iso.policyUnknown'));
			expect(result.scene.edges.some(edge => edge.kind === 'ingress' || edge.kind === 'egress')).toBe(false);
		}
		expect(missing.missingGroupIds).toEqual(['missing']);
	});
});
