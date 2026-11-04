export interface Overview {
	collected_at: string;
	unavailable_sections: string[];
	disabled_sections: string[];
	hypervisor_count: number | null;
	running_vms: number | null;
	gpu_instances: number | null;
	instance_stats?: { total: number; active: number; shutoff: number; error: number; other: number } | null;
	vcpus: { total: number | null; allowed: number | null; used: number | null };
	ram_gb: { total: number | null; used: number | null };
	disk_gb: { total: number | null; used: number | null; volumes: number | null; images: number | null };
	containers_count: number | null;
	file_storage_count: number | null;
	database_instances_count: number | null;
	object_storage_containers_count: number | null;
	object_storage_unreadable_accounts: number | null;
}

export interface VersionInfo {
	platform: { backend_version: string };
	runtime: { python_version: string; uptime_seconds: number };
	dependencies: Record<string, string | null>;
	git: { commit: string | null; tag: string | null; branch: string | null };
}

export interface ServiceVersion {
	service: 'nova' | 'neutron' | 'palimpsest' | 'drover' | 'lumen' | 'waygate';
	status: 'available' | 'unavailable' | 'disabled';
	version: string | null;
	version_kind: 'product' | 'api' | null;
}

export interface ServiceVersions {
	services: ServiceVersion[];
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
