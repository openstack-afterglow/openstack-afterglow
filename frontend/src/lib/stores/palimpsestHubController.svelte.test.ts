import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api/client';
import { hubApi, HUB_PAGE_SIZE } from '$lib/api/palimpsestHub';
import type { HubMe, HubLayer, HubLayerDetail, HubBuild, HubExport } from '$lib/api/palimpsestHub';
import type { PackageIdentity } from '$lib/api/palimpsestPackages';
import { createPalimpsestHubController } from './palimpsestHubController.svelte';

const ROOT = `sha256:${'a'.repeat(64)}`;
const OTHER = `sha256:${'b'.repeat(64)}`;
const original: PackageIdentity = { token: 'jwt-A', projectId: 'project-A', userId: 'user-A' };
function me(actor = original): HubMe {
  return { user_id: actor.userId, project_id: actor.projectId, project_name: 'Project', is_system_admin: false, roles: [], capabilities: { inventory: true, download: true, upload: false, delete: false, build: true } };
}
function layer(digest = ROOT): HubLayer {
  return { blob_digest: digest, size_bytes: 3, media_type: 'application/vnd.squashfs', disk_format: null, arch: 'x86_64', os_variant: null, parent_digest: null, base_image_digest: null, config_digest: ROOT, chain_id: null, name: 'python-runtime', kind: 'squashfs', ubuntu_base: null, python_version: '3.12', config_json: {}, project_id: 'shared-other-project', is_published: true, created_by: null, created_at: null };
}
function detail(digest = ROOT): HubLayerDetail { return { ...layer(digest), ancestors: [], chain_complete: false }; }
function build(): HubBuild {
  return { id: 'build-A', name: 'recent build', recipe_digest: ROOT, base_digest: ROOT, layer_digests: [], status: 'error', output_digest: null, output_size_bytes: null, error_code: 'worker_error', created_at: '2026-10-01T00:00:00Z', started_at: null, completed_at: null };
}
function exported(): HubExport {
  return { id: 'export-A', source_image_id: 'image-A', source_name: 'source', source_disk_format: 'qcow2', source_size_bytes: 123, target_disk_format: 'raw', status: 'error', progress_pct: 0, error_code: 'conversion_failed', error_message: 'upstream error', blob_digest: null, size_bytes: null, filename: null, download_path: null, created_at: '2026-10-01T00:00:00Z', started_at: null, completed_at: null };
}
async function settle() { for (let i = 0; i < 16; i++) await Promise.resolve(); }
function setup() {
  let actor: PackageIdentity | null = { ...original };
  let ready = true;
  let leaves = new Set(['palimpsest-inventory_reader', 'palimpsest-download_user']);
  const api: typeof hubApi = {
    me: vi.fn(async (caller) => me(caller)),
    layers: vi.fn(async () => [layer()]),
    detail: vi.fn(async (_caller, _signal, digest) => detail(digest)),
    ancestors: vi.fn(async () => []),
    builds: vi.fn(async () => [build()]),
    exports: vi.fn(async () => [exported()]),
    download: vi.fn(async () => new Blob(['abc'])),
  };
  const controller = createPalimpsestHubController(() => actor, api, (leaf) => ready && leaves.has(leaf), () => ready, () => 1000);
  return { api, controller,
    setActor(next: PackageIdentity | null) { actor = next; controller.bindIdentity(); },
    mutateToken(token: string) { if (actor) actor.token = token; controller.bindIdentity(); },
    permissions(value: boolean, next = [...leaves]) { ready = value; leaves = new Set(next); controller.syncCapabilities(); },
  };
}

