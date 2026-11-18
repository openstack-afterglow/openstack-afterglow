import { getStatusLabel, getStatusStyle } from '$lib/config/statusColors';
import { t } from '$lib/i18n/ns/instance';
import type { Instance } from '$lib/types/compute';
import type { FloatingIpDetail, NetworkInfo, PortInfo } from '$lib/types/networks';
import { buildSecurityGroupUnion, type SecurityGroupUnionGroup, type SecurityGroupUnionRow } from '$lib/utils/securityGroupUnion';
import type { IsoScene, IsoStatus, IsoTone } from '../iso/types';

interface InstanceIsoInput {
	instance: Pick<Instance, 'id' | 'name' | 'status'>;
	ports: readonly PortInfo[];
	networks: readonly NetworkInfo[];
	floatingIps: readonly FloatingIpDetail[];
	/** Null means the authoritative policy is not ready; never use cached rules in this case. */
	policy: { groups: readonly SecurityGroupUnionGroup[]; groupIds: readonly string[] } | null;
	waygateLocked: boolean;
}

export type InstanceIsoDetail =
	| { kind: 'port'; label: string; port: PortInfo; network?: string }
	| { kind: 'network'; label: string; ports: readonly PortInfo[] }
	| { kind: 'rules'; label: string; rules: SecurityGroupUnionRow[] }
	| { kind: 'floating'; label: string; addresses: readonly FloatingIpDetail[] }
	| { kind: 'policy'; label: string; groups: readonly string[] };

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

const EGRESS_DETAIL_LIMIT = 3;

