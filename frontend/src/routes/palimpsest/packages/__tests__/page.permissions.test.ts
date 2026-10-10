import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import type { Writable } from 'svelte/store';
import type { IssuedPackageKey, PackageKey, ProjectContext } from '$lib/api/palimpsestPackages';
import type * as PackageModule from '$lib/api/palimpsestPackages';
import type { Locale } from '$lib/i18n/locales';

const mocks = vi.hoisted(() => ({ context: vi.fn(), keys: vi.fn(), issue: vi.fn() }));
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
vi.mock('$lib/api/palimpsestPackages', async (importOriginal) => {
  const original = await importOriginal<typeof PackageModule>();
  return {
    ...original,
    packageApi: {
      ...original.packageApi,
      context: mocks.context, keys: mocks.keys, issue: mocks.issue,
      inventory: vi.fn(async (actor) => ({ project_id: actor.projectId, namespace: 'packages', items: [], next_cursor: null })),
    },
  };
});

import Page from '../+page.svelte';
import { auth } from '$lib/stores/auth';
import { serviceCapabilities, serviceDenials } from '$lib/stores/servicePermissions';
import { t } from '$lib/i18n/ns/palimpsest-packages';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';

// Production exports are read-only; this fixture deliberately supplies writable stores.
const capabilities = serviceCapabilities as Writable<(leaf: string) => boolean>;
const denials = serviceDenials as Writable<(leaf: string) => boolean>;

const nativeContext: ProjectContext = {
  project_id: 'project-a', project_name: 'Project A', namespace: 'packages', package_authority: 'registry.example',
  capabilities: { packages_read: true, packages_download: true, packages_write: true, keys_issue: true, keys_revoke: true },
};
const issuedKey: PackageKey = {
  key_id: 'key-a', name: 'ci-draft', project_id: 'project-a', owner_user_id: 'user-a', namespace: 'packages',
  scope: { packages: ['team/image'] }, actions: ['packages:write'],
  created_at: '2026-10-01T00:00:00Z', expires_at: '2026-10-31T00:00:00Z', revoked_at: null,
};
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
  auth.set({ ...get(auth), token: 'jwt-a', projectId: 'project-a', userId: 'user-a' });
  granted();
  mocks.context.mockResolvedValue(nativeContext);
  mocks.keys.mockResolvedValue({ project_id: 'project-a', namespace: 'packages', items: [] });
  mocks.issue.mockResolvedValue({ key: issuedKey, secret: 'private-one-time-value' });
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
