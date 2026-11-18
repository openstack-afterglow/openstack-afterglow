import type { TopologyData, TopologyIpAddress, TopologyNetwork } from '$lib/types/topology';
import { packNodes, stackPlatforms } from '../iso/layout';
import type { IsoEdge, IsoNode, IsoPlatform, IsoScene, IsoStatus, IsoTone } from '../iso/types';

export const topologyPlatformId = (id: string) => `network:${id}`;
type DraftNode = Omit<IsoNode, 'x' | 'y'>;
type SceneText = { unresolvedAddress: (address: string) => string };
type ParsedAddress = { bits: 32 | 128; value: bigint };

function statusOf(status?: string | null): IsoStatus {
	switch (status) {
		case 'ACTIVE': case 'ONLINE': return 'ok';
		case 'BUILD': case 'PENDING_CREATE': case 'PENDING_UPDATE': case 'PENDING_DELETE': case 'REBUILD': case 'REBOOT': return 'pending';
		case 'DEGRADED': case 'DRAINING': return 'warning';
		case 'ERROR': return 'error';
		case 'DOWN': case 'OFFLINE': case 'SHUTOFF': case 'PAUSED': case 'SUSPENDED': case 'INACTIVE': return 'off';
		default: return 'unknown';
	}
}

function addressValue(address: string): ParsedAddress | null {
	if (!address.includes(':')) {
		if (!/^(?:\d{1,3}\.){3}\d{1,3}$/.test(address)) return null;
		const octets = address.split('.').map(Number);
		if (octets.some((octet) => octet > 255)) return null;
		return { bits: 32, value: octets.reduce((n, octet) => (n << 8n) | BigInt(octet), 0n) };
	}
	if (!/^[a-f\d:.]+$/i.test(address)) return null;
	try {
		// WHATWG URL validates and canonicalizes IPv6, including embedded IPv4 tails.
		const host = new URL(`http://[${address}]/`).hostname.slice(1, -1);
		const halves = host.split('::');
		const left = halves[0] ? halves[0].split(':') : [];
		const right = halves[1] ? halves[1].split(':') : [];
		const value = [...left, ...Array<string>(8 - left.length - right.length).fill('0'), ...right]
			.reduce((n, part) => (n << 16n) | BigInt(`0x${part}`), 0n);
		return { bits: 128, value };
	} catch {
		return null;
	}
}

function contains(address: ParsedAddress, cidr: string) {
	const [ip, prefixText, extra] = cidr.split('/');
	if (extra !== undefined || !/^\d{1,3}$/.test(prefixText ?? '')) return false;
	const network = addressValue(ip);
	const prefix = Number(prefixText);
	if (!network || network.bits !== address.bits || prefix > network.bits) return false;
	const shift = BigInt(network.bits - prefix);
	return (network.value >> shift) === (address.value >> shift);
}