export function buildInstanceIsoScene({ instance, ports, networks, floatingIps, policy, waygateLocked }: InstanceIsoInput) {
	const instanceId = `instance:${instance.id}`;
	const zoneId = 'policy';
	const details = new Map<string, InstanceIsoDetail>();
	const groupNames = new Map(policy?.groups.map(group => [group.id, group.name || group.id]));
	const union = policy && buildSecurityGroupUnion(policy.groups, policy.groupIds);
	const groups = union?.appliedGroupIds.map(id => groupNames.get(id)!) ?? [];
	const policyKnown = union !== null && union.missingGroupIds.length === 0;
	const policyLabel = t('network.securityGroups');
	const scene: IsoScene = {
		nodes: [{ id: instanceId, kind: 'instance', label: instance.name || instance.id, x: 0, y: 0,
			platformId: zoneId, tone: 'accent', status: resourceStatus(instance.status), interactive: false,
			badges: waygateLocked ? [{ text: t('network.iso.managed'), tone: 'warning' }] : undefined }],
		platforms: [{ id: zoneId, label: policyLabel, sublabel: !policyKnown ? t('network.iso.policyUnknown')
			: groups.join(', ') || t('network.none'), style: 'zone', tone: 'shared', x: -0.9, y: -0.9, w: 1.8, h: 1.9 }],
		edges: [],
		legend: [
			{ kind: 'platform', label: t('network.network'), tone: 'internal' },
			{ kind: 'edge', label: t('securityGroupUnion.direction.ingress'), tone: 'shared' },
			{ kind: 'edge', label: t('securityGroupUnion.direction.egress'), tone: 'router' },
		],
	};
	details.set(zoneId, { kind: 'policy', label: policyLabel, groups });

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
	let networkIndex = 0;
	let networkDepth = 0;
	let rowDepth = 0;
	for (const [id, members] of networksByPort) {
		const networkId = members[0].network_id;
		const network = networkId ? catalog.get(networkId) : undefined;
		const label = network?.name || networkId;
		const tone: IsoTone = network?.is_external ? 'external' : network?.is_shared ? 'shared' : 'internal';
		const right = networkIndex % 2 === 0;
		const x = networkDepth + (right ? 1.3 : 0.05);
		const y = networkDepth + (right ? 0.05 : 1.3);
		const h = 1.2 + (members.length - 1) * 0.95;
		if (label) {
			scene.platforms.push({ id, label, x, y, w: 1.25, h, style: 'slab', tone });
			details.set(id, { kind: 'network', label, ports: members });
		}
		for (const [index, port] of members.entries()) {
			const portId = `port:${port.id}`;
			const address = port.fixed_ips.map(ip => ip.ip_address).join(', ');
			const portLabel = port.name || t('network.iso.port');
			const status = resourceStatus(port.status);
			scene.nodes.push({ id: portId, label: portLabel, sublabel: address || undefined,
				ariaLabel: [portLabel, address, port.id].filter(Boolean).join(', '), kind: 'port', tone,
				x: x + 0.57, y: y + 0.37 + index * 0.95, size: 'sm', platformId: label ? id : undefined, status,
				badges: port.status ? [{ text: getStatusLabel(port.status), tone: getStatusStyle(port.status).tone }] : undefined });
			scene.edges.push({ id: `interface:${port.id}`, from: instanceId, to: portId, kind: 'link', tone, flow: true });
			details.set(portId, { kind: 'port', label: portLabel, port, network: label });
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
		scene.nodes.push({ id: internetId, kind: 'internet', label, tone: 'external', x: 2.7, y: 2.7, size: 'sm' });
		details.set(internetId, { kind: 'floating', label, addresses });
		for (const ip of addresses) {
			scene.edges.push({ id: `floating:${ip.id}`, from: `port:${ip.port_id}`, to: internetId,
				kind: 'link', tone: 'external', label: ip.floating_ip_address, flow: true });
		}
	}

	// As in SecurityGroupUnion, one missing applied group invalidates the entire displayed union.
	if (!policyKnown || !union || !policy) return { scene, details, policyKnown, missingGroupIds: union?.missingGroupIds ?? [] };
	const applied = new Set(union.appliedGroupIds);
	const internetVersions = new Set<string>();
	for (const group of policy.groups) {
		if (!applied.has(group.id)) continue;
		for (const rule of group.rules) {
			if (rule.direction === 'ingress' && !rule.remote_group_id && (rule.remote_ip_prefix === '0.0.0.0/0' || rule.remote_ip_prefix === '::/0')) {
				internetVersions.add(rule.ethertype);
			}
		}
	}
	const outgoing = union.rows.filter(row => row.direction === 'egress');
	const egress = t('securityGroupUnion.direction.egress');
	const groupedEgress = outgoing.length > EGRESS_DETAIL_LIMIT;
	let sourceIndex = 0;
	for (const row of union.rows) {
		const incoming = row.direction === 'ingress';
		if (!incoming && row.direction !== 'egress') continue;
		if (!incoming && groupedEgress) continue;
		const all = row.remote.kind === 'cidr' && (row.remote.value === '0.0.0.0/0' || row.remote.value === '::/0');
		const internet = all && incoming && internetVersions.has(row.ethertype);
		const kind = internet ? 'internet' : row.remote.kind === 'group' ? 'security-group' : 'cidr';
		const label = internet ? t('network.iso.internet') : all ? t('securityGroupUnion.any')
			: row.remote.kind === 'group' ? groupNames.get(row.remote.value) ?? row.remote.value : row.remote.value;
		const id = `rule:${row.key}`;
		const tone = incoming ? 'shared' : 'router';
		const side = incoming ? (sourceIndex % 3 - 1) * 0.65 : 0;
		const depth = incoming ? Math.floor(sourceIndex++ / 3) * 0.9 : outgoing.indexOf(row) * 0.9;
		scene.nodes.push({ id, kind, label, sublabel: all ? row.remote.value : undefined, tone, size: 'sm',
			x: (incoming ? -1.88 + side : -1.37) - depth, y: (incoming ? -1.88 - side : 0.6) - depth });
		scene.edges.push({ id: `edge:${id}`, from: incoming ? id : instanceId, to: incoming ? instanceId : id, directed: true,
			kind: incoming ? 'ingress' : 'egress', tone, label: row.protocol === null ? row.protocolLabel : `${row.protocolLabel} ${row.portLabel}` });
		details.set(id, { kind: 'rules', label, rules: [row] });
	}
	if (groupedEgress) {
		const id = 'egress';
		scene.nodes.push({ id, kind: 'cidr', label: egress, tone: 'router', size: 'sm', x: -1.37, y: 0.6 });
		scene.edges.push({ id: `edge:${id}`, from: instanceId, to: id, directed: true, kind: 'egress', tone: 'router',
			label: t('network.iso.rulesCount', { count: outgoing.length }) });
		details.set(id, { kind: 'rules', label: egress, rules: outgoing });
	}
	return { scene, details, policyKnown, missingGroupIds: union.missingGroupIds };
}
