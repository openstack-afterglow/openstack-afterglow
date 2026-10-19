import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/errors';
import DomainInventory from '../../../../routes/admin/domains/+page.svelte';
const mocks = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), update: vi.fn() }));
vi.mock('$lib/api/domains', () => ({ domainsApi: mocks }));
const initial = get(auth);
beforeEach(() => {
  vi.resetAllMocks(); initLocale('en'); projectSwitching.set(false);
  auth.set({ ...initial, token: 'system-token', userId: 'operator', projectId: 'operator-project', isSystemAdmin: true, domainId: 'operator-domain' });
  authReady.set(true);
  mocks.list.mockResolvedValue({ items: [{ id: 'tenant-a', name: 'Research', description: '', enabled: true }] });
  mocks.create.mockResolvedValue({ id: 'tenant-b', name: 'Second', description: '', enabled: true });
  mocks.update.mockResolvedValue({ id: 'tenant-a', name: 'Research', description: '', enabled: false });
});
afterEach(() => { cleanup(); auth.set(initial); authReady.set(false); projectSwitching.set(false); initLocale('ko'); });

describe('system domain inventory', () => {
  it('creates a native domain only after explicit submission', async () => {
    render(DomainInventory);
    await screen.findByText('Research');
    expect(mocks.create).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole('button', { name: 'Create domain' }));
    await fireEvent.input(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Second' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({ name: 'Second', description: '', enabled: true }, { token: 'system-token', projectId: 'operator-project' }));
  });
  it('edits the exact domain including its enabled state, without moving existing users', async () => {
    render(DomainInventory); await screen.findByText('Research');
    await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await fireEvent.click(screen.getByRole('checkbox', { name: 'Enable domain' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith('tenant-a', { name: 'Research', description: '', enabled: false }, { token: 'system-token', projectId: 'operator-project' }));
    expect(mocks.create).not.toHaveBeenCalled();
  });
  it('shows native inventory denial rather than an empty successful inventory', async () => {
    mocks.list.mockRejectedValue(new ApiError(403, 'domain_native_denied'));
    render(DomainInventory);
    await screen.findByText('domain_native_denied');
    expect(screen.queryByText('No domains found.')).toBeNull();
    expect(get(auth).isSystemAdmin).toBe(true);
  });
});
