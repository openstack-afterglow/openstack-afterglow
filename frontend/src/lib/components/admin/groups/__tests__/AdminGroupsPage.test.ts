import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import { ApiError } from '$lib/api/client';
import { auth } from '$lib/stores/auth';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), listDomains: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { constructor(_status: number, message: string) { super(message); } } }));
vi.mock('$lib/api/domains', () => ({ domainsApi: { list: mocks.listDomains } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'admin-project', userId: 'actor' }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [30, 60] }) }));
import Page from '../AdminGroupsPage.svelte';

const group = { id: 'g1', name: 'Domain A group', description: '', domain_id: 'domain-a', created_at: null };
const member = { id: 'u1', name: 'Current member', email: 'current@example.test', enabled: true, domain_id: 'home-current', identity_read_only: true };
const candidate = { id: 'a1111111-1111-4111-8111-111111111111', name: 'New member', email: 'new@example.test', enabled: true, domain_id: 'personal-home' };
beforeEach(() => {
  vi.resetAllMocks();
  auth.update((value) => ({ ...value, token: 'token', projectId: 'admin-project', userId: 'actor' }));
  mocks.listDomains.mockResolvedValue({ items: [
    { id: 'domain-a', name: 'Domain A', enabled: true },
    { id: 'accounts', name: 'Accounts', enabled: true },
    { id: 'research-home', name: 'Research', enabled: true },
    { id: 'disabled', name: 'Disabled', enabled: false },
  ] });
  mocks.get.mockImplementation((path: string) => {
    if (path === '/api/v1/admin/groups?domain_id=domain-a') return Promise.resolve([group]);
    if (path === '/api/v1/admin/groups/g1/users?domain_id=domain-a') return Promise.resolve([member]);
    if (path === '/api/v1/admin/domains/domain-a/members') return Promise.resolve({ domain_id: 'domain-a', items: [candidate] });
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
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'New' } });
    await fireEvent.click(screen.getByRole('button', { name: '추가' }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith(`/api/v1/admin/groups/g1/users/${candidate.id}?domain_id=domain-a`, {}, 'token', 'admin-project'));
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

  it('preserves verified members while directory loading and denial stay distinct from no matches, then retries the exact scope', async () => {
    const directory = Promise.withResolvers<{ domain_id: string; items: typeof candidate[] }>();
    mocks.get.mockImplementation((path: string) => {
      if (path === '/api/v1/admin/groups?domain_id=domain-a') return Promise.resolve([group]);
      if (path === '/api/v1/admin/groups/g1/users?domain_id=domain-a') return Promise.resolve([member]);
      if (path === '/api/v1/admin/domains/domain-a/members') return directory.promise;
      throw new Error(`Unexpected path: ${path}`);
    });
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await screen.findByText(group.name);
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText(member.email);
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'New' } });
    expect(screen.getByText('추가 가능한 사용자 확인 중...')).toBeTruthy();
    expect(screen.queryByText('일치하는 사용자가 없습니다')).toBeNull();
    expect(screen.queryByRole('button', { name: '추가' })).toBeNull();
    directory.reject(new ApiError(403, 'identity_native_denied'));
    await screen.findByText('identity_native_denied');
    expect(screen.getByText(member.id)).toBeTruthy();
    expect(screen.queryByText('일치하는 사용자가 없습니다')).toBeNull();
    mocks.get.mockResolvedValueOnce({ domain_id: 'domain-a', items: [candidate] });
    await fireEvent.click(screen.getByRole('button', { name: '사용자 목록 다시 조회' }));
    await screen.findByText(candidate.email);
    expect(mocks.get).toHaveBeenLastCalledWith('/api/v1/admin/domains/domain-a/members', 'token', 'admin-project', { refresh: true });
    await fireEvent.click(screen.getByRole('button', { name: '추가' }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith(`/api/v1/admin/groups/g1/users/${candidate.id}?domain_id=domain-a`, {}, 'token', 'admin-project'));
  });

  it('uses full user UUID rather than duplicate names for candidate selection and member exclusion', async () => {
    const sameNameMember = { ...member, name: 'pieroot' };
    const sameNameCandidate = { ...candidate, name: 'pieroot' };
    mocks.get.mockImplementation((path: string) => {
      if (path === '/api/v1/admin/groups?domain_id=domain-a') return Promise.resolve([group]);
      if (path === '/api/v1/admin/groups/g1/users?domain_id=domain-a') return Promise.resolve([sameNameMember]);
      if (path === '/api/v1/admin/domains/domain-a/members') return Promise.resolve({ domain_id: 'domain-a', items: [sameNameMember, sameNameCandidate] });
      throw new Error(`Unexpected path: ${path}`);
    });
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await screen.findByText(group.name);
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText(member.email);
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: '  PIEROOT  ' } });
    expect(screen.getAllByText('pieroot')).toHaveLength(2);
    expect(screen.getByText(candidate.email)).toBeTruthy();
    expect(screen.getByText(candidate.domain_id)).toBeTruthy();
    expect(screen.getAllByRole('button', { name: '추가' })).toHaveLength(1);
    await fireEvent.click(within(screen.getByText(candidate.id).closest('li')!).getByRole('button', { name: '추가' }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith(`/api/v1/admin/groups/g1/users/${candidate.id}?domain_id=domain-a`, {}, 'token', 'admin-project'));
  });

  it('discards late directory success after a domain ABA transition and keeps the new lookup failure non-actionable', async () => {
    const oldDirectory = Promise.withResolvers<{ domain_id: string; items: typeof candidate[] }>();
    let directoryCalls = 0;
    mocks.get.mockImplementation((path: string) => {
      if (path === '/api/v1/admin/groups?domain_id=domain-a') return Promise.resolve([group]);
      if (path === '/api/v1/admin/groups?domain_id=domain-b') return Promise.resolve([{ ...group, id: 'g2', name: 'Domain B group', domain_id: 'domain-b' }]);
      if (path === '/api/v1/admin/groups/g1/users?domain_id=domain-a') return Promise.resolve([member]);
      if (path === '/api/v1/admin/domains/domain-a/members') return ++directoryCalls === 1 ? oldDirectory.promise : Promise.reject(new ApiError(403, 'new_directory_denied'));
      throw new Error(`Unexpected path: ${path}`);
    });
    const view = render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await screen.findByText(group.name);
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText(member.email);
    await view.rerender({ domainId: 'domain-b', domainName: 'Domain B' });
    await screen.findByText('Domain B group');
    await view.rerender({ domainId: 'domain-a', domainName: 'Domain A' });
    await screen.findByText(group.name);
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText('new_directory_denied');
    oldDirectory.resolve({ domain_id: 'domain-a', items: [candidate] });
    await tick();
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'New' } });
    expect(screen.getByText('new_directory_denied')).toBeTruthy();
    expect(screen.queryByText(candidate.id)).toBeNull();
    expect(screen.queryByRole('button', { name: '추가' })).toBeNull();
    expect(screen.queryByText('일치하는 사용자가 없습니다')).toBeNull();
    expect(mocks.put).not.toHaveBeenCalled();
  });


  it('clears a successful candidate directory before reloading and keeps it unusable after the new lookup fails', async () => {
    render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
    await screen.findByText(group.name);
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText(member.email);
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'New' } });
    await screen.findByText(candidate.id);
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    const directory = Promise.withResolvers<{ domain_id: string; items: typeof candidate[] }>();
    mocks.get.mockImplementation((path: string) => {
      if (path === '/api/v1/admin/groups/g1/users?domain_id=domain-a') return Promise.resolve([member]);
      if (path === '/api/v1/admin/domains/domain-a/members') return directory.promise;
      throw new Error(`Unexpected path: ${path}`);
    });
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText('추가 가능한 사용자 확인 중...');
    expect(screen.queryByText(candidate.id)).toBeNull();
    expect(screen.queryByRole('button', { name: '추가' })).toBeNull();
    directory.reject(new ApiError(403, 'directory_refresh_denied'));
    await screen.findByText('directory_refresh_denied');
    expect(screen.getByText(member.email)).toBeTruthy();
    expect(screen.queryByText(candidate.id)).toBeNull();
    expect(screen.queryByRole('button', { name: '추가' })).toBeNull();
    expect(screen.queryByText('일치하는 사용자가 없습니다')).toBeNull();
    expect(mocks.put).not.toHaveBeenCalled();
  });
});

