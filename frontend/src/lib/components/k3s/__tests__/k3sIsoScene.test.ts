import { describe, expect, it } from 'vitest';
import type { K3sNodegroup, ServiceInfo } from '$lib/types/k3s';
import type { PortInfo } from '$lib/types/networks';
import type { SecurityGroup } from '$lib/types/securityGroup';
import { layoutScene } from '$lib/components/iso/layout';
import { buildK3sIsoScene, k3sSecurityGroupNodeOf, K3S_GRID_PAGE_SIZE, listK3sGridNodes, type K3sGridNode } from '../k3sIsoScene';

type Input = Parameters<typeof buildK3sIsoScene>[0];
const node: K3sGridNode = { id: 'server', role: 'server', name: 'cp-1' };
const port = (id: string, security_group_ids: string[] | undefined, address = '10.0.0.3'): PortInfo => ({
	id, name: null, status: 'ACTIVE', device_owner: 'compute:nova', project_id: 'project', network_id: 'lan',
	fixed_ips: [{ ip_address: address }], security_group_ids,
});
const ssh: SecurityGroup = { id: 'ssh', name: 'SSH', description: '', rules: [
	{ id: 'ingress-22', direction: 'ingress', protocol: 'tcp', port_range_min: 22, port_range_max: 22,
		ethertype: 'IPv4', remote_ip_prefix: '10.0.0.0/24', remote_group_id: null },
] };
const lb: ServiceInfo = { namespace: 'default', name: 'ingress', type: 'LoadBalancer', cluster_ip: '10.43.1.9',
	external_ips: ['192.0.2.9'], ports: [{ name: 'https', protocol: 'TCP', port: 443, target_port: 'https', node_port: 30443 }],
	selector: {}, created_at: '',
};
const input: Input = {
	cluster: { api_address: 'https://192.0.2.4:6443', server_ip: '10.0.0.3' },
	nodes: [node], nodeData: {}, networks: [{ id: 'lan', name: 'Cluster LAN' }], floating: null, services: null,
	labels: { server: 'Control plane', agent: 'Worker', api: 'API', services: 'Services',
		volume: { boot: 'Boot', csi: 'CSI', attached: 'Attached' }, csiShare: 'CSI share', rate: () => 'Measured',
		ruleCount: count => `${count} rules`, moreSources: count => `${count} additional sources`,
		ingress: 'Ingress', egress: 'Egress', missingGroup: 'Rules unavailable' },
};
const id = (...parts: string[]) => JSON.stringify(parts);

