import { get } from 'svelte/store';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { catalogApi, type CatalogSource, type CatalogLayerPage, type CatalogLayerDetail } from '$lib/api/palimpsestCatalog';
import type { PackageIdentity } from '$lib/api/palimpsestPackages';
import { ApiError } from '$lib/api/errors';

export type CatalogFailure = 'denied' | 'unavailable' | 'failed' | 'notFound' | 'invalidResponse';
export function createPalimpsestCatalogController() {
  let source = $state<CatalogSource>('managed');
  let query = $state('');
  let page = $state<CatalogLayerPage | null>(null);
  let loading = $state(false);
  let error = $state<CatalogFailure | null>(null);
  let selected = $state<string | null>(null);
  let detail = $state<CatalogLayerDetail | null>(null);
  let detailLoading = $state(false);
  let detailError = $state<CatalogFailure | null>(null);
  let authorized = $state(false);
  let identity: PackageIdentity | null = null;
  let authorityKey = '', epoch = 0, listTicket = 0, detailTicket = 0;
  let listAbort: AbortController | null = null, detailAbort: AbortController | null = null;
  let previous = $state<number[]>([]);
  let requestedOffset = 0;
  let unsubscribers: (() => void)[] = [];
  let disposed = false;

  function closeDetail() {
    ++detailTicket; detailAbort?.abort(); detailAbort = null;
    selected = null; detail = null; detailLoading = false; detailError = null;
  }
  function clearList() {
    ++listTicket; listAbort?.abort(); listAbort = null;
    page = null; loading = false; error = null; previous = []; closeDetail();
  }
  function syncAuthority() {
    const actor = get(auth);
    const ready = get(authReady) && !get(projectSwitching) && !get(logoutInProgress);
    const allowed = ready && actor.isSystemAdmin && !!actor.token && !!actor.userId;
    const key = JSON.stringify([allowed, actor.token, actor.userId, actor.projectId, actor.domainId, actor.sessionId]);
    if (key === authorityKey) return;
    authorityKey = key; ++epoch; authorized = allowed;
    identity = allowed ? { token: actor.token!, userId: actor.userId!, projectId: actor.projectId ?? '' } : null;
    clearList();
    if (identity) void load(0);
  }
  function start() {
    if (disposed || unsubscribers.length) return;
    // Store subscriptions fence even same-tick A→B→A transitions before a Svelte effect runs.
    let binding = true;
    const change = () => { if (!binding) syncAuthority(); };
    unsubscribers = [auth.subscribe(change), authReady.subscribe(change), projectSwitching.subscribe(change), logoutInProgress.subscribe(change)];
    binding = false; syncAuthority();
  }
  const owns = (generation: number, actor: PackageIdentity) => !disposed && authorized && generation === epoch && identity === actor;
  function failure(cause: unknown, isDetail = false): CatalogFailure {
    if (cause instanceof ApiError) {
      if (cause.status === 401 || cause.status === 403) return 'denied';
      if (cause.status === 404) return isDetail ? 'notFound' : 'unavailable';
      if (cause.status === 502 || cause.status === 503 || cause.status === 504) return 'unavailable';
    }
    return 'failed';
  }
  async function load(offset: number) {
    if (!identity || disposed) return;
    requestedOffset = offset;
    const actor = identity, generation = epoch, ticket = ++listTicket, requestedSource = source, requestedQuery = query;
    listAbort?.abort(); const abort = new AbortController(); listAbort = abort;
    loading = true; page = null; error = null; closeDetail();
    try {
      const result = await catalogApi.layers(actor, abort.signal, requestedSource, requestedQuery, offset);
      if (!owns(generation, actor) || ticket !== listTicket) return;
      if (result.source !== requestedSource || result.offset !== offset || !Array.isArray(result.items)
        || (result.has_more && (!Number.isSafeInteger(result.next_offset) || result.next_offset! <= offset))) {
        error = 'invalidResponse'; return;
      }
      page = result;
    } catch (cause) {
      if (owns(generation, actor) && ticket === listTicket) error = failure(cause);
    } finally {
      if (owns(generation, actor) && ticket === listTicket) loading = false;
    }
  }
  async function search(value: string) {
    query = value.trim(); previous = []; await load(0);
  }
  async function setSource(value: CatalogSource) {
    if (value === source) return;
    source = value; clearList(); await load(0);
  }
  async function next() {
    if (loading || !page?.has_more || page.next_offset === null) return;
    previous.push(page.offset); await load(page.next_offset);
  }
  async function back() {
    if (loading || !previous.length) return;
    await load(previous.pop()!);
  }
  async function openDetail(id: string) {
    if (!identity || disposed) return;
    closeDetail(); selected = id; detailLoading = true;
    const actor = identity, generation = epoch, ticket = detailTicket, requestedSource = source;
    const abort = new AbortController(); detailAbort = abort;
    try {
      const result = await catalogApi.detail(actor, abort.signal, requestedSource, id);
      if (!owns(generation, actor) || ticket !== detailTicket) return;
      if (result.id !== id || !Array.isArray(result.ancestors) || !Array.isArray(result.children) || !Array.isArray(result.bundles)) {
        detailError = 'invalidResponse'; return;
      }
      detail = result;
    } catch (cause) {
      if (owns(generation, actor) && ticket === detailTicket) detailError = failure(cause, true);
    } finally {
      if (owns(generation, actor) && ticket === detailTicket) detailLoading = false;
    }
  }
  function dispose() {
    disposed = true; ++epoch; clearList(); authorized = false; identity = null;
    for (const unsubscribe of unsubscribers) unsubscribe();
    unsubscribers = [];
  }
  return {
    get source() { return source; }, get query() { return query; }, get page() { return page; },
    get loading() { return loading; }, get error() { return error; }, get authorized() { return authorized; },
    get selected() { return selected; }, get detail() { return detail; }, get detailLoading() { return detailLoading; },
    get detailError() { return detailError; }, get canBack() { return previous.length > 0; },
    start, search, setSource, next, back, openDetail, closeDetail, dispose,
    refresh: () => load(requestedOffset),
  };
}
