import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { acceptAuthVerification, auth, getAuthVerificationEpoch, logoutInProgress, projectSwitching, setAuth } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { refreshAuthState } from '$lib/utils/authSession';
import type { MailSettings, MailDelivery, MailOperation } from '$lib/api/email';
import type { User } from '$lib/types/common';
import type * as EmailModule from '$lib/api/email';
import type { AnnouncementAdmin } from '$lib/types/announcements';
import { ApiError } from '$lib/api/errors';
const mocks = vi.hoisted(() => ({
	settings: vi.fn(), save: vi.fn(), reset: vi.fn(), check: vi.fn(), test: vi.fn(), message: vi.fn(), history: vi.fn(), receipt: vi.fn(), announcement: vi.fn(), preferences: vi.fn(), savePreferences: vi.fn(), confirm: vi.fn(),
}));
vi.mock('$lib/api/email', async importOriginal => ({
	...await importOriginal<typeof EmailModule>(),
	emailApi: mocks,
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
import AdminEmailSettingsPanel from '../AdminEmailSettingsPanel.svelte';
import AdminUserEmailComposer from '../users/AdminUserEmailComposer.svelte';
import EmailNotificationsSection from '../../account/EmailNotificationsSection.svelte';
import AnnouncementEmailAction from '../AnnouncementEmailAction.svelte';
import MailOperationResult from '../MailOperationResult.svelte';
import en from '$lib/i18n/messages/en/admin-email.json';
const catalogs = import.meta.glob<Record<string, string>>('$lib/i18n/messages/*/admin-email.json', { eager: true, import: 'default' });
const settings: MailSettings = {
	revision: 7, source: 'config',
	smtp: { enabled: true, host: 'smtp.example.test', port: 587, username: 'mailer', security: 'starttls', timeout_seconds: 10, password_configured: true, from_address: 'cloud@example.test', from_name: 'Cloud' },
	imap: { enabled: true, host: 'imap.example.test', port: 993, username: 'test', security: 'tls', timeout_seconds: 10, password_configured: true, mailbox: 'INBOX' },
	notifications: { announcements_enabled: true, resource_alerts_enabled: false },
};
const operationId = 'd06803e9-63c6-4a4f-a1ad-af62f2b08250';
const operation: MailOperation = { operation_id: operationId, kind: 'test', status: 'pending', counts: { pending: 1, dispatching: 0, accepted: 0, failed: 0, unknown: 0, cancelled: 0 } };
const delivery: MailDelivery = { id: 'delivery-id', operation_id: operationId, kind: 'test', user_id: null, recipient_email: 'test@example.test', subject: 'Connection test', status: 'accepted', error_code: null, message_id: '<stable@example.test>', created_at: '2026-11-03T00:00:00Z', updated_at: '2026-11-03T00:00:00Z' };
const user: User = { id: 'a718fbcb-a609-4d3a-986a-9e7d50840b69', name: 'Alice', email: 'alice@example.test', enabled: true, domain_id: 'home', default_project_id: null, created_at: null };
const announcement: AnnouncementAdmin = { id: 42, title: 'Maintenance', body: 'Scheduled work', severity: 'info', target_type: 'project', target_id: 'target-project', starts_at: '2099-01-01T00:00:00Z', ends_at: null, is_active: true, created_at: '', updated_at: 'revision-a', created_by_user_id: 'admin', created_by_username: 'Administrator' };
function deferred<T>() { return Promise.withResolvers<T>(); }
function element<T extends HTMLElement>(id: string): T { return document.getElementById(id) as T; }
async function submit(id: string) { await fireEvent.submit(element(id).closest('form')!); }
function renewAuth() {
	const current = get(auth);
	setAuth(refreshAuthState({
		token: 'renewed-token', refresh_token: 'renewed-refresh', user_id: current.userId!, username: 'Admin',
		domain_id: 'home', domain_name: 'Home', identity_domain_id: 'home', identity_domain_name: 'Home',
		project_id: 'project', project_name: 'Project', roles: ['admin'], is_system_admin: true,
		can_write: true, is_domain_manager: false, can_create_domain: false,
		available_domains: [{ id: 'home', name: 'Home' }], auth_method: 'password',
		expires_at: new Date(Date.now() + 3_600_000).toISOString(),
	}, current));
}
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	auth.set({ ...get(auth), sessionId: 'logical-login', token: 'admin-token', userId: 'admin', username: 'Admin', identityDomainId: 'home', domainId: 'home', projectId: 'project', roles: ['admin'], isSystemAdmin: true });
	expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
	logoutInProgress.set(false); projectSwitching.set(false);
	mocks.settings.mockResolvedValue(structuredClone(settings)); mocks.history.mockResolvedValue({ items: [], total: 0 });
	mocks.check.mockResolvedValue({ revision: 7, smtp: { status: 'ok' }, imap: { status: 'failed', code: 'mail_auth_failed' } });
	mocks.save.mockResolvedValue({ ...settings, revision: 8, source: 'runtime' }); mocks.reset.mockResolvedValue({ ...settings, revision: 9 });
	mocks.test.mockResolvedValue(operation); mocks.message.mockResolvedValue({ ...operation, kind: 'individual' });
	mocks.announcement.mockResolvedValue({ ...operation, kind: 'announcement' }); mocks.confirm.mockResolvedValue(true);
	mocks.preferences.mockResolvedValue({ announcements: true, resource_alerts: false });
	mocks.savePreferences.mockImplementation(async value => value);
	vi.spyOn(crypto, 'randomUUID').mockReturnValue(operationId);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); initLocale('ko'); });

