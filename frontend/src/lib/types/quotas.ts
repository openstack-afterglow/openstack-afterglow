export interface Project { id: string; name: string; }
export interface QuotaLimit { limit: number; in_use: number; }
export interface Quotas {
	compute?: { instances?: QuotaLimit; cores?: QuotaLimit; ram?: QuotaLimit };
	volume?: { volumes?: QuotaLimit; gigabytes?: QuotaLimit };
}
export interface GpuQuota { gpu_type: string; limit: number; in_use: number; available: number; }
export interface GpuDefaultQuota { gpu_type: string; limit: number; }
export interface QuotaItem { limit: number; in_use: number; }
export interface ManilaFileQuota { shares: QuotaItem; gigabytes: QuotaItem; share_networks: QuotaItem; }

/** Full `/api/v1/dashboard/quotas` view; optional keys depend on enabled services and adapter fallbacks. */
export interface DashboardQuotas {
  compute: { instances: QuotaItem; cores: QuotaItem; ram: QuotaItem; key_pairs?: QuotaItem; server_groups?: QuotaItem };
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
}
export interface DashboardAlert {
	type: 'quota' | 'instance_error';
	severity: 'warning' | 'danger';
	message: string;
	count: number;
}

export interface DashboardOverviewQuotas {
	compute: { instances: QuotaItem; cores: QuotaItem; ram: QuotaItem };
	storage: { volumes: QuotaItem; gigabytes: QuotaItem };
	network: { floatingip: QuotaItem };
	file_storage: { shares: QuotaItem; gigabytes: QuotaItem; share_networks?: QuotaItem } | null;
	alerts: DashboardAlert[];
}
