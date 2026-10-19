import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import type { Writable } from 'svelte/store';
import type { IssuedPackageKey, PackageKey, ProjectContext, PackageSummary, PackageVersion, ScopedPage } from '$lib/api/palimpsestPackages';
import type * as PackageModule from '$lib/api/palimpsestPackages';
import type { Locale } from '$lib/i18n/locales';

const mocks = vi.hoisted(() => ({ context: vi.fn(), keys: vi.fn(), issue: vi.fn(), inventory: vi.fn(), versions: vi.fn(), detail: vi.fn() }));
// Hoisted module-boundary mocks load their store/fixture dependencies inside the factories.
vi.mock('$app/navigation', () => ({ beforeNavigate: vi.fn() }));
vi.mock('$app/stores', async () => {
  const { writable } = await import('svelte/store');
  return { page: writable({ url: new URL('http://localhost/palimpsest/packages') }) };
});
vi.mock('$lib/stores/auth', async () => {
  const { writable } = await import('svelte/store');
  return {
    auth: writable({ token: 'jwt-a', projectId: 'project-a', userId: 'user-a' }),
    authReady: writable(true), projectSwitching: writable(false), logoutInProgress: writable(false),
  };
});
vi.mock('$lib/stores/servicePermissions', async () => {
  const { writable } = await import('svelte/store');
  return { serviceCapabilities: writable((_leaf: string) => true), serviceDenials: writable((_leaf: string) => false) };
});
vi.mock('$lib/components/palimpsest/HubArtifactsPanel.svelte', async () => ({ default: (await import('./WorkspacePanelFixture.svelte')).default }));
vi.mock('$lib/components/palimpsest/PalimpsestLocalGuide.svelte', async () => ({ default: (await import('./WorkspacePanelFixture.svelte')).default }));
vi.mock('$lib/api/palimpsestPackages', async (importOriginal) => {
  const original = await importOriginal<typeof PackageModule>();
  return {
    ...original,
    packageApi: {
      ...original.packageApi,
      context: mocks.context, keys: mocks.keys, issue: mocks.issue,
      inventory: mocks.inventory, versions: mocks.versions, detail: mocks.detail,
    },
  };
});

import Page from '../+page.svelte';
import { auth } from '$lib/stores/auth';
import { page } from '$app/stores';
import { ApiError } from '$lib/api/errors';
import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
import { t } from '$lib/i18n/ns/palimpsest-packages';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';

// Production exports are read-only; this fixture deliberately supplies writable stores.
const capabilities = serviceCapabilities as Writable<(leaf: string) => boolean>;
const denials = serviceDenials as Writable<(leaf: string) => boolean>;
const route = page as unknown as Writable<{ url: URL }>;

