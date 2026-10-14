import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { createAdminCredentialsController } from '../adminCredentialsController.svelte';
import CredentialManagement from '$lib/components/admin/credentials/CredentialManagement.svelte';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import type { CredentialAuthority } from '$lib/types/adminCredential';
import { t } from '$lib/i18n/ns/admin-identity';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('$lib/api/adminCredentials', () => ({ credentialRequest: request }));
const authority: CredentialAuthority = { token: 'token-a', userId: 'user-a', projectId: 'project-a', admin: true, ready: true };
const app = { id: 'app-a', user_id: 'user-a', name: 'robot', description: '', project_id: 'project-a', expires_at: null, roles: [{ id: 'reader-id', name: 'reader' }], unrestricted: false };
const credential = { id: 'cred-a', user_id: 'user-a', project_id: 'project-a', type: 'cert' };

beforeEach(() => {
  request.mockReset().mockImplementation((path: string) => {
    if (path.includes('/users?')) return Promise.resolve({ items: [{ id: 'user-b', name: 'Other' }], next_marker: null });
    if (path.endsWith('/context')) return Promise.resolve({ user_id: 'user-a', project_id: 'project-a', roles: app.roles });
    if (path.includes('/cred-a')) return Promise.resolve(credential);
    return Promise.resolve({ items: [] });
  });
});
afterEach(cleanup);

async function readyApplication() {
  const ctrl = createAdminCredentialsController('application');
  ctrl.setAuthority(authority);
  await ctrl.open('create');
  ctrl.draft.name = 'robot'; ctrl.draft.role_ids = ['reader-id'];
  return ctrl;
}

