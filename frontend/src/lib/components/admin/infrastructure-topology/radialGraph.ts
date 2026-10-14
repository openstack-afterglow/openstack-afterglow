import type { FabricLink, InfrastructureTopologySnapshot, ObservedRoute, SwitchPort, TopologyFlow, TopologyTrace } from '$lib/types/infrastructureTopology';
import { buildPeerProbeEdges, collapseHops, safeRate, type PeerProbeEdge } from './evidence';

export type FlowMetric = 'pps' | 'Bps';
export type EvidenceLayer = 'flow' | 'physical' | 'route' | 'probe' | 'trace';
export const LAYERS: EvidenceLayer[] = ['flow', 'physical', 'route', 'probe', 'trace'];
export const SCALE: Record<FlowMetric, { maximum: number; ticks: number[] }> = {
	pps: { maximum: 1_000_000, ticks: [0, 1, 100, 10_000, 1_000_000] },
	Bps: { maximum: 1_073_741_824, ticks: [0, 1024, 1_048_576, 1_073_741_824] },
};
export interface RadialNode {
	id: string; kind: 'host' | 'switch' | 'port' | 'router' | 'gap' | 'destination' | 'peer' | 'route';
	label: string; x: number; y: number; state: string; layer?: EvidenceLayer;
	hostId?: string; deviceId?: string; portId?: string; traceIds?: string[];
}
export interface RadialEdge {
	id: string; source: string; target: string; layer: EvidenceLayer; state: string;
	hostId?: string; flow?: TopologyFlow; observations?: TopologyFlow[]; receiverOnly?: boolean;
	link?: FabricLink; port?: SwitchPort; portDirection?: 'rx' | 'tx'; probe?: PeerProbeEdge;
	trace?: TopologyTrace; route?: ObservedRoute; membership?: boolean; lane: number;
}
export interface RadialGraph {
	nodes: RadialNode[]; edges: RadialEdge[];
	bounds: { x: number; y: number; w: number; h: number }; hostRadius: number; switchRadius: number;
}
/** Numeric chunks compare without locale dependence, integer parsing or uint64 precision loss. */
export function naturalId(a: string, b: string): number {
	const aa = a.match(/\d+|\D+/g) ?? [], bb = b.match(/\d+|\D+/g) ?? [];
	for (let i = 0; i < Math.min(aa.length, bb.length); i++) {
		const x = aa[i], y = bb[i];
		if (x === y) continue;
		if (/^\d+$/.test(x) && /^\d+$/.test(y)) {
			const xx = x.replace(/^0+/, '') || '0', yy = y.replace(/^0+/, '') || '0';
			if (xx.length !== yy.length) return xx.length - yy.length;
			if (xx !== yy) return xx < yy ? -1 : 1;
		}
		return x < y ? -1 : 1;
	}
	return aa.length - bb.length || (a < b ? -1 : a > b ? 1 : 0);
}
export function magnitude(value: number | null, state: string, metric: FlowMetric) {
	const rate = state === 'fresh' ? safeRate(value) : null;
	const amount = rate === null ? 0 : Math.min(1, Math.log1p(rate) / Math.log1p(SCALE[metric].maximum));
	return { rate, width: rate === null ? 1.5 : 1.5 + 6 * amount, opacity: rate === null ? 0.45 : 0.35 + 0.65 * amount,
		zero: rate === 0, unknown: rate === null, saturated: rate !== null && rate > SCALE[metric].maximum };
}
export function edgeRate(edge: RadialEdge, metric: FlowMetric): number | null {
	if (edge.flow) return metric === 'pps' ? edge.flow.packets_per_second : edge.flow.bytes_per_second;
	if (!edge.port || !edge.portDirection) return null;
	const port = edge.port;
	return edge.portDirection === 'rx' ? metric === 'pps' ? port.rx_packets_per_second : port.rx_bytes_per_second
		: metric === 'pps' ? port.tx_packets_per_second : port.tx_bytes_per_second;
}
export function edgeWindow(edge: RadialEdge): number | null { return edge.flow?.window_seconds ?? edge.port?.window_seconds ?? null; }
const hostNode = (id: string) => `host:${id}`;
const switchNode = (id: string) => `switch:${id}`;
const tupleId = (...parts: string[]) => JSON.stringify(parts);