describe('administrator saved mail settings', () => {
	it('keeps passwords masked and sends revision-fenced explicit secret actions, clearing drafts before settlement', async () => {
		const pending = deferred<MailSettings>(); mocks.save.mockReturnValueOnce(pending.promise);
		render(AdminEmailSettingsPanel);
		await screen.findByDisplayValue('smtp.example.test');
		expect(document.querySelector('input[type=password]')).toBeNull();
		await fireEvent.change(element('email-smtp-secret-action'), { target: { value: 'replace' } });
		await fireEvent.input(element('email-smtp-password'), { target: { value: 'ephemeral-secret' } });
		await fireEvent.change(element('email-imap-secret-action'), { target: { value: 'clear' } });
		await submit('email-smtp-host');
		expect(mocks.save).toHaveBeenCalledTimes(1);
		const payload = mocks.save.mock.calls[0][0];
		expect(payload.revision).toBe(7); expect(payload.smtp.password).toBe('ephemeral-secret');
		expect(payload.smtp).not.toHaveProperty('password_configured'); expect(payload.imap.clear_password).toBe(true);
		expect(document.querySelector('input[type=password]')).toBeNull();
		expect(document.body.textContent).not.toContain('ephemeral-secret');
		await submit('email-smtp-host'); expect(mocks.save).toHaveBeenCalledTimes(1);
		renewAuth();
		pending.resolve({ ...settings, revision: 8, source: 'runtime' });
		await screen.findByText(en.saved);
		expect(mocks.settings).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: en.check }));
		expect(mocks.check.mock.calls[0][0].token).toBe('renewed-token');
	});
	it('uses saved configuration for connection checks and reports SMTP and IMAP independently', async () => {
		render(AdminEmailSettingsPanel); await screen.findByDisplayValue('smtp.example.test');
		await fireEvent.input(element('email-smtp-host'), { target: { value: 'unsaved.example.test' } });
		await fireEvent.click(screen.getByRole('button', { name: en.check }));
		await screen.findByText('Checked revision 7');
		expect(mocks.check).toHaveBeenCalledWith(expect.objectContaining({ token: 'admin-token', project: 'project' }));
		expect(mocks.save).not.toHaveBeenCalled();
		expect(screen.getByText(en['status.ok'])).toBeTruthy(); expect(screen.getByText(en['status.failed'])).toBeTruthy();
		expect(element<HTMLInputElement>('email-smtp-host').value).toBe('unsaved.example.test');
	});
	it('requires refresh after conflict and never displays raw input/provider error text', async () => {
		mocks.save.mockRejectedValueOnce(new ApiError(409, 'ephemeral-secret provider diagnostic'));
		render(AdminEmailSettingsPanel); await screen.findByDisplayValue('smtp.example.test');
		await submit('email-smtp-host'); await screen.findByText(en.conflict);
		expect((screen.getByRole('button', { name: en.save }) as HTMLButtonElement).disabled).toBe(true);
		expect(document.body.textContent).not.toContain('ephemeral-secret');
		await fireEvent.click(screen.getAllByRole('button', { name: en.refresh })[0]);
		await waitFor(() => expect((screen.getByRole('button', { name: en.save }) as HTMLButtonElement).disabled).toBe(false));
	});
	it('resets only on explicit confirmation with the saved revision', async () => {
		render(AdminEmailSettingsPanel); await screen.findByDisplayValue('smtp.example.test');
		mocks.confirm.mockResolvedValueOnce(false);
		await fireEvent.click(screen.getByRole('button', { name: en.reset })); expect(mocks.reset).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: en.reset }));
		expect(mocks.reset).toHaveBeenCalledWith(7, expect.objectContaining({ token: 'admin-token' }));
		await fireEvent.click(screen.getByRole('button', { name: en.reset }));
		expect(mocks.reset).toHaveBeenLastCalledWith(9, expect.objectContaining({ token: 'admin-token' }));
	});
	it('clears secrets and rejects a late same-tick owner ABA result', async () => {
		const pending = deferred<MailSettings>(); mocks.save.mockReturnValueOnce(pending.promise);
		render(AdminEmailSettingsPanel); await screen.findByDisplayValue('smtp.example.test');
		await fireEvent.change(element('email-smtp-secret-action'), { target: { value: 'replace' } });
		await fireEvent.input(element('email-smtp-password'), { target: { value: 'private-draft' } });
		await submit('email-smtp-host');
		const original = get(auth); auth.set({ ...original, projectId: 'foreign' }); auth.set(original);
		pending.resolve({ ...settings, smtp: { ...settings.smtp, host: 'stale-result.example.test' } }); await tick();
		expect(screen.queryByDisplayValue('stale-result.example.test')).toBeNull();
		expect(document.querySelector('input[type=password]')).toBeNull();
		expect(screen.queryByText(en.saved)).toBeNull();
	});
	it.each(['accepted', 'unknown'] as const)('keeps original SMTP %s separate from confirmed mailbox receipt, with manual history refresh', async status => {
		mocks.history.mockResolvedValue({ items: [{ ...delivery, status }], total: 1 });
		mocks.receipt.mockResolvedValueOnce({ status: 'not_found' }).mockResolvedValueOnce({ status: 'confirmed' });
		render(AdminEmailSettingsPanel); await screen.findByText('Connection test');
		expect(screen.getByText(en[`status.${status}`])).toBeTruthy(); expect(screen.queryByText(en['status.confirmed'])).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: en.receipt }));
		await screen.findByText(en['status.not_found']); expect(screen.queryByText(en['status.confirmed'])).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: en.receipt })); await screen.findByText(en['status.confirmed']);
		expect(screen.getByText(en[`status.${status}`])).toBeTruthy();
		expect(mocks.receipt).toHaveBeenLastCalledWith('delivery-id', expect.objectContaining({ token: 'admin-token' }));
		await fireEvent.click(screen.getAllByRole('button', { name: en.refresh })[1]);
		expect(mocks.history).toHaveBeenCalledTimes(2);
	});
	it('queues one explicit test and blocks automatic replay after an unknown result', async () => {
		mocks.test.mockRejectedValue(new Error('SMTP-password raw error'));
		render(AdminEmailSettingsPanel); await screen.findByDisplayValue('smtp.example.test');
		await fireEvent.input(element('email-test-recipient'), { target: { value: 'test@example.test' } });
		await submit('email-test-recipient'); await screen.findByText(en.unknown);
		await submit('email-test-recipient');
		expect(mocks.test).toHaveBeenCalledTimes(1);
		expect(mocks.test).toHaveBeenCalledWith(operationId, 'test@example.test', expect.objectContaining({ token: 'admin-token' }));
		expect(document.body.textContent).toContain(operationId); expect(document.body.textContent).not.toContain('SMTP-password');
	});
});

