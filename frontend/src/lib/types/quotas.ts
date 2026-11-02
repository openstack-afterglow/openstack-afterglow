export interface Project { id: string; name: string; }
export interface QuotaLimit extends QuotaItem { reserved?: number; }
export interface ComputeQuotas {
	instances?: QuotaLimit;
	cores?: QuotaLimit;
	ram?: QuotaLimit;
	metadata_items?: QuotaLimit;
	key_pairs?: QuotaLimit;
	server_groups?: QuotaLimit;
	server_group_members?: QuotaLimit;
	injected_files?: QuotaLimit;
	injected_file_content_bytes?: QuotaLimit;
	injected_file_path_bytes?: QuotaLimit;
	[key: string]: QuotaLimit | undefined;
}
export interface VolumeQuotas {
	volumes?: QuotaLimit;
	snapshots?: QuotaLimit;
	gigabytes?: QuotaLimit;
	[key: string]: QuotaLimit | undefined;
}
export interface NetworkQuotas {
	network?: QuotaLimit;
	subnet?: QuotaLimit;
	port?: QuotaLimit;
	router?: QuotaLimit;
	floatingip?: QuotaLimit;
	security_group?: QuotaLimit;
	security_group_rule?: QuotaLimit;
	[key: string]: QuotaLimit | undefined;
}
export interface FileStorageQuotas {
	shares?: QuotaLimit;
	gigabytes?: QuotaLimit;
	snapshots?: QuotaLimit;
	snapshot_gigabytes?: QuotaLimit;
	share_networks?: QuotaLimit;
	share_groups?: QuotaLimit;
	share_group_snapshots?: QuotaLimit;
	[key: string]: QuotaLimit | undefined;
}
export interface Quotas {
	compute: ComputeQuotas | null;
	volume: VolumeQuotas | null;
	network: NetworkQuotas | null;
	file_storage: FileStorageQuotas | null;
	project_id?: string;
	availability?: Record<string, boolean>;
	errors?: Record<string, string>;
}
export interface QuotaUpdateResponse {
	status: 'updated' | 'partial';
	updated: string[];
	errors: Record<string, string>;
}
export interface GpuQuota extends QuotaItem { gpu_type: string; available: number; }
export interface GpuDefaultQuota { gpu_type: string; limit: number; }
export interface QuotaItem {
	limit: number;
	in_use: number;
	available?: number | null;
	quota_scope?: 'project' | 'domain';
	domain_id?: string | null;
	project_limit?: number | null;
	project_in_use?: number | null;
	native_project_limit?: number | null;
}
export interface ComputePoolSummary {
	state: 'unmanaged' | 'active' | 'paused' | 'unavailable';
	domain_id: string | null;
	limits: Record<string, number>;
	usage: Record<string, number | null>;
	available: Record<string, number | null>;
	project_limits: Record<string, number>;
	project_usage: Record<string, number | null>;
	project_available: Record<string, number | null>;
	error?: string;
}
export interface ManilaFileQuota { shares: QuotaItem; gigabytes: QuotaItem; share_networks: QuotaItem; }

/** Full `/api/v1/dashboard/quotas` view; optional keys depend on enabled services and adapter fallbacks. */
export interface DashboardQuotas {
  compute: { instances: QuotaItem; cores: QuotaItem | null; ram: QuotaItem | null; key_pairs?: QuotaItem; server_groups?: QuotaItem };
  native_compute?: ComputeQuotas | null;
  storage: {
    volumes: QuotaItem;
    gigabytes: QuotaItem;
    snapshots?: QuotaItem;
    backups?: QuotaItem;
    backup_gigabytes?: QuotaItem;
  };
  network: {
    floatingip: QuotaItem;
    network?: QuotaItem;
    subnet?: QuotaItem;
    port?: QuotaItem;
    router?: QuotaItem;
    security_group?: QuotaItem;
    security_group_rule?: QuotaItem;
  };
  /** Manila disabled returns a flat `{ limit, in_use, reserved }` sentinel, so every entry is optional. */
  file_storage: { shares?: QuotaItem; gigabytes?: QuotaItem; share_networks?: QuotaItem; snapshot_gigabytes?: QuotaItem };
  gpu?: GpuQuota[];
  gpu_available?: boolean;
  database?: { instances_count: number };
  object_storage?: { container_count: number; object_count: number; bytes_used: number };
  compute_pool?: ComputePoolSummary;
}
export interface DashboardAlert {
	type: 'quota' | 'instance_error';
	severity: 'warning' | 'danger';
	message: string;
	count: number;
}

export interface DashboardOverviewQuotas {
	compute: { instances: QuotaItem; cores: QuotaItem | null; ram: QuotaItem | null };
	storage: { volumes: QuotaItem; gigabytes: QuotaItem };
	network: { floatingip: QuotaItem };
	file_storage: { shares: QuotaItem; gigabytes: QuotaItem; share_networks?: QuotaItem } | null;
	alerts: DashboardAlert[];
	compute_pool?: ComputePoolSummary;
}
