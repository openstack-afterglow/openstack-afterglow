import { get } from 'svelte/store';
import { hubApi, HUB_PAGE_SIZE, HubClientError, sameHubIdentity } from '$lib/api/palimpsestHub';
import type { HubMe, HubLayer, HubLayerDetail, HubBuild, HubExport, HubFilters } from '$lib/api/palimpsestHub';
import type { PackageIdentity } from '$lib/api/palimpsestPackages';
import { projectPermissions, serviceCapabilities } from './servicePermissions';
import { t } from '$lib/i18n/ns/palimpsest-hub';

export type HubLane = 'me' | 'inventory' | 'detail' | 'download' | 'builds' | 'exports';
type Failure = { message?: string; key?: Parameters<typeof t>[0] };
const permissionsReady = () => {
  const state = get(projectPermissions);
  return !!state.permissions && !state.loading && !state.error;
};

export function createPalimpsestHubController(
  identity: () => PackageIdentity | null,
  api = hubApi,
  can: (leaf: string) => boolean = (leaf) => get(serviceCapabilities)(leaf),
  ready: () => boolean = permissionsReady,
  now: () => number = Date.now,
) {
  let bound = $state.raw<PackageIdentity | null>(null);
  let me = $state<HubMe | null>(null);
  let inventory = $state<HubLayer[] | null>(null);
  let detail = $state<HubLayerDetail | null>(null);
  let builds = $state<HubBuild[] | null>(null);
  let exports = $state<HubExport[] | null>(null);
  let filters = $state<HubFilters>({});
  let offset = $state(0);
  let hasNext = $state(false);
  let selected = $state<string | null>(null);
  let busy = $state<Partial<Record<HubLane, boolean>>>({});
  let failures = $state<Partial<Record<HubLane, Failure>>>({});
  let observed = $state<Partial<Record<HubLane, number>>>({});
  let generation = 0;
  let disposed = false;
  let wasReady = false;
  const requests = new Map<HubLane, AbortController>();
  const current = () => !disposed && !!bound && sameHubIdentity(bound, identity());
  const authority = () => current() && ready() && !!me && !busy.me && !failures.me;
  const canInventory = () => authority() && me!.capabilities.inventory && (me!.is_system_admin || can('palimpsest-inventory_reader'));
  const canDownload = () => canInventory() && me!.capabilities.download && (me!.is_system_admin || can('palimpsest-download_user'));
  const canBuilds = () => authority() && me!.capabilities.build;
  function allowed(lane: HubLane): boolean {
    if (!current() || !ready()) return false;
    if (lane === 'me') return true;
    if (lane === 'builds') return canBuilds();
    if (lane === 'download') return canDownload();
    return canInventory();
  }
  function cancel(lane: HubLane) {
    requests.get(lane)?.abort(); requests.delete(lane); busy[lane] = false;
  }
  function closeDetail() {
    cancel('detail'); cancel('download'); detail = null; selected = null;
    delete failures.detail; delete failures.download;
  }
  function reset() {
    ++generation;
    for (const lane of requests.keys()) cancel(lane);
    me = null; inventory = null; detail = null; builds = null; exports = null;
    selected = null; offset = 0; hasNext = false; failures = {}; busy = {}; observed = {};
  }
  function failure(error: unknown): Failure {
    if (error instanceof HubClientError) return { key: error.code === 'too-large' ? 'error.size' : `error.${error.code}` as Parameters<typeof t>[0] };
    return error instanceof Error && error.message ? { message: error.message } : { key: 'error.request' };
  }
  async function run<T>(lane: HubLane, work: (actor: PackageIdentity, signal: AbortSignal) => Promise<T>, apply: (value: T) => void): Promise<boolean> {
    if (!allowed(lane)) return false;
    cancel(lane);
    const actor = { ...bound! }; // Never let a mutable identity object change an in-flight actor.
    const epoch = generation;
    const request = new AbortController();
    requests.set(lane, request); busy[lane] = true; delete failures[lane];
    const owns = () => current() && epoch === generation && sameHubIdentity(actor, identity()) && requests.get(lane) === request && !request.signal.aborted;
    try {
      const value = await work(actor, request.signal);
      if (!owns() || !allowed(lane)) return false;
      apply(value); observed[lane] = now(); return true;
    } catch (error) {
      if (owns() && allowed(lane)) failures[lane] = failure(error);
      return false;
    } finally {
      if (owns()) { requests.delete(lane); busy[lane] = false; }
    }
  }
  async function loadInventory() {
    const query = { ...filters }, page = offset;
    await run('inventory', (actor, signal) => api.layers(actor, signal, query, page), (rows) => {
      inventory = rows.slice(0, HUB_PAGE_SIZE); hasNext = rows.length > HUB_PAGE_SIZE;
    });
  }
  async function loadBuilds() {
    await run('builds', (actor, signal) => api.builds(actor, signal), (rows) => { builds = rows; });
  }
  async function loadExports() {
    await run('exports', (actor, signal) => api.exports(actor, signal), (rows) => { exports = rows; });
  }
  async function loadMe() {
    const digest = selected;
    me = null;
    const loaded = await run('me', (actor, signal) => api.me(actor, signal), (value) => {
      if (value.user_id !== bound?.userId || value.project_id !== bound?.projectId) {
        throw new HubClientError('response');
      }
      me = value;
    });
    if (loaded) {
      // Refresh detail before independent jobs can finish; a later explicit
      // download must not be cancelled by trailing work from this refresh.
      const selectedDetail = digest && canInventory() && selected === digest ? openDetail(digest) : Promise.resolve();
      await Promise.all([loadInventory(), loadBuilds(), loadExports(), selectedDetail]);
    }
  }
  function bindIdentity() {
    if (disposed) return;
    const actor = identity();
    if (sameHubIdentity(bound, actor)) return;
    reset(); bound = actor ? { ...actor } : null; wasReady = ready();
    if (bound && wasReady) void loadMe();
  }
  function syncCapabilities() {
    if (!current()) { bindIdentity(); return; }
    const available = ready();
    if (!available && wasReady) {
      reset(); // No response may cross a pending-authority interval, even ABA.
    }
    const resumed = available && !wasReady;
    wasReady = available;
    if (resumed && !me && !busy.me) { void loadMe(); return; }
    if (!available || !authority()) return;
    if (!canInventory()) {
      for (const lane of ['inventory', 'detail', 'download', 'exports'] as HubLane[]) {
        cancel(lane); delete failures[lane];
      }
      inventory = null; exports = null; closeDetail(); hasNext = false;
    } else {
      if (inventory === null && !busy.inventory && !failures.inventory) void loadInventory();
      if (exports === null && !busy.exports && !failures.exports) void loadExports();
    }
    if (!canBuilds()) { cancel('builds'); builds = null; delete failures.builds; }
    else if (builds === null && !busy.builds && !failures.builds) void loadBuilds();
    if (!canDownload()) cancel('download');
  }
  async function setFilters(next: HubFilters) {
    cancel('inventory'); closeDetail(); inventory = null; hasNext = false; offset = 0;
    delete observed.inventory; filters = { ...next };
    await loadInventory();
  }
  async function page(direction: -1 | 1) {
    if (busy.inventory || direction === 1 && !hasNext || direction === -1 && offset === 0) return;
    closeDetail(); inventory = null; hasNext = false; offset = Math.max(0, offset + direction * HUB_PAGE_SIZE);
    await loadInventory();
  }
  async function openDetail(digest: string) {
    closeDetail(); selected = digest;
    await run('detail', (actor, signal) => api.detail(actor, signal, digest), (value) => {
      if (value.blob_digest !== digest) throw new HubClientError('response');
      detail = value; // Hub, not row.project_id equality, governs public/shared visibility.
    });
  }
  async function download(): Promise<Blob | null> {
    const layer = detail;
    if (!layer || busy.download) return null;
    let result: Blob | null = null;
    await run('download', (actor, signal) => api.download(actor, signal, layer), (blob) => { result = blob; });
    return result;
  }
  async function refresh(visible = true) {
    if (!visible || !current() || !ready() || requests.size) return;
    await loadMe();
  }
  function dispose() { reset(); disposed = true; bound = null; }
  const errorText = (lane: HubLane) => {
    const error = failures[lane];
    return error?.key ? t(error.key) : error?.message ?? '';
  };
  const translatedErrors = $derived.by(() => Object.fromEntries(
    Object.keys(failures).map((lane) => [lane, errorText(lane as HubLane)]),
  ) as Partial<Record<HubLane, string>>);
  return {
    bindIdentity, syncCapabilities, loadMe, loadInventory, loadBuilds, loadExports, setFilters, page,
    openDetail, closeDetail, download, refresh, dispose,
    get me() { return authority() ? me : null; },
    get inventory() { return canInventory() && !failures.inventory ? inventory : null; },
    get detail() { return canInventory() && !failures.detail ? detail : null; },
    get builds() { return canBuilds() && !failures.builds ? builds : null; },
    get exports() { return canInventory() && !failures.exports ? exports : null; },
    get errors() { return current() && ready() ? translatedErrors : {}; },
    get busy() { return current() ? busy : {}; },
    get observed() { return current() && ready() ? observed : {}; },
    get offset() { return current() ? offset : 0; },
    get hasNext() { return canInventory() && hasNext; },
    get selected() { return canInventory() ? selected : null; },
    get canInventory() { return canInventory(); },
    get canDownload() { return canDownload(); },
    get canBuilds() { return canBuilds(); },
  };
}
