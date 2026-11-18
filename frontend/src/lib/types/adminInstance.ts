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
	status?: 'success' | 'failed' | 'skipped' | 'unconfirmed';
	detail?: string;
}

export interface RecoveryFault {
	message: string | null;
	created: string | null;
	code: number | null;
}

export interface RecoveryAnalysis {
	server: {
		id: string;
		name: string;
		status: string;
		compute_host: string | null;
		hypervisor_hostname?: string | null;
		power_state: number | null;
		fault: RecoveryFault | null;
	};
	last_error_migration: {
		migration_type: string;
		source_compute: string | null;
		source_node?: string | null;
		dest_compute: string | null;
		created_at: string | null;
		updated_at: string | null;
	} | null;
	volumes: { volume_id: string; device: string | null; status: string; bootable: boolean }[] | null;
	ports: { id: string; status: string; binding_vif_type: string | null }[] | null;
	checks: RecoveryCheck[];
	scenario: string;
	scenario_description: string;
	steps: RecoveryStep[];
	auto_executable: boolean;
	plan_fingerprint: string | null;
	placement_note: string | null;
}

export interface RecoveryRequest {
	plan_fingerprint: string;
}

export type UnconfirmedRecoveryAction = 'hard_reboot' | 'reset_server_state';

export interface RecoveryObservation {
	observed_status: string;
	observed_task_state: string | null;
	observed_fault: RecoveryFault | null;
	observed_acceptance: boolean;
	observation_timed_out: boolean;
	observation_terminal: boolean;
	recovered: boolean;
}

export interface RecoveryResult extends RecoveryObservation {
	executed: boolean;
	unconfirmed_action: UnconfirmedRecoveryAction | null;
	observation_may_recover: boolean;
	requested_at: string;
	scenario: string;
	steps: RecoveryStep[];
}
