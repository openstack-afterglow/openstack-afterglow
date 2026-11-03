import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
import type { SignupOptions } from '$lib/types/enrollmentPolicy';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), goto: vi.fn(), clearAuth: vi.fn(), close: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock('$app/stores', () => ({ page: writable({ params: { token: 'recovery_token_12345678901234567890' } }) }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto, invalidate: vi.fn().mockResolvedValue(undefined) }));
vi.mock('$lib/stores/cloudShell.svelte', () => ({ cloudShell: { close: mocks.close } }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: mocks.success, error: mocks.error } }));
vi.mock('$lib/stores/auth', () => ({
 auth: writable({ token: null, userId: null, identityDomainId: null, projectId: null, domainId: null, sessionId: null }),
 authReady: writable(true), logoutInProgress: writable(false), projectSwitching: writable(false), clearAuth: mocks.clearAuth,
}));
import { auth, authReady, logoutInProgress } from '$lib/stores/auth';
import { freshLoginDestination } from '$lib/utils/mcpConsent';
import { page } from '$app/stores';
import Request from '../AccountEmailRequest.svelte';
import Recovery from '../../../../routes/recover/[token]/+page.svelte';
const tokenPage = page as unknown as Writable<{ params: { token: string }; url?: URL }>;
const token = 'recovery_token_12345678901234567890';
const options: SignupOptions = { signup_enabled: true, signup_button_visible: true, smtp_configured: true, recovery_enabled: true };
const requestOptions = { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false };
function signedIn(reauthenticated = true) {
 auth.update(state => ({ ...state, federated: true, token: 'signed-in-token', userId: 'alice', identityDomainId: 'home', domainId: 'workspace', projectId: 'project', sessionId: 'session' }));
 tokenPage.update(state => ({ ...state, url: new URL(`http://localhost/recover/${token}${reauthenticated ? '?reauthenticated=1' : ''}`) }));
}
beforeEach(() => {
 vi.resetAllMocks(); initLocale('en');
 sessionStorage.clear(); history.replaceState(null, '', '/');
 auth.update(state => ({ ...state, token: null, userId: null, identityDomainId: null, projectId: null, domainId: null, sessionId: undefined }));
 (authReady as Writable<boolean>).set(true); (logoutInProgress as Writable<boolean>).set(false);
 mocks.goto.mockResolvedValue(undefined); mocks.close.mockResolvedValue(undefined);
 tokenPage.set({ params: { token }, url: new URL(`http://localhost/recover/${token}`) });
 mocks.get.mockResolvedValue(options); mocks.post.mockResolvedValue({ accepted: true });
});
afterEach(() => vi.restoreAllMocks());
afterEach(() => { cleanup(); initLocale('ko'); });

