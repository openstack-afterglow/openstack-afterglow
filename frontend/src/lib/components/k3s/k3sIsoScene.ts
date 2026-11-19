import type { Instance } from '$lib/types/compute';
import type { K3sCluster, K3sInterfaceInfo, K3sNodegroup, ServiceInfo } from '$lib/types/k3s';
import type { FloatingIpDetail, NetworkInfo, PortInfo } from '$lib/types/networks';
import type { SecurityGroup } from '$lib/types/securityGroup';
import type { IsoNode, IsoPlatform, IsoScene, IsoStatus } from '$lib/components/iso/types';
import { buildSecurityGroupUnion, type SecurityGroupUnionRow } from '$lib/utils/securityGroupUnion';

export const K3S_GRID_PAGE_SIZE = 4;
const PORT_LIMIT = 3;
const VOLUME_LIMIT = 3;
const SHARE_LIMIT = 2;
const GROUP_LIMIT = 2;
const SERVICE_LIMIT = 6;
const STORAGE_STEP = 0.95;
const SOURCE_LIMIT = 3;

export type K3sGridNode = { id: string; role: 'server' | 'agent'; name?: string; status?: string };
export type K3sGridInstance = Pick<Instance, 'name' | 'status' | 'image_id'>;
export type K3sGridVolume = {
	volume_id: string; name?: string | null; status?: string; size?: number; device?: string | null;
	metadata?: Readonly<Record<string, string>>;
};
export type K3sGridShare = {
	file_storage_id: string; name: string | null; share_proto: string | null; status: string;
	state?: string; association_state?: string; exports?: string[];
};
export type K3sGridPolicy = { ports: PortInfo[]; security_groups: SecurityGroup[] };
export type K3sGridRate = { ts: number; value: number };
export type K3sGridTraffic = { rx: K3sGridRate | null; tx: K3sGridRate | null };
export type K3sGridNodeData = {
	instance: K3sGridInstance | null;
	interfaces: readonly K3sInterfaceInfo[] | null;
	policy: K3sGridPolicy | null;
	fallbackPorts: readonly PortInfo[] | null;
	volumes: readonly K3sGridVolume[] | null;
	shares: readonly K3sGridShare[] | null;
	floating: readonly FloatingIpDetail[] | null;
	traffic: K3sGridTraffic | null;
};
export type K3sGridServices = { items: readonly ServiceInfo[]; failedNamespaces: readonly string[] };
export type K3sGridVolumeClass = 'boot' | 'csi' | 'attached';

type Volume = { item: K3sGridVolume; classification: K3sGridVolumeClass };
type Share = { item: K3sGridShare; csiHint: boolean };
type Group = { id: string; name: string; rules: SecurityGroupUnionRow[] | null };
type Port = {
	id: string; networkId?: string; fixedIps: string[]; status?: string; primary?: boolean;
	groups: Group[] | null; floating: FloatingIpDetail[] | null;
};
type NetworkMember = { vm: K3sGridNode; vmLabel: string; port: Port };
type DetailBody =
	| { kind: 'vm'; vm: K3sGridNode; ports: Port[] | null; volumes: Volume[] | null; shares: Share[] | null; traffic: K3sGridTraffic | null }
	| { kind: 'port'; port: Port; vm: string; network: string | undefined }
	| { kind: 'network'; id: string; members: NetworkMember[] }
	| { kind: 'group'; group: Group; portId: string }
	| { kind: 'rules'; rules: SecurityGroupUnionRow[] }
	| { kind: 'floating'; item: FloatingIpDetail }
	| { kind: 'api'; address: string; serverIp: string | null; matchesPort: boolean }
	| { kind: 'volume'; volume: Volume; vm: string }
	| { kind: 'share'; share: Share; vm: string }
	| { kind: 'service'; item: ServiceInfo }
	| { kind: 'services'; catalog: K3sGridServices | null };