describe('Drover grid scene', () => {
	it('keeps rules on the specific Neutron port, not the network or another port', () => {
		const { scene, details } = buildK3sIsoScene({ ...input, nodeData: {
			server: { policy: { ports: [port('public', ['ssh', 'missing']), port('private', [], '10.0.0.4')], security_groups: [ssh] } },
		} });
		const groupId = 'sg:public:ssh';
		expect(scene.edges.filter(edge => edge.to === groupId)).toMatchObject([{ from: id('port', 'server', 'public'), flow: false }]);
		expect(scene.edges.filter(edge => edge.to === id('network', 'lan'))).toHaveLength(2);
		expect(details.get(groupId)).toMatchObject({ kind: 'group', portId: 'public', group: { rules: [{ protocol: 'tcp', portRangeMin: 22 }] } });
		expect(details.get('sg:public:missing')).toMatchObject({ group: { rules: null } });
		const groupNode = scene.nodes.find(item => item.id === groupId);
		expect(groupNode).toMatchObject({ platformId: id('network', 'lan'), sublabel: '1 rules' });
		expect(groupNode?.status).toBeUndefined();
		expect(scene.nodes.find(item => item.id === 'sg:public:missing')).toMatchObject({ sublabel: 'Rules unavailable' });
		expect(details.get(id('port', 'server', 'private'))).toMatchObject({ port: { groups: [] } });
	});

	it('puts the control-plane and worker ports and their group chips inside the same slab', () => {
		const worker: K3sGridNode = { id: 'worker', role: 'agent' };
		const { scene, details } = buildK3sIsoScene({ ...input, nodes: [worker, node], nodeData: {
			server: { policy: { ports: [port('one', ['ssh'])], security_groups: [ssh] } },
			worker: { policy: { ports: [port('two', ['ssh'])], security_groups: [ssh] } },
		} });
		const lan = scene.platforms.find(item => item.style === 'slab')!;
		expect(scene.platforms.filter(item => item.style === 'slab')).toHaveLength(1);
		expect(details.get(lan.id)).toMatchObject({ members: [{ vm: { id: 'server' } }, { vm: { id: 'worker' } }] });
		const members = scene.nodes.filter(item => item.platformId === lan.id);
		expect(members.map(item => item.id)).toEqual([id('port', 'server', 'one'), 'sg:one:ssh', id('port', 'worker', 'two'), 'sg:two:ssh']);
		expect(members.every(item => item.x > lan.x && item.x < lan.x + lan.w && item.y > lan.y && item.y < lan.y + lan.h)).toBe(true);
		expect(scene.edges.filter(edge => members.some(item => item.id === edge.to) && edge.flow)).toMatchObject([
			{ from: id('vm', 'server'), to: id('port', 'server', 'one') },
			{ from: id('vm', 'worker'), to: id('port', 'worker', 'two') },
		]);
	});

	it('expands only the selected port group, caps sources, and retains the fan when a source is selected', () => {
		const group = { ...ssh, rules: Array.from({ length: 6 }, (_, i) => ({
			...ssh.rules[0], id: `src-${i}`, remote_ip_prefix: `10.0.${i}.0/24`,
		})) };
		const data = { ...input, nodeData: { server: { policy: { ports: [port('one', ['ssh']), port('two', ['ssh'])], security_groups: [group] } } } };
		expect(buildK3sIsoScene(data).scene.nodes.some(item => item.id.includes('>'))).toBe(false);
		const selected = buildK3sIsoScene({ ...data, expandedSecurityGroup: 'sg:one:ssh' });
		const sources = selected.scene.nodes.filter(item => item.id.includes('>'));
		expect(sources).toHaveLength(4);
		expect(sources.every(item => item.id.startsWith('sg:one:ssh>'))).toBe(true);
		expect(sources.at(-1)).toMatchObject({ id: 'sg:one:ssh>more', label: '3 additional sources' });
		expect(selected.details.get('sg:one:ssh>more')).toMatchObject({ rules: expect.arrayContaining([
			expect.objectContaining({ remote: { kind: 'cidr', value: '10.0.5.0/24' } }),
		]) });
		expect(selected.scene.edges.filter(edge => edge.kind === 'ingress')).toMatchObject(sources.map(source => ({ from: source.id, to: 'sg:one:ssh', flow: false })));
		expect(k3sSecurityGroupNodeOf(sources[0].id)).toBe('sg:one:ssh');
		expect(buildK3sIsoScene({ ...data, expandedSecurityGroup: sources[0].id })).toEqual(selected);
	});

	it.each([3, 4])('separates a full Services zone from the rest of a %i-VM diagram', (count) => {
		const nodes: K3sGridNode[] = [node, ...Array.from({ length: count - 1 }, (_, i): K3sGridNode => ({ id: `worker-${i}`, role: 'agent' }))];
		const nodeData = Object.fromEntries(nodes.map((vm, i) => [vm.id, {
			policy: { ports: [port(`port-${i}`, ['ssh', 'default'], `10.0.0.${i + 3}`)], security_groups: [ssh, { ...ssh, id: 'default' }] },
			volumes: Array.from({ length: 3 }, (_, j) => ({ volume_id: `vol-${i}-${j}`, name: `disk-${j}`, status: 'in-use' })),
			shares: Array.from({ length: 2 }, (_, j) => ({ file_storage_id: `share-${i}-${j}`, name: `NFS share ${j}`, share_proto: 'NFS', status: 'available' })),
		}]));
		const services = Array.from({ length: 6 }, (_, i) => ({ ...lb, name: `svc-${i}` }));
		const { scene } = buildK3sIsoScene({ ...input, nodes, nodeData, services: { items: services, failedNamespaces: [] } });
		const zone = scene.platforms.find(item => item.id === 'services')!;
		const inside = scene.nodes.filter(item => item.kind === 'k8s-service');
		const outside = scene.nodes.filter(item => item.kind !== 'k8s-service');
		expect(inside).toHaveLength(6);
		expect(outside.some(item => item.x >= zone.x && item.x <= zone.x + zone.w && item.y >= zone.y && item.y <= zone.y + zone.h)).toBe(false);
		for (const [index, service] of inside.entries()) {
			for (const other of [...outside, ...inside.slice(index + 1)]) {
				expect(Math.hypot(service.x - other.x, service.y - other.y)).toBeGreaterThanOrEqual(1.19);
			}
		}
		if (count === 3) {
			const { bounds } = layoutScene(scene);
			expect(Math.min((1040 - 20) / bounds.w, (416 - 20) / bounds.h)).toBeGreaterThanOrEqual(0.45);
		}
	});

	it('links the API only to the observed address match without claiming Service reachability', () => {
		const floating = [{ id: 'fip', floating_ip_address: '192.0.2.4', fixed_ip_address: '10.0.0.3', port_id: 'public', status: 'ACTIVE' }];
		const { scene, details } = buildK3sIsoScene({ ...input, floating, services: { items: [lb], failedNamespaces: ['restricted'] },
			nodeData: { server: { policy: { ports: [port('public', [])], security_groups: [] } } },
		});
		expect(scene.edges.filter(edge => edge.from === 'api')).toMatchObject([{ to: id('floating', 'fip'), flow: true }]);
		expect(details.get('api')).toMatchObject({ matchesPort: true });
		expect(details.get(id('service', 'default', 'ingress'))).toMatchObject({ item: lb });
		expect(details.get('services')).toMatchObject({ catalog: { failedNamespaces: ['restricted'] } });
		expect(scene.edges.some(edge => edge.from.includes('service') || edge.to.includes('service'))).toBe(false);
		expect(buildK3sIsoScene(input).details.get('api')).toMatchObject({ matchesPort: false });
	});

	it('distinguishes likely boot, name and metadata CSI hints, and ordinary attached volumes', () => {
		const volumes = [
			{ volume_id: 'a', name: 'k3s-server-root', device: '/dev/vda' },
			{ volume_id: 'b', name: 'pvc-431', device: '/dev/vdb' },
			{ volume_id: 'c', name: 'renamed', metadata: { 'csi.storage.k8s.io/pv/name': 'pv-1' } },
			{ volume_id: 'd', name: 'manual', device: '/dev/vdc' },
		];
		const shares = [{ file_storage_id: 'share', name: 'pvc-share', share_proto: 'NFS', status: 'available' }];
		const { details } = buildK3sIsoScene({ ...input, nodeData: { server: { instance: { name: 'node', status: 'ACTIVE', image_id: null }, volumes, shares } } });
		expect(details.get(id('vm', 'server'))).toMatchObject({ volumes: volumes.map((item, i) => ({ item, classification: ['boot', 'csi', 'csi', 'attached'][i] })) });
		expect(details.get(id('share', 'server', 'share'))).toMatchObject({ share: { csiHint: true, item: { share_proto: 'NFS' } } });
		const imageBoot = buildK3sIsoScene({ ...input, nodeData: { server: { instance: { name: 'node', status: 'ACTIVE', image_id: 'image' }, volumes } } });
		expect(imageBoot.details.get(id('volume', 'server', 'a'))).toMatchObject({ volume: { classification: 'attached' } });
	});

	it('retains the VM and Drover ports when storage, policy and traffic fail', () => {
		const { scene, details } = buildK3sIsoScene({ ...input, nodeData: { server: {
			policy: null, volumes: null, shares: [], traffic: null,
			interfaces: [{ vm_id: 'server', port_id: 'primary', net_id: 'lan', fixed_ips: [{ ip_address: '10.0.0.3' }], is_primary: true, node_role: 'server' }],
		} } });
		expect(details.get(id('vm', 'server'))).toMatchObject({ volumes: null, shares: [], traffic: null, ports: [{ id: 'primary', groups: null, floating: null }] });
		expect(scene.nodes.find(item => item.kind === 'instance')).toMatchObject({ status: 'unknown', badges: undefined });
		expect(scene.nodes.some(item => item.kind === 'security-group' || item.kind === 'volume')).toBe(false);
	});

	it('orders compute and children deterministically and bounds rendered counts without dropping inspector data', () => {
		const nodes: K3sGridNode[] = [node, ...Array.from({ length: 20 }, (_, i): K3sGridNode => ({ id: `agent-${i}`, role: 'agent' }))];
		const ports = Array.from({ length: 10 }, (_, i) => port(`port-${i}`, ['ssh', 'a', 'b', 'c']));
		const services = Array.from({ length: 30 }, (_, i) => ({ ...lb, name: `svc-${i}` }));
		const make = (orderedNodes: K3sGridNode[], orderedPorts: PortInfo[], orderedServices: ServiceInfo[]) => buildK3sIsoScene({ ...input,
			nodes: orderedNodes, services: { items: orderedServices, failedNamespaces: [] },
			nodeData: { server: { policy: { ports: orderedPorts, security_groups: [ssh] } } },
		});
		const actual = make(nodes, ports, services);
		const reversed = make([...nodes].reverse(), [...ports].reverse(), [...services].reverse());
		expect(actual).toEqual(reversed);
		expect(actual.scene.nodes.filter(item => item.kind === 'instance')).toHaveLength(K3S_GRID_PAGE_SIZE);
		expect(actual.scene.nodes.filter(item => item.kind === 'port')).toHaveLength(3);
		expect(actual.scene.nodes.filter(item => item.kind === 'k8s-service')).toHaveLength(6);
		expect(new Set(actual.scene.nodes.filter(item => item.kind === 'instance').map(item => item.x)).size).toBe(2);
		expect(actual.hiddenResources).toBeGreaterThan(0);
		expect(actual.details.get(id('vm', 'server'))).toMatchObject({ ports: expect.arrayContaining([expect.objectContaining({ id: 'port-9' })]) });
		expect(actual.details.get('services')).toMatchObject({ catalog: { items: expect.arrayContaining([expect.objectContaining({ name: 'svc-29' })]) } });
	});

	it('includes secondary control planes observed in nodegroups without duplicating the primary VM', () => {
		const group: K3sNodegroup = {
			id: 'group', cluster_id: 'cluster', name: 'servers', role: 'server', node_count: 2,
			flavor_id: null, image_id: null, labels: {}, taints: [], is_default: true,
			stampede_enabled: false, min_size: 2, max_size: 2, stampede_state: {}, created_at: null, updated_at: null,
			vms: [{ vm_id: 'server', name: 'first', status: 'ACTIVE' }, { vm_id: 'second', name: 'second', status: 'BUILD' }],
		};
		expect(listK3sGridNodes({ server_vm_id: 'server', agent_vm_ids: ['worker'] }, [group])).toMatchObject([
			{ id: 'second', role: 'server', status: 'BUILD' }, { id: 'server', role: 'server', name: 'first' }, { id: 'worker', role: 'agent' },
		]);
	});
});
