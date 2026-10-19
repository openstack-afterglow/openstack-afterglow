import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { createAdminCredentialsController } from '../adminCredentialsController.svelte';
import CredentialManagement from '$lib/components/admin/credentials/CredentialManagement.svelte';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import type { CredentialAuthority } from '$lib/types/adminCredential';
import { t } from '$lib/i18n/ns/admin-identity';
import { t as dt } from '$lib/i18n/ns/domain-admin';
import { getLocale, initLocale, intlLocale } from '$lib/i18n/runtime.svelte';
import { LOCALES } from '$lib/i18n/locales';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('$lib/api/adminCredentials', () => ({ credentialRequest: request }));
const initialAuth = get(auth);
const initialLocale = getLocale();
const domainId = 'domain-a';
const props = { domainId, domainName: 'Domain A' };
const authority: CredentialAuthority = { token: 'token-a', userId: 'user-a', projectId: 'project-a', admin: true, ready: true };
const app = { id: 'app-a', domain_id: domainId, user_id: 'user-a', name: 'robot', description: '', project_id: 'project-a', expires_at: null, roles: [{ id: 'reader-id', name: 'reader' }], unrestricted: false };
const credential = { id: 'cred-a', domain_id: domainId, user_id: 'user-a', project_id: 'project-a', type: 'cert' };
const users = [{ id: 'user-a', domain_id: domainId, name: 'Actor' }, { id: 'user-b', domain_id: domainId, name: 'Other' }];
const context = { domain_id: domainId, user_id: 'user-a', project_id: 'project-a', roles: app.roles };

function respond(path: string, selectedDomain: string, _authority: CredentialAuthority, method?: string, body?: Record<string, unknown>) {
  if (path.includes('/users?')) return Promise.resolve({ items: selectedDomain === domainId ? users : [], next_marker: null });
  if (path.endsWith('/context')) return Promise.resolve(context);
  if (method === 'POST') return Promise.resolve(path.includes('/application-credentials') ? { ...app, secret: 'once-secret' } : { ...credential, ...body });
  if (method === 'PATCH') return Promise.resolve({ ...credential, ...body });
  if (method === 'DELETE') return Promise.resolve(undefined);
  if (path.includes('/cred-a')) return Promise.resolve(credential);
  if (path.includes('/app-a')) return Promise.resolve(app);
  return Promise.resolve({ items: [] });
}
beforeEach(() => { request.mockReset().mockImplementation(respond); authReady.set(false); projectSwitching.set(false); });
afterEach(() => { cleanup(); auth.set(initialAuth); authReady.set(false); projectSwitching.set(false); initLocale(initialLocale); });

async function ready(kind: 'application' | 'user' = 'application') {
  const ctrl = createAdminCredentialsController(kind, domainId);
  ctrl.setAuthority(authority);
  await ctrl.loadUsers();
  return ctrl;
}
async function readyApplication() {
  const ctrl = await ready();
  await ctrl.open('create');
  ctrl.draft.name = 'robot'; ctrl.draft.role_ids = ['reader-id'];
  return ctrl;
}
function authenticate() {
  auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', username: 'Actor', projectId: 'project-a', isSystemAdmin: true });
  authReady.set(true);
}

