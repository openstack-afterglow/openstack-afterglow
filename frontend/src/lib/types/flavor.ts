export interface FlavorQuotaBlocker {
	code: string;
	resource?: string | null;
	required?: number | null;
	remaining?: number | null;
}

export type FlavorCapacityStatus = 'available' | 'insufficient' | 'unavailable';

/** Advisory snapshot of one eligible compute host; Nova still performs the final allocation. */
export interface FlavorCapacityInfo {
	status: FlavorCapacityStatus;
	reason?: 'default_compute_zone_unavailable' | null;
	checked_at: string;
	candidate_hosts: number;
	cpu_resource_class: 'VCPU' | 'PCPU' | null;
	/** Per-VM CPU bound on this one host, not aggregate or raw free CPU capacity. */
	remaining_vcpus: number | null;
	/** Per-VM RAM bound on the same host, not aggregate or raw free RAM capacity. */
	remaining_ram_mb: number | null;
	/** Host totals only: single-cell headroom and GPU NUMA proximity remain for Nova to verify. */
	numa_unverified?: boolean;
}

export interface FlavorEligibility {
	selectable: boolean;
	quota_scope?: 'project' | 'domain';
	domain_id?: string | null;
	requirements: {
		instances: number;
		cores: number;
		ram_mb: number;
		gpus: Record<string, number>;
	};
	remaining: {
		instances: number;
		cores: number;
		ram_mb: number;
		gpus: Record<string, number>;
	};
	blockers: FlavorQuotaBlocker[];
	capacity?: FlavorCapacityInfo | null;
}

/**
 * Why a flavor cannot be used for VM creation right now.
 * `quota`: project quota is short; `capacity_insufficient`: no single eligible host fits;
 * `unchecked`: eligibility or a required check could not be verified, which never admits creation.
 */
export type FlavorCreateBlock = 'quota' | 'capacity_insufficient' | 'unchecked';

/**
 * Creation-only admission derives from eligibility, explicit blockers and the same-host capacity snapshot.
 * A missing or unverified (`unavailable`) snapshot never admits creation, even without a blocker code.
 */
export function flavorCreateBlock(flavor: { eligibility?: FlavorEligibility | null } | null | undefined): FlavorCreateBlock | null {
	const eligibility = flavor?.eligibility;
	if (!eligibility) return 'unchecked';
	const codes = (eligibility.blockers ?? []).map(blocker => blocker.code);
	const quotaCodes = codes.filter(code => !code.startsWith('host_capacity_'));
	if (quotaCodes.includes('domain_pool_paused')) return 'unchecked';
	if (quotaCodes.some(code => code.endsWith('_unavailable'))) return 'unchecked';
	if (quotaCodes.length > 0) return 'quota';
	if (codes.includes('host_capacity_unavailable')) return 'unchecked';
	if (codes.includes('host_capacity_insufficient')) return 'capacity_insufficient';
	if (!eligibility.selectable) return 'unchecked';
	const capacity = eligibility.capacity?.status;
	if (capacity === 'insufficient') return 'capacity_insufficient';
	if (capacity !== 'available') return 'unchecked';
	return null;
}

export interface FlavorGpuPrimaryAlias {
	name: string;
	count: number;
	resource_class: string;
	profile_name: string;
}

export interface Flavor {
	id: string;
	name: string;
	display_name?: string | null;
	cpu_automation_managed?: boolean;
	vcpus: number;
	ram: number;
	disk: number;
	is_public: boolean;
	description: string | null;
	extra_specs: Record<string, string>;
	is_gpu: boolean | null;
	gpu_count: number | null;
	gpu_primary_aliases?: FlavorGpuPrimaryAlias[] | null;
	frontend_visible?: boolean;
	usage_schedule_required?: boolean;
}

export interface FlavorComposition {
	vcpus: number;
	ram_mb: number;
	gpu_profile_id: string | null;
	gpu_count: number;
}

/** Complete owner-scoped advisory capacity, never persisted as admission authority. */
export interface FlavorComposerSnapshot {
	checked_at: string;
	status: FlavorCapacityStatus;
	gpu_profiles: { id: string; name: string }[];
	variants: {
		gpu_profile_id: string | null;
		gpu_count: number;
		status: FlavorCapacityStatus;
		regions: {
			vcpus: { min: number; max: number; step: number };
			ram_mb: { min: number; max: number; step: number };
		}[];
		preview: FlavorOption | null;
	}[];
}

export interface FlavorComposerOptions {
	vcpus: number[];
	ram_mb: number[];
	gpu_profiles: { id: string; name: string; status: FlavorCapacityStatus }[];
	gpu_counts: number[];
	selection: FlavorOption | null;
	checked_at: string;
	status: FlavorCapacityStatus;
}

export type FlavorOption = Pick<Flavor, 'id' | 'name' | 'display_name' | 'cpu_automation_managed' | 'vcpus' | 'ram' | 'disk' | 'is_public'> & {
	extra_specs?: Record<string, string>;
	is_gpu?: boolean;
	gpu_count?: number;
	gpu_primary_aliases?: FlavorGpuPrimaryAlias[] | null;
	usage_schedule_required?: boolean;
	eligibility?: FlavorEligibility | null;
	composition?: FlavorComposition | null;
};

export interface PagedResponse<T> {
	items: T[];
	next_marker: string | null;
	count: number;
}
