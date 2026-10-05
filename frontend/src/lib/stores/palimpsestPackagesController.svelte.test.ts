import { describe, expect, it, vi } from 'vitest';
import { createPalimpsestPackagesController } from './palimpsestPackagesController.svelte';
import { packageApi } from '$lib/api/palimpsestPackages';
import type { IssuedPackageKey, PackageIdentity, PackageKey, PackageSummary, PackageVersion, ProjectContext, ScopedPage, VersionPage } from '$lib/api/palimpsestPackages';
import { getLocale, initLocale } from '$lib/i18n/runtime.svelte';

const A = '11111111111141118111111111111111';
const B = '22222222222242228222222222222222';
const USER = 'abcdef0123456789'.repeat(4);
const KEY_ID = '33333333-3333-4333-8333-333333333333';
const ROOT = `sha256:${'a'.repeat(64)}`;
function context(project = A, namespace: string | null = `p-${project}`): ProjectContext {
  return { project_id: project, project_name: project === A ? 'A' : 'B', namespace, package_authority: 'registry.example', capabilities: { packages_read: true, packages_write: true, keys_issue: true } };
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
    issue: vi.fn(async (identity) => ({ key: key(identity.projectId, identity.userId), secret: 'one-time-private-value' })),
    revoke: vi.fn(async () => undefined),
    download: vi.fn(async () => new Blob(['archive'])),
  };
  const controller = createPalimpsestPackagesController(() => actor, api);
  function switchTo(project: string | null) {
    actor = project ? { token: `jwt-${project}`, projectId: project, userId } : null;
    controller.bindIdentity();
  }
  function refreshToken(token: string) {
    if (!actor) throw new Error('identity required');
    actor = { ...actor, token };
    controller.bindIdentity();
  }
  return { api, controller, switchTo, refreshToken };
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