describe('credential selected-domain and sensitive lifecycle', () => {
  it.each(['token', 'userId', 'projectId', 'admin', 'ready'] as const)('discards issued secrets immediately on %s change', async field => {
    const ctrl = await readyApplication(); await ctrl.submit();
    expect(ctrl.issued?.secret).toBe('once-secret');
    ctrl.setAuthority({ ...authority, [field]: field === 'admin' || field === 'ready' ? false : 'changed' });
    expect(ctrl.issued).toBeNull(); expect(ctrl.mode).toBeNull(); expect(ctrl.draft.blob).toBe('');
    ctrl.dispose();
  });
  it.each(['close', 'dispose', 'domain', 'authority'] as const)('does not publish late creation secret after %s, including ABA transitions', async event => {
    const ctrl = await readyApplication();
    const pending = Promise.withResolvers<unknown>(); request.mockImplementationOnce(() => pending.promise);
    const saving = ctrl.submit();
    if (event === 'domain') { ctrl.setScope('domain-b'); ctrl.setScope(domainId); }
    else if (event === 'authority') { ctrl.setAuthority({ ...authority, projectId: 'project-b' }); ctrl.setAuthority(authority); }
    else ctrl[event]();
    pending.resolve({ ...app, secret: 'late-secret' }); await saving;
    expect(ctrl.issued).toBeNull(); expect(ctrl.mode).toBeNull(); ctrl.dispose();
  });
  it('requires nonempty explicit domain before any lookup', async () => {
    const ctrl = createAdminCredentialsController('user', ''); ctrl.setAuthority(authority);
    await ctrl.load(); await ctrl.loadUsers(); await ctrl.open('create');
    expect(request).not.toHaveBeenCalled(); expect(ctrl.allowed).toBe(false); ctrl.dispose();
  });
  it('passes selected domain through every directory page, list, context, detail, reveal and mutation', async () => {
    const application = await readyApplication();
    await application.submit(); application.close(); await application.open('detail', app);
    await application.open('delete', app); await application.submit(); application.dispose();
    const user = await ready('user');
    await user.open('create'); user.draft.user_id = 'user-a'; user.draft.project_id = 'project-a'; user.draft.type = 'cert'; user.draft.blob = '{"key":"new"}'; await user.submit();
    await user.open('detail', credential);
    request.mockImplementationOnce(() => Promise.resolve({ ...credential, blob: '{"key":"old"}' })); await user.reveal(true);
    user.draft.blob = '{"key":"changed"}'; await user.submit();
    await user.open('delete', credential); await user.submit();
    expect(request.mock.calls.every(([, selectedDomain]) => selectedDomain === domainId)).toBe(true);
    expect(request.mock.calls.some(([path]) => path.includes('/users?limit=100'))).toBe(true);
    expect(request.mock.calls.some(([path]) => path.endsWith('/context'))).toBe(true);
    expect(request.mock.calls.some(([path]) => path.includes('sensitive=true'))).toBe(true);
    expect(request.mock.calls.some(([path, , , method, body]) => path.endsWith('/cred-a') && method === 'PATCH' && body.blob === '{"key":"changed"}')).toBe(true);
    expect(request.mock.calls.some(([path, , , method]) => path.includes('/app-a?user_id=user-a') && method === 'DELETE')).toBe(true);
    expect(user.draft.blob).toBe(''); user.dispose();
  });
  it('does not invent the current user or list their credentials in another selected domain', async () => {
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? { items: [users[1]], next_marker: null } : { items: [] }));
    const ctrl = await ready();
    expect(ctrl.users).toEqual([users[1]]); expect(ctrl.selectedUser).toBe(''); expect(ctrl.canCreate).toBe(false);
    await ctrl.open('create'); expect(ctrl.mode).toBeNull();
    expect(request.mock.calls.some(([path]) => path.includes('application-credentials'))).toBe(false);
    await ctrl.selectUser('user-b'); expect(ctrl.selectedUser).toBe('user-b'); expect(ctrl.canCreate).toBe(false);
    await ctrl.selectUser('user-a'); expect(ctrl.selectedUser).toBe('user-b'); ctrl.dispose();
  });
  it.each([{ ...context, project_id: 'foreign-project' }, { ...context, user_id: 'foreign-user' }, { ...context, domain_id: 'foreign-domain' }])('rejects application creation context outside the actual caller/project/domain', async invalidContext => {
    const ctrl = await ready(); request.mockImplementationOnce(() => Promise.resolve(invalidContext));
    await ctrl.open('create'); expect(ctrl.context).toBeNull(); expect(ctrl.modalError).toBe(t('credentials.scopeDenied'));
    ctrl.draft.role_ids = ['reader-id']; await ctrl.submit();
    expect(request.mock.calls.some(([, , , method]) => method === 'POST')).toBe(false); ctrl.dispose();
  });
  it('rejects an issued secret with foreign provenance before publishing it', async () => {
    const ctrl = await readyApplication(); request.mockImplementationOnce(() => Promise.resolve({ ...app, domain_id: 'foreign', secret: 'foreign-secret' }));
    await ctrl.submit(); expect(ctrl.issued).toBeNull(); expect(ctrl.modalError).toBe(t('credentials.scopeDenied')); ctrl.dispose();
  });
  it.each(['application', 'user'] as const)('shows HTTP 502 rollback failure distinctly and refreshes %s metadata without retrying POST', async kind => {
    const ctrl = kind === 'application' ? await readyApplication() : await ready('user');
    if (kind === 'user') {
      await ctrl.open('create'); ctrl.draft.user_id = 'user-a'; ctrl.draft.project_id = 'project-a'; ctrl.draft.type = 'cert'; ctrl.draft.blob = '{"key":"new"}';
    }
    const persisted = kind === 'application' ? app : credential;
    const base = `/api/v1/admin/${kind === 'application' ? 'application' : 'user'}-credentials`;
    request.mockImplementation((path: string, scope: string, actor: CredentialAuthority, method?: string, body?: Record<string, unknown>) => {
      if (method === 'POST') return Promise.reject(new ApiError(502, '', 'credential_rollback_failed'));
      if (path === base || path.startsWith(`${base}?`)) return Promise.resolve({ items: [persisted] });
      return respond(path, scope, actor, method, body);
    });
    await ctrl.submit();
    expect(ctrl.modalError).toBe(dt('credentials.rollbackFailed'));
    expect(ctrl.modalError).not.toBe(t('credentials.unavailable'));
    await vi.waitFor(() => expect(ctrl.items).toEqual([persisted]));
    expect(ctrl.issued).toBeNull(); expect(ctrl.mode).toBe('create');
    expect(request.mock.calls.filter(([, , , method]) => method === 'POST')).toHaveLength(1);
    ctrl.dispose();
  });
  it('does not let an older context overwrite a newer modal', async () => {
    const ctrl = await ready(); const pending = Promise.withResolvers<unknown>(); request.mockImplementationOnce(() => pending.promise);
    const opening = ctrl.open('create'); ctrl.close(); await ctrl.open('create');
    pending.resolve({ ...context, project_id: 'old-project' }); await opening;
    expect(ctrl.context).toEqual(context); ctrl.dispose();
  });
  it('owner selection discards issued secret and rejects an old list', async () => {
    const ctrl = await readyApplication(); await ctrl.submit();
    const pending = Promise.withResolvers<unknown>(); request.mockImplementationOnce(() => pending.promise); const loading = ctrl.load();
    await ctrl.selectUser('user-b'); pending.resolve({ items: [app] }); await loading;
    expect(ctrl.items).toEqual([]); expect(ctrl.issued).toBeNull(); ctrl.dispose();
  });
  it('clears owner selection while a list is pending without leaving a spinner or stale inventory', async () => {
    const ctrl = await ready(); const pending = Promise.withResolvers<unknown>();
    request.mockImplementationOnce(() => pending.promise); const loading = ctrl.load();
    expect(ctrl.loading).toBe(true); await ctrl.selectUser('');
    expect(ctrl.loading).toBe(false); expect(ctrl.selectedUser).toBe('');
    pending.resolve({ items: [app] }); await loading;
    expect(ctrl.items).toEqual([]); expect(ctrl.loading).toBe(false); ctrl.dispose();
  });
  it('requires explicit delete confirmation and never offers fictional application edits', async () => {
    const ctrl = await ready(); await ctrl.open('delete', app);
    expect(request.mock.calls.some(([, , , method]) => method === 'DELETE')).toBe(false);
    await ctrl.submit();
    expect(request.mock.calls.some(([path, scope, , method]) => path.includes('/app-a?user_id=user-a') && scope === domainId && method === 'DELETE')).toBe(true);
    expect(request.mock.calls.some(([, , , method]) => method === 'PATCH')).toBe(false); ctrl.dispose();
  });
  it.each(['close', 'domain', 'authority'] as const)('drops a late reveal after %s and clears edit drafts', async event => {
    const ctrl = await ready('user'); await ctrl.open('detail', credential);
    expect(request.mock.calls.some(([path]) => path.includes('sensitive=true'))).toBe(false);
    const pending = Promise.withResolvers<unknown>(); request.mockImplementationOnce(() => pending.promise); const revealing = ctrl.reveal(true);
    if (event === 'domain') { ctrl.setScope('domain-b'); ctrl.setScope(domainId); }
    else if (event === 'authority') ctrl.setAuthority({ ...authority, admin: false });
    else ctrl.close();
    pending.resolve({ ...credential, blob: 'sensitive-blob' }); await revealing;
    expect(ctrl.detail).toBeNull(); expect(ctrl.draft.blob).toBe(''); ctrl.dispose();
  });
  it('rejects mismatched reveal metadata without copying its blob into an edit draft', async () => {
    const ctrl = await ready('user'); await ctrl.open('detail', credential);
    request.mockImplementationOnce(() => Promise.resolve({ ...credential, domain_id: 'foreign', blob: 'foreign-blob' })); await ctrl.reveal(true);
    expect(ctrl.draft.blob).toBe(''); expect(ctrl.detail).toEqual(credential); expect(ctrl.modalError).toBe(t('credentials.scopeDenied')); ctrl.dispose();
  });
  it('publishes native and directory denial as errors, never verified empty success or platform revocation', async () => {
    request.mockRejectedValue(new ApiError(403, '', 'credential_native_denied'));
    const ctrl = createAdminCredentialsController('user', domainId); ctrl.setAuthority(authority); await ctrl.load(); await ctrl.loadUsers();
    expect(ctrl.error).toBe(t('credentials.denied')); expect(ctrl.directoryError).toBe(t('credentials.denied')); expect(ctrl.items).toEqual([]); expect(ctrl.allowed).toBe(true); ctrl.dispose();
  });
  it('clears secrets and blocks a definitively denied platform-admin token', async () => {
    const ctrl = await readyApplication(); await ctrl.submit(); request.mockRejectedValueOnce(new ApiError(403, '', 'credential_admin_denied')); await ctrl.load();
    expect(ctrl.allowed).toBe(false); expect(ctrl.issued).toBeNull(); expect(ctrl.mode).toBeNull();
    ctrl.setAuthority(authority); expect(ctrl.allowed).toBe(false); ctrl.dispose();
  });
  it('ignores an old authority denial instead of disabling the new authority', async () => {
    const ctrl = await ready('user'); const pending = Promise.withResolvers<unknown>(); request.mockImplementationOnce(() => pending.promise); const loading = ctrl.load();
    ctrl.setAuthority({ ...authority, token: 'token-b' }); pending.reject(new ApiError(403, '', 'credential_admin_denied')); await loading;
    expect(ctrl.allowed).toBe(true); expect(ctrl.error).toBe(''); ctrl.dispose();
  });
  it('reads all scoped directory pages before publishing the selector', async () => {
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?')
      ? path.includes('marker=user-a') ? { items: [users[1]], next_marker: null } : { items: [users[0]], next_marker: 'user-a' }
      : { items: [] }));
    const ctrl = await ready('user'); expect(ctrl.users).toEqual(users); expect(ctrl.directoryError).toBe('');
    expect(request.mock.calls.filter(([path]) => path.includes('/users?')).every(([, scope]) => scope === domainId)).toBe(true); ctrl.dispose();
  });
  it('rejects an entire mixed-domain directory page instead of silently filtering it', async () => {
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? { items: [users[0], { ...users[1], domain_id: 'foreign' }], next_marker: null } : { items: [] }));
    const ctrl = await ready('user'); expect(ctrl.users).toEqual([]); expect(ctrl.directoryError).toBe(t('credentials.scopeDenied')); expect(ctrl.canCreate).toBe(false); ctrl.dispose();
  });
  it('rejects mixed-domain credential metadata rather than publishing a filtered partial success', async () => {
    const ctrl = await ready('user'); request.mockResolvedValueOnce({ items: [credential, { ...credential, id: 'foreign', domain_id: 'foreign' }] }); await ctrl.load();
    expect(ctrl.items).toEqual([]); expect(ctrl.error).toBe(t('credentials.scopeDenied')); ctrl.dispose();
  });
  it('fences both late directory and list publication on selected-domain ABA', async () => {
    const ctrl = await ready('user'); const directory = Promise.withResolvers<unknown>(), list = Promise.withResolvers<unknown>();
    request.mockImplementationOnce(() => directory.promise); const oldDirectory = ctrl.loadUsers();
    request.mockImplementationOnce(() => list.promise); const oldList = ctrl.load();
    ctrl.setScope('domain-b'); ctrl.setScope(domainId); await ctrl.loadUsers();
    directory.resolve({ items: [{ ...users[0], name: 'Stale' }], next_marker: null }); list.resolve({ items: [credential] }); await Promise.all([oldDirectory, oldList]);
    expect(ctrl.users).toEqual(users); expect(ctrl.items).toEqual([]); expect(ctrl.selectedUser).toBe(''); ctrl.dispose();
  });
  it('reports stalled directory pagination without publishing partial users', async () => {
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? { items: [users[0]], next_marker: 'user-a' } : { items: [] }));
    const ctrl = await ready('user'); expect(ctrl.users).toEqual([]); expect(ctrl.directoryError).not.toBe(''); ctrl.dispose();
  });
});

