import type { FloatingIpInfo } from '$lib/types/networks';

export interface SubnetDetail {
	id: string; name: string; cidr: string;
	gateway_ip: string | null; dhcp_enabled: boolean;
}
export interface TopologyNetwork {
	id: string; name: string; status: string;
	is_external: boolean; is_shared: boolean;
	project_id: string | null;
	subnet_details: SubnetDetail[];
	mtu?: number | null;
	// provider_* 는 admin 응답(GET /api/v1/admin/topology) 전용. 사용자 응답에는 키 자체가 없다.
	provider_network_type?: string | null;
	provider_segmentation_id?: number | null;
	provider_physical_network?: string | null;
}
export interface TopologyRouterRoute {
	destination: string;
	nexthop: string;
}
export interface TopologyRouter {
	id: string; name: string; status: string;
	external_gateway_network_id: string | null;
	external_gateway_ips: string[];
	interface_ips: { ip_address: string; subnet_id: string }[];
	is_distributed: boolean;
	is_ha: boolean;
	connected_subnet_ids: string[];
	dvr_subnet_ids: string[];
	project_id: string | null;
	enable_snat?: boolean | null;
	routes?: TopologyRouterRoute[];
}
export interface TopologyIpAddress {
	addr: string;
	type: string;
	network_name: string;
	network_id?: string | null;
	port_id?: string | null;
	mac_addr?: string | null;
}
export interface TopologyInstance {
	id: string; name: string; status: string;
	project_id?: string | null;
	network_names: string[];
	ip_addresses: TopologyIpAddress[];
	flavor_name?: string | null;
	image_id?: string | null;
	/** Trove 데이터베이스 인스턴스 여부 (백엔드가 Trove 인스턴스 IP 와 대조해 채운다) */
	is_database?: boolean;
}
export interface TopologyLBMember {
	id: string; address: string; protocol_port: number;
	status: string; subnet_id: string | null; pool_id: string; server_id: string | null;
}
export interface TopologyLBListener {
	id: string; name: string; protocol: string; protocol_port: number;
	default_pool_id: string | null;
}
export interface TopologyLoadBalancer {
	id: string; name: string;
	vip_address: string | null; vip_port_id: string | null;
	vip_subnet_id: string | null; vip_network_id: string | null;
	provisioning_status: string; operating_status: string;
	project_id: string | null;
	listeners: TopologyLBListener[];
	members: TopologyLBMember[];
}
export interface TopologyData {
	networks: TopologyNetwork[];
	routers: TopologyRouter[];
	instances: TopologyInstance[];
	floating_ips: FloatingIpInfo[];
	load_balancers?: TopologyLoadBalancer[];
}
export interface TrafficRate { rx_bps: number; tx_bps: number; }
export interface TopologyTrafficInterface {
	instance_id: string;
	network_id: string;
	mac_address: string;
	rx_bps: number;
	tx_bps: number;
}
/** 네트워크 사용량 히스토리 1 샘플 (30초 rate 윈도우) */
export interface TrafficHistoryPoint { ts: number; rx_bps: number; tx_bps: number; }
/**
 * 방향별 통계. 표본이 없으면 각 항목 null (0 과 구분한다).
 *
 * 합계가 아니라 방향별인 이유: 패널의 `합산 트래픽` 행이 `▼ rx ▲ tx` 로 방향별이라,
 * 합계로 두면 같은 화면에서 대조할 수 없는 세 번째 숫자가 된다.
 * `max` 의 rx·tx 는 서로 다른 시점일 수 있다(각 방향의 독립적인 최고값).
 */
export interface TrafficHistoryStats {
	avg: TrafficRate | null;
	max: TrafficRate | null;
	latest: TrafficRate | null;
}
export interface TopologyTrafficHistory {
	network_id: string;
	range: string;
	/** 샘플 간격(초). rate 윈도우 이하임이 백엔드에서 보장된다 */
	step_s: number;
	/** 백엔드 rate 윈도우 문자열(예: "30s") */
	window: string;
	series: TrafficHistoryPoint[];
	stats: TrafficHistoryStats;
	_meta?: { source?: string; router_traffic?: string };
}
export interface TopologyTraffic {
	ts: number;
	instances: Record<string, TrafficRate>;
	networks: Record<string, TrafficRate>;
	routers: Record<string, TrafficRate>;
	load_balancers: Record<string, TrafficRate>;
	interfaces?: Record<string, TopologyTrafficInterface>;
	_meta?: { router_traffic?: string };
}
