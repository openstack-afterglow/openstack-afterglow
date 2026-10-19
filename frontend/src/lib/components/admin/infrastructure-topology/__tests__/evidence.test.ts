import { afterEach, describe, expect, it } from 'vitest';
import { buildNetworkMap, buildNicEvidence, buildPeerProbeEdges, collapseHops, nicHistory, quantity, safeRate } from '../evidence';
import { edgeLabel, fabricErrorMessages } from '../presentation';
import { buildRadialGraph } from '../radialGraph';
import { makeHost, makeMeshSnapshot, makeNetworkHosts, makeTrace } from './fixtures';
import { initLocale, intlLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/infra-topology';

afterEach(() => initLocale('ko'));

describe('NIC evidence and directional traffic', () => {
	it('keeps LLDP physical links distinct from IP neighbors and routing evidence', () => {
		const host = makeHost(); const [row] = buildNicEvidence(host, true);
		expect(row.physical).toEqual([{ chassis: '02:00:00:00:00:01', port: 'Ethernet1', name: 'switch-a' }]);
		expect(row.neighbors).toEqual([{ ip: '10.0.0.1', mac: '02:00:00:00:00:01', state: 'REACHABLE' }]);
		expect(row.routes).toEqual([{ destination: 'default', gateway: '10.0.0.1', metric: 100 }]);
		host.observation!.lldp = []; expect(buildNicEvidence(host, true)[0].physical).toEqual([]);
		expect(buildNicEvidence(host, true)[0].neighbors).toHaveLength(1);
	});
	it('does not assign interface totals or rates to any remote endpoint', () => {
		const row = buildNicEvidence(makeHost(), true)[0];
		for (const edge of [...row.physical, ...row.neighbors, ...row.routes]) {
			expect(edge).not.toHaveProperty('rx_bytes'); expect(edge).not.toHaveProperty('tx_packets'); expect(edge).not.toHaveProperty('rates');
		}
	});
	it.each([false, true])('animates independently only fresh positive rates with verified=%s', verified => {
		const host = makeHost(); const [fresh] = buildNicEvidence(host, verified);
		expect(fresh.rxActive).toBe(verified); expect(fresh.txActive).toBe(false);
		host.observation_state = 'stale'; const [stale] = buildNicEvidence(host, verified); expect(stale.rxActive).toBe(false); expect(stale.txActive).toBe(false);
	});
	it('retains positive packet-rate direction when byte rate is unknown and hides reset/null directions', () => {
		const host = makeHost(), rates = host.observation!.interfaces[0].rates;
		rates.rx_bytes = null; rates.tx_bytes = null; rates.tx_packets = 3;
		expect(buildNicEvidence(host, true)[0]).toMatchObject({ rxActive: true, txActive: true });
		rates.rx_packets = null; rates.tx_packets = 0;
		expect(buildNicEvidence(host, true)[0]).toMatchObject({ rxActive: false, txActive: false });
	});
	it('does not publish residual edges from failed/unsupported source collections', () => {
		const host = makeHost(); host.observation!.sources.lldp = 'unsupported'; host.observation!.sources.neighbors = 'error'; host.observation!.sources.routes = 'error'; host.observation!.sources.counters = 'error';
		expect(buildNicEvidence(host, true)[0]).toMatchObject({ physical: [], neighbors: [], routes: [], rxActive: false, txActive: false });
	});
	it('does not substitute host heartbeat for absent NIC evidence', () => {
		const host = makeHost(); host.observation = null; expect(buildNicEvidence(host, true)).toEqual([]);
	});
});

describe('directed TCP peer evidence', () => {
	it('keeps source→service-port direction, never invents reverse edges and creates outside-inventory endpoints', () => {
		const host = makeHost(); host.peer_probes = [{ target_host_id: 'controller:node-z', address: '10.0.0.20', port: 443, status: 'up', checked_at: 1_800_000_000, latency_ms: 2.1, error: null }];
		const edges = buildPeerProbeEdges([host], true);
		expect(edges).toHaveLength(1); expect(edges[0]).toMatchObject({ source: host.id, target_host_id: 'controller:node-z', targetName: 'controller:node-z', targetInInventory: false, port: 443, status: 'up' });
		expect(host.reachability.status).toBe('up');
		host.peer_probes[0].status = 'down'; expect(buildPeerProbeEdges([host], true)[0].status).toBe('down'); expect(host.reachability.status).toBe('up');
	});
	it.each(['stale', 'unmeasured'] as const)('marks %s probe directions unknown and drops latency without erasing recorded timestamps', state => {
		const host = makeHost(); host.observation_state = state; host.peer_probes = [{ target_host_id: 'controller:node-b', address: '10.0.0.20', port: 3306, status: 'up', checked_at: 1_800_000_000, latency_ms: 3, error: null }];
		const edges = buildPeerProbeEdges([host, makeHost('controller:node-b')], true);
		expect(edges[0]).toMatchObject({ status: 'unknown', latency_ms: null, checked_at: 1_800_000_000, targetName: 'node-b', targetInInventory: true });
		expect(edges[0].error).toBe(state === 'stale' ? 'probe_stale' : 'probe_unmeasured');
	});
	it('never treats unverified snapshot or configured-but-unmeasured probes as successful', () => {
		const host = makeHost(); host.peer_probes = [{ target_host_id: 'controller:node-b', address: '10.0.0.20', port: 443, status: 'unknown', checked_at: null, latency_ms: null, error: 'probe_unmeasured' }];
		expect(buildPeerProbeEdges([host], true)[0].status).toBe('unknown');
		host.peer_probes[0].status = 'up'; expect(buildPeerProbeEdges([host], false)[0]).toMatchObject({ status: 'unknown', latency_ms: null, error: 'probe_stale' });
	});
});

describe('whole-network evidence graph', () => {
	it('merges shared router IPs and RTT ranges while keeping non-response gaps separate', () => {
		const graph = buildNetworkMap(makeNetworkHosts(), true);
		const routers = graph.nodes.filter(node => node.kind === 'router');
		expect(routers).toHaveLength(1);
		expect(routers[0]).toMatchObject({ label: '10.0.0.1', minHop: 1, rttMin: 1.2, rttMax: 3.6 });
		expect(routers[0].pathIds).toHaveLength(2);
		const gaps = graph.nodes.filter(node => node.kind === 'gap');
		expect(gaps).toHaveLength(2); expect(gaps[0].id).not.toBe(gaps[1].id);
		expect(gaps.every(node => node.pathIds.length === 1 && node.label === '*')).toBe(true);
	});
	it('collapses a consecutive no-reply run into one gap per path without widening the map per hop', () => {
		const host = makeHost(), trace = makeTrace();
		trace.target = '192.0.2.99'; trace.result!.reached = false;
		trace.result!.hops = [{ hop: 1, ip: '10.0.0.1', rtt_ms: 0.2 }, ...Array.from({ length: 15 }, (_, index) => ({ hop: index + 2, ip: null, rtt_ms: null }))];
		host.traces = [trace];
		const graph = buildNetworkMap([host], true);
		const gaps = graph.nodes.filter(node => node.kind === 'gap');
		expect(gaps).toHaveLength(1);
		expect(gaps[0]).toMatchObject({ minHop: 2, maxHop: 16, column: 2, rttMin: null });
		expect(graph.nodes.find(node => node.kind === 'destination')).toMatchObject({ label: '192.0.2.99', column: 3 });
		expect(graph.edges.at(-1)).toMatchObject({ state: 'unconfirmed', dashed: true });
		expect(graph.width).toBe(210 + 3 * 250 + 220);
		expect(collapseHops(trace.result!.hops)).toEqual([{ kind: 'hop', hop: trace.result!.hops[0] }, { kind: 'gap', from: 2, to: 16, count: 15 }]);
	});
	it('does not duplicate a reached target hop and leaves unreached final segments dashed', () => {
		const hosts = makeNetworkHosts();
		hosts[1].traces[0].result!.hops.pop(); hosts[1].traces[0].result!.reached = false;
		const graph = buildNetworkMap(hosts, true);
		expect(graph.nodes.filter(node => node.label === hosts[0].traces[0].target)).toHaveLength(1);
		expect(graph.paths[0].nodeIds).toHaveLength(4);
		expect(graph.edges.filter(edge => edge.pathId === graph.paths[0].id).every(edge => !edge.dashed)).toBe(true);
		expect(graph.edges.filter(edge => edge.pathId === graph.paths[1].id).at(-1)).toMatchObject({ dashed: true, state: 'unconfirmed' });
	});
	it.each(['complete', 'error'] as const)('keeps a target-IP hop with unreached %s result as one unconfirmed destination', status => {
		const host = makeHost(), trace = makeTrace();
		trace.result!.reached = false; trace.result!.status = status;
		trace.status = status; host.traces = [trace];
		const graph = buildNetworkMap([host], true);
		expect(graph.nodes.filter(node => node.label === trace.target)).toHaveLength(1);
		expect(graph.nodes.find(node => node.label === trace.target)?.kind).toBe('destination');
		expect(graph.paths[0].nodeIds).toHaveLength(4);
		expect(graph.edges.at(-1)).toMatchObject({ state: 'unconfirmed', dashed: true });
		expect(graph.edges.some(edge => edge.source === edge.target)).toBe(false);
	});
	it.each(['queued', 'running', 'error', 'unsupported'] as const)('shows %s diagnostics without inventing hops', status => {
		const host = makeHost(); host.traces = [makeTrace(status)];
		if (status === 'error' || status === 'unsupported') host.traces[0].result = { ...makeTrace().result!, status, hops: [], reached: false, error: 'command_failed' };
		const graph = buildNetworkMap([host], true);
		expect(graph.paths[0].hops).toEqual([]);
		expect(graph.nodes.map(node => node.kind)).toEqual(['host', 'destination']);
		expect(graph.edges).toHaveLength(1); expect(graph.edges[0]).toMatchObject({ state: status, dashed: true });
	});
	it('keeps only the latest measured path per target alongside a newer pending diagnostic', () => {
		const host = makeHost(), old = makeTrace(), latest = makeTrace(), pending = makeTrace('queued');
		old.id = 'old'; latest.id = 'latest'; latest.created_at += 10; pending.id = 'pending'; pending.created_at += 20;
		host.traces = [old, pending, latest];
		const graph = buildNetworkMap([host], true);
		expect(graph.paths.map(path => path.id)).toEqual([`${host.id}:latest`, `${host.id}:pending`]);
		expect(graph.paths[1].hops).toHaveLength(0);
	});
	it('flags stale and unverified paths and uses deterministic fixed coordinates independent of inventory order', () => {
		const hosts = makeNetworkHosts(); hosts[1].observation_state = 'stale';
		const graph = buildNetworkMap(hosts, true);
		expect(graph.paths.map(path => path.stale)).toEqual([false, true]);
		expect(graph.edges.filter(edge => edge.pathId === graph.paths[1].id).every(edge => edge.stale)).toBe(true);
		expect(buildNetworkMap(hosts, false).paths.every(path => path.stale)).toBe(true);
		expect(buildNetworkMap([...hosts].reverse(), true)).toEqual(graph);
		expect(graph.nodes.filter(node => node.kind === 'host').map(node => [node.x, node.y])).toEqual([[210, 50], [210, 160]]);
		expect(graph.nodes.find(node => node.kind === 'router')).toMatchObject({ x: 460, y: 50, column: 1 });
	});
	it('integrates directed peer probes and retains outside-inventory endpoints', () => {
		const hosts = makeNetworkHosts();
		hosts[0].peer_probes = [{ target_host_id: hosts[1].id, address: '10.0.0.20', port: 443, status: 'up', checked_at: 1, latency_ms: 2, error: null }, { target_host_id: 'outside', address: '10.0.0.99', port: 3306, status: 'down', checked_at: 1, latency_ms: null, error: 'timeout' }];
		const graph = buildNetworkMap(hosts, true);
		expect(graph.edges.filter(edge => edge.kind === 'probe')).toHaveLength(2);
		expect(graph.edges.find(edge => edge.target === `host:${hosts[1].id}`)).toMatchObject({ source: `host:${hosts[0].id}`, state: 'up' });
		expect(graph.nodes.find(node => node.kind === 'peer')?.label).toContain('10.0.0.99:3306');
	});
});

describe('NIC quantities and history', () => {
	it('scales widths against all host NIC byte rates and preserves null history intervals', () => {
		const host = makeHost(), nic = host.observation!.interfaces[0];
		nic.history = [{ ts: 1, rates: { ...nic.rates } }, { ts: 2, rates: { rx_bytes: null, tx_bytes: null, rx_packets: null, tx_packets: null } }];
		host.observation!.interfaces.push({ ...nic, name: 'eno2', rates: { ...nic.rates, rx_bytes: 4096 } });
		const rows = buildNicEvidence(host, true);
		expect(rows[1].rxWidth).toBe(6.5); expect(rows[0].rxWidth).toBeLessThan(rows[1].rxWidth);
		expect(rows[0].history).toEqual([{ timestamp: 1000, rxRate: 128, txRate: 0 }, { timestamp: 2000, rxRate: null, txRate: null }]);
		expect(buildNicEvidence(host, false)[0]).toMatchObject({ history: [], rxWidth: 1.5, rates: { rx_bytes: null, tx_bytes: null, rx_packets: null, tx_packets: null } });
	});
	it('never publishes non-finite or unmeasured quantities', () => {
		const host = makeHost(); host.observation!.interfaces[0].rates.rx_bytes = Infinity;
		expect(buildNicEvidence(host, true)[0].rates.rx_bytes).toBeNull();
		host.observation!.sources.counters = 'error';
		expect(buildNicEvidence(host, true)[0]).toMatchObject({ rateState: 'unknown', history: [], rxWidth: 1.5, rxActive: false });
	});
});

describe('NIC quantities and history provenance', () => {
	it('preserves missing intervals in Bklit history and rejects unverified or unmeasured history', () => {
		const host = makeHost(), nic = host.observation!.interfaces[0];
		nic.history = [{ ts: 1, rates: { ...nic.rates } }, { ts: 2, rates: { rx_bytes: null, tx_bytes: null, rx_packets: null, tx_packets: null } }];
		expect(nicHistory(host, nic.name, true)).toEqual([{ timestamp: 1000, rxRate: 128, txRate: 0 }, { timestamp: 2000, rxRate: null, txRate: null }]);
		expect(nicHistory(host, nic.name, false)).toEqual([]);
		host.observation!.sources.counters = 'error'; expect(nicHistory(host, nic.name, true)).toEqual([]);
	});
	it.each([NaN, Infinity, -1, null])('keeps invalid %s rates unknown in both NIC consumers', value => {
		expect(safeRate(value)).toBeNull(); expect(quantity(value, 'rx_bytes', true)).toBe(t('unknown'));
		const host = makeHost(), nic = host.observation!.interfaces[0];
		nic.rates = { rx_bytes: value, tx_bytes: value, rx_packets: value, tx_packets: value };
		nic.history = [{ ts: 1, rates: { ...nic.rates } }];
		expect(buildNicEvidence(host, true)[0]).toMatchObject({ rates: { rx_bytes: null, tx_bytes: null, rx_packets: null, tx_packets: null }, rxActive: false, txActive: false, rxWidth: 1.5, txWidth: 1.5 });
		expect(nicHistory(host, nic.name, true)).toEqual([{ timestamp: 1000, rxRate: null, txRate: null }]);
	});
	it.each([[0.5, 0.5, 'B'], [0, 0, 'B'], [1536, 1.5, 'KiB'], [3 * 1024 ** 3, 3, 'GiB']] as const)('formats %s without invalid unit indexing', (rate, value, unit) => {
		expect(quantity(rate, 'rx_bytes', true)).toBe(t('bytesRate', { value: value.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }), unit }));
	});
});

