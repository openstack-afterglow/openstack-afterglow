import { api, ApiError } from '$lib/api/client';

export interface MailTransport {
	enabled: boolean;
	host: string;
	port: number;
	username: string;
	security: 'starttls' | 'tls' | 'none';
	timeout_seconds: number;
	password_configured: boolean;
}
export interface MailSettings {
	revision: number;
	source: 'config' | 'runtime';
	smtp: MailTransport & { from_address: string; from_name: string };
	imap: MailTransport & { mailbox: string };
	notifications: { announcements_enabled: boolean; resource_alerts_enabled: boolean };
}
export type SecretAction = 'keep' | 'replace' | 'clear';
export interface MailSecretUpdate { password?: string; clear_password?: boolean; reconfirm_password?: boolean }
export type MailSettingsUpdate = {
	revision: number;
	smtp: Omit<MailSettings['smtp'], 'password_configured'> & MailSecretUpdate;
	imap: Omit<MailSettings['imap'], 'password_configured'> & MailSecretUpdate;
	notifications: MailSettings['notifications'];
};
export type DeliveryStatus = 'pending' | 'dispatching' | 'accepted' | 'failed' | 'unknown' | 'cancelled';
export interface MailOperation {
	operation_id: string;
	kind: string;
	status: DeliveryStatus | 'partial';
	counts: Record<DeliveryStatus, number>;
	audience_pending?: boolean;
}
export interface MailDelivery {
	id: string;
	operation_id: string;
	kind: string;
	user_id: string | null;
	recipient_email: string;
	subject: string;
	status: DeliveryStatus;
	error_code: string | null;
	message_id: string;
	created_at: string;
	updated_at: string;
}
export interface MailHistory { items: MailDelivery[]; total: number }
export interface MailConnectionCheck {
	revision: number;
	smtp: { status: 'ok' | 'failed' | 'disabled'; code?: string };
	imap: { status: 'ok' | 'failed' | 'disabled'; code?: string };
}
export interface MailReceipt { status: 'confirmed' | 'not_found' | 'disabled' | 'failed' | 'not_sent'; code?: string }
export interface MailPreferences { announcements: boolean; resource_alerts: boolean }
export interface MailAuthority { token: string; project?: string }
const options = { cache: 'no-store' as const, replayOnUnauthorized: false };
const root = '/api/v1/admin/email';
const MAIL_REJECTION_CODES: Record<string, true> = {
	mail_invalid_operation_id: true, mail_invalid_subject: true, mail_invalid_body: true, mail_invalid_email: true,
	mail_invalid_user_ids: true, mail_invalid_schedule: true, mail_recipient_ineligible: true, mail_operation_conflict: true,
	mail_announcement_not_found: true, mail_announcement_inactive: true, mail_announcement_scheduled: true,
	mail_announcement_changed: true, mail_identity_required: true, mail_identity_changed: true, mail_identity_unavailable: true,
	system_admin_required: true,
};

// Do not render server/provider prose: even validation errors could contain a submitted secret.
export function mailError(error: unknown): 'conflict' | 'failed' {
	return error instanceof ApiError && error.status === 409 ? 'conflict' : 'failed';
}

/** A rejected intent is editable; an uncertain enqueue must never be replayed. */
export function mailDispatchFailure(error: unknown): { status: 'rejected' | 'indeterminate'; message: 'rejected' | 'unknown'; code?: string } {
	const code = error instanceof ApiError && error.code && Object.hasOwn(MAIL_REJECTION_CODES, error.code) ? error.code : undefined;
	const rejected = error instanceof ApiError && ((error.status >= 400 && error.status < 500)
		|| (error.status === 503 && code === 'mail_identity_unavailable'));
	return rejected ? { status: 'rejected', message: 'rejected', code } : { status: 'indeterminate', message: 'unknown' };
}
export function secretUpdate(action: SecretAction, password: string, reconfirm: boolean): MailSecretUpdate {
	return action === 'replace' ? { password } : action === 'clear' ? { clear_password: true } : reconfirm ? { reconfirm_password: true } : {};
}
export const emailApi = {
	settings: (a: MailAuthority) => api.get<MailSettings>(`${root}/settings`, a.token, a.project, { ...options, refresh: true }),
	save: (payload: MailSettingsUpdate, a: MailAuthority) => api.put<MailSettings>(`${root}/settings`, payload, a.token, a.project, options),
	reset: (revision: number, a: MailAuthority) => api.delete<MailSettings>(`${root}/settings?revision=${revision}`, a.token, a.project, options),
	check: (a: MailAuthority) => api.post<MailConnectionCheck>(`${root}/connection-check`, {}, a.token, a.project, { ...options, timeoutMs: 75_000 }),
	test: (operation_id: string, recipient_email: string, a: MailAuthority) => api.post<MailOperation>(`${root}/test-message`, { operation_id, recipient_email }, a.token, a.project, options),
	message: (operation_id: string, user_ids: string[], subject: string, body: string, a: MailAuthority) => api.post<MailOperation>(`${root}/messages`, { operation_id, user_ids, subject, body }, a.token, a.project, options),
	history: (offset: number, a: MailAuthority) => api.get<MailHistory>(`${root}/deliveries?limit=50&offset=${offset}`, a.token, a.project, { ...options, refresh: true }),
	receipt: (delivery_id: string, a: MailAuthority) => api.post<MailReceipt>(`${root}/receipt-check`, { delivery_id }, a.token, a.project, { ...options, timeoutMs: 45_000 }),
	announcement: (id: number, operation_id: string, a: MailAuthority) => api.post<MailOperation>(`/api/v1/admin/announcements/${id}/email`, { operation_id }, a.token, a.project, options),
	preferences: (a: MailAuthority) => api.get<MailPreferences>('/api/v1/profile/email-notifications', a.token, a.project, { ...options, refresh: true }),
	savePreferences: (payload: MailPreferences, a: MailAuthority) => api.put<MailPreferences>('/api/v1/profile/email-notifications', payload, a.token, a.project, options),
};
