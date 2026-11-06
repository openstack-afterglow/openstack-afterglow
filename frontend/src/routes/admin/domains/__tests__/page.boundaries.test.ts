import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { tick } from 'svelte';

const mocks = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), update: vi.fn() }));
vi.mock('$lib/api/domains', () => ({ domainsApi: mocks }));
vi.mock('$lib/api/client', () => ({ api: { get: vi.fn() }, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/stores/auth', () => ({
  auth: writable({ token: 'token', sessionId: 'login-a', userId: 'actor', identityDomainId: 'accounts', domainId: 'working', projectId: 'project-a', isSystemAdmin: true, roles: ['admin'] }),
  authReady: writable(true), projectSwitching: writable(false),
}));

import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/domain-admin';
import { t as commonT } from '$lib/i18n/ns/common';
import Page from '../+page.svelte';

const domain = { id: 'domain-a', name: 'Domain A', description: '', enabled: true };
beforeEach(() => {
  vi.resetAllMocks();
  auth.update((state) => ({ ...state, token: 'token', sessionId: 'login-a', userId: 'actor', identityDomainId: 'accounts', domainId: 'working', projectId: 'project-a', isSystemAdmin: true, roles: ['admin'] }));
  authReady.set(true); projectSwitching.set(false);
  mocks.list.mockResolvedValue({ items: [domain] });
});
afterEach(cleanup);

it.each(['success', 'failure'] as const)('settles a pending domain write after bearer renewal without leaving the modal busy: %s', async (outcome) => {
  const pending = Promise.withResolvers<typeof domain>();
  mocks.create.mockReturnValueOnce(pending.promise);
  render(Page);
  await waitFor(() => expect(screen.getByRole('button', { name: t('inventory.create') })).toMatchObject({ disabled: false }));
  await fireEvent.click(screen.getByRole('button', { name: t('inventory.create') }));
  const dialog = screen.getByRole('dialog', { name: t('inventory.create') });
  await fireEvent.input(within(dialog).getByRole('textbox', { name: t('form.name') }), { target: { value: 'Created domain' } });
  await fireEvent.click(within(dialog).getByRole('button', { name: t('actions.save') }));
  expect(mocks.create).toHaveBeenCalledExactlyOnceWith({ name: 'Created domain', description: '', enabled: true }, { token: 'token', projectId: 'project-a' });
  auth.update((state) => ({ ...state, token: 'renewed-token' }));
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({ token: 'renewed-token', projectId: 'project-a' }));
  expect(screen.getByRole('dialog', { name: t('inventory.create') })).toBe(dialog);
  expect(within(dialog).getByRole('button', { name: t('actions.save') })).toMatchObject({ disabled: true });
  if (outcome === 'success') {
    mocks.list.mockResolvedValueOnce({ items: [domain, { ...domain, id: 'created', name: 'Created domain' }] });
    pending.resolve({ ...domain, id: 'created', name: 'Created domain' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(screen.getByRole('button', { name: t('inventory.create') })).toMatchObject({ disabled: false }));
    await fireEvent.click(screen.getByRole('button', { name: t('inventory.create') }));
    const fresh = within(screen.getByRole('dialog', { name: t('inventory.create') }));
    await fireEvent.input(fresh.getByRole('textbox', { name: t('form.name') }), { target: { value: 'Another domain' } });
    expect(fresh.getByRole('button', { name: t('actions.save') })).toMatchObject({ disabled: false });
  } else {
    pending.reject(new Error('native-write-rejected'));
    await within(dialog).findByText(t('inventory.failed'));
    expect(within(dialog).getByRole('button', { name: t('actions.save') })).toMatchObject({ disabled: false });
    expect(within(dialog).getByRole('textbox', { name: t('form.name') })).toMatchObject({ value: 'Created domain' });
  }
  await tick();
  expect(mocks.create).toHaveBeenCalledTimes(1);
});

it('retires a pending inventory read after a synchronous readiness loss/restoration', async () => {
  const pending = Promise.withResolvers<{ items: typeof domain[] }>();
  const fresh = { ...domain, id: 'fresh-domain', name: 'Fresh verified domain' };
  render(Page);
  await screen.findByText(domain.name);
  await fireEvent.input(screen.getByRole('searchbox', { name: commonT('table.search') }), { target: { value: '^Domain A$' } });
  mocks.list.mockReturnValueOnce(pending.promise);
  await fireEvent.click(screen.getByRole('button', { name: t('actions.refresh') }));
  mocks.list.mockResolvedValueOnce({ items: [fresh] });
  authReady.set(false); authReady.set(true);
  await screen.findByText(fresh.name);
  expect((screen.getByRole('searchbox', { name: commonT('table.search') }) as HTMLInputElement).value).toBe('');
  pending.resolve({ items: [{ ...domain, id: 'stale-domain', name: 'Stale private domain' }] });
  await tick(); await tick();
  expect(screen.queryByText('Stale private domain')).toBeNull();
  expect(screen.getByText(fresh.name)).toBeTruthy();
});

it('does not let a pre-readiness-loss save settle into or unlock a new modal write', async () => {
  const oldWrite = Promise.withResolvers<typeof domain>();
  const newWrite = Promise.withResolvers<typeof domain>();
  mocks.create.mockReturnValueOnce(oldWrite.promise).mockReturnValueOnce(newWrite.promise);
  render(Page);
  await waitFor(() => expect(screen.getByRole('button', { name: t('inventory.create') })).toMatchObject({ disabled: false }));
  await fireEvent.click(screen.getByRole('button', { name: t('inventory.create') }));
  let dialog = screen.getByRole('dialog', { name: t('inventory.create') });
  await fireEvent.input(within(dialog).getByRole('textbox', { name: t('form.name') }), { target: { value: 'Old pending domain' } });
  await fireEvent.click(within(dialog).getByRole('button', { name: t('actions.save') }));
  authReady.set(false); authReady.set(true);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  await waitFor(() => expect(screen.getByRole('button', { name: t('inventory.create') })).toMatchObject({ disabled: false }));
  await fireEvent.click(screen.getByRole('button', { name: t('inventory.create') }));
  dialog = screen.getByRole('dialog', { name: t('inventory.create') });
  await fireEvent.input(within(dialog).getByRole('textbox', { name: t('form.name') }), { target: { value: 'New pending domain' } });
  await fireEvent.click(within(dialog).getByRole('button', { name: t('actions.save') }));
  oldWrite.resolve({ ...domain, id: 'old-created', name: 'Old pending domain' });
  await tick(); await tick();
  expect(screen.getByRole('dialog', { name: t('inventory.create') })).toBe(dialog);
  expect(within(dialog).getByRole('button', { name: t('actions.save') })).toMatchObject({ disabled: true });
  expect(within(dialog).getByRole('textbox', { name: t('form.name') })).toMatchObject({ value: 'New pending domain' });
  expect(mocks.list).toHaveBeenCalledTimes(2);
  newWrite.reject(new Error('new-write-rejected'));
  await within(dialog).findByText(t('inventory.failed'));
  expect(within(dialog).getByRole('button', { name: t('actions.save') })).toMatchObject({ disabled: false });
  expect(mocks.create).toHaveBeenCalledTimes(2);
});
