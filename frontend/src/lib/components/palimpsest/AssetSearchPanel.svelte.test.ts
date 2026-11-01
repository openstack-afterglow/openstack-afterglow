import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get, type Writable } from 'svelte/store';
import type * as SvelteStore from 'svelte/store';
import type * as AssetModule from '$lib/api/palimpsestAssets';
import type { PackageSummary, PackageVersion, ProjectContext } from '$lib/api/palimpsestPackages';
import type { ProjectPermissions } from '$lib/stores/servicePermissions';
import { projectPermissions } from '$lib/stores/servicePermissions';
import { auth, authReady, logoutInProgress, projectSwitching, setAuth } from '$lib/stores/auth';
import { assetApi } from '$lib/api/palimpsestAssets';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';
import AssetSearchPanel from './AssetSearchPanel.svelte';
import PackagesPage from '../../../routes/palimpsest/packages/+page.svelte';
import type { ReusableAsset, CloudEnvironment } from '$lib/api/palimpsestAssets';
import { refreshAuthState } from '$lib/utils/authSession';
import { defaultUsageDraft, toLocalDateTime } from '$lib/utils/instanceUsage';

vi.mock('$lib/stores/servicePermissions', async () => {
  const { writable } = await vi.importActual<typeof SvelteStore>('svelte/store');
  return { projectPermissions: writable({ permissions: null, loading: true, error: '' }), serviceCapabilities: writable(() => true), serviceDenials: writable(() => false) };
});
vi.mock('$lib/api/palimpsestAssets', async (original) => {
  const module = await original<typeof AssetModule>();
  return { ...module, assetApi: {
    hub: vi.fn(), environments: vi.fn(), context: vi.fn(), packages: vi.fn(), versions: vi.fn(),
    bundle: vi.fn(), packageDownload: vi.fn(), consume: vi.fn(), consumeStatus: vi.fn(), resources: vi.fn(), cleanup: vi.fn(),
  } };
});
const permissions = projectPermissions as Writable<{ permissions: ProjectPermissions | null; loading: boolean; error: string }>;
const identity = { token: 'browser-jwt', projectId: 'project-a', userId: 'user-a' };
const digest = `sha256:${'a'.repeat(64)}`;
const otherDigest = `sha256:${'b'.repeat(64)}`;
const pkg: PackageSummary = { package_id: 'package-a', project_id: identity.projectId, namespace: 'private-namespace', name: 'torch-training', package_type: 'runtime-bundle', visibility: 'project', tags: [{ tag: 'stable', digest }, { tag: 'candidate', digest: otherDigest }], platforms: [], version_count: 2, latest_pushed_at: null, latest_pushed_by: identity.userId };
const context: ProjectContext = { project_id: identity.projectId, project_name: 'Project A', namespace: pkg.namespace, package_authority: 'registry.example', capabilities: { packages_read: true, packages_download: true, packages_write: false, keys_issue: false, keys_revoke: false } };
function version(root: string): PackageVersion {
  return { project_id: identity.projectId, namespace: pkg.namespace, package: pkg.name, root_digest: root, root_media_type: 'application/vnd.oci.image.manifest.v1+json', root_descriptor: { digest: root, mediaType: 'application/vnd.oci.image.manifest.v1+json', size: 3 }, graph: { [root]: { media_type: 'application/vnd.oci.image.manifest.v1+json', size_bytes: 3 } }, platforms: [], archive_digest: digest, archive_size_bytes: 3, total_bytes: 3, provenance: {}, pushed_by: identity.userId, pushed_key_id: null, pushed_at: '2026-10-25T00:00:00Z' };
}
const originalLocale = getLocale();
const initialAuth = get(auth);
const initialClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
const initialAuthReady = get(authReady), initialLogout = get(logoutInProgress), initialSwitching = get(projectSwitching);
beforeEach(() => {
  initLocale('en');
  permissions.set({ permissions: { is_owner: false, is_manager: false, can_write: true, service_permissions: { palimpsest: ['palimpsest-inventory_reader', 'palimpsest-download_user'] } }, loading: false, error: '' });
  auth.set({ ...initialAuth, token: identity.token, projectId: identity.projectId, userId: identity.userId, canWrite: true, domainId: 'working-domain', identityDomainId: 'identity-domain' });
  authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
  vi.mocked(assetApi.hub).mockResolvedValue({ items: [], offset: 0, next_offset: null, has_more: false });
  vi.mocked(assetApi.environments).mockResolvedValue({ items: [], offset: 0, next_offset: null, has_more: false });
  vi.mocked(assetApi.context).mockResolvedValue(context);
  vi.mocked(assetApi.packages).mockResolvedValue({ project_id: identity.projectId, namespace: pkg.namespace, items: [pkg], next_cursor: null });
  vi.mocked(assetApi.versions).mockResolvedValue({ project_id: identity.projectId, namespace: pkg.namespace, items: [version(digest), version(otherDigest)], next_cursor: null });
  vi.mocked(assetApi.packageDownload).mockResolvedValue(new Blob(['private-bundle']));
});
afterEach(() => {
  cleanup(); auth.set(initialAuth); initLocale(originalLocale); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals();
  authReady.set(initialAuthReady); logoutInProgress.set(initialLogout); projectSwitching.set(initialSwitching);
  if (initialClipboard) Object.defineProperty(navigator, 'clipboard', initialClipboard);
  else Reflect.deleteProperty(navigator, 'clipboard');
});