/** One endpoint family per directed pair. Distinct interfaces stay distinct; nothing is summed. */
export function selectFlowObservations(flows: TopologyFlow[]) {
	const pairs = new Map<string, TopologyFlow[]>();
	for (const flow of flows) {
		if (!(flow.direction === 'egress' && flow.reporting_host_id === flow.source_host_id || flow.direction === 'ingress' && flow.reporting_host_id === flow.target_host_id)) continue;
		const key = tupleId(flow.source_host_id, flow.target_host_id);
		const rows = pairs.get(key) ?? []; rows.push(flow); pairs.set(key, rows);
	}
	return [...pairs.entries()].sort(([a], [b]) => naturalId(a, b)).flatMap(([, rows]) => {
		rows.sort((a, b) => naturalId(a.id, b.id));
		const sender = rows.filter(row => row.direction === 'egress'), receiver = rows.filter(row => row.direction === 'ingress');
		const measured = (row: TopologyFlow) => row.state === 'fresh' && (safeRate(row.packets_per_second) !== null || safeRate(row.bytes_per_second) !== null);
		const chosen = sender.some(measured) ? sender : receiver.some(measured) ? receiver : sender.length ? sender : receiver;
		return chosen.map(flow => ({ flow, observations: rows, receiverOnly: flow.direction === 'ingress' }));
	});
}

