// Tab-local, secret-free continuation state for provider sign-in and onboarding.
const PROVIDER_LOGIN_KEY = 'afterglow_provider_login';
const PENDING_INVITATION_KEY = 'afterglow_pending_invitation';
// Onboarding tokens are opaque URL-safe strings; anything else never becomes a path.
const ONBOARDING_TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,512}$/;
const LOOPBACK_HOSTS: Record<string, true> = { localhost: true, '127.0.0.1': true, '[::1]': true };

export interface PendingProviderLogin {
	domainId: string;
	providerId: string;
}

function storage(): Storage | null {
	if (typeof window === 'undefined') return null;
	try {
		return window.sessionStorage;
	} catch {
		return null;
	}
}

export function isOnboardingToken(value: string): boolean {
	return ONBOARDING_TOKEN_PATTERN.test(value);
}

/** Provider authorization must leave only for HTTPS, or HTTP on a loopback development IdP. */
export function isSafeAuthorizeUrl(raw: string): boolean {
	let url: URL;
	try {
		url = new URL(raw);
	} catch {
		return false;
	}
	if (url.username || url.password) return false;
	return url.protocol === 'https:' || (url.protocol === 'http:' && LOOPBACK_HOSTS[url.hostname] === true);
}

export function storePendingProviderLogin(pending: PendingProviderLogin): void {
	try {
		storage()?.setItem(PROVIDER_LOGIN_KEY, JSON.stringify(pending));
	} catch { /* the server-side state cookie remains authoritative */ }
}

/** Reads and clears the exact registration origin and provider chosen before redirect. */
export function takePendingProviderLogin(): PendingProviderLogin | null {
	const store = storage();
	if (!store) return null;
	try {
		const raw = store.getItem(PROVIDER_LOGIN_KEY);
		store.removeItem(PROVIDER_LOGIN_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as Partial<PendingProviderLogin>;
		if (typeof parsed.domainId !== 'string' || !parsed.domainId || typeof parsed.providerId !== 'string' || !parsed.providerId) return null;
		return { domainId: parsed.domainId, providerId: parsed.providerId };
	} catch {
		return null;
	}
}

export function storePendingInvitation(token: string): void {
	if (!isOnboardingToken(token)) return;
	try {
		storage()?.setItem(PENDING_INVITATION_KEY, token);
	} catch { /* the user can reopen the emailed link */ }
}

/** Returns the invitation to resume after sign-in, clearing it so it resumes once. */
export function takePendingInvitationPath(): string | null {
	const store = storage();
	if (!store) return null;
	try {
		const token = store.getItem(PENDING_INVITATION_KEY);
		store.removeItem(PENDING_INVITATION_KEY);
		return token && isOnboardingToken(token) ? `/invitations/${token}` : null;
	} catch {
		return null;
	}
}

export type OnboardingErrorKey =
	| 'onboarding.linkInvalid'
	| 'onboarding.accountExists'
	| 'onboarding.invalidInput'
	| 'onboarding.unavailable'
	| 'onboarding.failed';

/** Maps onboarding API failures to fixed messages; server text can echo submitted input. */
export function onboardingErrorKey(status: number | null): OnboardingErrorKey {
	if (status === 404 || status === 410) return 'onboarding.linkInvalid';
	if (status === 409) return 'onboarding.accountExists';
	if (status === 400 || status === 422) return 'onboarding.invalidInput';
	if (status === null || status === 0 || status === 429 || status === 503) return 'onboarding.unavailable';
	return 'onboarding.failed';
}

/** Only exact registration conflicts can authorize a username retry or identify an existing email. */
export function registrationConflictKind(error: { status: number; code?: string; message: string }): 'username' | 'email' | 'recovery' | null {
	if (error.status !== 409) return null;
	if (error.code === 'signup_enrollment_recovery_required' || error.message === 'signup_enrollment_recovery_required') return 'recovery';
	if (error.message === 'Username already belongs to an account') return 'username';
	if (error.message === 'Account already exists; sign in to accept an invitation') return 'email';
	return null;
}

export type SignupApprovalState = 'pending' | 'rejected';

/** Only these exact forbidden responses represent an enrollment decision. Never render server text. */
export function signupApprovalState(error: { status: number; code?: string; message: string }): SignupApprovalState | null {
	if (error.status !== 403) return null;
	if (error.code === 'signup_approval_pending' || error.message === 'signup_approval_pending') return 'pending';
	if (error.code === 'signup_approval_rejected' || error.message === 'signup_approval_rejected') return 'rejected';
	return null;
}