describe('registered-user compose and account preferences', () => {
	it('submits only the immutable selected ID and clears authored content after durable acceptance', async () => {
		const pending = deferred<MailOperation>(); mocks.message.mockReturnValueOnce(pending.promise);
		render(AdminUserEmailComposer, { user, domainId: 'home' });
		await fireEvent.click(screen.getByRole('button', { name: en.compose }));
		expect(screen.queryByRole('textbox', { name: en.recipient })).toBeNull();
		await fireEvent.input(element('user-email-subject'), { target: { value: 'Private subject' } });
		await fireEvent.input(element('user-email-body'), { target: { value: '<b>Plain text only</b>' } });
		await submit('user-email-subject');
		expect(mocks.message).toHaveBeenCalledWith(operationId, [user.id], 'Private subject', '<b>Plain text only</b>', expect.objectContaining({ token: 'admin-token' }));
		expect(element<HTMLInputElement>('user-email-subject').value).toBe('Private subject'); expect(element<HTMLTextAreaElement>('user-email-body').value).toBe('<b>Plain text only</b>');
		await submit('user-email-subject'); expect(mocks.message).toHaveBeenCalledTimes(1);
		pending.resolve({ ...operation, kind: 'individual' }); await screen.findByText(en.queued);
		expect(element<HTMLInputElement>('user-email-subject').value).toBe(''); expect(element<HTMLTextAreaElement>('user-email-body').value).toBe('');
	});
	it.each([409, 422, 503])('keeps a rejected draft editable after HTTP%s and assigns a fresh operation to explicit resubmission', async status => {
		mocks.message.mockRejectedValueOnce(new ApiError(status, 'private-diagnostic', status === 503 ? 'mail_identity_unavailable' : 'mail_recipient_ineligible'));
		vi.mocked(crypto.randomUUID).mockReturnValueOnce(operationId).mockReturnValueOnce('a06803e9-63c6-4a4f-a1ad-af62f2b08250');
		render(AdminUserEmailComposer, { user, domainId: 'home' });
		await fireEvent.click(screen.getByRole('button', { name: en.compose }));
		await fireEvent.input(element('user-email-subject'), { target: { value: 'Retained subject' } });
		await fireEvent.input(element('user-email-body'), { target: { value: 'Retained body' } });
		await submit('user-email-subject');
		expect(element<HTMLInputElement>('user-email-subject').value).toBe('Retained subject');
		expect(element<HTMLTextAreaElement>('user-email-body').value).toBe('Retained body');
		expect((screen.getByRole('button', { name: en.send }) as HTMLButtonElement).disabled).toBe(false);
		expect(screen.queryByText(en.unknown)).toBeNull(); expect(document.body.textContent).not.toContain('private-diagnostic');
		await submit('user-email-subject');
		expect(mocks.message).toHaveBeenCalledTimes(2); expect(mocks.message.mock.calls[1][0]).toBe('a06803e9-63c6-4a4f-a1ad-af62f2b08250');
	});
	it('preserves a compose draft through token renewal but clears it for the next selected user', async () => {
		const view = render(AdminUserEmailComposer, { user, domainId: 'home' });
		await fireEvent.click(screen.getByRole('button', { name: en.compose }));
		await fireEvent.input(element('user-email-subject'), { target: { value: 'Keep during refresh' } });
		renewAuth(); await tick();
		expect(element<HTMLInputElement>('user-email-subject').value).toBe('Keep during refresh');
		await view.rerender({ user: { ...user, id: 'bob', email: 'bob@example.test' }, domainId: 'home' });
		expect(screen.queryByDisplayValue('Keep during refresh')).toBeNull(); expect(screen.getByRole('button', { name: en.compose })).toBeTruthy();
	});
	it('loads and explicitly saves both owner-bound notification preferences', async () => {
		auth.update(state => ({ ...state, isSystemAdmin: false }));
		render(EmailNotificationsSection);
		await waitFor(() => expect(element<HTMLInputElement>('email-preference-announcements').disabled).toBe(false));
		expect(element<HTMLInputElement>('email-preference-announcements').checked).toBe(true);
		expect(element<HTMLInputElement>('email-preference-resource-alerts').checked).toBe(false);
		await fireEvent.click(element('email-preference-resource-alerts'));
		expect(mocks.savePreferences).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: en.save })); await screen.findByText(en.preferenceSaved);
		expect(mocks.savePreferences).toHaveBeenCalledWith({ announcements: true, resource_alerts: true }, expect.objectContaining({ token: 'admin-token' }));
	});
	it('does not publish another owner’s late preference response after ABA', async () => {
		const pending = deferred<{ announcements: boolean; resource_alerts: boolean }>();
		const fresh = deferred<{ announcements: boolean; resource_alerts: boolean }>();
		mocks.preferences.mockReturnValueOnce(pending.promise).mockReturnValueOnce(fresh.promise);
		render(EmailNotificationsSection);
		await waitFor(() => expect(mocks.preferences).toHaveBeenCalledTimes(1));
		const original = get(auth); auth.set({ ...original, userId: 'other' }); auth.set(original);
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		await waitFor(() => expect(mocks.preferences).toHaveBeenCalledTimes(2));
		pending.resolve({ announcements: false, resource_alerts: true }); await tick();
		expect(element<HTMLInputElement>('email-preference-announcements').disabled).toBe(true);
		fresh.resolve({ announcements: true, resource_alerts: false });
		await waitFor(() => expect(element<HTMLInputElement>('email-preference-announcements').disabled).toBe(false));
		expect(element<HTMLInputElement>('email-preference-resource-alerts').checked).toBe(false);
	});
});