describe('credential operator UI', () => {
  it('reveals blobs explicitly and clears them on authority change', async () => {
    authenticate(); request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? { items: users, next_marker: null }
      : path.includes('sensitive=true') ? { ...credential, blob: 'revealed-sensitive-value' } : path.includes('/cred-a') ? credential : { items: [credential] }));
    render(CredentialManagement, { kind: 'user', ...props });
    await vi.waitFor(() => expect(screen.getByText('cred-a')).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: t('credentials.details') })); expect(screen.queryByText('revealed-sensitive-value')).toBeNull();
    await vi.waitFor(() => expect((screen.getByRole('button', { name: t('credentials.reveal') }) as HTMLButtonElement).disabled).toBe(false));
    await fireEvent.click(screen.getByRole('button', { name: t('credentials.reveal') })); await vi.waitFor(() => expect(screen.getByText('revealed-sensitive-value')).toBeTruthy());
    auth.update(state => ({ ...state, projectId: 'project-b' }));
    await vi.waitFor(() => expect(screen.queryByText('revealed-sensitive-value')).toBeNull()); expect(screen.queryByRole('dialog')).toBeNull();
  });
  it('offers no synthetic current-user option when directory lacks that caller', async () => {
    authenticate(); request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? { items: [users[1]], next_marker: null } : { items: [] }));
    render(CredentialManagement, { kind: 'application', ...props });
    await vi.waitFor(() => expect(screen.getByRole('option', { name: 'Other · user-b' })).toBeTruthy());
    expect(screen.queryByRole('option', { name: /Actor/ })).toBeNull(); expect((screen.getByRole('button', { name: t('actions.create') }) as HTMLButtonElement).disabled).toBe(true);
  });
  it('requires a verified same-domain directory before enabling application issuance, not a list result', async () => {
    authenticate(); const directory = Promise.withResolvers<unknown>(), list = Promise.withResolvers<unknown>();
    request.mockImplementation((path: string) => path.includes('/users?') ? directory.promise : list.promise);
    render(CredentialManagement, { kind: 'application', ...props });
    const create = screen.getByRole('button', { name: t('actions.create') }) as HTMLButtonElement; expect(create.disabled).toBe(true);
    directory.resolve({ items: users, next_marker: null }); await vi.waitFor(() => expect(create.disabled).toBe(false));
    auth.update(state => ({ ...state, isSystemAdmin: false })); await vi.waitFor(() => expect(create.disabled).toBe(true)); list.resolve({ items: [] });
  });
  it('filters real same-domain project/type metadata locally', async () => {
    authenticate(); const second = { ...credential, id: 'cred-b', project_id: 'project-b', type: 'ec2' };
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? { items: users, next_marker: null } : { items: [credential, second] }));
    render(CredentialManagement, { kind: 'user', ...props }); await vi.waitFor(() => expect(screen.getByText('cred-b')).toBeTruthy());
    await fireEvent.change(screen.getByRole('combobox', { name: t('credentials.project') }), { target: { value: 'project-b' } });
    expect(screen.queryByText('cred-a')).toBeNull(); expect(screen.getByText('cred-b')).toBeTruthy();
    await fireEvent.change(screen.getByRole('combobox', { name: t('credentials.type') }), { target: { value: 'cert' } }); expect(screen.getByText(t('credentials.noMatches'))).toBeTruthy();
    expect(request.mock.calls.some(([path]) => path.includes('type=') || path.includes('project_id='))).toBe(false);
  });
  it.each(LOCALES)('formats table and detail expiry in %s while retaining the exact ISO timestamp', async locale => {
    initLocale(locale); authenticate();
    const timestamp = '2031-02-03T04:05:06.123456Z';
    const expiring = { ...app, expires_at: timestamp };
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? { items: users, next_marker: null } : path.includes('/app-a') ? expiring : { items: [expiring] }));
    render(CredentialManagement, { kind: 'application', ...props });
    const formatted = new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(Date.parse(timestamp));
    await vi.waitFor(() => expect(screen.getByTitle(timestamp).textContent).toBe(formatted));
    expect(screen.getByTitle(timestamp).getAttribute('datetime')).toBe(timestamp);
    await fireEvent.click(screen.getByRole('button', { name: t('credentials.details') }));
    await vi.waitFor(() => expect(screen.getAllByTitle(timestamp)).toHaveLength(2));
    for (const time of screen.getAllByTitle(timestamp)) {
      expect(time.textContent).toBe(formatted); expect(time.getAttribute('datetime')).toBe(timestamp);
    }
  });
  it('filters actual application expiry metadata without pretending unknown expiry is active', async () => {
    authenticate(); const expired = { ...app, id: 'expired', name: 'expired-robot', expires_at: '2000-01-01T00:00:00Z' };
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?') ? { items: users, next_marker: null } : { items: [app, expired, { ...app, id: 'unknown', name: 'unknown-robot', expires_at: 'invalid' }] }));
    render(CredentialManagement, { kind: 'application', ...props }); await vi.waitFor(() => expect(screen.getByText('expired-robot')).toBeTruthy());
    await fireEvent.change(screen.getByRole('combobox', { name: t('credentials.expiry') }), { target: { value: 'expired' } }); expect(screen.queryByText('robot')).toBeNull(); expect(screen.getByText('expired-robot')).toBeTruthy();
    await fireEvent.change(screen.getByRole('combobox', { name: t('credentials.expiry') }), { target: { value: 'active' } }); expect(screen.getByText('robot')).toBeTruthy(); expect(screen.queryByText('unknown-robot')).toBeNull();
  });
  it('does not render native denial as an empty inventory', async () => {
    authenticate(); request.mockRejectedValue(new ApiError(403, '', 'credential_native_denied'));
    render(CredentialManagement, { kind: 'user', ...props }); await vi.waitFor(() => expect(screen.getAllByText(t('credentials.denied')).length).toBeGreaterThan(0));
    expect(screen.queryByText(t('credentials.empty'))).toBeNull();
  });
  it('clears dialog, owner selection and search on direct domain prop change and rejects a late reveal', async () => {
    authenticate(); request.mockImplementation((path: string, scope: string) => scope !== domainId ? respond(path, scope, authority) : Promise.resolve(path.includes('/users?') ? { items: users, next_marker: null } : path.includes('/cred-a') ? credential : { items: [credential] }));
    const view = render(CredentialManagement, { kind: 'user', ...props }); await vi.waitFor(() => expect(screen.getByText('cred-a')).toBeTruthy());
    await fireEvent.input(screen.getByRole('searchbox', { name: t('credentials.search') }), { target: { value: 'cred-a' } });
    await fireEvent.change(screen.getByRole('combobox', { name: t('credentials.user') }), { target: { value: 'user-a' } });
    await vi.waitFor(() => expect(screen.getByText('cred-a')).toBeTruthy()); await fireEvent.click(screen.getByRole('button', { name: t('credentials.details') }));
    await vi.waitFor(() => expect((screen.getByRole('button', { name: t('credentials.reveal') }) as HTMLButtonElement).disabled).toBe(false));
    const pending = Promise.withResolvers<unknown>(); request.mockImplementationOnce(() => pending.promise); await fireEvent.click(screen.getByRole('button', { name: t('credentials.reveal') }));
    await view.rerender({ kind: 'user', domainId: 'domain-b', domainName: 'Domain B' });
    pending.resolve({ ...credential, blob: 'late-foreign-secret' }); await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.queryByText('late-foreign-secret')).toBeNull(); expect((screen.getByRole('searchbox', { name: t('credentials.search') }) as HTMLInputElement).value).toBe('');
    expect((screen.getByRole('combobox', { name: t('credentials.user') }) as HTMLSelectElement).value).toBe('');
  });
  it('keeps once-only secrets through Escape until explicit close', async () => {
    authenticate(); render(CredentialManagement, { kind: 'application', ...props });
    await vi.waitFor(() => expect((screen.getByRole('button', { name: t('actions.create') }) as HTMLButtonElement).disabled).toBe(false));
    await fireEvent.click(screen.getByRole('button', { name: t('actions.create') })); await vi.waitFor(() => expect(screen.getByRole('checkbox', { name: 'reader' })).toBeTruthy());
    await fireEvent.input(screen.getByRole('textbox', { name: t('form.name') }), { target: { value: 'robot' } }); await fireEvent.click(screen.getByRole('checkbox', { name: 'reader' }));
    await fireEvent.click(screen.getByRole('button', { name: t('actions.save') })); await vi.waitFor(() => expect(screen.getByText('once-secret')).toBeTruthy());
    await fireEvent.keyDown(document, { key: 'Escape' }); expect(screen.getByText('once-secret')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: t('credentials.close') })); await vi.waitFor(() => expect(screen.queryByText('once-secret')).toBeNull());
  });
});