const nativeContext: ProjectContext = {
  project_id: 'project-a', project_name: 'Project A', namespace: 'packages', package_authority: 'registry.example',
  capabilities: { packages_read: true, packages_download: true, packages_write: true, keys_issue: true, keys_revoke: true },
};
const issuedKey: PackageKey = {
  key_id: 'key-a', name: 'ci-draft', project_id: 'project-a', owner_user_id: 'user-a', namespace: 'packages',
  scope: { packages: ['team/image'] }, actions: ['packages:write'],
  created_at: '2026-10-01T00:00:00Z', expires_at: '2026-10-31T00:00:00Z', revoked_at: null,
};
function packageRow(name: string, digest = 'a', platform = 'amd64'): PackageSummary {
  return {
    package_id: name, project_id: 'project-a', namespace: 'packages', name,
    package_type: 'oci-image', visibility: 'project', tags: [{ tag: 'stable', digest: `sha256:${digest.repeat(64)}` }],
    platforms: [{ os: 'linux', architecture: platform }], version_count: 1,
    latest_pushed_at: '2026-10-01T00:00:00Z', latest_pushed_by: 'user-a',
  };
}
function packageVersion(row: PackageSummary, digest: string): PackageVersion {
  return {
    project_id: row.project_id, namespace: row.namespace, package: row.name,
    root_digest: digest, root_media_type: 'application/vnd.oci.image.manifest.v1+json',
    root_descriptor: { digest, mediaType: 'application/vnd.oci.image.manifest.v1+json', size: 1 },
    graph: {}, platforms: row.platforms, archive_digest: digest, archive_size_bytes: 1, total_bytes: 1,
    provenance: {}, pushed_by: 'user-a', pushed_key_id: 'key-a', pushed_at: '2026-10-01T00:00:00Z',
  };
}
async function selectNative() {
  await fireEvent.click(screen.getByRole('tab', { name: t('workspace.packages') }));
}
let previousLocale: Locale;
function unavailable() {
  capabilities.set(() => false);
  denials.set(() => false);
}
function granted() {
  denials.set(() => false);
  capabilities.set(() => true);
}
async function openDraft() {
  render(Page);
  await selectNative();
  await screen.findByText('Project A');
  await fireEvent.click(screen.getByRole('tab', { name: t('tabs.keys') }));
  const issue = screen.getByRole('button', { name: t('keys.issue') });
  await waitFor(() => expect((issue as HTMLButtonElement).disabled).toBe(false));
  await fireEvent.click(issue);
  const modal = screen.getByRole('dialog', { name: t('create.label') });
  await fireEvent.input(within(modal).getByRole('textbox', { name: t('create.name') }), { target: { value: 'ci-draft' } });
  await fireEvent.input(within(modal).getByRole('textbox', { name: t('create.packages') }), { target: { value: 'team/image' } });
  await fireEvent.input(within(modal).getByRole('spinbutton', { name: t('create.expiry') }), { target: { value: '14' } });
  await fireEvent.click(within(modal).getByRole('checkbox', { name: t('action.packagesWrite') }));
  return modal;
}
function expectPreservedDraft(disabled: boolean) {
  const modal = screen.getByRole('dialog', { name: t('create.label') });
  const name = within(modal).getByRole('textbox', { name: t('create.name') }) as HTMLInputElement;
  const packages = within(modal).getByRole('textbox', { name: t('create.packages') }) as HTMLInputElement;
  const expiry = within(modal).getByRole('spinbutton', { name: t('create.expiry') }) as HTMLInputElement;
  expect(name.value).toBe('ci-draft'); expect(packages.value).toBe('team/image'); expect(expiry.value).toBe('14');
  expect(name.disabled).toBe(disabled); expect(packages.disabled).toBe(disabled); expect(expiry.disabled).toBe(disabled);
  expect((within(modal).getByRole('checkbox', { name: t('action.packagesWrite') }) as HTMLInputElement).checked).toBe(true);
  expect((within(modal).getByRole('button', { name: t('keys.issue') }) as HTMLButtonElement).disabled).toBe(disabled);
  return modal;
}
beforeEach(() => {
  previousLocale = getLocale(); initLocale('en');
  vi.clearAllMocks();
  route.set({ url: new URL('http://localhost/palimpsest/packages') });
  auth.set({ ...get(auth), token: 'jwt-a', projectId: 'project-a', userId: 'user-a' });
  granted();
  mocks.context.mockResolvedValue(nativeContext);
  mocks.keys.mockResolvedValue({ project_id: 'project-a', namespace: 'packages', items: [] });
  mocks.issue.mockResolvedValue({ key: issuedKey, secret: 'private-one-time-value' });
  mocks.inventory.mockResolvedValue({ project_id: 'project-a', namespace: 'packages', items: [], next_cursor: null });
  mocks.versions.mockImplementation(async (_actor, _signal, name) => ({ project_id: 'project-a', namespace: 'packages', package: name, items: [], next_cursor: null }));
  mocks.detail.mockImplementation(async (_actor, _signal, name) => packageRow(name));
});
afterEach(() => { cleanup(); initLocale(previousLocale); });

