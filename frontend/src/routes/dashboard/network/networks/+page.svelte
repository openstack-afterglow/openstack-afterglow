<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
  import { t } from '$lib/i18n/ns/network-pages';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { onDestroy, untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { sessionScopeKey } from '$lib/utils/authSession';
  import { api, ApiError } from '$lib/api/client';
  import { createSwr } from '$lib/utils/swr.svelte';
  import { apiMut } from '$lib/api/mutations';
  import type { Network, FloatingIp } from '$lib/types/networks';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import SlidePanel from '$lib/components/SlidePanel.svelte';
  import NetworkDetailPanel from '$lib/components/NetworkDetailPanel.svelte';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import FloatingIpAllocateModal from '$lib/components/network/FloatingIpAllocateModal.svelte';
  import NetworkCreateModal from '$lib/components/dashboard/network/networks/NetworkCreateModal.svelte';
  import NetworksTableCard from '$lib/components/dashboard/network/networks/NetworksTableCard.svelte';
  import FloatingIpCard from '$lib/components/dashboard/network/networks/FloatingIpCard.svelte';
  import { toast } from '$lib/stores/toast';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations, partitionBulkIds } from '$lib/utils/bulkActions';
  import { Alert, Button, EmptyState, Field, Pagination, PageHeader, PageShell, ResourceToolbar, SelectInput } from '$lib/components/ui';
  import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceState, type ExperienceContext } from '$lib/utils/experience';
  import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';

  let networks = $state<Network[]>([]);
  let floatingIps = $state<FloatingIp[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let hasInventory = $state(false);
  let deleting = $state<string | null>(null);
  let selectedNetworkId = $state<string | null>(null);
  let defaultNetworkId = $state<string | null>(null);
  let settingDefault = $state<string | null>(null);
  let showAllocateModal = $state(false);
  let showModal = $state(false);
  let creating = $state(false);
  let createError = $state('');
  let activeDomain = $state<'networks' | 'floating-ips' | null>(null);
  let selection = createResourceSelection();
  let busy = $state(false);
  let search = $state('');
  const columns = (): TableColumn<Network>[] => [
    { key: 'name', label: tl('table.name'), value: row => row.name || row.id },
    { key: 'cidr', label: 'CIDR', value: row => row.cidrs?.join(', ') || null, filterValues: row => row.cidrs?.length ? row.cidrs : [null] },
    { key: 'type', label: t('networksTable.type'), value: row => row.is_external ? 'external' : row.is_shared ? 'shared' : 'internal', format: (_value, row) => row.is_external ? t('networksTable.external') : row.is_shared ? t('networksTable.shared') : t('networksTable.internal') },
    { key: 'subnets', label: t('networksTable.subnets'), value: row => row.subnets.length },
    { key: 'status', label: t('networksTable.status'), value: row => row.status },
  ];
  const view = createTableView({ rows: () => networks, columns, search: () => search, searchable: row => [row.name, row.id, ...(row.cidrs ?? [])] });
  let floatingSearch = $state('');
  const floatingColumns = (): TableColumn<FloatingIp>[] => [
    { key: 'address', label: t('floatingIpCard.title'), value: row => row.floating_ip_address },
    { key: 'fixed', label: t('floatingIps.columns.fixedIp'), value: row => row.fixed_ip_address },
    { key: 'status', label: t('floatingIps.columns.status'), value: row => row.status },
  ];
  const floatingView = createTableView({ rows: () => floatingIps, columns: floatingColumns, search: () => floatingSearch, searchable: row => [row.id, row.floating_ip_address, row.fixed_ip_address ?? '', row.status] });
  const visibleFloatingIds = $derived(new Set(floatingView.rows.map(row => row.id)));
  $effect(() => { const ids = visibleFloatingIds; untrack(() => { if (activeDomain === 'floating-ips') selection.retain(ids); }); });
  let displayPage = $state(1);
  let pageSize = $state(20);
  let stateVersion = 0;
  let live = true;
  onDestroy(() => { live = false; });
  const filteredNetworks = $derived(view.rows);
  const pageCount = $derived(Math.max(1, Math.ceil(filteredNetworks.length / pageSize)));
  const visibleNetworks = $derived(filteredNetworks.slice((Math.min(displayPage, pageCount) - 1) * pageSize, Math.min(displayPage, pageCount) * pageSize));
  $effect(() => { search; view.sort; view.filters; pageSize; displayPage = 1; });
  $effect(() => { if (displayPage > pageCount) displayPage = pageCount; });
  let selectableNetworkIds = $derived(new Set(networks.filter((network) => network.project_id === $auth.projectId && !network.is_external).map((network) => network.id)));
  const visibleSelectableIds = $derived(new Set(visibleNetworks.filter((network) => selectableNetworkIds.has(network.id)).map((network) => network.id)));
  $effect(() => { search; view.sort; view.filters; displayPage; pageSize; untrack(() => { if (activeDomain === 'networks') selection.clear(); }); });
  $effect(() => { const ids = visibleSelectableIds; untrack(() => { if (activeDomain === 'networks') selection.retain(ids); }); });
  let selectableFloatingIpIds = $derived(new Set(floatingIps.map((fip) => fip.id)));

  function toggleSelect(domain: 'networks' | 'floating-ips', id: string) {
    if (activeDomain !== domain) {
      selection.clear();
      activeDomain = domain;
    }
    selection.toggle(id);
  }
  function toggleAll(domain: 'networks' | 'floating-ips') {
    if (activeDomain !== domain) {
      selection.clear();
      activeDomain = domain;
    }
    selection.toggleAll(domain === 'networks' ? visibleSelectableIds : visibleFloatingIds);
  }


  $effect(() => { if (!showModal) createError = ''; });

  const tok = () => $auth.token ?? undefined;
  const pid = () => $auth.projectId ?? undefined;
  const { swrGet, swrSet } = createSwr(() => $auth.projectId);

  async function fetchNetworks(opts?: { refresh?: boolean }, experience: ExperienceContext | undefined = beginExperienceLoad('network', 'resource.list')) {
    const path = '/api/v1/networks';
    const projectId = pid(), userId = $auth.userId;
    let appliedVersion = 0;
    const current = () => live && appliedVersion === stateVersion && pid() === projectId && $auth.userId === userId;
    if (loading || refreshing) experienceState(experience, 'loading');
    const cached = swrGet<Network[]>(path);
    if (cached && networks.length === 0) {
      networks = cached;
      const cachedVersion = ++stateVersion;
      experienceState(experience, cached.length ? 'ready' : 'empty');
      if (experience) void experienceApplied(experience, { transport: 'cache' }, () => live && stateVersion === cachedVersion && pid() === projectId && $auth.userId === userId);
    }
    try {
      networks = await api.withExperience(experience).get<Network[]>(path, tok(), pid(), opts);
      hasInventory = true;
      swrSet(path, networks);
      if (activeDomain === 'networks') selection.retain(visibleSelectableIds);
      error = '';
      appliedVersion = ++stateVersion;
      if (experience?.action !== 'create') experienceState(experience, networks.length ? 'ready' : 'empty');
      if (experience) void experienceApplied(experience, {}, current);
    } catch (e) {
      error = e instanceof ApiError ? t('networks.loadFailed', { status: e.status }) : t('networks.serverError');
      appliedVersion = ++stateVersion;
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience, {}, current);
    } finally { loading = false; }
  }

  async function fetchDefaultNetwork() {
    try {
      const record = await api.get<{ network_id: string | null }>('/api/v1/networks/default', tok(), pid());
      defaultNetworkId = record.network_id;
    } catch { defaultNetworkId = null; }
  }

  async function setAsDefault(networkId: string) {
    if (!selectableNetworkIds.has(networkId)) {
      toast.warning(t('networks.onlyOwnedDefault'));
      return;
    }
    settingDefault = networkId;
    const experience = beginExperienceAction('network', 'update', 'resource.list');
    try {
      await api.withExperience(experience).put('/api/v1/networks/default', { network_id: networkId }, tok(), pid());
      defaultNetworkId = networkId;
      if (experience) void experienceApplied(experience);
    } catch (e) {
      toast.error(t('networks.setDefaultFailed', { error: e instanceof ApiError ? e.message : String(e) }));
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience);
    } finally { settingDefault = null; }
  }

  async function fetchFloatingIps(opts?: { refresh?: boolean }, experience: ExperienceContext | undefined = beginExperienceLoad('network', 'resource.list')) {
    const projectId = pid(), userId = $auth.userId;
    try {
      floatingIps = await api.withExperience(experience).get<FloatingIp[]>('/api/v1/networks/floating-ips', tok(), pid(), opts);
      if (activeDomain === 'floating-ips') selection.retain(floatingIps.map((fip) => fip.id));
      experienceState(experience, floatingIps.length ? 'ready' : 'empty');
      if (experience) {
        const assigned = floatingIps;
        void experienceApplied(experience, {}, () => live && floatingIps === assigned && pid() === projectId && $auth.userId === userId);
      }
    } catch { /* 오류 무시 */ }
  }
  async function runBulkAction(domain: 'networks' | 'floating-ips', eligible: ReadonlySet<string>, mutate: (id: string, token: string | undefined, projectId: string | undefined, experience: ExperienceContext | undefined) => Promise<unknown>) {
    const snapshotIds = [...selection.ids];
    const { eligible: eligibleIds, skipped } = partitionBulkIds(snapshotIds, eligible);
    if (eligibleIds.length === 0) return;
    if (!await confirmDialog(t(domain === 'networks' ? 'networks.bulk.deleteConfirm' : 'networks.bulk.releaseConfirm', { count: eligibleIds.length, skipped: skipped.length }))) return;
    const tokenSnapshot = tok();
    const projectSnapshot = pid();
    busy = true;
    const experience = beginExperienceAction('network', 'delete', 'resource.list');
    try {
      const results = await executeBulkMutations(eligibleIds, (id) => mutate(id, tokenSnapshot, projectSnapshot, experience));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      const failedCount = results.length - succeeded.length;
      const sameProjectDomain = projectSnapshot === pid() && activeDomain === domain;
      if (sameProjectDomain) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(t(domain === 'networks' ? 'networks.bulk.deleteDone' : 'networks.bulk.releaseDone', { count: succeeded.length }));
      if (failedCount > 0) {
        toast.error(t(domain === 'networks' ? 'networks.bulk.deleteFailed' : 'networks.bulk.releaseFailed', { count: failedCount }));
        experienceState(experience, 'error');
        if (experience) void experienceApplied(experience);
      }
      if (skipped.length > 0) toast.warning(t(domain === 'networks' ? 'networks.bulk.deleteSkipped' : 'networks.bulk.releaseSkipped', { count: skipped.length }));
      if (sameProjectDomain) {
        if (domain === 'networks') await fetchNetworks({ refresh: true }, experience);
        else await fetchFloatingIps(undefined, experience);
      }
    } finally {
      busy = false;
    }
  }
  function bulkActions(): BulkSelectionAction[] {
    if (activeDomain === 'networks') {
      return [{
        key: 'delete-network',
        label: t('networks.delete'),
        tone: 'danger',
        disabled: partitionBulkIds(selection.ids, selectableNetworkIds).eligible.length === 0,
        onAction: () => runBulkAction('networks', selectableNetworkIds, (id, token, projectId, experience) => api.withExperience(experience).delete(`/api/v1/networks/${id}`, token, projectId)),
      }];
    }
    if (activeDomain === 'floating-ips') {
      return [{
        key: 'release-floating-ip',
        label: t('networks.release'),
        tone: 'warning',
        disabled: partitionBulkIds(selection.ids, selectableFloatingIpIds).eligible.length === 0,
        onAction: () => runBulkAction('floating-ips', selectableFloatingIpIds, (id, token, projectId, experience) => api.withExperience(experience).delete(`/api/v1/networks/floating-ips/${id}`, token, projectId)),
      }];
    }
    return [];
  }

  async function forceRefresh() {
    const experience = beginExperienceAction('network', 'refresh', 'resource.list');
    refreshing = true;
    try { await Promise.all([fetchNetworks({ refresh: true }, experience), fetchFloatingIps({ refresh: true }, experience)]); }
    finally { refreshing = false; }
  }

  async function createNetwork(body: Record<string, unknown>): Promise<boolean> {
    creating = true; createError = '';
    const experience = beginExperienceAction('network', 'create', 'resource.list');
    try {
      await apiMut(t('networks.create'), () => api.withExperience(experience).post('/api/v1/networks', body, tok(), pid()));
      await fetchNetworks(undefined, experience);
      return true;
    } catch (e) {
      createError = e instanceof ApiError ? e.message : t('networks.createFailed');
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience);
      return false;
    } finally { creating = false; }
  }

  async function deleteNetwork(id: string, name: string, isExternal: boolean) {
    if (!selectableNetworkIds.has(id)) { toast.warning(t('networks.onlyOwnedDelete')); return; }
    if (isExternal) { toast.warning(t('networks.externalDelete')); return; }
    if (!await confirmDialog(`${t('networks.deleteConfirm', { name: name ? `${name} (${id})` : id })}\n${t('list.deleteImpact')}`)) return;
    deleting = id;
    const experience = beginExperienceAction('network', 'delete', 'resource.list');
    try {
      await apiMut(t('networks.deleteAction'), () => api.withExperience(experience).delete(`/api/v1/networks/${id}`, tok(), pid()));
      await fetchNetworks(undefined, experience);
    } catch {
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience);
    }
    finally { deleting = null; }
  }

  function openNetworkPanel(id: string) {
    selectedNetworkId = id;
    history.pushState({ networkId: id }, '', `/dashboard/network/networks/${id}`);
  }
  function closeNetworkPanel() {
    selectedNetworkId = null;
    history.pushState({}, '', '/dashboard/network/networks');
  }

  const ar = createAutoRefresh(async () => { await Promise.allSettled([fetchNetworks(), fetchFloatingIps()]); }, {
    storageKey: 'dashboard-network-networks',
    defaultActive: true, defaultInterval: 30, intervalOptions: [10, 15, 30, 60], invokeOnMount: false,
  });

  const viewOwner = $derived(sessionScopeKey($auth));
  $effect(() => {
    viewOwner;
    const projectId = untrack(() => $auth.projectId);
    untrack(() => {
      selection.clear();
      activeDomain = null;
      hasInventory = false;
      displayPage = 1;
      search = '';
      view.reset();
      floatingSearch = '';
      floatingView.reset();
      if (!projectId) return;
      loading = true;
      void fetchNetworks();
      void fetchFloatingIps();
      void fetchDefaultNetwork();
    });
  });
