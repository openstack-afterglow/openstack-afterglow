/**
 * 빌트인 AI 채팅 사용량 — 타입 + 시계열 피벗(순수 함수).
 *
 * 백엔드 timeseries 는 (bucket × source) 행 목록을 준다. TimeSeriesChart 는 {ts, <key>} 포인트를
 * 기대하므로, 버킷별로 source(web/api/system)를 피벗해 스택 차트용 데이터로 변환한다.
 * 이 변환은 UI 위험 중심(경계·정렬)이라 순수 함수로 격리해 단위 테스트한다.
 */

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

export type UsageMetric = 'total_tokens' | 'credited_cost' | 'request_count';

/** 버킷 문자열 → epoch 초. 실패 시 0. TimeSeriesChart 는 ts(초)를 기대. */
export function bucketToTs(bucket: string): number {
	if (!bucket) return 0;
	// "YYYY-MM" → 월초, 그 외는 ISO 로 파싱(공백 → T).
	const iso = bucket.length === 7 ? `${bucket}-01` : bucket.replace(' ', 'T');
	const ms = Date.parse(iso);
	return Number.isNaN(ms) ? 0 : Math.floor(ms / 1000);
}

/**
 * (bucket × source) 행들을 버킷별 스택 포인트로 피벗.
 * 반환: [{ts, bucket, web, api, system, total}] (ts 오름차순). 값 = metric.
 */
export function pivotTimeseries(
	rows: readonly TimeseriesRow[],
	metric: UsageMetric = 'total_tokens'
): Array<Record<string, number | string>> {
	const byBucket = new Map<string, Record<string, number | string>>();
	for (const r of rows) {
		let point = byBucket.get(r.bucket);
		if (!point) {
			point = { bucket: r.bucket, ts: bucketToTs(r.bucket), web: 0, api: 0, system: 0, total: 0 };
			byBucket.set(r.bucket, point);
		}
		const v = Number(r[metric] ?? 0);
		const key = r.source || 'web';
		point[key] = (Number(point[key]) || 0) + v;
		point.total = (Number(point.total) || 0) + v;
	}
	return [...byBucket.values()].sort((a, b) => (a.ts as number) - (b.ts as number));
}

/** by_source 목록에서 특정 소스의 항목(없으면 0 기본). */
export function sourceRow(by: readonly UsageBySource[], source: string): UsageBySource {
	return by.find((s) => s.source === source) ?? { source, tokens: 0, credited_cost: 0, request_count: 0 };
}