export type K3sIsoDetail = DetailBody & { label: string };

interface SceneInput {
	cluster: Pick<K3sCluster, 'api_address' | 'server_ip'>;
	nodes: readonly K3sGridNode[];
	nodeData: Readonly<Record<string, Partial<K3sGridNodeData>>>;
	networks: readonly NetworkInfo[];
	floating: readonly FloatingIpDetail[] | null;
	services: K3sGridServices | null;
	expandedSecurityGroup?: string | null;
	labels: {
		server: string; agent: string; api: string; services: string;
		volume: Record<K3sGridVolumeClass, string>;
		csiShare: string;
		rate: (traffic: K3sGridTraffic) => string;
		ruleCount: (count: number) => string;
		moreSources: (count: number) => string;
		missingGroup: string;
		ingress: string;
		egress: string;
	};
}

function compare(a: string, b: string): number {
	return a < b ? -1 : a > b ? 1 : 0;
}

function ordered<T>(values: readonly T[], key: (value: T) => string): T[] {
	return [...values].sort((a, b) => compare(key(a), key(b)));
}

function orderNodes(nodes: readonly K3sGridNode[]): K3sGridNode[] {
	return [...nodes].sort((a, b) => Number(a.role === 'agent') - Number(b.role === 'agent') || compare(a.id, b.id));
}

export function listK3sGridNodes(cluster: Pick<K3sCluster, 'server_vm_id' | 'agent_vm_ids'>, nodegroups: readonly K3sNodegroup[]): K3sGridNode[] {
	const nodes = new Map<string, K3sGridNode>();
	for (const id of cluster.agent_vm_ids) nodes.set(id, { id, role: 'agent' });
	for (const group of ordered(nodegroups, group => group.id)) {
		for (const vm of group.vms) {
			nodes.set(vm.vm_id, { id: vm.vm_id, role: group.role, name: vm.name || undefined, status: vm.status });
		}
	}
	if (cluster.server_vm_id) {
		const id = cluster.server_vm_id;
		nodes.set(id, { ...nodes.get(id), id, role: 'server' });
	}
	return orderNodes([...nodes.values()]);
}

function csiHint(name: string | null | undefined, metadata?: Readonly<Record<string, string>>): boolean {
	return Boolean(name?.startsWith('pvc-') || Object.entries(metadata ?? {}).some(([key, value]) => (
		Boolean(value) && (/^csi\.storage\.k8s\.io\//.test(key)
			|| (/^(provisioner|storage\.kubernetes\.io\/csiProvisionerIdentity)$/.test(key) && /(?:^|\.)csi(?:\.|$)/.test(value)))
	)));
}

function classifyVolumes(volumes: readonly K3sGridVolume[], instance: K3sGridInstance | null | undefined): Volume[] {
	// Nova does not expose the root mapping here. A conventional device is only a hint
	// when Nova explicitly reports volume-backed boot and only one attachment matches.
	const rootCandidates = instance?.image_id === null
		? volumes.filter(volume => /^\/dev\/(?:vd|sd|xvd)a$/.test(volume.device ?? '')) : [];
	const bootId = rootCandidates.length === 1 ? rootCandidates[0].volume_id : null;
	return ordered(volumes, volume => volume.volume_id).map(item => ({
		item,
		classification: csiHint(item.name, item.metadata) ? 'csi' : item.volume_id === bootId ? 'boot' : 'attached',
	}));
}

