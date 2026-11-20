import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import messages from '$lib/i18n/messages/en/admin-chat.json';
import type { AccountUsage, ProviderAccount, ProviderCredential, RelayPage } from '../providerAccounts';

const mocks = vi.hoisted(() => {
  class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
  return { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), remove: vi.fn(), confirm: vi.fn(), ApiError };
});
const session = writable({ token: 'token', projectId: 'project', userId: 'admin', sessionId: 'login-1', identityDomainId: 'domain', domainId: 'domain', isSystemAdmin: true, roles: ['admin'] });
vi.mock('$lib/stores/auth', () => ({ auth: { subscribe: (run: Parameters<typeof session.subscribe>[0]) => session.subscribe(run) } }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get, post: mocks.post, patch: mocks.patch, put: mocks.put, delete: mocks.remove }, ApiError: mocks.ApiError }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/i18n/ns/admin-chat', () => {
  const copy = new Set([
    'identityHelp', 'accountIdentity', 'credentialIdentity', 'credentialPathIdentity', 'connectionIdentity',
    'confirmAccountDelete', 'confirmCredentialDelete', 'confirmDisconnect', 'registered', 'unknownValue',
    'thisMonth', 'monthPeriod', 'allTimeUsage', 'deletedCredentialUsage', 'usageFigures', 'lastUsed',
    'accountMonthTotal', 'providerMonthTotal', 'usdAmount', 'usageLoading', 'usageFailed',
    'selectionOrder', 'priorityHelp', 'weightHelp', 'quotaGroupHelp', 'modelIdsHelp', 'operationsHelp', 'expiryHelp',
    'cooldownHelp', 'generation', 'generationHelp', 'currentEndpointHelp', 'keyConfiguredHelp', 'environmentNameHelp',
    'subscriptionStatusHelp', 'subscriptionExpiryLabel', 'subscriptionExpiryHelp',
  ].map((key) => `accounts.${key}`));
  return { t: (key: string, values?: Record<string, unknown>) => {
    if (copy.has(key)) {
      return messages[key as keyof typeof messages].replace(/\{(\w+)\}/g, (_, field) => String(values?.[field]));
    }
    return key + (values ? ' ' + Object.values(values).join(' ') : '');
  } };
});
vi.mock('$lib/i18n/runtime.svelte', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, intlLocale: () => 'en-US' };
});
import ProviderAccountsPanel from '../ProviderAccountsPanel.svelte';
import { eligibility, allowedDeviceUri, sumLedgerCosts } from '../providerAccounts';

