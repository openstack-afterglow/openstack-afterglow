import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => {
  class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
  return { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), remove: vi.fn(), confirm: vi.fn(), ApiError };
});
const session = writable({ token: 'token', projectId: 'project', userId: 'admin', sessionId: 'login-1', identityDomainId: 'domain', domainId: 'domain', isSystemAdmin: true, roles: ['admin'] });
vi.mock('$lib/stores/auth', () => ({ auth: { subscribe: (run: Parameters<typeof session.subscribe>[0]) => session.subscribe(run) } }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post, patch: mocks.patch, put: mocks.put, delete: mocks.remove }, ApiError: mocks.ApiError }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('$lib/i18n/ns/admin-chat', () => ({
  t: Object.assign((key: string, values?: Record<string, unknown>) => key + (values ? ' ' + Object.values(values).join(' ') : ''), { rich: (key: string) => [key] })
}));
vi.mock('$lib/i18n/runtime.svelte', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, intlLocale: () => 'en-US' };
});

import LegacyProviderAuth from '../LegacyProviderAuth.svelte';
import { supportsProviderAccounts } from '../providerAccounts';

const base = '/api/v1/chat/admin/providers/7';
const apiKeyProvider = { id: 7, name: 'Legacy', auth_mode: 'api_key' as const, has_api_key: true };
const chatgptProvider = { id: 7, name: 'Legacy', auth_mode: 'chatgpt_device' as const, has_credentials: false, auth_status: 'disconnected' };

function deferred<T>() { return Promise.withResolvers<T>(); }

afterEach(() => cleanup());
beforeEach(() => {
  vi.clearAllMocks();
  session.set({ token: 'token', projectId: 'project', userId: 'admin', sessionId: 'login-1', identityDomainId: 'domain', domainId: 'domain', isSystemAdmin: true, roles: ['admin'] });
  mocks.get.mockRejectedValue(new Error('unexpected request'));
  mocks.post.mockResolvedValue({}); mocks.patch.mockResolvedValue({}); mocks.put.mockResolvedValue({});
  mocks.remove.mockResolvedValue(undefined); mocks.confirm.mockResolvedValue(true);
});

describe('native provider contract detection', () => {
  it.each([
    ['an old native provider with no selection policy', {}, false],
    ['an old provider carrying an unknown policy value', { selection_policy: 'round-robin' }, false],
    ['a provider whose policy is null', { selection_policy: null }, false],
    ['priority', { selection_policy: 'priority' }, true],
    ['weighted', { selection_policy: 'weighted' }, true],
    ['explicit', { selection_policy: 'explicit' }, true]
  ])('%s', (_name, provider, expected) => {
    expect(supportsProviderAccounts(provider)).toBe(expected);
  });
});

