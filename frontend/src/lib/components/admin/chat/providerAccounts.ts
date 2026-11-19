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
	created_at?: string;
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
	created_at?: string;
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
interface CredentialUsage {
	credential_id: number | null;
	requests: number;
	prompt_tokens: number;
	completion_tokens: number;
	raw_cost: string;
	month_requests?: number;
	month_prompt_tokens?: number;
	month_completion_tokens?: number;
	month_raw_cost?: string;
	last_used_at?: string | null;
}

export interface AccountUsage {
	provider_id: number;
	account_id: number;
	period?: { kind: 'calendar_month'; start: string; end: string; timezone: string };
	credentials: CredentialUsage[];
}

const unusedKeyUsage = { requests: 0, input: 0, output: 0, cost: '0' };

// PostgreSQL decimal amounts can arrive in exponent notation. Align scales without rounding.
export function sumLedgerCosts(costs: Iterable<string | null>): string | null {
	let units = 0n;
	let scale = 0;
	for (const cost of costs) {
		const match = cost?.match(/^(-?)(\d+)(?:\.(\d+))?(?:e([+-]?\d+))?$/i);
		if (!match) return null;
		const [, sign, whole, fraction = '', exponent = '0'] = match;
		const nextScale = fraction.length - Number(exponent);
		if (!Number.isInteger(nextScale) || Math.abs(nextScale) > 1000) return null;
		const nextUnits = BigInt(`${sign}${whole}${fraction}`);
		const alignedScale = Math.max(scale, nextScale);
		units = units * 10n ** BigInt(alignedScale - scale) + nextUnits * 10n ** BigInt(alignedScale - nextScale);
		scale = alignedScale;
	}
	if (!scale) return units.toString();
	const digits = (units < 0n ? -units : units).toString().padStart(scale + 1, '0');
	const fraction = digits.slice(-scale).replace(/0+$/, '');
	return `${units < 0n ? '-' : ''}${digits.slice(0, -scale)}${fraction ? `.${fraction}` : ''}`;
}

function monthlyFigures(row: CredentialUsage | undefined) {
	if (!row) return unusedKeyUsage;
	const { month_requests: requests, month_prompt_tokens: input, month_completion_tokens: output, month_raw_cost: rawCost } = row;
	if (requests == null || input == null || output == null || rawCost == null) return null;
	const cost = sumLedgerCosts([rawCost]);
	return cost === null ? null : { requests, input, output, cost };
}

export function summarizeAccountUsage(account: ProviderAccount, usage: AccountUsage) {
	const rows = new Map(usage.credentials.map((row) => [row.credential_id, row]));
	let period: { start: number; end: number; timezone: string } | null = null;
	if (usage.period?.kind === 'calendar_month' && usage.period.timezone === 'UTC') {
		const { start, end, timezone } = usage.period;
		const startTime = Date.parse(start), endTime = Date.parse(end);
		if (Number.isFinite(startTime) && Number.isFinite(endTime) && startTime < endTime) {
			period = { start: startTime, end: endTime, timezone };
		}
	}
	const keys = new Map(account.credentials.map(({ id }) => {
		const row = rows.get(id);
		return [id, {
			month: period ? monthlyFigures(row) : null,
			allTime: row ? { requests: row.requests, input: row.prompt_tokens, output: row.completion_tokens, cost: row.raw_cost } : unusedKeyUsage,
			lastUsed: row?.last_used_at,
		}];
	}));
	const monthCost = period ? sumLedgerCosts(Array.from(keys.values(), ({ month }) => month?.cost ?? null)) : null;
	return { period, keys, monthCost, deleted: rows.get(null) };
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
