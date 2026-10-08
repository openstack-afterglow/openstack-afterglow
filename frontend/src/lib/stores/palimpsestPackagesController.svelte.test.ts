import { describe, expect, it, vi } from 'vitest';
import { createPalimpsestPackagesController } from './palimpsestPackagesController.svelte';
import { packageApi } from '$lib/api/palimpsestPackages';
import type { IssuedPackageKey, KeyAction, PackageIdentity, PackageKey, PackageSummary, PackageVersion, ProjectContext, ScopedPage, VersionPage } from '$lib/api/palimpsestPackages';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';

const A = '11111111111141118111111111111111';
const B = '22222222222242228222222222222222';
const USER = 'abcdef0123456789'.repeat(4);
const KEY_ID = '33333333-3333-4333-8333-333333333333';
const ROOT = `sha256:${'a'.repeat(64)}`;
function context(project = A, namespace: string | null = `p-${project}`): ProjectContext {
  return { project_id: project, project_name: project === A ? 'A' : 'B', namespace, package_authority: 'registry.example', capabilities: { packages_read: true, packages_download: true, packages_write: true, keys_issue: true, keys_revoke: true } };
}
function summary(project = A, name = 'test'): PackageSummary {
  return { package_id: `${project}-${name}`, project_id: project, namespace: `p-${project}`, name, package_type: 'oci-image', visibility: 'project', tags: [{ tag: 'latest', digest: ROOT }], platforms: [{ os: 'linux', architecture: 'amd64' }], version_count: 1, latest_pushed_at: '2026-10-01T00:00:00Z', latest_pushed_by: USER };
}
function version(project = A, name = 'test', digest = ROOT): PackageVersion {
  return { project_id: project, namespace: `p-${project}`, package: name, root_digest: digest, root_media_type: 'application/vnd.oci.image.manifest.v1+json', root_descriptor: { digest, mediaType: 'application/vnd.oci.image.manifest.v1+json', size: 123 }, graph: { [digest]: { media_type: 'application/vnd.oci.image.manifest.v1+json', size_bytes: 123 } }, platforms: [{ os: 'linux', architecture: 'amd64' }], archive_digest: ROOT, archive_size_bytes: 4096, total_bytes: 123, provenance: {}, pushed_by: USER, pushed_key_id: KEY_ID, pushed_at: '2026-10-01T00:00:00Z' };
}
function key(project = A, owner = USER): PackageKey {
  return { key_id: KEY_ID, name: 'ci', owner_user_id: owner, project_id: project, namespace: `p-${project}`, scope: { packages: ['test'] }, actions: ['packages:read'], created_at: '2026-10-01T00:00:00Z', expires_at: '2026-10-31T00:00:00Z', revoked_at: null };
}
function inventory(project = A): ScopedPage<PackageSummary> {
  return { project_id: project, namespace: `p-${project}`, items: [summary(project)], next_cursor: null };
}
function history(project = A, name = 'test'): VersionPage {
  return { project_id: project, namespace: `p-${project}`, package: name, items: [version(project, name)], next_cursor: null };
}
function setup(userId = USER) {
  let leaves = ['palimpsest-inventory_reader', 'palimpsest-publish_editor', 'palimpsest-download_user', 'palimpsest-keys_editor', 'palimpsest-keys_admin'];
  let permissionsReady = true;
  let actor: PackageIdentity | null = { token: 'jwt-A', projectId: A, userId };
  const api: typeof packageApi = {
    context: vi.fn(async (identity) => context(identity.projectId)),
    register: vi.fn(async (identity) => context(identity.projectId)),
    inventory: vi.fn(async (identity) => inventory(identity.projectId)),
    detail: vi.fn(async (identity, _signal, name) => summary(identity.projectId, name)),
    versions: vi.fn(async (identity, _signal, name) => history(identity.projectId, name)),
    version: vi.fn(async (identity, _signal, name, digest) => version(identity.projectId, name, digest)),
    resolve: vi.fn(async (identity, _signal, name, tag) => ({ project_id: identity.projectId, namespace: `p-${identity.projectId}`, package: name, tag, digest: ROOT })),
    keys: vi.fn(async (identity) => ({ project_id: identity.projectId, namespace: `p-${identity.projectId}`, items: [key(identity.projectId, identity.userId)] })),
    issue: vi.fn(async (identity, _signal, body) => ({ key: { ...key(identity.projectId, identity.userId), actions: body.actions, scope: body.scope }, secret: 'one-time-private-value' })),
    revoke: vi.fn(async () => undefined),
    download: vi.fn(async () => new Blob(['archive'])),
  };
  const controller = createPalimpsestPackagesController(() => actor, api, (leaf) => permissionsReady && leaves.includes(leaf), (leaf) => permissionsReady && !leaves.includes(leaf));
  function switchTo(project: string | null) {
    actor = project ? { token: `jwt-${project}`, projectId: project, userId } : null;
    controller.bindIdentity();
  }
  function refreshToken(token: string) {
    if (!actor) throw new Error('identity required');
    actor = { ...actor, token };
    controller.bindIdentity();
  }
  function switchUser(nextUser: string) {
    if (!actor) throw new Error('identity required');
    actor = { ...actor, userId: nextUser };
    controller.bindIdentity();
  }
  return { api, controller, switchTo, switchUser, refreshToken,
    grant: (...next: string[]) => { leaves = next; permissionsReady = true; },
    unavailable: () => { permissionsReady = false; },
  };
}
const request = { name: 'ci', scope: { packages: ['test'] }, actions: ['packages:read'], expires_in_days: 30 } as const;
const issueRequest = { ...request, scope: { packages: ['test'] }, actions: ['packages:read' as const] };

