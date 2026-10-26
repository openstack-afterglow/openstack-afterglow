export type AuthMode = 'api_key' | 'chatgpt_device' | 'anthropic_subscription';
export interface AccountProvider {
	id: number;
	name: string;
	auth_mode?: AuthMode;
	provider_type?: string;
	api_base?: string | null;
	is_active?: boolean;
	selection_policy?: 'priority' | 'weighted' | 'explicit';
	selected_credential_id?: number | null;
}
export interface PoolEntry {
	id: number;
	name: string;
	is_active: boolean;
	priority: number;
	weight: number;
	allowed_model_ids: number[] | null;
	allowed_capabilities: string[] | null;
}
export interface ProviderCredential extends PoolEntry {
	account_id: number;
	auth_mode: AuthMode;
	generation: number;
	api_key_configured: boolean;
	api_key_source: string | null;
	api_key_env: string | null;
	subscription_status: string;
	subscription_expires_at: string | null;
	expires_at: string | null;
	cooldown_until: string | null;
}
export interface ProviderAccount extends PoolEntry {
	provider_id: number;
	quota_group: string | null;
	credentials: ProviderCredential[];
}
export interface ProbeModel {
	id: number;
	provider_id: number;
	model_name: string;
	display_name?: string | null;
	model_kind?: string;
	is_active: boolean;
}
export interface ProbeResult {
	status: 'connected' | 'failed';
	reason: 'auth_rejected' | 'timeout' | 'invalid_response' | 'provider_error' | null;
	mode: 'structured' | 'plain';
	elapsed_ms: number;
	model_id: number;
	generation: number;
	checked_at: string;
}
export interface AccountUsage {
	provider_id: number;
	account_id: number;
	credentials: { credential_id: number | null; requests: number; prompt_tokens: number; completion_tokens: number; raw_cost: string }[];
}
export interface DeviceAttempt {
	attempt_id: string;
	status: 'pending' | 'connected' | 'cancelled' | 'expired' | 'error';
	verification_uri?: string;
	user_code?: string;
	expires_at: string;
	interval_seconds: number;
}
// Blank is unrestricted; a single '-' deliberately denies every model/operation.
export function eligibility(value: string, numeric: true): number[] | null;
export function eligibility(value: string, numeric?: false): string[] | null;
export function eligibility(value: string, numeric = false): (number | string)[] | null {
	if (!value.trim()) return null;
	if (value.trim() === '-') return [];
	const parts = value.split(',').map((part) => part.trim());
	const operations: Record<string, true> = { chat: true, responses: true, messages: true, count_tokens: true, embeddings: true, search: true, image: true, tts: true, stt: true, realtime: true };
	if (parts.some((part) => !part || (numeric ? !/^\d+$/.test(part) || !Number.isSafeInteger(Number(part)) || Number(part) <= 0 : !Object.hasOwn(operations, part)))) throw new Error('eligibility');
	return [...new Set(parts.map((part) => numeric ? Number(part) : part))];
}
export function eligibilityDraft(value: (number | string)[] | null): string {
	return value === null ? '' : value.length ? value.join(', ') : '-';
}
export function localTimestamp(value: string | null): string {
	if (!value) return '';
	const date = new Date(value);
	if (!Number.isFinite(date.getTime())) return '';
	return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export function allowedDeviceUri(value: string | undefined): string | null {
	if (!value) return null;
	try {
		const url = new URL(value);
		return url.protocol === 'https:' && !url.username && !url.password && !url.port && (url.hostname === 'openai.com' || url.hostname.endsWith('.openai.com') || url.hostname === 'chatgpt.com' || url.hostname.endsWith('.chatgpt.com')) ? url.href : null;
	} catch { return null; }
}

export interface RelayDispatch {
	attempt_id: string;
	endpoint: string | null;
	model: string | null;
	operation: string;
	status: 'dispatched' | 'response_received';
	status_code: number | null;
	recorded_at: string;
}
export interface RelayUsage {
	ledger_id: number;
	generation: number;
	settled_at: string;
	settled_model: string;
	status: 'settled';
	dispatches: RelayDispatch[] | null;
}
export interface RelayPage {
	provider_id: number;
	account_id: number;
	credential_id: number;
	boundary: 'settled_usage';
	items: RelayUsage[];
	next_before_id: number | null;
}
export function safeEndpoint(value: string | null | undefined): string | null {
	if (!value) return null;
	try {
		const url = new URL(value);
		if (!['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol)) return null;
		return `${url.protocol}//${url.host}${url.pathname}`;
	} catch { return null; }
}