</script>

<NetworkCreateModal bind:open={showModal} {creating} error={createError} onCreate={createNetwork} />

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb={t('networks.breadcrumb')} title={hasInventory ? `${t('networks.title')} (${networks.length})` : t('networks.title')}>
    {#snippet actions()}
      <Button onclick={() => showModal = true} variant="primary">{t('networks.createButton')}</Button>
    {/snippet}
  </PageHeader>
  <p class="text-[13px] text-ink-2" aria-live="polite">{$auth.domainName ? `${$auth.domainName} / ` : ''}{$auth.projectName || $auth.projectId || '—'} · {#if hasInventory}{t('list.results', { shown: filteredNetworks.length, total: networks.length })}{:else if loading}<LoadingState variant="inline" label={t('list.loading')} />{:else}{t('list.unavailable')}{/if}</p>
  <ResourceToolbar label={t('networks.toolbar')}>
    <RegexSearch id="user-network-search" bind:value={search} label={t('list.search')} placeholder={t('list.searchPlaceholder')} class="min-w-0 w-full md:flex-1 md:basis-48" />
    <Button variant="ghost" onclick={() => { search = ''; view.reset(); }}>{t('list.reset')}</Button>
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        {refreshing}
        onManualRefresh={forceRefresh}
      />
    {/snippet}
  </ResourceToolbar>
  <TableViewControls {view} class={networks.length && !loading ? 'lg:hidden' : ''} />

  {#if error}<Alert tone="danger">{error}</Alert>{/if}

  {#if loading}
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('networks.title') })} />
  {:else if networks.length === 0 && floatingIps.length === 0 && !error}
    <EmptyState headline={t('networks.empty')} description={t('networks.emptyDescription')} />
  {:else}
    <div class="flex flex-col gap-4">
      {#if filteredNetworks.length === 0 && networks.length > 0}<EmptyState headline={t('list.noMatches')} />{/if}
      <NetworksTableCard
        {view}
        networks={visibleNetworks} {defaultNetworkId} {deleting} {settingDefault}
        selectedIds={selection.ids}
        selectableIds={visibleSelectableIds}
        selectionDisabled={busy}
        onToggleSelect={(id) => toggleSelect('networks', id)}
        onToggleAll={() => toggleAll('networks')}
        onOpenPanel={openNetworkPanel} onSetDefault={setAsDefault} onDelete={deleteNetwork}
      />
      <div class="flex flex-wrap items-end justify-between gap-3">
        <Field label={t('list.pageSize')} for="user-networks-page-size"><SelectInput id="user-networks-page-size" bind:value={() => String(pageSize), (value) => pageSize = Number(value)}>{#each [20, 50, 100] as size}<option value={size}>{size}</option>{/each}</SelectInput></Field>
        <Pagination class="!mt-0" page={displayPage} totalPages={pageCount} hasPrev={displayPage > 1} hasNext={displayPage < pageCount} onPrev={() => displayPage--} onNext={() => displayPage++} />
      </div>
    </div>
  {/if}
  <section class="space-y-3">
    <RegexSearch id="network-floating-search" bind:value={floatingSearch} label={t('floatingIpCard.title')} />
    <TableViewControls view={floatingView} class="" />
    {#if !loading}
      <FloatingIpCard
        emptyLabel={floatingIps.length ? tl('table.noMatches') : undefined}
        floatingIps={floatingView.rows}
        hasExternalNetwork={networks.some((n) => n.is_external)}
        selectedIds={selection.ids}
        selectableIds={visibleFloatingIds}
        selectionDisabled={busy}
        onToggleSelect={(id) => toggleSelect('floating-ips', id)}
        onToggleAll={() => toggleAll('floating-ips')}
        onAllocateClick={() => (showAllocateModal = true)}
      />
    {/if}
  </section>
</PageShell>

<BulkSelectionOverlay
  count={selection.count}
  ariaLabel={t('networks.bulkAria')}
  actions={bulkActions()}
  {busy}
  onClear={() => { selection.clear(); activeDomain = null; }}
/>

<FloatingIpAllocateModal
  bind:open={showAllocateModal} {networks}
  token={tok()} projectId={pid()} onAllocated={fetchFloatingIps}
/>

{#if selectedNetworkId}
  <SlidePanel onClose={closeNetworkPanel} ariaLabel={t('networks.detail')} width="w-full md:w-[60vw] max-w-2xl">
    <NetworkDetailPanel
      networkId={selectedNetworkId} apiBase="/api/v1/networks"
      onClose={closeNetworkPanel} token={tok()} projectId={pid()}
    />
  </SlidePanel>
{/if}
