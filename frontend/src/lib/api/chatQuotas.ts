export interface UserQuota {
	user_id: string;
	project_id: string | null;
	monthly_credit_limit: string | null;
	weekly_credit_limit: string | null;
	month_credited_cost: string;
	week_credited_cost: string;
	is_active: boolean;
	updated_at: string | null;
}

export interface UserQuotaList {
	default_monthly_credit_limit: string;
	items: UserQuota[];
}

export function formatCredit(value: string | null, unlimitedLabel = '무제한'): string {
	if (value === null || Number(value) === 0) return unlimitedLabel;
	return Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

export function isCreditInput(value: string): boolean {
	return /^\d{1,10}(\.\d{1,8})?$/.test(value) && Number(value) > 0;
}