function collectPorts(data: Partial<K3sGridNodeData>, floating: readonly FloatingIpDetail[] | null): Port[] | null {
	const policy = data.policy;
	const observed = policy?.ports ?? data.fallbackPorts;
	const drover = data.interfaces;
	if (!observed && !drover) return null;
	const reported = new Map(drover?.map(port => [port.port_id, port]));
	const compute = new Map(observed?.map(port => [port.id, port]));
	const allGroups = policy?.security_groups ?? [];
	const groupsById = new Map(allGroups.map(group => [group.id, group]));
	const portGroups = new Map<string, Group>();
	return [...new Set([...reported.keys(), ...compute.keys()])].sort().map(id => {
		const native = compute.get(id);
		const path = reported.get(id);
		const ids = native?.security_group_ids;
		return {
			id, networkId: native?.network_id || path?.net_id,
			fixedIps: [...new Set((native?.fixed_ips ?? path?.fixed_ips ?? []).map(ip => ip.ip_address))].sort(),
			status: native?.status, primary: path?.is_primary,
			groups: ids ? [...new Set(ids)].sort().map(groupId => {
				let entry = portGroups.get(groupId);
				if (!entry) {
					const group = groupsById.get(groupId);
					entry = { id: groupId, name: group?.name || groupId,
						rules: Array.isArray(group?.rules) ? buildSecurityGroupUnion(allGroups, [groupId]).rows : null };
					portGroups.set(groupId, entry);
				}
				return entry;
			}) : null,
			floating: floating && ordered(floating.filter(ip => ip.port_id === id), ip => ip.id),
		};
	});
}

function status(value: string | null | undefined): IsoStatus {
	switch (value?.toLowerCase()) {
		case 'active': case 'available': case 'in-use': return 'ok';
		case 'building': case 'build': case 'creating': return 'pending';
		case 'down': case 'shutoff': return 'off';
		case 'error': return 'error';
		default: return 'unknown';
	}
}

function endpointHost(address: string): string | null {
	try {
		return new URL(address.includes('://') ? address : `https://${address}`).hostname.replace(/^\[|\]$/g, '');
	} catch {
		return null;
	}
}

const scopedId = (...parts: string[]) => JSON.stringify(parts);
const serviceKey = (service: ServiceInfo) => `${service.namespace}/${service.name}`;

/** Rule nodes keep their parent selected so the fan remains inspectable. */
export function k3sSecurityGroupNodeOf(id: string | null | undefined): string | null {
	return id?.startsWith('sg:') ? id.split('>')[0] : null;
}

function ruleSources(id: string, rows: SecurityGroupUnionRow[], labels: SceneInput['labels']) {
	const ingress = new Map<string, SecurityGroupUnionRow[]>();
	const egress: SecurityGroupUnionRow[] = [];
	for (const rule of rows) {
		if (rule.direction === 'egress') egress.push(rule);
		if (rule.direction !== 'ingress') continue;
		const key = JSON.stringify([rule.ethertype, rule.remote.kind, rule.remote.value]);
		const existing = ingress.get(key);
		if (existing) existing.push(rule);
		else ingress.set(key, [rule]);
	}
	const sources = [...ingress.entries()];
	const fan = sources.slice(0, SOURCE_LIMIT).map(([key, rules]) => ({
		id: `${id}>source:${key}`, rules, incoming: true, label: rules[0].remote.value,
		kind: rules[0].remote.kind === 'group' ? 'security-group' as const : 'cidr' as const,
	}));
	const hidden = sources.slice(SOURCE_LIMIT);
	if (hidden.length) fan.push({ id: `${id}>more`, rules: hidden.flatMap(([, rules]) => rules), incoming: true,
		label: labels.moreSources(hidden.length), kind: 'cidr' });
	if (egress.length > SOURCE_LIMIT) {
		fan.push({ id: `${id}>egress`, rules: egress, incoming: false, label: labels.egress, kind: 'cidr' });
	} else {
		for (const rule of egress) fan.push({ id: `${id}>rule:${rule.key}`, rules: [rule], incoming: false,
			label: rule.remote.value, kind: rule.remote.kind === 'group' ? 'security-group' : 'cidr' });
	}
	return fan;
}

