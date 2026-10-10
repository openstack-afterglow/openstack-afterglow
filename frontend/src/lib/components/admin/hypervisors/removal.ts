
export interface RemovalCheck {
	code: string;
	label: string;
	state: 'pass' | 'blocked' | 'unknown';
	detail: string;
}

export interface RemovalServer {
	id: string;
	name: string;
	status: string;
	project_id: string;
	created_at: string | null;
}

export interface RemovalMigration {
	id: string;
	uuid: string;
	instance_uuid: string;
	source_compute: string | null;
	dest_compute: string | null;
	status: string;
	migration_type: string;
	created_at: string | null;
	updated_at: string | null;
}

export interface RemovalProvider {
	uuid: string;
	name: string;
	parent_provider_uuid: string | null;
	generation: number;
	allocations: Record<string, unknown>;
}

/** The public inspection contract; sampled uptime is information, not a ping. */
export interface RemovalReport {
	hypervisor_id: string;
	hostname: string;
	checked_at: string;
	service: {
		id: string;
		host: string;
		binary: string;
		state: string;
		status: string;
		updated_at: string | null;
		forced_down: boolean | null;
		disabled_reason: string | null;
		zone: string | null;
	};
	uptime: {
		status: 'available' | 'unavailable';
		value: string | null;
		host_time: string | null;
		source?: 'live' | 'last_observed' | 'unavailable';
		observed_at?: string | null;
	};
	servers: RemovalServer[];
	history: {
		deleted_servers: RemovalServer[];
		migrations: RemovalMigration[];
		note: string;
	};
	placement: { providers: RemovalProvider[] };
	checks: RemovalCheck[];
	eligible: boolean;
}

export interface RemovalInspection {
	report: RemovalReport;
	review_token: string | null;
	expires_at: string | null;
}

export interface RemovalApproval {
	review_token: string;
	confirm_hostname: string;
	reason: string;
	reviewed_metadata: true;
	compute_stopped: true;
}

export interface RemovalResult {
	status: 'removed' | 'removal_unverified';
	verified: boolean;
	hypervisor_id: string;
	hostname: string;
	service_id: string;
	detail: string;
	checks: RemovalCheck[];
}

/** Check the wall clock at submission too: a rendered enabled button is not authority. */
export function hasValidRemovalReview(
	inspection: RemovalInspection | null,
	now = Date.now(),
): inspection is RemovalInspection & { review_token: string; expires_at: string } {
	if (!inspection?.report.eligible || !inspection.review_token || !inspection.expires_at) return false;
	if (inspection.report.checks.length === 0 || inspection.report.checks.some((check) => check.state !== 'pass')) return false;
	const expires = Date.parse(inspection.expires_at);
	return Number.isFinite(expires) && expires > now;
}

/** Nova accepting DELETE is insufficient; all completion verification must succeed. */
export function isVerifiedRemoval(result: RemovalResult | null): boolean {
	return result?.status === 'removed' && result.verified === true;
}

export const REMOVAL_CHECK_STATE_KEY = {
	pass: 'hypervisors.removal.state.pass',
	blocked: 'hypervisors.removal.state.blocked',
	unknown: 'hypervisors.removal.state.unknown',
} as const;
