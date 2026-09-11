// wire 타입은 $lib/types/topology 가 정본이며 여기서는 재수출만 한다.
export type {
	SubnetDetail,
	TopologyNetwork,
	TopologyRouter,
	TopologyRouterRoute,
	TopologyIpAddress,
	TopologyInstance,
	TopologyLBMember,
	TopologyLBListener,
	TopologyLoadBalancer,
	TopologyData,
	TrafficRate,
	TopologyTrafficInterface,
	TopologyTraffic,
} from '$lib/types/topology';
export type { FloatingIpInfo, FloatingIpDetail } from '$lib/types/networks';
import type { TopologyLoadBalancer } from '$lib/types/topology';

// Internal derived types used across topology components
export interface ItemRow {
	type: 'router' | 'instance';
	id: string;
	name: string;
	status: string;
	connectedNetIds: string[];
	netIps: Map<string, string[]>;
	floatingNetIps: Map<string, string[]>;
	leftIdx: number;
	rightIdx: number;
}
export interface LBItem {
	lb: TopologyLoadBalancer;
	vipNetId: string | null;
}
export interface Anchor { x: number; y: number; }
