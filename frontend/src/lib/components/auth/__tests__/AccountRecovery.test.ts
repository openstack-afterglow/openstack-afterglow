import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$app/stores', () => ({ page: writable({ params: { token: 'recovery_token_12345678901234567890' } }) }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError }));
import { page } from '$app/stores';
import Request from '../AccountEmailRequest.svelte';
import Recovery from '../../../../routes/recover/[token]/+page.svelte';
const tokenPage = page as unknown as Writable<{ params: { token: string } }>;
const token = 'recovery_token_12345678901234567890';
const options = { signup_enabled: true, smtp_configured: true, recovery_enabled: true };
const requestOptions = { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false };
beforeEach(() => {
 vi.resetAllMocks(); initLocale('en');
 tokenPage.set({ params: { token } });
 mocks.get.mockResolvedValue(options); mocks.post.mockResolvedValue({ accepted: true });
});
afterEach(() => { cleanup(); initLocale('ko'); });

describe('public email-first entry', () => {
 it('posts signup email only, without any existing domain or credentials', async () => {
  render(Request, { signup: true });
  await fireEvent.input(await screen.findByLabelText(/^Email/), { target: { value: 'alice@example.com' } });
  await fireEvent.click(screen.getByRole('button', { name: 'Send verification link' }));
  expect(await screen.findByText('If this address can sign up, a verification link has been sent. Check your inbox.')).toBeTruthy();
  expect(mocks.post).toHaveBeenCalledWith('/api/v1/auth/registrations', { email: 'alice@example.com' }, undefined, undefined, requestOptions);
  expect(screen.queryByLabelText(/^Password/)).toBeNull();
 });
 it.each(['username', 'password'])('requests %s recovery with non-enumerating confirmation', async kind => {
  render(Request);
  await fireEvent.click(await screen.findByLabelText(kind === 'username' ? 'Find username' : 'Reset password'));
  await fireEvent.input(screen.getByLabelText(/^Email/), { target: { value: 'alice@example.com' } });
  await fireEvent.click(screen.getByRole('button', { name: 'Send verification link' }));
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(`/api/v1/auth/recovery/${kind}`, { email: 'alice@example.com' }, undefined, undefined, requestOptions));
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
});
