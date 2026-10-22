import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import type { ProviderAccount, ProviderCredential } from '../providerAccounts';

const mocks = vi.hoisted(() => {
  class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
  return { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), remove: vi.fn(), confirm: vi.fn(), ApiError };
});
const session = writable({ token: 'token', projectId: 'project', userId: 'admin', sessionId: 'login-1', identityDomainId: 'domain', domainId: 'domain', isSystemAdmin: true, roles: ['admin'] });
vi.mock('$lib/stores/auth', () => ({ auth: { subscribe: (run: Parameters<typeof session.subscribe>[0]) => session.subscribe(run) } }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post, patch: mocks.patch, put: mocks.put, delete: mocks.remove }, ApiError: mocks.ApiError }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/i18n/ns/admin-chat', () => ({ t: (key: string, values?: Record<string, unknown>) => key + (values ? ' ' + Object.values(values).join(' ') : '') }));
vi.mock('$lib/i18n/runtime.svelte', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, intlLocale: () => 'en-US' };
});
import ProviderAccountsPanel from '../ProviderAccountsPanel.svelte';
import { eligibility, allowedDeviceUri } from '../providerAccounts';

function deferred<T>() { return Promise.withResolvers<T>(); }
const credential: ProviderCredential = { id: 101, account_id: 11, name: 'Key A', auth_mode: 'api_key', generation: 2, is_active: true, priority: 0, weight: 1, api_key_configured: true, api_key_source: 'database', api_key_env: null, subscription_status: 'disconnected', subscription_expires_at: null, allowed_model_ids: null, allowed_capabilities: null, expires_at: null, cooldown_until: null };
const account: ProviderAccount = { id: 11, provider_id: 1, name: 'Team A', is_active: true, priority: 0, weight: 1, allowed_model_ids: null, allowed_capabilities: null, quota_group: null, credentials: [credential] };
let records: ProviderAccount[];
const provider = { id: 1, name: 'Endpoint', auth_mode: 'api_key' as const, selection_policy: 'priority' as const };
const base = '/api/v1/chat/admin/providers/1';
async function openPanel(props: Record<string, unknown> = {}) {
  const component = render(ProviderAccountsPanel, { provider, token: 'token', projectId: 'project', ...props });
  await fireEvent.click(screen.getByRole('button', { name: 'accounts.manage' }));
  await screen.findByRole('region', { name: 'Team A' });
  return component;
}
function accountRegion() { return within(screen.getByRole('region', { name: 'Team A' })); }
afterEach(() => { cleanup(); vi.useRealTimers(); });
beforeEach(() => {
  vi.clearAllMocks();
  records = structuredClone([account]);
  session.set({ token: 'token', projectId: 'project', userId: 'admin', sessionId: 'login-1', identityDomainId: 'domain', domainId: 'domain', isSystemAdmin: true, roles: ['admin'] });
  mocks.get.mockImplementation((path: string) => path.endsWith('/accounts') ? Promise.resolve(structuredClone(records)) : Promise.reject(new Error('unexpected request')));
  mocks.confirm.mockResolvedValue(true);
  mocks.post.mockResolvedValue({}); mocks.patch.mockResolvedValue({}); mocks.put.mockResolvedValue({}); mocks.remove.mockResolvedValue(undefined);
});

