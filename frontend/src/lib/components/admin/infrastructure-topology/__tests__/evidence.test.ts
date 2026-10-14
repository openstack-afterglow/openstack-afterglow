import { afterEach, describe, expect, it } from 'vitest';
import { buildPeerProbeEdges, collapseHops, nicHistory, quantity, safeRate } from '../evidence';
import { edgeLabel, fabricErrorMessages } from '../presentation';
import { buildRadialGraph } from '../radialGraph';
import { makeHost, makeMeshSnapshot, makeTrace } from './fixtures';
import { initLocale, intlLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/infra-topology';

afterEach(() => initLocale('ko'));
describe('NIC quantities and history provenance', () => {
	it('preserves missing intervals in Bklit history and does not share NIC totals with remote endpoints', () => {
		const host = makeHost(), nic = host.observation!.interfaces[0];
		nic.history = [{ ts: 1, rates: { ...nic.rates } }, { ts: 2, rates: { rx_bytes: null, tx_bytes: null, rx_packets: null, tx_packets: null } }];
		expect(nicHistory(host, nic.name, true)).toEqual([{ timestamp: 1000, rxRate: 128, txRate: 0 }, { timestamp: 2000, rxRate: null, txRate: null }]);
		expect(nicHistory(host, nic.name, false)).toEqual([]);
		host.observation!.sources.counters = 'error'; expect(nicHistory(host, nic.name, true)).toEqual([]);
	});
	it.each([NaN, Infinity, -1, null])('keeps invalid %s values unknown rather than zero', value => {
		expect(safeRate(value)).toBeNull(); expect(quantity(value, 'rx_bytes', true)).toBe(t('unknown'));
	});
	it.each([[0.5, 0.5, 'B'], [0, 0, 'B'], [1536, 1.5, 'KiB'], [3 * 1024 ** 3, 3, 'GiB']] as const)('formats %s without invalid unit indexing', (rate, value, unit) => {
		expect(quantity(rate, 'rx_bytes', true)).toBe(t('bytesRate', { value: value.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }), unit }));
	});
});
describe('directed service-port observations', () => {
	it('retains outside-inventory targets and never invents reverse checks or whole-host failures', () => {
		const host = makeHost(); host.peer_probes = [{ target_host_id: 'outside', address: '10.0.0.20', port: 443, status: 'down', checked_at: 1_800_000_000, latency_ms: null, error: 'connection_refused' }];
		const edges = buildPeerProbeEdges([host], true);
		expect(edges).toHaveLength(1); expect(edges[0]).toMatchObject({ source: host.id, targetInInventory: false, targetName: 'outside', status: 'down', port: 443 });
		expect(host.reachability.status).toBe('up');
	});
	it.each(['stale', 'unmeasured'] as const)('marks %s probes unknown without erasing observed timestamps', state => {
		const host = makeHost(); host.observation_state = state; host.peer_probes = [{ target_host_id: 'controller:node-b', address: '10.0.0.20', port: 3306, status: 'up', checked_at: 1_800_000_000, latency_ms: 3, error: null }];
		expect(buildPeerProbeEdges([host, makeHost('controller:node-b')], true)[0]).toMatchObject({ status: 'unknown', latency_ms: null, checked_at: 1_800_000_000, targetName: 'node-b', targetInInventory: true, error: state === 'stale' ? 'probe_stale' : 'probe_unmeasured' });
	});
});
describe('trace-local gaps and localized provenance', () => {
	it('collapses only consecutive unanswered hops and preserves exact responding hops', () => {
		const trace = makeTrace(), hops = [{ hop: 1, ip: '10.0.0.1', rtt_ms: 0.2 }, ...Array.from({ length: 15 }, (_, i) => ({ hop: i + 2, ip: null, rtt_ms: null }))];
		expect(collapseHops(hops)).toEqual([{ kind: 'hop', hop: hops[0] }, { kind: 'gap', from: 2, to: 16, count: 15 }]);
		expect(collapseHops(trace.result!.hops)).toHaveLength(3);
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
