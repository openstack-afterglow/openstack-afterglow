import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-identity';
import type { User } from '$lib/types/common';
import AdminUserDeleteModal from '../AdminUserDeleteModal.svelte';

const user: User & { domain_id: string } = { id: 'a718fbcb-a609-4d3a-986a-9e7d50840b69', name: 'Alice', email: 'alice@example.test', enabled: true, domain_id: 'native-home', default_project_id: null, created_at: null };
const props = { user, domainId: user.domain_id, domainName: 'Native home display name' };
const field = () => screen.getByRole('textbox', { name: t('userDelete.confirmId') });
const submit = () => screen.getByRole('button', { name: 'Delete' }) as HTMLButtonElement;
beforeEach(() => initLocale('en'));
afterEach(() => { cleanup(); initLocale('ko'); });

describe('AdminUserDeleteModal exact identity confirmation', () => {
  it('shows full native identity and irreversible account scope, and cancellation never writes', async () => {
    const onDelete = vi.fn(); const onClose = vi.fn();
    render(AdminUserDeleteModal, { ...props, onDelete, onClose });
    expect(screen.getByRole('dialog', { name: 'Delete user account' })).toBeTruthy();
    for (const value of [user.name, user.id, user.domain_id, props.domainName, t('userDelete.warning')]) expect(screen.getByText(value)).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledOnce(); expect(onDelete).not.toHaveBeenCalled();
  });

  it('requires the full exact ID, rejects form submission bypass, and coalesces duplicate clicks', async () => {
    const pending = Promise.withResolvers<true>(); const onDelete = vi.fn(() => pending.promise); const onClose = vi.fn();
    render(AdminUserDeleteModal, { ...props, onDelete, onClose });
    for (const value of ['', user.id.slice(0, 8), ` ${user.id}`, user.id.toUpperCase()]) {
      await fireEvent.input(field(), { target: { value } });
      expect(submit().disabled).toBe(true);
      await fireEvent.submit(field().closest('form')!);
      expect(onDelete).not.toHaveBeenCalled();
    }
    await fireEvent.input(field(), { target: { value: user.id } });
    await fireEvent.click(submit()); await fireEvent.submit(field().closest('form')!);
    expect(onDelete).toHaveBeenCalledExactlyOnceWith(user.id, user.id);
    expect((field() as HTMLInputElement).disabled).toBe(true);
    pending.resolve(true); await tick();
    expect(onClose).toHaveBeenCalledOnce(); await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('keeps the account and denial visible, without treating an error as success', async () => {
    const onDelete = vi.fn().mockResolvedValue({ error: 'Native account not found', rereadRequired: false }); const onClose = vi.fn();
    render(AdminUserDeleteModal, { ...props, onDelete, onClose });
    await fireEvent.input(field(), { target: { value: user.id } }); await fireEvent.click(submit());
    expect(await screen.findByText('Native account not found')).toBeTruthy();
    expect(screen.getByText(user.id)).toBeTruthy(); expect(onClose).not.toHaveBeenCalled();
  });

  it('requires closing and rereading after an uncertain response; no blind retry exists', async () => {
    const onDelete = vi.fn().mockResolvedValue({ error: 'Native timeout', rereadRequired: true });
    render(AdminUserDeleteModal, { ...props, onDelete, onClose: vi.fn() });
    await fireEvent.input(field(), { target: { value: user.id } }); await fireEvent.click(submit());
    expect(await screen.findByText('Native timeout')).toBeTruthy();
    expect(screen.getByText(t('userDelete.rereadRequired'))).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
    await fireEvent.submit(field().closest('form')!); expect(onDelete).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'Close' })).toBeTruthy();
  });

  it('rejects a foreign home and discards typed confirmation when the target changes', async () => {
    const onDelete = vi.fn(); const onClose = vi.fn();
    const view = render(AdminUserDeleteModal, { ...props, domainId: 'foreign-home', onDelete, onClose });
    await fireEvent.input(field(), { target: { value: user.id } }); await fireEvent.submit(field().closest('form')!);
    expect(onDelete).not.toHaveBeenCalled();
    await view.rerender({ ...props, onDelete, onClose });
    expect((field() as HTMLInputElement).value).toBe('');
    expect(submit().disabled).toBe(true);
  });

  it('ignores late results after target changes', async () => {
    const pending = Promise.withResolvers<true>(); const onDelete = vi.fn(() => pending.promise); const onClose = vi.fn();
    const view = render(AdminUserDeleteModal, { ...props, onDelete, onClose });
    await fireEvent.input(field(), { target: { value: user.id } }); await fireEvent.click(submit());
    await view.rerender({ ...props, user: { ...user, id: 'another-id', name: 'Bob' }, onDelete, onClose });
    pending.resolve(true); await tick(); expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText('Bob')).toBeTruthy(); view.unmount();
  });

});
