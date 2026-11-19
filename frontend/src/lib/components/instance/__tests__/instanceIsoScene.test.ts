import { describe, expect, it } from 'vitest';
import { t } from '$lib/i18n/ns/instance';
import { getStatusLabel } from '$lib/config/statusColors';
import type { PortInfo } from '$lib/types/networks';
import type { SecurityGroupRule } from '$lib/types/securityGroup';
import type { IsoScene } from '$lib/components/iso/types';
import { buildInstanceIsoScene, securityGroupNodeOf } from '../instanceIsoScene';

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
const portGroups = (entries: Record<string, string[]>) => new Map(Object.entries(entries));
const input = {
	instance, ports: [first, second],
	networks: [
		{ id: 'lan', name: 'front-net', is_external: true }, { id: 'data', name: 'data-net', is_shared: true },
		{ id: 'unattached', name: 'unused', is_external: false, is_shared: false },
	],
	floatingIps: [
		{ id: 'fip', port_id: first.id, status: 'ACTIVE', fixed_ip_address: '192.0.2.4', floating_ip_address: '203.0.113.9' },
		{ id: 'other', port_id: 'not-this-vm', status: 'ACTIVE', fixed_ip_address: null, floating_ip_address: '203.0.113.10' },
	],
	// port-a carries two groups, port-b only one: the same group on two ports stays two port-level associations.
	policy: { groups, portGroupIds: portGroups({ 'port-a': ['ssh', 'infra'], 'port-b': ['ssh'] }) },
	volumes: null,
	shares: null,
	waygateLocked: true,
};
// Groups on a port are ordered by name in code-unit order (uppercase before lowercase).
const sgIds = (scene: IsoScene) => scene.nodes.filter(node => node.kind === 'security-group' && node.id.startsWith('sg:') && !node.id.includes('>')).map(node => node.id);