describe('explicit announcement email', () => {
	it('shows deferred scheduled audience as unknown cardinality, not zero recipients', () => {
		const view = render(MailOperationResult, { operation: { ...operation, kind: 'announcement', audience_pending: true, counts: { pending: 0, dispatching: 0, accepted: 0, failed: 0, unknown: 0, cancelled: 0 } } });
		expect(screen.getByText(en.audiencePending)).toBeTruthy();
		expect(screen.getByText(en['status.pending'])).toBeTruthy();
		expect(view.container.querySelector('dl')).toBeNull();
	});
	it('explains schedule before queuing and never submits a recipient override', async () => {
		render(AnnouncementEmailAction, { announcement });
		await fireEvent.click(screen.getByRole('button', { name: en.sendAnnouncement }));
		expect(mocks.confirm).toHaveBeenCalledWith(expect.stringContaining(en.schedule));
		expect(mocks.announcement).toHaveBeenCalledWith(42, operationId, expect.objectContaining({ token: 'admin-token' }));
		await screen.findByRole('link', { name: en.history }); expect(mocks.announcement).toHaveBeenCalledTimes(1);
	});
	it('unlocks a definitively rejected announcement action without creating an unknown outcome', async () => {
		mocks.announcement.mockRejectedValueOnce(new ApiError(422, 'private-diagnostic', 'mail_invalid_schedule'));
		render(AnnouncementEmailAction, { announcement });
		await fireEvent.click(screen.getByRole('button', { name: en.sendAnnouncement }));
		await waitFor(() => expect((screen.getByRole('button', { name: en.sendAnnouncement }) as HTMLButtonElement).disabled).toBe(false));
		expect(screen.queryByText(en.unknown)).toBeNull(); expect(document.body.textContent).not.toContain('private-diagnostic');
		await fireEvent.click(screen.getByRole('button', { name: en.sendAnnouncement }));
		expect(mocks.announcement).toHaveBeenCalledTimes(2);
	});
	it('cancellation sends nothing and owner replacement while confirmation is open discards the action', async () => {
		const confirmation = deferred<boolean>(); mocks.confirm.mockReturnValueOnce(confirmation.promise);
		render(AnnouncementEmailAction, { announcement });
		await fireEvent.click(screen.getByRole('button', { name: en.sendAnnouncement }));
		const original = get(auth); auth.set({ ...original, projectId: 'other' }); auth.set(original);
		confirmation.resolve(true); await tick(); expect(mocks.announcement).not.toHaveBeenCalled();
	});
});

describe('email locale coverage', () => {
	it('has native complete catalogs for every supported locale', () => {
		expect(Object.keys(catalogs)).toHaveLength(9);
		for (const catalog of Object.values(catalogs)) {
			expect(Object.keys(catalog).sort()).toEqual(Object.keys(en).sort());
			for (const value of Object.values(catalog)) expect(value.trim()).not.toBe('');
		}
	});
});
