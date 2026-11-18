import { t } from '$lib/i18n/ns/chat-studio';
import type { DomainBillingReadiness } from './modelCatalog';

type BillingRow = { domain_billing?: DomainBillingReadiness | null };

const reasonKeys = {
	pricing_unavailable: 'modelBilling.pricing',
	output_budget_unenforced: 'modelBilling.outputBudget',
	context_limit_unknown: 'modelBilling.contextLimit'
} as const;

/** Older Lumen omits `domain_billing`; only an explicit `ready: false` blocks dashboard chat. */
export function modelBillingReady(model: BillingRow): boolean {
	return model.domain_billing?.ready !== false;
}

export function domainBillingReasonLabel(code: unknown): string {
	return typeof code === 'string' && Object.hasOwn(reasonKeys, code)
		? t(reasonKeys[code as keyof typeof reasonKeys])
		: t('modelBilling.unready');
}

/** Localized reason a model cannot be admitted for domain-billed chat, or null when it can. */
export function modelBillingReason(model: BillingRow): string | null {
	return modelBillingReady(model) ? null : domainBillingReasonLabel(model.domain_billing?.reason_code);
}

/**
 * Keeps a ready candidate, replaces an unready one with the first ready row in catalog
 * order (reporting it as displaced), picks the first ready row when nothing was chosen,
 * and keeps an explicit `null` (a remembered model that no longer exists) as no selection.
 */
export function resolveReadySelection<T extends BillingRow>(
	models: readonly T[], candidate: T | null | undefined
): { model: T | null; displaced: T | null } {
	if (candidate === null) return { model: null, displaced: null };
	if (candidate && modelBillingReady(candidate)) return { model: candidate, displaced: null };
	return { model: models.find(modelBillingReady) ?? null, displaced: candidate ?? null };
}

type NamedBillingRow = BillingRow & { display_name: string };

/** Notice for a remembered model that can no longer be admitted. */
export function modelBillingFallbackNotice(displaced: NamedBillingRow, next: NamedBillingRow | null): string {
	const reason = modelBillingReason(displaced) ?? t('modelBilling.unready');
	return next
		? t('modelBilling.fallback', { previous: displaced.display_name, next: next.display_name, reason })
		: t('modelBilling.unavailable', { previous: displaced.display_name, reason });
}

/** Reason shown before sending when an agent is pinned to an unready model. */
export function agentModelBlockedMessage(model: NamedBillingRow): string | null {
	const reason = modelBillingReason(model);
	return reason === null ? null : t('modelBilling.agentBlocked', { name: model.display_name, reason });
}

export function noReadyModelsGuidance(): string {
	return t('modelBilling.noneReady');
}

const admissionRefusal = /^requested chat capability is not available: domain_billing \(([a-z_]+)\)$/;

/** Maps Lumen's 422 domain_billing admission refusal to the picker's localized reason. */
export function domainBillingAdmissionMessage(cause: unknown): string | undefined {
	if (!(cause instanceof Error) || !('status' in cause) || cause.status !== 422) return undefined;
	const match = admissionRefusal.exec(cause.message.trim());
	return match ? domainBillingReasonLabel(match[1]) : undefined;
}