describe('buildInstanceIsoScene', () => {
	it('shows the instance, all observed ports and only port-associated floating IPs', () => {
		const { scene, details } = buildInstanceIsoScene(input);
		expect(scene.platforms.map(platform => platform.id)).toEqual(['network:lan', 'network:data']);
		expect(scene.platforms.map(platform => platform.kind)).toEqual(['external-network', 'shared-network']);
		expect(scene.nodes[0]).toMatchObject({ id: 'instance:vm', badges: [{ text: t('network.iso.managed') }] });
		expect(scene.nodes[0].platformId).toBeUndefined();
		expect(scene.nodes.find(node => node.id === 'port:port-a')).toMatchObject({ sublabel: '192.0.2.4, 2001:db8::4', platformId: 'network:lan', status: 'ok' });
		expect(scene.nodes.find(node => node.id === 'port:port-b')).toMatchObject({
			platformId: 'network:data', status: undefined,
			badges: [{ text: getStatusLabel('DOWN') }],
		});
		expect(scene.edges).toContainEqual(expect.objectContaining({ from: 'port:port-a', to: 'floating:external', label: '203.0.113.9' }));
		expect(scene.edges.some(edge => edge.label === '203.0.113.10')).toBe(false);
		expect(details.get('network:data')).toMatchObject({ kind: 'network', ports: [second] });
		expect(buildInstanceIsoScene({ ...input, ports: [second, first] }).scene).toEqual(scene);
	});

	it('attaches each security group to its own port, never to a network or the instance', () => {
		const { scene, details } = buildInstanceIsoScene(input);
		expect(sgIds(scene)).toEqual(['sg:port-a:ssh', 'sg:port-a:infra', 'sg:port-b:ssh']);
		const links = scene.edges.filter(edge => edge.id.startsWith('sg-link:'));
		expect(links.map(edge => [edge.from, edge.to])).toEqual([
			['port:port-a', 'sg:port-a:ssh'], ['port:port-a', 'sg:port-a:infra'], ['port:port-b', 'sg:port-b:ssh'],
		]);
		// No group is wired to the instance or a platform id, and no zone wraps the instance.
		expect(scene.edges.some(edge => edge.from === 'instance:vm' && edge.to.startsWith('sg:'))).toBe(false);
		expect(scene.platforms.some(platform => platform.style === 'zone')).toBe(false);
		expect(scene.nodes.find(node => node.id === 'sg:port-b:ssh')).toMatchObject({ platformId: 'network:data' });
		expect(details.get('sg:port-a:ssh')).toMatchObject({ kind: 'security-group', groupId: 'ssh', ports: [first], missing: false, internetOpen: true });
		expect(details.get('port:port-b')).toMatchObject({ kind: 'port', securityGroups: ['SSH'] });
	});

	it('places group chips on the slab beside their port, on the side facing away from the instance', () => {
		const { scene } = buildInstanceIsoScene(input);
		for (const portId of ['port-a', 'port-b']) {
			const port = scene.nodes.find(node => node.id === `port:${portId}`)!;
			const slab = scene.platforms.find(platform => platform.id === port.platformId)!;
			for (const id of sgIds(scene).filter(sg => sg.startsWith(`sg:${portId}:`))) {
				const chip = scene.nodes.find(node => node.id === id)!;
				expect(chip.y).toBe(port.y);
				expect(chip.x).toBeGreaterThanOrEqual(slab.x);
				expect(chip.x).toBeLessThanOrEqual(slab.x + slab.w);
				// The first slab opens to the right and the second to the left of the instance.
				expect(portId === 'port-a' ? chip.x > port.x : chip.x < port.x).toBe(true);
			}
		}
	});

	it('keeps floating-IP Internet beyond the slab containing three ports', () => {
		const ports = [first, { ...first, id: 'port-b' }, { ...first, id: 'port-c' }];
		const { scene } = buildInstanceIsoScene({ ...input, ports, policy: { groups, portGroupIds: portGroups({ 'port-a': ['ssh'], 'port-b': ['ssh'], 'port-c': ['ssh'] }) } });
		const slab = scene.platforms.find(platform => platform.id === 'network:lan')!;
		const internet = scene.nodes.find(node => node.id === 'floating:external')!;
		expect(internet.x + internet.y).toBeGreaterThan(slab.x + slab.w + slab.y + slab.h);
	});

	it('does not infer a network kind when the catalog has no classification', () => {
		const { scene } = buildInstanceIsoScene({ ...input, networks: [{ id: 'lan', name: 'front-net' }] });
		expect(scene.platforms.map(platform => platform.kind)).toEqual([undefined, undefined]);
	});

	it('draws remote sources only for the selected group and wires them to that group', () => {
		const collapsed = buildInstanceIsoScene(input);
		expect(collapsed.scene.edges.some(edge => edge.kind === 'ingress' || edge.kind === 'egress')).toBe(false);

		const { scene, details } = buildInstanceIsoScene({ ...input, expandedSecurityGroup: 'sg:port-a:infra' });
		const ingress = scene.edges.filter(edge => edge.kind === 'ingress');
		expect(ingress).toHaveLength(3);
		expect(ingress.every(edge => edge.to === 'sg:port-a:infra')).toBe(true);
		const internet = ingress.find(edge => edge.label === 'TCP 23–24')!;
		expect(internet).toMatchObject({ directed: true });
		expect(scene.nodes.find(node => node.id === internet.from)).toMatchObject({ kind: 'internet', label: t('network.iso.internet'), sublabel: '0.0.0.0/0' });
		expect(scene.nodes.find(node => node.id === ingress.find(edge => edge.label === 'TCP 443')?.from)).toMatchObject({ kind: 'security-group', label: 'trusted-clients' });
		expect(scene.nodes.find(node => node.label === '2001:db8::/32')?.kind).toBe('cidr');
		const egress = scene.edges.find(edge => edge.kind === 'egress')!;
		expect(egress).toMatchObject({ from: 'sg:port-a:infra', label: t('securityGroupUnion.any') });
		expect(details.get(egress.to)).toMatchObject({ kind: 'rules', rules: [{ ethertype: 'IPv4', protocol: null, remote: { value: '0.0.0.0/0' } }] });
		// A selected remote source keeps its group expanded; a source of another group does not exist.
		expect(securityGroupNodeOf(internet.from)).toBe('sg:port-a:infra');
		expect(securityGroupNodeOf('port:port-a')).toBeNull();
		expect(buildInstanceIsoScene({ ...input, expandedSecurityGroup: internet.from }).scene).toEqual(scene);
	});

	it('uses one stable remote source for disjoint ingress rules of the same IP version', () => {
		const inbound = [rule('ssh'), rule('https', { port_range_min: 443, port_range_max: 443 }),
			rule('ssh-v6', { ethertype: 'IPv6', remote_ip_prefix: '::/0' })];
		const policy = { groups: [{ id: 'web', name: 'web', rules: inbound }], portGroupIds: portGroups({ 'port-a': ['web'], 'port-b': [] }) };
		const { scene, details } = buildInstanceIsoScene({ ...input, policy, expandedSecurityGroup: 'sg:port-a:web' });
		const ingress = scene.edges.filter(edge => edge.kind === 'ingress');
		expect(ingress).toHaveLength(2);
		const ipv4 = ingress.find(edge => edge.label === t('network.iso.rulesCount', { count: 2 }))!;
		expect(details.get(ipv4.from)).toMatchObject({ kind: 'rules', rules: [
			{ ethertype: 'IPv4', portRangeMin: 22 }, { ethertype: 'IPv4', portRangeMin: 443 },
		] });
		const withoutHttps = buildInstanceIsoScene({ ...input, expandedSecurityGroup: 'sg:port-a:web',
			policy: { ...policy, groups: [{ ...policy.groups[0], rules: [inbound[0]] }] } });
		expect(withoutHttps.scene.edges.find(edge => edge.kind === 'ingress')).toMatchObject({ from: ipv4.from, label: 'TCP 22' });
	});

	it('distinguishes IPv4 and IPv6 sources from the same named remote group', () => {
		const remote = { remote_group_id: 'trusted', remote_ip_prefix: null };
		const rules = [rule('v4', remote), rule('v6', { ...remote, ethertype: 'IPv6' })];
		const policy = {
			groups: [{ id: 'web', name: 'web', rules }, { id: 'trusted', name: 'default', rules: [] }],
			portGroupIds: portGroups({ 'port-a': ['web'], 'port-b': [] }),
		};
		const { scene } = buildInstanceIsoScene({ ...input, policy, expandedSecurityGroup: 'sg:port-a:web' });
		expect(scene.nodes.filter(node => node.kind === 'security-group' && node.id.includes('>'))).toEqual([
			expect.objectContaining({ label: 'default', sublabel: 'IPv4' }),
			expect.objectContaining({ label: 'default', sublabel: 'IPv6' }),
		]);
	});

	it('collapses long egress lists and extra ingress sources into counts without losing inspector rules', () => {
		const egress = Array.from({ length: 4 }, (_, i) => rule(`out-${i}`, { direction: 'egress', remote_ip_prefix: `192.0.2.${i}/32` }));
		const ingress = Array.from({ length: 6 }, (_, i) => rule(`in-${i}`, { remote_ip_prefix: `198.51.100.${i}/32` }));
		const policy = { groups: [{ id: 'x', name: 'x', rules: [...egress, ...ingress] }], portGroupIds: portGroups({ 'port-a': ['x'], 'port-b': [] }) };
		const { scene, details } = buildInstanceIsoScene({ ...input, policy, expandedSecurityGroup: 'sg:port-a:x' });
		expect(scene.edges.filter(edge => edge.kind === 'egress')).toEqual([expect.objectContaining({ to: 'sg:port-a:x>egress', label: t('network.iso.rulesCount', { count: 4 }) })]);
		expect(details.get('sg:port-a:x>egress')).toMatchObject({ kind: 'rules', rules: egress.map(() => expect.anything()) });
		expect(scene.nodes.find(node => node.id === 'sg:port-a:x>more')).toMatchObject({ label: t('network.iso.moreSources', { count: 3 }) });
		expect(details.get('sg:port-a:x>more')).toMatchObject({ kind: 'rules', rules: [expect.anything(), expect.anything(), expect.anything()] });
		expect(scene.edges.filter(edge => edge.kind === 'ingress')).toHaveLength(4);
	});

	it('separates observed no groups from unknown policy and a group that is not in the snapshot', () => {
		const empty = buildInstanceIsoScene({ ...input, policy: { groups, portGroupIds: portGroups({ 'port-a': [], 'port-b': [] }) } });
		const unknown = buildInstanceIsoScene({ ...input, policy: null });
		const missing = buildInstanceIsoScene({ ...input, policy: { groups, portGroupIds: portGroups({ 'port-a': ['ssh', 'missing'], 'port-b': [] }) } });
		expect(empty.policyKnown).toBe(true);
		expect(sgIds(empty.scene)).toEqual([]);
		expect(empty.details.get('port:port-a')).toMatchObject({ securityGroups: [] });
		expect(unknown.policyKnown).toBe(false);
		expect(sgIds(unknown.scene)).toEqual([]);
		expect(unknown.details.get('port:port-a')).toMatchObject({ securityGroups: null });
		// The port with the missing group keeps its other group; only the unresolved one is unknown.
		expect(missing.policyKnown).toBe(false);
		expect(missing.missingGroupIds).toEqual(['missing']);
		expect(sgIds(missing.scene)).toEqual(['sg:port-a:ssh', 'sg:port-a:missing']);
		expect(missing.scene.nodes.find(node => node.id === 'sg:port-a:missing')).toMatchObject({ status: 'unknown', sublabel: t('network.iso.groupMissing') });
		expect(missing.details.get('sg:port-a:missing')).toMatchObject({ kind: 'security-group', missing: true, rules: [] });
	});

	it('shows attached volumes and file shares behind the instance and keeps unobserved storage out of the scene', () => {
		const volumes = [
			{ volume_id: 'vol-data', name: 'data', device: '/dev/vdb', size: 100, status: 'in-use', delete_on_termination: false },
			{ volume_id: 'vol-root', name: null, device: '/dev/vda', size: 20, status: 'in-use', delete_on_termination: true },
		];
		const shares = [
			{ file_storage_id: 'share-1', name: 'logs', share_proto: 'nfs', status: 'available', access_level: 'rw', association_state: 'tracked' },
			{ file_storage_id: 'share-2', name: null, share_proto: null, status: 'unknown', association_state: 'unknown' },
			{ file_storage_id: 'share-3', name: 'old', share_proto: 'cephfs', status: 'available', association_state: 'mismatch' },
		];
		const { scene, details } = buildInstanceIsoScene({ ...input, volumes, shares });
		expect(scene.nodes.filter(node => node.kind === 'volume').map(node => node.id)).toEqual(['volume:vol-root', 'volume:vol-data']);
		expect(scene.nodes.find(node => node.id === 'volume:vol-root')).toMatchObject({
			label: 'vol-root', sublabel: `${t('network.iso.sizeGb', { size: 20 })} · /dev/vda`, status: 'ok',
			badges: [{ text: t('network.iso.deleteWithInstance') }],
		});
		expect(scene.nodes.find(node => node.id === 'volume:vol-data')).toMatchObject({ label: 'data', badges: undefined });
		expect(scene.edges.filter(edge => edge.id.startsWith('volume-link:')).every(edge => edge.from === 'instance:vm' && edge.flow === false)).toBe(true);
		expect(scene.nodes.find(node => node.id === 'share:share-1')).toMatchObject({ kind: 'file-share', sublabel: 'NFS · rw', status: 'ok', badges: undefined });
		expect(scene.nodes.find(node => node.id === 'share:share-2')).toMatchObject({ status: 'unknown', label: 'share-2' });
		expect(scene.nodes.find(node => node.id === 'share:share-3')?.badges).toEqual([expect.objectContaining({ text: t('network.iso.shareMismatch') })]);
		expect(details.get('volume:vol-data')).toMatchObject({ kind: 'volume', volume: volumes[0] });
		expect(details.get('share:share-3')).toMatchObject({ kind: 'share', share: shares[2] });
		// Storage is placed behind the instance, away from every network slab.
		for (const node of scene.nodes.filter(item => item.kind === 'volume' || item.kind === 'file-share')) {
			expect(node.x + node.y).toBeLessThan(0);
		}
		const unobserved = buildInstanceIsoScene(input);
		expect(unobserved.scene.nodes.some(node => node.kind === 'volume' || node.kind === 'file-share')).toBe(false);
		const none = buildInstanceIsoScene({ ...input, volumes: [], shares: [] });
		expect(none.scene.nodes.some(node => node.kind === 'volume' || node.kind === 'file-share')).toBe(false);
	});
});
