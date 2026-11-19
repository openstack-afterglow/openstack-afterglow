import { getStatusLabel, getStatusStyle } from '$lib/config/statusColors';
import { t } from '$lib/i18n/ns/instance';
import type { Instance } from '$lib/types/compute';
import type { StorageAttachment, VolumeAttachment } from '$lib/types/instanceStorage';
import type { FloatingIpDetail, NetworkInfo, PortInfo } from '$lib/types/networks';
import { buildSecurityGroupUnion, type SecurityGroupUnionGroup, type SecurityGroupUnionRow } from '$lib/utils/securityGroupUnion';
import type { IsoNode, IsoScene, IsoStatus, IsoTone } from '../iso/types';

interface InstanceIsoInput {
	instance: Pick<Instance, 'id' | 'name' | 'status'>;
	ports: readonly PortInfo[];
	networks: readonly NetworkInfo[];
	floatingIps: readonly FloatingIpDetail[];
	/**
	 * Security groups are applied per port. Null means the authoritative per-port policy is not ready;
	 * never use cached rules in this case.
	 */
	policy: { groups: readonly SecurityGroupUnionGroup[]; portGroupIds: ReadonlyMap<string, readonly string[]> } | null;
	/** Null means attached volumes were not observed; an empty list is an observed "none". */
	volumes: readonly VolumeAttachment[] | null;
	/** Null means file-share associations were not observed; an empty list is an observed "none". */
	shares: readonly StorageAttachment[] | null;
	waygateLocked: boolean;
	/** Node id of a security group (or one of its rule nodes) whose remote sources are drawn. */
	expandedSecurityGroup?: string | null;
}

export type InstanceIsoDetail =
	| { kind: 'port'; label: string; port: PortInfo; network?: string; securityGroups: readonly string[] | null }
	| { kind: 'network'; label: string; ports: readonly PortInfo[] }
	| { kind: 'security-group'; label: string; groupId: string; ports: readonly PortInfo[]; rules: SecurityGroupUnionRow[]; missing: boolean; internetOpen: boolean }
	| { kind: 'rules'; label: string; rules: SecurityGroupUnionRow[] }
	| { kind: 'floating'; label: string; addresses: readonly FloatingIpDetail[] }
	| { kind: 'volume'; label: string; volume: VolumeAttachment }
	| { kind: 'share'; label: string; share: StorageAttachment };

const EGRESS_DETAIL_LIMIT = 3;
const INGRESS_DETAIL_LIMIT = 3;
const STORAGE_STEP = 0.95;

function resourceStatus(status: string): IsoStatus {
	const { tone, pulse } = getStatusStyle(status);
	if (pulse) return 'pending';
	if (tone === 'success') return 'ok';
	if (tone === 'danger') return 'error';
	if (tone === 'warning') return 'warning';
	return ['DOWN', 'OFFLINE', 'SHUTOFF', 'STOPPED', 'PAUSED', 'SUSPENDED'].includes(status?.toUpperCase()) ? 'off' : 'unknown';
}