describe('public email-first entry', () => {
 it.each([true, false])('posts signup email without domain or credentials even when signup link visibility is %s', async visible => {
  mocks.get.mockResolvedValueOnce({ ...options, signup_button_visible: visible });
  render(Request, { signup: true });
  await fireEvent.input(await screen.findByLabelText(/^Email/), { target: { value: 'alice@example.com' } });
  await fireEvent.click(screen.getByRole('button', { name: 'Send verification link' }));
  expect(await screen.findByText('If this address can sign up, a verification link has been sent. Check your inbox.')).toBeTruthy();
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/registrations', { email: 'alice@example.com' }, undefined, undefined, requestOptions);
  expect(screen.queryByLabelText(/^Password/)).toBeNull();
 });
 it.each(['username', 'password'])('requests %s recovery independently of signup visibility and permission', async kind => {
  mocks.get.mockResolvedValueOnce({ ...options, signup_enabled: false, signup_button_visible: false });
  render(Request);
  await fireEvent.click(await screen.findByLabelText(kind === 'username' ? 'Find username' : 'Reset password'));
  await fireEvent.input(screen.getByLabelText(/^Email/), { target: { value: 'alice@example.com' } });
  await fireEvent.click(screen.getByRole('button', { name: 'Send verification link' }));
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(`/api/v1/auth/recovery/${kind}`, { email: 'alice@example.com' }, undefined, undefined, requestOptions));
  expect(await screen.findByText('Request accepted. If this address is eligible, an email will be sent. Acceptance does not confirm delivery. Check your inbox; if no email arrives or you cannot access it, contact your administrator.')).toBeTruthy();
  expect(mocks.post).toHaveBeenCalledOnce();
 });
 it('does not invent success when SMTP readiness is unavailable', async () => {
  mocks.get.mockResolvedValue({ ...options, smtp_configured: false });
  render(Request, { signup: true });
  expect(await screen.findByText('Email requests are not currently available. Contact your administrator or try again later.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Send verification link' })).toBeNull();
  expect(mocks.post).not.toHaveBeenCalled();
 });
 it('renders safe failure instead of accepted confirmation on transport error', async () => {
  mocks.post.mockRejectedValue(new ApiError(503, 'secret-server-value'));
  render(Request);
  await fireEvent.input(await screen.findByLabelText(/^Email/), { target: { value: 'alice@example.com' } });
  await fireEvent.click(screen.getByRole('button', { name: 'Send verification link' }));
  expect(await screen.findByText('The verification link could not be sent. Try again shortly.')).toBeTruthy();
  expect(screen.queryByText(/If this address is eligible/)).toBeNull();
  expect(document.body.textContent).not.toContain('secret-server-value');
 });
 it.each([
  ['ko', '비밀번호 자체는 보내지 않습니다'],
  ['en', 'it never sends the password itself'],
  ['ja', 'パスワード自体は送信しません'],
  ['zh-CN', '不会发送密码本身'],
  ['sw', 'hakitumi nenosiri lenyewe'],
  ['nb', 'selve passordet sendes aldri'],
  ['ms', 'kata laluan itu sendiri tidak dihantar'],
  ['vi', 'không gửi chính mật khẩu'],
  ['bn', 'পাসওয়ার্ড নিজে পাঠানো হয় না'],
 ] as const)('explains that recovery mail opens a form instead of emailing a password (%s)', async (locale, guidance) => {
  initLocale(locale); render(Request);
  await fireEvent.click((await screen.findAllByRole('radio'))[1]);
  expect(screen.getByText(text => text.includes(guidance))).toBeTruthy();
  expect(screen.queryByLabelText(/^Password$/)).toBeNull();
  expect(mocks.post).not.toHaveBeenCalled();
 });
});

