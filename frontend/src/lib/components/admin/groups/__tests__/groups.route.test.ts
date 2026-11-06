import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { writable } from 'svelte/store';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), listDomains: vi.fn() }));
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/admin/groups?domain_id=domain-a') } }));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error {} }));
vi.mock('$lib/api/domains', () => ({ domainsApi: { list: mocks.listDomains } }));
vi.mock('$lib/stores/auth', () => ({
  auth: writable({ token: 'token', sessionId: 'login-a', userId: 'actor', identityDomainId: 'accounts', domainId: 'working', projectId: 'project-a', isSystemAdmin: true, roles: ['admin'] }),
  authReady: writable(true), projectSwitching: writable(false),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({ createAutoRefresh: () => ({ active: false, intervalSeconds: 60, intervalOptions: [30, 60] }) }));

import { auth, authReady, projectSwitching } from '$lib/stores/auth';
import { t as commonT } from '$lib/i18n/ns/common';
import { t as domainT } from '$lib/i18n/ns/domain-admin';
import { t as identityT } from '$lib/i18n/ns/admin-identity';
import Route from '../../../../../routes/admin/groups/+page.svelte';

const domain = { id: 'domain-a', name: 'Domain A', description: '', enabled: true };
const group = { id: 'group-a', name: 'Domain A group', description: '', domain_id: domain.id, created_at: null };
const user = { id: 'native-user-a', name: 'New member', email: 'member@example.test', domain_id: domain.id, enabled: true };

beforeEach(() => {
  vi.resetAllMocks();
  auth.update((state) => ({ ...state, token: 'token', sessionId: 'login-a', userId: 'actor', identityDomainId: 'accounts', domainId: 'working', projectId: 'project-a', isSystemAdmin: true, roles: ['admin'] }));
  authReady.set(true); projectSwitching.set(false);
  mocks.listDomains.mockResolvedValue({ items: [domain] });
  mocks.get.mockImplementation((path: string) => {
    if (path === '/api/v1/admin/groups?domain_id=domain-a') return Promise.resolve([group]);
    if (path === '/api/v1/admin/groups/group-a/users?domain_id=domain-a') return Promise.resolve([]);
    if (path === '/api/v1/admin/domains/domain-a/members') return Promise.resolve({ domain_id: domain.id, items: [user] });
    throw new Error(`Unexpected fixture request: ${path}`);
  });
});
afterEach(cleanup);

it('keeps the actual group route child, regex, facets, ordering and expanded candidates mounted during source refresh', async () => {
  render(Route);
  await screen.findByText(group.name);
  const search = screen.getByRole('searchbox', { name: identityT('groupPage.search') }) as HTMLInputElement;
  await fireEvent.input(search, { target: { value: '^Domain (A|B) group$' } });
  const controls = within(screen.getAllByRole('group', { name: commonT('table.controls') })[0]);
  await fireEvent.click(controls.getByRole('button', { name: commonT('table.sortColumn', { column: identityT('form.name'), direction: commonT('table.none') }) }));
  const filterName = commonT('table.filterColumn', { column: identityT('form.name') });
  await fireEvent.click(controls.getByRole('button', { name: filterName }));
  const filter = within(screen.getByRole('dialog', { name: filterName }));
  await fireEvent.click(filter.getByRole('button', { name: commonT('table.selectAll') }));
  await fireEvent.click(filter.getByRole('button', { name: commonT('actions.close') }));
  await fireEvent.click(screen.getByRole('button', { name: identityT('groupCard.members') }));
  await screen.findByText(user.email);
  const candidates = screen.getByRole('searchbox', { name: identityT('groupCard.userSearch') }) as HTMLInputElement;
  await fireEvent.input(candidates, { target: { value: '^New member$' } });
  auth.update((state) => ({ ...state, token: 'renewed-token' }));
  await tick();
  expect(screen.getByRole('searchbox', { name: identityT('groupCard.userSearch') })).toBe(candidates);
  const pending = Promise.withResolvers<{ items: typeof domain[] }>();
  mocks.listDomains.mockReturnValueOnce(pending.promise);
  await fireEvent.click(screen.getByRole('button', { name: domainT('actions.refresh') }));
  expect(mocks.listDomains).toHaveBeenLastCalledWith({ token: 'renewed-token', projectId: 'project-a' }, { refresh: true });
  expect(screen.getByRole('searchbox', { name: identityT('groupPage.search') })).toBe(search);
  expect(screen.getByRole('searchbox', { name: identityT('groupCard.userSearch') })).toBe(candidates);
  expect(screen.getByText(user.id)).toBeTruthy();
  pending.resolve({ items: [{ ...domain, name: 'Renamed Domain A' }] });
  await waitFor(() => expect(screen.getByRole('button', { name: domainT('actions.refresh') })).toMatchObject({ disabled: false }));
  expect(search.value).toBe('^Domain (A|B) group$');
  expect(candidates.value).toBe('^New member$');
  expect(controls.getByRole('button', { name: commonT('table.sortColumn', { column: identityT('form.name'), direction: commonT('table.ascending') }) })).toBeTruthy();
  mocks.get.mockResolvedValueOnce([group, { ...group, id: 'group-b', name: 'Domain B group' }]);
  await fireEvent.click(screen.getByRole('button', { name: commonT('autoRefresh.refreshNow') }));
  await waitFor(() => expect(screen.getByText(identityT('groupPage.results', { shown: '1', total: '2' }))).toBeTruthy());
  expect(screen.queryByText('Domain B group')).toBeNull();
  expect(screen.getByRole('searchbox', { name: identityT('groupCard.userSearch') })).toBe(candidates);
});

it('retains only the previously verified same-owner child on source lookup failure, then removes a selection absent from a successful replacement', async () => {
  render(Route);
  await screen.findByText(group.name);
  const search = screen.getByRole('searchbox', { name: identityT('groupPage.search') });
  await fireEvent.input(search, { target: { value: '^Domain A group$' } });
  mocks.listDomains.mockRejectedValueOnce(new Error('source_directory_unavailable'));
  await fireEvent.click(screen.getByRole('button', { name: domainT('actions.refresh') }));
  await screen.findByText(domainT('scope.loadFailed'));
  expect(screen.getByRole('searchbox', { name: identityT('groupPage.search') })).toBe(search);
  mocks.listDomains.mockResolvedValueOnce({ items: [] });
  await fireEvent.click(screen.getByRole('button', { name: domainT('actions.refresh') }));
  await screen.findByText(domainT('scope.invalid'));
  expect(screen.queryByRole('searchbox', { name: identityT('groupPage.search') })).toBeNull();
  expect(screen.queryByText(group.name)).toBeNull();
});

it('invalidates the route child on an authority ABA and never republishes its older source refresh', async () => {
  render(Route);
  await screen.findByText(group.name);
  const pending = Promise.withResolvers<{ items: typeof domain[] }>();
  mocks.listDomains.mockReturnValueOnce(pending.promise);
  await fireEvent.click(screen.getByRole('button', { name: domainT('actions.refresh') }));
  mocks.listDomains.mockResolvedValueOnce({ items: [] });
  auth.update((state) => ({ ...state, isSystemAdmin: false }));
  auth.update((state) => ({ ...state, isSystemAdmin: true }));
  await screen.findByText(domainT('scope.invalid'));
  pending.resolve({ items: [domain] });
  await tick(); await tick();
  expect(screen.queryByRole('searchbox', { name: identityT('groupPage.search') })).toBeNull();
  expect(screen.queryByText(group.name)).toBeNull();
});
