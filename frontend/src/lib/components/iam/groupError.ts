import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/domain-iam-groups';
import { iamErrorMessage } from './iamError';

// Stable /api/v1/iam/groups details; anything else keeps the shared IAM mapping.
const DETAIL_KEYS = {
	domain_group_not_found: 'errorNotFound',
	domain_group_name_exists: 'errorNameExists',
	domain_group_name_reserved: 'errorNameReserved',
	domain_group_read_only: 'errorReadOnly',
	domain_manager_projection_is_private: 'errorReserved',
	domain_group_member_exists: 'errorMemberExists',
	domain_group_member_not_found: 'errorMemberNotFound',
	'Privileged accounts are read-only in domain IAM': 'errorPrivileged',
	'User has not joined this domain': 'errorNotJoined',
	'Owner-bearing group grants require an explicit project ownership transition': 'errorOwnerGrant'
} as const;

export function groupErrorMessage(cause: unknown, fallback: string): string {
	if (cause instanceof ApiError && cause.message in DETAIL_KEYS) return t(DETAIL_KEYS[cause.message as keyof typeof DETAIL_KEYS]);
	return iamErrorMessage(cause, fallback);
}

/** Boundary codes describe the target, not lost manager authority. */
export function groupAuthorityLost(cause: unknown): boolean {
	return cause instanceof ApiError && cause.status === 403 && !(cause.message in DETAIL_KEYS);
}
