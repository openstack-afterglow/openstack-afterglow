import { get } from 'svelte/store';
import { t } from '$lib/i18n/ns/chat-settings';
import { intlLocale } from '$lib/i18n/runtime.svelte';
import { auth, logoutInProgress } from '$lib/stores/auth';
import { authDisplayContext } from '$lib/stores/authDisplayContext';
import { api } from './client';
import { isCreditInput } from './chatQuotas';
import type { ApiKey, ApiKeyIssuancePolicy } from './chatUsage';

// Display names only. Lumen's issuance policy decides which scopes are offered.
const modelKeyScopeLabels = {
	'models:read': 'apiKeys.scope.models',
	'compat:completions:write': 'apiKeys.scope.chat',
	'embeddings:write': 'apiKeys.scope.embeddings',
	'compat:images:write': 'apiKeys.scope.images',
	'compat:audio:write': 'apiKeys.scope.audio',
	'native:audio:write': 'apiKeys.scope.audio',
	'compat:realtime:write': 'apiKeys.scope.realtime',
	'decisions:write': 'apiKeys.scope.decisions'
} as const;

export function modelKeyScopeLabel(scope: string): string {
	return Object.hasOwn(modelKeyScopeLabels, scope) ? t(modelKeyScopeLabels[scope as keyof typeof modelKeyScopeLabels]) : scope;
}

export async function readKeyIssuancePolicy(token: string, projectId: string): Promise<ApiKeyIssuancePolicy> {
	const policy = await api.get<ApiKeyIssuancePolicy>(`${lumenBrowserPath}/api-keys/issuance-policy`, token, projectId, { refresh: true });
	if (policy.monthly_credit_limit !== null && !isCreditInput(policy.monthly_credit_limit)) throw new Error('Invalid credit limit');
	if (!Array.isArray(policy.allowed_scopes) || !policy.scope_capabilities
		|| policy.allowed_scopes.some((scope) => typeof scope !== 'string' || !Array.isArray(policy.scope_capabilities[scope]))) {
		throw new Error('Invalid scope policy');
	}
	return policy;
}

/** Manager-only: scopes service-key creation accepts, independent of the manager's own project role. */
export async function readServiceKeyIssuancePolicy(token: string, projectId: string): Promise<{ allowed: string[]; defaults: string[] }> {
	const policy = await api.get<{ allowed_scopes: unknown; default_scopes?: unknown }>(`${lumenBrowserPath}/service-keys/issuance-policy`, token, projectId, { refresh: true });
	const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every((scope) => typeof scope === 'string');
	if (!strings(policy?.allowed_scopes)) throw new Error('Invalid service key scope policy');
	const allowed = policy.allowed_scopes;
	// Defaults are a suggestion; never preselect a scope creation would reject.
	return { allowed, defaults: strings(policy.default_scopes) ? policy.default_scopes.filter((scope) => allowed.includes(scope)) : [] };
}

export interface ServiceKey extends ApiKey {
	key_kind: 'service';
	owner_domain_id: string;
	created_by_user_id: string | null;
}

export interface DomainPool {
	domain_id: string;
	balance_credits: string;
	reserved_credits: string;
	monthly_used_credits: string;
	manager_monthly_limit_credits: string | null;
	admin_ceiling_credits: string | null;
	is_active: boolean;
}

export interface ServiceKeyInventory {
	items: ServiceKey[];
	next_before_id: number | null;
}

export const lumenBrowserPath = '/api/v1/chat';

export function currentBillingSession(key: string, role: 'manager' | 'admin') {
	const scope = get(authDisplayContext);
	const state = get(auth);
	if (!scope.ready || scope.key !== key || get(logoutInProgress) || !state.token || !state.projectId || !state.domainId || !state.userId) return null;
	if (!(role === 'manager' ? state.isDomainManager : state.isSystemAdmin)) return null;
	return { token: state.token, projectId: state.projectId, domainId: state.domainId, userId: state.userId };
}

const creditInput = /^\d{1,10}(\.\d{1,8})?$/;

export function validDomainCredit(value: string, positive = false): boolean {
	return creditInput.test(value) && (!positive || /[1-9]/.test(value));
}

// Compare the same eight fractional digits as the upstream decimal contract.
export function exceedsDomainCeiling(value: string, ceiling: string | null): boolean {
	if (ceiling === null) return false;
	const scaled = (decimal: string) => {
		const [whole, fraction = ''] = decimal.split('.');
		return BigInt(whole + fraction.padEnd(8, '0'));
	};
	return scaled(value) > scaled(ceiling);
}

export function displayDomainCredit(value: string | number | null | undefined): string {
	if (value == null || !Number.isFinite(Number(value))) return t('domainBilling.unavailable');
	return new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 8 }).format(value as number | `${number}`);
}

export function domainBillingCode(body: Record<string, unknown>): string | undefined {
	const candidates = [body.code, body.detail, body.error];
	for (const candidate of candidates) {
		const value = candidate && typeof candidate === 'object' && 'code' in candidate ? candidate.code : candidate;
		if (typeof value === 'string' && Object.hasOwn(billingErrors, value)) return value;
	}
}

const billingErrors = {
	domain_credit_insufficient: 'domainBilling.insufficient',
	domain_credit_limit_exceeds_ceiling: 'domainBilling.overCeiling',
	domain_credit_balance_overflow: 'domainBilling.balanceOverflow',
	idempotency_key_reused_with_different_intent: 'domainBilling.topupConflict'
} as const;

export function domainBillingErrorMessage(cause: unknown): string | undefined {
	if (cause && typeof cause === 'object') {
		if ('code' in cause && typeof cause.code === 'string' && Object.hasOwn(billingErrors, cause.code)) {
			return t(billingErrors[cause.code as keyof typeof billingErrors]);
		}
		cause = 'message' in cause ? cause.message : undefined;
	}
	if (typeof cause !== 'string' || !Object.hasOwn(billingErrors, cause)) return;
	return t(billingErrors[cause as keyof typeof billingErrors]);
}
