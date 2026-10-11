// Stable catalogue shared with the user-dashboard summary contract.
export const RESOURCE_CATEGORIES = [
	'instances', 'volumes', 'floating_ips', 'networks', 'subnets', 'routers',
	'security_groups', 'load_balancers', 'images', 'keypairs', 'database_instances',
	'database_backups', 'k3s_clusters', 'waygate_gateways', 'containers', 'magnum_clusters',
	'shares', 'share_snapshots', 'share_networks', 'security_services', 'buckets',
	'volume_snapshots', 'volume_backups', 'packages', 'secrets',
] as const;

export type ResourceCategory = typeof RESOURCE_CATEGORIES[number];
export type InventoryState = 'ready' | 'disabled' | 'denied' | 'failed';

export interface ResourceItem {
	id: string;
	name: string;
	status: string;
	project_id: string;
	project_name: string;
	owner_scope: 'user' | 'project';
	owner_id: string;
	href: string;
	flavor_name?: string;
	vcpus?: number | null;
	ram_mb?: number | null;
	size?: number | null;
	volume_type?: string;
	created_at?: string;
}

export type ResourceInventory = {
	items: ResourceItem[];
	error?: string;
} & (
	| { state: 'ready'; count: number }
	| { state: Exclude<InventoryState, 'ready'>; count: null }
);

export type ResourceTotal = { known_count: number } & (
	| { state: 'ready'; count: number }
	| { state: Exclude<InventoryState, 'ready'> | 'partial'; count: null }
);

export interface ResourceUsage {
	vcpus: number | null;
	ram_mb: number | null;
	storage_gb: number | null;
}

export interface ProjectResourceInventory {
	project_id: string;
	project_name: string;
	resources: Record<ResourceCategory, ResourceInventory>;
	usage: ResourceUsage;
}

export interface UserDashboardSummary {
	user_id: string;
	current_project_id: string;
	projects: ProjectResourceInventory[];
	totals: {
		resources: Record<ResourceCategory, ResourceTotal>;
		usage: ResourceUsage;
	};
}