describe('Hub current-caller consumer boundary', () => {
  it('accepts Hub-visible shared rows and exposes chain/error details without invented metrics', async () => {
    const { controller } = setup(); controller.bindIdentity(); await settle();
    expect(controller.inventory?.[0].project_id).toBe('shared-other-project');
    expect(controller.builds?.[0]).toMatchObject({ status: 'error', output_size_bytes: null, error_code: 'worker_error' });
    expect(controller.exports?.[0]).toMatchObject({ status: 'error', progress_pct: 0, size_bytes: null, error_message: 'upstream error' });
    await controller.openDetail(ROOT);
    expect(controller.detail).toMatchObject({ chain_complete: false, ancestors: [] });
    expect(controller.observed).toMatchObject({ inventory: 1000, builds: 1000, exports: 1000 });
    controller.dispose();
  });
  it('rejects identity mismatch before any artifact or monitoring request', async () => {
    const { controller, api } = setup(); vi.mocked(api.me).mockResolvedValue(me({ ...original, userId: 'other-user' }));
    controller.bindIdentity(); await settle();
    expect(controller.me).toBeNull(); expect(controller.errors.me).toBeTruthy();
    expect(api.layers).not.toHaveBeenCalled(); expect(api.builds).not.toHaveBeenCalled();
    controller.dispose();
  });
  it('keeps inventory 403 separate from successful build/export status lanes', async () => {
    const { controller, api } = setup(); vi.mocked(api.layers).mockRejectedValue(new ApiError(403, 'inventory denied'));
    controller.bindIdentity(); await settle();
    expect(controller.errors.inventory).toBe('inventory denied'); expect(controller.inventory).toBeNull();
    expect(controller.builds?.[0].id).toBe('build-A'); expect(controller.exports?.[0].id).toBe('export-A');
    expect(controller.errors.me).toBeUndefined(); expect(controller.observed.inventory).toBeUndefined();
    controller.dispose();
  });
  it('keeps build and export 403 separate from healthy inventory without making errors verified zero', async () => {
    const { controller, api } = setup();
    vi.mocked(api.builds).mockRejectedValue(new ApiError(403, 'build denied'));
    vi.mocked(api.exports).mockRejectedValue(new ApiError(403, 'exports denied'));
    controller.bindIdentity(); await settle();
    expect(controller.inventory?.length).toBe(1);
    expect(controller.builds).toBeNull(); expect(controller.exports).toBeNull();
    expect(controller.errors).toMatchObject({ builds: 'build denied', exports: 'exports denied' });
    expect(controller.observed.builds).toBeUndefined(); expect(controller.observed.exports).toBeUndefined();
    controller.dispose();
  });
  it('masks immediately on token changes and discards old same-project responses including ABA', async () => {
    const { controller, api, setActor } = setup();
    const old = Promise.withResolvers<HubMe>(); vi.mocked(api.me).mockReturnValueOnce(old.promise);
    controller.bindIdentity();
    setActor({ ...original, token: 'jwt-rotated' }); await settle();
    setActor({ ...original }); await settle();
    old.resolve({ ...me(), project_name: 'stale identity' }); await settle();
    expect(controller.me?.project_name).toBe('Project');
    expect(vi.mocked(api.me).mock.calls.map(([actor]) => actor.token)).toEqual(['jwt-A', 'jwt-rotated', 'jwt-A']);
    controller.dispose();
  });
  it('snapshots mutable identities and drops a download when the token changes in place', async () => {
    const { controller, api, mutateToken } = setup(); controller.bindIdentity(); await settle(); await controller.openDetail(ROOT);
    const pending = Promise.withResolvers<Blob>(); vi.mocked(api.download).mockReturnValueOnce(pending.promise);
    const saving = controller.download(); const caller = vi.mocked(api.download).mock.calls[0][0];
    mutateToken('next-token'); await settle(); pending.resolve(new Blob(['abc']));
    expect(await saving).toBeNull(); expect(caller.token).toBe('jwt-A'); expect(controller.detail).toBeNull();
    controller.dispose();
  });
  it('discards project A response after A/B/A transitions and logout', async () => {
    const { controller, api, setActor } = setup(); controller.bindIdentity(); await settle();
    const pending = Promise.withResolvers<HubLayer[]>(); vi.mocked(api.layers).mockReturnValueOnce(pending.promise);
    const loading = controller.loadInventory();
    setActor({ ...original, projectId: 'project-B', token: 'jwt-B' }); await settle();
    setActor({ ...original }); await settle(); pending.resolve([{ ...layer(), name: 'stale-A' }]); await loading;
    expect(controller.inventory?.[0].name).toBe('python-runtime');
    setActor(null); expect(controller.inventory).toBeNull(); expect(controller.me).toBeNull(); expect(controller.builds).toBeNull();
    controller.dispose();
  });
  it('discards filter ABA responses and clears detail on query changes', async () => {
    const { controller, api } = setup(); controller.bindIdentity(); await settle(); await controller.openDetail(ROOT);
    const pending = Promise.withResolvers<HubLayer[]>(); vi.mocked(api.layers).mockReturnValueOnce(pending.promise);
    const first = controller.setFilters({ name: 'alpha' });
    await controller.setFilters({ name: 'beta' }); await controller.setFilters({ name: 'alpha' });
    pending.resolve([{ ...layer(), name: 'stale-alpha' }]); await first;
    expect(controller.inventory?.[0].name).toBe('python-runtime'); expect(controller.detail).toBeNull();
    expect(vi.mocked(api.layers).mock.calls.slice(-3).map((args) => args[2])).toEqual([{ name: 'alpha' }, { name: 'beta' }, { name: 'alpha' }]);
    controller.dispose();
  });
  it('drops old detail responses after selection changes and never saves a closed detail download', async () => {
    const { controller, api } = setup(); controller.bindIdentity(); await settle();
    const pending = Promise.withResolvers<HubLayerDetail>(); vi.mocked(api.detail).mockReturnValueOnce(pending.promise);
    const first = controller.openDetail(ROOT); await controller.openDetail(OTHER); pending.resolve(detail(ROOT)); await first;
    expect(controller.detail?.blob_digest).toBe(OTHER);
    const bytes = Promise.withResolvers<Blob>(); vi.mocked(api.download).mockReturnValueOnce(bytes.promise);
    const saving = controller.download(); controller.closeDetail(); bytes.resolve(new Blob(['abc']));
    expect(await saving).toBeNull(); controller.dispose();
  });
  it('masks all lanes on pending authority, aborts responses across pending ABA and respects denial', async () => {
    const { controller, api, permissions } = setup(); controller.bindIdentity(); await settle();
    const pending = Promise.withResolvers<HubLayer[]>(); vi.mocked(api.layers).mockReturnValueOnce(pending.promise);
    const loading = controller.loadInventory(); permissions(false);
    expect(controller.inventory).toBeNull(); expect(controller.builds).toBeNull(); expect(controller.me).toBeNull();
    permissions(true); await settle(); pending.resolve([{ ...layer(), name: 'old-permission' }]); await loading;
    expect(controller.inventory?.[0].name).toBe('python-runtime');
    permissions(true, []); expect(controller.inventory).toBeNull(); expect(controller.canDownload).toBe(false);
    expect(controller.builds?.[0].id).toBe('build-A');
    const callsBeforeRecovery = vi.mocked(api.layers).mock.calls.length;
    permissions(true, ['palimpsest-inventory_reader', 'palimpsest-download_user']); await settle();
    expect(api.layers).toHaveBeenCalledTimes(callsBeforeRecovery + 1);
    expect(controller.inventory?.[0].name).toBe('python-runtime');
    expect(controller.exports?.[0].id).toBe('export-A');
    controller.dispose();
  });
  it('allows verified native system exceptions only while permission snapshot is ready', async () => {
    const { controller, api, permissions } = setup();
    vi.mocked(api.me).mockResolvedValue({ ...me(), is_system_admin: true });
    permissions(true, []); controller.bindIdentity(); await settle();
    expect(controller.canInventory).toBe(true); expect(controller.canDownload).toBe(true);
    permissions(false); expect(controller.canInventory).toBe(false); expect(controller.me).toBeNull();
    controller.dispose();
  });
  it('uses lookahead pages without pretending loaded rows are total inventory', async () => {
    const { controller, api } = setup();
    const rows = Array.from({ length: HUB_PAGE_SIZE + 1 }, (_, index) => ({ ...layer(), blob_digest: `sha256:${index.toString(16).padStart(64, '0')}` }));
    vi.mocked(api.layers).mockResolvedValueOnce(rows).mockResolvedValueOnce([]);
    controller.bindIdentity(); await settle(); expect(controller.inventory).toHaveLength(HUB_PAGE_SIZE); expect(controller.hasNext).toBe(true);
    await controller.page(1); expect(controller.offset).toBe(HUB_PAGE_SIZE); expect(controller.inventory).toEqual([]); expect(controller.hasNext).toBe(false);
    await controller.page(1); expect(api.layers).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.layers).mock.calls[1][3]).toBe(HUB_PAGE_SIZE);
    await controller.page(-1); expect(controller.offset).toBe(0); controller.dispose();
  });
  it('never overlaps refresh or runs it while hidden, and retains last observation on independent failures', async () => {
    const { controller, api } = setup(); controller.bindIdentity(); await settle();
    await controller.refresh(false); expect(api.me).toHaveBeenCalledTimes(1);
    const pending = Promise.withResolvers<HubMe>(); vi.mocked(api.me).mockReturnValueOnce(pending.promise);
    const first = controller.refresh(true); await controller.refresh(true); expect(api.me).toHaveBeenCalledTimes(2);
    pending.resolve(me()); await first;
    vi.mocked(api.builds).mockRejectedValueOnce(new ApiError(503, 'worker unavailable')); await controller.loadBuilds();
    expect(controller.builds).toBeNull(); expect(controller.errors.builds).toBe('worker unavailable'); expect(controller.observed.builds).toBe(1000);
    controller.dispose(); await controller.refresh(true); expect(api.me).toHaveBeenCalledTimes(2);
  });
  it('does not cancel a newer explicit download when unrelated refreshed jobs finish', async () => {
    const { controller, api } = setup(); controller.bindIdentity(); await settle(); await controller.openDetail(ROOT);
    const jobs = Promise.withResolvers<HubBuild[]>();
    vi.mocked(api.builds).mockReturnValueOnce(jobs.promise);
    const refreshing = controller.refresh(true); await settle();
    const bytes = Promise.withResolvers<Blob>();
    vi.mocked(api.download).mockReturnValueOnce(bytes.promise);
    const saving = controller.download();
    const signal = vi.mocked(api.download).mock.calls.at(-1)![1];
    jobs.resolve([build()]); await refreshing;
    expect(signal.aborted).toBe(false);
    const blob = new Blob(['abc']); bytes.resolve(blob);
    expect(await saving).toBe(blob);
    controller.dispose();
  });
});
