export interface AdminInstance {
	id: string;
	name: string;
	status: string;
	project_id: string | null;
	user_id: string | null;
	flavor: string;
	flavor_display_name?: string | null;
	host: string | null;
	created_at: string | null;
	fault?: string | null;
}

export interface PagedResponse<T> {
	items: T[];
	next_marker: string | null;
	count: number;
}

export interface TsPoint {
	ts: number;
	total?: number;
	active?: number;
	shutoff?: number;
	error?: number;
	shelved?: number;
	[key: string]: number | undefined;
}

export interface RecoveryCheck {
	key: string;
	label: string;
	passed: boolean;
	detail: string;
}

export interface RecoveryStep {
	action: string;
	description: string;
	params?: Record<string, string>;
	status?: 'success' | 'failed' | 'skipped';
	detail?: string;
}

export interface RecoveryAnalysis {
	server: { id: string; name: string; status: string; compute_host: string | null; fault: { message: string | null; code: number | null; created: string | null } | null };
	last_error_migration: { migration_type: string; source_compute: string | null; dest_compute: string | null; created_at: string | null } | null;
	volumes: { volume_id: string; device: string | null; status: string; bootable: boolean }[];
	ports: { id: string; status: string; binding_vif_type: string | null }[];
	checks: RecoveryCheck[];
	scenario: string;
	scenario_description: string;
	steps: RecoveryStep[];
	auto_executable: boolean;
	placement_note: string | null;
}

export interface RecoveryResult {
	executed: boolean;
	scenario: string;
	steps: RecoveryStep[];
}
