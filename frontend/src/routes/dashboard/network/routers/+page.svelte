<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import { t } from '$lib/i18n/ns/network-pages';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { onDestroy, untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { sessionScopeKey } from '$lib/utils/authSession';
  import { api, ApiError } from '$lib/api/client';
  import type { Router, Network } from '$lib/types/networks';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import SlidePanel from '$lib/components/SlidePanel.svelte';
  import RouterDetailPanel from '$lib/components/RouterDetailPanel.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import RouterCreateModal from '$lib/components/network/routers/RouterCreateModal.svelte';
  import RouterCardGrid from '$lib/components/network/routers/RouterCardGrid.svelte';
  import RouterEmptyState from '$lib/components/network/routers/RouterEmptyState.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations } from '$lib/utils/bulkActions';
  import { toast } from '$lib/stores/toast';
  import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceState, type ExperienceContext } from '$lib/utils/experience';
  import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import { t as tr } from '$lib/i18n/ns/network-resources';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';

  let selectedRouterId = $state<string | null>(null);

  function openRouterPanel(id: string) {
    selectedRouterId = id;
    history.pushState({ routerId: id }, '', `/dashboard/network/routers/${id}`);
  }
  function closeRouterPanel() {
    selectedRouterId = null;
    history.pushState({}, '', '/dashboard/network/routers');
  }

  let routers = $state<Router[]>([]);
  let externalNetworks = $state<Network[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let showModal = $state(false);
  // Tutorial delete anchors attach only to the router created in this view.
  let lastCreated = $state<string | null>(null);
  let selection = createResourceSelection();
  let busy = $state(false);
  let stateVersion = 0;
  let live = true;
  onDestroy(() => { live = false; });
  let search = $state('');
  const columns = (): TableColumn<Router>[] => [
    { key: 'name', label: tr('network.labels.name'), value: row => row.name || row.id },
    { key: 'status', label: t('networksTable.status'), value: row => row.status },
    { key: 'gateway', label: tr('network.routers.externalGateway'), value: row => row.external_gateway_network_id },
    { key: 'subnets', label: tr('network.routers.connectedSubnets'), value: row => row.connected_subnet_ids.length },
  ];
  const view = createTableView({ rows: () => routers, columns, search: () => search, searchable: row => [row.name, row.id, row.status, row.external_gateway_network_id ?? ''] });
  const visibleSelectableIds = $derived(new Set(view.rows.filter(row => selectableIds.has(row.id)).map(row => row.id)));
  $effect(() => { const ids = visibleSelectableIds; untrack(() => selection.retain(ids)); });
  let selectableIds = $derived(new Set(routers.filter((router) => router.project_id && router.project_id === $auth.projectId).map((router) => router.id)));

  async function bulkDelete() {
    const ids = [...selection.ids];
    if (ids.length === 0) return;
    if (!await confirmDialog(t('routers.bulkConfirm', { count: ids.length }))) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    busy = true;
    const experience = beginExperienceAction('network', 'delete', 'resource.list');
    try {
      const results = await executeBulkMutations(ids, (id) => api.withExperience(experience).delete(`/api/v1/routers/${id}`, tokenSnapshot, projectSnapshot));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      if (projectSnapshot === ($auth.projectId ?? undefined)) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(t('routers.bulkDone', { count: succeeded.length }));
      const failedCount = results.length - succeeded.length;
      if (failedCount > 0) {
        toast.error(t('routers.bulkFailed', { count: failedCount }));
        experienceState(experience, 'error');
        if (experience) void experienceApplied(experience);
      }
      if (projectSnapshot === ($auth.projectId ?? undefined)) await fetchRouters({ refresh: true }, experience);
    } finally {
      busy = false;
    }
  }

  async function fetchRouters(opts?: { refresh?: boolean }, experience: ExperienceContext | undefined = beginExperienceLoad('network', 'resource.list')) {
    const projectId = $auth.projectId, userId = $auth.userId;
    let appliedVersion = 0;
    const current = () => live && appliedVersion === stateVersion && $auth.projectId === projectId && $auth.userId === userId;
    if (loading || refreshing) experienceState(experience, 'loading');
    try {
      routers = await api.withExperience(experience).get<Router[]>('/api/v1/routers', $auth.token ?? undefined, $auth.projectId ?? undefined, opts);
      if (selection.count > 0) selection.retain(routers.map((router) => router.id));
      error = '';
      appliedVersion = ++stateVersion;
      if (experience?.action !== 'create') experienceState(experience, routers.length ? 'ready' : 'empty');
      if (experience) void experienceApplied(experience, {}, current);
    } catch (e) {
      error = e instanceof ApiError ? t('routers.loadFailed', { status: e.status }) : t('routers.serverError');
      appliedVersion = ++stateVersion;
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience, {}, current);
    } finally {
      loading = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try { await fetchRouters({ refresh: true }, beginExperienceAction('network', 'refresh', 'resource.list')); } finally { refreshing = false; }
  }

  async function fetchNetworks() {
    try {
      const nets = await api.get<Network[]>('/api/v1/networks', $auth.token ?? undefined, $auth.projectId ?? undefined);
      externalNetworks = nets.filter(n => n.is_external);
    } catch { /* ignore */ }
  }

  function prefetchNetworks() {
    void api.prefetch('/api/v1/networks', $auth.token ?? undefined, $auth.projectId ?? undefined);
  }

  function openCreate() {
    showModal = true;
    void fetchNetworks();
  }

  async function createRouter(form: { name: string; external_network_id: string }): Promise<string | true> {
    const experience = beginExperienceAction('network', 'create', 'resource.list');
    try {
      const body: Record<string, unknown> = { name: form.name };
      if (form.external_network_id) body.external_network_id = form.external_network_id;
      const created = await api.withExperience(experience).post<Router>('/api/v1/routers', body, $auth.token ?? undefined, $auth.projectId ?? undefined);
      lastCreated = created.id;
      await fetchRouters(undefined, experience);
      return true;
    } catch (e) {
      experienceState(experience, 'error');
      return e instanceof ApiError ? e.message : t('routers.createFailed');
    }
  }

  function externalNetworkName(id: string | null): string {
    if (!id) return '';
    const net = externalNetworks.find(n => n.id === id);
    return net?.name || id.slice(0, 12) + '…';
  }

  const ar = createAutoRefresh(() => fetchRouters(), {
    storageKey: 'dashboard-network-routers',
    defaultActive: true,
    defaultInterval: 30,
    intervalOptions: [10, 15, 30, 60],
    invokeOnMount: false,
  });

  const viewOwner = $derived(sessionScopeKey($auth));
  $effect(() => {
    viewOwner;
    const projectId = untrack(() => $auth.projectId);
    if (!projectId) return;
    untrack(() => {
      selection.clear();
      lastCreated = null;
      search = ''; view.reset();
      loading = true;
      void fetchRouters();
    });
  });
</script>
<RouterCreateModal bind:open={showModal} {externalNetworks} onCreate={createRouter} />

<PageShell class="bulk-selection-page">
  <PageHeader breadcrumb={t('routers.breadcrumb')} title={t('routers.title')}>
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing}
        onManualRefresh={forceRefresh}
      />
      <TutorialStartButton tour="routers" compactOnMobile />
      <Button onclick={openCreate} onintent={prefetchNetworks} variant="primary" dataTour="routers-create-open">{t('routers.createButton')}</Button>
    {/snippet}
  </PageHeader>

  <RegexSearch id="router-search" bind:value={search} />
  <TableViewControls {view} class="" />
  {#if routers.length > 0 && view.rows.length === 0}<p class="text-sm text-ink-2">{tl('table.noMatches')}</p>{/if}
  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  <div data-tour="routers-list-section">
  {#if loading}
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('routers.title') })} />
  {:else if routers.length === 0}
    <RouterEmptyState />
  {:else}
    <RouterCardGrid
      routers={view.rows} {externalNetworkName}
      highlightId={lastCreated}
      selectedIds={selection.ids}
      selectableIds={visibleSelectableIds}
      selectionDisabled={busy}
      onToggleSelect={(id) => selection.toggle(id)}
      onToggleAll={() => selection.toggleAll(visibleSelectableIds)}
      onOpen={openRouterPanel}
    />
  {/if}
  </div>
</PageShell>

<BulkSelectionOverlay
  count={selection.count}
  ariaLabel={t('routers.bulkAria')}
  actions={[{ key: 'delete', label: t('routers.delete'), tone: 'danger', onAction: bulkDelete }]}
  {busy}
  onClear={() => selection.clear()}
/>

{#if selectedRouterId}
  <SlidePanel onClose={closeRouterPanel} ariaLabel={t('routers.detail')} width="w-full md:w-[60vw] max-w-2xl">
    <RouterDetailPanel
      routerId={selectedRouterId}
      highlightDelete={lastCreated !== null && selectedRouterId === lastCreated}
      onClose={closeRouterPanel}
      onDeleted={() => { fetchRouters(); closeRouterPanel(); }}
    />
  </SlidePanel>
{/if}
