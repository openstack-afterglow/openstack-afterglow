import { t } from '$lib/i18n/ns/palimpsest-packages';
import { packageApi, samePackageIdentity } from '$lib/api/palimpsestPackages';
import type { PackageIdentity, ProjectContext, PackageSummary, PackageVersion, PackageKey, CreatePackageKey, IssuedPackageKey } from '$lib/api/palimpsestPackages';
import type { KeyAction } from '$lib/api/palimpsestPackages';
import { get } from 'svelte/store';
import { serviceCapabilities, serviceDenials } from './servicePermissions';

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
export function createPalimpsestPackagesController(identity: () => PackageIdentity | null, api = packageApi, can: (leaf: string) => boolean = (leaf) => get(serviceCapabilities)(leaf), denied: (leaf: string) => boolean = (leaf) => get(serviceDenials)(leaf)) {
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
  let issuingActions = $state.raw<KeyAction[] | null>(null);
  let errors = $state<Partial<Record<Lane, StoredError>>>({});
  const translatedErrors = $derived.by(() => Object.fromEntries(
    Object.entries(errors).map(([lane, error]) => [lane, errorText(error)]),
  ) as Partial<Record<Lane, string>>);
  const translatedLatestVersions = $derived.by(() => Object.fromEntries(
    Object.entries(latestVersions).map(([id, latest]) => [id, { version: latest.version, error: errorText(latest.error) }]),
  ));
  let busy = $state<Partial<Record<Lane, boolean>>>({});
  let bound = $state.raw<PackageIdentity | null>(null);
  let generation = 0;
  let secretGeneration = 0;
  let disposed = false;
  const requests = new Map<Lane, AbortController>();

  // Native context and current project permissions must both be ready for this exact actor.
  const hasContextAuthority = () => !disposed && !!bound && samePackageIdentity(bound, identity()) && !!context && !busy.context && !errors.context;
  const canRead = () => hasContextAuthority() && !!context?.capabilities.packages_read && can('palimpsest-inventory_reader');
  const canPublish = () => hasContextAuthority() && !!context?.capabilities.packages_write && can('palimpsest-publish_editor');
  const canDownload = () => hasContextAuthority() && !!context?.capabilities.packages_download && can('palimpsest-download_user');
  const canIssue = () => hasContextAuthority() && !!context?.capabilities.keys_issue && can('palimpsest-keys_editor');
  const canRevoke = () => hasContextAuthority() && !!context?.capabilities.keys_revoke && can('palimpsest-keys_admin');
  function canDelegate(action: KeyAction) {
    switch (action) {
      case 'packages:inventory': return canRead();
      case 'packages:read': case 'cache:read': return canDownload();
      case 'packages:write': case 'cache:write': return canPublish();
      default: return false;
    }
  }
  // A false capability may mean verification is unavailable. Only loaded denials revoke.
  const issueDenied = () => denied('palimpsest-keys_editor') || context?.capabilities.keys_issue === false;
  function delegationDenied(action: KeyAction) {
    switch (action) {
      case 'packages:inventory': return denied('palimpsest-inventory_reader') || context?.capabilities.packages_read === false;
      case 'packages:read': case 'cache:read': return denied('palimpsest-download_user') || context?.capabilities.packages_download === false;
      case 'packages:write': case 'cache:write': return denied('palimpsest-publish_editor') || context?.capabilities.packages_write === false;
      default: return true;
    }
  }
  function canPublishLane(lane: Lane) {
    switch (lane) {
      case 'context': case 'issue': return true; // Issuance is retained privately, then masked by its getter.
      case 'inventory': case 'metadata': case 'detail': case 'version': return canRead();
      case 'keys': return canIssue() || canRevoke();
      case 'register': return canPublish();
      case 'revoke': return canRevoke();
      case 'download': return canDownload();
    }
  }

  function reset() {
    generation += 1;
    secretGeneration += 1;
    for (const request of requests.values()) request.abort();
    requests.clear();
    context = null; inventory = null; nextCursor = null; detail = null;
    latestVersions = {};
    versions = null; versionsCursor = null; version = null; keys = null; issued = null; issuingActions = null;
    errors = {}; busy = {};
  }
  function discardSecret() {
    secretGeneration += 1;
    issued = null;
  }
  function syncCapabilities() {
    if (!bound || !samePackageIdentity(bound, identity()) || issueDenied() || issued?.key.actions.some(delegationDenied) || issuingActions?.some(delegationDenied)) discardSecret();
    if (!canIssue() && !canRevoke()) keys = null;
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
    const namespace = context?.namespace;
    busy[lane] = true; errors[lane] = '';
    const owns = () => !disposed && !request.signal.aborted && currentGeneration === generation && requests.get(lane) === request && samePackageIdentity(actor, identity());
    try {
      const value = await work(actor, request.signal);
      if (owns() && canPublishLane(lane) && (!namespaceRequired || namespace === context?.namespace)) apply(value);
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
    if (!canRead() || !actor || !bound || !samePackageIdentity(actor, bound) || !context?.namespace || !inventory) return;
    requests.get('metadata')?.abort();
    const request = new AbortController();
    requests.set('metadata', request);
    const epoch = generation;
    const namespace = context.namespace;
    const pending = inventory.filter((item) => !latestVersions[item.package_id]);
    let index = 0;
    const owns = () => !disposed && !request.signal.aborted && epoch === generation && requests.get('metadata') === request && samePackageIdentity(actor, identity());
    busy.metadata = true;
    async function worker() {
      while (owns() && canRead() && namespace === context?.namespace && index < pending.length) {
        const item = pending[index++];
        try {
          const history = await api.versions(identity()!, request.signal, item.name, undefined, 1);
          if (!owns() || !canRead() || namespace !== context?.namespace) return;
          assertOwner(history);
          if (history.package !== item.name) throw new LocalizedError('error.versionPackage');
          const value = history.items[0] ?? null;
          if (value) { assertOwner(value); if (value.package !== item.name) throw new LocalizedError('error.versionPackage'); }
          latestVersions[item.package_id] = { version: value, error: value ? '' : new LocalizedError('error.noLatest') };
        } catch (error) {
          if (owns() && canRead() && namespace === context?.namespace) latestVersions[item.package_id] = { version: null, error: requestError(error, 'error.latest') };
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(4, pending.length) }, () => worker()));
    if (owns()) { busy.metadata = false; requests.delete('metadata'); }
  }
  async function loadInventory(more = false) {
    if (!canRead()) return;
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
      assertOwner(value, false);
      if (context && context.namespace !== value.namespace) reset();
      context = value;
      syncCapabilities();
    }, false);
    if (canRead() && context?.namespace && !busy.inventory) void loadInventory();
  }
  function bindIdentity() {
    const current = identity();
    if (disposed) return;
    if (samePackageIdentity(bound, current)) { bound = current; return; }
    reset(); bound = current;
    if (bound) void loadContext();
  }
  async function register() {
    if (!context || context.namespace || !canPublish()) return;
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
    if (!canRead()) return;
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
    if (!canRead() || !name || !versionsCursor) return;
    await run('detail', (actor, signal) => api.versions(actor, signal, name, versionsCursor ?? undefined), (page) => {
      assertOwner(page);
      if (page.package !== name) throw new LocalizedError('error.historyPackage');
      page.items.forEach((item) => { assertOwner(item); if (item.package !== name) throw new LocalizedError('error.versionPackage'); });
      versions = [...versions ?? [], ...page.items]; versionsCursor = page.next_cursor;
    });
  }
  async function selectVersion(digest: string) {
    const name = detail?.name;
    if (!canRead() || !name) return;
    version = null;
    await run('version', (actor, signal) => api.version(actor, signal, name, digest), (value) => {
      assertOwner(value);
      if (value.package !== name || value.root_digest !== digest) throw new LocalizedError('error.version');
      version = value;
    });
  }
  async function resolveTag(tag: string) {
    const name = detail?.name;
    if (!canRead() || !name) return;
    version = null;
    await run('version', (actor, signal) => api.resolve(actor, signal, name, tag), (value) => {
      assertOwner(value);
      if (value.package !== name || value.tag !== tag) throw new LocalizedError('error.tag');
      void selectVersion(value.digest);
    });
  }
  async function loadKeys() {
    if (!canIssue() && !canRevoke()) { keys = null; return; }
    keys = null;
    await run('keys', (actor, signal) => api.keys(actor, signal), (page) => {
      assertOwner(page); page.items.forEach(assertKey); keys = page.items;
    });
  }
  async function issueKey(body: CreatePackageKey) {
    if (!canIssue() || busy.issue || issued) return;
    if (!body.actions.length || !body.actions.every(canDelegate)) { errors.issue = new LocalizedError('validation.actions'); return; }
    discardSecret();
    const epoch = secretGeneration;
    const actor = identity();
    const delegatedActions = [...body.actions];
    issuingActions = delegatedActions;
    try {
      await run('issue', (requestActor, signal) => api.issue(requestActor, signal, { ...body, actions: delegatedActions }), (value) => {
        assertKey(value.key);
        syncCapabilities();
        if (epoch === secretGeneration && !issueDenied() && !delegatedActions.some(delegationDenied) && !value.key.actions.some(delegationDenied)) issued = value;
      });
    } finally {
      if (issuingActions === delegatedActions) issuingActions = null;
      if (!disposed && samePackageIdentity(actor, identity()) && context?.namespace) void loadKeys();
    }
  }
  async function revokeKey(key: PackageKey) {
    if (!canRevoke()) return;
    assertKey(key);
    await run('revoke', (actor, signal) => api.revoke(actor, signal, key.key_id), () => {
      if (issued?.key.key_id === key.key_id) issued = null;
      void loadKeys();
    });
  }
  async function download(name: string, digest: string) {
    if (!canDownload()) return;
    await run('download', (actor, signal) => api.download(actor, signal, name, digest), (blob) => {
      if (!canDownload()) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a'); anchor.href = url;
      anchor.download = `${name.replaceAll('/', '-')}-${digest.replace('sha256:', '')}.tar`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 0);
    });
  }
  function dispose() { reset(); bound = null; disposed = true; }
  return {
    get canRead() { return canRead(); }, get canPublish() { return canPublish(); }, get canDownload() { return canDownload(); },
    get canIssue() { return canIssue(); }, get canRevoke() { return canRevoke(); }, get issueDenied() { return issueDenied(); }, canDelegate,
    get context() { return context; }, get inventory() { return inventory; }, get nextCursor() { return nextCursor; },
    get latestVersions() { return translatedLatestVersions; },
    get detail() { return canRead() ? detail : null; }, get versions() { return canRead() ? versions : null; }, get versionsCursor() { return canRead() ? versionsCursor : null; },
    get version() { return canRead() ? version : null; }, get keys() { return canIssue() || canRevoke() ? keys : null; },
    get issued() { return canIssue() && !issueDenied() && issued?.key.actions.every((action) => canDelegate(action) && !delegationDenied(action)) ? issued : null; },
    get busy() { return busy; }, get errors() { return translatedErrors; },
    bindIdentity, loadContext, loadInventory, register, openPackage, closeDetail, moreVersions, selectVersion, resolveTag,
    loadKeys, issueKey, revokeKey, download, discardSecret, syncCapabilities, dispose,
  };
}