describe('project-private package transitions', () => {
  it('never publishes an A inventory that completes after B becomes current', async () => {
    const { controller, api, switchTo } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.latestVersions[`${A}-test`]?.version?.project_id).toBe(A));
    const old = Promise.withResolvers<ScopedPage<PackageSummary>>();
    vi.mocked(api.inventory).mockReturnValueOnce(old.promise);
    const loadingA = controller.loadInventory();
    switchTo(B);
    await vi.waitFor(() => expect(controller.latestVersions[`${B}-test`]?.version?.project_id).toBe(B));
    old.resolve(inventory(A));
    await loadingA;
    expect(controller.context?.project_id).toBe(B);
    expect(controller.inventory?.map((item) => item.project_id)).toEqual([B]);
    expect(controller.latestVersions[`${B}-test`]?.version?.project_id).toBe(B);
    controller.dispose();
  });

  it('rejects a foreign row even when the inventory envelope names the current project', async () => {
    const { controller, api } = setup();
    vi.mocked(api.inventory).mockResolvedValue({ ...inventory(A), items: [summary(B)] });
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.errors.inventory).toBeTruthy());
    expect(controller.inventory).toBeNull();
    expect(controller.latestVersions).toEqual({});
    controller.dispose();
  });

  it('keeps unregistered state distinct from empty inventory until explicit registration', async () => {
    const { controller, api } = setup();
    vi.mocked(api.context).mockResolvedValueOnce(context(A, null));
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.context?.namespace).toBeNull());
    expect(controller.inventory).toBeNull();
    await controller.register();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    expect(controller.context?.namespace).toBe(`p-${A}`);
    controller.dispose();
  });

  it('cannot resurrect an issued secret after its once-only view is discarded', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    const pending = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(pending.promise);
    const issuing = controller.issueKey(issueRequest);
    controller.discardSecret();
    pending.resolve({ key: key(), secret: 'late-private-value' });
    await issuing;
    expect(controller.issued).toBeNull();
    expect(controller.busy.issue).toBe(false);
    await vi.waitFor(() => expect(controller.keys?.[0].name).toBe('ci'));
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it('clears visible secrets immediately while project rescope is still pending', async () => {
    const { controller, switchTo } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    await controller.issueKey(issueRequest);
    expect(controller.issued?.secret).toBe('one-time-private-value');
    switchTo(null);
    expect(controller.context).toBeNull();
    expect(controller.inventory).toBeNull();
    expect(controller.keys).toBeNull();
    expect(controller.issued).toBeNull();
    switchTo(B);
    await vi.waitFor(() => expect(controller.inventory?.[0].project_id).toBe(B));
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it('does not publish a late secret after navigation disposes the page', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    const pending = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(pending.promise);
    const issuing = controller.issueKey(issueRequest);
    controller.dispose();
    pending.resolve({ key: key(), secret: 'late-private-value' });
    await issuing;
    expect(controller.issued).toBeNull();
    expect(controller.context).toBeNull();
    expect(controller.keys).toBeNull();
  });

  it('never inserts a previous package version into a newly opened detail', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    await controller.openPackage('alpha');
    const pending = Promise.withResolvers<PackageVersion>();
    vi.mocked(api.version).mockReturnValueOnce(pending.promise);
    const selecting = controller.selectVersion(ROOT);
    await controller.openPackage('beta');
    pending.resolve(version(A, 'alpha'));
    await selecting;
    expect(controller.detail?.name).toBe('beta');
    expect(controller.version).toBeNull();
    expect(controller.versions?.map((item) => item.package)).toEqual(['beta']);
    controller.dispose();
  });
  it('accepts a 64-hex federated owner without UUID normalization', async () => {
    const federatedOwner = 'ABCDEF0123456789'.repeat(4);
    const { controller } = setup(federatedOwner);
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    await controller.issueKey(issueRequest);
    expect(controller.issued?.key.owner_user_id).toBe(federatedOwner);
    await controller.loadKeys();
    expect(controller.keys?.[0].owner_user_id).toBe(federatedOwner);
    controller.dispose();
  });

  it('rejects an owner differing only by identifier case', async () => {
    const { controller, api } = setup('LDAP.Member');
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    vi.mocked(api.issue).mockResolvedValueOnce({ key: key(A, 'ldap.member'), secret: 'must-not-render' });
    await controller.issueKey(issueRequest);
    expect(controller.issued).toBeNull();
    expect(controller.errors.issue).toBeTruthy();
    controller.dispose();
  });
  it('keeps an in-flight issued secret through a same-project JWT refresh', async () => {
    const { controller, api, refreshToken } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    const pending = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(pending.promise);
    const issuing = controller.issueKey(issueRequest);
    refreshToken('rotated-jwt');
    expect(controller.inventory?.[0].name).toBe('test');
    pending.resolve({ key: key(), secret: 'preserved-on-refresh' });
    await issuing;
    expect(controller.issued?.secret).toBe('preserved-on-refresh');
    await vi.waitFor(() => expect(controller.keys?.[0].key_id).toBe(KEY_ID));
    expect(vi.mocked(api.keys).mock.calls.at(-1)?.[0].token).toBe('rotated-jwt');
    controller.dispose();
  });

  it('does not cancel pending issuance when a different mutation completes', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    const pending = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(pending.promise);
    const issuing = controller.issueKey(issueRequest);
    await controller.revokeKey({ ...key(), key_id: '44444444-4444-4444-8444-444444444444' });
    pending.resolve({ key: key(), secret: 'independent-issue-result' });
    await issuing;
    expect(controller.issued?.secret).toBe('independent-issue-result');
    expect(controller.busy.issue).toBe(false);
    controller.dispose();
  });

  it('does not let an older same-project inventory replace a refreshed inventory', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.latestVersions[`${A}-test`]?.version?.project_id).toBe(A));
    const old = Promise.withResolvers<ScopedPage<PackageSummary>>();
    vi.mocked(api.inventory).mockReturnValueOnce(old.promise);
    const loadingOld = controller.loadInventory();
    vi.mocked(api.inventory).mockResolvedValueOnce({ ...inventory(), items: [summary(A, 'new')] });
    await controller.loadInventory();
    expect(controller.inventory?.[0].name).toBe('new');
    old.resolve({ ...inventory(), items: [summary(A, 'old')] });
    await loadingOld;
    expect(controller.inventory?.map((item) => item.name)).toEqual(['new']);
    controller.dispose();
  });

  it('renders inventory before metadata and drops stale project metadata', async () => {
    const { controller, api, switchTo } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.latestVersions[`${A}-test`]?.version?.project_id).toBe(A));
    const old = Promise.withResolvers<VersionPage>();
    vi.mocked(api.versions).mockReturnValueOnce(old.promise);
    const loadingA = controller.loadInventory();
    await vi.waitFor(() => expect(controller.inventory?.[0].project_id).toBe(A));
    expect(controller.latestVersions[`${A}-test`]).toBeUndefined();
    switchTo(B);
    await vi.waitFor(() => expect(controller.latestVersions[`${B}-test`]?.version?.project_id).toBe(B));
    old.resolve(history(A));
    await loadingA;
    expect(controller.inventory?.map((item) => item.project_id)).toEqual([B]);
    expect(controller.latestVersions[`${A}-test`]).toBeUndefined();
    controller.dispose();
  });
  it('retranslates retained local errors without changing server errors or the one-time secret', async () => {
    const previousLocale = getLocale();
    const { controller, api } = setup();
    try {
      initLocale('ko');
      controller.bindIdentity();
      await vi.waitFor(() => expect(controller.latestVersions[`${A}-test`]?.version?.project_id).toBe(A));
      await controller.issueKey(issueRequest);
      const issued = controller.issued;
      expect(issued?.secret).toBe('one-time-private-value');
      await controller.openPackage('test', undefined, 'foreign-namespace');
      vi.mocked(api.versions).mockRejectedValueOnce(null);
      await controller.loadInventory();
      const detailError = controller.errors.detail;
      const metadataError = controller.latestVersions[`${A}-test`].error;
      expect(controller.detail).toBeNull();
      expect(controller.latestVersions[`${A}-test`].version).toBeNull();
      const serverError = 'opaque upstream error: packages:read / p-project';
      vi.mocked(api.keys).mockRejectedValueOnce(new Error(serverError));
      await controller.loadKeys();
      for (const locale of ['en', 'ja', 'zh-CN'] as const) {
        initLocale(locale);
        expect(controller.errors.detail).not.toBe(detailError);
        expect(controller.latestVersions[`${A}-test`].error).not.toBe(metadataError);
        expect(controller.errors.keys).toBe(serverError);
        expect(controller.issued).toBe(issued);
        expect(controller.inventory?.[0].project_id).toBe(A);
      }
      initLocale('ko');
      expect(controller.errors.detail).toBe(detailError);
      expect(controller.latestVersions[`${A}-test`].error).toBe(metadataError);
      controller.discardSecret();
      initLocale('en');
      expect(controller.issued).toBeNull();
    } finally {
      controller.dispose();
      initLocale(previousLocale);
    }
  });
});