export function buildK3sIsoScene(input: SceneInput) {
	const { cluster, labels } = input;
	const scene: IsoScene = { nodes: [], platforms: [], edges: [] };
	const details = new Map<string, K3sIsoDetail>();
	const portsByNetwork = new Map<string, NetworkMember[]>();
	const unmapped: NetworkMember[] = [];
	const seenPorts = new Set<string>();
	const duplicatePorts = new Set<string>();
	const networksById = new Map(input.networks.map(network => [network.id, network]));
	const networkLabel = (id: string) => networksById.get(id)?.name || id;
	let hiddenResources = 0;
	let matchesPort = false;
	const apiId = 'api';
	const apiHost = cluster.api_address ? endpointHost(cluster.api_address) : null;
	const expandedGroup = k3sSecurityGroupNodeOf(input.expandedSecurityGroup);
	const drawnFloating = new Map<string, string>();

	function add(element: IsoNode | IsoPlatform, detail: DetailBody) {
		if ('style' in element) scene.platforms.push(element);
		else scene.nodes.push(element);
		details.set(element.id, { ...detail, label: element.label });
	}
	function link(from: string, to: string, tone: IsoNode['tone'], flow = false) {
		scene.edges.push({ id: scopedId('link', from, to), from, to, kind: 'link', tone, flow });
	}
	function limited<T>(items: readonly T[] | null | undefined, limit: number) {
		hiddenResources += Math.max(0, (items?.length ?? 0) - limit);
		return items?.slice(0, limit) ?? [];
	}

	const nodes = orderNodes(input.nodes).slice(0, K3S_GRID_PAGE_SIZE);
	for (const [index, vm] of nodes.entries()) {
		const data = input.nodeData[vm.id] ?? {};
		const ports = collectPorts(data, data.floating ?? input.floating);
		const volumes = data.volumes ? classifyVolumes(data.volumes, data.instance) : null;
		const shares = data.shares ? ordered(data.shares, share => share.file_storage_id).map(item => ({ item, csiHint: csiHint(item.name) })) : null;
		const traffic = data.traffic ?? null;
		const role = vm.role === 'server' ? labels.server : labels.agent;
		const tone = vm.role === 'server' ? 'accent' : 'info';
		const secondRow = nodes.length === K3S_GRID_PAGE_SIZE && index >= 2;
		const x = secondRow ? -2.85 : -0.15;
		const y = nodes.length === K3S_GRID_PAGE_SIZE ? -1.65 + (index % 2) * 2.9 - (secondRow ? 0.95 : 0) : -1.85 + index * 2.3;
		const vmId = scopedId('vm', vm.id);
		const vmLabel = data.instance?.name || vm.name || `${role} · ${vm.id.slice(0, 8)}`;
		add({ id: vmId, kind: 'instance', label: vmLabel, sublabel: role, tone, x, y, size: 'lg',
			status: status(data.instance?.status || vm.status), badges: traffic && (traffic.rx || traffic.tx) ? [{ text: labels.rate(traffic), tone: 'info' }] : undefined,
		}, { kind: 'vm', vm, ports, volumes, shares, traffic });

		for (const port of limited(ports, PORT_LIMIT)) {
			if (seenPorts.has(port.id)) duplicatePorts.add(port.id);
			seenPorts.add(port.id);
			const member = { vm, vmLabel, port };
			if (!port.networkId) {
				unmapped.push(member);
				continue;
			}
			const members = portsByNetwork.get(port.networkId);
			if (members) members.push(member);
			else portsByNetwork.set(port.networkId, [member]);
		}

		for (const [position, volume] of limited(volumes, VOLUME_LIMIT).entries()) {
			const { item, classification } = volume;
			const id = scopedId('volume', vm.id, item.volume_id);
			add({ id, kind: 'volume', label: item.name || item.volume_id, sublabel: labels.volume[classification],
				tone: classification === 'csi' ? 'shared' : 'neutral', x: x - 1.15 - position * STORAGE_STEP, y: y - 0.2, size: 'sm', status: status(item.status),
			}, { kind: 'volume', volume, vm: vmLabel });
			link(vmId, id, 'neutral');
		}
		for (const [position, share] of limited(shares, SHARE_LIMIT).entries()) {
			const { item } = share;
			const id = scopedId('share', vm.id, item.file_storage_id);
			add({ id, kind: 'file-share', label: item.name || item.file_storage_id, sublabel: share.csiHint ? labels.csiShare : item.share_proto || undefined,
				tone: 'shared', x: x - 0.2, y: y - 1.15 - position * STORAGE_STEP, size: 'sm', status: status(item.status),
			}, { kind: 'share', share, vm: vmLabel });
			link(vmId, id, 'shared');
		}
	}

	function placePort({ vm, vmLabel, port }: NetworkMember, x: number, y: number, tone: IsoNode['tone'], slab?: IsoPlatform) {
		const vmId = scopedId('vm', vm.id);
		const portId = scopedId('port', vm.id, port.id);
		const address = port.fixedIps.join(', ');
		const label = address || port.id;
		const platformId = slab?.id;
		add({ id: portId, kind: 'port', label, tone, x, y, size: 'sm', platformId, status: port.status ? status(port.status) : undefined },
			{ kind: 'port', port, vm: vmLabel, network: slab?.label });
		link(vmId, portId, tone, true);
		// This is an explicit membership edge, not a second animated path to the network.
		if (platformId) link(portId, platformId, tone);
		if (apiHost && port.fixedIps.includes(apiHost)) {
			matchesPort = true;
			link(apiId, portId, 'external', true);
		}
		const apiFip = port.floating?.find(ip => ip.floating_ip_address === apiHost);
		const floating = limited(apiFip ? [apiFip, ...port.floating!.filter(ip => ip !== apiFip)] : port.floating, 1);
		for (const ip of floating) {
			let id = drawnFloating.get(ip.id);
			if (!id) {
				id = scopedId('floating', ip.id);
				drawnFloating.set(ip.id, id);
				add({ id, kind: 'floating-ip', label: ip.floating_ip_address, tone: 'external', x: x - 0.18, y: y - 1.15,
					size: 'sm', status: status(ip.status) }, { kind: 'floating', item: ip });
				if (apiHost === ip.floating_ip_address) {
					matchesPort = true;
					link(apiId, id, 'external', true);
				}
			}
			link(id, portId, 'external', true);
		}
		for (const [column, group] of limited(port.groups, GROUP_LIMIT).entries()) {
			const scope = duplicatePorts.has(port.id) ? `${encodeURIComponent(vm.id)}:` : '';
			const id = `sg:${scope}${encodeURIComponent(port.id)}:${encodeURIComponent(group.id)}`;
			const gx = x + 0.9 + column * 0.85;
			const sublabel = group.rules ? labels.ruleCount(group.rules.length) : labels.missingGroup;
			add({ id, kind: 'security-group', label: group.name, sublabel, tone: 'shared', size: 'sm', platformId,
				ariaLabel: [group.name, sublabel, address || port.id].join(', '), x: gx, y,
			}, { kind: 'group', group, portId: port.id });
			link(portId, id, 'shared');
			if (expandedGroup !== id || !group.rules) continue;
			const fan = ruleSources(id, group.rules, labels);
			for (const [slot, item] of fan.entries()) {
				const rule = item.rules[0];
				const edgeTone = item.incoming ? 'shared' : 'router';
				add({ id: item.id, kind: item.kind, label: item.label, tone: edgeTone, size: 'sm', platformId,
					ariaLabel: item.label === labels.egress ? item.label : `${item.incoming ? labels.ingress : labels.egress}, ${item.label}`,
					x: (slab ? slab.x + slab.w : gx + 0.4) + 0.65, y: y + (slot - (fan.length - 1) / 2) * 0.7,
				}, { kind: 'rules', rules: item.rules });
				scene.edges.push({ id: `edge:${item.id}`, from: item.incoming ? item.id : id, to: item.incoming ? id : item.id,
					kind: item.incoming ? 'ingress' : 'egress', tone: edgeTone, directed: true, flow: false,
					label: item.rules.length > 1 ? labels.ruleCount(item.rules.length)
						: rule.protocol === null ? rule.protocolLabel : `${rule.protocolLabel} ${rule.portLabel}`,
				});
			}
		}
	}

	// Keep the busiest shared network closest to the nodes and wrap smaller slabs under it.
	const networks = [...portsByNetwork.entries()].sort(([a, left], [b, right]) => right.length - left.length || compare(a, b));
	let networkY = -2.1;
	let networkX = 1;
	let rowWidth = 0;
	for (const [index, [id, members]] of networks.entries()) {
		const network = networksById.get(id);
		const kind = network?.is_external === true ? 'external-network' : network?.is_shared === true ? 'shared-network'
			: network?.is_external === false && network.is_shared === false ? 'internal-network' : undefined;
		const tone = kind === 'external-network' ? 'external' : kind === 'shared-network' ? 'shared' : kind === 'internal-network' ? 'internal' : 'neutral';
		const widest = Math.max(...members.map(({ port }) => Math.min(port.groups?.length ?? 0, GROUP_LIMIT)));
		const lane = 1.2 + widest * 0.88;
		const rows = Math.min(4, members.length);
		const w = Math.ceil(members.length / rows) * lane;
		const h = 0.9 + (rows - 1) * 1.2;
		if (index && networkY + h > 4.4) {
			networkY = -2.1;
			networkX += rowWidth + 0.45;
			rowWidth = 0;
		}
		const slab: IsoPlatform = { id: scopedId('network', id), label: networkLabel(id), kind, tone, x: networkX, y: networkY, w, h, style: 'slab' };
		add(slab, { kind: 'network', id, members });
		for (const [slot, member] of members.entries()) {
			placePort(member, slab.x + 0.55 + Math.floor(slot / rows) * lane, slab.y + 0.43 + slot % rows * 1.2, tone, slab);
		}
		rowWidth = Math.max(rowWidth, w);
		networkY += h + 0.45;
	}
	for (const [index, member] of unmapped.entries()) {
		placePort(member, 0.55 + 2.6 * Math.floor(index / 4), 2.8 + (index % 4) * 0.9, 'neutral');
	}

	if (cluster.api_address) {
		add({ id: apiId, kind: 'gateway', label: labels.api, sublabel: cluster.api_address, tone: 'external', x: 0.75, y: -3.75, size: 'sm' },
			{ kind: 'api', address: cluster.api_address, serverIp: cluster.server_ip, matchesPort });
	}

	const catalog = input.services ? { ...input.services, items: ordered(input.services.items, serviceKey), failedNamespaces: [...input.services.failedNamespaces].sort() } : null;
	const serviceItems = limited(catalog?.items, SERVICE_LIMIT);
	const serviceX = -3.3;
	const serviceY = -2.65;
	const serviceColumns = Math.min(3, serviceItems.length);
	const servicesId = 'services';
	add({ id: servicesId, label: labels.services, style: 'zone', tone: 'info', x: serviceX, y: serviceY,
		w: Math.max(1.15, serviceColumns * 1.2), h: 1 + Math.max(0, Math.ceil(serviceItems.length / 3) - 1) * 1.2 },
		{ kind: 'services', catalog });
	for (const [index, item] of serviceItems.entries()) {
		const id = scopedId('service', item.namespace, item.name);
		add({ id, kind: 'k8s-service', label: serviceKey(item), sublabel: item.type, tone: 'info', size: 'sm',
			x: serviceX + 0.55 + index % 3 * 1.2, y: serviceY + 0.55 + Math.floor(index / 3) * 1.2, platformId: servicesId,
		}, { kind: 'service', item });
	}
	return { scene, details, hiddenResources };
}
