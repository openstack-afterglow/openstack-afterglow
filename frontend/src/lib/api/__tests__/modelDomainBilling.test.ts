import { describe, expect, it } from 'vitest';
import { t } from '$lib/i18n/ns/chat-studio';
import {
	agentModelBlockedMessage,
	domainBillingAdmissionMessage,
	modelBillingFallbackNotice,
	modelBillingReady,
	modelBillingReason,
	resolveReadySelection
} from '../modelDomainBilling';
import type { ModelCatalogRow } from '../modelCatalog';

const ready: ModelCatalogRow = { id: 1, model_name: 'ready', display_name: 'Ready', domain_billing: { ready: true, reason_code: null } };
const legacy: ModelCatalogRow = { id: 2, model_name: 'legacy', display_name: 'Legacy Lumen' };
const unpriced: ModelCatalogRow = { id: 3, model_name: 'unpriced', display_name: 'Unpriced', domain_billing: { ready: false, reason_code: 'pricing_unavailable' } };
const unbounded: ModelCatalogRow = { id: 4, model_name: 'unbounded', display_name: 'Unbounded', domain_billing: { ready: false, reason_code: 'output_budget_unenforced' } };
const unknownWindow: ModelCatalogRow = { id: 5, model_name: 'unknown-window', display_name: 'Unknown window', domain_billing: { ready: false, reason_code: 'context_limit_unknown' } };

describe('domain billing readiness', () => {
	it('treats a missing domain_billing (older Lumen) as ready and maps every reason', () => {
		expect(modelBillingReady(legacy)).toBe(true);
		expect(modelBillingReason(legacy)).toBeNull();
		expect(modelBillingReason(ready)).toBeNull();
		expect(modelBillingReason(unpriced)).toBe(t('modelBilling.pricing'));
		expect(modelBillingReason(unbounded)).toBe(t('modelBilling.outputBudget'));
		expect(modelBillingReason(unknownWindow)).toBe(t('modelBilling.contextLimit'));
		expect(modelBillingReason({ domain_billing: { ready: false, reason_code: null } })).toBe(t('modelBilling.unready'));
	});

	it('defaults to the first ready row in catalog order and never auto-selects an unready one', () => {
		expect(resolveReadySelection([unpriced, unknownWindow, ready, legacy], undefined)).toEqual({ model: ready, displaced: null });
		expect(resolveReadySelection([unpriced, legacy], undefined)).toEqual({ model: legacy, displaced: null });
	});

	it('keeps a ready choice, keeps an explicit empty choice, and displaces an unready one', () => {
		const rows = [unpriced, ready, legacy];
		expect(resolveReadySelection(rows, legacy)).toEqual({ model: legacy, displaced: null });
		expect(resolveReadySelection(rows, null)).toEqual({ model: null, displaced: null });
		expect(resolveReadySelection(rows, unpriced)).toEqual({ model: ready, displaced: unpriced });
		expect(modelBillingFallbackNotice(unpriced, ready)).toBe(t('modelBilling.fallback', {
			previous: 'Unpriced', next: 'Ready', reason: t('modelBilling.pricing')
		}));
	});

	it('selects nothing when every row is unready and explains the remembered model', () => {
		expect(resolveReadySelection([unpriced, unbounded], unbounded)).toEqual({ model: null, displaced: unbounded });
		expect(modelBillingFallbackNotice(unbounded, null)).toBe(t('modelBilling.unavailable', {
			previous: 'Unbounded', reason: t('modelBilling.outputBudget')
		}));
	});

	it('explains an agent pinned to an unready model', () => {
		expect(agentModelBlockedMessage(ready)).toBeNull();
		expect(agentModelBlockedMessage(unknownWindow)).toBe(t('modelBilling.agentBlocked', {
			name: 'Unknown window', reason: t('modelBilling.contextLimit')
		}));
	});

	it('maps only the exact 422 domain_billing admission refusal', () => {
		const refusal = (status: number, reason: string) => Object.assign(
			new Error(`requested chat capability is not available: domain_billing (${reason})`), { status }
		);
		expect(domainBillingAdmissionMessage(refusal(422, 'context_limit_unknown'))).toBe(t('modelBilling.contextLimit'));
		expect(domainBillingAdmissionMessage(refusal(422, 'future_reason'))).toBe(t('modelBilling.unready'));
		expect(domainBillingAdmissionMessage(refusal(409, 'pricing_unavailable'))).toBeUndefined();
		expect(domainBillingAdmissionMessage(Object.assign(new Error('requested chat capability is not available: vision'), { status: 422 }))).toBeUndefined();
		expect(domainBillingAdmissionMessage('requested chat capability is not available: domain_billing (pricing_unavailable)')).toBeUndefined();
	});
});
