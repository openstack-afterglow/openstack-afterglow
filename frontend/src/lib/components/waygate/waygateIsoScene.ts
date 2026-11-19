import { getStatusLabel, getStatusStyle } from '$lib/config/statusColors';
import { t } from '$lib/i18n/ns/waygate';
import type { Network } from '$lib/types/networks';
import type { WaygateClient, WaygateNetworkAttachment, WaygateServer } from '$lib/types/waygate';
import { waygateTrafficFreshnessMs } from '$lib/utils/waygateTraffic';
import type { IsoEdge, IsoScene, IsoStatus, IsoTone } from '../iso/types';

export type WaygateIsoTarget =
	| { kind: 'server' }
	| { kind: 'peer'; id: string }
	| { kind: 'peers' }
	| { kind: 'attachment'; id: number };

interface WaygateIsoInput {
	server: WaygateServer;
	clients: readonly WaygateClient[];
	attachments: readonly WaygateNetworkAttachment[];
	networks: readonly Pick<Network, 'id' | 'name' | 'is_external' | 'is_shared'>[];
	now: number;
	pollSeconds: number;
	locale: string;
}

export type WaygatePeerStatus = 'disabled' | 'unknown' | 'delayed' | 'online' | 'offline';

export function waygatePeerStatus(client: WaygateClient, now: number, pollSeconds: number): WaygatePeerStatus {
	if (!client.enabled) return 'disabled';
	if (!client.last_reported_at || typeof client.online !== 'boolean') return 'unknown';
	const reportedAt = Date.parse(client.last_reported_at);
	const freshness = waygateTrafficFreshnessMs(client.report_interval_seconds, pollSeconds);
	if (!Number.isFinite(reportedAt) || now - reportedAt > freshness) return 'delayed';
	return client.online ? 'online' : 'offline';
}

const PEER_LIMIT = 6;
const PEER_MARK: Record<WaygatePeerStatus, { status?: IsoStatus; tone: IsoTone }> = {
	disabled: { tone: 'neutral' },
	unknown: { status: 'unknown', tone: 'neutral' },
	delayed: { status: 'warning', tone: 'warning' },
	online: { status: 'ok', tone: 'success' },
	offline: { tone: 'neutral' },
};

