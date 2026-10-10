// Waygate standalone API responses, forwarded by the authenticated Afterglow BFF.

export interface WaygateServer {
	id: string;
	project_id: string;
	name: string;
	status: string;
	status_reason: string | null;
	server_vm_id: string | null;
	endpoint_ip: string | null;
	listen_port: number;
	tunnel_cidr: string;
	dns: string | null;
	persistent_keepalive: number;
	server_public_key: string | null;
	created_at: string | null;
	updated_at: string | null;
	// Redis 최신 상태 병합 (에이전트가 마지막으로 보고한 시각/피어 수)
	last_status_reported_at: string | null;
	peer_count: number | null;
	report_interval_seconds?: number | null;
}

export interface WaygateServerCreateRequest {
	name?: string;
	dns?: string | null;
	persistent_keepalive?: number;
}

export interface WaygateServerUpdateRequest {
	dns?: string | null;
	persistent_keepalive?: number;
}

export interface WaygateClient {
	id: string;
	server_id: string;
	project_id: string;
	/** Missing/null legacy ownership never grants a connect-only user profile access. */
	owner_user_id?: string | null;
	name: string;
	enabled: boolean;
	public_key: string;
	tunnel_ip: string;
	allowed_ips: string[];
	dns: string | null;
	mtu: number | null;
	persistent_keepalive: number;
	inherit_dns?: boolean;
	inherit_persistent_keepalive?: boolean;
	psk_enabled: boolean;
	created_at: string | null;
	updated_at: string | null;
	// Redis 상태 병합
	online: boolean | null;
	last_handshake_at: string | null;
	last_reported_at: string | null;
	report_interval_seconds?: number | null;
	// Gateway perspective peer counters; UI client RX is tx_bytes and client TX is rx_bytes.
	rx_bytes: number | null;
	tx_bytes: number | null;
}

/** One-time issuance response; plaintext is omitted when issued for another owner. */
export interface WaygateClientCreateResult extends WaygateClient {
	tunnel_conf: string | null;
}

export interface WaygateClientCreateRequest {
	name: string;
	owner_user_id?: string | null;
	allowed_ips?: string[];
	dns?: string | null;
	mtu?: number | null;
	persistent_keepalive?: number;
}

export interface WaygateClientUpdateRequest {
	name?: string;
	owner_user_id?: string;
	enabled?: boolean;
	dns?: string | null;
	mtu?: number | null;
	persistent_keepalive?: number;
	inherit_dns?: boolean;
	inherit_persistent_keepalive?: boolean;
}

// 네트워크 연결 (Phase 2) — 멀티 NIC + SNAT
export interface WaygateNetworkAttachment {
	id: number;
	server_id: string;
	project_id: string;
	network_id: string;
	subnet_id: string | null;
	port_id: string | null;
	cidr: string | null;
	nat_mode: string;
	status: string;
	created_at: string | null;
	updated_at: string | null;
}

export interface WaygateNetworkAttachRequest {
	network_id: string;
	subnet_id?: string;
	nat_mode?: string;
}

// 백업 / 마이그레이션 (Phase 3)
export interface WaygateExportResult {
	export_scope: 'caller_owned_and_unassigned_profiles';
	excluded_assigned_client_count: number;
	excluded_assigned_client_ids: string[];
	[field: string]: unknown;
}

export interface WaygateImportResult {
	imported: number;
	skipped: { name?: string; reason: string }[];
}
