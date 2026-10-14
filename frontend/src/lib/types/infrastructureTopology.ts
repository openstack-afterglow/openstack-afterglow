import type { MonitoredHost } from './hostHealth';

export interface TopologyAuthority {
	token?: string;
	userId?: string;
	projectId?: string;
	admin: boolean;
	ready: boolean;
}
export type EvidenceSource = 'measured' | 'unsupported' | 'error';
export type ObservationState = 'fresh' | 'stale' | 'unmeasured';
export interface PeerProbe {
	target_host_id: string;
	address: string;
	port: number;
	status: 'up' | 'down' | 'unknown';
	checked_at: number | null;
	latency_ms: number | null;
	error: 'connection_refused' | 'timeout' | 'network_unreachable' | 'probe_error' | 'source_unavailable' | 'probe_stale' | 'probe_unmeasured' | null;
}
export interface InterfaceCounters {
	rx_bytes: number | null;
	tx_bytes: number | null;
	rx_packets: number | null;
	tx_packets: number | null;
}
export interface ObservedInterface extends InterfaceCounters {
	name: string;
	mac: string | null;
	operstate: string;
	addresses: string[];
	ifindex: number | null;
	physical: boolean | null;
	rates: InterfaceCounters;
	history: { ts: number; rates: InterfaceCounters }[];
}
export interface ObservedNeighbor { interface: string; ip: string; mac: string | null; state: string }
export interface ObservedRoute { interface: string; destination: string; gateway: string | null; metric: number | null }
export interface ObservedLldp {
	interface: string; chassis_id: string; port_id: string; system_name: string | null;
	management_address?: string | null; port_description?: string | null;
}
export interface HostObservation {
	captured_at: number;
	boot_id: string;
	interfaces: ObservedInterface[];
	interfaces_omitted?: number;
	evidence_omitted?: number;
	neighbors: ObservedNeighbor[];
	routes: ObservedRoute[];
	lldp: ObservedLldp[];
	peer_probes?: PeerProbe[];
	sources: Record<'addresses' | 'neighbors' | 'routes' | 'lldp' | 'counters' | 'flows', EvidenceSource> & { peer_probes?: EvidenceSource };
}
export type TraceStatus = 'queued' | 'running' | 'complete' | 'unsupported' | 'error' | 'expired';
export type TraceError = 'traceroute_missing' | 'local_target_denied' | 'command_failed' | 'timeout' | 'route_unavailable';
export interface TraceResult {
	status: 'complete' | 'unsupported' | 'error';
	hops: { hop: number; ip: string | null; rtt_ms: number | null }[];
	reached: boolean;
	error: TraceError | null;
	source_interface: string | null;
	next_hop: string | null;
	completed_at: number;
}
export interface TopologyTrace {
	id: string;
	target: string;
	max_hops: number;
	timeout_seconds: number;
	status: TraceStatus;
	created_at: number;
	expires_at: number;
	result: TraceResult | null;
}
export interface TopologyHost extends Pick<MonitoredHost, 'id' | 'name' | 'role' | 'address' | 'reachability' | 'heartbeat'> {
	observation: HostObservation | null;
	observation_state: ObservationState;
	observer_configured: boolean;
	traces: TopologyTrace[];
	peer_probes: PeerProbe[];
}
export interface InfrastructureTopologySnapshot {
	enabled: boolean;
	error: string | null;
	inventory_error: string | null;
	interval_seconds: number;
	trace_targets: string[];
	hosts: TopologyHost[];
	flows: TopologyFlow[];
	fabric: FabricSnapshot;
}

export type MeasurementState = ObservationState | 'error';
export type MeasurementReason = 'first_sample' | 'counter_reset' | 'collector_reset' | 'overflow' | 'stale_sample' | 'collector_error';
/** Rates are computed server-side from continuous uint64 counters; raw flow counters never cross this boundary. */
export interface TopologyFlow {
	id: string;
	source_host_id: string;
	target_host_id: string;
	reporting_host_id: string;
	interface: string;
	direction: 'ingress' | 'egress';
	captured_at: number;
	window_seconds: number | null;
	packets_per_second: number | null;
	bytes_per_second: number | null;
	state: MeasurementState;
	measurement: 'linux_skb_header_counter';
	reason?: MeasurementReason | null;
}
export interface FabricEndpoint { kind: 'host' | 'switch'; id: string; port: string }
export interface SwitchPort {
	id: string; device_id: string; ifindex: number; name: string;
	physical?: boolean | null;
	captured_at: number | null; state: MeasurementState; operstate: 'up' | 'down' | 'unknown';
	window_seconds: number | null;
	rx_packets_per_second: number | null; tx_packets_per_second: number | null;
	rx_bytes_per_second: number | null; tx_bytes_per_second: number | null;
	measurement: 'snmp_if_mib';
	reason?: MeasurementReason | null;
}
export interface FabricLink {
	id: string; source: FabricEndpoint; target: FabricEndpoint;
	captured_at: number; state: ObservationState; evidence: 'lldp';
	source_port_id: string | null; target_port_id: string | null;
}
export interface FabricDevice { id: string; name: string; chassis_id: string; state: MeasurementState }
export interface FabricSnapshot {
	state: 'unconfigured' | 'available' | 'partial' | 'unavailable';
	generated_at: number;
	devices: FabricDevice[]; ports: SwitchPort[]; links: FabricLink[];
	coverage: { description: string; last_observed_at: number | null; error: string | null };
}
export interface TopologySelection { kind: 'node' | 'edge'; id: string }