const sourcePath = '/api/v1/admin/groups/g1/candidates?domain_id=domain-a&user_domain_id=accounts';
const account = { ...candidate, name: 'pieroot', email: 'account@example.test', domain_id: 'accounts' };
async function chooseSource(name: string) {
  await fireEvent.click(screen.getByRole('button', { name: '계정 홈 도메인' }));
  await fireEvent.click(await screen.findByRole('option', { name }));
}
async function openGroup() {
  render(Page, { domainId: 'domain-a', domainName: 'Domain A' });
  await screen.findByText(group.name);
  await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
  await screen.findByText(member.email);
  await waitFor(() => expect((screen.getByRole('button', { name: '계정 홈 도메인' }) as HTMLButtonElement).disabled).toBe(false));
}

describe('explicit account home candidates', () => {
  it('keeps default lookup unchanged and offers only enabled foreign native homes, never a global source', async () => {
    await openGroup();
    expect(mocks.get.mock.calls.some(([path]) => path.includes('/candidates'))).toBe(false);
    expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/domains/domain-a/members', 'token', 'admin-project', { refresh: true });
    await fireEvent.click(screen.getByRole('button', { name: '계정 홈 도메인' }));
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(screen.getByRole('option', { name: 'Accounts accounts' })).toBeTruthy();
    expect(screen.getByRole('option', { name: 'Research research-home' })).toBeTruthy();
    expect(screen.queryByRole('option', { name: /Disabled|전체|All/ })).toBeNull();
    await fireEvent.click(screen.getByRole('option', { name: '현재 도메인 및 가입한 계정 domain-a' }));
    expect(mocks.get.mock.calls.some(([path]) => path.includes('/candidates'))).toBe(false);
    expect(mocks.listDomains).toHaveBeenCalledOnce();
  });

  it('selects a not-yet-joined Accounts UUID by name, email and full ID and adds it without changing scope', async () => {
    const second = { ...account, id: 'b2222222-2222-4222-8222-222222222222', email: 'second@example.test' };
    const original = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation((path: string) => path === sourcePath
      ? Promise.resolve({ domain_id: 'domain-a', user_domain_id: 'accounts', items: [account, second] }) : original(path));
    await openGroup();
    await chooseSource('Accounts accounts');
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: '  PIEROOT  ' } });
    await screen.findByText(second.id);
    expect(screen.getAllByText('pieroot')).toHaveLength(2);
    for (const query of [' SECOND@EXAMPLE.TEST ', second.id.toUpperCase()]) {
      await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: query } });
      expect(screen.queryByText(account.id)).toBeNull();
      expect(screen.getByText(second.id)).toBeTruthy();
    }
    await fireEvent.click(within(screen.getByText(second.id).closest('li')!).getByRole('button', { name: '추가' }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledExactlyOnceWith(`/api/v1/admin/groups/g1/users/${second.id}?domain_id=domain-a&user_domain_id=accounts`, {}, 'token', 'admin-project'));
    expect(screen.getByText(group.name)).toBeTruthy();
    expect(mocks.get.mock.calls.filter(([path]) => path.startsWith('/api/v1/admin/groups?'))).toEqual([['/api/v1/admin/groups?domain_id=domain-a', 'token', 'admin-project']]);
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.patch).not.toHaveBeenCalled();
  });

  it.each(['success', 'error'])('fences late source ABA %s and clears candidates immediately', async (outcome) => {
    const old = Promise.withResolvers<unknown>();
    let accountsCalls = 0;
    const original = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation((path: string) => {
      if (path === sourcePath) return ++accountsCalls === 1 ? old.promise : Promise.resolve({ domain_id: 'domain-a', user_domain_id: 'accounts', items: [account] });
      if (path.includes('user_domain_id=research-home')) return Promise.resolve({ domain_id: 'domain-a', user_domain_id: 'research-home', items: [] });
      return original(path);
    });
    await openGroup();
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'New' } });
    await screen.findByText(candidate.id);
    await chooseSource('Accounts accounts');
    expect(screen.queryByText(candidate.id)).toBeNull();
    await chooseSource('Research research-home');
    await chooseSource('Accounts accounts');
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'pieroot' } });
    await screen.findByText(account.email);
    if (outcome === 'success') old.resolve({ domain_id: 'domain-a', user_domain_id: 'accounts', items: [{ ...account, id: 'stale', email: 'stale@example.test' }] });
    else old.reject(new ApiError(503, 'old_source_failed'));
    await tick();
    expect(screen.getByText(account.email)).toBeTruthy();
    expect(screen.queryByText('stale@example.test')).toBeNull();
    expect(screen.queryByText('old_source_failed')).toBeNull();
  });

  it('keeps verified members and default candidates usable when home-domain list fails, with independent retry', async () => {
    mocks.listDomains.mockRejectedValueOnce(new ApiError(503, 'domains_unavailable'));
    await openGroup();
    await screen.findByText('domains_unavailable');
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'New' } });
    await screen.findByText(candidate.id);
    expect(screen.getByText(member.email)).toBeTruthy();
    expect(screen.getByRole('button', { name: '추가' })).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: '홈 도메인 목록 다시 조회' }));
    await waitFor(() => expect(screen.queryByText('domains_unavailable')).toBeNull());
    expect(mocks.listDomains).toHaveBeenLastCalledWith(expect.objectContaining({ token: 'token', projectId: 'admin-project' }), { refresh: true });
    expect(mocks.get.mock.calls.filter(([path]) => path === '/api/v1/admin/domains/domain-a/members')).toHaveLength(1);
  });

  it.each([
    { domain_id: 'wrong', user_domain_id: 'accounts', items: [account] },
    { domain_id: 'domain-a', user_domain_id: 'wrong', items: [account] },
    { domain_id: 'domain-a', user_domain_id: 'accounts', items: [{ ...account, domain_id: 'wrong' }] },
  ])('blocks mismatched exact source responses %#', async (response) => {
    const original = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation((path: string) => path === sourcePath ? Promise.resolve(response) : original(path));
    await openGroup();
    await chooseSource('Accounts accounts');
    await screen.findByRole('button', { name: '사용자 목록 다시 조회' });
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'pieroot' } });
    expect(screen.queryByText(account.id)).toBeNull();
    expect(screen.queryByRole('button', { name: '추가' })).toBeNull();
    expect(screen.getByText(member.email)).toBeTruthy();
    expect(mocks.put).not.toHaveBeenCalled();
  });

  it('disables source selection while add is pending and fences its result after collapse/reopen', async () => {
    const request = Promise.withResolvers<unknown>();
    mocks.put.mockReturnValueOnce(request.promise);
    const original = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation((path: string) => path === sourcePath ? Promise.resolve({ domain_id: 'domain-a', user_domain_id: 'accounts', items: [account] }) : original(path));
    await openGroup();
    await chooseSource('Accounts accounts');
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'pieroot' } });
    await screen.findByText(account.email);
    await fireEvent.click(screen.getByRole('button', { name: '계정 홈 도메인' }));
    await fireEvent.click(screen.getByRole('button', { name: '추가' }));
    expect((screen.getByRole('button', { name: '계정 홈 도메인' }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(screen.getByRole('option', { name: 'Research research-home' }));
    expect(mocks.get.mock.calls.some(([path]) => path.includes('user_domain_id=research-home'))).toBe(false);
    await fireEvent.click(screen.getByRole('button', { name: '계정 홈 도메인' }));
    expect(screen.queryByRole('listbox')).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText(member.email);
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'new source query' } });
    request.resolve({});
    await waitFor(() => expect((screen.getByRole('button', { name: '계정 홈 도메인' }) as HTMLButtonElement).disabled).toBe(false));
    expect((screen.getByRole('searchbox', { name: '사용자 검색' }) as HTMLInputElement).value).toBe('new source query');
    expect(mocks.put).toHaveBeenCalledTimes(1);
  });
});