it('opens a real controller package selection, chooses its immutable version and offers safe executable local guidance', async () => {
  const onGuide = vi.fn(), writeText = vi.fn(async (_text: string) => {});
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  render(AssetSearchPanel, { identity, onGuide });
  const card = (await screen.findByRole('heading', { name: pkg.name })).closest('article')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  const select = await screen.findByLabelText('Version or tag') as HTMLSelectElement;
  expect(select.value).toBe(digest);
  await fireEvent.change(select, { target: { value: otherDigest } });
  expect(select.value).toBe(otherDigest);
  expect(screen.queryByRole('region', { name: 'Local verification and execution' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Copy commands' })).toBeNull();
  await fireEvent.click(screen.getByRole('checkbox', { name: 'I verified that my installed client supports bundle unpack' }));
  expect(screen.getByRole('region', { name: 'Local verification and execution' }).textContent)
    .toContain(`palimpsest pull 'registry.example/private-namespace/torch-training@${otherDigest}'`);
  await fireEvent.click(screen.getByRole('button', { name: 'Browser download' }));
  const commands = screen.getByRole('region', { name: 'Local verification and execution' });
  expect(commands.textContent).toContain(`palimpsest bundle unpack ./palimpsest-runtime-${otherDigest.slice(7)}.oci.tar --output ./palimpsest-bundle-${otherDigest.slice(7)}`);
  expect(commands.textContent).toContain(`palimpsest run ./palimpsest-bundle-${otherDigest.slice(7)}`);
  expect(commands.textContent).not.toContain(`palimpsest-runtime-${digest.slice(7)}.oci.tar`);
  expect(commands.textContent).not.toContain(identity.token);
  await fireEvent.click(screen.getByRole('button', { name: 'Copy commands' }));
  await vi.waitFor(() => expect(writeText).toHaveBeenCalledOnce());
  expect(writeText.mock.calls[0][0]).toBe(commands.textContent);
  await fireEvent.click(screen.getByRole('button', { name: 'Local SDK setup' }));
  expect(onGuide).toHaveBeenCalledOnce();
  expect(assetApi.packageDownload).not.toHaveBeenCalled();
  expect(assetApi.consume).not.toHaveBeenCalled();
});

it('does not let API display names become shell commands or output paths', async () => {
  const malicious = 'torch; $(touch /tmp/asset-name-injection)';
  vi.mocked(assetApi.packages).mockResolvedValueOnce({ project_id: identity.projectId, namespace: pkg.namespace, items: [{ ...pkg, name: malicious }], next_cursor: null });
  vi.mocked(assetApi.versions).mockResolvedValueOnce({ project_id: identity.projectId, namespace: pkg.namespace, items: [{ ...version(digest), package: malicious }], next_cursor: null });
  render(AssetSearchPanel, { identity, onGuide: vi.fn() });
  const card = (await screen.findByRole('heading', { name: malicious })).closest('article')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  await screen.findByLabelText('Version or tag');
  expect(screen.queryByRole('region', { name: 'Local verification and execution' })).toBeNull();
  await fireEvent.click(screen.getByRole('checkbox', { name: 'I verified that my installed client supports bundle unpack' }));
  expect(screen.getByText('The native registry reference is not configured. Use the authorized browser download or ask the operator to configure the reference authority.')).toBeTruthy();
  await fireEvent.click(screen.getByRole('button', { name: 'Browser download' }));
  const commands = screen.getByRole('region', { name: 'Local verification and execution' }).textContent!;
  expect(screen.getByRole('heading', { name: `Use ${malicious}` })).toBeTruthy();
  expect(commands).not.toContain(malicious);
  expect(commands).not.toContain('$(touch');
  expect(commands).toContain(`palimpsest-runtime-${digest.slice(7)}.oci.tar`);
});

it('removes a private use selection immediately when permissions become unavailable', async () => {
  render(AssetSearchPanel, { identity, onGuide: vi.fn() });
  const card = (await screen.findByRole('heading', { name: pkg.name })).closest('article')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  await screen.findByLabelText('Version or tag');
  permissions.set({ permissions: null, loading: false, error: 'Permission graph unavailable' });
  await tick();
  expect(screen.queryByRole('heading', { name: `Use ${pkg.name}` })).toBeNull();
  expect(screen.queryByRole('region', { name: 'Local verification and execution' })).toBeNull();
  expect(screen.getByText('Permission graph unavailable')).toBeTruthy();
  expect(assetApi.packageDownload).not.toHaveBeenCalled();
});

it('requests the chosen immutable version but never saves its late bytes after the use panel closes', async () => {
  const createObjectURL = vi.fn(() => 'blob:must-not-be-created');
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL: vi.fn() }));
  const pending = Promise.withResolvers<Blob>();
  vi.mocked(assetApi.packageDownload).mockReturnValueOnce(pending.promise);
  render(AssetSearchPanel, { identity, onGuide: vi.fn() });
  const card = (await screen.findByRole('heading', { name: pkg.name })).closest('article')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  const select = await screen.findByLabelText('Version or tag');
  await fireEvent.change(select, { target: { value: otherDigest } });
  await fireEvent.click(screen.getByRole('button', { name: 'Browser download' }));
  await fireEvent.click(screen.getByRole('button', { name: 'Download complete bundle' }));
  expect(assetApi.packageDownload).toHaveBeenCalledWith(identity, expect.any(AbortSignal), pkg.name, otherDigest);
  const downloadSignal = vi.mocked(assetApi.packageDownload).mock.calls.at(-1)![1];
  await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(downloadSignal.aborted).toBe(true);
  pending.resolve(new Blob(['private bytes arriving after close']));
  await pending.promise; await tick();
  expect(createObjectURL).not.toHaveBeenCalled();
  expect(screen.queryByRole('heading', { name: `Use ${pkg.name}` })).toBeNull();
});