describe('trace-local gaps and localized radial provenance', () => {
	it('sorts hops without mutating input and never joins nonconsecutive unanswered hops', () => {
		const hops = [{ hop: 5, ip: null, rtt_ms: null }, { hop: 2, ip: null, rtt_ms: null }, { hop: 1, ip: '10.0.0.1', rtt_ms: 0.2 }, { hop: 3, ip: null, rtt_ms: null }];
		expect(collapseHops(hops)).toEqual([{ kind: 'hop', hop: hops[2] }, { kind: 'gap', from: 2, to: 3, count: 2 }, { kind: 'gap', from: 5, to: 5, count: 1 }]);
		expect(hops.map(hop => hop.hop)).toEqual([5, 2, 1, 3]);
		expect(collapseHops(makeTrace().result!.hops)).toHaveLength(3);
	});
	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('labels actual counter-reset evidence and multiple fabric faults in %s', locale => {
		initLocale(locale); const snapshot = makeMeshSnapshot();
		snapshot.flows = [{ ...snapshot.flows[0], state: 'unmeasured', reason: 'counter_reset', packets_per_second: null, bytes_per_second: null, window_seconds: null }];
		const graph = buildRadialGraph(snapshot, true), edge = graph.edges.find(row => row.layer === 'flow')!;
		expect(edgeLabel(edge, graph, 'pps')).toContain(t('workspace.reason.counter_reset'));
		expect(edgeLabel(edge, graph, 'pps')).toContain(t('unknown'));
		expect(fabricErrorMessages('snmp_authentication,snmp_timeout')).toEqual([t('workspace.fabricError.snmp_authentication'), t('workspace.fabricError.snmp_timeout')]);
		expect(fabricErrorMessages('unsafe unbounded detail')).toEqual([t('workspace.fabricError.snmp_collector_error')]);
	});
});
