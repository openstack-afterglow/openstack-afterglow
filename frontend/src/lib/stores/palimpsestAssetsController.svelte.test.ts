import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPalimpsestAssetsController } from './palimpsestAssetsController.svelte';
import { assetApi } from '$lib/api/palimpsestAssets';
import type { AssetIdentity, AssetPage, CloudEnvironment, CloudRequest, ConsumeResult, ReusableAsset } from '$lib/api/palimpsestAssets';
import type { PackageSummary, PackageVersion, ProjectContext, ScopedPage } from '$lib/api/palimpsestPackages';

const actorA: AssetIdentity = { token: 'jwt-a', projectId: 'project-a', userId: 'user-a', sessionId: 'session-a' };
const digest = `sha256:${'a'.repeat(64)}`;
const otherDigest = `sha256:${'b'.repeat(64)}`;
const revision = `sha256:${'c'.repeat(64)}`;
const asset: ReusableAsset = { id: 'asset-a', name: 'torch training', kind: 'layer-bundle', blob_digest: digest, chain_id: digest, arch: 'x86_64', ubuntu_base: '24.04', size_bytes: 3, created_at: null, visibility: 'public', layer_count: 2, chain_complete: true, download_allowed: true, base_image_digest: otherDigest, local_supported: true, local_reason: null };
const environment: CloudEnvironment = { ...asset, id: 'environment-a', source: 'managed', revision, cloud_supported: true, cloud_reason: null };
const pkg: PackageSummary = { package_id: 'package-a', project_id: actorA.projectId, namespace: 'verified-namespace', name: 'training', package_type: 'runtime-bundle', visibility: 'project', tags: [{ tag: 'latest', digest }], platforms: [], version_count: 2, latest_pushed_at: null, latest_pushed_by: actorA.userId };
const context: ProjectContext = { project_id: actorA.projectId, project_name: 'Project A', namespace: pkg.namespace, package_authority: 'registry.example', capabilities: { packages_read: true, packages_download: true, packages_write: false, keys_issue: false, keys_revoke: false } };
function version(root = digest): PackageVersion {
  return { project_id: actorA.projectId, namespace: pkg.namespace, package: pkg.name, root_digest: root, root_media_type: 'application/vnd.oci.image.manifest.v1+json', root_descriptor: { digest: root, mediaType: 'application/vnd.oci.image.manifest.v1+json', size: 3 }, graph: { [root]: { media_type: 'application/vnd.oci.image.manifest.v1+json', size_bytes: 3 } }, platforms: [], archive_digest: digest, archive_size_bytes: 3, total_bytes: 3, provenance: {}, pushed_by: actorA.userId, pushed_key_id: null, pushed_at: '2026-10-25T00:00:00Z' };
}
const page = <T>(items: T[], offset = 0): AssetPage<T> => ({ items, offset, has_more: true, next_offset: offset + 20 });
const privatePage = <T>(items: T[], next_cursor: string | null = null): ScopedPage<T> => ({ project_id: actorA.projectId, namespace: pkg.namespace, items, next_cursor });
const body: CloudRequest = { revision, flavor_id: 'flavor-a', network_id: 'network-a', key_name: 'caller-key', server_name: 'my-server', ssh_username: 'ubuntu' };
const accepted: ConsumeResult = { consume_id: 17, server_id: 'server-a', status: 'building', ready: false, revision, project_id: actorA.projectId };
const controllers: { dispose: () => void }[] = [];
afterEach(() => { for (const controller of controllers.splice(0)) controller.dispose(); });
function setup() {
  let actor: AssetIdentity | null = { ...actorA };
  let permitted = true, downloadable = true, writable = true;
  const api: typeof assetApi = {
    hub: vi.fn(async (_actor, _signal, _q, offset = 0) => page([asset], offset)),
    environments: vi.fn(async (_actor, _signal, _q, offset = 0) => page([environment], offset)),
    context: vi.fn(async () => context),
    packages: vi.fn(async () => privatePage([pkg], 'next-private-page')),
    versions: vi.fn(async () => privatePage([version(), version(otherDigest)])),
    bundle: vi.fn(async () => new Blob(['bundle'])),
    packageDownload: vi.fn(async () => new Blob(['package'])),
    consume: vi.fn(async () => accepted),
    consumeStatus: vi.fn(async () => ({ ...accepted, status: 'active', ready: true })),
    cleanup: vi.fn(async () => ({ ...accepted, server_id: null, status: 'deleted', ready: false })),
    resources: vi.fn(async () => ({ flavors: [], networks: [], keys: [] })),
  };
  const controller = createPalimpsestAssetsController(() => actor, () => permitted, () => downloadable, () => writable, api);
  controllers.push(controller);
  controller.bind();
  return { controller, api,
    bind: (next: AssetIdentity | null) => { actor = next; controller.bind(); },
    permissions: (read: boolean, download = read, write = download) => { permitted = read; downloadable = download; writable = write; controller.bind(); },
  };
}
async function ready(controller: { readonly packages: ScopedPage<PackageSummary> | null }) {
  await vi.waitFor(() => expect(controller.packages?.items[0].name).toBe(pkg.name));
}