describe('candidate authority lifetime', () => {
  it.each(['token', 'userId'] as const)('discards source candidates after an actor %s change', async (key) => {
    const pending = Promise.withResolvers<unknown>();
    const original = mocks.get.getMockImplementation()!;
    let sourceCalls = 0;
    const freshAccount = { ...account, id: 'fresh-account', email: 'fresh@example.test' };
    mocks.get.mockImplementation((path: string) => path === sourcePath
      ? ++sourceCalls === 1 ? pending.promise : Promise.resolve({ domain_id: 'domain-a', user_domain_id: 'accounts', items: [freshAccount] })
      : original(path));
    await openGroup();
    await chooseSource('Accounts accounts');
    auth.update((value) => ({ ...value, [key]: 'changed' }));
    await waitFor(() => expect(screen.queryByRole('searchbox', { name: '사용자 검색' })).toBeNull());
    await screen.findByText(group.name);
    await fireEvent.click(screen.getByRole('button', { name: '멤버' }));
    await screen.findByText(member.email);
    await chooseSource('Accounts accounts');
    await fireEvent.input(screen.getByRole('searchbox', { name: '사용자 검색' }), { target: { value: 'pieroot' } });
    await screen.findByText(freshAccount.email);
    pending.resolve({ domain_id: 'domain-a', user_domain_id: 'accounts', items: [account] });
    await tick();
    expect(screen.getByText(freshAccount.email)).toBeTruthy();
    expect(screen.queryByText(account.email)).toBeNull();
    expect(mocks.put).not.toHaveBeenCalled();
  });
});