describe('credential authority and sensitive lifecycle', () => {
  it.each(['token', 'userId', 'projectId', 'admin', 'ready'] as const)('discards one-time secret immediately on %s change', async (field) => {
    const ctrl = await readyApplication();
    request.mockImplementationOnce(() => Promise.resolve({ ...app, secret: 'once-secret' }));
    await ctrl.submit();
    expect(ctrl.issued?.secret).toBe('once-secret');
    ctrl.setAuthority({ ...authority, [field]: field === 'admin' || field === 'ready' ? false : 'changed' });
    expect(ctrl.issued).toBeNull(); expect(ctrl.mode).toBeNull(); expect(ctrl.draft.blob).toBe('');
    ctrl.dispose();
  });
  it.each(['close', 'dispose', 'scope'] as const)('does not publish late creation secret after %s', async (event) => {
    const ctrl = await readyApplication();
    const pending = Promise.withResolvers<unknown>();
    request.mockImplementationOnce(() => pending.promise);
    const saving = ctrl.submit();
    if (event === 'scope') {
      ctrl.setAuthority({ ...authority, projectId: 'project-b' });
      ctrl.setAuthority(authority); // ABA still cannot resurrect old secret.
    } else ctrl[event]();
    pending.resolve({ ...app, secret: 'late-secret' }); await saving;
    expect(ctrl.issued).toBeNull(); expect(ctrl.mode).toBeNull();
    ctrl.dispose();
  });
  it('does not let an older context request overwrite a newer modal', async () => {
    const ctrl = createAdminCredentialsController('application'); ctrl.setAuthority(authority);
    const oldContext = Promise.withResolvers<unknown>();
    request.mockImplementationOnce(() => oldContext.promise);
    const oldOpen = ctrl.open('create'); ctrl.close();
    await ctrl.open('create');
    oldContext.resolve({ user_id: 'old-user', project_id: 'old-project', roles: [] }); await oldOpen;
    expect(ctrl.context?.project_id).toBe('project-a'); ctrl.dispose();
  });
  it('user selection discards an issued secret and fences an old list', async () => {
    const ctrl = await readyApplication();
    request.mockImplementationOnce(() => Promise.resolve({ ...app, secret: 'once-secret' })); await ctrl.submit();
    const pending = Promise.withResolvers<unknown>();
    request.mockImplementationOnce(() => pending.promise); const oldLoad = ctrl.load();
    await ctrl.selectUser('user-b');
    pending.resolve({ items: [app] }); await oldLoad;
    expect(ctrl.items).toEqual([]); expect(ctrl.issued).toBeNull(); ctrl.dispose();
  });
  it('keeps blob retrieval explicit and drops late sensitive detail on modal close', async () => {
    const ctrl = createAdminCredentialsController('user'); ctrl.setAuthority(authority);
    await ctrl.open('detail', credential);
    expect(request.mock.calls.some(([path]) => path.includes('sensitive=true'))).toBe(false);
    const pending = Promise.withResolvers<unknown>(); request.mockImplementationOnce(() => pending.promise);
    const reveal = ctrl.reveal(true); ctrl.close();
    pending.resolve({ ...credential, blob: 'sensitive-blob' }); await reveal;
    expect(ctrl.detail).toBeNull(); expect(ctrl.draft.blob).toBe(''); ctrl.dispose();
  });
  it('requires confirmation and uses native delete without edit fiction for applications', async () => {
    const ctrl = createAdminCredentialsController('application'); ctrl.setAuthority(authority);
    await ctrl.open('delete', app);
    expect(request.mock.calls.some(([, , method]) => method === 'DELETE')).toBe(false);
    await ctrl.submit();
    expect(request.mock.calls.some(([path, , method]) => path.includes('/app-a?user_id=user-a') && method === 'DELETE')).toBe(true);
    expect(request.mock.calls.some(([, , method]) => method === 'PATCH')).toBe(false); ctrl.dispose();
  });
  it('publishes verified empty separately from directory and native denial errors', async () => {
    const ctrl = createAdminCredentialsController('user');
    request.mockImplementation((path: string) => path.includes('/users?') ? Promise.reject(new ApiError(503, '', 'credential_unavailable')) : Promise.reject(new ApiError(403, '', 'credential_native_denied')));
    ctrl.setAuthority(authority); await ctrl.load(); await ctrl.loadUsers();
    expect(ctrl.error).not.toBe(''); expect(ctrl.directoryError).not.toBe(''); expect(ctrl.items).toEqual([]);
    expect(ctrl.allowed).toBe(true); ctrl.dispose();
  });
  it('clears sensitive state and blocks a definitively denied platform-admin token', async () => {
    const ctrl = await readyApplication();
    request.mockImplementationOnce(() => Promise.resolve({ ...app, secret: 'once-secret' })); await ctrl.submit();
    request.mockImplementationOnce(() => Promise.reject(new ApiError(403, '', 'credential_admin_denied')));
    await ctrl.load();
    expect(ctrl.allowed).toBe(false); expect(ctrl.issued).toBeNull(); expect(ctrl.mode).toBeNull();
    ctrl.setAuthority(authority); // A stale store update cannot restore this denied token.
    expect(ctrl.allowed).toBe(false); ctrl.dispose();
  });
  it('reads every directory page before publishing a complete selector', async () => {
    const ctrl = createAdminCredentialsController('user');
    request.mockImplementation((path: string) => {
      if (!path.includes('/users?')) return Promise.resolve({ items: [] });
      return Promise.resolve(path.includes('marker=user-b')
        ? { items: [{ id: 'user-c', name: 'Third' }], next_marker: null }
        : { items: [{ id: 'user-b', name: 'Other' }], next_marker: 'user-b' });
    });
    ctrl.setAuthority(authority); await ctrl.loadUsers();
    expect(ctrl.users.map(u => u.id)).toEqual(['user-b', 'user-c']); expect(ctrl.directoryError).toBe(''); ctrl.dispose();
  });
  it('reports a directory pagination stall without publishing partial users as complete', async () => {
    const ctrl = createAdminCredentialsController('user');
    request.mockImplementation((path: string) => Promise.resolve(path.includes('/users?')
      ? { items: [{ id: 'user-b', name: 'Other' }], next_marker: 'user-b' }
      : { items: [] }));
    ctrl.setAuthority(authority); await ctrl.loadUsers();
    expect(ctrl.users).toEqual([]); expect(ctrl.directoryError).not.toBe(''); ctrl.dispose();
  });
  it('prefills a user blob only after explicit edit and clears it after native PATCH', async () => {
    const ctrl = createAdminCredentialsController('user'); ctrl.setAuthority(authority);
    await ctrl.open('detail', credential);
    expect(ctrl.draft.blob).toBe('');
    request.mockImplementationOnce(() => Promise.resolve({ ...credential, blob: '{"key":"old"}' }));
    await ctrl.reveal(true); expect(ctrl.draft.blob).toBe('{"key":"old"}');
    ctrl.draft.blob = '{"key":"new"}';
    await ctrl.submit();
    expect(request.mock.calls.some(([path, , method, body]) => path.endsWith('/cred-a') && method === 'PATCH' && body.blob === '{"key":"new"}')).toBe(true);
    expect(ctrl.draft.blob).toBe(''); expect(ctrl.detail).toBeNull(); ctrl.dispose();
  });
});