describe('legacy provider API-key rotation', () => {
  it('patches the provider itself and never calls an account or credential route', async () => {
    const onupdated = vi.fn().mockResolvedValue(undefined);
    render(LegacyProviderAuth, { provider: apiKeyProvider, token: 'token', projectId: 'project', onupdated });
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.changeKey' }));
    await fireEvent.input(screen.getByLabelText('configuration.apiKey'), { target: { value: 'replacement-key' } });
    await fireEvent.submit(screen.getByRole('form', { name: 'configuration.changeKey' }));
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(base, { api_key: 'replacement-key' }, 'token', 'project'));
    await waitFor(() => expect(onupdated).toHaveBeenCalledTimes(1));
    const touched = [...mocks.get.mock.calls, ...mocks.post.mock.calls, ...mocks.patch.mock.calls, ...mocks.put.mock.calls, ...mocks.remove.mock.calls].map((call) => String(call[0]));
    expect(touched.some((path) => path.includes('/accounts') || path.includes('/credentials'))).toBe(false);
  });

  it('clears the submitted key immediately and never renders it when the server rejects', async () => {
    const pending = deferred<unknown>(); mocks.patch.mockReturnValue(pending.promise);
    render(LegacyProviderAuth, { provider: apiKeyProvider, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.changeKey' }));
    const input = screen.getByLabelText('configuration.apiKey') as HTMLInputElement;
    expect(input.type).toBe('password');
    await fireEvent.input(input, { target: { value: 'private-key-never-render' } });
    await fireEvent.submit(screen.getByRole('form', { name: 'configuration.changeKey' }));
    expect(input.value).toBe('');
    pending.reject(new mocks.ApiError('upstream echoed private-key-never-render', 503));
    await screen.findByText('configuration.couldNotConnectToTheSubscriptionAuthenticationProviderOr');
    expect(document.body.textContent).not.toContain('private-key-never-render');
    expect((screen.getByLabelText('configuration.apiKey') as HTMLInputElement).value).toBe('');
  });

  it('does not submit a second rotation while the first is still in flight', async () => {
    const pending = deferred<unknown>(); mocks.patch.mockReturnValue(pending.promise);
    render(LegacyProviderAuth, { provider: apiKeyProvider, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.changeKey' }));
    await fireEvent.input(screen.getByLabelText('configuration.apiKey'), { target: { value: 'first' } });
    const form = screen.getByRole('form', { name: 'configuration.changeKey' });
    await fireEvent.submit(form);
    await fireEvent.submit(form);
    expect(mocks.patch).toHaveBeenCalledTimes(1);
    pending.resolve({});
  });
});

describe('legacy subscription authentication', () => {
  it('starts, polls and cancels a device attempt through the provider-level route only', async () => {
    const expires = new Date(Date.now() + 600_000).toISOString();
    mocks.post.mockImplementation(async (path: string) => path.endsWith('/poll')
      ? { attempt_id: 'a1', status: 'pending', expires_at: expires, interval_seconds: 5 }
      : { attempt_id: 'a1', status: 'pending', expires_at: expires, interval_seconds: 5, user_code: 'ABCD-1234', verification_uri: 'https://auth.openai.com/codex/device' });
    render(LegacyProviderAuth, { provider: chatgptProvider, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.connect' }));
    await fireEvent.click(await screen.findByRole('button', { name: 'configuration.connectChatgpt' }));
    expect(await screen.findByText('ABCD-1234')).toBeTruthy();
    expect(mocks.post).toHaveBeenCalledWith(`${base}/auth/device`, {}, 'token', 'project');
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.checkNow' }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith(`${base}/auth/device/a1/poll`, {}, 'token', 'project'));
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.cancelAuthentication' }));
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(`${base}/auth/device/a1`, 'token', 'project'));
    expect(screen.queryByText('ABCD-1234')).toBeNull();
    const touched = [...mocks.post.mock.calls, ...mocks.remove.mock.calls].map((call) => String(call[0]));
    expect(touched.some((path) => path.includes('/accounts') || path.includes('/credentials'))).toBe(false);
  });

  it('abandons an in-flight start when the signed-in identity changes and never reveals its code', async () => {
    const pending = deferred<unknown>(); mocks.post.mockReturnValue(pending.promise);
    render(LegacyProviderAuth, { provider: chatgptProvider, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.connect' }));
    await fireEvent.click(await screen.findByRole('button', { name: 'configuration.connectChatgpt' }));
    session.set({ token: 'other', projectId: 'project', userId: 'someone-else', sessionId: 'login-2', identityDomainId: 'domain', domainId: 'domain', isSystemAdmin: true, roles: ['admin'] });
    pending.resolve({ attempt_id: 'late', status: 'pending', expires_at: new Date(Date.now() + 600_000).toISOString(), interval_seconds: 5, user_code: 'LATE-CODE', verification_uri: 'https://auth.openai.com/codex/device' });
    await Promise.resolve(); await Promise.resolve();
    expect(screen.queryByText('LATE-CODE')).toBeNull();
  });

  it('disconnects a connected subscription only after confirmation and stays put if declined', async () => {
    const connected = { ...chatgptProvider, has_credentials: true, auth_status: 'configured' };
    mocks.confirm.mockResolvedValueOnce(false);
    render(LegacyProviderAuth, { provider: connected, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.disconnect' }));
    expect(mocks.remove).not.toHaveBeenCalled();
    mocks.confirm.mockResolvedValueOnce(true);
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.disconnect' }));
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(`${base}/auth`, 'token', 'project'));
  });

  it('warns that a subscription connection is shared by every user, but not for a plain API key', async () => {
    const { unmount } = render(LegacyProviderAuth, { provider: chatgptProvider, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.connect' }));
    expect(await screen.findByText('configuration.experimental · configuration.sharedByAllUsers')).toBeTruthy();
    expect(screen.getByText('configuration.thisConnectionIsSharedByAllAfterglowUsersUse')).toBeTruthy();
    unmount();
    render(LegacyProviderAuth, { provider: apiKeyProvider, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.changeKey' }));
    await screen.findByLabelText('configuration.apiKey');
    expect(screen.queryByText('configuration.thisConnectionIsSharedByAllAfterglowUsersUse')).toBeNull();
  });
});
