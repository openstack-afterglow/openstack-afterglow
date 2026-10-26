import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';

import { ApiError } from '$lib/api/client';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'personal' }) }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn() } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: (callback: (force?: boolean) => Promise<void>) => ({ active: false, intervalSeconds: 15, intervalOptions: [15], refresh: () => callback(true) }) }));

import Panel from '../LoadBalancerDetailPanel.svelte';
let owner: string;
let base: string;
beforeEach(() => {
  vi.clearAllMocks(); owner = 'foreign'; base = '/api/v1/admin/loadbalancers/lb';
  mocks.post.mockResolvedValue({}); mocks.confirm.mockResolvedValue(true);
  mocks.get.mockImplementation((path: string) => {
    if (path === base) return Promise.resolve({ id: 'lb', name: 'Foreign LB', status: 'ERROR', project_id: owner });
    if (path === `${base}/listeners`) return Promise.resolve([{ id: 'listener', name: 'listener', protocol: 'HTTP', protocol_port: 80 }]);
    if (path === `${base}/pools`) return Promise.resolve([{ id: 'pool', name: 'pool', protocol: 'HTTP', lb_algorithm: 'ROUND_ROBIN' }]);
    if (path === `${base}/pools/pool/members`) return Promise.resolve([{ id: 'member', address: '10.0.0.1', protocol_port: 80, weight: 1 }]);
    if (path === `${base}/status`) return Promise.resolve({ id: 'lb', name: 'LB', listeners: [] });
    return Promise.reject(new Error(`Unexpected read: ${path}`));
  });
});

describe('loadbalancer administrator read transport', () => {
  it('reads foreign parent, child collections and status as admin without advertising consumer writes', async () => {
    render(Panel, { props: { lbId: 'lb', isAdmin: true } });
    await screen.findByText('Foreign LB');
    await screen.findByText('listener');
    expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
    expect(screen.queryByRole('button', { name: '+ 추가' })).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: '▼ 멤버' }));
    await screen.findByText('10.0.0.1:80');
    expect(mocks.get).toHaveBeenCalledWith(`${base}/pools/pool/members`, 'token', 'personal');
    expect(mocks.get).toHaveBeenCalledWith(`${base}/status`, 'token', 'personal', { refresh: false });
    expect(mocks.get.mock.calls.every(call => String(call[0]).startsWith('/api/v1/admin/'))).toBe(true);
    expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.delete).not.toHaveBeenCalled();
  });

  it('routes manual detail refresh through forced parent, children and status reads', async () => {
    render(Panel, { props: { lbId: 'lb', isAdmin: true } });
    await screen.findByText('Foreign LB');
    await screen.findByText('listener');
    await fireEvent.click(screen.getByTitle('지금 새로고침'));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith(`${base}/status`, 'token', 'personal', { refresh: true }));
    for (const path of [base, `${base}/listeners`, `${base}/pools`]) {
      expect(mocks.get).toHaveBeenCalledWith(path, 'token', 'personal', { refresh: true });
    }
  });

  it('displays member read denial instead of claiming the pool has no members', async () => {
    const get = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation((path: string) => path.endsWith('/members')
      ? Promise.reject(new ApiError(502, 'member lookup unavailable')) : get(path));
    render(Panel, { props: { lbId: 'lb', isAdmin: true } });
    await screen.findByText('listener');
    await fireEvent.click(screen.getByRole('button', { name: '▼ 멤버' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText('멤버가 없습니다.')).toBeNull();
  });

  it('keeps consumer reads unchanged outside administrator mode', async () => {
    base = '/api/v1/loadbalancers/lb'; owner = 'personal';
    render(Panel, { props: { lbId: 'lb' } });
    await screen.findByText('listener');
    expect(mocks.get.mock.calls.every(call => String(call[0]).startsWith('/api/v1/loadbalancers/'))).toBe(true);
    expect(screen.getAllByRole('button', { name: '삭제' }).length).toBeGreaterThan(0);
  });

  it('same-project administrator listener creation uses native caller write then administrator refresh', async () => {
    owner = 'personal';
    render(Panel, { props: { lbId: 'lb', isAdmin: true } });
    await screen.findByText('listener');
    const add = screen.getAllByRole('button', { name: '+ 추가' });
    await fireEvent.click(add[0]);
    const submit = screen.getByRole('button', { name: '생성' });
    await fireEvent.click(submit);
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/v1/loadbalancers/lb/listeners', expect.any(Object), 'token', 'personal'));
    expect(mocks.get.mock.calls.every(call => String(call[0]).startsWith('/api/v1/admin/'))).toBe(true);
  });
});