describe('endpoint account management', () => {
  it('adds a second account with explicit deny-all operation eligibility and refreshes the visible list', async () => {
    mocks.post.mockImplementation(async (_path, body) => { records.push({ ...body, id: 12, provider_id: 1, is_active: true, credentials: [] }); return records[1]; });
    await openPanel();
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.addAccount' }));
    await fireEvent.input(screen.getByLabelText('accounts.name'), { target: { value: 'Team B' } });
    await fireEvent.input(screen.getByLabelText('accounts.operations'), { target: { value: '-' } });
    await fireEvent.submit(screen.getByRole('form', { name: 'accounts.accountEditor' }));
    await screen.findByRole('region', { name: 'Team B' });
    expect(mocks.post).toHaveBeenCalledWith(`${base}/accounts`, expect.objectContaining({ name: 'Team B', allowed_model_ids: null, allowed_capabilities: [] }), 'token', 'project');
    expect(screen.queryByRole('form')).toBeNull();
  });

  it('rotates only the selected credential and immediately clears submitted plaintext, even on rejection', async () => {
    const pending = deferred<unknown>(); mocks.patch.mockReturnValue(pending.promise);
    await openPanel();
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.editCredential' }));
    await fireEvent.change(screen.getByLabelText('accounts.keySource'), { target: { value: 'stored' } });
    const input = screen.getByLabelText('configuration.apiKey') as HTMLInputElement;
    expect(input.type).toBe('password');
    await fireEvent.input(input, { target: { value: 'private-key-never-render' } });
    await fireEvent.submit(screen.getByRole('form', { name: 'accounts.credentialEditor' }));
    expect(input.value).toBe('');
    expect(mocks.patch).toHaveBeenCalledWith(`${base}/accounts/11/credentials/101`, expect.objectContaining({ api_key: 'private-key-never-render', api_key_env: null }), 'token', 'project');
    pending.reject(new mocks.ApiError('provider echoed private-key-never-render', 409));
    await screen.findByText('accounts.requestFailed 409');
    expect(screen.getByRole('form', { name: 'accounts.credentialEditor' })).toBeTruthy();
    expect(document.body.textContent).not.toContain('private-key-never-render');
    expect((screen.getByLabelText('configuration.apiKey') as HTMLInputElement).value).toBe('');
  });

  it('rejects invalid model identifiers without sending a mutation', async () => {
    await openPanel();
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.editCredential' }));
    await fireEvent.input(screen.getByLabelText('accounts.modelIds'), { target: { value: '1,not-an-id' } });
    await fireEvent.submit(screen.getByRole('form', { name: 'accounts.credentialEditor' }));
    expect(await screen.findByText('accounts.validation')).toBeTruthy();
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it('saves explicit credential selection, expiry, cooldown and eligibility without replacing the key', async () => {
    await openPanel();
    await fireEvent.change(screen.getByLabelText('accounts.selectionPolicy'), { target: { value: 'explicit' } });
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.savePolicy' }));
    expect((await screen.findByRole('alert')).textContent).toContain('accounts.selectCredential');
    expect(mocks.patch).not.toHaveBeenCalled();
    await fireEvent.change(screen.getByLabelText('accounts.selectedCredential'), { target: { value: '101' } });
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.savePolicy' }));
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(base, { selection_policy: 'explicit', selected_credential_id: 101 }, 'token', 'project'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'accounts.savePolicy' }).hasAttribute('disabled')).toBe(false));
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.editCredential' }));
    await fireEvent.input(screen.getByLabelText('accounts.modelIds'), { target: { value: '10, 11' } });
    await fireEvent.input(screen.getByLabelText('accounts.operations'), { target: { value: 'chat,responses' } });
    await fireEvent.input(screen.getByLabelText('configuration.expirationTime'), { target: { value: '2030-01-01T12:00' } });
    await fireEvent.input(screen.getByLabelText('accounts.cooldown'), { target: { value: '2029-01-01T12:00' } });
    await fireEvent.submit(screen.getByRole('form', { name: 'accounts.credentialEditor' }));
    const body = mocks.patch.mock.calls.at(-1)![1];
    expect(body).toMatchObject({ allowed_model_ids: [10, 11], allowed_capabilities: ['chat', 'responses'], expires_at: expect.stringMatching(/^2030-/), cooldown_until: expect.stringMatching(/^2029-/) });
    expect(body).not.toHaveProperty('api_key');
  });

  it('shows account-scoped allocated ledger usage rather than clearing the result after fetch', async () => {
    mocks.get.mockImplementation(async (path: string) => path.endsWith('/usage') ? { provider_id: 1, account_id: 11, credentials: [{ credential_id: 101, requests: 3, prompt_tokens: 200, completion_tokens: 25, raw_cost: '0.125' }] } : structuredClone(records));
    await openPanel();
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.usage' }));
    expect(await screen.findByText('accounts.usageRow 101 3 200 25 0.125')).toBeTruthy();
    expect(mocks.get).toHaveBeenCalledWith(`${base}/accounts/11/usage`, 'token', 'project');
  });

  it('does not delete after an ABA identity transition during confirmation', async () => {
    const confirmation = deferred<boolean>(); mocks.confirm.mockReturnValue(confirmation.promise);
    await openPanel();
    await fireEvent.click(accountRegion().getAllByRole('button', { name: 'configuration.delete' })[1]);
    session.update((value) => ({ ...value, userId: 'another-admin' }));
    session.update((value) => ({ ...value, userId: 'admin' }));
    confirmation.resolve(true);
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Team A' })).toBeNull());
    expect(mocks.remove).not.toHaveBeenCalled();
  });

  it('keeps the manager and unsaved editor open when a refreshed provider object has the same identity', async () => {
    const component = await openPanel();
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.editCredential' }));
    await fireEvent.change(screen.getByLabelText('accounts.keySource'), { target: { value: 'stored' } });
    await fireEvent.input(screen.getByLabelText('configuration.apiKey'), { target: { value: 'unsaved-private-key' } });
    await component.rerender({ provider: { ...provider, name: 'Refreshed endpoint', selection_policy: 'weighted' }, token: 'token', projectId: 'project' });
    expect(screen.getByText('Refreshed endpoint')).toBeTruthy();
    expect(screen.getByRole('form', { name: 'accounts.credentialEditor' })).toBeTruthy();
    expect((screen.getByLabelText('configuration.apiKey') as HTMLInputElement).value).toBe('unsaved-private-key');
    expect(screen.getByRole('region', { name: 'Team A' })).toBeTruthy();
    expect(mocks.get).toHaveBeenCalledTimes(1);
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it('ignores a late private list after closing and reopening under another provider', async () => {
    const pending = deferred<ProviderAccount[]>(); mocks.get.mockReturnValueOnce(pending.promise);
    const component = render(ProviderAccountsPanel, { provider, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.manage' }));
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.close' }));
    await component.rerender({ provider: { ...provider, id: 2, name: 'Other endpoint' }, token: 'token', projectId: 'project' });
    records = [];
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.manage' }));
    pending.resolve([account]);
    await screen.findByText('accounts.empty');
    expect(screen.queryByText('Key A (#101)')).toBeNull();
    expect(screen.getByText('Other endpoint')).toBeTruthy();
  });

  it('retains credential rows after delete fails and never reports the deletion as successful', async () => {
    mocks.remove.mockRejectedValue(new mocks.ApiError('not allowed', 403));
    await openPanel();
    await fireEvent.click(accountRegion().getAllByRole('button', { name: 'configuration.delete' })[1]);
    expect(await screen.findByText('accounts.requestFailed 403')).toBeTruthy();
    expect(screen.getByText('Key A (#101)')).toBeTruthy();
    expect(mocks.remove).toHaveBeenCalledWith(`${base}/accounts/11/credentials/101`, 'token', 'project');
  });
});

describe('eligibility and device URI boundaries', () => {
  it('preserves unrestricted versus explicit deny-all and rejects malformed numeric IDs', () => {
    expect(eligibility('', true)).toBeNull(); expect(eligibility('-', true)).toEqual([]);
    expect(eligibility('12,12,13', true)).toEqual([12,13]); expect(() => eligibility('12,,13', true)).toThrow();
    expect(() => eligibility('9007199254740992', true)).toThrow();
  });
  it('accepts only credential-free HTTPS provider-owned device verification URLs', () => {
    expect(allowedDeviceUri('https://auth.openai.com/device')).toBe('https://auth.openai.com/device');
    for (const value of ['javascript:alert(1)', 'https://openai.com.evil.test/device', 'https://secret@openai.com/device', 'http://chatgpt.com/device', 'https://chatgpt.com:444/device']) expect(allowedDeviceUri(value)).toBeNull();
  });
});