describe('asset search source isolation', () => {
  it('resets every source pagination on query change without reusing a private cursor', async () => {
    const { controller, api } = setup(); await ready(controller);
    await controller.load('hub', 40);
    await controller.load('packages', 'next-private-page');
    await controller.load('environments', 20);
    expect(controller.hub?.offset).toBe(40);
    await controller.search('  tensorflow  ');
    expect(controller.query).toBe('tensorflow');
    expect(vi.mocked(api.hub).mock.calls.at(-1)?.slice(2)).toEqual(['tensorflow', 0]);
    expect(vi.mocked(api.environments).mock.calls.at(-1)?.slice(2)).toEqual(['tensorflow', 0]);
    expect(vi.mocked(api.packages).mock.calls.at(-1)?.slice(2)).toEqual(['tensorflow', undefined]);
    expect(controller.hub?.offset).toBe(0);
    expect(controller.environments?.offset).toBe(0);
  });

  it('retains successful sources and their paging when private inventory fails or retries', async () => {
    const { controller, api } = setup(); await ready(controller);
    vi.mocked(api.packages).mockRejectedValueOnce(new Error('Native private inventory unavailable'));
    await controller.search('torch');
    expect(controller.errors.packages).toContain('unavailable');
    expect(controller.packages).toBeNull();
    expect(controller.hub?.items).toEqual([asset]);
    expect(controller.environments?.items).toEqual([environment]);
    await controller.load('hub', 20);
    const hubCalls = vi.mocked(api.hub).mock.calls.length;
    await controller.load('packages');
    expect(controller.errors.packages).toBeUndefined();
    expect(controller.packages?.items).toEqual([pkg]);
    expect(controller.hub?.offset).toBe(20);
    expect(api.hub).toHaveBeenCalledTimes(hubCalls);
  });

  it('does not restore a prior query page after the new search completes', async () => {
    const { controller, api } = setup(); await ready(controller);
    const pending = Promise.withResolvers<AssetPage<ReusableAsset>>();
    vi.mocked(api.hub).mockReturnValueOnce(pending.promise);
    const oldPage = controller.load('hub', 20);
    const oldSignal = vi.mocked(api.hub).mock.calls.at(-1)![1];
    await controller.search('new-query');
    pending.resolve(page([{ ...asset, name: 'stale-result' }], 20));
    await oldPage;
    expect(oldSignal.aborted).toBe(true);
    expect(controller.hub?.items[0].name).toBe(asset.name);
    expect(controller.hub?.offset).toBe(0);
  });

  it.each([
    { project_id: 'foreign-project' }, { namespace: 'foreign-namespace' },
  ])('rejects private inventory envelope mismatch %j', async (changed) => {
    const { controller, api } = setup(); await ready(controller);
    vi.mocked(api.packages).mockResolvedValueOnce({ ...privatePage([pkg]), ...changed });
    await controller.load('packages');
    expect(controller.packages).toBeNull(); expect(controller.errors.packages).toBeTruthy();
    expect(controller.hub?.items[0]).toEqual(asset);
  });

  it.each([{ project_id: 'foreign-project' }, { namespace: 'foreign-namespace' }])('rejects a private inventory row mismatch %j', async (changed) => {
    const { controller, api } = setup(); await ready(controller);
    vi.mocked(api.packages).mockResolvedValueOnce(privatePage([{ ...pkg, ...changed }]));
    await controller.load('packages');
    expect(controller.packages).toBeNull(); expect(controller.errors.packages).toBeTruthy();
  });

  it('does not query packages or register a namespace when the caller has none', async () => {
    const { controller, api } = setup(); await ready(controller);
    vi.mocked(api.context).mockResolvedValueOnce({ ...context, namespace: null });
    vi.mocked(api.packages).mockClear();
    await controller.load('packages');
    expect(controller.context?.namespace).toBeNull();
    expect(controller.packages?.items).toEqual([]);
    expect(api.packages).not.toHaveBeenCalled();
  });
});

