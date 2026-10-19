import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import UserDomainManagers from '../UserDomainManagers.svelte';
const mocks = vi.hoisted(() => ({ managers: vi.fn(), grantManager: vi.fn(), revokeManager: vi.fn() }));
vi.mock('$lib/api/domains', () => ({ domainsApi: mocks }));
const roles = [{ id: 'native-manager', name: 'manager', grantable: true }, { id: 'native-admin', name: 'admin', grantable: false }];

beforeEach(() => {
  vi.resetAllMocks();
  initLocale('en');
  auth.update(state => ({ ...state, token: 'system-token', projectId: 'operator-project', isSystemAdmin: true }));
  mocks.managers.mockResolvedValue({ items: [], roles });
  mocks.grantManager.mockResolvedValue({ items: [], roles });
  mocks.revokeManager.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); initLocale('ko'); });

describe('native domain manager bootstrap', () => {
  it('requires an explicit native role choice before granting in the selected user domain', async () => {
    const changed = vi.fn();
    render(UserDomainManagers, { userId: 'alice', domainId: 'tenant-a', onChanged: changed });
    await screen.findByText('No direct domain manager roles. Inspect group/inherited authority in the permissions list above.');
    const grant = screen.getByRole('button', { name: 'Grant role' });
    expect((grant as HTMLButtonElement).disabled).toBe(true);
    expect(mocks.grantManager).not.toHaveBeenCalled();
    await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'native-manager' } });
    await fireEvent.click(grant);
    await waitFor(() => expect(changed).toHaveBeenCalledOnce());
    expect(mocks.grantManager).toHaveBeenCalledWith('tenant-a', 'alice', 'native-manager', { token: 'system-token', projectId: 'operator-project' });
  });

  it('does not publish an old domain grant result after user/domain changes', async () => {
    const { promise, resolve } = Promise.withResolvers<unknown>();
    mocks.grantManager.mockReturnValue(promise);
    const changed = vi.fn();
    const view = render(UserDomainManagers, { userId: 'alice', domainId: 'tenant-a', onChanged: changed });
    await screen.findByRole('combobox');
    await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'native-manager' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Grant role' }));
    await view.rerender({ userId: 'bob', domainId: 'tenant-b', onChanged: changed });
    resolve({ items: [{ user_id: 'alice', role_id: 'native-manager', role_name: 'manager' }], roles });
    await tick();
    expect(changed).not.toHaveBeenCalled();
    expect(mocks.managers).toHaveBeenLastCalledWith('tenant-b', { token: 'system-token', projectId: 'operator-project' });
  });
});
