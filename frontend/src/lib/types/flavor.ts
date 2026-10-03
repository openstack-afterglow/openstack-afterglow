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

export interface Flavor {
	id: string;
	name: string;
	vcpus: number;
	ram: number;
	disk: number;
	is_public: boolean;
	description: string | null;
	extra_specs: Record<string, string>;
	is_gpu: boolean;
	gpu_count: number;
	frontend_visible?: boolean;
}

export type FlavorOption = Pick<Flavor, 'id' | 'name' | 'vcpus' | 'ram' | 'disk' | 'is_public'> & {
	extra_specs?: Record<string, string>;
	eligibility?: FlavorEligibility | null;
};

export interface PagedResponse<T> {
	items: T[];
	next_marker: string | null;
	count: number;
}