describe('Palimpsest scoped service actions', () => {
  it('denies mutations and download without service leaves despite permissive native context', async () => {
    const { controller, api, grant } = setup();
    grant();
    vi.mocked(api.context).mockResolvedValueOnce(context(A, null));
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.context).not.toBeNull());
    await controller.register();
    await controller.issueKey(issueRequest);
    await controller.revokeKey(key());
    await controller.download('test', ROOT);
    for (const call of [api.register, api.issue, api.revoke, api.download]) expect(call).not.toHaveBeenCalled();
    controller.dispose();
  });

  it('requires publish for namespace registration and never treats it as key authority', async () => {
    const { controller, api, grant } = setup();
    grant('palimpsest-publish_editor');
    vi.mocked(api.context).mockResolvedValueOnce(context(A, null));
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.context).not.toBeNull());
    await controller.register();
    expect(api.register).toHaveBeenCalledOnce();
    await controller.issueKey(issueRequest);
    expect(api.issue).not.toHaveBeenCalled();
    expect(controller.canDownload).toBe(false);
    controller.dispose();
  });

  it('requires key editor plus every delegated action and reserves revoke for key admin', async () => {
    const { controller, api, grant } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.context).not.toBeNull());
    grant('palimpsest-keys_editor');
    await controller.issueKey(issueRequest);
    expect(api.issue).not.toHaveBeenCalled();
    grant('palimpsest-keys_editor', 'palimpsest-download_user');
    await controller.issueKey({ ...issueRequest, actions: ['packages:read', 'packages:write'] });
    expect(api.issue).not.toHaveBeenCalled();
    await controller.issueKey(issueRequest);
    expect(api.issue).toHaveBeenCalledOnce();
    await controller.revokeKey(key());
    expect(api.revoke).not.toHaveBeenCalled();
    grant('palimpsest-keys_admin');
    await controller.revokeKey(key());
    expect(api.revoke).toHaveBeenCalledOnce();
    await expect(controller.revokeKey(key(B))).rejects.toThrow();
    await expect(controller.revokeKey(key(A, 'another-user'))).rejects.toThrow();
    expect(api.revoke).toHaveBeenCalledOnce();
    controller.dispose();
  });

  it('keeps native denial authoritative and drops secrets issued during a downgrade', async () => {
    const { controller, api, grant } = setup();
    const denied = context();
    denied.capabilities.packages_download = false;
    denied.capabilities.keys_revoke = false;
    vi.mocked(api.context).mockResolvedValueOnce(denied);
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.context).not.toBeNull());
    await controller.download('test', ROOT);
    await controller.revokeKey(key());
    expect(api.download).not.toHaveBeenCalled();
    expect(api.revoke).not.toHaveBeenCalled();
    await controller.loadContext();
    const pending = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(pending.promise);
    const issuing = controller.issueKey(issueRequest);
    grant('palimpsest-download_user');
    pending.resolve({ key: key(), secret: 'not-authorized-anymore' });
    await issuing;
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it('separates metadata-only discovery from download, publish and key management', async () => {
    const { controller, api, grant } = setup();
    grant('palimpsest-inventory_reader');
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.inventory?.[0].name).toBe('test'));
    await controller.openPackage('test');
    expect(controller.detail?.name).toBe('test');
    expect(controller.canDelegate('packages:inventory')).toBe(true);
    expect(controller.canDelegate('packages:read')).toBe(false);
    await controller.download('test', ROOT);
    await controller.issueKey(issueRequest);
    await controller.revokeKey(key());
    expect(api.download).not.toHaveBeenCalled();
    expect(api.issue).not.toHaveBeenCalled();
    expect(api.revoke).not.toHaveBeenCalled();
    controller.dispose();
  });

  it('allows a download user without editor or admin mutation authority', async () => {
    const { controller, api, grant } = setup();
    grant('palimpsest-inventory_reader', 'palimpsest-download_user');
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.context).not.toBeNull());
    const objectUrl = vi.fn(() => 'blob:archive');
    const revokeUrl = vi.fn();
    const NativeURL = URL;
    vi.stubGlobal('URL', class extends NativeURL { static createObjectURL = objectUrl; static revokeObjectURL = revokeUrl; });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    try {
      await controller.download('test', ROOT);
      expect(api.download).toHaveBeenCalledOnce();
      expect(click).toHaveBeenCalledOnce();
      await controller.issueKey(issueRequest);
      await controller.revokeKey(key());
      expect(api.issue).not.toHaveBeenCalled();
      expect(api.revoke).not.toHaveBeenCalled();
      expect(controller.canPublish).toBe(false);
      await vi.waitFor(() => expect(revokeUrl).toHaveBeenCalledWith('blob:archive'));
    } finally { controller.dispose(); vi.unstubAllGlobals(); click.mockRestore(); }
  });

  it('delegates inventory and write-only scopes independently without adding download', async () => {
    const { controller, api, grant } = setup();
    grant('palimpsest-inventory_reader', 'palimpsest-publish_editor', 'palimpsest-keys_editor');
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.context).not.toBeNull());
    await controller.issueKey({ ...issueRequest, actions: ['packages:inventory', 'packages:write', 'cache:write'] });
    expect(api.issue).toHaveBeenCalledOnce();
    expect(controller.issued?.key.actions).toEqual(['packages:inventory', 'packages:write', 'cache:write']);
    controller.discardSecret();
    await controller.issueKey({ ...issueRequest, actions: ['packages:write'] });
    expect(api.issue).toHaveBeenCalledTimes(2);
    controller.discardSecret();
    for (const action of ['packages:read', 'cache:read'] as const) {
      await controller.issueKey({ ...issueRequest, actions: [action] });
    }
    await controller.issueKey({ ...issueRequest, actions: ['vm:launch'] } as unknown as typeof issueRequest);
    expect(api.issue).toHaveBeenCalledTimes(2);
    await controller.revokeKey(key());
    expect(api.revoke).not.toHaveBeenCalled();
    controller.dispose();
  });

  it('denies all risky actions while native context is pending or failed, including refresh', async () => {
    const { controller, api } = setup();
    const pending = Promise.withResolvers<ProjectContext>();
    vi.mocked(api.context).mockReturnValueOnce(pending.promise);
    controller.bindIdentity();
    for (const allowed of [controller.canRead, controller.canPublish, controller.canDownload, controller.canIssue, controller.canRevoke]) expect(allowed).toBe(false);
    await controller.issueKey(issueRequest);
    await controller.download('test', ROOT);
    expect(api.issue).not.toHaveBeenCalled();
    expect(api.download).not.toHaveBeenCalled();
    pending.resolve(context());
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    const refresh = Promise.withResolvers<ProjectContext>();
    vi.mocked(api.context).mockReturnValueOnce(refresh.promise);
    const loading = controller.loadContext();
    expect(controller.canPublish).toBe(false);
    expect(controller.canDownload).toBe(false);
    expect(controller.canIssue).toBe(false);
    expect(controller.canRevoke).toBe(false);
    refresh.reject(new Error('context unavailable'));
    await loading;
    expect(controller.canRead).toBe(false);
    expect(controller.canPublish).toBe(false);
    expect(controller.canDownload).toBe(false);
    expect(controller.canIssue).toBe(false);
    expect(controller.canRevoke).toBe(false);
    controller.dispose();
  });

  it('never flashes authority during permission loading, failure or a new project context', async () => {
    const { controller, api, grant, unavailable, switchTo } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.issueKey(issueRequest);
    unavailable(); // Loading and failures are not loaded denials.
    expect(controller.canPublish).toBe(false);
    expect(controller.canDownload).toBe(false);
    expect(controller.canIssue).toBe(false);
    expect(controller.canRevoke).toBe(false);
    expect(controller.issued).toBeNull();
    controller.syncCapabilities();
    grant('palimpsest-download_user', 'palimpsest-keys_editor');
    expect(controller.issued?.secret).toBe('one-time-private-value');
    const next = Promise.withResolvers<ProjectContext>();
    vi.mocked(api.context).mockReturnValueOnce(next.promise);
    switchTo(B);
    expect(controller.canIssue).toBe(false);
    expect(controller.canDownload).toBe(false);
    expect(controller.keys).toBeNull();
    next.resolve(context(B));
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it('does not override any native capability denial with service leaves', async () => {
    const { controller, api } = setup();
    const denied = context(A, null);
    denied.capabilities = { packages_read: false, packages_download: false, packages_write: false, keys_issue: false, keys_revoke: false };
    vi.mocked(api.context).mockResolvedValueOnce(denied);
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.context).not.toBeNull());
    await controller.register();
    await controller.loadInventory();
    await controller.openPackage('test');
    await controller.issueKey(issueRequest);
    await controller.revokeKey(key());
    await controller.download('test', ROOT);
    for (const call of [api.register, api.inventory, api.detail, api.issue, api.revoke, api.download]) expect(call).not.toHaveBeenCalled();
    controller.dispose();
  });

  it('discards an in-flight content download when download permission is lost', async () => {
    const { controller, api, grant } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canDownload).toBe(true));
    const pending = Promise.withResolvers<Blob>();
    vi.mocked(api.download).mockReturnValueOnce(pending.promise);
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    try {
      const downloading = controller.download('test', ROOT);
      grant('palimpsest-inventory_reader');
      pending.resolve(new Blob(['must-not-download']));
      await downloading;
      expect(api.download).toHaveBeenCalledOnce();
      expect(click).not.toHaveBeenCalled();
    } finally { controller.dispose(); click.mockRestore(); }
  });
});

