import { t } from '$lib/i18n/ns/palimpsest-packages';
import { packageApi, samePackageIdentity } from '$lib/api/palimpsestPackages';
import type { PackageIdentity, ProjectContext, PackageSummary, PackageVersion, PackageKey, CreatePackageKey, IssuedPackageKey } from '$lib/api/palimpsestPackages';

type MessageKey = Parameters<typeof t>[0];
// Store local message keys separately from opaque server errors; translate only when rendered.
class LocalizedError extends Error {
  constructor(readonly key: MessageKey) { super(); }
}
type StoredError = string | LocalizedError;
function errorText(error: StoredError) { return typeof error === 'string' ? error : t(error.key); }
function requestError(error: unknown, fallback: MessageKey): StoredError {
  return error instanceof LocalizedError ? error : error instanceof Error ? error.message : new LocalizedError(fallback);
}

type Lane = 'context' | 'inventory' | 'metadata' | 'detail' | 'version' | 'keys' | 'register' | 'issue' | 'revoke' | 'download';
export function createPalimpsestPackagesController(identity: () => PackageIdentity | null, api = packageApi) {
  let context = $state<ProjectContext | null>(null);
  let inventory = $state<PackageSummary[] | null>(null);
  let latestVersions = $state<Record<string, { version: PackageVersion | null; error: StoredError }>>({});
  let nextCursor = $state<string | null>(null);
  let detail = $state<PackageSummary | null>(null);
  let versions = $state<PackageVersion[] | null>(null);
  let versionsCursor = $state<string | null>(null);
  let version = $state<PackageVersion | null>(null);
  let keys = $state<PackageKey[] | null>(null);
  let issued = $state<IssuedPackageKey | null>(null);
  let errors = $state<Partial<Record<Lane, StoredError>>>({});
  const translatedErrors = $derived.by(() => Object.fromEntries(
    Object.entries(errors).map(([lane, error]) => [lane, errorText(error)]),
  ) as Partial<Record<Lane, string>>);
  const translatedLatestVersions = $derived.by(() => Object.fromEntries(
    Object.entries(latestVersions).map(([id, latest]) => [id, { version: latest.version, error: errorText(latest.error) }]),
  ));
  let busy = $state<Partial<Record<Lane, boolean>>>({});
  let bound: PackageIdentity | null = null;
  let generation = 0;
  let secretGeneration = 0;
  let disposed = false;
  const requests = new Map<Lane, AbortController>();

  function reset() {
    generation += 1;
    secretGeneration += 1;
    for (const request of requests.values()) request.abort();
    requests.clear();
    context = null; inventory = null; nextCursor = null; detail = null;
    latestVersions = {};
    versions = null; versionsCursor = null; version = null; keys = null; issued = null;
    errors = {}; busy = {};
  }
  function discardSecret() {
    secretGeneration += 1;
    issued = null;
  }
  async function run<T>(lane: Lane, work: (actor: PackageIdentity, signal: AbortSignal) => Promise<T>, apply: (value: T) => void, namespaceRequired = true) {
    const actor = identity();
    if (disposed || !actor || !bound || !samePackageIdentity(actor, bound) || (namespaceRequired && !context?.namespace)) return;
    if (lane === 'register' || lane === 'issue' || lane === 'revoke') {
      if (requests.has(lane)) return;
    } else requests.get(lane)?.abort();
    const request = new AbortController();
    requests.set(lane, request);
    const currentGeneration = generation;
    busy[lane] = true; errors[lane] = '';
    const owns = () => !disposed && !request.signal.aborted && currentGeneration === generation && requests.get(lane) === request && samePackageIdentity(actor, identity());
    try {
      const value = await work(actor, request.signal);
      if (owns()) apply(value);
    } catch (error) {
      if (owns()) errors[lane] = requestError(error, 'error.request');
    } finally {
      if (owns()) { busy[lane] = false; requests.delete(lane); }
    }
  }
  function assertOwner(value: { project_id: string; namespace?: string | null }, namespaceRequired = true) {
    if (!bound || value.project_id !== bound.projectId || (namespaceRequired && value.namespace !== context?.namespace)) {
      throw new LocalizedError('error.owner');
    }
  }
  function assertKey(key: PackageKey) {
    assertOwner(key);
    if (!bound || key.owner_user_id !== bound.userId) throw new LocalizedError('error.keyOwner');
  }
  async function hydrateLatest() {
    const actor = identity();
    if (disposed || !actor || !bound || !samePackageIdentity(actor, bound) || !context?.namespace || !inventory) return;
    requests.get('metadata')?.abort();
    const request = new AbortController();
    requests.set('metadata', request);
    const epoch = generation;
    const pending = inventory.filter((item) => !latestVersions[item.package_id]);
    let index = 0;
    const owns = () => !disposed && !request.signal.aborted && epoch === generation && requests.get('metadata') === request && samePackageIdentity(actor, identity());
    busy.metadata = true;
    async function worker() {
      while (owns() && index < pending.length) {
        const item = pending[index++];
        try {
          const history = await api.versions(actor!, request.signal, item.name, undefined, 1);
          if (!owns()) return;
          assertOwner(history);
          if (history.package !== item.name) throw new LocalizedError('error.versionPackage');
          const value = history.items[0] ?? null;
          if (value) { assertOwner(value); if (value.package !== item.name) throw new LocalizedError('error.versionPackage'); }
          latestVersions[item.package_id] = { version: value, error: value ? '' : new LocalizedError('error.noLatest') };
        } catch (error) {
          if (owns()) latestVersions[item.package_id] = { version: null, error: requestError(error, 'error.latest') };
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(4, pending.length) }, () => worker()));
    if (owns()) { busy.metadata = false; requests.delete('metadata'); }
  }
  async function loadInventory(more = false) {
    if (!context?.capabilities.packages_read) return;
    if (!more) {
      requests.get('metadata')?.abort(); requests.delete('metadata'); busy.metadata = false;
      inventory = null; nextCursor = null; latestVersions = {};
    }
    let metadata: Promise<void> | undefined;
    await run('inventory', (actor, signal) => api.inventory(actor, signal, more ? nextCursor ?? undefined : undefined), (page) => {
      assertOwner(page);
      page.items.forEach((item) => assertOwner(item));
      inventory = more ? [...inventory ?? [], ...page.items] : page.items;
      nextCursor = page.next_cursor;
      metadata = hydrateLatest();
    });
    await metadata;
  }
  async function loadContext() {
    await run('context', (actor, signal) => api.context(actor, signal), (value) => {
      assertOwner(value, false); context = value;
      if (value.namespace && value.capabilities.packages_read) void loadInventory();
    }, false);
  }
  function bindIdentity() {
    const current = identity();
    if (disposed) return;
    if (samePackageIdentity(bound, current)) { bound = current; return; }
    reset(); bound = current;
    if (bound) void loadContext();
  }
  async function register() {
    if (!context || context.namespace || !context.capabilities.packages_write) return;
    await run('register', (actor, signal) => api.register(actor, signal), (value) => {
      assertOwner(value, false);
      void loadContext();
    }, false);
  }
  function closeDetail() {
    for (const lane of ['detail', 'version', 'download'] as Lane[]) {
      requests.get(lane)?.abort(); requests.delete(lane); busy[lane] = false; errors[lane] = '';
    }
    detail = null; versions = null; versionsCursor = null; version = null;
  }
  async function openPackage(name: string, digest?: string, namespace?: string) {
    closeDetail();
    if (namespace && namespace !== context?.namespace) { errors.detail = new LocalizedError('error.linkNamespace'); return; }
    await run('detail', async (actor, signal) => {
      const [summary, history] = await Promise.all([api.detail(actor, signal, name), api.versions(actor, signal, name)]);
      return { summary, history };
    }, ({ summary, history }) => {
      assertOwner(summary); assertOwner(history);
      if (summary.name !== name) throw new LocalizedError('error.packageName');
      if (history.package !== name) throw new LocalizedError('error.historyPackage');
      history.items.forEach((item) => { assertOwner(item); if (item.package !== name) throw new LocalizedError('error.versionPackage'); });
      detail = summary; versions = history.items; versionsCursor = history.next_cursor;
      if (digest) void selectVersion(digest);
    });
  }
  async function moreVersions() {
    const name = detail?.name;
    if (!name || !versionsCursor) return;
    await run('detail', (actor, signal) => api.versions(actor, signal, name, versionsCursor ?? undefined), (page) => {
      assertOwner(page);
      if (page.package !== name) throw new LocalizedError('error.historyPackage');
      page.items.forEach((item) => { assertOwner(item); if (item.package !== name) throw new LocalizedError('error.versionPackage'); });
      versions = [...versions ?? [], ...page.items]; versionsCursor = page.next_cursor;
    });
  }
  async function selectVersion(digest: string) {
    const name = detail?.name;
    if (!name) return;
    version = null;
    await run('version', (actor, signal) => api.version(actor, signal, name, digest), (value) => {
      assertOwner(value);
      if (value.package !== name || value.root_digest !== digest) throw new LocalizedError('error.version');
      version = value;
    });
  }
  async function resolveTag(tag: string) {
    const name = detail?.name;
    if (!name) return;
    version = null;
    await run('version', (actor, signal) => api.resolve(actor, signal, name, tag), (value) => {
      assertOwner(value);
      if (value.package !== name || value.tag !== tag) throw new LocalizedError('error.tag');
      void selectVersion(value.digest);
    });
  }
  async function loadKeys() {
    keys = null;
    await run('keys', (actor, signal) => api.keys(actor, signal), (page) => {
      assertOwner(page); page.items.forEach(assertKey); keys = page.items;
    });
  }
  async function issueKey(body: CreatePackageKey) {
    if (!context?.capabilities.keys_issue || busy.issue || issued) return;
    discardSecret();
    const epoch = secretGeneration;
    const actor = identity();
    try {
      await run('issue', (requestActor, signal) => api.issue(requestActor, signal, body), (value) => {
        assertKey(value.key);
        if (epoch === secretGeneration) issued = value;
      });
    } finally {
      if (!disposed && samePackageIdentity(actor, identity()) && context?.namespace) void loadKeys();
    }
  }
  async function revokeKey(key: PackageKey) {
    assertKey(key);
    await run('revoke', (actor, signal) => api.revoke(actor, signal, key.key_id), () => {
      if (issued?.key.key_id === key.key_id) issued = null;
      void loadKeys();
    });
  }
  async function download(name: string, digest: string) {
    await run('download', (actor, signal) => api.download(actor, signal, name, digest), (blob) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a'); anchor.href = url;
      anchor.download = `${name.replaceAll('/', '-')}-${digest.replace('sha256:', '')}.tar`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 0);
    });
  }
  function dispose() { reset(); bound = null; disposed = true; }
  return {
    get context() { return context; }, get inventory() { return inventory; }, get nextCursor() { return nextCursor; },
    get latestVersions() { return translatedLatestVersions; },
    get detail() { return detail; }, get versions() { return versions; }, get versionsCursor() { return versionsCursor; },
    get version() { return version; }, get keys() { return keys; }, get issued() { return issued; },
    get busy() { return busy; }, get errors() { return translatedErrors; },
    bindIdentity, loadContext, loadInventory, register, openPackage, closeDetail, moreVersions, selectVersion, resolveTag,
    loadKeys, issueKey, revokeKey, download, discardSecret, dispose,
  };
}