describe('private actor and selected immutable version fences', () => {
  it.each(['projectId', 'userId', 'sessionId'] as const)('cancels private results across a %s ABA transition', async (field) => {
    const { controller, api, bind } = setup(); await ready(controller);
    const pending = Promise.withResolvers<ScopedPage<PackageSummary>>();
    vi.mocked(api.packages).mockReturnValueOnce(pending.promise);
    const oldLoad = controller.load('packages');
    await vi.waitFor(() => expect(api.packages).toHaveBeenCalledTimes(2));
    const oldSignal = vi.mocked(api.packages).mock.calls.at(-1)![1];
    bind({ ...actorA, [field]: 'other-actor-value' });
    bind({ ...actorA });
    await ready(controller);
    pending.resolve(privatePage([{ ...pkg, name: 'old-private-result' }]));
    await oldLoad;
    expect(oldSignal.aborted).toBe(true);
    expect(controller.packages?.items[0].name).toBe(pkg.name);
    expect(controller.selection).toBeNull();
  });

  it.each([{ project_id: 'foreign-project' }, { namespace: 'foreign-namespace' }, { package: 'another-package' }])('refuses a version row belonging to %j before any download', async (changed) => {
    const { controller, api } = setup(); await ready(controller);
    vi.mocked(api.versions).mockResolvedValueOnce(privatePage([{ ...version(), ...changed }]));
    await controller.select({ source: 'packages', asset: pkg });
    expect(controller.version).toBeNull();
    expect(controller.errors.versions).toBeTruthy();
    expect(await controller.download()).toBeNull();
    expect(api.packageDownload).not.toHaveBeenCalled();
  });

  it('downloads the chosen immutable digest, never the mutable latest tag', async () => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'packages', asset: pkg });
    controller.version = controller.versions!.items[1];
    expect(await controller.download()).toBeInstanceOf(Blob);
    expect(api.packageDownload).toHaveBeenCalledWith(actorA, expect.any(AbortSignal), pkg.name, otherDigest);
    expect(api.bundle).not.toHaveBeenCalled();
  });

  it('cannot use a foreign package version supplied after a valid selection', async () => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'packages', asset: pkg });
    controller.version = { ...version(), package: 'another-package' };
    expect(await controller.download()).toBeNull();
    expect(api.packageDownload).not.toHaveBeenCalled();
  });

  it('discards bytes if the selected version changes while its download is pending', async () => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'packages', asset: pkg });
    const pending = Promise.withResolvers<Blob>();
    vi.mocked(api.packageDownload).mockReturnValueOnce(pending.promise);
    const downloading = controller.download();
    const oldSignal = vi.mocked(api.packageDownload).mock.calls.at(-1)![1];
    controller.version = controller.versions!.items[1];
    pending.resolve(new Blob(['obsolete-private-bytes']));
    expect(await downloading).toBeNull();
    expect(oldSignal.aborted).toBe(true);
    expect(controller.version?.root_digest).toBe(otherDigest);
  });

  it('hides data and cancels download immediately when permission readiness is lost', async () => {
    const { controller, api, permissions } = setup(); await ready(controller);
    await controller.select({ source: 'hub', asset });
    const pending = Promise.withResolvers<Blob>(); vi.mocked(api.bundle).mockReturnValueOnce(pending.promise);
    const downloading = controller.download();
    const oldSignal = vi.mocked(api.bundle).mock.calls.at(-1)![1];
    permissions(false);
    expect(controller.selection).toBeNull(); expect(controller.packages).toBeNull();
    pending.resolve(new Blob(['must-not-save']));
    expect(await downloading).toBeNull(); expect(oldSignal.aborted).toBe(true);
  });
});

