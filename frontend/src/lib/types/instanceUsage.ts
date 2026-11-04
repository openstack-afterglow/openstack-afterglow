export type UsageExpiryAction = 'shelve' | 'delete';

export const USAGE_STATES = ['active', 'blocked', 'shelve_requested', 'offload_requested', 'stop_requested',
	'volume_flags_requested', 'volumes_ready', 'delete_requested', 'complete', 'unknown'] as const;
export type UsageState = typeof USAGE_STATES[number];

export interface UsageScheduleRequest {
	expires_at: string | null;
	expiry_action: UsageExpiryAction;
	delete_volumes: boolean;
	reason: string;
}

export interface UsageScheduleInfo extends UsageScheduleRequest {
	instance_id: string;
	expires_at: string;
	starts_at: string;
	revision: string;
	state: UsageState;
	source: 'created' | 'adopted';
	last_error: string | null;
	extended_at?: string | null;
	extended_by?: string | null;
	instance_name?: string;
	server_name?: string;
}

export interface UsageExtensionPolicy {
	domain_id: string;
	review_required: boolean;
	revision: string;
	can_manage: boolean;
}

export interface UsageExtensionRequest {
	id: string;
	domain_id: string;
	project_id: string;
	instance_id: string;
	instance_name: string | null;
	requested_by: string;
	requested_at: string;
	expires_at: string;
	reason: string;
	schedule_revision: string;
	policy_revision: string;
	revision: string;
	status: 'pending' | 'applying' | 'approved' | 'rejected' | 'stale' | 'uncertain';
	reviewed_by: string | null;
	reviewed_at: string | null;
	can_review: boolean;
}

export interface UsageExtensionPage {
	items: UsageExtensionRequest[];
	next_cursor: string | null;
}

export interface UsageExtensionPending {
	status: 'pending';
	request: UsageExtensionRequest;
	schedule: UsageScheduleInfo;
}

/** Tab-local form values; never persisted to browser storage. */
export interface UsageScheduleDraft {
	expiresLocal: string;
	defaultExpiresAt: string;
	expiryAction: UsageExpiryAction;
	deleteVolumes: boolean;
	reason: string;
}
