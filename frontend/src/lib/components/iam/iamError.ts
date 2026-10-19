import { ApiError } from '$lib/api/client';
import { t } from '$lib/i18n/ns/domain-iam';

// Stable backend codes; unknown codes keep the server detail rather than hiding it.
const CODE_KEYS = {
	identity_invalid_input: 'errorInvalidInput',
	last_login_method: 'errorLastLoginMethod',
	revision_conflict: 'errorRevisionConflict',
	smtp_not_configured: 'errorSmtpNotConfigured',
	signup_domains_required: 'errorSignupDomainsRequired',
	signup_domain_not_allowed: 'errorSignupDomainNotAllowed',
	invalid_email_domain: 'errorInvalidEmailDomain',
	invalid_scopes: 'errorInvalidScopes',
	unsafe_url: 'errorUnsafeUrl',
	provider_not_found: 'errorProviderNotFound',
	provider_name_conflict: 'errorProviderNameConflict',
	kind_immutable: 'errorKindImmutable',
	idp_not_found: 'errorIdpNotFound',
	idp_domain_mismatch: 'errorIdpDomainMismatch',
	idp_disabled: 'errorIdpDisabled',
	client_secret_required: 'errorClientSecretRequired',
	client_secret_replacement_required: 'errorClientSecretReplacementRequired',
	unsupported_token_auth_method: 'errorUnsupportedTokenAuthMethod',
	unavailable: 'errorUnavailable'
} as const;

export function iamErrorMessage(cause: unknown, fallback: string): string {
	if (cause instanceof ApiError && cause.code && cause.code in CODE_KEYS) return t(CODE_KEYS[cause.code as keyof typeof CODE_KEYS]);
	return cause instanceof Error && cause.message ? cause.message : fallback;
}