describe('package draft and secret verification boundaries', () => {
  it('keeps the open draft disabled through same-scope token rotation and permission loading/failure', async () => {
    await openDraft();
    unavailable();
    auth.set({ ...get(auth), token: 'rotated-jwt' });
    await tick();
    const modal = expectPreservedDraft(true);
    await fireEvent.submit(modal.querySelector('form')!);
    expect(mocks.issue).not.toHaveBeenCalled();
    unavailable(); // A failed permissions fetch has the same unavailable authority contract.
    await tick();
    expectPreservedDraft(true);
    granted(); await tick();
    expectPreservedDraft(false);
    await fireEvent.submit(screen.getByRole('dialog', { name: t('create.label') }).querySelector('form')!);
    await screen.findByText('private-one-time-value');
    expect(mocks.issue.mock.calls[0][0].token).toBe('rotated-jwt');
    expect(mocks.issue.mock.calls[0][2]).toMatchObject({ name: 'ci-draft', actions: ['packages:write'], expires_in_days: 14 });
  });

  it('keeps draft fields and actions disabled during a native refresh outage, then restores them', async () => {
    await openDraft();
    const refresh = Promise.withResolvers<ProjectContext>();
    mocks.context.mockReturnValueOnce(refresh.promise);
    await fireEvent.click(screen.getByRole('button', { name: t('actions.refresh') }));
    await tick(); expectPreservedDraft(true);
    refresh.reject(new Error('native outage'));
    await waitFor(() => expect((screen.getByRole('button', { name: t('actions.refresh') }) as HTMLButtonElement).disabled).toBe(false));
    expectPreservedDraft(true);
    await fireEvent.click(screen.getByRole('button', { name: t('actions.refresh') }));
    await waitFor(() => expectPreservedDraft(false));
  });

  it.each(['service', 'native', 'project'] as const)('closes the draft on definitive %s authority loss', async (loss) => {
    await openDraft();
    if (loss === 'service') {
      capabilities.set((leaf) => leaf !== 'palimpsest-keys_editor');
      denials.set((leaf) => leaf === 'palimpsest-keys_editor');
    } else if (loss === 'native') {
      mocks.context.mockResolvedValueOnce({ ...nativeContext, capabilities: { ...nativeContext.capabilities, keys_issue: false } });
      await fireEvent.click(screen.getByRole('button', { name: t('actions.refresh') }));
    } else {
      mocks.context.mockReturnValueOnce(new Promise<ProjectContext>(() => {}));
      auth.set({ ...get(auth), projectId: 'project-b' });
    }
    await waitFor(() => expect(screen.queryByRole('dialog', { name: t('create.label') })).toBeNull());
    expect(mocks.issue).not.toHaveBeenCalled();
  });

  it('masks an issued secret during explicit native refresh without consuming it', async () => {
    const modal = await openDraft();
    await fireEvent.submit(modal.querySelector('form')!);
    await screen.findByText('private-one-time-value');
    const refresh = Promise.withResolvers<ProjectContext>();
    mocks.context.mockReturnValueOnce(refresh.promise);
    await fireEvent.click(screen.getByRole('button', { name: t('actions.refresh') }));
    await tick();
    expect(screen.queryByText('private-one-time-value')).toBeNull();
    refresh.resolve(nativeContext);
    await screen.findByText('private-one-time-value');
  });

  it('reveals a successful late issuance only after permission verification and closes the retained draft', async () => {
    const modal = await openDraft();
    const response = Promise.withResolvers<IssuedPackageKey>();
    mocks.issue.mockReturnValueOnce(response.promise);
    await fireEvent.submit(modal.querySelector('form')!);
    await waitFor(() => expect(mocks.issue).toHaveBeenCalledOnce());
    unavailable(); await tick();
    response.resolve({ key: issuedKey, secret: 'private-late-value' });
    await waitFor(() => expectPreservedDraft(true));
    expect(screen.queryByText('private-late-value')).toBeNull();
    granted();
    await screen.findByText('private-late-value');
    expect(screen.queryByRole('dialog', { name: t('create.label') })).toBeNull();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });
});