it('saves the selected private version when its same-session identity prop rotates during download', async () => {
  const createObjectURL = vi.fn((_blob: Blob) => 'blob:refreshed-private-bundle'), revokeObjectURL = vi.fn();
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL }));
  const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const pending = Promise.withResolvers<Blob>();
  vi.mocked(assetApi.packageDownload).mockReturnValueOnce(pending.promise);
  const onGuide = vi.fn();
  const mounted = render(AssetSearchPanel, { identity, onGuide });
  const card = (await screen.findByRole('heading', { name: pkg.name })).closest('article')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  await screen.findByLabelText('Version or tag');
  await fireEvent.click(screen.getByRole('button', { name: 'Browser download' }));
  await fireEvent.click(screen.getByRole('button', { name: 'Download complete bundle' }));
  const downloadSignal = vi.mocked(assetApi.packageDownload).mock.calls.at(-1)![1];
  const rotated = { ...identity, token: 'ordinary-rotated-jwt' };
  const current = get(auth);
  // Exercise the one-use native refresh mapping that preserves existing authority,
  // rather than temporarily publishing an unverified raw token.
  setAuth(refreshAuthState({ token: rotated.token, user_id: identity.userId, username: 'Researcher',
    project_id: identity.projectId, project_name: 'Project A', expires_at: null, can_write: true,
    domain_id: 'working-domain', identity_domain_id: 'identity-domain', identity_domain_name: 'Accounts' }, current));
  expect(get(authReady)).toBe(true);
  await mounted.rerender({ identity: rotated, onGuide });
  expect(downloadSignal.aborted).toBe(false);
  const bytes = new Blob(['private verified bundle']);
  pending.resolve(bytes);
  await vi.waitFor(() => expect(createObjectURL).toHaveBeenCalledWith(bytes));
  expect(createObjectURL).toHaveBeenCalledOnce();
  expect(anchorClick).toHaveBeenCalledOnce();
  await vi.waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:refreshed-private-bundle'), { timeout: 2000 });
});

