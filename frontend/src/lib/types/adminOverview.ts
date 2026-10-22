export interface Overview {
	hypervisor_count: number;
	running_vms: number;
	gpu_instances: number;
	instance_stats?: { total: number; active: number; shutoff: number; error: number; other: number };
	vcpus: { total: number; allowed: number; used: number };
	ram_gb: { total: number; used: number };
	disk_gb: { total: number; used: number };
	containers_count: number;
	file_storage_count: number;
	database_instances_count: number;
	object_storage_containers_count: number;
}

export interface VersionInfo {
	platform: { backend_version: string };
	runtime: { python_version: string; uptime_seconds: number };
	dependencies: Record<string, string | null>;
	git: { commit: string | null; tag: string | null; branch: string | null };
}

export interface DomainUsage {
	domain_id: string | null;
	domain_name: string | null;
	owner_status: 'known' | 'deleted_project' | 'unknown_owner' | 'deleted_domain';
	project_ids: string[];
	project_count: number;
	instances: number;
	vcpus: number | null;
	ram_mb: number | null;
	gpu_instances: number | null;
	volumes: number;
	volume_gb: number;
	attached_volumes: number;
	attached_gb: number;
	available_volumes: number;
	available_gb: number;
}
