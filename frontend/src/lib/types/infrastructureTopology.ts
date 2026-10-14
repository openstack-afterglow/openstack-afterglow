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
	rates: InterfaceCounters;
	history: { ts: number; rates: InterfaceCounters }[];
}
export interface ObservedNeighbor { interface: string; ip: string; mac: string | null; state: string }
export interface ObservedRoute { interface: string; destination: string; gateway: string | null; metric: number | null }
export interface ObservedLldp { interface: string; chassis_id: string; port_id: string; system_name: string | null }
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
	sources: Record<'addresses' | 'neighbors' | 'routes' | 'lldp' | 'counters', EvidenceSource> & { peer_probes?: EvidenceSource };
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
}