export function buildWaygateIsoScene({ server, clients, attachments, networks, now, pollSeconds, locale }: WaygateIsoInput) {
	const serverId = `server:${server.id}`;
	const tunnelId = 'tunnel';
	const peersId = 'peers';
	const peersLabel = t('project.client.heading');
	const tunnelLabel = t('project.server.tunnelCidr');
	const encryptedLabel = t('project.iso.encrypted');
	const targets = new Map<string, WaygateIsoTarget>([[serverId, { kind: 'server' }], [tunnelId, { kind: 'server' }]]);
	const { tone: serverTone, pulse } = getStatusStyle(server.status);
	const serverStatus: IsoStatus = serverTone === 'success' ? 'ok' : serverTone === 'danger' ? 'error'
		: pulse ? 'pending' : serverTone === 'warning' ? 'warning' : 'unknown';
	const endpoint = server.endpoint_ip
		? `${server.endpoint_ip.includes(':') ? `[${server.endpoint_ip}]` : server.endpoint_ip}:${server.listen_port}` : undefined;
	const scene: IsoScene = {
		nodes: [{ id: serverId, kind: 'vpn-server', label: server.name || server.id, sublabel: endpoint,
			tone: 'accent', status: serverStatus, x: 0, y: 0, size: 'lg', platformId: tunnelId,
			badges: [
				{ text: server.status ? getStatusLabel(server.status) : t('project.status.unknown'), tone: serverTone },
				...(server.peer_count == null ? [] : [{ text: t('project.iso.reportedPeers', { count: server.peer_count }), tone: 'info' as const }]),
			] }],
		platforms: [{ id: tunnelId, label: tunnelLabel, sublabel: server.tunnel_cidr || undefined,
			style: 'slab', tone: 'shared', x: -0.79, y: -0.79, w: 1.58, h: 1.58 }],
		edges: [],
		legend: [{ kind: 'edge', label: encryptedLabel, tone: 'info' },
			{ kind: 'platform', label: t('project.network.attachedHeading'), tone: 'internal' }],
	};

	const peers = clients.filter(client => client.server_id === server.id).sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
	const observed = peers.map(client => {
		const state = waygatePeerStatus(client, now, pollSeconds);
		const handshake = client.last_handshake_at ? Date.parse(client.last_handshake_at) : NaN;
		return { client, state, handshake, inactive: serverStatus !== 'ok' || state !== 'online' || !Number.isFinite(handshake) };
	});
	const collapsed = observed.length > PEER_LIMIT;
	if (observed.length) {
		const columns = collapsed ? 1 : Math.min(2, observed.length);
		const rows = collapsed ? 1 : Math.ceil(observed.length / columns);
		const w = columns * 1.1 + 0.4;
		const h = rows * 1.1 + 0.4;
		// Leave a full label band between the client slab and the raised gateway block.
		const x = -w - 1.28, y = -h - 0.66;
		scene.platforms.push({ id: peersId, label: peersLabel, x, y, w, h, tone: 'info', style: 'slab' });
		targets.set(peersId, { kind: 'peers' });
		if (collapsed) {
			const id = 'peer-group';
			scene.nodes.push({ id, label: t('project.iso.profileCount', { count: observed.length }),
				kind: 'peer-group', tone: 'info', x: x + w / 2, y: y + h / 2, platformId: peersId });
			targets.set(id, { kind: 'peers' });
			const edge: IsoEdge = { id: `encrypted:${id}`, from: id, to: serverId,
				kind: 'tunnel', tone: 'info', label: encryptedLabel, directed: true, bidirectional: true,
				inactive: observed.every(peer => peer.inactive) };
			scene.edges.push(edge);
		} else {
			for (const [index, { client, state, handshake, inactive }] of observed.entries()) {
				const id = `peer:${client.id}`;
				const mark = PEER_MARK[state];
				const statusText = t(`project.status.${state}`);
				const time = Number.isFinite(handshake) ? new Date(handshake).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' }) : undefined;
				const timeLabel = time ? `${t('project.client.lastHandshake')}: ${time}` : undefined;
				scene.nodes.push({ id, label: client.name || client.id, sublabel: client.tunnel_ip || undefined,
					kind: 'peer', tone: 'info', status: mark.status, size: 'sm', platformId: peersId,
					x: x + 0.73 + (index % columns) * 1.1, y: y + 0.73 + Math.floor(index / columns) * 1.1,
					ariaLabel: [client.name || client.id, client.tunnel_ip, timeLabel].filter(Boolean).join(', '),
					badges: [{ text: statusText, tone: mark.tone }, ...(time ? [{ text: time, tone: 'neutral' as const }] : [])] });
				targets.set(id, { kind: 'peer', id: client.id });
				const edge: IsoEdge = { id: `encrypted:${id}`, from: id, to: serverId, kind: 'tunnel',
					tone: 'info', directed: true, bidirectional: true, inactive, label: observed.length === 1 ? encryptedLabel : undefined };
				scene.edges.push(edge);
			}
		}
	}

	const networkById = new Map(networks.map(network => [network.id, network]));
	const attached = attachments.filter(attachment => attachment.server_id === server.id).sort((a, b) => a.id - b.id);
	for (const [index, attachment] of attached.entries()) {
		const id = `attachment:${attachment.id}`;
		const network = networkById.get(attachment.network_id);
		const tone: IsoTone = network?.is_external ? 'external' : network?.is_shared ? 'shared' : 'internal';
		const kind = network && (network.is_external ? 'external-network' : network.is_shared ? 'shared-network' : 'internal-network');
		const depth = Math.floor(index / 2) * 1.45;
		const right = index % 2 === 0;
		const sublabel = [attachment.cidr, attachment.status !== 'ACTIVE' ? getStatusLabel(attachment.status) : undefined]
			.filter(Boolean).join(' · ') || undefined;
		scene.platforms.push({ id, label: network?.name || attachment.network_id, sublabel, kind,
			x: depth + (right ? 1.28 : -0.08), y: depth + (right ? -0.08 : 1.28), w: 1.33, h: 1.33, style: 'slab', tone });
		targets.set(id, { kind: 'attachment', id: attachment.id });
		const edge: IsoEdge = { id: `link:${id}`, from: serverId, to: id, kind: 'link', tone,
			label: attachment.nat_mode || undefined, flow: true, inactive: attachment.status !== 'ACTIVE' };
		scene.edges.push(edge);
	}
	return { scene, targets };
}
