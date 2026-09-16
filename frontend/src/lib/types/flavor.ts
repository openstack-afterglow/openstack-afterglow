export interface FlavorQuotaBlocker {
	code: string;
	resource?: string | null;
	required?: number | null;
	remaining?: number | null;
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