it.each([
  { local_supported: false, base_image_digest: otherDigest },
  { local_supported: true, base_image_digest: null },
])('does not offer execution or browser bytes for incompatible Hub metadata %j', async (compatibility) => {
  const row: ReusableAsset = { id: 'hub-incompatible', name: 'Not a bootable environment', kind: 'layer-bundle', blob_digest: digest,
    chain_id: digest, arch: 'x86_64', ubuntu_base: '24.04', size_bytes: 3, created_at: null, visibility: 'public', layer_count: 1,
    chain_complete: true, download_allowed: true, local_reason: null, ...compatibility };
  vi.mocked(assetApi.hub).mockResolvedValue({ items: [row], offset: 0, has_more: false, next_offset: null });
  render(AssetSearchPanel, { identity, onGuide: vi.fn() });
  const card = (await screen.findByText(row.name)).closest<HTMLElement>('article, tr')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  expect(screen.queryByRole('region', { name: 'Local verification and execution' })).toBeNull();
  expect(screen.getByText('This bundle lacks a compatible boot image or architecture metadata. Ask the operator for a complete runnable environment bundle.')).toBeTruthy();
  await fireEvent.click(screen.getByRole('button', { name: 'Browser download' }));
  expect((screen.getByRole('button', { name: 'Download complete bundle' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole('region', { name: 'Local verification and execution' })).toBeNull();
  expect(assetApi.bundle).not.toHaveBeenCalled();
});

it('retains an accepted cloud receipt and replay lock across real outer workspace tab changes', async () => {
  const environment: CloudEnvironment = { id: 'managed-training', name: 'Managed training', kind: 'layer-bundle', blob_digest: digest,
    chain_id: digest, arch: 'x86_64', ubuntu_base: '24.04', size_bytes: 3, created_at: null, visibility: 'public', layer_count: 1,
    chain_complete: true, download_allowed: false, local_supported: true, local_reason: null, base_image_digest: otherDigest,
    source: 'managed', revision: otherDigest, cloud_supported: true, cloud_reason: null };
  vi.mocked(assetApi.environments).mockResolvedValue({ items: [environment], offset: 0, has_more: false, next_offset: null });
  vi.mocked(assetApi.resources).mockResolvedValue({ flavors: [
    { id: 'flavor-a', name: 'm1.small', display_name: 'cpu.2c_4g', vcpus: 2, ram: 4096 },
    { id: 'flavor-b', name: 'dedicated-small', display_name: 'cpu.2c_4g', vcpus: 2, ram: 4096, extra_specs: { 'hw:cpu_policy': 'dedicated' } },
  ], networks: [{ id: 'network-a', name: 'Training network' }], keys: [{ name: 'training-key' }] });
  vi.mocked(assetApi.consume).mockResolvedValue({ consume_id: 71, server_id: 'server-71', status: 'building', ready: false, revision: otherDigest, project_id: identity.projectId });
  render(PackagesPage);
  const card = (await screen.findByRole('heading', { name: environment.name })).closest('article')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  await fireEvent.click(screen.getByRole('button', { name: 'Create cloud instance' }));
  const modal = await screen.findByRole('dialog', { name: 'Create cloud instance' });
  await vi.waitFor(() => expect(assetApi.resources).toHaveBeenCalledOnce());
  await fireEvent.input(within(modal).getByLabelText('Instance name'), { target: { value: 'training-vm' } });
  for (const [label, option] of [['Flavor', /cpu\.2c_4g.*dedicated-small.*flavor-b/], ['Network', /Training network/], ['SSH keypair', /training-key/]] as const) {
    await fireEvent.click(within(modal).getByLabelText(label));
    await fireEvent.click(await screen.findByRole('option', { name: option }));
  }
  await fireEvent.click(within(modal).getByRole('button', { name: 'Create cloud instance' }));
  await screen.findByRole('heading', { name: 'Cloud operation #71' });
  expect(screen.getByText('Accepted or still being verified. A request is not proof that the VM is ready.')).toBeTruthy();
  await fireEvent.click(screen.getByRole('tab', { name: 'Local use guide' }));
  expect(screen.queryByRole('heading', { name: 'Cloud operation #71' })).toBeNull();
  await fireEvent.click(screen.getByRole('tab', { name: 'Find reusable assets' }));
  await screen.findByRole('heading', { name: 'Cloud operation #71' });
  expect((screen.getByRole('button', { name: 'Create cloud instance' }) as HTMLButtonElement).disabled).toBe(true);
  expect(assetApi.consume).toHaveBeenCalledOnce();
  expect(assetApi.consume).toHaveBeenCalledWith(identity, expect.any(AbortSignal), environment.id, expect.objectContaining({ flavor_id: 'flavor-b' }));
});

it('cancels private browser bytes when a rotated token has not regained verified authority', async () => {
  const createObjectURL = vi.fn(() => 'blob:must-not-save-unverified');
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL: vi.fn() }));
  const pending = Promise.withResolvers<Blob>();
  vi.mocked(assetApi.packageDownload).mockReturnValueOnce(pending.promise);
  const onGuide = vi.fn(), mounted = render(AssetSearchPanel, { identity, onGuide });
  const card = (await screen.findByRole('heading', { name: pkg.name })).closest('article')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  await screen.findByLabelText('Version or tag');
  await fireEvent.click(screen.getByRole('button', { name: 'Browser download' }));
  await fireEvent.click(screen.getByRole('button', { name: 'Download complete bundle' }));
  const downloadSignal = vi.mocked(assetApi.packageDownload).mock.calls.at(-1)![1];
  const unverified = { ...identity, token: 'not-yet-verified-jwt' };
  auth.update((state) => ({ ...state, token: unverified.token }));
  await mounted.rerender({ identity: unverified, onGuide });
  expect(get(authReady)).toBe(false);
  expect(downloadSignal.aborted).toBe(true);
  pending.resolve(new Blob(['bytes from unverified scope']));
  await pending.promise; await tick();
  expect(createObjectURL).not.toHaveBeenCalled();
});

