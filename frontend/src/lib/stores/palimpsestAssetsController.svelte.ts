import { assetApi, sameAssetActor } from '$lib/api/palimpsestAssets';
import { ApiError } from '$lib/api/client';
import type { ReusableAsset, CloudEnvironment, AssetPage, ConsumeResult, CloudRequest, CloudResources, AssetIdentity } from '$lib/api/palimpsestAssets';
import type { PackageIdentity, PackageSummary, PackageVersion, ScopedPage, ProjectContext } from '$lib/api/palimpsestPackages';
import { HubClientError } from '$lib/api/palimpsestHub';
import { t as hubText } from '$lib/i18n/ns/palimpsest-hub';

export type AssetSource = 'hub' | 'packages' | 'environments';
type Lane = AssetSource | 'versions' | 'download' | 'resources' | 'consume' | 'status' | 'cleanup';
export type AssetSelection = { source: 'hub'; asset: ReusableAsset } | { source: 'environments'; asset: CloudEnvironment } | { source: 'packages'; asset: PackageSummary };
export function createPalimpsestAssetsController(
  identity: () => AssetIdentity | null,
  permitted: () => boolean,
  canDownload: () => boolean,
  canWrite: () => boolean,
  api = assetApi,
) {
  let bound = $state.raw<AssetIdentity | null>(null);
  let query = $state('');
  let hub = $state<AssetPage<ReusableAsset> | null>(null);
  let environments = $state<AssetPage<CloudEnvironment> | null>(null);
  let packages = $state<ScopedPage<PackageSummary> | null>(null);
  let context = $state<ProjectContext | null>(null);
  let selection = $state<AssetSelection | null>(null);
  let versions = $state<ScopedPage<PackageVersion> | null>(null);
  let version = $state<PackageVersion | null>(null);
  let resources = $state<CloudResources | null>(null);
  let consume = $state<ConsumeResult | null>(null);
  let consumeLocked = $state(false);
  let errors = $state<Partial<Record<Lane, string>>>({});
  let busy = $state<Partial<Record<Lane, boolean>>>({});
  let generation = 0;
  let disposed = false;
  let allowed = false;
  const requests = new Map<Lane, AbortController>();
  const owned = () => !disposed && !!bound && sameAssetActor(bound, identity());
  const current = () => owned() && permitted();
  function cancel(lane: Lane) { requests.get(lane)?.abort(); requests.delete(lane); busy[lane] = false; }
  function close() {
    for (const lane of ['versions', 'download', 'resources'] as Lane[]) cancel(lane);
    selection = null; versions = null; version = null; resources = null;
    delete errors.versions; delete errors.download; delete errors.resources;
  }
  function reset() {
    generation++;
    for (const lane of requests.keys()) cancel(lane);
    hub = null; packages = null; environments = null; context = null; consume = null;
    consumeLocked = false;
    close(); errors = {}; busy = {}; query = '';
  }
  async function run<T>(lane: Lane, operation: (actor: PackageIdentity, signal: AbortSignal) => Promise<T>, apply: (value: T) => void) {
    if (!current() || lane === 'download' && !canDownload() || lane === 'consume' && (!canWrite() || !canDownload()) || lane === 'cleanup' && !canWrite()) return;
    if (lane === 'consume' && busy.consume) return;
    cancel(lane);
    const actor = { ...bound! }, epoch = generation, request = new AbortController();
    requests.set(lane, request); busy[lane] = true; delete errors[lane];
    const owns = () => owned() && (lane === 'consume' || lane === 'cleanup' || permitted()) && epoch === generation && requests.get(lane) === request && !request.signal.aborted;
    try {
      const result = await operation(actor, request.signal);
      if (owns() && (lane !== 'download' || canDownload())) apply(result);
    } catch (error) {
      if (owns()) {
        errors[lane] = error instanceof HubClientError ? hubText(error.code === 'too-large' ? 'error.size' : 'error.response') : error instanceof Error ? error.message : hubText('error.request');
        if (lane === 'consume' && error instanceof ApiError && [400, 403, 404, 409, 422].includes(error.status)) consumeLocked = false;
      }
    } finally {
      if (owns()) { requests.delete(lane); busy[lane] = false; }
    }
  }
  async function load(source: AssetSource, page: number | string = 0) {
    const q = query;
    if (source === 'hub') {
      hub = null;
      await run(source, (actor, signal) => api.hub(actor, signal, q, Number(page)), (value) => { hub = value; });
    } else if (source === 'environments') {
      environments = null;
      await run(source, (actor, signal) => api.environments(actor, signal, q, Number(page)), (value) => { environments = value; });
    } else {
      packages = null;
      await run(source, async (actor, signal) => {
        const verified = await api.context(actor, signal);
        if (verified.project_id !== actor.projectId) throw new Error('Invalid project response');
        if (!verified.capabilities.packages_read) throw new Error('Package inventory denied');
        if (!verified.namespace) return { verified, inventory: { project_id: actor.projectId, namespace: '', items: [], next_cursor: null } as ScopedPage<PackageSummary> };
        const inventory = await api.packages(actor, signal, q, typeof page === 'string' ? page : undefined);
        if (inventory.project_id !== actor.projectId || inventory.namespace !== verified.namespace || inventory.items.some((item) => item.project_id !== actor.projectId || item.namespace !== verified.namespace)) throw new Error('Invalid package ownership response');
        return { verified, inventory };
      }, ({ verified, inventory }) => { context = verified; packages = inventory; });
    }
  }
  async function search(value: string) {
    query = value.trim(); close();
    await Promise.all([load('hub'), load('packages'), load('environments')]);
  }
  function bind() {
    const actor = identity(), ready = permitted();
    if (!sameAssetActor(bound, actor)) { reset(); bound = actor ? { ...actor } : null; }
    else if (actor) bound = { ...actor };
    if (allowed && !ready) {
      for (const lane of requests.keys()) if (lane !== 'consume' && lane !== 'cleanup') cancel(lane);
      hub = null; packages = null; environments = null; context = null; close();
    }
    const started = ready && (!allowed || hub === null && packages === null && environments === null && !Object.keys(errors).length && !Object.values(busy).some(Boolean));
    allowed = ready;
    if (actor && started) void search(query);
    if (!canDownload()) cancel('download');
    if (!canWrite()) { cancel('resources'); resources = null; }
  }
  async function select(value: AssetSelection) {
    close(); selection = value;
    if (value.source === 'packages') await moreVersions();
  }
  async function moreVersions() {
    const selected = selection;
    if (selected?.source !== 'packages') return;
    const previous = versions;
    await run('versions', (actor, signal) => api.versions(actor, signal, selected.asset.name, previous?.next_cursor ?? undefined), (value) => {
      if (value.project_id !== bound?.projectId || value.namespace !== selected.asset.namespace
        || value.items.some((item) => item.project_id !== bound?.projectId || item.namespace !== selected.asset.namespace || item.package !== selected.asset.name)) throw new Error('Invalid version ownership response');
      versions = { ...value, items: [...previous?.items ?? [], ...value.items] };
      if (!version) version = value.items[0] ?? null;
    });
  }
  async function download(): Promise<Blob | null> {
    const selected = selection, chosen = version;
    if (!selected || selected.source === 'environments') return null;
    let result: Blob | null = null;
    await run('download', (actor, signal) => selected.source === 'hub'
      ? api.bundle(actor, signal, selected.asset.blob_digest)
      : chosen ? api.packageDownload(actor, signal, selected.asset.name, chosen.root_digest) : Promise.reject(new Error('Select a version')),
    (blob) => { result = blob; });
    return result;
  }
  async function loadResources() {
    if (!canWrite()) return;
    await run('resources', (actor, signal) => api.resources(actor, signal), (value) => { resources = value; });
  }
  async function create(body: CloudRequest) {
    const selected = selection;
    if (selected?.source !== 'environments' || !selected.asset.cloud_supported || !canWrite() || busy.consume || consumeLocked || body.revision !== selected.asset.revision) return;
    consume = null; consumeLocked = true;
    await run('consume', (actor, signal) => api.consume(actor, signal, selected.asset.id, body), (value) => {
      if (value.project_id !== bound?.projectId || value.revision !== body.revision) throw new Error('Invalid consume ownership response');
      consume = value;
      if (value.ready && value.status === 'active') consumeLocked = false;
    });
  }
  async function refreshConsume() {
    const previous = consume;
    if (!previous) return;
    await run('status', (actor, signal) => api.consumeStatus(actor, signal, previous.consume_id), (value) => {
      if (value.project_id !== bound?.projectId || value.consume_id !== previous.consume_id || value.revision !== previous.revision) throw new Error('Invalid consume ownership response');
      consume = value;
      if (value.ready && value.status === 'active') consumeLocked = false;
    });
  }
  async function cleanup() {
    const previous = consume;
    if (!previous || busy.cleanup || !canWrite()) return;
    await run('cleanup', (actor, signal) => api.cleanup(actor, signal, previous.consume_id), (value) => {
      if (value.project_id !== bound?.projectId || value.consume_id !== previous.consume_id || value.revision !== previous.revision) throw new HubClientError('response');
      consume = value;
      if (value.status === 'deleted') consumeLocked = false;
    });
  }
  function dispose() { reset(); disposed = true; bound = null; }
  function invalidateActor() { reset(); bound = null; allowed = false; }
  function pauseAuthority() {
    for (const lane of requests.keys()) if (lane !== 'consume' && lane !== 'cleanup') cancel(lane);
    hub = null; packages = null; environments = null; context = null; close(); allowed = false;
  }
  return {
    bind, search, load, select, close, moreVersions, download, loadResources, create, refreshConsume, dispose, invalidateActor, pauseAuthority, cleanup,
    get hub() { return current() ? hub : null; },
    get environments() { return current() ? environments : null; },
    get packages() { return current() ? packages : null; },
    get context() { return current() ? context : null; },
    get selection() { return current() ? selection : null; },
    get versions() { return current() ? versions : null; },
    get version() { return current() ? version : null; },
    set version(value: PackageVersion | null) {
      cancel('download');
      version = value && versions?.items.includes(value) ? value : null;
    },
    get resources() { return current() && canWrite() ? resources : null; },
    get consume() { return current() ? consume : null; },
    get consumeLocked() { return current() && consumeLocked; },
    get errors() { return current() ? errors : {}; },
    get busy() { return current() ? busy : {}; },
    get query() { return query; },
  };
}