function deferred<T>() { return Promise.withResolvers<T>(); }
const credential: ProviderCredential = { id: 101, account_id: 11, name: 'Key A', auth_mode: 'api_key', generation: 2, is_active: true, priority: 0, weight: 1, api_key_configured: true, api_key_source: 'database', api_key_env: null, subscription_status: 'disconnected', subscription_expires_at: null, allowed_model_ids: null, allowed_capabilities: null, expires_at: null, cooldown_until: null };
const account: ProviderAccount = { id: 11, provider_id: 1, name: 'Team A', is_active: true, priority: 0, weight: 1, allowed_model_ids: null, allowed_capabilities: null, quota_group: null, credentials: [credential] };
let records: ProviderAccount[];
const provider = { id: 1, name: 'Endpoint', auth_mode: 'api_key' as const, selection_policy: 'priority' as const };
const base = '/api/v1/chat/admin/providers/1';
const accountName = 'Account Team A (ID 11)';
const keyName = 'API key Key A (ID 101)';
const keyPathName = `${accountName} / ${keyName}`;
const period = { kind: 'calendar_month', start: '2026-11-01T00:00:00+00:00', end: '2026-12-01T00:00:00+00:00', timezone: 'UTC' } as const;
const monthText = 'This month (Nov 1, 2026 – Nov 30, 2026, UTC)';
const allTimeRow = { credential_id: 101, requests: 3, prompt_tokens: 200, completion_tokens: 25, raw_cost: '0.125' };
const monthRow = { ...allTimeRow, month_requests: 2, month_prompt_tokens: 120, month_completion_tokens: 15, month_raw_cost: '0.1', last_used_at: '2026-11-06T12:00:00Z' };
const keyUsage = (credentials: AccountUsage['credentials'], account_id = 11): AccountUsage => ({ provider_id: 1, account_id, period, credentials });
const legacyUsage = { provider_id: 1, account_id: 11, credentials: [] } satisfies AccountUsage;
function poolRead(path: string) {
  if (path.endsWith('/accounts')) return structuredClone(records);
  const id = path.match(/\/accounts\/(\d+)\/usage$/)?.[1];
  return id ? { ...legacyUsage, account_id: Number(id) } : null;
}
function credentialRegion(id = 101) { return within(document.querySelector(`[data-credential-id="${id}"]`) as HTMLElement); }
async function openPanel(props: Record<string, unknown> = {}) {
  const component = render(ProviderAccountsPanel, { provider, token: 'token', projectId: 'project', ...props });
  await fireEvent.click(screen.getByRole('button', { name: 'accounts.manage' }));
  await screen.findByRole('region', { name: accountName });
  return component;
}
function accountRegion() { return within(screen.getByRole('region', { name: accountName })); }
type TextQueries = Pick<typeof screen, 'getByText'>;
function description(scope: TextQueries, term: string) {
  const label = scope.getByText(term, { selector: 'dt' });
  const detail = label.nextElementSibling;
  expect(label.closest('dl')).not.toBeNull();
  expect(detail?.tagName).toBe('DD');
  return detail;
}
afterEach(() => { cleanup(); vi.useRealTimers(); });
beforeEach(() => {
  vi.clearAllMocks();
  records = structuredClone([account]);
  session.set({ token: 'token', projectId: 'project', userId: 'admin', sessionId: 'login-1', identityDomainId: 'domain', domainId: 'domain', isSystemAdmin: true, roles: ['admin'] });
  mocks.get.mockImplementation(async (path: string) => {
    const result = poolRead(path);
    if (result) return result;
    throw new Error('unexpected request');
  });
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
    await screen.findByRole('region', { name: 'Account Team B (ID 12)' });
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

  it.each(['priority', 'weighted', 'explicit'] as const)('sorts both lists by priority then ID under %s', async (selection_policy) => {
    records[0].credentials = [
      { ...credential, id: 100, name: 'Later priority', priority: 2 },
      { ...credential, id: 102, name: 'Tied priority' },
      credential,
    ];
    records.unshift(
      { ...account, id: 10, name: 'Later account', priority: 4, credentials: [] },
      { ...account, id: 12, name: 'Tied account', credentials: [] },
    );
    await openPanel({ provider: { ...provider, selection_policy } });
    const sections = screen.getAllByRole('region', { name: /^Account .* \(ID \d+\)$/ });
    expect(sections.map((section) => section.getAttribute('aria-label'))).toEqual([
      accountName, 'Account Tied account (ID 12)', 'Account Later account (ID 10)',
    ]);
    const keys = [...sections[0].querySelectorAll('[data-credential-id]')];
    expect(keys.map((key) => key.getAttribute('data-credential-id'))).toEqual(['101', '102', '100']);
    if (selection_policy === 'priority') {
      sections.forEach((section, index) => expect(section.querySelector('h4')?.parentElement?.textContent).toContain(`Selection order ${index + 1}`));
      keys.forEach((key, index) => expect(within(key as HTMLElement).getByText(`Selection order ${index + 1}`)).toBeTruthy());
    } else {
      expect(screen.queryByText(/^Selection order \d+$/)).toBeNull();
    }
  });

  it('changes selection badges only after saving the policy successfully', async () => {
    await openPanel();
    await fireEvent.change(screen.getByLabelText('accounts.selectionPolicy'), { target: { value: 'weighted' } });
    expect(screen.getAllByText('Selection order 1')).toHaveLength(2);
    mocks.patch.mockRejectedValueOnce(new mocks.ApiError('conflict', 409));
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.savePolicy' }));
    await screen.findByText('accounts.requestFailed 409');
    expect(screen.getAllByText('Selection order 1')).toHaveLength(2);
    await fireEvent.click(screen.getByRole('button', { name: 'accounts.savePolicy' }));
    await waitFor(() => expect(screen.queryByText('Selection order 1')).toBeNull());
  });

  it('pairs account and key settings with their values and visible help', async () => {
    const expiry = '2030-01-01T12:00:00Z';
    const cooldown = '2029-01-01T12:00:00Z';
    Object.assign(records[0], { quota_group: 'team-pool', allowed_model_ids: [] });
    Object.assign(records[0].credentials[0], { api_key_env: 'TUTORIAL_API_KEY', allowed_model_ids: [43], allowed_capabilities: ['chat'], expires_at: expiry, cooldown_until: cooldown });
    await openPanel();
    const accountSettings = within(accountRegion().getByRole('heading', { name: 'accounts.accountEditor' }).nextElementSibling as HTMLElement);
    const key = credentialRegion();
    const commonSettings = [
      ['accounts.priority', '0', 'accounts.priorityHelp'],
      ['accounts.weight', '1', 'accounts.weightHelp'],
    ] as const;
    function expectSetting(scope: TextQueries, label: string, value: string, help: keyof typeof messages) {
      const detail = within(description(scope, label) as HTMLElement);
      expect(detail.getByText(value)).toBeTruthy();
      expect(detail.getByText(messages[help])).toBeTruthy();
    }
    for (const [label, value, help] of commonSettings) {
      expectSetting(accountSettings, label, value, help);
      expectSetting(key, label, value, help);
    }
    expectSetting(accountSettings, 'accounts.quotaGroup', 'team-pool', 'accounts.quotaGroupHelp');
    expectSetting(accountSettings, 'accounts.modelIds', '-', 'accounts.modelIdsHelp');
    expectSetting(accountSettings, 'accounts.operations', 'accounts.unrestricted', 'accounts.operationsHelp');
    expectSetting(key, 'accounts.modelIds', '43', 'accounts.modelIdsHelp');
    expectSetting(key, 'accounts.operations', 'chat', 'accounts.operationsHelp');
    expectSetting(key, 'configuration.expirationTime', new Date(expiry).toLocaleString('en-US'), 'accounts.expiryHelp');
    expectSetting(key, 'accounts.cooldown', new Date(cooldown).toLocaleString('en-US'), 'accounts.cooldownHelp');
    expectSetting(key, 'Generation', '2', 'accounts.generationHelp');
    expectSetting(key, 'accounts.currentEndpoint', 'accounts.providerDefaultEndpoint', 'accounts.currentEndpointHelp');
    expectSetting(key, 'configuration.apiKey', 'configuration.keyConfigured', 'accounts.keyConfiguredHelp');
    expectSetting(key, 'accounts.environmentName', 'TUTORIAL_API_KEY', 'accounts.environmentNameHelp');
  });

  it('distinguishes account and key IDs everywhere and shows both registration times when available', async () => {
    const accountCreated = '2025-01-02T03:04:05+00:00';
    const keyCreated = '2026-10-04T12:30:00+00:00';
    records[0].created_at = accountCreated;
    records[0].credentials[0].created_at = keyCreated;
    records[0].credentials.push({ ...credential, id: 102, name: 'Key B' });
    await openPanel({ provider: { ...provider, selection_policy: 'explicit' } });
    expect(accountRegion().getByRole('heading', { name: accountName })).toBeTruthy();
    expect(credentialRegion().getByText(keyName)).toBeTruthy();
    expect(credentialRegion().getByText('Provider #1 · Account #11 · API key #101')).toBeTruthy();
    expect(screen.getByRole('option', { name: keyPathName })).toBeTruthy();
    expect(screen.getByText(/Lumen uses these internal IDs in logs and the ledger/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Team A #11|Key A \(#101\)/);
    expect(accountRegion().getByText(`Registered: ${new Date(accountCreated).toLocaleString('en-US')}`)).toBeTruthy();
    expect(credentialRegion().getByText(`Registered: ${new Date(keyCreated).toLocaleString('en-US')}`)).toBeTruthy();
    expect(credentialRegion(102).getByText('Registered: Unknown')).toBeTruthy();

    mocks.confirm.mockResolvedValue(false);
    await fireEvent.click(accountRegion().getAllByRole('button', { name: 'configuration.delete' })[0]);
    expect(mocks.confirm).toHaveBeenLastCalledWith(`Delete ${accountName} and all its credentials? This cannot be undone.`);
    await fireEvent.click(credentialRegion().getByRole('button', { name: 'configuration.delete' }));
    expect(mocks.confirm).toHaveBeenLastCalledWith(`Delete ${keyPathName}? This cannot be undone.`);
  });

  it('identifies the exact subscription key in disconnect confirmation', async () => {
    const expires = '2030-01-01T12:00:00Z';
    Object.assign(records[0].credentials[0], { auth_mode: 'anthropic_subscription', subscription_status: 'configured', subscription_expires_at: expires });
    await openPanel({ provider: { ...provider, auth_mode: 'anthropic_subscription' } });
    const key = credentialRegion();
    expect(description(key, 'configuration.subscriptionAuthentication')?.textContent).toContain(messages['accounts.subscriptionStatusHelp']);
    expect(description(key, messages['accounts.subscriptionExpiryLabel'])?.textContent).toContain(new Date(expires).toLocaleString('en-US'));
    await fireEvent.click(credentialRegion().getByRole('button', { name: 'configuration.disconnect' }));
    expect(mocks.confirm).toHaveBeenLastCalledWith(`Disconnect ${keyPathName}? Its saved subscription grant will be removed.`);
    expect(mocks.remove).toHaveBeenCalledWith(`${base}/accounts/11/credentials/101/auth`, 'token', 'project');
  });

  it('automatically shows the UTC month, all-time figures, last use, and real zeros for a key absent from the ledger', async () => {
    records[0].credentials.push({ ...credential, id: 102, name: 'Key B' });
    mocks.get.mockImplementation(async (path: string) => path.endsWith('/usage') ? keyUsage([monthRow, { ...allTimeRow, credential_id: null }]) : structuredClone(records));
    await openPanel();
    const month = await credentialRegion().findByText(monthText, { selector: 'dt' });
    expect(Array.from(month.closest('dl')!.children, (child) => [child.tagName, child.textContent])).toEqual([
      ['DT', monthText],
      ['DD', 'Ledger requests: 2 · Input 120 · Output 15 · USD 0.1'],
      ['DT', 'All time'],
      ['DD', 'Ledger requests: 3 · Input 200 · Output 25 · USD 0.125'],
    ]);
    expect(credentialRegion().getByText(`Last used: ${new Date(monthRow.last_used_at).toLocaleString('en-US')}`)).toBeTruthy();
    expect(description(credentialRegion(102), monthText)?.textContent).toBe('Ledger requests: 0 · Input 0 · Output 0 · USD 0');
    expect(credentialRegion(102).queryByText(/^Last used:/)).toBeNull();
    expect(accountRegion().getByText('This month, account keys total: USD 0.1')).toBeTruthy();
    expect(accountRegion().getByText('Deleted keys, all time: Ledger requests: 3 · Input 200 · Output 25 · USD 0.125')).toBeTruthy();
    expect(screen.getByText('accounts.usageNotice')).toBeTruthy();
    expect(mocks.get).toHaveBeenCalledWith(`${base}/accounts/11/usage`, 'token', 'project');
  });

  it.each([undefined, period])('keeps an incomplete monthly row unknown while showing legacy totals (%j)', async (reportedPeriod) => {
    mocks.get.mockImplementation(async (path: string) => path.endsWith('/usage')
      ? { ...legacyUsage, period: reportedPeriod, credentials: [allTimeRow] }
      : structuredClone(records));
    await openPanel();
    await waitFor(() => expect(description(credentialRegion(), 'All time')?.textContent).toBe('Ledger requests: 3 · Input 200 · Output 25 · USD 0.125'));
    expect(description(credentialRegion(), reportedPeriod ? monthText : 'This month')?.textContent).toBe('Unknown');
    expect(accountRegion().getAllByText('Registered: Unknown')).toHaveLength(2);
    expect(screen.getByText('This month, provider keys total: Unknown')).toBeTruthy();
  });

  it('isolates a usage failure to its account and refreshes that account without mixing incompatible months', async () => {
    records.push({ ...account, id: 12, name: 'Team B', credentials: [{ ...credential, account_id: 12, id: 102, name: 'Key B' }] });
    const pending = deferred<AccountUsage>();
    const otherMonthRow = { ...monthRow, credential_id: 102, month_raw_cost: '0.2' };
    mocks.get.mockImplementation(async (path: string) => {
      if (path.endsWith('/accounts')) return structuredClone(records);
      return path.endsWith('/11/usage') ? pending.promise : keyUsage([otherMonthRow], 12);
    });
    await openPanel();
    expect(mocks.get).not.toHaveBeenCalledWith(`${base}/accounts/12/usage`, 'token', 'project');
    expect(accountRegion().getByRole('button', { name: 'accounts.addCredential' }).hasAttribute('disabled')).toBe(false);
    pending.reject(new mocks.ApiError('irrelevant upstream body', 503));
    expect((await accountRegion().findByRole('alert')).textContent).toContain("Couldn't load account usage");
    expect(description(credentialRegion(), 'This month')?.textContent).toBe('Unknown');
    expect(description(credentialRegion(), 'All time')?.textContent).toBe('Unknown');
    await waitFor(() => expect(description(credentialRegion(102), monthText)?.textContent).toBe('Ledger requests: 2 · Input 120 · Output 15 · USD 0.2'));
    expect(screen.getByText('This month, provider keys total: Unknown')).toBeTruthy();

    mocks.get.mockResolvedValueOnce(keyUsage([monthRow]));
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.usage' }));
    expect(await screen.findByText('This month, provider keys total: USD 0.3')).toBeTruthy();
    expect(accountRegion().queryByRole('alert')).toBeNull();
    expect(mocks.get.mock.calls.filter(([path]) => path === `${base}/accounts/11/usage`)).toHaveLength(2);

    mocks.get.mockResolvedValueOnce({ ...keyUsage([monthRow]), period: { ...period, start: period.end, end: '2027-01-01T00:00:00Z' } });
    await fireEvent.click(accountRegion().getByRole('button', { name: 'accounts.usage' }));
    await waitFor(() => expect(description(credentialRegion(), 'This month (Dec 1, 2026 – Dec 31, 2026, UTC)')?.textContent).toBe('Ledger requests: 2 · Input 120 · Output 15 · USD 0.1'));
    expect(screen.getByText('This month, provider keys total: Unknown')).toBeTruthy();
  });

  it('discards a late usage result superseded by a new inventory read', async () => {
    const pending = deferred<AccountUsage>();
    let initial = true;
    mocks.get.mockImplementation(async (path: string) => {
      if (path.endsWith('/accounts')) return structuredClone(records);
      if (!initial) return keyUsage([{ ...monthRow, month_raw_cost: '0.2' }]);
      initial = false;
      return pending.promise;
    });
    await openPanel();
    await fireEvent.click(screen.getByRole('button', { name: 'configuration.refreshAll' }));
    await screen.findByText('This month, provider keys total: USD 0.2');
    await act(() => { pending.resolve(keyUsage([monthRow])); });
    expect(screen.getByText('This month, provider keys total: USD 0.2')).toBeTruthy();
  });

  it('aligns decimal scales without rounding tiny, large, or scientific-notation costs', () => {
    expect(sumLedgerCosts(['9007199254740993.000000001', '1E-8', '-0.000000001'])).toBe('9007199254740993.00000001');
    expect(sumLedgerCosts(['0.1', '0.2'])).toBe('0.3');
  });

  it('does not delete after an ABA identity transition during confirmation', async () => {
    const confirmation = deferred<boolean>(); mocks.confirm.mockReturnValue(confirmation.promise);
    await openPanel();
    await fireEvent.click(accountRegion().getAllByRole('button', { name: 'configuration.delete' })[1]);
    session.update((value) => ({ ...value, userId: 'another-admin' }));
    session.update((value) => ({ ...value, userId: 'admin' }));
    confirmation.resolve(true);
    await waitFor(() => expect(screen.queryByRole('region', { name: accountName })).toBeNull());
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
    expect(screen.getByRole('region', { name: accountName })).toBeTruthy();
    expect(screen.queryByText('Selection order 1')).toBeNull();
    expect(mocks.get.mock.calls.filter(([path]) => path.endsWith('/accounts'))).toHaveLength(1);
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
    expect(screen.queryByText(keyName)).toBeNull();
    expect(screen.getByText('Other endpoint')).toBeTruthy();
  });

  it('retains credential rows after delete fails and never reports the deletion as successful', async () => {
    mocks.remove.mockRejectedValue(new mocks.ApiError('not allowed', 403));
    await openPanel();
    await fireEvent.click(accountRegion().getAllByRole('button', { name: 'configuration.delete' })[1]);
    expect(await screen.findByText('accounts.requestFailed 403')).toBeTruthy();
    expect(screen.getByText(keyName)).toBeTruthy();
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
    mocks.get.mockImplementation(async (path: string) => poolRead(path) ?? structuredClone(models));
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
    await screen.findByText('API key Key B (ID 102)');
    expect(screen.getByText(keyName)).toBeTruthy();
    expect(mocks.post).toHaveBeenCalledWith(`${base}/accounts/11/credentials`, expect.objectContaining({ name: 'Key B', api_key: 'private-key-B' }), 'token', 'project');
    expect(mocks.patch).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain('private-key-B');
  });

  it('tests each exact key only on explicit action, with cost notice and selected registered text model', async () => {
    records[0].credentials.push({ ...credential, id: 102, name: 'Key B' });
    probeReads(); mocks.post.mockResolvedValue(result);
    await openPanel();
    await chooseKey();
    expect(within(screen.getByRole('region', { name: 'accounts.probeTitle' })).getByRole('heading', { name: keyPathName })).toBeTruthy();
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
    await waitFor(() => expect(screen.queryByRole('region', { name: accountName })).toBeNull());
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
    mocks.get.mockImplementation(async (path: string) => poolRead(path) ?? models.map((model) => ({ ...model, updated_at: '2030-01-01' })));
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
    mocks.get.mockImplementation(async (path: string) => poolRead(path) ?? (path.includes('before_id=7') ? { ...relay(101, 6), items: [{ ...relay().items[0], ledger_id: 6, dispatches: null }] } : { ...relay(path.includes('/102/') ? 102 : 101), next_before_id: path.includes('/101/') ? 7 : null }));
    await openPanel({ provider: { ...provider, api_base: 'https://current-user:current-secret@current.example/v1?key=current-query' } });
    expect(mocks.get.mock.calls.filter(([path]) => path.includes('/relays'))).toHaveLength(0);
    expect(within(description(row(), 'accounts.currentEndpoint') as HTMLElement).getByText('https://current.example/v1')).toBeTruthy();
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
    expect(await screen.findByRole('region', { name: accountName })).toBeTruthy();
    expect(screen.queryByText('accounts.poolUnavailable')).toBeNull();
  });

  it('does not turn history read failures into zero and permits explicit retry', async () => {
    mocks.get.mockImplementation(async (path: string) => {
      const result = poolRead(path);
      if (result) return result;
      throw new mocks.ApiError('echoed-secret', 503);
    });
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
    mocks.get.mockImplementation(async (path: string) => poolRead(path) ?? relay(102));
    await openPanel();
    await fireEvent.click(row().getByRole('button', { name: 'accounts.loadRelays' }));
    expect(await row().findByText('accounts.networkError')).toBeTruthy();
    expect(document.body.textContent).not.toContain('old-key-102');
  });

  it.each(['close', 'ABA', 'refresh-generation', 'destroy'])('discards private late history after %s', async (change) => {
    const pending = deferred<RelayPage>();
    mocks.get.mockImplementation(async (path: string) => poolRead(path) ?? pending.promise);
    const component = await openPanel();
    await fireEvent.click(row().getByRole('button', { name: 'accounts.loadRelays' }));
    if (change === 'close') { await fireEvent.click(screen.getByRole('button', { name: 'configuration.close' })); }
    if (change === 'ABA') { session.update((value) => ({ ...value, projectId: 'other' })); session.update((value) => ({ ...value, projectId: 'project' })); }
    if (change === 'refresh-generation') { records[0].credentials[0].generation = 3; await fireEvent.click(screen.getByRole('button', { name: 'configuration.refreshAll' })); await waitFor(() => expect(mocks.get.mock.calls.filter(([path]) => path.endsWith('/accounts'))).toHaveLength(2)); }
    if (change === 'destroy') component.unmount();
    pending.resolve(relay());
    await Promise.resolve();
    expect(document.body.textContent).not.toContain('old-key-101');
  });
});