async function catalogCloudForm() {
  const environment: CloudEnvironment = { id: 'managed-training', name: 'Managed training', kind: 'layer-bundle', blob_digest: digest,
    chain_id: digest, arch: 'x86_64', ubuntu_base: '24.04', size_bytes: 3, created_at: null, visibility: 'public', layer_count: 1,
    chain_complete: true, download_allowed: false, local_supported: true, local_reason: null, base_image_digest: otherDigest,
    source: 'managed', revision: otherDigest, cloud_supported: true, cloud_reason: null };
  vi.mocked(assetApi.environments).mockResolvedValue({ items: [environment], offset: 0, has_more: false, next_offset: null });
  vi.mocked(assetApi.resources).mockResolvedValue({ flavors: [
    { id: 'required', name: 'Training GPU', vcpus: 4, ram: 8192, usage_schedule_required: true },
    { id: 'large', name: 'Large CPU', vcpus: 12, ram: 32768 },
    { id: 'small', name: 'Small CPU', vcpus: 2, ram: 4096, usage_schedule_required: false },
  ], networks: [{ id: 'network-a', name: 'Training network' }], keys: [{ name: 'training-key' }] });
  vi.mocked(assetApi.consume).mockResolvedValue({ consume_id: 72, server_id: 'server-72', status: 'building', ready: false, revision: otherDigest, project_id: identity.projectId });
  const mounted = render(AssetSearchPanel, { identity, onGuide: vi.fn() });
  const card = (await screen.findByRole('heading', { name: environment.name })).closest('article')!;
  await fireEvent.click(within(card).getByRole('button', { name: 'Use asset' }));
  await fireEvent.click(screen.getByRole('button', { name: 'Create cloud instance' }));
  const modal = await screen.findByRole('dialog', { name: 'Create cloud instance' });
  await vi.waitFor(() => expect(assetApi.resources).toHaveBeenCalledOnce());
  await fireEvent.input(within(modal).getByLabelText('Instance name'), { target: { value: 'scheduled-vm' } });
  for (const [label, option] of [['Flavor', /Training GPU/], ['Network', /Training network/], ['SSH keypair', /training-key/]] as const) {
    await fireEvent.click(within(modal).getByLabelText(label));
    await fireEvent.click(await screen.findByRole('option', { name: option }));
  }
  return { mounted, modal, submit: within(modal).getByRole('button', { name: 'Create cloud instance' }) as HTMLButtonElement };
}

