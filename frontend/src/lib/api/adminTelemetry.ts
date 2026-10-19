import { getBaseUrl } from '$lib/api/client';

export type TelemetryStatus = 'available' | 'partial' | 'not_configured' | 'forbidden' | 'unavailable' | 'not_found';
export interface NativeSection<T = Record<string, unknown> | unknown[]> {
	status: TelemetryStatus;
	error: string | null;
	data: T | null;
}
export interface NativePage<T> {
	status: TelemetryStatus;
	error: string | null;
	items: T[];
	next_marker: string | null;
	truncated: boolean;
}
export type AlarmType = 'gnocchi_resources_threshold' | 'gnocchi_aggregation_by_metrics_threshold'
	| 'gnocchi_aggregation_by_resources_threshold' | 'event' | 'composite'
	| 'loadbalancer_member_health' | 'prometheus';
export interface NativeAlarm {
	alarm_id: string;
	name: string;
	type: AlarmType;
	description?: string | null;
	enabled?: boolean;
	severity?: 'low' | 'moderate' | 'critical' | null;
	repeat_actions?: boolean;
	state?: string | null;
	state_reason?: string | null;
	state_timestamp?: string | null;
	evaluate_timestamp?: string | null;
	timestamp?: string | null;
	project_id?: string | null;
	user_id?: string | null;
	alarm_actions?: string[];
	ok_actions?: string[];
	insufficient_data_actions?: string[];
	time_constraints?: Record<string, unknown>[];
	[key: string]: unknown;
}
export interface AlarmWrite {
	name: string;
	description: string;
	type: AlarmType;
	enabled: boolean;
	severity: 'low' | 'moderate' | 'critical';
	repeat_actions: boolean;
	alarm_actions: string[];
	ok_actions: string[];
	insufficient_data_actions: string[];
	time_constraints: Record<string, unknown>[];
	[key: string]: unknown;
}
export interface AlarmHistory {
	event_id?: string;
	type?: string | null;
	timestamp?: string | null;
	user_id?: string | null;
	project_id?: string | null;
}
export interface AodhOverview {
	status: TelemetryStatus;
	error: string | null;
	checked_at: string;
	capabilities: NativeSection;
	alarms: NativePage<NativeAlarm>;
}
export interface AodhDetail {
	status: TelemetryStatus;
	error: string | null;
	alarm: NativeAlarm | null;
	history: NativePage<AlarmHistory>;
}
export interface ArchivePolicy {
	name: string;
	back_window?: number;
	aggregation_methods?: string[];
	definition?: { granularity?: number | string | null; points?: number | string | null; timespan?: number | string | null }[];
}
export interface ArchivePolicyRule {
	name: string;
	metric_pattern?: string;
	archive_policy_name?: string;
}
export interface GnocchiOverview {
	status: TelemetryStatus;
	error: string | null;
	checked_at: string;
	capabilities: NativeSection;
	processing: NativeSection;
	archive_policies: NativeSection<ArchivePolicy[]>;
	archive_policy_rules: NativeSection<ArchivePolicyRule[]>;
	resource_types: NativeSection<(string | { name: string })[]>;
}
export interface NativeResource {
	id: string;
	type?: string | null;
	project_id?: string | null;
	started_at?: string | null;
	ended_at?: string | null;
	metrics?: Record<string, string>;
}
export interface NativeMetric {
	id: string;
	name?: string | null;
	unit?: string | null;
	resource_id?: string | null;
	archive_policy?: unknown;
	archive_policy_name?: string | null;
	created_by_project_id?: string | null;
}
export interface MetricMeasures {
	status: TelemetryStatus;
	error: string | null;
	metric: NativeMetric | null;
	measures: { timestamp: string; granularity: number; value: number }[];
	truncated: boolean;
}
export interface TelemetryAuthority { token: string; projectId: string }

export class TelemetryError extends Error {
	constructor(public readonly status: number, public readonly code: string, public readonly uncertain = false) {
		super(code);
		this.name = 'TelemetryError';
	}
}

/** Native administration must never use the shared cache or auth-recovery mutation replay. */
export async function adminTelemetryRequest<T>(
	path: string,
	authority: TelemetryAuthority,
	options: { method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; body?: unknown } = {},
): Promise<T> {
	const method = options.method ?? 'GET';
	const mutation = method !== 'GET';
	if (!/^\/(aodh|gnocchi)(\/|\?|$)/.test(path)) throw new TelemetryError(400, 'telemetry_invalid_request');
	try {
		const response = await fetch(`${getBaseUrl()}/api/v1/admin/telemetry${path}`, {
			method,
			cache: 'no-store',
			credentials: 'include',
			redirect: 'error',
			signal: AbortSignal.timeout(15_000),
			headers: {
				Authorization: `Bearer ${authority.token}`,
				...(authority.projectId ? { 'X-Project-Id': authority.projectId } : {}),
				Accept: 'application/json',
				...(mutation ? { 'Content-Type': 'application/json', 'X-Afterglow-Page': typeof window === 'undefined' ? '/admin/monitoring' : window.location.pathname } : {}),
			},
			...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
		});
		if (!response.ok) {
			const body: unknown = await response.json().catch(() => null);
			const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
			const code = detail && typeof detail === 'object' && 'code' in detail && typeof detail.code === 'string'
				&& /^telemetry_[a-z_]+$/.test(detail.code) ? detail.code
				: response.status === 403 ? 'telemetry_forbidden' : response.status === 401 ? 'telemetry_auth_required' : 'telemetry_unavailable';
			throw new TelemetryError(response.status, code, mutation && response.status >= 500);
		}
		if (response.status === 204) return undefined as T;
		return await response.json() as T;
	} catch (error) {
		if (error instanceof TelemetryError) throw error;
		// An interrupted write may have committed upstream. Never infer failure or resend it.
		throw new TelemetryError(503, 'telemetry_unavailable', mutation);
	}
}