const allLeaves = ['palimpsest-inventory_reader', 'palimpsest-publish_editor', 'palimpsest-download_user', 'palimpsest-keys_editor', 'palimpsest-keys_admin'];
const secretDenials: { action: KeyAction; leaf: string; native: keyof ProjectContext['capabilities'] }[] = [
  { action: 'packages:read', leaf: 'palimpsest-keys_editor', native: 'keys_issue' },
  { action: 'packages:inventory', leaf: 'palimpsest-inventory_reader', native: 'packages_read' },
  { action: 'packages:read', leaf: 'palimpsest-download_user', native: 'packages_download' },
  { action: 'cache:read', leaf: 'palimpsest-download_user', native: 'packages_download' },
  { action: 'packages:write', leaf: 'palimpsest-publish_editor', native: 'packages_write' },
  { action: 'cache:write', leaf: 'palimpsest-publish_editor', native: 'packages_write' },
];

describe('one-time secrets during same-scope verification', () => {
  it('retains an issued secret and detail through token rotation and permission outages', async () => {
    const { controller, api, refreshToken, unavailable, grant } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.openPackage('test');
    await controller.selectVersion(ROOT);
    await controller.issueKey(issueRequest);
    const issued = controller.issued;
    unavailable();
    refreshToken('latest-token');
    controller.syncCapabilities();
    expect(controller.issued).toBeNull();
    expect(controller.detail).toBeNull();
    expect(controller.versions).toBeNull();
    expect(controller.version).toBeNull();
    expect(controller.issueDenied).toBe(false);
    await controller.issueKey(issueRequest);
    expect(api.issue).toHaveBeenCalledOnce();
    // Repeated failed/pending verification must never advance the secret epoch.
    controller.syncCapabilities();
    grant(...allLeaves);
    expect(controller.issued).toBe(issued);
    expect(controller.detail?.name).toBe('test');
    expect(controller.version?.root_digest).toBe(ROOT);
    await controller.loadKeys();
    expect(vi.mocked(api.keys).mock.calls.at(-1)?.[0].token).toBe('latest-token');
    controller.dispose();
  });

  it('masks but retains a secret across pending and failed native refreshes', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.issueKey(issueRequest);
    const issued = controller.issued;
    const pending = Promise.withResolvers<ProjectContext>();
    vi.mocked(api.context).mockReturnValueOnce(pending.promise);
    const loading = controller.loadContext();
    controller.syncCapabilities();
    expect(controller.issued).toBeNull();
    expect(controller.issueDenied).toBe(false);
    pending.reject(new Error('native outage'));
    await loading;
    controller.syncCapabilities();
    expect(controller.issued).toBeNull();
    expect(controller.issueDenied).toBe(false);
    await controller.loadContext();
    expect(controller.issued).toBe(issued);
    controller.dispose();
  });

  it.each(['permissions', 'native'] as const)('privately retains a successful issuance arriving during %s verification', async (verification) => {
    const { controller, api, unavailable, grant, refreshToken } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    const response = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(response.promise);
    const issuing = controller.issueKey(issueRequest);
    const native = Promise.withResolvers<ProjectContext>();
    let loading: Promise<void> | undefined;
    if (verification === 'permissions') unavailable();
    else { vi.mocked(api.context).mockReturnValueOnce(native.promise); loading = controller.loadContext(); }
    refreshToken('new-jwt');
    controller.syncCapabilities();
    response.resolve({ key: key(), secret: 'retained-until-verified' });
    await issuing;
    expect(controller.issued).toBeNull();
    await controller.issueKey(issueRequest);
    expect(api.issue).toHaveBeenCalledOnce();
    if (verification === 'permissions') grant(...allLeaves);
    else { native.resolve(context()); await loading; }
    expect(controller.issued?.secret).toBe('retained-until-verified');
    controller.dispose();
  });

  it.each(secretDenials)('permanently discards $action on loaded $leaf denial', async ({ action, leaf }) => {
    const { controller, grant, unavailable } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.issueKey({ ...issueRequest, actions: [action] });
    expect(controller.issued?.secret).toBe('one-time-private-value');
    unavailable();
    controller.syncCapabilities();
    grant(...allLeaves.filter((value) => value !== leaf));
    expect(controller.issued).toBeNull();
    controller.syncCapabilities();
    grant(...allLeaves);
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it.each(secretDenials)('permanently discards $action when native $native resolves false', async ({ action, native }) => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.issueKey({ ...issueRequest, actions: [action] });
    const pending = Promise.withResolvers<ProjectContext>();
    vi.mocked(api.context).mockReturnValueOnce(pending.promise);
    const loading = controller.loadContext();
    controller.syncCapabilities();
    expect(controller.issued).toBeNull();
    const denied = context();
    denied.capabilities[native] = false;
    pending.resolve(denied);
    await loading; // No route effect is required to irreversibly consume the denial.
    await controller.loadContext();
    expect(controller.canIssue).toBe(true);
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it.each(secretDenials)('does not resurrect late $action issuance after a $leaf denial and regrant', async ({ action, leaf }) => {
    const { controller, api, grant } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    const response = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(response.promise);
    const issuing = controller.issueKey({ ...issueRequest, actions: [action] });
    grant(...allLeaves.filter((value) => value !== leaf));
    controller.syncCapabilities();
    grant(...allLeaves);
    response.resolve({ key: { ...key(), actions: [action] }, secret: 'revoked-before-arrival' });
    await issuing;
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it('invalidates late issuance on native denial even if grants return before its response', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    const response = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(response.promise);
    const issuing = controller.issueKey(issueRequest);
    const denied = context();
    denied.capabilities.packages_download = false;
    vi.mocked(api.context).mockResolvedValueOnce(denied);
    await controller.loadContext();
    await controller.loadContext();
    response.resolve({ key: key(), secret: 'native-revoked' });
    await issuing;
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it.each(['packages:inventory', 'packages:write', 'cache:write'] as const)('keeps $0 secrets when only unrelated leaves/capabilities are denied', async (action) => {
    const { controller, api, grant } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.issueKey({ ...issueRequest, actions: [action] });
    grant('palimpsest-keys_editor', action === 'packages:inventory' ? 'palimpsest-inventory_reader' : 'palimpsest-publish_editor');
    controller.syncCapabilities();
    const restricted = context();
    restricted.capabilities.packages_download = false;
    restricted.capabilities.keys_revoke = false;
    restricted.capabilities[action === 'packages:inventory' ? 'packages_write' : 'packages_read'] = false;
    vi.mocked(api.context).mockResolvedValueOnce(restricted);
    await controller.loadContext();
    expect(controller.issued?.secret).toBe('one-time-private-value');
    expect(controller.canDownload).toBe(false);
    expect(controller.canRevoke).toBe(false);
    controller.dispose();
  });

  it.each(['project', 'user', 'auth'] as const)('discards retained secrets on real %s identity loss', async (scope) => {
    const { controller, switchTo, switchUser, unavailable, grant } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.issueKey(issueRequest);
    unavailable();
    controller.syncCapabilities();
    if (scope === 'project') switchTo(B);
    else if (scope === 'user') switchUser('different-user');
    else switchTo(null);
    expect(controller.issued).toBeNull();
    if (scope === 'user') switchUser(USER);
    else switchTo(A);
    grant(...allLeaves);
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it('discards a secret on a resolved namespace boundary change', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.issueKey(issueRequest);
    vi.mocked(api.context).mockResolvedValueOnce(context(A, 'new-namespace'));
    await controller.loadContext();
    await controller.loadContext();
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it('never publishes inventory or details that arrive without current read authority', async () => {
    const { controller, api, unavailable, grant } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.latestVersions[`${A}-test`]?.version).toBeTruthy());
    const rows = Promise.withResolvers<ScopedPage<PackageSummary>>();
    const detail = Promise.withResolvers<PackageSummary>();
    vi.mocked(api.inventory).mockReturnValueOnce(rows.promise);
    vi.mocked(api.detail).mockReturnValueOnce(detail.promise);
    const loading = controller.loadInventory();
    const opening = controller.openPackage('test');
    unavailable();
    rows.resolve(inventory()); detail.resolve(summary());
    await Promise.all([loading, opening]);
    grant(...allLeaves);
    expect(controller.inventory).toBeNull();
    expect(controller.detail).toBeNull();
    expect(controller.latestVersions).toEqual({});
    controller.dispose();
  });

  it('does not restore a retained late secret after explicit dismissal during verification', async () => {
    const { controller, api, unavailable, grant } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    const response = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(response.promise);
    const issuing = controller.issueKey(issueRequest);
    unavailable();
    response.resolve({ key: key(), secret: 'privately-retained' });
    await issuing;
    expect(controller.issued).toBeNull();
    controller.discardSecret();
    grant(...allLeaves);
    expect(controller.issued).toBeNull();
    controller.dispose();
  });

  it('invalidates late issuance and old details across a namespace change and return', async () => {
    const { controller, api } = setup();
    controller.bindIdentity();
    await vi.waitFor(() => expect(controller.canIssue).toBe(true));
    await controller.openPackage('test');
    const response = Promise.withResolvers<IssuedPackageKey>();
    vi.mocked(api.issue).mockReturnValueOnce(response.promise);
    const issuing = controller.issueKey(issueRequest);
    vi.mocked(api.context).mockResolvedValueOnce(context(A, 'different-namespace'));
    await controller.loadContext();
    expect(controller.detail).toBeNull();
    await controller.loadContext();
    response.resolve({ key: key(), secret: 'old-namespace' });
    await issuing;
    expect(controller.issued).toBeNull();
    expect(controller.detail).toBeNull();
    controller.dispose();
  });
});