describe('managed environment consume provenance and unknown outcomes', () => {
  it('preserves an in-flight consume and its replay lock through ordinary JWT rotation', async () => {
    const { controller, api, bind } = setup(); await ready(controller);
    await controller.search('torch');
    await controller.select({ source: 'environments', asset: environment });
    const pending = Promise.withResolvers<ConsumeResult>();
    vi.mocked(api.consume).mockReturnValueOnce(pending.promise);
    const creating = controller.create(body);
    const consumeSignal = vi.mocked(api.consume).mock.calls.at(-1)![1];
    bind({ ...actorA, token: 'jwt-rotated' });
    expect(consumeSignal.aborted).toBe(false);
    expect(controller.query).toBe('torch');
    expect(controller.consumeLocked).toBe(true);
    pending.resolve(accepted); await creating;
    expect(controller.consume).toEqual(accepted);
    await controller.create(body);
    expect(api.consume).toHaveBeenCalledOnce();
    await controller.refreshConsume();
    expect(api.consumeStatus).toHaveBeenCalledWith({ ...actorA, token: 'jwt-rotated' }, expect.any(AbortSignal), accepted.consume_id);
    expect(controller.consume?.ready).toBe(true);
  });

  it.each(['before', 'after'] as const)('preserves the accepted handle and replay lock when permission loading occurs %s consume completion', async (timing) => {
    const { controller, api, permissions } = setup(); await ready(controller);
    await controller.search('torch');
    await controller.select({ source: 'environments', asset: environment });
    const pending = Promise.withResolvers<ConsumeResult>();
    vi.mocked(api.consume).mockReturnValueOnce(pending.promise);
    const creating = controller.create(body);
    const consumeSignal = vi.mocked(api.consume).mock.calls.at(-1)![1];
    if (timing === 'after') { pending.resolve(accepted); await creating; }
    permissions(false);
    expect(controller.consume).toBeNull();
    expect(controller.query).toBe('torch');
    expect(consumeSignal.aborted).toBe(false);
    if (timing === 'before') { pending.resolve(accepted); await creating; }
    permissions(true); await ready(controller);
    expect(controller.consume).toEqual(accepted);
    expect(controller.consumeLocked).toBe(true);
    expect(controller.query).toBe('torch');
    await controller.select({ source: 'environments', asset: environment });
    await controller.create(body);
    expect(api.consume).toHaveBeenCalledOnce();
  });

  it('does not restore a consume accepted in a superseded login session after session ABA', async () => {
    const { controller, api, bind } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment });
    const pending = Promise.withResolvers<ConsumeResult>();
    vi.mocked(api.consume).mockReturnValueOnce(pending.promise);
    const creating = controller.create(body);
    const consumeSignal = vi.mocked(api.consume).mock.calls.at(-1)![1];
    bind({ ...actorA, sessionId: 'session-other' }); bind({ ...actorA });
    pending.resolve(accepted); await creating;
    expect(consumeSignal.aborted).toBe(true);
    expect(controller.consume).toBeNull();
    expect(controller.query).toBe('');
  });

  it('sends the exact selected immutable revision as the caller and tracks accepted-not-ready separately', async () => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment });
    await controller.create(body);
    expect(api.consume).toHaveBeenCalledWith(actorA, expect.any(AbortSignal), environment.id, body);
    expect(controller.consume).toEqual(accepted);
    expect(controller.consume?.ready).toBe(false);
    await controller.refreshConsume();
    expect(api.consumeStatus).toHaveBeenCalledWith(actorA, expect.any(AbortSignal), accepted.consume_id);
    expect(controller.consume?.ready).toBe(true);
    expect(api.consume).toHaveBeenCalledOnce();
  });

  it('refuses a revision other than the selected managed environment before POST', async () => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment });
    await controller.create({ ...body, revision: otherDigest });
    expect(api.consume).not.toHaveBeenCalled();
    expect(controller.consume).toBeNull();
  });

  it.each([{ project_id: 'foreign-project' }, { revision: otherDigest }])('refuses consume response mismatch %j', async (changed) => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment });
    vi.mocked(api.consume).mockResolvedValueOnce({ ...accepted, ...changed });
    await controller.create(body);
    expect(controller.consume).toBeNull(); expect(controller.errors.consume).toBeTruthy();
  });

  it.each([{ project_id: 'foreign-project' }, { revision: otherDigest }, { consume_id: 99 }])('does not replace the accepted operation with mismatched status %j', async (changed) => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment }); await controller.create(body);
    vi.mocked(api.consumeStatus).mockResolvedValueOnce({ ...accepted, ...changed, ready: true });
    await controller.refreshConsume();
    expect(controller.consume).toEqual(accepted); expect(controller.errors.status).toBeTruthy();
  });

  it('never replays an indeterminate POST after duplicate click, close/reopen, or a search', async () => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment });
    const pending = Promise.withResolvers<ConsumeResult>();
    vi.mocked(api.consume).mockReturnValueOnce(pending.promise);
    const creating = controller.create(body);
    await controller.create(body);
    expect(api.consume).toHaveBeenCalledOnce();
    pending.reject(new TypeError('Connection lost after request transmission'));
    await creating;
    expect(controller.errors.consume).toBeTruthy();
    await controller.create(body);
    controller.close(); await controller.select({ source: 'environments', asset: environment });
    await controller.create(body);
    await controller.search('torch'); await controller.select({ source: 'environments', asset: environment });
    await controller.create(body);
    expect(api.consume).toHaveBeenCalledOnce();
    expect(controller.consume?.ready).not.toBe(true);
  });
});

