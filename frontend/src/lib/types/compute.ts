export interface IpAddress {
  addr: string;
  type: string;
  network_name: string;
}

export interface Instance {
  id: string;
  name: string;
  status: string;
  image_name: string | null;
  flavor_name: string | null;
  ip_addresses: IpAddress[];
  created_at: string | null;
  union_libraries: string[];
  union_strategy: string | null;
  union_upper_volume_id?: string | null;
  union_share_ids?: string[];
  metadata?: Record<string, string>;
  fault?: { code?: number; message?: string; details?: string; created?: string } | null;
  image_id?: string | null;
  flavor_id?: string | null;
  key_name?: string | null;
  host?: string | null;  // 현재 하이퍼바이저 호스트 (관리자 스코프에서만 채워짐)
}

export interface DashboardSummary {
  instances: { total: number; active: number; shutoff: number; error: number };
  gpu_used: number;
}

export type DashboardRecentInstance = Pick<
  Instance,
  'id' | 'name' | 'status' | 'flavor_name' | 'ip_addresses' | 'created_at'
>;

export interface DashboardOverviewSummary {
  instances: DashboardSummary['instances'];
  recent_instances: DashboardRecentInstance[];
}

export interface ImageInfo {
  id: string;
  name: string;
  status: string;
  visibility?: string;
  repository?: string;
  tag?: string;
  size?: number;
  min_disk?: number;
  min_ram?: number;
  disk_format?: string;
  container_format?: string;
  created_at?: string;
  updated_at?: string;
  owner?: string;
  protected?: boolean;
  tags?: string[];
  os_distro?: string | null;
  os_version?: string | null;
  os_type?: string;
  properties?: Record<string, unknown> | null;
}