/** Layout reads identities only, never rate/status. Controllers are anchors, not transit nodes. */
export function buildRadialGraph(snapshot: InfrastructureTopologySnapshot, verified: boolean): RadialGraph {
	const nodes = new Map<string, RadialNode>(), edges: RadialEdge[] = [];
	const hosts = [...snapshot.hosts].sort((a, b) => naturalId(a.id, b.id));
	const devices = [...snapshot.fabric.devices].sort((a, b) => naturalId(a.id, b.id));
	const ports = new Map(snapshot.fabric.ports.map(port => [port.id, port]));
	const state = (value: string) => verified ? value : 'stale';
	const polar = (radius: number, angle: number) => ({ x: radius * Math.cos(angle), y: radius * Math.sin(angle) });
	const add = (node: RadialNode) => { if (!nodes.has(node.id)) nodes.set(node.id, node); return nodes.get(node.id)!; };
	for (const host of hosts) add({ id: hostNode(host.id), kind: 'host', label: host.name, x: 0, y: 0, state: state(host.observation_state), hostId: host.id });
	for (const device of devices) add({ id: switchNode(device.id), kind: 'switch', label: device.name, x: 0, y: 0, state: state(device.state), deviceId: device.id, layer: 'physical' });
	// Port identity comes from a resolved IF-MIB row, or an explicit unresolved LLDP endpoint.
	const portNodes = new Map<string, { node: RadialNode; deviceId: string }>();
	const endpoint = (value: FabricLink['source'], portId: string | null) => {
		if (value.kind === 'host') return nodes.has(hostNode(value.id)) ? hostNode(value.id) : null;
		if (!nodes.has(switchNode(value.id))) return null;
		const id = portId ? `port:${portId}` : `lldp-port:${tupleId(value.id, value.port)}`;
		const port = portId ? ports.get(portId) : undefined;
		if (!portNodes.has(id)) {
			const node = add({ id, kind: 'port', label: port?.name ?? value.port, x: 0, y: 0, state: state(port?.state ?? 'unmeasured'), deviceId: value.id, portId: port?.id, layer: 'physical' });
			portNodes.set(id, { node, deviceId: value.id });
		}
		return id;
	};
	const physicalPort = (value: FabricLink['source'], id: string | null) => {
		const port = id ? ports.get(id) : undefined;
		return value.kind === 'switch' && port?.physical === true && port.device_id === value.id ? port : undefined;
	};
	for (const link of [...snapshot.fabric.links].sort((a, b) => naturalId(a.id, b.id))) {
		const sourcePort = physicalPort(link.source, link.source_port_id), targetPort = physicalPort(link.target, link.target_port_id);
		const source = endpoint(link.source, sourcePort?.id ?? null), target = endpoint(link.target, targetPort?.id ?? null);
		if (!source || !target || source === target) continue;
		const resolved = (link.source.kind !== 'switch' || sourcePort !== undefined) && (link.target.kind !== 'switch' || targetPort !== undefined);
		const observed = resolved ? (sourcePort?.state === 'fresh' ? sourcePort : targetPort?.state === 'fresh' ? targetPort : sourcePort ?? targetPort) : undefined;
		if (!observed) edges.push({ id: `physical:${link.id}`, source, target, layer: 'physical', state: state(link.state), link, lane: 0 });
		else for (const direction of ['rx', 'tx'] as const) {
			const local = observed === sourcePort ? source : target, remote = local === source ? target : source;
			edges.push({ id: `physical:${link.id}:${direction}`, source: direction === 'rx' ? remote : local, target: direction === 'rx' ? local : remote,
				layer: 'physical', state: state(link.state === 'fresh' ? observed.state : link.state), link, port: observed, portDirection: direction, lane: 1 });
		}
	}
	const portGroups = new Map<string, { node: RadialNode; deviceId: string }[]>();
	for (const item of portNodes.values()) {
		const group = portGroups.get(item.deviceId) ?? [];
		group.push(item); portGroups.set(item.deviceId, group);
	}
	const portRadius = Math.max(76, ...[...portGroups.values()].map(group => group.length * 16));
	const controllerCount = hosts.filter(host => host.role === 'controller').length;
	const controllerRadius = controllerCount <= 1 ? 0 : Math.max(80, controllerCount * 24);
	// Leave room for the whole port cluster, not just its switch center.
	const switchRadius = Math.max(210, controllerRadius + portRadius + 80,
		devices.length > 1 ? (portRadius + 40) / Math.sin(Math.PI / devices.length) : 0);
	const hostRadius = Math.max(440, (hosts.length - controllerCount) * 32, switchRadius + portRadius + 160);
	for (const role of ['controller', 'compute', 'storage'] as const) {
		const group = hosts.filter(host => host.role === role);
		group.forEach((host, index) => {
			const angle = role === 'controller' ? -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, group.length)
				: (role === 'compute' ? Math.PI : 0) - Math.PI * 0.36 + (index + 0.5) * Math.PI * 0.72 / Math.max(1, group.length);
			Object.assign(nodes.get(hostNode(host.id))!, polar(role === 'controller' ? controllerRadius : hostRadius, angle));
		});
	}
	devices.forEach((device, index) => Object.assign(nodes.get(switchNode(device.id))!, polar(switchRadius, -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, devices.length))));
	for (const device of devices) {
		const group = (portGroups.get(device.id) ?? []).sort((a, b) => naturalId(a.node.id, b.node.id));
		const center = nodes.get(switchNode(device.id))!;
		group.forEach(({ node }, index) => {
			const point = polar(Math.max(76, group.length * 16), -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, group.length));
			node.x = center.x + point.x; node.y = center.y + point.y;
			edges.push({ id: `membership:${node.id}`, source: center.id, target: node.id, layer: 'physical', state: node.state, membership: true, lane: 0 });
		});
	}
	const flowLanes = new Map<string, number>();
	for (const { flow, observations, receiverOnly } of selectFlowObservations(snapshot.flows)) {
		const source = hostNode(flow.source_host_id), target = hostNode(flow.target_host_id);
		if (!nodes.has(source) || !nodes.has(target) || source === target) continue;
		const key = tupleId(source, target), lane = (flowLanes.get(key) ?? 0) + 1;
		flowLanes.set(key, lane);
		edges.push({ id: `flow:${flow.id}`, source, target, layer: 'flow', state: state(flow.state), flow, observations, receiverOnly, hostId: flow.reporting_host_id, lane });
	}
	const outside = new Map<number, RadialNode[]>();
	const traceTargets = new Set(hosts.flatMap(host => host.traces.map(trace => trace.target)));
	const external = (node: RadialNode, ring: number) => {
		const existed = nodes.has(node.id), value = add(node);
		if (!existed) { const group = outside.get(ring) ?? []; group.push(value); outside.set(ring, group); }
		return value.id;
	};
	for (const probe of buildPeerProbeEdges(hosts, verified)) {
		const target = probe.targetInInventory ? hostNode(probe.target_host_id) : external({ id: `peer:${tupleId(probe.target_host_id, probe.address, String(probe.port))}`, kind: 'peer', label: `${probe.targetName} · ${probe.address}:${probe.port}`, x: 0, y: 0, state: probe.status, layer: 'probe' }, 1);
		edges.push({ id: `probe:${tupleId(probe.source, probe.target_host_id, probe.address, String(probe.port))}`, source: hostNode(probe.source), target, layer: 'probe', state: probe.status, probe, hostId: probe.source, lane: 1 });
	}
	for (const host of hosts) {
		if (host.observation?.sources.routes === 'measured') for (const route of host.observation.routes) {
			const id = tupleId(host.id, route.interface, route.destination, route.gateway ?? '', String(route.metric));
			const target = external({ id: `route:${id}`, kind: 'route', label: `${route.gateway ?? '—'} → ${route.destination}`, x: 0, y: 0, state: state(host.observation_state), layer: 'route' }, 1);
			edges.push({ id: `route:${id}`, source: hostNode(host.id), target, layer: 'route', state: state(host.observation_state), hostId: host.id, route, lane: 0 });
		}
		const groups = new Map<string, TopologyTrace[]>();
		for (const trace of host.traces) { const group = groups.get(trace.target) ?? []; group.push(trace); groups.set(trace.target, group); }
		for (const [target, rows] of [...groups].sort(([a], [b]) => naturalId(a, b))) {
			rows.sort((a, b) => b.created_at - a.created_at || naturalId(a.id, b.id));
			const measured = rows.find(row => row.result?.hops.length), latest = rows[0];
			for (const trace of measured && measured !== latest ? [measured, latest] : [latest]) {
				let previous = hostNode(host.id);
				const traceState = !verified || host.observation_state !== 'fresh' || trace.status === 'expired' ? 'stale' : trace.status;
				const hops = collapseHops(trace.result?.hops ?? []);
				const path = tupleId(host.id, trace.id);
				hops.forEach((item, index) => {
					const id = item.kind === 'gap' ? `gap:${path}:${item.from}` : `ip:${item.hop.ip}`;
					const next = external({ id, kind: item.kind === 'gap' ? 'gap' : traceTargets.has(item.hop.ip!) ? 'destination' : 'router', label: item.kind === 'gap' ? `* ${item.from}–${item.to}` : item.hop.ip!, x: 0, y: 0, state: traceState, layer: 'trace', traceIds: [] }, index + 2);
					const node = nodes.get(next)!; node.traceIds ??= []; if (!node.traceIds.includes(path)) node.traceIds.push(path);
					if (node.state === 'stale' && traceState !== 'stale') node.state = traceState;
					const lastUnconfirmed = item.kind === 'hop' && item.hop.ip === target && !trace.result?.reached && traceState === 'complete';
					edges.push({ id: `trace:${path}:${index}`, source: previous, target: next, layer: 'trace', state: lastUnconfirmed ? 'unconfirmed' : traceState, hostId: host.id, trace, lane: 0 }); previous = next;
				});
				if (nodes.get(previous)?.label !== target) {
					const next = external({ id: `ip:${target}`, kind: 'destination', label: target, x: 0, y: 0, state: traceState, layer: 'trace', traceIds: [path] }, hops.length + 2);
					edges.push({ id: `trace:${path}:destination`, source: previous, target: next, layer: 'trace', state: trace.result?.reached ? traceState : traceState === 'complete' ? 'unconfirmed' : traceState, hostId: host.id, trace, lane: 0 });
				}
			}
		}
	}
	for (const [ring, group] of outside) {
		group.sort((a, b) => naturalId(a.id, b.id));
		group.forEach((node, index) => Object.assign(node, polar(Math.max(hostRadius, switchRadius + 230) + ring * 180, -Math.PI / 2 + index * Math.PI * 2 / group.length)));
	}
	const orderedNodes = [...nodes.values()].sort((a, b) => naturalId(a.id, b.id));
	edges.sort((a, b) => naturalId(a.id, b.id));
	return { nodes: orderedNodes, edges, hostRadius: Math.max(hostRadius, switchRadius + 230), switchRadius,
		bounds: graphBounds(orderedNodes) };
}
export function graphBounds(nodes: RadialNode[]) {
	const left = Math.min(-120, ...nodes.map(node => node.x - 90)), top = Math.min(-120, ...nodes.map(node => node.y - 50));
	return { x: left, y: top, w: Math.max(120, ...nodes.map(node => node.x + 90)) - left, h: Math.max(120, ...nodes.map(node => node.y + 80)) - top };
}
export function visibleGraph(graph: RadialGraph, layers: Record<EvidenceLayer, boolean>): RadialGraph {
	const nodes = graph.nodes.filter(node => !node.layer || layers[node.layer]);
	const ids = new Set(nodes.map(node => node.id));
	return { ...graph, nodes, edges: graph.edges.filter(edge => layers[edge.layer] && ids.has(edge.source) && ids.has(edge.target)), bounds: graphBounds(nodes) };
}
export function curve(source: { x: number; y: number }, target: { x: number; y: number }, lane = 0) {
	const dx = target.x - source.x, dy = target.y - source.y, length = Math.hypot(dx, dy);
	if (length === 0) return { d: '', x: source.x, y: source.y };
	const ux = dx / length, uy = dy / length, bend = lane * Math.min(70, length * 0.16);
	// Keep a forward segment even when fit/zoom brings fixed-size node targets close together.
	const startTrim = Math.min(24, length * 0.4), endTrim = Math.min(27, length * 0.4);
	const a = { x: source.x + ux * startTrim, y: source.y + uy * startTrim }, b = { x: target.x - ux * endTrim, y: target.y - uy * endTrim };
	const middle = { x: (a.x + b.x) / 2 - uy * bend, y: (a.y + b.y) / 2 + ux * bend };
	return { d: `M ${a.x} ${a.y} Q ${middle.x} ${middle.y} ${b.x} ${b.y}`, x: (a.x + 2 * middle.x + b.x) / 4, y: (a.y + 2 * middle.y + b.y) / 4 };
}