function compareId(a: { id: string }, b: { id: string }) {
	return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

function shortId(id: string) {
	return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

/** Id of the security-group node a selected id belongs to (the node itself or one of its rule sources). */
export function securityGroupNodeOf(id: string | null | undefined): string | null {
	return id?.startsWith('sg:') ? id.split('>')[0] : null;
}

function isAnyCidr(value: string) {
	return value === '0.0.0.0/0' || value === '::/0';
}

export function buildInstanceIsoScene({ instance, ports, networks, floatingIps, policy, volumes, shares, waygateLocked, expandedSecurityGroup }: InstanceIsoInput) {
	const instanceId = `instance:${instance.id}`;
	const details = new Map<string, InstanceIsoDetail>();
	const groupsById = new Map(policy?.groups.map(group => [group.id, group]));
	const missingGroupIds = new Set<string>();
	const scene: IsoScene = {
		nodes: [{ id: instanceId, kind: 'instance', label: instance.name || instance.id, x: 0, y: 0,
			tone: 'accent', status: resourceStatus(instance.status), interactive: false,
			badges: waygateLocked ? [{ text: t('network.iso.managed'), tone: 'warning' }] : undefined }],
		platforms: [],
		edges: [],
		legend: [
			{ kind: 'platform', label: t('network.network'), tone: 'internal' },
			{ kind: 'node', label: t('network.securityGroups'), tone: 'shared' },
		],
	};

	const catalog = new Map(networks.map(network => [network.id, network]));
	const networksByPort = new Map<string, PortInfo[]>();
	const portsById = new Map(ports.map(port => [port.id, port]));
	for (const port of [...ports].sort(compareId)) {
		// Keep a port with no reported network separate; do not manufacture a network slab for it.
		const key = port.network_id ? `network:${port.network_id}` : `unmapped:${port.id}`;
		const members = networksByPort.get(key);
		if (members) members.push(port);
		else networksByPort.set(key, [port]);
	}

	const groupIdsOf = (port: PortInfo) => {
		const ids = policy?.portGroupIds.get(port.id);
		if (!ids) return null;
		return [...new Set(ids)].sort((a, b) => {
			const left = groupsById.get(a)?.name || a;
			const right = groupsById.get(b)?.name || b;
			return left < right ? -1 : left > right ? 1 : a < b ? -1 : 1;
		});
	};

	const expandedNode = securityGroupNodeOf(expandedSecurityGroup);
	let networkIndex = 0;
	let networkDepth = 0;
	let rowDepth = 0;
	let slabExtent = 0;
	for (const [id, members] of networksByPort) {
		const networkId = members[0].network_id;
		const network = networkId ? catalog.get(networkId) : undefined;
		const label = network?.name || networkId;
		const tone: IsoTone = network?.is_external ? 'external' : network?.is_shared ? 'shared' : 'internal';
		const right = networkIndex % 2 === 0;
		// Security groups sit on the slab beside their port, in a column on the side facing away from the instance.
		const widest = Math.max(0, ...members.map(port => groupIdsOf(port)?.length ?? 0));
		const extra = widest ? 0.2 + 0.75 * widest : 0;
		const w = 1.25 + extra;
		const x = networkDepth + (right ? 1.3 : 0.05 - extra);
		const y = networkDepth + (right ? 0.05 : 1.3);
		const h = 1.2 + (members.length - 1) * 0.95;
		const portX = x + (right ? 0.57 : extra + 0.57);
		if (label) {
			const kind = network?.is_external ? 'external-network' : network?.is_shared ? 'shared-network'
				: network?.is_external === false && network.is_shared === false ? 'internal-network' : undefined;
			scene.platforms.push({ id, label, x, y, w, h, style: 'slab', tone, kind });
			slabExtent = Math.max(slabExtent, (x + y + w + h) / 2);
			details.set(id, { kind: 'network', label, ports: members });
		}
		for (const [index, port] of members.entries()) {
			const portId = `port:${port.id}`;
			const address = port.fixed_ips.map(ip => ip.ip_address).join(', ');
			const portLabel = port.name || t('network.iso.port');
			const down = port.status === 'DOWN';
			const status = down ? undefined : resourceStatus(port.status);
			const portY = y + 0.37 + index * 0.95;
			const platformId = label ? id : undefined;
			const groupIds = groupIdsOf(port);
			scene.nodes.push({ id: portId, label: portLabel, sublabel: address || undefined,
				ariaLabel: [portLabel, address, port.id].filter(Boolean).join(', '), kind: 'port', tone,
				x: portX, y: portY, size: 'sm', platformId, status,
				badges: port.status ? [{ text: getStatusLabel(port.status), tone: getStatusStyle(port.status).tone }] : undefined });
			scene.edges.push({ id: `interface:${port.id}`, from: instanceId, to: portId, kind: 'link', tone, flow: true });
			details.set(portId, { kind: 'port', label: portLabel, port, network: label,
				securityGroups: groupIds?.map(groupId => groupsById.get(groupId)?.name || groupId) ?? null });

			for (const [column, groupId] of (groupIds ?? []).entries()) {
				const group = groupsById.get(groupId);
				const nodeId = `sg:${port.id}:${groupId}`;
				const name = group?.name || groupId;
				if (!group) missingGroupIds.add(groupId);
				const rows = group ? buildSecurityGroupUnion([group], [groupId]).rows : [];
				const internetOpen = !!group?.rules.some(rule => rule.direction === 'ingress' && !rule.remote_group_id
					&& isAnyCidr(rule.remote_ip_prefix ?? (rule.ethertype === 'IPv6' ? '::/0' : '0.0.0.0/0')));
				const sgX = portX + (right ? 0.82 + column * 0.75 : -0.82 - column * 0.75);
				scene.nodes.push({ id: nodeId, kind: 'security-group', label: name, tone: 'shared', size: 'sm', platformId,
					sublabel: group ? t('network.iso.rulesCount', { count: rows.length }) : t('network.iso.groupMissing'),
					ariaLabel: [name, group ? t('network.iso.rulesCount', { count: rows.length }) : t('network.iso.groupMissing'),
						`${portLabel}${address ? ` ${address}` : ''}`].join(', '),
					status: group ? undefined : 'unknown',
					badges: internetOpen ? [{ text: t('network.iso.internetOpen'), tone: 'warning' }] : undefined,
					x: sgX, y: portY });
				scene.edges.push({ id: `sg-link:${nodeId}`, from: portId, to: nodeId, kind: 'link', tone: 'shared', flow: false });
				details.set(nodeId, { kind: 'security-group', label: name, groupId, ports: [port], rules: rows, missing: !group, internetOpen });
				if (!group || expandedNode !== nodeId) continue;

				// Remote sources of the selected group, drawn beyond the slab edge on the group's side.
				const ingress = new Map<string, SecurityGroupUnionRow[]>();
				const outgoing: SecurityGroupUnionRow[] = [];
				for (const row of rows) {
					if (row.direction === 'ingress') {
						const key = JSON.stringify([row.ethertype, row.remote.kind, row.remote.value]);
						const bucket = ingress.get(key);
						if (bucket) bucket.push(row);
						else ingress.set(key, [row]);
					} else if (row.direction === 'egress') outgoing.push(row);
				}
				const sources = [...ingress].map(([key, rules]) => ({ id: `${nodeId}>source:${key}`, rules }));
				const shownIngress = sources.slice(0, INGRESS_DETAIL_LIMIT + (sources.length === INGRESS_DETAIL_LIMIT + 1 ? 1 : 0));
				const hiddenIngress = sources.slice(shownIngress.length);
				const groupedEgress = outgoing.length > EGRESS_DETAIL_LIMIT;
				const fan: { id: string; rules: SecurityGroupUnionRow[]; incoming: boolean; aggregate?: 'more' | 'egress' }[] = shownIngress.map(source => ({ ...source, incoming: true }));
				if (hiddenIngress.length) fan.push({ id: `${nodeId}>more`, rules: hiddenIngress.flatMap(source => source.rules), incoming: true, aggregate: 'more' });
				if (groupedEgress) fan.push({ id: `${nodeId}>egress`, rules: outgoing, incoming: false, aggregate: 'egress' });
				else for (const row of outgoing) fan.push({ id: `${nodeId}>rule:${row.key}`, rules: [row], incoming: false });
				const edgeX = right ? x + w + 0.6 : x - 0.6;
				for (const [slot, item] of fan.entries()) {
					const row = item.rules[0];
					const all = row.remote.kind === 'cidr' && isAnyCidr(row.remote.value);
					const internet = all && item.incoming && !item.aggregate;
					const kind: IsoNode['kind'] = item.aggregate ? 'cidr' : internet ? 'internet' : row.remote.kind === 'group' ? 'security-group' : 'cidr';
					const remoteLabel = item.aggregate === 'more' ? t('network.iso.moreSources', { count: hiddenIngress.length })
						: item.aggregate === 'egress' ? t('securityGroupUnion.direction.egress')
						: internet ? t('network.iso.internet') : all ? t('securityGroupUnion.any')
						: row.remote.kind === 'group' ? groupsById.get(row.remote.value)?.name ?? row.remote.value : row.remote.value;
					const sublabel = item.aggregate ? undefined : all ? row.remote.value : row.remote.kind === 'group' ? row.ethertype : undefined;
					const tone: IsoTone = item.incoming ? 'shared' : 'router';
					scene.nodes.push({ id: item.id, kind, label: remoteLabel, sublabel, tone, size: 'sm', platformId,
						ariaLabel: !item.aggregate && row.remote.kind === 'group' ? `${remoteLabel}, ${row.ethertype}, ${row.remote.value}` : undefined,
						x: edgeX, y: portY + (slot - (fan.length - 1) / 2) * 0.6 });
					const ruleLabel = item.rules.length > 1 ? t('network.iso.rulesCount', { count: item.rules.length })
						: row.protocol === null ? row.protocolLabel : `${row.protocolLabel} ${row.portLabel}`;
					scene.edges.push({ id: `edge:${item.id}`, from: item.incoming ? item.id : nodeId, to: item.incoming ? nodeId : item.id,
						directed: true, kind: item.incoming ? 'ingress' : 'egress', tone, label: ruleLabel });
					details.set(item.id, { kind: 'rules', label: remoteLabel, rules: item.rules });
				}
				if (!scene.legend!.some(entry => entry.kind === 'edge')) {
					scene.legend!.push({ kind: 'edge', label: t('securityGroupUnion.direction.ingress'), tone: 'shared' },
						{ kind: 'edge', label: t('securityGroupUnion.direction.egress'), tone: 'router' });
				}
			}
		}
		rowDepth = Math.max(rowDepth, h);
		if (++networkIndex % 2 === 0) {
			networkDepth += rowDepth + 0.3;
			rowDepth = 0;
		}
	}

	const addresses = floatingIps.filter(ip => !!ip.port_id && portsById.has(ip.port_id)).sort(compareId);
	if (addresses.length) {
		const internetId = 'floating:external';
		const label = t('network.iso.internet');
		// On the center diagonal, x + y is the depth projected toward the viewer.
		const depth = Math.max(2.29, slabExtent + 0.35);
		scene.nodes.push({ id: internetId, kind: 'internet', label, tone: 'external', x: depth, y: depth, size: 'sm' });
		details.set(internetId, { kind: 'floating', label, addresses });
		for (const ip of addresses) {
			scene.edges.push({ id: `floating:${ip.id}`, from: `port:${ip.port_id}`, to: internetId,
				kind: 'link', tone: 'external', label: ip.floating_ip_address, flow: true });
		}
	}

	// Attached storage hangs behind the instance: block volumes up-left, file shares up-right.
	// Associations are configured/observed attachments, not proof of guest mounts or data traffic.
	const attached = [...(volumes ?? [])].sort((a, b) => (a.device ?? '') < (b.device ?? '') ? -1 : (a.device ?? '') > (b.device ?? '') ? 1 : a.volume_id < b.volume_id ? -1 : 1);
	for (const [index, volume] of attached.entries()) {
		const id = `volume:${volume.volume_id}`;
		const label = volume.name || shortId(volume.volume_id);
		const sublabel = [volume.size ? t('network.iso.sizeGb', { size: volume.size }) : '', volume.device ?? ''].filter(Boolean).join(' · ') || undefined;
		scene.nodes.push({ id, kind: 'volume', label, sublabel, tone: 'info', size: 'sm', x: -1.45 - index * STORAGE_STEP, y: -0.35,
			ariaLabel: [label, sublabel, volume.volume_id].filter(Boolean).join(', '),
			status: volume.status ? resourceStatus(volume.status === 'in-use' ? 'ACTIVE' : volume.status) : 'unknown',
			badges: volume.delete_on_termination ? [{ text: t('network.iso.deleteWithInstance'), tone: 'warning' }] : undefined });
		scene.edges.push({ id: `volume-link:${volume.volume_id}`, from: instanceId, to: id, kind: 'link', tone: 'info', flow: false });
		details.set(id, { kind: 'volume', label, volume });
	}
	if (attached.length) scene.legend!.push({ kind: 'node', label: t('network.iso.volume'), tone: 'info' });

	const attachedShares = [...(shares ?? [])].sort((a, b) => a.file_storage_id < b.file_storage_id ? -1 : 1);
	for (const [index, share] of attachedShares.entries()) {
		const id = `share:${share.file_storage_id}`;
		const label = share.name || shortId(share.file_storage_id);
		const sublabel = [share.share_proto?.toUpperCase(), share.access_level].filter(Boolean).join(' · ') || undefined;
		const association = share.association_state;
		const badge = association === 'mismatch' ? { text: t('network.iso.shareMismatch'), tone: 'warning' as const }
			: association === 'untracked' ? { text: t('network.iso.shareUntracked'), tone: 'neutral' as const } : undefined;
		scene.nodes.push({ id, kind: 'file-share', label, sublabel, tone: 'shared', size: 'sm', x: -0.35, y: -1.45 - index * STORAGE_STEP,
			ariaLabel: [label, sublabel, share.file_storage_id].filter(Boolean).join(', '),
			status: association === 'unknown' || !share.status ? 'unknown' : resourceStatus(share.status === 'available' ? 'ACTIVE' : share.status),
			badges: badge ? [badge] : undefined });
		scene.edges.push({ id: `share-link:${share.file_storage_id}`, from: instanceId, to: id, kind: 'link', tone: 'shared', flow: false });
		details.set(id, { kind: 'share', label, share });
	}
	if (attachedShares.length) scene.legend!.push({ kind: 'node', label: t('network.iso.share'), tone: 'shared' });

	return { scene, details, policyKnown: policy !== null && missingGroupIds.size === 0, missingGroupIds: [...missingGroupIds].sort() };
}
