import type { InterfaceCounters, ObservationState, PeerProbe, TopologyHost, TopologyTrace, TraceResult } from '$lib/types/infrastructureTopology';
import { t } from '$lib/i18n/ns/infra-topology';
import { intlLocale } from '$lib/i18n/runtime.svelte';

const byteUnits = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
export function quantity(value: number | null, key: keyof InterfaceCounters, rate = false): string {
	if (value === null || !Number.isFinite(value) || value < 0) return t('unknown');
	if (key.endsWith('bytes')) {
		const power = value < 1 ? 0 : Math.min(byteUnits.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
		return t(rate ? 'bytesRate' : 'bytes', { value: (value / 1024 ** power).toLocaleString(intlLocale(), { maximumFractionDigits: 2 }), unit: byteUnits[power] });
	}
	return t(rate ? 'packetsRate' : 'packets', { value: value.toLocaleString(intlLocale(), { maximumFractionDigits: rate ? 2 : 0 }) });
}

export const safeRate = (value: number | null): number | null => value !== null && Number.isFinite(value) && value >= 0 ? value : null;
export function nicHistory(host: TopologyHost, name: string, verified: boolean) {
	if (!verified || host.observation?.sources.counters !== 'measured') return [];
	return (host.observation.interfaces.find(nic => nic.name === name)?.history ?? []).map(sample => ({
		timestamp: sample.ts * 1000, rxRate: safeRate(sample.rates.rx_bytes), txRate: safeRate(sample.rates.tx_bytes),
	}));
}

export interface NicEvidence {
	interface: string;
	physical: { chassis: string; port: string; name: string | null }[];
	neighbors: { ip: string; mac: string | null; state: string }[];
	routes: { destination: string; gateway: string | null; metric: number | null }[];
	rxActive: boolean;
	txActive: boolean;
	rates: InterfaceCounters;
	rateState: 'fresh' | 'stale' | 'unknown';
	rxWidth: number;
	txWidth: number;
	history: { timestamp: number; rxRate: number | null; txRate: number | null }[];
}
/** Only LLDP on a classified physical NIC qualifies as physical-link evidence.
 * Neighbor/route records never imply cables or receive apportioned NIC totals.
 * Raw unqualified LLDP advertisements remain available in NicDetails. */
export function buildNicEvidence(host: TopologyHost, verified: boolean): NicEvidence[] {
	const observation = host.observation;
	if (!observation) return [];
	const fresh = verified && host.observation_state === 'fresh' && observation.sources.counters === 'measured';
	const largest = fresh ? Math.max(0, ...observation.interfaces.flatMap(nic => [safeRate(nic.rates.rx_bytes) ?? 0, safeRate(nic.rates.tx_bytes) ?? 0])) : 0;
	const width = (rate: number | null) => rate !== null && rate > 0 && largest > 0 ? 1.5 + 5 * Math.log1p(rate) / Math.log1p(largest) : 1.5;
	return observation.interfaces.map(nic => ({
		interface: nic.name,
		rates: {
			rx_bytes: fresh ? safeRate(nic.rates.rx_bytes) : null,
			tx_bytes: fresh ? safeRate(nic.rates.tx_bytes) : null,
			rx_packets: fresh ? safeRate(nic.rates.rx_packets) : null,
			tx_packets: fresh ? safeRate(nic.rates.tx_packets) : null,
		},
		rateState: !verified || host.observation_state !== 'fresh' ? 'stale' : fresh ? 'fresh' : 'unknown',
		rxWidth: width(safeRate(nic.rates.rx_bytes)),
		txWidth: width(safeRate(nic.rates.tx_bytes)),
		history: nicHistory(host, nic.name, verified),
		physical: nic.physical === true && observation.sources.lldp === 'measured' ? observation.lldp.filter(edge => edge.interface === nic.name).map(edge => ({ chassis: edge.chassis_id, port: edge.port_id, name: edge.system_name })) : [],
		neighbors: observation.sources.neighbors === 'measured' ? observation.neighbors.filter(edge => edge.interface === nic.name).map(edge => ({ ip: edge.ip, mac: edge.mac, state: edge.state })) : [],
		routes: observation.sources.routes === 'measured' ? observation.routes.filter(edge => edge.interface === nic.name).map(edge => ({ destination: edge.destination, gateway: edge.gateway, metric: edge.metric })) : [],
		rxActive: verified && host.observation_state === 'fresh' && observation.sources.counters === 'measured' && ((Number.isFinite(nic.rates.rx_bytes) && (nic.rates.rx_bytes ?? 0) > 0) || (Number.isFinite(nic.rates.rx_packets) && (nic.rates.rx_packets ?? 0) > 0)),
		txActive: verified && host.observation_state === 'fresh' && observation.sources.counters === 'measured' && ((Number.isFinite(nic.rates.tx_bytes) && (nic.rates.tx_bytes ?? 0) > 0) || (Number.isFinite(nic.rates.tx_packets) && (nic.rates.tx_packets ?? 0) > 0)),
	}));
}

export interface PeerProbeEdge extends PeerProbe {
	source: string;
	sourceName: string;
	targetName: string;
	targetInInventory: boolean;
}
/** A successful TCP connect proves only this directed source-to-port observation.
 * Targets outside inventory remain explicit endpoints, never collapsed into a host. */
export function buildPeerProbeEdges(hosts: TopologyHost[], verified: boolean): PeerProbeEdge[] {
	const inventory = new Map(hosts.map(host => [host.id, host]));
	return hosts.flatMap(host => host.peer_probes.map<PeerProbeEdge>(probe => ({
		...probe, source: host.id, sourceName: host.name,
		targetName: inventory.get(probe.target_host_id)?.name ?? probe.target_host_id,
		targetInInventory: inventory.has(probe.target_host_id),
		status: verified && host.observation_state === 'fresh' ? probe.status : 'unknown',
		latency_ms: verified && host.observation_state === 'fresh' ? probe.latency_ms : null,
		error: host.observation_state === 'unmeasured' ? probe.error ?? 'probe_unmeasured' : !verified || host.observation_state === 'stale' ? 'probe_stale' : probe.error,
	})));
}
export interface NetworkNode {
	id: string;
	kind: 'host' | 'router' | 'gap' | 'destination' | 'peer';
	label: string;
	hostId?: string;
	column: number;
	x: number;
	y: number;
	minHop: number | null;
	/** Last hop of a collapsed no-reply run; null for responding nodes. */
	maxHop: number | null;
	rttMin: number | null;
	rttMax: number | null;
	pathIds: string[];
	stale: boolean;
	/** Host nodes only: the observation state shown to the operator. */
	observationState?: ObservationState;
}
export type CollapsedHop = { kind: 'hop'; hop: TraceResult['hops'][number] } | { kind: 'gap'; from: number; to: number; count: number };
/** Gaps remain trace-local; they are not inferred routers or fault locations. */
export function collapseHops(hops: TraceResult['hops']): CollapsedHop[] {
	const items: CollapsedHop[] = [];
	for (const hop of [...hops].sort((a, b) => a.hop - b.hop)) {
		const previous = items.at(-1);
		if (hop.ip !== null) items.push({ kind: 'hop', hop });
		else if (previous?.kind === 'gap' && previous.to + 1 === hop.hop) { previous.to = hop.hop; previous.count += 1; }
		else items.push({ kind: 'gap', from: hop.hop, to: hop.hop, count: 1 });
	}
	return items;
}
export interface NetworkPath {
	id: string;
	hostId: string;
	hostName: string;
	target: string;
	status: TopologyTrace['status'];
	error: TraceResult['error'];
	stale: boolean;
	reached: boolean;
	hops: TraceResult['hops'];
	nodeIds: string[];
}
export interface NetworkEdge {
	id: string;
	source: string;
	target: string;
	kind: 'trace' | 'probe';
	state: 'observed' | 'unconfirmed' | 'queued' | 'running' | 'error' | 'unsupported' | 'expired' | 'up' | 'down' | 'unknown';
	dashed: boolean;
	stale: boolean;
	pathId?: string;
	probe?: PeerProbeEdge;
	d: string;
	labelX: number;
	labelY: number;
}
export interface NetworkMapGraph {
	nodes: NetworkNode[];
	paths: NetworkPath[];
	edges: NetworkEdge[];
	width: number;
	height: number;
}

/** Fixed pixel layers describe only reported outbound paths, not physical cables.
 * A router IP is shared evidence; a non-response is local to its individual trace. */
export function buildNetworkMap(hosts: TopologyHost[], verified: boolean): NetworkMapGraph {
	const compare = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;
	const roles = ['compute', 'controller', 'storage'];
	const orderedHosts = [...hosts].sort((a, b) => roles.indexOf(a.role) - roles.indexOf(b.role) || compare(a.name, b.name) || compare(a.id, b.id));
	const paths: NetworkPath[] = [];
	for (const host of orderedHosts) {
		const targets = new Map<string, TopologyTrace[]>();
		for (const trace of host.traces) {
			const group = targets.get(trace.target) ?? [];
			group.push(trace);
			targets.set(trace.target, group);
		}
		for (const target of [...targets.keys()].sort(compare)) {
			const traces = targets.get(target)!.sort((a, b) => b.created_at - a.created_at || compare(a.id, b.id));
			const measured = traces.find(trace => trace.result && trace.result.hops.length > 0);
			const latest = traces[0];
			const selected = measured && latest !== measured ? [measured, latest] : [latest];
			for (const trace of selected) {
				paths.push({ id: `${host.id}:${trace.id}`, hostId: host.id, hostName: host.name, target,
					status: trace.result?.status ?? trace.status, error: trace.result?.error ?? null,
					stale: !verified || host.observation_state !== 'fresh' || trace.status === 'expired',
					reached: trace.result?.reached ?? false,
					hops: [...(trace.result?.hops ?? [])].sort((a, b) => a.hop - b.hop), nodeIds: [] });
			}
		}
	}
	const responding = new Set(paths.flatMap(path => path.hops.flatMap(hop => hop.ip === null ? [] : [hop.ip])));
	const targets = new Set(paths.map(path => path.target));
	// Columns follow each path's collapsed position, so a long no-reply run occupies one column;
	// labels keep the actual hop numbers.
	const finalColumn = Math.max(1, ...paths.map(path => collapseHops(path.hops).length)) + 1;
	const nodes = new Map<string, NetworkNode>();
	const addNode = (id: string, kind: NetworkNode['kind'], label: string, column: number, stale: boolean, pathId?: string, hop?: TraceResult['hops'][number]) => {
		let node = nodes.get(id);
		if (!node) {
			node = { id, kind, label, column, x: 0, y: 0, minHop: null, maxHop: null, rttMin: null, rttMax: null, pathIds: [], stale };
			nodes.set(id, node);
		}
		node.column = Math.min(node.column, column);
		node.stale = node.stale && stale;
		if (pathId && !node.pathIds.includes(pathId)) node.pathIds.push(pathId);
		if (hop) {
			node.minHop = Math.min(node.minHop ?? hop.hop, hop.hop);
			if (hop.rtt_ms !== null && Number.isFinite(hop.rtt_ms)) {
				node.rttMin = Math.min(node.rttMin ?? hop.rtt_ms, hop.rtt_ms);
				node.rttMax = Math.max(node.rttMax ?? hop.rtt_ms, hop.rtt_ms);
			}
		}
		return node;
	};
	for (const host of orderedHosts) {
		const node = addNode(`host:${host.id}`, 'host', host.name, 0, !verified || host.observation_state !== 'fresh');
		node.hostId = host.id;
		node.observationState = verified ? host.observation_state : 'stale';
	}
	const edges: NetworkEdge[] = [];
	for (const path of paths) {
		path.nodeIds.push(`host:${path.hostId}`);
		collapseHops(path.hops).forEach((item, index) => {
			const column = index + 1;
			if (item.kind === 'gap') {
				const id = `gap:${path.id}:${item.from}`;
				const node = addNode(id, 'gap', '*', column, path.stale, path.id, { hop: item.from, ip: null, rtt_ms: null });
				node.maxHop = item.to;
				path.nodeIds.push(id);
				return;
			}
			const { hop } = item;
			const id = `ip:${hop.ip}`;
			addNode(id, targets.has(hop.ip!) ? 'destination' : 'router', hop.ip!, column, path.stale, path.id, hop);
			path.nodeIds.push(id);
		});
		const destinationId = responding.has(path.target) ? `ip:${path.target}` : `destination:${path.target}`;
		addNode(destinationId, 'destination', path.target, finalColumn, path.stale, path.id);
		const last = path.hops.at(-1);
		const confirmed = path.reached && last?.ip === path.target;
		if (path.nodeIds.at(-1) !== destinationId) path.nodeIds.push(destinationId);
		for (let index = 1; index < path.nodeIds.length; index++) {
			const state: NetworkEdge['state'] = path.hops.length === 0
				? path.status === 'complete' ? 'unconfirmed' : path.status
				: path.nodeIds[index] === destinationId && !confirmed ? 'unconfirmed' : 'observed';
			edges.push({ id: `${path.id}:${index}`, source: path.nodeIds[index - 1], target: path.nodeIds[index], kind: 'trace', state,
				dashed: state !== 'observed', stale: path.stale, pathId: path.id, d: '', labelX: 0, labelY: 0 });
		}
	}
	const probes = buildPeerProbeEdges(orderedHosts, verified).sort((a, b) => compare(`${a.source}:${a.target_host_id}:${a.address}:${a.port}`, `${b.source}:${b.target_host_id}:${b.address}:${b.port}`));
	for (const [index, probe] of probes.entries()) {
		const targetId = probe.targetInInventory ? `host:${probe.target_host_id}` : `peer:${probe.target_host_id}:${probe.address}:${probe.port}`;
		if (!probe.targetInInventory) addNode(targetId, 'peer', `${probe.targetName} · ${probe.address}:${probe.port}`, finalColumn, probe.status === 'unknown');
		edges.push({ id: `probe:${index}`, source: `host:${probe.source}`, target: targetId, kind: 'probe', state: probe.status,
			dashed: probe.status === 'unknown', stale: probe.error === 'probe_stale' || probe.error === 'probe_unmeasured', probe, d: '', labelX: 0, labelY: 0 });
	}
	const columns = new Map<number, NetworkNode[]>();
	for (const node of nodes.values()) {
		const column = columns.get(node.column) ?? [];
		column.push(node);
		columns.set(node.column, column);
	}
	for (const [column, layer] of columns) {
		if (column !== 0) layer.sort((a, b) => compare(a.label, b.label) || compare(a.id, b.id));
		layer.forEach((node, row) => { node.x = 210 + column * 250; node.y = 50 + row * 110; });
	}
	for (const [index, edge] of edges.entries()) {
		const source = nodes.get(edge.source)!;
		const target = nodes.get(edge.target)!;
		if (edge.kind === 'probe' && target.kind === 'host') {
			const bend = 30 + (index % 6) * 20;
			edge.d = `M ${source.x} ${source.y + 22} C ${bend} ${source.y + 22}, ${bend} ${target.y + 22}, ${target.x} ${target.y + 22}`;
			edge.labelX = bend + 30; edge.labelY = (source.y + target.y) / 2 + 14;
		} else {
			const start = source.x + 180, end = target.x;
			const middle = (start + end) / 2;
			edge.d = `M ${start} ${source.y + 22} C ${middle} ${source.y + 22}, ${middle} ${target.y + 22}, ${end} ${target.y + 22}`;
			edge.labelX = middle; edge.labelY = (source.y + target.y) / 2 + 12;
		}
	}
	return { nodes: [...nodes.values()], paths, edges,
		width: Math.max(640, ...[...nodes.values()].map(node => node.x + 220)),
		height: Math.max(150, ...[...nodes.values()].map(node => node.y + 95)) };
}
