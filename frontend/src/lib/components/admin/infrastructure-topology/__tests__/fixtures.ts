import type { FabricSnapshot, InfrastructureTopologySnapshot, SwitchPort, TopologyFlow, TopologyHost, TopologyTrace } from '$lib/types/infrastructureTopology';

export function makeHost(id = 'compute:node-a'): TopologyHost {
	return {
		id, name: id.split(':')[1], role: id.startsWith('storage:') ? 'storage' : id.startsWith('controller:') ? 'controller' : 'compute', address: '10.0.0.10',
		reachability: { status: 'up', checked_at: null, latency_ms: 1, error: null },
		heartbeat: { status: 'up', updated_at: null, source: 'nova-compute' }, observation_state: 'fresh', traces: [],
		observer_configured: true, peer_probes: [],
		observation: {
			interfaces_omitted: 0, evidence_omitted: 0, captured_at: 1_800_000_000, boot_id: 'boot-a',
			sources: { addresses: 'measured', counters: 'measured', routes: 'measured', neighbors: 'measured', lldp: 'measured', flows: 'unsupported' },
			interfaces: [{ name: 'eno1', mac: '02:00:00:00:00:10', operstate: 'UP', addresses: ['10.0.0.10/24'], ifindex: 2, physical: true,
				rx_bytes: 8192, tx_bytes: 4096, rx_packets: 80, tx_packets: 40,
				rates: { rx_bytes: 128, tx_bytes: 0, rx_packets: 2, tx_packets: 0 }, history: [],
			}],
			lldp: [{ interface: 'eno1', chassis_id: '02:00:00:00:00:01', port_id: 'Ethernet1', system_name: 'switch-a', management_address: '192.168.0.2', port_description: 'host access' }],
			neighbors: [{ interface: 'eno1', ip: '10.0.0.1', mac: '02:00:00:00:00:01', state: 'REACHABLE' }],
			routes: [{ interface: 'eno1', destination: 'default', gateway: '10.0.0.1', metric: 100 }],
		},
	};
}
export function makeSnapshot(): InfrastructureTopologySnapshot {
	return { enabled: true, error: null, inventory_error: null, interval_seconds: 10, trace_targets: ['203.0.113.9'],
		hosts: [makeHost(), makeHost('controller:node-b'), makeHost('storage:node-c')], flows: [],
		fabric: { state: 'unconfigured', generated_at: 1_800_000_000, devices: [], ports: [], links: [], coverage: { description: 'SNMPv3 IF-MIB and LLDP evidence', last_observed_at: null, error: null } },
	};
}
export function makeFlow(overrides: Partial<TopologyFlow> = {}): TopologyFlow {
	return { id: `flow:${'a'.repeat(64)}`, source_host_id: 'compute:node-a', target_host_id: 'storage:node-c', reporting_host_id: 'compute:node-a', interface: 'eno1', direction: 'egress', captured_at: 1_800_000_000, window_seconds: 10, packets_per_second: 12, bytes_per_second: 3072, state: 'fresh', reason: null, measurement: 'linux_skb_header_counter', ...overrides };
}
export function makePort(overrides: Partial<SwitchPort> = {}): SwitchPort {
	return { id: 'switch:sw-a:if:5', device_id: 'switch:sw-a', ifindex: 5, name: 'Ethernet5', physical: true, captured_at: 1_800_000_000, state: 'fresh', reason: null, operstate: 'up', window_seconds: 10, rx_packets_per_second: 14, tx_packets_per_second: 3, rx_bytes_per_second: 3584, tx_bytes_per_second: 768, measurement: 'snmp_if_mib', ...overrides };
}
export function makeFabric(): FabricSnapshot {
	const ports = [makePort(), makePort({ id: 'switch:sw-a:if:6', ifindex: 6, name: 'Ethernet6' }), makePort({ id: 'switch:sw-b:if:8', device_id: 'switch:sw-b', ifindex: 8, name: 'Ethernet8' })];
	return { state: 'available', generated_at: 1_800_000_000,
		devices: [{ id: 'switch:sw-a', name: 'switch-a', chassis_id: '02:00:00:00:00:01', state: 'fresh' }, { id: 'switch:sw-b', name: 'switch-b', chassis_id: '02:00:00:00:00:02', state: 'fresh' }], ports,
		links: ['compute:node-a', 'controller:node-b', 'storage:node-c'].map((id, index) => ({
			id: `fabric-link:${index}`, source: { kind: 'host', id, port: 'eno1' }, target: { kind: 'switch', id: ports[index].device_id, port: ports[index].name }, source_port_id: null, target_port_id: ports[index].id, captured_at: 1_800_000_000, state: 'fresh', evidence: 'lldp',
		})), coverage: { description: 'SNMPv3 IF-MIB and LLDP evidence', last_observed_at: 1_800_000_000, error: null },
	};
}
export function makeMeshSnapshot(): InfrastructureTopologySnapshot {
	const snapshot = makeSnapshot(); snapshot.fabric = makeFabric();
	snapshot.flows = [makeFlow(), makeFlow({ id: `flow:${'b'.repeat(64)}`, reporting_host_id: 'storage:node-c', direction: 'ingress', packets_per_second: 9, bytes_per_second: 2304 })];
	for (const [index, host] of snapshot.hosts.entries()) {
		host.observation!.sources.flows = 'measured';
		host.observation!.lldp[0].chassis_id = snapshot.fabric.devices[index === 2 ? 1 : 0].chassis_id;
		host.observation!.lldp[0].port_id = snapshot.fabric.ports[index].name;
	}
	return snapshot;
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
	const hosts = [makeHost(), makeHost('controller:node-b')]; hosts[0].traces = [makeTrace()];
	const second = makeTrace(); second.id = 'trace-b'; second.target = '198.51.100.7'; second.result!.hops[0].rtt_ms = 3.6; second.result!.hops[2].ip = second.target;
	hosts[1].traces = [second]; return hosts;
}
