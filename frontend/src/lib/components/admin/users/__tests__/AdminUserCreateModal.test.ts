import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import AdminUserCreateModal from '../AdminUserCreateModal.svelte';

beforeEach(() => initLocale('en'));
afterEach(() => { cleanup(); initLocale('ko'); });

describe('domain-selected user creation', () => {

  it('discards a password and errors when the dialog closes, ignoring an old submission', async () => {
    const { promise, resolve } = Promise.withResolvers<string | { identity_domain_id: string; identity_domain_name: string }>();
    const create = vi.fn(() => promise);
    const view = render(AdminUserCreateModal, { open: true, domainId: 'tenant-a', domainName: 'Research', onCreate: create });
    const password = screen.getByLabelText(/^Password/);
    await fireEvent.input(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'alice' } });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Personal identity domain name' }), { target: { value: 'Personal' } });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Email' }), { target: { value: 'alice@example.com' } });
    await fireEvent.input(password, { target: { value: 'not-persisted-secret' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ name: 'alice', password: 'not-persisted-secret' }));
    await view.rerender({ open: false, domainId: 'tenant-a', domainName: 'Research', onCreate: create });
    await view.rerender({ open: true, domainId: 'tenant-a', domainName: 'Research', onCreate: create });
    resolve('Old domain error');
    await tick();
    expect(document.querySelector<HTMLInputElement>('input[type="password"]')?.value).toBe('');
    expect(screen.queryByText('Old domain error')).toBeNull();
  });

  it('requires a personal domain and presents returned immutable identity separately from the joined target', async () => {
    const create = vi.fn().mockResolvedValue({ identity_domain_id: 'personal-id', identity_domain_name: 'Personal' });
    render(AdminUserCreateModal, { open: true, domainId: 'tenant-a', domainName: 'Research', onCreate: create });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'alice' } });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Email' }), { target: { value: 'alice@example.com' } });
    await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: 'not-persisted-secret' } });
    expect((screen.getByRole('button', { name: 'Create' }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.input(screen.getByRole('textbox', { name: 'Personal identity domain name' }), { target: { value: 'Personal' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(create).toHaveBeenCalledWith({ name: 'alice', email: 'alice@example.com', password: 'not-persisted-secret', personal_domain_name: 'Personal', enabled: true });
    expect(await screen.findByText('personal-id')).toBeTruthy();
    expect(screen.getByText('Personal')).toBeTruthy();
    expect(screen.getByText('Joined working domain')).toBeTruthy();
    expect(screen.queryByLabelText(/^Password/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Close' })).toBeTruthy();
  });
});
