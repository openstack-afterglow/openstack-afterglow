export type QuotaLimitSource = 'default' | 'user';

export interface CreditPolicy {
	credit_per_usd: string;
	usd_per_credit: string;
	formula: string;
}

export interface UserQuota {
	user_id: string;
	project_id: string | null;
	monthly_credit_limit: string | null;
	weekly_credit_limit: string | null;
	configured_monthly_credit_limit: string | null;
	configured_weekly_credit_limit: string | null;
	monthly_limit_source: QuotaLimitSource;
	weekly_limit_source: QuotaLimitSource;
	weekly_bound_by_monthly: boolean;
	month_credited_cost: string;
	week_credited_cost: string;
	is_active: boolean;
	updated_at: string | null;
}

export interface UserQuotaList {
	default_monthly_credit_limit: string | null;
	default_weekly_credit_limit: string | null;
	credit_policy: CreditPolicy;
	items: UserQuota[];
}

export interface UserUsageAggregate {
	model_name?: string;
	provider?: string | null;
	source?: 'web' | 'api';
	prompt_tokens: number;
	completion_tokens: number;
	total_tokens: number;
	credited_cost: string;
	raw_cost: string;
	request_count: number;
}

export interface UserUsageRecord {
	id: number;
	created_at: string;
	model_name: string;
	provider: string | null;
	prompt_tokens: number;
	completion_tokens: number;
	total_tokens: number;
	credited_cost: string;
	raw_cost: string;
	source: 'web' | 'api';
	api_key_id: number | null;
	pricing_status: string;
}

export interface UserUsageDetail {
	user_id: string;
	range: '7d' | '30d' | '90d' | '1y' | 'all';
	period_start: string | null;
	period_end: string;
	overview: UserUsageAggregate;
	by_model: UserUsageAggregate[];
	by_source: UserUsageAggregate[];
	records: UserUsageRecord[];
	next_before_id: number | null;
}

export function formatCredit(value: string | null, unlimitedLabel = '무제한'): string {
	if (value === null || Number(value) === 0) return unlimitedLabel;
	return Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

export function isCreditInput(value: string): boolean {
	return /^\d{1,10}(\.\d{1,8})?$/.test(value) && Number(value) > 0;
}