describe('persistent Palimpsest workspace', () => {
  it.each(['en', 'ko', 'ja', 'zh-CN'] as const)('keeps Hub and the guide reachable after native 403 in %s', async (locale) => {
    initLocale(locale);
    mocks.context.mockRejectedValue(new ApiError(403, 'Administrative or service identities cannot authorize package access'));
    render(Page);
    expect(screen.getByRole('tab', { name: t('workspace.hub') }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByTestId('hub-panel').getAttribute('data-project-id')).toBe('project-a');
    await selectNative();
    await screen.findByText(t('context.unavailable'));
    expect(screen.getByText(t('context.accessHelp'))).toBeTruthy();
    await fireEvent.click(screen.getByRole('tab', { name: t('workspace.local') }));
    const guide = screen.getByTestId('local-guide');
    expect(guide.getAttribute('data-project-id')).toBe('project-a');
    expect(guide.getAttribute('data-authority')).toBe('');
    expect(guide.getAttribute('data-namespace')).toBe('');
    expect(screen.queryByText(t('context.unavailable'))).toBeNull();
    await fireEvent.click(screen.getByRole('tab', { name: t('workspace.hub') }));
    expect(screen.getByTestId('hub-panel').getAttribute('data-user-id')).toBe('user-a');
    expect(mocks.inventory).not.toHaveBeenCalled();
    expect(mocks.keys).not.toHaveBeenCalled();
    expect(mocks.issue).not.toHaveBeenCalled();
  });

  it.each(['pending', 'no-namespace', 'no-identity'] as const)('reaches every outer tab with %s native context', async (state) => {
    if (state === 'pending') mocks.context.mockReturnValue(new Promise<ProjectContext>(() => {}));
    if (state === 'no-namespace') mocks.context.mockResolvedValue({ ...nativeContext, namespace: null });
    if (state === 'no-identity') auth.set({ ...get(auth), token: '' });
    render(Page);
    expect(screen.getByTestId('hub-panel')).toBeTruthy();
    await fireEvent.click(screen.getByRole('tab', { name: t('workspace.local') }));
    expect(screen.getByTestId('local-guide')).toBeTruthy();
    await selectNative();
    expect(screen.getByRole('tabpanel', { name: t('workspace.packages') })).toBeTruthy();
    for (const key of ['workspace.hub', 'workspace.packages', 'workspace.local'] as const) {
      expect((screen.getByRole('tab', { name: t(key) }) as HTMLButtonElement).disabled).toBe(false);
    }
    await fireEvent.click(screen.getByRole('tab', { name: t('workspace.hub') }));
    expect(screen.getByTestId('hub-panel')).toBeTruthy();
    expect(mocks.issue).not.toHaveBeenCalled();
  });


  it('selects native for a package deep link even when native context is denied', async () => {
    route.set({ url: new URL('http://localhost/palimpsest/packages?package=team/image&namespace=packages') });
    mocks.context.mockRejectedValue(new ApiError(403, 'Native context denied'));
    render(Page);
    await screen.findByText(t('context.unavailable'));
    expect(screen.getByRole('tab', { name: t('workspace.packages') }).getAttribute('aria-selected')).toBe('true');
    await fireEvent.click(screen.getByRole('tab', { name: t('workspace.local') }));
    expect(screen.getByTestId('local-guide')).toBeTruthy();
    expect(mocks.detail).not.toHaveBeenCalled();
  });

  it('opens deep-linked details and selects native again when the route package changes', async () => {
    route.set({ url: new URL('http://localhost/palimpsest/packages?package=team/image&namespace=packages') });
    render(Page);
    await screen.findByRole('dialog', { name: t('detail.label') });
    expect(mocks.detail.mock.calls[0][2]).toBe('team/image');
    await fireEvent.click(screen.getByRole('button', { name: t('actions.close') }));
    await fireEvent.click(screen.getByRole('tab', { name: t('workspace.hub') }));
    route.set({ url: new URL('http://localhost/palimpsest/packages?package=next/image&namespace=packages') });
    await screen.findByRole('dialog', { name: t('detail.label') });
    expect(screen.getByRole('tab', { name: t('workspace.packages') }).getAttribute('aria-selected')).toBe('true');
    expect(mocks.detail.mock.calls.at(-1)?.[2]).toBe('next/image');
  });

  it('keeps namespace validation on deep links instead of treating the route as authority', async () => {
    route.set({ url: new URL('http://localhost/palimpsest/packages?package=team/image&namespace=foreign') });
    render(Page);
    await screen.findByText(t('error.linkNamespace'));
    expect(mocks.detail).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog', { name: t('detail.label') })).toBeNull();
  });

  it('discards a late once-only secret when a route change selects another native package', async () => {
    const modal = await openDraft();
    const response = Promise.withResolvers<IssuedPackageKey>();
    mocks.issue.mockReturnValueOnce(response.promise);
    await fireEvent.submit(modal.querySelector('form')!);
    await waitFor(() => expect(mocks.issue).toHaveBeenCalledOnce());
    route.set({ url: new URL('http://localhost/palimpsest/packages?package=team/image') });
    await tick();
    response.resolve({ key: issuedKey, secret: 'discarded-late-secret' });
    await waitFor(() => expect(mocks.keys.mock.calls.length).toBeGreaterThan(1));
    expect(screen.queryByText('discarded-late-secret')).toBeNull();
    expect(screen.queryByRole('dialog', { name: t('secret.label') })).toBeNull();
  });
});

describe('loaded-only native package search', () => {
  it('matches loaded names, namespaces, tags, tag/latest digests and platforms without new requests', async () => {
    const alpha = packageRow('team/alpha');
    const beta = { ...packageRow('team/beta', 'b', 'arm64'), tags: [{ tag: 'preview', digest: `sha256:${'b'.repeat(64)}` }], platforms: [{ os: 'windows', architecture: 'arm64', variant: 'v8' }] };
    mocks.inventory.mockResolvedValue({ project_id: 'project-a', namespace: 'packages', items: [alpha, beta], next_cursor: 'next-page' });
    mocks.versions.mockImplementation(async (_actor, _signal, name) => ({
      project_id: 'project-a', namespace: 'packages', package: name, next_cursor: null,
      items: [packageVersion(name === alpha.name ? alpha : beta, `sha256:${(name === alpha.name ? 'c' : 'd').repeat(64)}`)],
    }));
    render(Page); await selectNative();
    const search = await screen.findByRole('searchbox', { name: t('search.label') });
    await waitFor(() => expect(screen.queryAllByText(t('metadata.loading'))).toHaveLength(0));
    expect(screen.getByText(t('search.scope'))).toBeTruthy();
    for (const [query, matched] of [['TEAM/ALPHA', 1], ['packages', 2], ['preview', 1], ['sha256:bbbb', 1], ['sha256:cccc', 1], ['linux/amd64', 1], ['windows/arm64/v8', 1], ['missing', 0]] as const) {
      await fireEvent.input(search, { target: { value: query } });
      expect(screen.getByText(t('search.count', { matched, loaded: 2 }))).toBeTruthy();
      expect(screen.getByRole('button', { name: t('inventory.more') })).toBeTruthy();
    }
    expect(screen.getByText(t('search.empty'))).toBeTruthy();
    await fireEvent.input(search, { target: { value: '   ' } });
    expect(screen.getByText(t('search.count', { matched: 2, loaded: 2 }))).toBeTruthy();
    expect(mocks.inventory).toHaveBeenCalledOnce();
    expect(mocks.context).toHaveBeenCalledOnce();
    expect(mocks.versions).toHaveBeenCalledTimes(2);
    expect(mocks.keys).not.toHaveBeenCalled();
    expect(mocks.issue).not.toHaveBeenCalled();
  });

  it('loads the next cursor with zero matches and retains every loaded row through filter changes', async () => {
    const alpha = packageRow('team/alpha'); const beta = packageRow('team/beta', 'b'); const gamma = packageRow('team/gamma', 'c');
    const next = Promise.withResolvers<ScopedPage<PackageSummary>>();
    mocks.inventory.mockResolvedValueOnce({ project_id: 'project-a', namespace: 'packages', items: [alpha, beta], next_cursor: 'opaque-cursor' }).mockReturnValueOnce(next.promise);
    render(Page); await selectNative();
    const search = await screen.findByRole('searchbox', { name: t('search.label') });
    await fireEvent.input(search, { target: { value: 'gamma' } });
    expect(screen.getByText(t('search.count', { matched: 0, loaded: 2 }))).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: t('inventory.more') }));
    expect(mocks.inventory.mock.calls[1][2]).toBe('opaque-cursor');
    expect(mocks.inventory.mock.calls[1][0]).toEqual({ token: 'jwt-a', projectId: 'project-a', userId: 'user-a' });
    await fireEvent.input(search, { target: { value: 'alpha' } });
    next.resolve({ project_id: 'project-a', namespace: 'packages', items: [gamma], next_cursor: null });
    await screen.findByText(t('search.count', { matched: 1, loaded: 3 }));
    expect(screen.getAllByText('packages/team/alpha').length).toBeGreaterThan(0);
    expect(screen.queryByText('packages/team/beta')).toBeNull();
    expect(screen.queryByText('packages/team/gamma')).toBeNull();
    await fireEvent.input(search, { target: { value: '' } });
    expect(screen.getByText(t('search.count', { matched: 3, loaded: 3 }))).toBeTruthy();
    for (const row of [alpha, beta, gamma]) expect(screen.getAllByText(`packages/${row.name}`).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: t('inventory.more') })).toBeNull();
    expect(mocks.inventory).toHaveBeenCalledTimes(2);
  });

  it('cannot grant download, key or inventory authority and rejects a page completed during denial', async () => {
    mocks.context.mockResolvedValue({ ...nativeContext, capabilities: { packages_read: true, packages_download: false, packages_write: false, keys_issue: false, keys_revoke: false } });
    const next = Promise.withResolvers<ScopedPage<PackageSummary>>();
    mocks.inventory.mockResolvedValueOnce({ project_id: 'project-a', namespace: 'packages', items: [packageRow('alpha'), packageRow('beta')], next_cursor: 'next' }).mockReturnValueOnce(next.promise);
    render(Page); await selectNative();
    const search = await screen.findByRole('searchbox', { name: t('search.label') });
    await fireEvent.input(search, { target: { value: 'alpha' } });
    for (const download of screen.getAllByRole('button', { name: t('actions.download') })) expect((download as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(screen.getByRole('button', { name: t('inventory.more') }));
    capabilities.set((leaf) => leaf !== 'palimpsest-inventory_reader');
    denials.set((leaf) => leaf === 'palimpsest-inventory_reader');
    await screen.findByText(t('inventory.denied'));
    expect(screen.queryByRole('searchbox', { name: t('search.label') })).toBeNull();
    next.resolve({ project_id: 'project-a', namespace: 'packages', items: [packageRow('late')], next_cursor: null });
    await tick(); await tick();
    granted();
    const restored = await screen.findByRole('searchbox', { name: t('search.label') });
    await fireEvent.input(restored, { target: { value: '' } });
    expect(screen.getByText(t('search.count', { matched: 2, loaded: 2 }))).toBeTruthy();
    expect(screen.queryByText('packages/late')).toBeNull();
    await fireEvent.click(screen.getByRole('tab', { name: t('tabs.keys') }));
    expect((screen.getByRole('button', { name: t('keys.issue') }) as HTMLButtonElement).disabled).toBe(true);
    expect(mocks.keys).not.toHaveBeenCalled();
    expect(mocks.issue).not.toHaveBeenCalled();
  });

  it('clears the filter and loaded rows on actor change instead of mixing projects', async () => {
    mocks.inventory.mockResolvedValueOnce({ project_id: 'project-a', namespace: 'packages', items: [packageRow('alpha'), packageRow('beta')], next_cursor: null });
    render(Page); await selectNative();
    const search = await screen.findByRole('searchbox', { name: t('search.label') });
    await fireEvent.input(search, { target: { value: 'alpha' } });
    mocks.context.mockResolvedValueOnce({ ...nativeContext, project_id: 'project-b', project_name: 'Project B', namespace: 'other' });
    mocks.inventory.mockResolvedValueOnce({ project_id: 'project-b', namespace: 'other', items: [{ ...packageRow('gamma'), project_id: 'project-b', namespace: 'other' }], next_cursor: null });
    mocks.versions.mockImplementation(async (_actor, _signal, name) => ({ project_id: 'project-b', namespace: 'other', package: name, items: [], next_cursor: null }));
    auth.set({ ...get(auth), token: 'jwt-b', projectId: 'project-b', userId: 'user-b' });
    await screen.findByText('Project B');
    const nextSearch = await screen.findByRole('searchbox', { name: t('search.label') });
    expect((nextSearch as HTMLInputElement).value).toBe('');
    expect(screen.getAllByText('other/gamma').length).toBeGreaterThan(0);
    expect(screen.queryByText('packages/alpha')).toBeNull();
    expect(screen.queryByText('packages/beta')).toBeNull();
    expect(mocks.inventory.mock.calls.at(-1)?.[0]).toEqual({ token: 'jwt-b', projectId: 'project-b', userId: 'user-b' });
  });
});