describe('credential consumer UI', () => {
  it('reveals sensitive blob only on explicit action and clears it on authority change', async () => {
    auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', username: 'Actor', projectId: 'project-a', isSystemAdmin: true });
    authReady.set(true); projectSwitching.set(false);
    request.mockImplementation((path: string) => {
      if (path.includes('/users?')) return Promise.resolve({ items: [], next_marker: null });
      if (path.includes('sensitive=true')) return Promise.resolve({ ...credential, blob: 'revealed-sensitive-value' });
      if (path.includes('/cred-a')) return Promise.resolve(credential);
      return Promise.resolve({ items: [credential] });
    });
    render(CredentialManagement, { kind: 'user' });
    await vi.waitFor(() => expect(screen.getByText('cred-a')).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: t('credentials.details') }));
    expect(screen.queryByText('revealed-sensitive-value')).toBeNull();
    await vi.waitFor(() => expect((screen.getByRole('button', { name: t('credentials.reveal') }) as HTMLButtonElement).disabled).toBe(false));
    await fireEvent.click(screen.getByRole('button', { name: t('credentials.reveal') }));
    await vi.waitFor(() => expect(screen.getByText('revealed-sensitive-value')).toBeTruthy());
    auth.update(s => ({ ...s, projectId: 'project-b' }));
    await vi.waitFor(() => expect(screen.queryByText('revealed-sensitive-value')).toBeNull());
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  it('updates issuance controls reactively when verified authority arrives before slow inventory', async () => {
    auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true });
    authReady.set(false); projectSwitching.set(false);
    const list = Promise.withResolvers<unknown>();
    request.mockImplementation((path: string) => path.includes('/users?') ? Promise.resolve({ items: [], next_marker: null }) : list.promise);
    render(CredentialManagement, { kind: 'application' });
    const create = screen.getByRole('button', { name: t('actions.create') }) as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    authReady.set(true);
    await vi.waitFor(() => expect(create.disabled).toBe(false));
    expect(screen.getAllByRole('status').some(node => node.textContent?.includes(t('state.loading')))).toBe(true);
    auth.update(s => ({ ...s, isSystemAdmin: false }));
    await vi.waitFor(() => expect(create.disabled).toBe(true));
    list.resolve({ items: [] });
  });
  it('keeps a once-only secret open through Escape until explicit close', async () => {
    auth.set({ ...get(auth), token: 'token-a', userId: 'user-a', projectId: 'project-a', isSystemAdmin: true });
    authReady.set(true); projectSwitching.set(false);
    request.mockImplementation((path: string, _authority: unknown, method?: string) => {
      if (path.includes('/users?')) return Promise.resolve({ items: [], next_marker: null });
      if (path.endsWith('/context')) return Promise.resolve({ user_id: 'user-a', project_id: 'project-a', roles: app.roles });
      if (method === 'POST') return Promise.resolve({ ...app, secret: 'once-only-visible' });
      return Promise.resolve({ items: [] });
    });
    render(CredentialManagement, { kind: 'application' });
    await fireEvent.click(screen.getByRole('button', { name: t('actions.create') }));
    await vi.waitFor(() => expect(screen.getByRole('checkbox', { name: 'reader' })).toBeTruthy());
    await fireEvent.input(screen.getByRole('textbox', { name: t('form.name') }), { target: { value: 'robot' } });
    await fireEvent.click(screen.getByRole('checkbox', { name: 'reader' }));
    await fireEvent.click(screen.getByRole('button', { name: t('actions.save') }));
    await vi.waitFor(() => expect(screen.getByText('once-only-visible')).toBeTruthy());
    await fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByText('once-only-visible')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: t('credentials.close') }));
    await vi.waitFor(() => expect(screen.queryByText('once-only-visible')).toBeNull());
  });
});
