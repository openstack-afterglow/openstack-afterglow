export interface VolumeBackupPolicyInput {
	max_daily: number;
	max_weekly: number;
	max_monthly: number;
	enabled: boolean;
	schedule_time: string;
	timezone: string;
	weekly_day: number;
	monthly_day: number;
	force: boolean;
}

export interface VolumeBackupPolicy extends VolumeBackupPolicyInput {
	volume_id: string;
	project_id: string;
	created_at: string;
	updated_at: string;
	next_run_at: string | null;
	next_tier: 'daily' | 'weekly' | 'monthly' | null;
	last_run_at: string | null;
	last_status: 'never' | 'creating' | 'available' | 'error' | 'unknown' | 'skipped';
	last_backup_id: string | null;
	last_error: string | null;
	source_status?: 'missing' | 'not_owned' | 'unavailable';
	source_available?: boolean | null;
	source_error?: string | null;
}

export function policyInput(policy: VolumeBackupPolicyInput): VolumeBackupPolicyInput {
	return {
		max_daily: policy.max_daily, max_weekly: policy.max_weekly, max_monthly: policy.max_monthly,
		enabled: policy.enabled, schedule_time: policy.schedule_time, timezone: policy.timezone,
		weekly_day: policy.weekly_day, monthly_day: policy.monthly_day, force: policy.force,
	};
}
