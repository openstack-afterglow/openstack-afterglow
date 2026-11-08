import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import AdminUserCreateModal from '../AdminUserCreateModal.svelte';
import type { DomainAccountResult } from '$lib/types/auth';

beforeEach(() => initLocale('en'));
afterEach(() => { cleanup(); initLocale('ko'); });

describe('admin account creation from a selected directory', () => {

  it('discards a password and errors when the dialog closes, ignoring an old submission', async () => {
    const { promise, resolve } = Promise.withResolvers<string | DomainAccountResult>();
    const create = vi.fn(() => promise);
    const view = render(AdminUserCreateModal, { open: true, domainId: 'tenant-a', onCreate: create });
    const password = screen.getByLabelText(/^Password/);
    await fireEvent.input(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'alice' } });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Email' }), { target: { value: 'alice@example.com' } });
    await fireEvent.input(password, { target: { value: 'not-persisted-secret' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ name: 'alice', password: 'not-persisted-secret' }));
    await view.rerender({ open: false, domainId: 'tenant-a', onCreate: create });
    await view.rerender({ open: true, domainId: 'tenant-a', onCreate: create });
    resolve('Old domain error');
    await tick();
    expect(document.querySelector<HTMLInputElement>('input[type="password"]')?.value).toBe('');
    expect(screen.queryByText('Old domain error')).toBeNull();
  });

  it('presents the accepted identity and deferred first-login project without admitting the selected directory domain', async () => {
    const result: DomainAccountResult = { user_id: 'alice-id', domain_id: 'accounts-id', domain_name: 'Accounts', identity_domain_id: 'accounts-id', identity_domain_name: 'Accounts', personal_domain_id: 'personal-id', personal_project_id: null, personal_project_name: 'alice-abcdefgh12345678', personal_project_deferred: true };
    const create = vi.fn().mockResolvedValue(result);
    render(AdminUserCreateModal, { open: true, domainId: 'tenant-a', onCreate: create });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'alice' } });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Email' }), { target: { value: 'alice@example.com' } });
    await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: 'not-persisted-secret' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(create).toHaveBeenCalledWith({ name: 'alice', email: 'alice@example.com', password: 'not-persisted-secret', enabled: true });
    expect(await screen.findByText('Not created yet. Prepared at the first successful sign-in.')).toBeTruthy();
    for (const value of [result.user_id, result.personal_domain_id!]) expect(screen.getByText(value)).toBeTruthy();
    expect(screen.getAllByText(result.identity_domain_id)).toHaveLength(1);
    expect(screen.queryByText(result.personal_project_name!)).toBeNull();
    expect(screen.queryByText('tenant-a')).toBeNull();
    expect(document.querySelectorAll('dl > div')).toHaveLength(3);
    expect(screen.queryByLabelText(/^Password/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Close' })).toBeTruthy();
  });

  it('marks the tutorial submit only for a sendable form and submits Enter as a click on Create', async () => {
    const create = vi.fn().mockResolvedValue('Synthetic denial');
    const marked = () => document.querySelector('[data-tour="admin-users-create-submit"]');
    render(AdminUserCreateModal, { open: true, domainId: 'tenant-a', onCreate: create });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'tut-user' } });
    await fireEvent.input(screen.getByRole('textbox', { name: 'Email' }), { target: { value: 'tut-user@example.test' } });
    await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: 'too-short' } });
    expect(marked()).toBeNull();
    await fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: 'practice-pass-1' } });
    expect(marked()).not.toBeNull();
    // Same shape as the tour engine's capture-phase guard for a later click step.
    const guard = (event: Event) => {
      if (event.target instanceof Element && event.target.closest('[data-tour="admin-users-create-submit"]')) { event.preventDefault(); event.stopPropagation(); }
    };
    const form = document.querySelector('[data-tour="admin-users-create-fields"]') as HTMLFormElement;
    document.addEventListener('click', guard, { capture: true });
    try {
      await fireEvent.submit(form);
      expect(create).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener('click', guard, { capture: true });
    }
    await fireEvent.submit(form);
    expect(create).toHaveBeenCalledOnce();
  });
});
