export interface EnrollmentPolicyWrite {
	revision: number;
	public_signup_enabled: boolean;
	approval_mode: 'auto' | 'admin';
	/** Sparse native quota keys. Omission retains the native default; -1 is unlimited. */
	personal_quotas: Record<string, number>;
}

export interface EnrollmentPolicy extends EnrollmentPolicyWrite {
	quota_fields: Record<string, string[]>;
	defaults_future_only: true;
	smtp_configured: boolean;
}

export type SignupRequestStatus = 'pending' | 'approved' | 'rejected' | 'consumed';
export type SignupRequestFilter = Exclude<SignupRequestStatus, 'consumed'> | 'all';

/** The review response has no mail delivery receipt and creates no native account. */
export interface SignupRequest {
	id: string;
	source: 'email' | 'oidc' | 'github';
	email: string;
	domain_id: string | null;
	provider_id: string | null;
	status: SignupRequestStatus;
	created_at: string;
	reviewed_at: string | null;
	reviewed_by_user_id: string | null;
}

export interface SignupRequestPage {
	items: SignupRequest[];
	next_cursor: string | null;
}
