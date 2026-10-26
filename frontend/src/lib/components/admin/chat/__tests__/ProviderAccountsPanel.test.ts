import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import type { ProviderAccount, ProviderCredential, RelayPage } from '../providerAccounts';

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

describe('explicit key connection probes', () => {
  const models = [{ id: 10, provider_id: 1, model_name: 'Text probe', model_kind: 'text', is_active: true },
    { id: 11, provider_id: 1, model_name: 'Image only', model_kind: 'image', is_active: true },
    { id: 12, provider_id: 2, model_name: 'Other provider', model_kind: 'text', is_active: true }];
  const result = { status: 'connected', reason: null, mode: 'structured', elapsed_ms: 12, model_id: 10, generation: 2, checked_at: '2026-10-25T12:00:00Z' };
  function probeReads() {
    mocks.get.mockImplementation((path: string) => Promise.resolve(structuredClone(path.endsWith('/accounts') ? records : models)));
  }
  async function chooseKey(id = 101) {
    const row = document.querySelector(`[data-credential-id="${id}"]`) as HTMLElement;
    await fireEvent.click(within(row).getByRole('button', { name: 'accounts.probeTitle' }));
    await screen.findByRole('option', { name: 'Text probe (#10)' });
    await fireEvent.change(screen.getByLabelText('accounts.probeModel'), { target: { value: '10' } });
  }

  it('adds a second distinct key without replacing the first key', async () => {
    mocks.post.mockImplementation(async (_path, body) => {
      records[0].credentials.push({ ...credential, ...body, id: 102, name: 'Key B' });
      return records[0].credentials[1];
    });
    await openPanel();
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.addCredential' }));
    await fireEvent.input(screen.getByLabelText('accounts.name'), { target: { value: 'Key B' } });
    await fireEvent.input(screen.getByLabelText('configuration.apiKey'), { target: { value: 'private-key-B' } });
    await fireEvent.submit(screen.getByRole('form', { name: 'accounts.credentialEditor' }));
    await screen.findByText('Key B (#102)');
    expect(screen.getByText('Key A (#101)')).toBeTruthy();
    expect(mocks.post).toHaveBeenCalledWith(`${base}/accounts/11/credentials`, expect.objectContaining({ name: 'Key B', api_key: 'private-key-B' }), 'token', 'project');
    expect(mocks.patch).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain('private-key-B');
  });

  it('tests each exact key only on explicit action, with cost notice and selected registered text model', async () => {
    records[0].credentials.push({ ...credential, id: 102, name: 'Key B' });
    probeReads(); mocks.post.mockResolvedValue(result);
    await openPanel();
    await chooseKey();
    expect(screen.getByText('accounts.probeCost')).toBeTruthy();
    expect(screen.queryByRole('option', { name: 'Image only (#11)' })).toBeNull();
    expect(screen.queryByRole('option', { name: 'Other provider (#12)' })).toBeNull();
    expect(mocks.post).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.probeRun' }));
    expect(await within(screen.getByRole('region', { name: 'accounts.probeTitle' })).findByText('accounts.probeConnected')).toBeTruthy();
    expect(mocks.post).toHaveBeenLastCalledWith(`${base}/accounts/11/credentials/101/probe`, { model_id: 10, generation: 2 }, 'token', 'project');
    await chooseKey(102);
    expect(within(screen.getByRole('region', { name: 'accounts.probeTitle' })).queryByText('accounts.probeConnected')).toBeNull();
    expect(document.querySelector('[data-credential-id="101"] [data-probe-status="connected"]')).toBeTruthy();
    mocks.post.mockResolvedValue({ ...result, status: 'failed', reason: 'provider_error', mode: 'plain' });
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.probeRun' }));
    await within(screen.getByRole('region', { name: 'accounts.probeTitle' })).findByText('accounts.probeFailed');
    expect(document.querySelector('[data-credential-id="101"] [data-probe-status="connected"]')).toBeTruthy();
    expect(document.querySelector('[data-credential-id="102"] [data-probe-status="failed"]')).toBeTruthy();
    expect(mocks.post).toHaveBeenLastCalledWith(`${base}/accounts/11/credentials/102/probe`, { model_id: 10, generation: 2 }, 'token', 'project');
    expect(mocks.post).toHaveBeenCalledTimes(2);
  });

  it('clears a completed result as soon as credential editing or refreshed inventory invalidates it', async () => {
    probeReads(); mocks.post.mockResolvedValue(result);
    await openPanel(); await chooseKey();
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.probeRun' }));
    await within(screen.getByRole('region', { name: 'accounts.probeTitle' })).findByText('accounts.probeConnected');
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.editCredential' }));
    expect(screen.queryByText('accounts.probeConnected')).toBeNull();
    expect(screen.queryByRole('region', { name: 'accounts.probeTitle' })).toBeNull();
  });

  it('masks a late probe result after an ABA identity transition', async () => {
    probeReads(); const pending = deferred<unknown>(); mocks.post.mockReturnValue(pending.promise);
    await openPanel(); await chooseKey();
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.probeRun' }));
    session.update((value) => ({ ...value, userId: 'other' }));
    session.update((value) => ({ ...value, userId: 'admin' }));
    pending.resolve(result);
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Team A' })).toBeNull());
    expect(screen.queryByText('accounts.probeConnected')).toBeNull();
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });

  it('ignores a stale generation result and sanitizes explicit request failures without another request', async () => {
    probeReads(); mocks.post.mockResolvedValue({ ...result, generation: 1 });
    await openPanel(); await chooseKey();
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.probeRun' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'accounts.probeRun' }).hasAttribute('disabled')).toBe(false));
    expect(screen.queryByText('accounts.probeConnected')).toBeNull();
    mocks.post.mockRejectedValue(new mocks.ApiError('upstream echoed private-secret', 502));
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.probeRun' }));
    await screen.findByText('accounts.requestFailed 502');
    expect(document.body.textContent).not.toContain('private-secret');
    expect(mocks.post).toHaveBeenCalledTimes(2);
  });

  it('invalidates observed row outcomes when refreshed model configuration or account inventory changes', async () => {
    probeReads(); mocks.post.mockResolvedValue(result);
    await openPanel(); await chooseKey();
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.probeRun' }));
    await waitFor(() => expect(document.querySelector('[data-credential-id="101"] [data-probe-status="connected"]')).toBeTruthy());
    mocks.get.mockImplementation((path: string) => Promise.resolve(structuredClone(path.endsWith('/accounts') ? records : models.map((model) => ({ ...model, updated_at: '2030-01-01' })))));
    await chooseKey();
    expect(document.querySelector('[data-credential-id="101"] [data-probe-status]')).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.probeRun' }));
    await waitFor(() => expect(document.querySelector('[data-credential-id="101"] [data-probe-status="connected"]')).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.refreshAll' }));
    await waitFor(() => expect(document.querySelector('[data-credential-id="101"] [data-probe-status]')).toBeNull());
  });
});

describe('settled per-key relay history', () => {
  const relay = (id = 101, ledger = 7): RelayPage => ({ provider_id: 1, account_id: 11, credential_id: id, boundary: 'settled_usage',
    items: [{ ledger_id: ledger, generation: 1, settled_at: '2026-10-25T12:00:00Z', settled_model: 'Historical model', status: 'settled',
      dispatches: [{ attempt_id: '00000000-0000-4000-8000-000000000001', endpoint: `https://secret@old-key-${id}.example/v1/chat?token=private-query#fragment`, model: 'Actual model', operation: 'chat', status: 'response_received', status_code: 200, recorded_at: '2026-10-25T11:59:59Z' }] }], next_before_id: null });
  function row(id = 101) { return within(document.querySelector(`[data-credential-id="${id}"]`) as HTMLElement); }

  it('shows distinct exact-key receipts separate from current configuration and pages only that key', async () => {
    records[0].credentials.push({ ...credential, id: 102, name: 'Key B' });
    mocks.get.mockImplementation(async (path: string) => path.endsWith('/accounts') ? structuredClone(records) : path.includes('before_id=7') ? { ...relay(101, 6), items: [{ ...relay().items[0], ledger_id: 6, dispatches: null }] } : { ...relay(path.includes('/102/') ? 102 : 101), next_before_id: path.includes('/101/') ? 7 : null });
    await openPanel({ provider: { ...provider, api_base: 'https://current-user:current-secret@current.example/v1?key=current-query' } });
    expect(mocks.get).toHaveBeenCalledTimes(1);
    expect(row().getByText('accounts.currentEndpoint: https://current.example/v1')).toBeTruthy();
    await fireEvent.click(row().getByRole('button', { name: 'accounts.loadRelays' }));
    expect(await row().findByText('accounts.recordedDestination: https://old-key-101.example/v1/chat')).toBeTruthy();
    expect(row().getByText('accounts.relayBoundary')).toBeTruthy();
    expect(row(102).queryByText(/old-key-101/)).toBeNull();
    await fireEvent.click(row().getByRole('button', { name: 'accounts.olderRelays' }));
    expect(await row().findByText('accounts.unknownDispatch')).toBeTruthy();
    expect(mocks.get).toHaveBeenCalledWith(`${base}/accounts/11/credentials/101/relays?limit=10&before_id=7`, 'token', 'project');
    await fireEvent.click(row(102).getByRole('button', { name: 'accounts.loadRelays' }));
    expect(await row(102).findByText('accounts.recordedDestination: https://old-key-102.example/v1/chat')).toBeTruthy();
    for (const secret of ['private-query', 'current-secret', 'current-query', 'fragment']) expect(document.body.textContent).not.toContain(secret);
  });

  it('renders unsupported pool failure honestly, disables writes and retries instead of announcing empty', async () => {
    mocks.get.mockRejectedValueOnce(new mocks.ApiError('private upstream body', 404));
    render(ProviderAccountsPanel, { provider, token: 'token', projectId: 'project' });
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.manage' }));
    expect(await screen.findByText('accounts.poolUnavailable')).toBeTruthy();
    expect(screen.queryByText('accounts.empty')).toBeNull();
    expect(screen.getByRole('button', { name: 'accounts.addAccount' }).hasAttribute('disabled')).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.refreshAll' }));
    expect(await screen.findByRole('region', { name: 'Team A' })).toBeTruthy();
    expect(screen.queryByText('accounts.poolUnavailable')).toBeNull();
  });

  it('does not turn history read failures into zero and permits explicit retry', async () => {
    mocks.get.mockImplementation(async (path: string) => path.endsWith('/accounts') ? structuredClone(records) : Promise.reject(new mocks.ApiError('echoed-secret', 503)));
    await openPanel();
    await fireEvent.click(row().getByRole('button', { name: 'accounts.loadRelays' }));
    expect(await row().findByText('accounts.requestFailed 503')).toBeTruthy();
    expect(row().queryByText('accounts.noSettledRelays')).toBeNull();
    expect(document.body.textContent).not.toContain('echoed-secret');
    mocks.get.mockResolvedValueOnce({ ...relay(), items: [] });
    await fireEvent.click(row().getByRole('button', { name: 'accounts.loadRelays' }));
    expect(await row().findByText('accounts.noSettledRelays')).toBeTruthy();
  });

  it('rejects foreign-key history DTO without rendering it', async () => {
    mocks.get.mockImplementation(async (path: string) => path.endsWith('/accounts') ? structuredClone(records) : relay(102));
    await openPanel();
    await fireEvent.click(row().getByRole('button', { name: 'accounts.loadRelays' }));
    expect(await row().findByText('accounts.networkError')).toBeTruthy();
    expect(document.body.textContent).not.toContain('old-key-102');
  });

  it.each(['close', 'ABA', 'refresh-generation', 'destroy'])('discards private late history after %s', async (change) => {
    const pending = deferred<RelayPage>();
    mocks.get.mockImplementation((path: string) => path.endsWith('/accounts') ? Promise.resolve(structuredClone(records)) : pending.promise);
    const component = await openPanel();
    await fireEvent.click(row().getByRole('button', { name: 'accounts.loadRelays' }));
    if (change === 'close') { await fireEvent.click(screen.getByRole('button', { name: 'configuration.close' })); }
    if (change === 'ABA') { session.update((value) => ({ ...value, projectId: 'other' })); session.update((value) => ({ ...value, projectId: 'project' })); }
    if (change === 'refresh-generation') { records[0].credentials[0].generation = 3; await fireEvent.click(screen.getByRole('button', { name: 'configuration.refreshAll' })); await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(3)); }
    if (change === 'destroy') component.unmount();
    pending.resolve(relay());
    await Promise.resolve();
    expect(document.body.textContent).not.toContain('old-key-101');
  });
});