it('sends the creation-clock calendar-month default, archive and retained volumes from the catalog form', async () => {
  const { submit } = await catalogCloudForm();
  expect((document.querySelector('#asset-usage-action') as HTMLSelectElement).value).toBe('shelve');
  expect(screen.queryByRole('checkbox', { name: 'Also permanently delete all attached volumes' })).toBeNull();
  await fireEvent.click(submit);
  expect(assetApi.consume).toHaveBeenCalledWith(identity, expect.any(AbortSignal), 'managed-training', expect.objectContaining({
    usage_schedule: { expires_at: null, expiry_action: 'shelve', delete_volumes: false, reason: '' },
  }));
});

it('blocks a later catalog deadline without a reason and sends changed deletion consent explicitly', async () => {
  const { submit } = await catalogCloudForm();
  const later = new Date(defaultUsageDraft().defaultExpiresAt); later.setUTCDate(later.getUTCDate() + 2);
  await fireEvent.input(document.querySelector('#asset-usage-expires')!, { target: { value: toLocalDateTime(later.toISOString()) } });
  expect(submit.disabled).toBe(true);
  await fireEvent.click(submit);
  expect(assetApi.consume).not.toHaveBeenCalled();
  await fireEvent.input(document.querySelector('#asset-usage-reason')!, { target: { value: '  Continuing research  ' } });
  await fireEvent.change(document.querySelector('#asset-usage-action')!, { target: { value: 'delete' } });
  const consent = screen.getByRole('checkbox', { name: 'Also permanently delete all attached volumes' }) as HTMLInputElement;
  expect(consent.checked).toBe(false);
  await fireEvent.click(consent);
  expect(submit.disabled).toBe(false);
  await fireEvent.click(submit);
  expect(assetApi.consume).toHaveBeenCalledWith(identity, expect.any(AbortSignal), 'managed-training', expect.objectContaining({
    usage_schedule: { expires_at: expect.any(String), expiry_action: 'delete', delete_volumes: true, reason: 'Continuing research' },
  }));
});