describe('tracked cloud operation cleanup', () => {
  it('releases the replay fence only after the exact accepted operation reports deleted', async () => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment }); await controller.create(body);
    expect(controller.consumeLocked).toBe(true);
    await controller.cleanup();
    expect(controller.consume?.status).toBe('deleted');
    expect(controller.consume?.server_id).toBeNull();
    expect(controller.consumeLocked).toBe(false);
    await controller.create(body);
    expect(api.consume).toHaveBeenCalledTimes(2);
  });

  it.each([{ project_id: 'foreign-project' }, { consume_id: 99 }, { revision: otherDigest }])('rejects cleanup receipt mismatch %j without replacing the tracked operation', async (changed) => {
    const { controller, api } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment }); await controller.create(body);
    vi.mocked(api.cleanup).mockResolvedValueOnce({ ...accepted, status: 'deleted', ...changed });
    await controller.cleanup();
    expect(controller.consume).toEqual(accepted);
    expect(controller.errors.cleanup).toBeTruthy();
    expect(controller.consumeLocked).toBe(true);
    await controller.create(body);
    expect(api.consume).toHaveBeenCalledOnce();
  });

  it('does not clean up without write authority or without a tracked accepted operation', async () => {
    const { controller, api, permissions } = setup(); await ready(controller);
    await controller.cleanup(); expect(api.cleanup).not.toHaveBeenCalled();
    await controller.select({ source: 'environments', asset: environment }); await controller.create(body);
    permissions(true, true, false);
    await controller.cleanup();
    expect(api.cleanup).not.toHaveBeenCalled();
    expect(controller.consume).toEqual(accepted);
    expect(controller.consumeLocked).toBe(true);
  });

  it('keeps unknown cleanup outcomes locked and never automatically retries during reads or rebinding', async () => {
    const { controller, api, bind } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment }); await controller.create(body);
    vi.mocked(api.cleanup).mockRejectedValueOnce(new TypeError('Connection lost after DELETE transmission'));
    await controller.cleanup();
    expect(controller.errors.cleanup).toBeTruthy();
    expect(controller.consume).toEqual(accepted);
    expect(controller.consumeLocked).toBe(true);
    bind({ ...actorA, token: 'rotated-jwt' });
    await controller.search('torch');
    vi.mocked(api.consumeStatus).mockResolvedValueOnce(accepted);
    await controller.refreshConsume();
    expect(api.cleanup).toHaveBeenCalledOnce();
    expect(controller.consumeLocked).toBe(true);
    await controller.select({ source: 'environments', asset: environment });
    await controller.create(body); expect(api.consume).toHaveBeenCalledOnce();
  });

  it.each(['bind', 'subscription'] as const)('never silently loses a transmitted cleanup outcome across temporary permission loss through %s', async (transition) => {
    const { controller, api, permissions } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment }); await controller.create(body);
    const pending = Promise.withResolvers<ConsumeResult>();
    vi.mocked(api.cleanup).mockReturnValueOnce(pending.promise);
    const cleaning = controller.cleanup();
    if (transition === 'subscription') controller.pauseAuthority();
    permissions(false);
    expect(controller.consume).toBeNull();
    permissions(true); await ready(controller);
    pending.resolve({ ...accepted, status: 'deleted', server_id: null }); await cleaning;
    const acknowledged = controller.consume?.status === 'deleted';
    const explicitlyUnknown = !!controller.errors.cleanup;
    expect(acknowledged || explicitlyUnknown).toBe(true);
    if (acknowledged) expect(controller.consumeLocked).toBe(false);
    else expect(controller.consumeLocked).toBe(true);
    expect(api.cleanup).toHaveBeenCalledOnce();
  });

  it('cannot apply late deleted bytes from a superseded session', async () => {
    const { controller, api, bind } = setup(); await ready(controller);
    await controller.select({ source: 'environments', asset: environment }); await controller.create(body);
    const pending = Promise.withResolvers<ConsumeResult>();
    vi.mocked(api.cleanup).mockReturnValueOnce(pending.promise);
    const cleaning = controller.cleanup();
    const cleanupSignal = vi.mocked(api.cleanup).mock.calls.at(-1)![1];
    bind({ ...actorA, sessionId: 'new-login-session' });
    pending.resolve({ ...accepted, status: 'deleted', server_id: null }); await cleaning;
    expect(cleanupSignal.aborted).toBe(true);
    expect(controller.consume).toBeNull();
  });
});
