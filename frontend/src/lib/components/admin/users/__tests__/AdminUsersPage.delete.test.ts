import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get, writable } from 'svelte/store';
import type * as Reactivity from 'svelte/reactivity';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '$lib/types/common';

const viewport = vi.hoisted(() => ({ desktop: true }));
vi.mock('svelte/reactivity', async original => ({ ...await original<typeof Reactivity>(), MediaQuery: class { get current() { return viewport.desktop; } } }));
vi.mock('$lib/stores/auth', () => ({
  auth: writable({ token: 'admin-token', userId: 'admin', sessionId: 'session-a', identityDomainId: 'accounts-home', domainId: 'working-domain', projectId: 'personal-project', isSystemAdmin: true }),
  authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
}));
const mocks = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn(), patch: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError }));
vi.mock('$lib/tutorial/engine', () => ({ startTour: vi.fn() }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [30, 60] }) }));
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import { ApiError } from '$lib/api/errors';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-identity';
import AdminUsersPage from '../AdminUsersPage.svelte';

const initialAuth = get(auth);
const alice: User & { domain_id: string } = { id: 'a718fbcb-a609-4d3a-986a-9e7d50840b69', name: 'Alice', email: 'alice@example.test', enabled: true, domain_id: 'native-home', default_project_id: null, created_at: null };
const bob: User = { ...alice, id: 'bob-native-id', name: 'Bob', email: 'bob@example.test' };
const self: User = { ...alice, id: 'admin', name: 'Current administrator', email: 'admin@example.test' };
let inventory: User[];
const userPath = '/api/v1/admin/users?limit=100&domain_id=native-home';
const activityPath = '/api/v1/admin/users/activity?limit=10&domain_id=native-home';
const deletePath = `/api/v1/admin/users/${alice.id}?domain_id=native-home`;
const readOptions = { refresh: true };
const modal = () => screen.queryByRole('dialog', { name: t('userDelete.title') });
const deleteAction = (name = alice.name) => screen.getByRole('button', { name: t('userDelete.actionLabel', { name }) });
async function loaded() { await screen.findByRole('button', { name: t('userDelete.actionLabel', { name: alice.name }) }); }
async function open(name = alice.name) { await fireEvent.click(deleteAction(name)); await screen.findByRole('dialog', { name: t('userDelete.title') }); }
async function confirm(id = alice.id) {
  const dialog = within(modal()!);
  await fireEvent.input(dialog.getByRole('textbox', { name: t('userDelete.confirmId') }), { target: { value: id } });
  await fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
}
function renderPage() { return render(AdminUsersPage, { domainId: alice.domain_id, domainName: 'Native home' }); }
beforeEach(() => {
  vi.resetAllMocks(); initLocale('en'); viewport.desktop = true; inventory = [alice, bob, self];
  auth.set({ ...initialAuth }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false);
  mocks.get.mockImplementation(async (path: string) => {
    if (path.includes('/activity?')) return [];
    if (path.includes('/sessions?')) return { sessions: [], count: 0 };
    if (path.includes('/permissions?')) return { items: [], count: 0 };
    if (path.includes('/managers')) return { items: [], roles: [] };
    return { items: [...inventory], next_marker: null };
  });
  mocks.delete.mockImplementation(async () => { inventory = inventory.filter(user => user.id !== alice.id); });
});
afterEach(() => { cleanup(); initLocale('ko'); });

describe.each([true, false])('AdminUsersPage delete consumer (desktop=%s)', desktop => {
  beforeEach(() => { viewport.desktop = desktop; });
  it('exposes a named destructive action, disables self, rereads native identity, and cancel never writes', async () => {
    renderPage(); await loaded();
    expect((screen.getByRole('button', { name: t('userDelete.selfProtected') }) as HTMLButtonElement).disabled).toBe(true);
    expect(document.querySelector('[data-responsive-view]')?.getAttribute('data-responsive-view')).toBe(desktop ? 'table' : 'cards');
    await open();
    expect(mocks.get).toHaveBeenCalledWith(userPath, 'admin-token', 'personal-project', readOptions);
    for (const value of [alice.id, alice.name, alice.domain_id, 'Native home']) expect(within(modal()!).getByText(value)).toBeTruthy();
    await fireEvent.click(within(modal()!).getByRole('button', { name: 'Cancel' }));
    expect(modal()).toBeNull(); expect(mocks.delete).not.toHaveBeenCalled();
  });

  it('sends one exact-home nonreplay DELETE and refreshes users/activity after success while preserving filters', async () => {
    renderPage(); await loaded();
    const search = screen.getByPlaceholderText(t('userPage.searchPlaceholder')) as HTMLInputElement;
    await fireEvent.input(search, { target: { value: 'Alice' } });
    await open(); await confirm();
    await waitFor(() => expect(modal()).toBeNull());
    expect(mocks.delete).toHaveBeenCalledExactlyOnceWith(deletePath, 'admin-token', 'personal-project', { replayOnUnauthorized: false });
    expect(mocks.get).toHaveBeenCalledWith(activityPath, 'admin-token', 'personal-project', readOptions);
    expect(search.value).toBe('Alice'); expect(screen.queryByRole('button', { name: t('userDelete.actionLabel', { name: 'Bob' }) })).toBeNull();
    expect(screen.getByText(t('userPage.noResults'))).toBeTruthy();
  });
});