/** Read-only diagram: an attachment is drawn only when the API resolves a unique endpoint. */
export function topologyIsoScene(data: TopologyData, projectId: string | null, text?: SceneText): IsoScene {
	const networks = data.networks.filter((network) => network.is_external || network.is_shared || network.project_id === projectId);
	const netById = new Map(networks.map((network) => [network.id, network]));
	const byName = new Map<string, TopologyNetwork[]>();
	const subnetToNet = new Map<string, string>();
	const scopes = new Map<string, DraftNode[]>();
	const tones = new Map<string, IsoTone>();
	const nodes: IsoNode[] = [];
	const platforms: IsoPlatform[] = [];
	const edges: IsoEdge[] = [];
	const routerBlocks: DraftNode[] = [];
	const detached: DraftNode[] = [];
	let tenantIndex = 0;
	for (const net of data.networks) {
		const group = byName.get(net.name) ?? [];
		group.push(net);
		byName.set(net.name, group);
	}
	for (const net of networks) {
		for (const subnet of net.subnet_details) subnetToNet.set(subnet.id, net.id);
		scopes.set(net.id, []);
		tones.set(net.id, net.is_external ? 'gateway' : net.is_shared ? 'shared' : tenantIndex++ % 2 ? 'internal-2' : 'internal');
	}
	function resolveAddressNetwork(addr: TopologyIpAddress) {
		if (addr.network_id) return netById.get(addr.network_id);
		const named = byName.get(addr.network_name);
		if (named?.length === 1) return netById.get(named[0].id);
		const ip = addressValue(addr.addr);
		if (!ip) return undefined;
		const matches = (named ?? data.networks).filter((network) => network.subnet_details.some((subnet) => contains(ip, subnet.cidr)));
		return matches.length === 1 ? netById.get(matches[0].id) : undefined;
	}
	function place(block: DraftNode, netId?: string | null) {
		const scope = netId ? scopes.get(netId) : undefined;
		if (!scope || !netId) detached.push(block);
		else {
			block.platformId = topologyPlatformId(netId);
			scope.push(block);
		}
	}

	for (const router of data.routers) {
		if (router.project_id !== projectId) continue;
		const gateway = router.external_gateway_network_id;
		const status = statusOf(router.status);
		const inactive = status === 'off' || status === 'error';
		routerBlocks.push({
			id: router.id, kind: 'router', tone: 'router', status, label: router.name || router.id,
			badges: [router.is_ha && 'HA', router.is_distributed && 'DVR', router.enable_snat && 'SNAT']
				.filter((value): value is string => typeof value === 'string').map((text) => ({ text, tone: 'neutral' })),
		});
		if (gateway && netById.get(gateway)?.is_external) {
			edges.push({ id: `gateway:${router.id}:${gateway}`, from: topologyPlatformId(gateway), to: router.id,
				kind: 'link', tone: 'gateway', bidirectional: true, label: router.external_gateway_ips.join(' · ') || undefined, inactive });
		}
		const ipsByNet = new Map<string, string[]>();
		for (const id of [...router.connected_subnet_ids, ...router.dvr_subnet_ids]) {
			const netId = subnetToNet.get(id);
			if (netId && netId !== gateway && !ipsByNet.has(netId)) ipsByNet.set(netId, []);
		}
		for (const ip of router.interface_ips) {
			const netId = subnetToNet.get(ip.subnet_id);
			if (!netId || netId === gateway) continue;
			const ips = ipsByNet.get(netId) ?? [];
			ips.push(ip.ip_address);
			ipsByNet.set(netId, ips);
		}
		for (const [netId, ips] of ipsByNet) {
			edges.push({ id: `router:${router.id}:${netId}`, from: router.id, to: topologyPlatformId(netId),
				kind: 'link', tone: 'router', bidirectional: true, inactive, label: [...new Set(ips)].join(' · ') || undefined });
		}
	}

	const instanceBlocks = new Map<string, DraftNode>();
	const lbBlocks = new Map<string, DraftNode>();
	const ownersByPort = new Map<string, DraftNode>();
	const ownersByFloatingAddress = new Map<string, Set<DraftNode>>();
	for (const instance of data.instances) {
		if (instance.project_id && instance.project_id !== projectId) continue;
		const block: DraftNode = { id: instance.id, kind: instance.is_database ? 'database' : 'instance',
			label: instance.name || instance.id, status: statusOf(instance.status), tone: instance.is_database ? 'internal-2' : 'internal', badges: [] };
		instanceBlocks.set(instance.id, block);
		const addressesByNet = new Map<string, string[]>();
		for (const ip of instance.ip_addresses) {
			if (ip.type === 'floating') {
				const owners = ownersByFloatingAddress.get(ip.addr) ?? new Set<DraftNode>();
				owners.add(block);
				ownersByFloatingAddress.set(ip.addr, owners);
				block.badges!.push({ text: ip.addr, tone: 'external' });
				continue;
			}
			if (ip.port_id) ownersByPort.set(ip.port_id, block);
			const net = resolveAddressNetwork(ip);
			if (!net) {
				block.badges!.push({ text: text?.unresolvedAddress(ip.addr) ?? ip.addr, tone: 'neutral' });
				continue;
			}
			const ips = addressesByNet.get(net.id) ?? [];
			ips.push(ip.addr);
			addressesByNet.set(net.id, ips);
		}
		const attachments = [...addressesByNet.keys()].sort((a, b) => Number(netById.get(a)?.is_external) - Number(netById.get(b)?.is_external) || a.localeCompare(b));
		const primary = attachments[0];
		if (primary) {
			const [first, ...remaining] = addressesByNet.get(primary)!;
			block.sublabel = first;
			for (const ip of remaining) block.badges!.push({ text: ip, tone: 'neutral' });
		}
		place(block, primary);
		for (const extra of attachments.slice(1)) {
			edges.push({ id: `nic:${instance.id}:${extra}`, from: instance.id, to: topologyPlatformId(extra),
				kind: 'link', tone: tones.get(extra) ?? 'internal', inactive: block.status === 'off' || block.status === 'error', label: addressesByNet.get(extra)?.join(' · ') });
		}
	}

	for (const lb of data.load_balancers ?? []) {
		if (lb.project_id && lb.project_id !== projectId) continue;
		const status = statusOf(lb.provisioning_status);
		const block: DraftNode = { id: lb.id, kind: 'loadbalancer', tone: 'accent', label: lb.name || lb.id,
			sublabel: lb.vip_address ?? undefined, status: status === 'ok' ? statusOf(lb.operating_status) : status, badges: [] };
		lbBlocks.set(lb.id, block);
		if (lb.vip_port_id) ownersByPort.set(lb.vip_port_id, block);
		const netId = lb.vip_network_id && netById.has(lb.vip_network_id) ? lb.vip_network_id : lb.vip_subnet_id ? subnetToNet.get(lb.vip_subnet_id) : undefined;
		place(block, netId);
		for (const member of lb.members) {
			const instance = member.server_id ? instanceBlocks.get(member.server_id) : undefined;
			const to = instance?.id ?? `member:${lb.id}:${member.id}`;
			const status = statusOf(member.status);
			if (!instance) {
				place({ id: to, kind: 'port', tone: 'neutral', size: 'sm', label: member.address, status, interactive: false },
					member.subnet_id ? subnetToNet.get(member.subnet_id) : undefined);
			}
			edges.push({ id: `member-link:${lb.id}:${member.id}`, from: lb.id, to, kind: 'flow', tone: 'accent',
				directed: true, inactive: status === 'off' || status === 'error', label: String(member.protocol_port) });
		}
	}

	const reportedFloatingAddresses = new Set<string>();
	for (const fip of data.floating_ips) {
		if (fip.project_id && fip.project_id !== projectId) continue;
		reportedFloatingAddresses.add(fip.floating_ip_address);
		const external = fip.floating_network_id && netById.get(fip.floating_network_id)?.is_external ? fip.floating_network_id : undefined;
		const directOwner = fip.instance_id ? (instanceBlocks.get(fip.instance_id) ?? lbBlocks.get(fip.instance_id)) : undefined;
		const floatingOwners = ownersByFloatingAddress.get(fip.floating_ip_address);
		const owner = directOwner ?? (fip.port_id ? ownersByPort.get(fip.port_id) : undefined)
			?? (floatingOwners?.size === 1 ? floatingOwners.values().next().value : undefined);
		const status = statusOf(fip.status);
		if (!owner) {
			place({ id: `fip:${fip.id}`, kind: 'floating-ip', tone: 'external', size: 'sm', label: fip.floating_ip_address,
				status, interactive: false }, external);
			continue;
		}
		if (!owner.badges?.some(({ text }) => text === fip.floating_ip_address)) owner.badges?.push({ text: fip.floating_ip_address, tone: 'external' });
		if (external) edges.push({ id: `fip:${fip.id}`, from: topologyPlatformId(external), to: owner.id, kind: 'flow',
			tone: 'external', directed: true, inactive: status === 'off' || status === 'error', label: fip.floating_ip_address });
	}
	const legacyEdgeIds = new Set<string>();
	for (const instance of data.instances) {
		if (!instanceBlocks.has(instance.id)) continue;
		for (const ip of instance.ip_addresses) {
			if (ip.type !== 'floating' || reportedFloatingAddresses.has(ip.addr) || !ip.network_id || !netById.get(ip.network_id)?.is_external) continue;
			const id = `fip-legacy:${instance.id}:${ip.addr}`;
			if (legacyEdgeIds.has(id)) continue;
			legacyEdgeIds.add(id);
			edges.push({ id, from: topologyPlatformId(ip.network_id), to: instance.id,
				kind: 'flow', tone: 'external', directed: true, label: ip.addr });
		}
	}

	const packed = networks.map((net) => ({ net, pack: packNodes(scopes.get(net.id)!.length) }));
	const external = packed.filter(({ net }) => net.is_external);
	const tenant = packed.filter(({ net }) => !net.is_external);
	const routerSlots = routerBlocks.map(() => ({ w: 1.6, h: 1.45 }));
	const detachedSlots = detached.length ? [packNodes(detached.length)] : [];
	const [externalOrigins, routerOrigins, tenantOrigins, detachedOrigins] = stackPlatforms([
		external.map(({ pack }) => pack), routerSlots, tenant.map(({ pack }) => pack), detachedSlots,
	]);
	function putNetworks(groups: typeof packed, origins: typeof externalOrigins) {
		for (const [i, { net, pack }] of groups.entries()) {
			const { x, y } = origins[i];
			platforms.push({ id: topologyPlatformId(net.id), label: net.name || net.id,
				sublabel: net.subnet_details.map(({ cidr }) => cidr).join(' · ') || undefined,
				tone: tones.get(net.id)!, style: 'slab', x, y, w: pack.w, h: pack.h });
			scopes.get(net.id)!.forEach((node, index) => nodes.push({ ...node, x: x + pack.positions[index].x, y: y + pack.positions[index].y }));
		}
	}
	putNetworks(external, externalOrigins);
	for (const [index, block] of routerBlocks.entries()) {
		const origin = routerOrigins[index];
		nodes.push({ ...block, x: origin.x + 0.8, y: origin.y + 0.72 });
	}
	putNetworks(tenant, tenantOrigins);
	if (detachedSlots.length) {
		const { x, y } = detachedOrigins[0];
		detached.forEach((node, index) => nodes.push({ ...node, x: x + detachedSlots[0].positions[index].x, y: y + detachedSlots[0].positions[index].y }));
	}
	return { nodes, platforms, edges };
}
