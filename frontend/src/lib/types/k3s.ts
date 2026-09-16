import type { FlavorEligibility } from './flavor';

export interface DashboardK3sStats {
  total: number;
  active: number;
  available: boolean;
}

export interface K3sCluster {
	id: string;
	name: string;
	status: string;
	status_reason: string | null;
	server_vm_id: string | null;
	agent_vm_ids: string[];
	agent_count: number;
	api_address: string | null;
	server_ip: string | null;
	network_id: string | null;
	key_name: string | null;
	k3s_version: string | null;
	created_at: string | null;
	updated_at: string | null;
	deleted_at: string | null;
	deleted_by_user_id: string | null;
	deleted_reason: string | null;
	master_count?: number;
	stampede_enabled?: boolean;
}
export interface K3sFlavor { id: string; name: string; vcpus: number; ram: number; disk: number; extra_specs?: Record<string, string>; gpu_count?: number; eligibility?: FlavorEligibility | null; }
export interface K3sNetwork { id: string; name: string; is_external: boolean; }
export interface K3sKeypair { name: string; }

export interface CloudShellTicket {
	ticket: string;
}

export interface K3sNodeHealth {
	name: string;
	role: 'server' | 'agent';
	ready: boolean;
	conditions: string[];
	kubelet_version: string | null;
}

export interface K3sClusterHealth {
	cluster_id: string;
	cluster_name: string;
	status: 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY' | 'UNREACHABLE' | 'UNKNOWN';
	api_server_reachable: boolean;
	healthz_ok: boolean;
	nodes: K3sNodeHealth[];
	checked_at: string;
	error: string | null;
	reachability: 'direct' | 'unreachable';
}

export interface K3sInterfaceInfo {
	port_id: string;
	net_id: string;
	fixed_ips: { ip_address: string; subnet_id?: string }[];
	vm_id: string;
	node_role: 'server' | 'agent';
	is_primary: boolean;
}

export interface ConfigMapInfo {
	name: string;
	namespace: string;
	data: Record<string, string>;
	binary_data: Record<string, string> | null;
	labels: Record<string, string>;
	annotations: Record<string, string>;
	created_at: string;
}

export interface SecretInfo {
	name: string;
	namespace: string;
	type: string;
	data: Record<string, string>;
	labels: Record<string, string>;
	annotations: Record<string, string>;
	created_at: string;
}

export interface K3sNodegroupVM {
	vm_id: string;
	name: string | null;
	status: string;
}

export interface K3sNodegroup {
	id: string;
	cluster_id: string;
	name: string;
	role: 'server' | 'agent';
	node_count: number;
	flavor_id: string | null;
	image_id: string | null;
	labels: Record<string, string>;
	taints: Record<string, unknown>[];
	is_default: boolean;
	// Stampede 오토스케일
	stampede_enabled: boolean;
	min_size: number;
	max_size: number;
	stampede_state: Record<string, unknown>;
	vms: K3sNodegroupVM[];
	created_at: string | null;
	updated_at: string | null;
}

export interface StampedeNodegroupStatus {
	id: string;
	name: string;
	role?: string;
	flavor_id?: string | null;
	stampede_enabled: boolean;
	min_size: number;
	max_size: number;
	node_count: number;
	in_flight?: number;
	capacity?: Record<string, { cpu_m?: number; memory_bytes?: number; gpu?: number } | unknown>;
	pending_assignments?: { namespace?: string; name?: string; resources?: Record<string, number> }[];
	blocked_reasons?: { namespace?: string; name?: string; reason?: string; message?: string }[];
	last_decision?: string;
	last_blocked_reason?: string;
	flavor_summary?: Record<string, unknown>;
	quota_state?: Record<string, unknown>;
	stampede_state: Record<string, unknown>;
}

export interface StampedeStatus {
	cluster_id: string;
	stampede_enabled: boolean;
	global_stampede_enabled: boolean;
	nodegroups: StampedeNodegroupStatus[];
}

export interface CertificateInfo {
	not_after: string;
	not_before: string;
	subject: string;
	issuer: string;
	days_remaining: number;
}

export interface CertificateExpiryResponse {
	ca: CertificateInfo | null;
	client: CertificateInfo | null;
	server_via_tls: CertificateInfo[];
}

export interface ContainerStatus {
	name: string;
	image: string;
	ready: boolean;
	restart_count: number;
	state: string;
}

export interface PodInfo {
	name: string;
	namespace: string;
	phase: string;
	ready: string;
	restarts: number;
	node: string | null;
	pod_ip: string | null;
	containers: ContainerStatus[];
	labels: Record<string, string>;
	created_at: string;
}

export interface PodLogResponse {
	name: string;
	namespace: string;
	container: string | null;
	log: string;
}

export interface ServicePort {
	name: string | null;
	port: number;
	target_port: number | string | null;
	node_port: number | null;
	protocol: string;
}

export interface ServiceInfo {
	name: string;
	namespace: string;
	type: string;
	cluster_ip: string | null;
	external_ips: string[];
	ports: ServicePort[];
	selector: Record<string, string>;
	created_at: string;
}

export interface DeploymentInfo {
	name: string;
	namespace: string;
	replicas: number;
	available: number;
	ready: number;
	updated: number;
	strategy: string;
	selector: Record<string, string>;
	images: string[];
	created_at: string;
}

export interface ReplicaSetInfo {
	name: string;
	namespace: string;
	replicas: number;
	ready: number;
	available: number;
	owner_kind: string | null;
	owner_name: string | null;
	selector: Record<string, string>;
	images: string[];
	created_at: string;
}

export interface K3sClusterTemplate {
	id: string;
	name: string;
	description: string | null;
	k3s_version: string | null;
	default_node_count: number;
	default_agent_flavor_id: string | null;
	default_image_id: string | null;
	plugins_enabled: Record<string, boolean>;
	os_type: string;
	public_visible: boolean;
	created_by: string | null;
	created_at: string | null;
	updated_at: string | null;
}
