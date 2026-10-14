import type { InfrastructureTopologySnapshot, TopologyHost, TopologyTrace } from '$lib/types/infrastructureTopology';

export function makeHost(id = 'compute:node-a'): TopologyHost {
	return {
		id, name: id.split(':')[1], role: id.startsWith('storage:') ? 'storage' : id.startsWith('controller:') ? 'controller' : 'compute', address: '10.0.0.10',
		reachability: { status: 'up', checked_at: null, latency_ms: 1, error: null },
		heartbeat: { status: 'up', updated_at: null, source: 'nova-compute' }, observation_state: 'fresh', traces: [],
		observer_configured: true,
		peer_probes: [],
		observation: {
			interfaces_omitted: 0, evidence_omitted: 0,
			captured_at: 1_800_000_000, boot_id: 'boot-a',
			sources: { addresses: 'measured', counters: 'measured', routes: 'measured', neighbors: 'measured', lldp: 'measured' },
			interfaces: [{ name: 'eno1', mac: '02:00:00:00:00:10', operstate: 'UP', addresses: ['10.0.0.10/24'], ifindex: 2,
				rx_bytes: 8192, tx_bytes: 4096, rx_packets: 80, tx_packets: 40,
				rates: { rx_bytes: 128, tx_bytes: 0, rx_packets: 2, tx_packets: 0 }, history: [],
			}],
			lldp: [{ interface: 'eno1', chassis_id: '02:00:00:00:00:01', port_id: 'Ethernet1', system_name: 'switch-a' }],
			neighbors: [{ interface: 'eno1', ip: '10.0.0.1', mac: '02:00:00:00:00:01', state: 'REACHABLE' }],
			routes: [{ interface: 'eno1', destination: 'default', gateway: '10.0.0.1', metric: 100 }],
		},
	};
}
export function makeSnapshot(): InfrastructureTopologySnapshot {
	return { enabled: true, error: null, inventory_error: null, interval_seconds: 10, trace_targets: ['203.0.113.9'], hosts: [makeHost(), makeHost('controller:node-b'), makeHost('storage:node-c')] };
}
export function makeTrace(status: TopologyTrace['status'] = 'complete'): TopologyTrace {
	return {
		id: 'trace-a', target: '203.0.113.9', status, max_hops: 16, timeout_seconds: 40, created_at: 1_800_000_000, expires_at: 1_800_000_090,
		result: status === 'complete' ? { status: 'complete', reached: true, error: null, source_interface: 'eno1', next_hop: '10.0.0.1', completed_at: 1_800_000_005,
			hops: [{ hop: 1, ip: '10.0.0.1', rtt_ms: 1.2 }, { hop: 2, ip: null, rtt_ms: null }, { hop: 3, ip: '203.0.113.9', rtt_ms: 8.4 }],
		} : null,
	};
}

export function makeNetworkHosts(): TopologyHost[] {
	const hosts = [makeHost(), makeHost('controller:node-b')];
	hosts[0].traces = [makeTrace()];
	const second = makeTrace();
	second.id = 'trace-b'; second.target = '198.51.100.7';
	second.result!.hops[0].rtt_ms = 3.6;
	second.result!.hops[2].ip = second.target;
	hosts[1].traces = [second];
	return hosts;
}