it('resets catalog consent after changed flavors and immediately drops drafts on same-tick actor ABA', async () => {
  const { modal } = await catalogCloudForm();
  await fireEvent.change(document.querySelector('#asset-usage-action')!, { target: { value: 'delete' } });
  await fireEvent.click(screen.getByRole('checkbox', { name: 'Also permanently delete all attached volumes' }));
  await fireEvent.click(within(modal).getByLabelText('Flavor'));
  await fireEvent.click(screen.getByRole('option', { name: /Large CPU/ }));
  expect((document.querySelector('#asset-usage-action') as HTMLSelectElement).value).toBe('shelve');
  const current = get(auth);
  auth.set({ ...current, projectId: 'project-b' });
  auth.set(current);
  await tick();
  expect(screen.queryByRole('dialog', { name: 'Create cloud instance' })).toBeNull();
  expect(document.querySelector('#asset-usage-action')).toBeNull();
  expect(assetApi.consume).not.toHaveBeenCalled();
});

it('reopens the same catalog asset with archive and retained disks after an accepted launch becomes active', async () => {
  const { submit } = await catalogCloudForm();
  await fireEvent.change(document.querySelector('#asset-usage-action')!, { target: { value: 'delete' } });
  await fireEvent.click(screen.getByRole('checkbox', { name: 'Also permanently delete all attached volumes' }));
  await fireEvent.click(submit);
  await screen.findByRole('heading', { name: 'Cloud operation #72' });
  expect(assetApi.consume).toHaveBeenCalledWith(identity, expect.any(AbortSignal), 'managed-training', expect.objectContaining({
    usage_schedule: { expires_at: null, expiry_action: 'delete', delete_volumes: true, reason: '' },
  }));
  vi.mocked(assetApi.consumeStatus).mockResolvedValue({ consume_id: 72, server_id: 'server-72', status: 'active', ready: true, revision: otherDigest, project_id: identity.projectId });
  await fireEvent.click(await screen.findByRole('button', { name: 'Refresh status' }));
  const reopen = screen.getByRole('button', { name: 'Create cloud instance' });
  await vi.waitFor(() => expect((reopen as HTMLButtonElement).disabled).toBe(false));
  await fireEvent.click(reopen);
  const modal = await screen.findByRole('dialog', { name: 'Create cloud instance' });
  expect((document.querySelector('#asset-usage-action') as HTMLSelectElement).value).toBe('shelve');
  expect(within(modal).queryByRole('checkbox', { name: 'Also permanently delete all attached volumes' })).toBeNull();
  await vi.waitFor(() => expect(assetApi.resources).toHaveBeenCalledTimes(2));
  await fireEvent.click(within(modal).getByRole('button', { name: 'Create cloud instance' }));
  expect(vi.mocked(assetApi.consume).mock.lastCall![3].usage_schedule).toEqual({ expires_at: null, expiry_action: 'shelve', delete_volumes: false, reason: '' });
});

it('rechecks the clock at catalog submission when an explicitly selected deadline expires while idle', async () => {
  const { modal, submit } = await catalogCloudForm();
  const deadline = new Date(Date.now() + 120_000);
  await fireEvent.input(document.querySelector('#asset-usage-expires')!, { target: { value: toLocalDateTime(deadline.toISOString()) } });
  expect(submit.disabled).toBe(false);
  vi.useFakeTimers({ toFake: ['Date'] });
  try {
    vi.setSystemTime(deadline.getTime() + 60_000);
    await fireEvent.click(submit);
    expect(assetApi.consume).not.toHaveBeenCalled();
    expect(within(modal).getByText('Choose a future date and time.')).toBeTruthy();
    expect(submit.disabled).toBe(true);
  } finally {
    vi.useRealTimers();
  }
});
