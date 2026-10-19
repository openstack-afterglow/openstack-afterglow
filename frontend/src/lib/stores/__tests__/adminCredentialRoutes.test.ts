import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { SvelteURL } from 'svelte/reactivity';
import { get } from 'svelte/store';
import ApplicationCredentialsPage from '../../../routes/admin/application-credentials/+page.svelte';
import UserCredentialsPage from '../../../routes/admin/user-credentials/+page.svelte';
import { acceptAuthVerification, auth, authReady, getAuthVerificationEpoch, hasVerifiedAuth, projectSwitching, setAuth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/domain-admin';
import { refreshAuthState } from '$lib/utils/authSession';

const { request, listDomains, page, goto } = vi.hoisted(() => ({
  request: vi.fn(), listDomains: vi.fn(), goto: vi.fn(),
  page: { url: new URL('https://afterglow.test/admin/application-credentials'), state: {} },
}));
vi.mock('$app/state', () => ({ page }));
vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$lib/api/domains', () => ({ domainsApi: { list: listDomains } }));
vi.mock('$lib/api/adminCredentials', () => ({ credentialRequest: request }));
const initialAuth = get(auth);
const domainId = 'domain-a';

beforeEach(() => {
  request.mockReset().mockImplementation((path: string) => Promise.resolve(path.includes('/users?')
    ? { items: [{ id: 'caller', name: 'Caller', domain_id: domainId }], next_marker: null }
    : { items: [] }));
  listDomains.mockReset().mockResolvedValue({ items: [{ id: domainId, name: 'Domain A', enabled: true, description: '' }] });
  goto.mockReset().mockImplementation(async (url: URL) => { page.url.search = url.search; });
  auth.set({ ...initialAuth, token: 'token', userId: 'caller', username: 'Caller', projectId: 'project-a', projectName: 'Project A', domainId, domainName: 'Domain A', identityDomainId: domainId, identityDomainName: 'Domain A', isSystemAdmin: true });
  expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true); projectSwitching.set(false);
});
afterEach(() => { cleanup(); auth.set(initialAuth); authReady.set(false); projectSwitching.set(false); });

const routes = [
  { component: ApplicationCredentialsPage, path: '/admin/application-credentials' },
  { component: UserCredentialsPage, path: '/admin/user-credentials' },
];
describe.each(routes)('credential route $path', ({ component, path }) => {
  it('requires an explicit selector before mounting any directory or credential consumer', async () => {
    page.url = new SvelteURL(path, 'https://afterglow.test'); render(component);
    await vi.waitFor(() => expect(screen.getByText(t('scope.required'))).toBeTruthy());
    expect(screen.getByText(t('scope.domain'))).toBeTruthy();
    expect(request).not.toHaveBeenCalled(); expect(goto).not.toHaveBeenCalled();
  });
  it('selects a domain through the real picker and mounts scoped consumers without a reload', async () => {
    page.url = new SvelteURL(path, 'https://afterglow.test'); render(component);
    await vi.waitFor(() => expect(screen.getByText(t('scope.required'))).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: t('scope.domain') }));
    await fireEvent.click(screen.getByRole('option', { name: /Domain A/ }));
    await vi.waitFor(() => expect(screen.getByText(`Domain A · ${domainId}`)).toBeTruthy());
    expect(goto).toHaveBeenCalledWith(expect.any(URL), { replaceState: true, keepFocus: true, noScroll: true });
    expect(page.url.searchParams.get('domain_id')).toBe(domainId);
    await vi.waitFor(() => expect(request.mock.calls.some(([url]) => url.includes('-credentials'))).toBe(true));
    expect(request.mock.calls.every(([, selectedDomain]) => selectedDomain === domainId)).toBe(true);
  });
  it('mounts a verified domain_id deep link with the selected name and scopes every consumer request', async () => {
    page.url = new SvelteURL(`${path}?domain_id=${domainId}`, 'https://afterglow.test'); render(component);
    await vi.waitFor(() => expect(screen.getByText(`Domain A · ${domainId}`)).toBeTruthy());
    await vi.waitFor(() => expect(request.mock.calls.some(([url]) => url.includes('-credentials'))).toBe(true));
    expect(request.mock.calls.every(([, selectedDomain]) => selectedDomain === domainId)).toBe(true);
    expect(request.mock.calls.some(([url]) => url.includes('/users?'))).toBe(true);
  });
  it('keeps the verified domain inventory across routine token rotation without remounting the boundary', async () => {
    page.url = new SvelteURL(`${path}?domain_id=${domainId}`, 'https://afterglow.test'); render(component);
    await vi.waitFor(() => expect(screen.getByText(`Domain A · ${domainId}`)).toBeTruthy());
    expect(listDomains).toHaveBeenCalledTimes(1);
    setAuth(refreshAuthState({
      token: 'rotated-token', user_id: 'caller', username: 'Caller',
      project_id: 'project-a', project_name: 'Project A', expires_at: null,
      domain_id: domainId, domain_name: 'Domain A', identity_domain_id: domainId, identity_domain_name: 'Domain A',
    }, get(auth)));
    expect(get(authReady)).toBe(true); expect(hasVerifiedAuth()).toBe(false);
    await vi.waitFor(() => expect(request.mock.calls.some(([, , authority]) => authority.token === 'rotated-token')).toBe(true));
    expect(listDomains).toHaveBeenCalledTimes(1);
    expect(page.url.searchParams.get('domain_id')).toBe(domainId);
  });
  it('rejects an unknown deep link instead of defaulting to the caller domain', async () => {
    page.url = new SvelteURL(`${path}?domain_id=unknown-domain`, 'https://afterglow.test'); render(component);
    await vi.waitFor(() => expect(screen.getByText(t('scope.invalid'))).toBeTruthy());
    expect(request).not.toHaveBeenCalled(); expect(goto).not.toHaveBeenCalled();
  });
});
