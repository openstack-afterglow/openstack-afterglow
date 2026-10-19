import type { IamEnrollmentStatus } from '$lib/api/domainIam';
import { t } from '$lib/i18n/ns/domain-iam';

const LABEL_KEYS = {
	delivery_pending: 'deliveryPending',
	pending: 'pending',
	accepted: 'accepted',
	revoked: 'revoked',
	expired: 'expired',
	delivery_failed: 'deliveryFailed',
	account_creating: 'accountCreating',
	granting: 'granting',
	activating: 'activating',
	recovery_required: 'recoveryRequired',
	failed: 'failed',
} as const satisfies Record<IamEnrollmentStatus, string>;

/** Localized label for a server enrollment status; an unknown status stays visible verbatim. */
export function enrollmentStatusLabel(status: string): string {
	return Object.hasOwn(LABEL_KEYS, status) ? t(LABEL_KEYS[status as IamEnrollmentStatus]) : status;
}