describe('AdminUsersPage deletion ownership and failure fences', () => {
  it.each([401, 408, 500, 503, 0])('retains the target and prevents retry of uncertain HTTP %s until explicit close and reread', async status => {
    mocks.delete.mockRejectedValueOnce(new ApiError(status, 'Native result uncertain'));
    renderPage(); await loaded(); await open(); await confirm();
    expect(await screen.findByText('Native result uncertain')).toBeTruthy();
    expect(within(modal()!).getByText(alice.id)).toBeTruthy();
    expect(within(modal()!).queryByRole('button', { name: 'Delete' })).toBeNull();
    await fireEvent.click(within(modal()!).getByRole('button', { name: 'Close' }));
    const reads = mocks.get.mock.calls.filter(([path]) => path === userPath).length;
    await open();
    expect(mocks.get.mock.calls.filter(([path]) => path === userPath).length).toBe(reads + 1);
    expect((within(modal()!).getByRole('textbox') as HTMLInputElement).value).toBe('');
    expect(mocks.delete).toHaveBeenCalledOnce();
  });

  it.each([403, 404, 409])('keeps a native HTTP %s rejection visible rather than synthesizing success', async status => {
    mocks.delete.mockRejectedValueOnce(new ApiError(status, 'Native deletion rejected'));
    renderPage(); await loaded(); await open(); await confirm();
    expect(await screen.findByText('Native deletion rejected')).toBeTruthy();
    expect(modal()).toBeTruthy(); expect(mocks.delete).toHaveBeenCalledOnce();
    expect(inventory.some(user => user.id === alice.id)).toBe(true);
  });

  it('shows transport failures without a retry and ignores late rejection after unmount', async () => {
    mocks.delete.mockRejectedValueOnce(new TypeError('Connection lost'));
    const view = renderPage(); await loaded(); await open(); await confirm();
    expect(await screen.findByText(t('userDelete.failed'))).toBeTruthy();
    expect(within(modal()!).queryByRole('button', { name: 'Delete' })).toBeNull();
    await fireEvent.click(within(modal()!).getByRole('button', { name: 'Close' }));
    const pending = Promise.withResolvers<void>(); mocks.delete.mockReturnValueOnce(pending.promise);
    await open(); await confirm(); const reads = mocks.get.mock.calls.length;
    view.unmount(); pending.reject(new ApiError(503, 'Old request error')); await tick();
    expect(screen.queryByText('Old request error')).toBeNull(); expect(mocks.get).toHaveBeenCalledTimes(reads);
  });

  it('does not offer deletion if the fresh native directory no longer contains the account', async () => {
    renderPage(); await loaded(); inventory = [bob, self];
    await fireEvent.click(deleteAction()); await tick();
    expect(modal()).toBeNull(); expect(mocks.delete).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: t('userDelete.actionLabel', { name: alice.name }) })).toBeNull();
  });

  it('preserves the exact domain inventory guard before offering confirmation', async () => {
    renderPage(); await loaded();
    mocks.get.mockResolvedValueOnce({ items: [{ ...alice, domain_id: 'foreign-home' }], next_marker: null });
    await fireEvent.click(deleteAction()); await tick();
    expect(modal()).toBeNull(); expect(mocks.delete).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeTruthy();
  });

  it('closes the same account editor on a previously captured delete action', async () => {
    renderPage(); await loaded(); const action = deleteAction();
    await fireEvent.click(screen.getByRole('button', { name: 'Alice' }));
    await screen.findByRole('heading', { name: t('userEdit.title') });
    await fireEvent.click(action); await screen.findByRole('dialog', { name: t('userDelete.title') });
    await confirm(); await waitFor(() => expect(modal()).toBeNull());
    expect(screen.queryByRole('heading', { name: t('userEdit.title') })).toBeNull();
  });

  it('invalidates typed confirmation before submission when the selected native domain changes away and back', async () => {
    const view = renderPage(); await loaded(); await open();
    const input = within(modal()!).getByRole('textbox');
    await fireEvent.input(input, { target: { value: alice.id } });
    const form = input.closest('form')!;
    await view.rerender({ domainId: 'foreign-home', domainName: 'Foreign' });
    await view.rerender({ domainId: alice.domain_id, domainName: 'Native home' });
    await fireEvent.submit(form); expect(modal()).toBeNull(); expect(mocks.delete).not.toHaveBeenCalled();
  });

  it('never opens deletion after administrator authority is lost', async () => {
    renderPage(); await loaded(); const action = deleteAction();
    auth.set({ ...initialAuth, isSystemAdmin: false }); await tick();
    expect((action as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(action); expect(modal()).toBeNull(); expect(mocks.delete).not.toHaveBeenCalled();
  });

  const transitions = ['userId', 'sessionId', 'identityDomainId', 'domainId', 'projectId', 'isSystemAdmin', 'ready', 'switching', 'logout'] as const;
  function crossBoundary(kind: typeof transitions[number]) {
    if (kind === 'ready') { authReady.set(false); authReady.set(true); }
    else if (kind === 'switching') { projectSwitching.set(true); projectSwitching.set(false); }
    else if (kind === 'logout') { logoutInProgress.set(true); logoutInProgress.set(false); }
    else { auth.set({ ...initialAuth, [kind]: kind === 'isSystemAdmin' ? false : 'replacement' }); auth.set({ ...initialAuth }); }
  }

  it.each(transitions)('invalidates typed confirmation on %s ABA without a DELETE', async kind => {
    renderPage(); await loaded(); await open();
    await fireEvent.input(within(modal()!).getByRole('textbox'), { target: { value: alice.id } });
    const staleForm = within(modal()!).getByRole('textbox').closest('form')!;
    crossBoundary(kind); await tick(); await fireEvent.submit(staleForm);
    expect(modal()).toBeNull(); expect(mocks.delete).not.toHaveBeenCalled();
  });

  it.each(transitions)('does not publish late DELETE success after %s ABA', async kind => {
    const pending = Promise.withResolvers<void>(); mocks.delete.mockReturnValueOnce(pending.promise);
    renderPage(); await loaded(); await open(); await confirm();
    const reads = mocks.get.mock.calls.length;
    crossBoundary(kind); await tick(); pending.resolve(); await tick();
    expect(modal()).toBeNull(); expect(mocks.get).toHaveBeenCalledTimes(reads);
    expect(deleteAction()).toBeTruthy();
  });

  it('fences the selected native domain and its ABA transitions', async () => {
    const pending = Promise.withResolvers<void>(); mocks.delete.mockReturnValueOnce(pending.promise);
    const view = renderPage(); await loaded(); await open(); await confirm();
    const reads = mocks.get.mock.calls.length;
    await view.rerender({ domainId: 'foreign-home', domainName: 'Foreign' });
    await view.rerender({ domainId: alice.domain_id, domainName: 'Native home' });
    pending.resolve(); await tick(); expect(modal()).toBeNull(); expect(mocks.get).toHaveBeenCalledTimes(reads);
  });

  it('drops a stale directory reread after owner ABA rather than opening a confirmation', async () => {
    renderPage(); await loaded();
    const pending = Promise.withResolvers<{ items: User[]; next_marker: null }>();
    mocks.get.mockReturnValueOnce(pending.promise);
    await fireEvent.click(deleteAction()); crossBoundary('sessionId');
    pending.resolve({ items: [alice], next_marker: null }); await tick();
    expect(modal()).toBeNull(); expect(mocks.delete).not.toHaveBeenCalled();
  });

  it('ignores late success after unmount and never refreshes the next page', async () => {
    const pending = Promise.withResolvers<void>(); mocks.delete.mockReturnValueOnce(pending.promise);
    const view = renderPage(); await loaded(); await open(); await confirm();
    const reads = mocks.get.mock.calls.length; view.unmount(); pending.resolve(); await tick();
    expect(mocks.get).toHaveBeenCalledTimes(reads);
  });

  it('clamps the last page after deleting its last user', async () => {
    inventory = Array.from({ length: 20 }, (_, index) => ({ ...bob, id: `row-${index}`, name: `A-${String(index).padStart(2, '0')}` }));
    inventory.push({ ...alice, name: 'Z-last' });
    renderPage(); await screen.findByRole('button', { name: t('userDelete.actionLabel', { name: 'A-00' }) });
    await fireEvent.click(screen.getByRole('button', { name: /Next/ }));
    await open('Z-last'); await confirm(); await waitFor(() => expect(modal()).toBeNull());
    expect(screen.getByRole('button', { name: t('userDelete.actionLabel', { name: 'A-00' }) })).toBeTruthy();
    expect(screen.queryByRole('button', { name: t('userDelete.actionLabel', { name: 'Z-last' }) })).toBeNull();
  });
});