describe('one-use recovery token', () => {
 it('reveals original username and home only from the non-cached token inspection', async () => {
  mocks.get.mockResolvedValue({ kind: 'username', email: 'alice@example.com', username: 'original-alice', identity_domain_id: 'original-home', identity_domain_name: 'Home' });
  render(Recovery);
  expect(await screen.findByText('original-alice')).toBeTruthy();
  expect(mocks.get).toHaveBeenCalledWith(`/api/v1/auth/recovery/${token}`, undefined, undefined, expect.objectContaining({ cache: 'no-store', refresh: true, replayOnUnauthorized: false }));
  expect(screen.getByRole('link', { name: 'Back to sign-in' }).getAttribute('href')).toBe('/login');
  expect(mocks.post).not.toHaveBeenCalled();
 });
 it('keeps a consumed username result when changing the open page language without inspecting again', async () => {
  mocks.get.mockResolvedValue({ kind: 'username', email: 'alice@example.com', username: 'original-alice', identity_domain_id: 'original-home', identity_domain_name: 'Home' });
  render(Recovery);
  await screen.findByText('original-alice');
  await fireEvent.click(document.getElementById('recover-token-locale')!);
  await fireEvent.click(document.querySelector('button.locale-choice[lang="ko"]')!);
  await screen.findByRole('heading', { level: 1, name: '계정 찾기' });
  expect(screen.getByText('original-alice')).toBeTruthy();
  expect(screen.getByText('original-home')).toBeTruthy();
  expect(mocks.get).toHaveBeenCalledOnce();
  expect(mocks.post).not.toHaveBeenCalled();
 });
 it('validates matching password, consumes once without replay, and clears secrets before waiting', async () => {
  mocks.get.mockResolvedValue({ kind: 'password', email: 'alice@example.com' });
  const pending = Promise.withResolvers<{ status: string }>(); mocks.post.mockReturnValue(pending.promise);
  render(Recovery);
  const password = await screen.findByLabelText(/^Password/) as HTMLInputElement;
  const confirm = screen.getByLabelText(/^Confirm password/) as HTMLInputElement;
  await fireEvent.input(password, { target: { value: 'long-new-password' } });
  await fireEvent.input(confirm, { target: { value: 'mismatch-password' } });
  await fireEvent.click(screen.getByRole('button', { name: 'Save new password' }));
  expect(mocks.post).not.toHaveBeenCalled();
  await fireEvent.input(confirm, { target: { value: 'long-new-password' } });
  await fireEvent.submit(password.form!); await fireEvent.submit(password.form!);
  expect(mocks.post).toHaveBeenCalledOnce();
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/recovery/password/complete', { token, new_password: 'long-new-password' }, undefined, undefined, requestOptions);
  expect(password.value).toBe(''); expect(confirm.value).toBe('');
  pending.resolve({ status: 'changed' });
  expect(await screen.findByText('The change is complete. Existing sessions have been revoked; sign in again.')).toBeTruthy();
 });
 it('requires explicit approval before consuming an email-change token', async () => {
  mocks.get.mockResolvedValue({ kind: 'email_change', email: 'new@example.com' });
  render(Recovery);
  const accept = await screen.findByRole('button', { name: 'Confirm email change' });
  expect(mocks.post).not.toHaveBeenCalled();
  await fireEvent.click(accept);
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/email/changes/accept', { token }, undefined, undefined, requestOptions);
 });
 it('does not report changed or replay an uncertain native email-change result', async () => {
  mocks.get.mockResolvedValue({ kind: 'email_change', email: 'new@example.com' });
  mocks.post.mockRejectedValue(new ApiError(503, 'native-secret-do-not-render'));
  render(Recovery);
  const accept = await screen.findByRole('button', { name: 'Confirm email change' }) as HTMLButtonElement;
  await fireEvent.click(accept);
  await screen.findByRole('link', { name: 'Request a new link' });
  expect(accept.disabled).toBe(true);
  expect(screen.queryByText('The change is complete. Existing sessions have been revoked; sign in again.')).toBeNull();
  expect(document.body.textContent).not.toContain('native-secret-do-not-render');
  await fireEvent.submit(accept.form!);
  expect(mocks.post).toHaveBeenCalledOnce();
 });

 it('discards a username revealed after navigation to a different token', async () => {
  const pending = Promise.withResolvers<object>(); mocks.get.mockReturnValueOnce(pending.promise);
  mocks.get.mockResolvedValueOnce({ kind: 'password', email: 'other@example.com' });
  render(Recovery); await waitFor(() => expect(mocks.get).toHaveBeenCalledOnce());
  tokenPage.set({ params: { token: 'other_recovery_token_1234567890' } });
  await screen.findByLabelText(/^Password/);
  pending.resolve({ kind: 'username', username: 'must-not-appear' });
  await pending.promise;
  expect(screen.queryByText('must-not-appear')).toBeNull();
 });

 it('keeps an unsigned mailed creation link tab-local through fresh provider login', async () => {
  mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com', identity_domain_id: 'home' });
  render(Recovery);
  const signIn = await screen.findByRole('button', { name: 'Sign in again with your provider' });
  expect(screen.queryByLabelText(/^Password/)).toBeNull();
  expect(location.href).not.toContain(token);
  await fireEvent.click(signIn);
  expect(mocks.goto).toHaveBeenCalledWith('/login?reauthenticate=1');
  expect(mocks.post).not.toHaveBeenCalled();
  signedIn();
  expect(freshLoginDestination('/dashboard')).toBe(`/recover/${token}?reauthenticated=1`);
  expect(sessionStorage.getItem('afterglow_password_create_continuation')).toBeNull();
  expect(freshLoginDestination('/dashboard')).toBe('/dashboard');
 });

 it('retains fresh-return presentation through initial verification, not a later readiness ABA', async () => {
  signedIn(); (authReady as Writable<boolean>).set(false);
  mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com' });
  render(Recovery);
  await screen.findByRole('button', { name: 'Sign in again with your provider' });
  (authReady as Writable<boolean>).set(true);
  await screen.findByLabelText(/^Password/);
  (authReady as Writable<boolean>).set(false); (authReady as Writable<boolean>).set(true);
  await screen.findByRole('button', { name: 'Sign in again with your provider' });
  expect(screen.queryByLabelText(/^Password/)).toBeNull();
  expect(mocks.post).not.toHaveBeenCalled();
 });

 it('requires provider reauthentication even when the original account session is ready', async () => {
  signedIn(false);
  mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com' });
  const first = render(Recovery);
  await fireEvent.click(await screen.findByRole('button', { name: 'Sign in again with your provider' }));
  expect(screen.queryByLabelText(/^Password/)).toBeNull();
  expect(mocks.post).not.toHaveBeenCalled();
  auth.update(state => ({ ...state, token: 'fresh-provider-token', sessionId: 'fresh-session' }));
  const destination = freshLoginDestination('/dashboard');
  expect(destination).toBe(`/recover/${token}?reauthenticated=1`);
  expect(mocks.goto).toHaveBeenCalledWith('/login?reauthenticate=1');
  first.unmount();
  auth.update(state => ({ ...state, token: 'fresh-provider-token', sessionId: 'fresh-session' }));
  tokenPage.set({ params: { token }, url: new URL(destination, 'http://localhost') });
  render(Recovery);
  expect(await screen.findByLabelText(/^Password/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Sign in again with your provider' })).toBeNull();
  expect(mocks.post).not.toHaveBeenCalled();
 });

 it('preserves only an unconsumed proof after explicit reauthentication-required rejection', async () => {
  signedIn(); mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com' });
  mocks.post.mockRejectedValue(new ApiError(403, 'reauthentication required', 'password_create_reauthentication_required'));
  render(Recovery);
  const password = await screen.findByLabelText(/^Password/) as HTMLInputElement;
  await fireEvent.input(password, { target: { value: 'long-new-password' } });
  await fireEvent.input(screen.getByLabelText(/^Confirm password/), { target: { value: 'long-new-password' } });
  await fireEvent.submit(password.form!);
  const signIn = await screen.findByRole('button', { name: 'Sign in again with your provider' });
  expect(screen.queryByLabelText(/^Password/)).toBeNull();
  expect(mocks.post).toHaveBeenCalledOnce(); expect(mocks.clearAuth).not.toHaveBeenCalled();
  expect(JSON.stringify(sessionStorage)).not.toContain('long-new-password');
  await fireEvent.click(signIn);
  expect(freshLoginDestination('/dashboard')).toBe(`/recover/${token}?reauthenticated=1`);
  expect(mocks.post).toHaveBeenCalledOnce();
 });

 it('creates only after signed-in confirmation, clears secrets pending, and signs out after success', async () => {
  signedIn();
  mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com', identity_domain_id: 'home' });
  const pending = Promise.withResolvers<{ status: string }>(); mocks.post.mockReturnValue(pending.promise);
  render(Recovery);
  const password = await screen.findByLabelText(/^Password/) as HTMLInputElement;
  const confirm = screen.getByLabelText(/^Confirm password/) as HTMLInputElement;
  await fireEvent.input(password, { target: { value: 'too-short' } });
  await fireEvent.input(confirm, { target: { value: 'too-short' } });
  await fireEvent.submit(password.form!); expect(mocks.post).not.toHaveBeenCalled();
  await fireEvent.input(password, { target: { value: 'long-new-password' } });
  await fireEvent.input(confirm, { target: { value: 'long-new-password' } });
  await fireEvent.submit(password.form!); await fireEvent.submit(password.form!);
  expect(password.value).toBe(''); expect(confirm.value).toBe('');
  expect(mocks.post).toHaveBeenCalledOnce();
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/recovery/password/create/complete', { token, new_password: 'long-new-password' }, 'signed-in-token', undefined, requestOptions);
  expect(JSON.stringify(sessionStorage)).not.toContain('long-new-password');
  pending.resolve({ status: 'created' });
  await waitFor(() => expect(mocks.clearAuth).toHaveBeenCalledOnce());
  expect(mocks.success).toHaveBeenCalledWith('Password created. Please sign in again.', 0);
  await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/login', { replaceState: true }));
 });

 it.each([
  [403, 'password_create_actor_mismatch', /current session does not match/],
  [410, 'expired', /expired|no longer valid|invalid/i],
  [409, 'password_already_exists', /A password already exists/],
  [409, 'password_create_identity_changed', /account changed/],
  [422, 'password_create_invalid_password', /Keystone rejected the password/],
  [400, 'rejected', /password could not be created/],
  [503, 'password_create_native_unavailable', /Password management is unavailable/],
 ] as const)('keeps creation failure %s explicit and never resubmits the proof', async (status, code, message) => {
  signedIn(); mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com' });
  mocks.post.mockRejectedValue(new ApiError(status, 'native-private-error', code));
  render(Recovery);
  const password = await screen.findByLabelText(/^Password/) as HTMLInputElement;
  await fireEvent.input(password, { target: { value: 'long-new-password' } });
  await fireEvent.input(screen.getByLabelText(/^Confirm password/), { target: { value: 'long-new-password' } });
  await fireEvent.submit(password.form!);
  expect(await screen.findByText(message)).toBeTruthy();
  await fireEvent.submit(password.form!); expect(mocks.post).toHaveBeenCalledOnce();
  expect(mocks.clearAuth).not.toHaveBeenCalled();
  expect(document.body.textContent).not.toContain('native-private-error');
  expect(password.value).toBe('');
 });

 it('reports a committed password with failed session revocation distinctly and never replays', async () => {
  signedIn(); mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com' });
  mocks.post.mockRejectedValue(new ApiError(503, 'private-error', 'password_create_sessions_failed'));
  render(Recovery);
  const password = await screen.findByLabelText(/^Password/) as HTMLInputElement;
  await fireEvent.input(password, { target: { value: 'long-new-password' } });
  await fireEvent.input(screen.getByLabelText(/^Confirm password/), { target: { value: 'long-new-password' } });
  await fireEvent.submit(password.form!);
  await waitFor(() => expect(mocks.clearAuth).toHaveBeenCalledOnce());
  expect(mocks.error).toHaveBeenCalledWith('The password was created, but other sessions could not be revoked and may still be active. Sign in again and ask your administrator to revoke the remaining sessions. Password creation will not be retried.');
  expect(mocks.success).not.toHaveBeenCalled(); expect(password.value).toBe('');
  await fireEvent.submit(password.form!); expect(mocks.post).toHaveBeenCalledOnce();
  await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/login', { replaceState: true }));
 });

 it('logs out on an unknown creation outcome without replaying or claiming success', async () => {
  signedIn(); mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com' });
  mocks.post.mockRejectedValue(new ApiError(502, 'native-private-error', 'password_create_outcome_unknown'));
  render(Recovery);
  const password = await screen.findByLabelText(/^Password/) as HTMLInputElement;
  await fireEvent.input(password, { target: { value: 'long-new-password' } });
  await fireEvent.input(screen.getByLabelText(/^Confirm password/), { target: { value: 'long-new-password' } });
  await fireEvent.submit(password.form!);
  await waitFor(() => expect(mocks.clearAuth).toHaveBeenCalledOnce());
  expect(mocks.error).toHaveBeenCalledWith(expect.stringContaining('result is unknown'));
  expect(mocks.success).not.toHaveBeenCalled();
  await fireEvent.submit(password.form!); expect(mocks.post).toHaveBeenCalledOnce();
  await waitFor(() => expect(mocks.goto).toHaveBeenCalledWith('/login', { replaceState: true }));
 });

 it('discards creation results across same-tick actor ABA and never clears the replacement session', async () => {
  signedIn(); mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com' });
  const pending = Promise.withResolvers<object>(); mocks.post.mockReturnValue(pending.promise);
  render(Recovery);
  const password = await screen.findByLabelText(/^Password/) as HTMLInputElement;
  await fireEvent.input(password, { target: { value: 'long-new-password' } });
  await fireEvent.input(screen.getByLabelText(/^Confirm password/), { target: { value: 'long-new-password' } });
  await fireEvent.submit(password.form!);
  auth.update(state => ({ ...state, userId: 'other' })); signedIn();
  pending.resolve({ status: 'created' }); await pending.promise;
  expect(mocks.clearAuth).not.toHaveBeenCalled(); expect(mocks.success).not.toHaveBeenCalled();
  expect(password.value).toBe('');
  await fireEvent.submit(password.form!); expect(mocks.post).toHaveBeenCalledOnce();
 });

 it('guides reopening the original mail when tab-local continuation storage is unavailable', async () => {
  mocks.get.mockResolvedValue({ kind: 'password_create', email: 'alice@example.com' });
  render(Recovery);
  const signIn = await screen.findByRole('button', { name: 'Sign in again with your provider' });
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage unavailable'); });
  await fireEvent.click(signIn);
  expect(await screen.findByText(/This tab cannot safely retain/)).toBeTruthy();
  expect(mocks.goto).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
  expect(screen.queryByLabelText(/^Password/)).toBeNull();
 });
});
