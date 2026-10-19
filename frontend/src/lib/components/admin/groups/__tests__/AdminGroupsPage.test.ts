import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import { ApiError } from '$lib/api/client';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { constructor(_status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'admin-project' }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [30, 60] }) }));
import Page from '../AdminGroupsPage.svelte';

const group = { id: 'g1', name: 'Domain A group', description: '', domain_id: 'domain-a', created_at: null };
const member = { id: 'u1', name: 'Current member', email: '', enabled: true };
beforeEach(() => {
  vi.resetAllMocks();
  mocks.get.mockImplementation((path: string) => {
    if (path === '/api/v1/admin/groups?domain_id=domain-a') return Promise.resolve([group]);
    if (path === '/api/v1/admin/groups/g1/users?domain_id=domain-a') return Promise.resolve([member]);
    if (path === '/api/v1/admin/domains/domain-a/members') return Promise.resolve({ domain_id: 'domain-a', items: [{ id: 'u2', name: 'New member', domain_id: 'personal-home' }] });
    throw new Error(`Unexpected path: ${path}`);
  });
});
afterEach(cleanup);

describe('domain-scoped group administration', () => {
  it('adds joined foreign-home users without widening the home credential directory', async () => {
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await screen.findByText('Domain A group');
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText('Current member');
    mocks.delete.mockRejectedValueOnce(new ApiError(403, 'identity_native_denied'));
    await fireEvent.click(screen.getByRole('button', { name: '제거' }));
    expect(await screen.findByText('identity_native_denied')).toBeTruthy();
    expect(mocks.delete).toHaveBeenCalledWith('/api/v1/admin/groups/g1/users/u1?domain_id=domain-a', 'token', 'admin-project');
    await fireEvent.input(screen.getByRole('textbox', { name: '사용자 검색' }), { target: { value: 'New' } });
    await fireEvent.click(screen.getByRole('button', { name: '추가' }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/api/v1/admin/groups/g1/users/u2?domain_id=domain-a', {}, 'token', 'admin-project'));
  });

  it('does not publish foreign group inventory', async () => {
    mocks.get.mockResolvedValue([{ ...group, domain_id: 'domain-b' }]);
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('Domain A group')).toBeNull();
  });

  it('shows membership and catalog denials rather than verified empty results', async () => {
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await screen.findByText('Domain A group');
    mocks.get.mockRejectedValue(new ApiError(403, 'identity_native_denied'));
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    expect(await screen.findByText('identity_native_denied')).toBeTruthy();
    expect(screen.queryByText('멤버가 없습니다')).toBeNull();
  });

  it('clears old-domain data and fences its late response after selection changes', async () => {
    const first = Promise.withResolvers<typeof group[]>();
    mocks.get.mockReturnValueOnce(first.promise);
    const view = render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await waitFor(() => expect(mocks.get).toHaveBeenCalledOnce());
    mocks.get.mockResolvedValue([{ ...group, id: 'g2', name: 'Domain B group', domain_id: 'domain-b' }]);
    await view.rerender({ domainId: 'domain-b', domainName: 'Domain B' });
    await screen.findByText('Domain B group');
    first.resolve([group]);
    await tick();
    expect(screen.queryByText('Domain A group')).toBeNull();
    expect(mocks.get.mock.calls[1][0]).toBe('/api/v1/admin/groups?domain_id=domain-b');
  });
});
