/** Built-in AI usage API types and cumulative source summaries. */

export interface UsageBySource {
	source: string; // web | api | system
	tokens: number;
	credited_cost: number;
	request_count: number;
}

export interface UsageSummary {
	found: boolean;
	total_credited_cost: number;
	lifetime_prompt_tokens: number;
	lifetime_completion_tokens: number;
	lifetime_request_count: number;
	month_credited_cost: number;
	week_credited_cost: number;
	quota_used: number;
	quota_max: number;
	quota_weekly_max: number;
	by_source: UsageBySource[];
}

export interface TimeseriesRow {
	bucket: string; // "YYYY-MM" | "YYYY-MM-DD" | "YYYY-MM-DD HH:00:00"
	source: string;
	total_tokens: number;
	credited_cost: number;
	request_count: number;
}

export interface KeyUsage {
	api_key_id: number;
	name: string | null;
	key_prefix: string | null;
	total_tokens: number;
	credited_cost: number;
	request_count: number;
}

export interface ApiKey {
	id: number;
	name: string;
	key_prefix: string;
	scopes: string[];
	is_active: boolean;
	last_used_at: string | null;
	created_at: string | null;
	revoked_at: string | null;
	expires_at: string | null;
	owner_monthly_credit_limit: string | null;
	admin_monthly_credit_limit: string | null;
	system_monthly_credit_limit: string | null;
	effective_monthly_credit_limit: string | null;
	month_credited_cost: string;
	owner_weekly_credit_limit: string | null;
	system_weekly_credit_limit: string | null;
	effective_weekly_credit_limit: string | null;
	week_credited_cost: string;
}

export interface ApiKeyIssuancePolicy {
	monthly_credit_limit: string | null;
	weekly_credit_limit: string | null;
	allowed_scopes: string[];
	scope_capabilities: Record<string, string[]>;
}

/** by_source 목록에서 특정 소스의 항목(없으면 0 기본). */
export function sourceRow(by: readonly UsageBySource[], source: string): UsageBySource {
	return by.find((s) => s.source === source) ?? { source, tokens: 0, credited_cost: 0, request_count: 0 };
}
