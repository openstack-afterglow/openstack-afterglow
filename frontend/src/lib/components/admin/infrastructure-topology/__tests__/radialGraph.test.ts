import { describe, expect, it } from 'vitest';
import { buildRadialGraph, curve, edgeRate, magnitude, naturalId, selectFlowObservations, visibleGraph, type RadialGraph } from '../radialGraph';
import { makeFlow, makeHost, makeMeshSnapshot, makeNetworkHosts, makePort, makeSnapshot, makeTrace } from './fixtures';

const coordinates = (graph: RadialGraph) => graph.nodes.map(({ id, x, y }) => ({ id, x, y }));
describe('controller-core identity layout', () => {
	it('places controllers at the core without inventing transit or a complete host mesh', () => {
		const snapshot = makeMeshSnapshot(), graph = buildRadialGraph(snapshot, true);
		const controller = graph.nodes.find(node => node.hostId === 'controller:node-b')!;
		expect(Math.hypot(controller.x, controller.y)).toBeLessThan(graph.switchRadius);
		const flows = graph.edges.filter(edge => edge.layer === 'flow');
		expect(flows).toHaveLength(1); expect(flows[0]).toMatchObject({ source: 'host:compute:node-a', target: 'host:storage:node-c' });
		expect(flows.some(edge => edge.source === controller.id || edge.target === controller.id)).toBe(false);
		expect(buildRadialGraph(makeSnapshot(), true).edges.filter(edge => edge.layer === 'flow' || edge.layer === 'physical')).toEqual([]);
	});
	it('keeps a dense switch-port cluster outside the controller core and host sectors', () => {
		const snapshot = makeMeshSnapshot();
		snapshot.hosts.push(makeHost('controller:node-d'), makeHost('controller:node-e'));
		snapshot.fabric.ports = Array.from({ length: 18 }, (_, index) => {
			const device = snapshot.fabric.devices[index % 2];
			return makePort({ id: `${device.id}:if:${index + 1}`, device_id: device.id, ifindex: index + 1 });
		});
		snapshot.fabric.links = snapshot.fabric.ports.map(port => ({
			id: `link:${port.id}`, source: { kind: 'host', id: snapshot.hosts[0].id, port: 'eno1' },
			target: { kind: 'switch', id: port.device_id, port: port.name }, source_port_id: null,
			target_port_id: port.id, state: 'fresh', captured_at: port.captured_at!, evidence: 'lldp',
		}));
		const graph = buildRadialGraph(snapshot, true);
		const controllers = graph.nodes.filter(node => node.hostId?.startsWith('controller:'));
		const coreRadius = Math.max(...controllers.map(node => Math.hypot(node.x, node.y)));
		for (const port of graph.nodes.filter(node => node.kind === 'port')) {
			expect(Math.hypot(port.x, port.y)).toBeGreaterThan(coreRadius + 44);
			expect(Math.hypot(port.x, port.y)).toBeLessThan(graph.hostRadius - 44);
		}
	});
	it('is independent of inventory order, locale-like identifiers, throughput and measurement freshness', () => {
		const snapshot = makeMeshSnapshot(); snapshot.hosts.push(makeHost('compute:node-10'), makeHost('compute:node-2'));
		const first = buildRadialGraph(snapshot, true), reversed = structuredClone(snapshot);
		reversed.hosts.reverse(); reversed.flows.reverse(); reversed.fabric.devices.reverse(); reversed.fabric.links.reverse(); reversed.fabric.ports.reverse();
		expect(coordinates(buildRadialGraph(reversed, true))).toEqual(coordinates(first));
		for (const flow of reversed.flows) { flow.packets_per_second = 900_000; flow.bytes_per_second = 0; flow.state = 'stale'; }
		for (const port of reversed.fabric.ports) { port.rx_packets_per_second = null; port.state = 'error'; }
		expect(coordinates(buildRadialGraph(reversed, false))).toEqual(coordinates(first));
		expect(['node-10', 'node-2', 'node-1', 'node-02'].sort(naturalId)).toEqual(['node-1', 'node-02', 'node-2', 'node-10']);
	});
});
describe('packet observation selection and fixed magnitude', () => {
	it('prefers sender egress while preserving receiver records for inspection, never summing endpoints', () => {
		const snapshot = makeMeshSnapshot(), chosen = selectFlowObservations(snapshot.flows);
		expect(chosen).toHaveLength(1); expect(chosen[0].flow.packets_per_second).toBe(12); expect(chosen[0].receiverOnly).toBe(false); expect(chosen[0].observations).toHaveLength(2);
	});
	it('uses an explicitly labeled fresh receiver when the sender has no continuous measurement', () => {
		const snapshot = makeMeshSnapshot(); Object.assign(snapshot.flows[0], { state: 'unmeasured', reason: 'counter_reset', packets_per_second: null, bytes_per_second: null, window_seconds: null });
		const [chosen] = selectFlowObservations(snapshot.flows); expect(chosen.receiverOnly).toBe(true); expect(chosen.flow.packets_per_second).toBe(9); expect(chosen.observations[0].reason).toBe('counter_reset');
	});
	it('keeps independently observed interfaces in distinct lanes and rejects inconsistent reporting endpoints', () => {
		const snapshot = makeMeshSnapshot(); snapshot.flows.push(makeFlow({ id: 'flow:interface2', interface: 'eno2', packets_per_second: 7 }), makeFlow({ id: 'flow:invalid', reporting_host_id: 'controller:node-b' }));
		const edges = buildRadialGraph(snapshot, true).edges.filter(edge => edge.layer === 'flow');
		expect(edges).toHaveLength(2); expect(edges.map(edge => edgeRate(edge, 'pps')).sort((a, b) => a! - b!)).toEqual([7, 12]); expect(edges[0].lane).not.toBe(edges[1].lane);
	});
	it.each(['pps', 'Bps'] as const)('monotonically encodes %s with fixed width/brightness, measured zero and unknown distinct', metric => {
		const values = [0, 1, 100, 10_000, 1_000_000].map(value => magnitude(value, 'fresh', metric));
		for (let i = 1; i < values.length; i++) { expect(values[i].width).toBeGreaterThan(values[i - 1].width); expect(values[i].opacity).toBeGreaterThan(values[i - 1].opacity); }
		expect(values[0]).toMatchObject({ zero: true, unknown: false, rate: 0 });
		expect(magnitude(null, 'fresh', metric)).toMatchObject({ zero: false, unknown: true, rate: null });
		for (const state of ['stale', 'unmeasured', 'error']) expect(magnitude(100, state, metric).rate).toBeNull();
		expect(magnitude(Infinity, 'fresh', metric).rate).toBeNull(); expect(magnitude(-1, 'fresh', metric).rate).toBeNull();
		expect(magnitude(10 ** 12, 'fresh', metric)).toMatchObject({ saturated: true, width: 7.5, opacity: 1 });
	});
	it('does not render rates from a retained unverified snapshot', () => {
		const graph = buildRadialGraph(makeMeshSnapshot(), false);
		for (const edge of graph.edges.filter(edge => edge.flow || edge.port)) expect(magnitude(edgeRate(edge, 'pps'), edge.state, 'pps').rate).toBeNull();
	});
});
describe('real LLDP devices/ports and IF-MIB rates', () => {
	it('draws each resolved switch port and observed RX/TX direction without borrowing host quantities', () => {
		const snapshot = makeMeshSnapshot(); snapshot.hosts[0].observation!.interfaces[0].rates = { rx_bytes: 900_000, tx_bytes: 900_000, rx_packets: 1000, tx_packets: 1000 };
		const graph = buildRadialGraph(snapshot, true), edges = graph.edges.filter(edge => edge.link?.id === snapshot.fabric.links[0].id);
		expect(graph.nodes.filter(node => node.kind === 'switch')).toHaveLength(2); expect(graph.nodes.filter(node => node.kind === 'port')).toHaveLength(3);
		expect(edges).toHaveLength(2);
		expect(edges.find(edge => edge.portDirection === 'rx')).toMatchObject({ source: 'host:compute:node-a', target: 'port:switch:sw-a:if:5' });
		expect(edgeRate(edges.find(edge => edge.portDirection === 'rx')!, 'pps')).toBe(14);
		expect(edgeRate(edges.find(edge => edge.portDirection === 'tx')!, 'Bps')).toBe(768);
	});
	it('keeps passive LLDP nodes with unknown ports when SNMP is unconfigured or counters are missing', () => {
		const snapshot = makeMeshSnapshot(); snapshot.fabric.state = 'unconfigured'; snapshot.fabric.ports = []; for (const link of snapshot.fabric.links) link.target_port_id = null;
		const graph = buildRadialGraph(snapshot, true), physical = graph.edges.filter(edge => edge.link);
		expect(graph.nodes.filter(node => node.kind === 'switch')).toHaveLength(2); expect(physical).toHaveLength(3);
		for (const edge of physical) { expect(edge.port).toBeUndefined(); expect(edgeRate(edge, 'pps')).toBeNull(); }
	});
	it.each([false, null, undefined])('retains LLDP but never promotes physical=%s switch counters to cable traffic', physical => {
		const snapshot = makeMeshSnapshot(); snapshot.fabric.ports[0].physical = physical;
		const edges = buildRadialGraph(snapshot, true).edges.filter(edge => edge.link?.id === snapshot.fabric.links[0].id);
		expect(edges).toHaveLength(1);
		expect(edges[0].port).toBeUndefined(); expect(edgeRate(edges[0], 'pps')).toBeNull(); expect(edgeRate(edges[0], 'Bps')).toBeNull();
	});
	it('never joins an actual counter belonging to a different switch device', () => {
		const snapshot = makeMeshSnapshot(); snapshot.fabric.ports[0].device_id = 'switch:sw-b';
		const edges = buildRadialGraph(snapshot, true).edges.filter(edge => edge.link?.id === snapshot.fabric.links[0].id);
		expect(edges).toHaveLength(1); expect(edges[0].port).toBeUndefined(); expect(edgeRate(edges[0], 'pps')).toBeNull();
	});
	it('never duplicates both endpoint counters of an actual switch-switch link', () => {
		const snapshot = makeMeshSnapshot(); snapshot.fabric.ports.push(makePort({ id: 'switch:sw-b:if:9', device_id: 'switch:sw-b', ifindex: 9, name: 'Ethernet9', rx_packets_per_second: 99 }));
		snapshot.fabric.links = [{ id: 'trunk', source: { kind: 'switch', id: 'switch:sw-a', port: 'Ethernet5' }, target: { kind: 'switch', id: 'switch:sw-b', port: 'Ethernet9' }, source_port_id: 'switch:sw-a:if:5', target_port_id: 'switch:sw-b:if:9', captured_at: 1_800_000_000, state: 'fresh', evidence: 'lldp' }];
		const edges = buildRadialGraph(snapshot, true).edges.filter(edge => edge.link);
		expect(edges).toHaveLength(2); expect(edges.every(edge => edge.port?.id === 'switch:sw-a:if:5')).toBe(true);
	});
	it.each(['source', 'target'] as const)('withholds cable rates if the %s switch endpoint is unresolved or nonphysical', endpoint => {
		for (const physical of [false, null, undefined, true] as const) {
			const snapshot = makeMeshSnapshot();
			const remote = makePort({ id: 'switch:sw-b:if:9', device_id: 'switch:sw-b', ifindex: 9, name: 'Ethernet9' });
			snapshot.fabric.ports.push(remote);
			const invalid = endpoint === 'source' ? snapshot.fabric.ports[0] : remote;
			invalid.physical = physical;
			const link = { id: 'unqualified-trunk', source: { kind: 'switch' as const, id: 'switch:sw-a', port: 'Ethernet5' }, target: { kind: 'switch' as const, id: 'switch:sw-b', port: 'Ethernet9' }, source_port_id: snapshot.fabric.ports[0].id as string | null, target_port_id: remote.id as string | null, captured_at: 1_800_000_000, state: 'fresh' as const, evidence: 'lldp' as const };
			if (physical === true) link[`${endpoint}_port_id`] = null;
			snapshot.fabric.links = [link];
			const graph = buildRadialGraph(snapshot, true), edges = graph.edges.filter(edge => edge.link);
			expect(edges).toHaveLength(1); expect(edges[0].port).toBeUndefined();
			expect(edgeRate(edges[0], 'pps')).toBeNull(); expect(edgeRate(edges[0], 'Bps')).toBeNull();
			expect(graph.nodes.some(node => node.deviceId === 'switch:sw-a')).toBe(true);
			expect(graph.nodes.some(node => node.deviceId === 'switch:sw-b')).toBe(true);
		}
	});
	it('retains independently measured packet quantities when byte counters are missing', () => {
		const snapshot = makeMeshSnapshot(); snapshot.fabric.ports[0].rx_bytes_per_second = null;
		const edge = buildRadialGraph(snapshot, true).edges.find(row => row.port?.id === 'switch:sw-a:if:5' && row.portDirection === 'rx')!;
		expect(edgeRate(edge, 'pps')).toBe(14); expect(edgeRate(edge, 'Bps')).toBeNull();
	});
});
describe('separate routes, TCP checks and trace evidence', () => {
	it('filters layers without moving identities and preserves outside-inventory TCP endpoints', () => {
		const snapshot = makeMeshSnapshot(); snapshot.hosts[0].peer_probes = [{ target_host_id: 'outside', address: '10.0.0.99', port: 443, status: 'down', checked_at: 1, latency_ms: null, error: 'timeout' }];
		const graph = buildRadialGraph(snapshot, true), filtered = visibleGraph(graph, { flow: true, physical: true, route: false, probe: false, trace: false });
		expect(graph.nodes.some(node => node.kind === 'peer')).toBe(true); expect(graph.edges.some(edge => edge.layer === 'route')).toBe(true);
		expect(filtered.nodes.some(node => node.kind === 'peer')).toBe(false); expect(filtered.edges.some(edge => edge.layer === 'route' || edge.layer === 'probe')).toBe(false);
		expect(filtered.nodes.filter(node => node.kind === 'host')).toEqual(graph.nodes.filter(node => node.kind === 'host'));
	});
	it('merges responding IPs but keeps collapsed response gaps local to each measured trace', () => {
		const snapshot = makeSnapshot(); snapshot.hosts = makeNetworkHosts();
		const graph = buildRadialGraph(snapshot, true);
		expect(graph.nodes.filter(node => node.kind === 'router')).toHaveLength(1); expect(graph.nodes.find(node => node.id === 'ip:10.0.0.1')?.traceIds).toHaveLength(2);
		expect(graph.nodes.filter(node => node.kind === 'gap')).toHaveLength(2); expect(graph.nodes.filter(node => node.kind === 'gap').every(node => node.traceIds?.length === 1)).toBe(true);
	});
	it('retains the latest measured path alongside a newer pending diagnostic without inventing hops', () => {
		const snapshot = makeSnapshot(), latest = makeTrace(), old = makeTrace(), pending = makeTrace('queued');
		old.id = 'old'; latest.id = 'latest'; latest.created_at += 10; pending.id = 'pending'; pending.created_at += 20; snapshot.hosts[0].traces = [old, latest, pending];
		const edges = buildRadialGraph(snapshot, true).edges.filter(edge => edge.trace);
		expect([...new Set(edges.map(edge => edge.trace!.id))].sort()).toEqual(['latest', 'pending']); expect(edges.filter(edge => edge.trace?.id === 'pending')).toHaveLength(1);
	});
	it('shows a target-IP response as unconfirmed if the diagnostic did not establish reachability', () => {
		const snapshot = makeSnapshot(); snapshot.hosts[0].traces = [makeTrace()]; snapshot.hosts[0].traces[0].result!.reached = false;
		const graph = buildRadialGraph(snapshot, true);
		expect(graph.nodes.filter(node => node.label === '203.0.113.9')).toHaveLength(1); expect(graph.edges.find(edge => edge.target === 'ip:203.0.113.9')?.state).toBe('unconfirmed');
		expect(curve({ x: 0, y: 0 }, { x: 100, y: 0 }, 1).d).not.toBe(curve({ x: 100, y: 0 }, { x: 0, y: 0 }, 1).d);
	});
});

describe('screen-space edge endpoint geometry', () => {
	it.each([0.1, 1, 30, 50, 51, 100])('retains source-to-target direction with %spx separation', length => {
		for (const direction of [-1, 1]) {
			const target = { x: direction * length, y: 0 }, shape = curve({ x: 0, y: 0 }, target, 1);
			const [startX, startY, controlX, controlY, endX, endY] = shape.d.match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/g)!.map(Number);
			expect([startX, startY, controlX, controlY, endX, endY].every(Number.isFinite)).toBe(true);
			expect((endX - startX) * direction).toBeGreaterThan(0);
			expect((endX - controlX) * direction).toBeGreaterThan(0);
			expect(startX * direction).toBeGreaterThanOrEqual(0);
			expect(endX * direction).toBeLessThanOrEqual(length);
		}
	});
	it('suppresses coincident endpoints instead of inventing a direction', () => {
		expect(curve({ x: 3, y: 4 }, { x: 3, y: 4 }, 2)).toEqual({ d: '', x: 3, y: 4 });
	});
});
