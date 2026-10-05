<script lang="ts">
  import { t } from '$lib/i18n/ns/network-pages';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { Router, Network } from '$lib/types/networks';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
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
  let selection = createResourceSelection();
  let busy = $state(false);
  let selectableIds = $derived(new Set(routers.filter((router) => $auth.isSystemAdmin || (router.project_id && router.project_id === $auth.projectId)).map((router) => router.id)));

  async function bulkDelete() {
    const ids = [...selection.ids];
    if (ids.length === 0) return;
    if (!await confirmDialog(t('routers.bulkConfirm', { count: ids.length }))) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    busy = true;
    try {
      const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/routers/${id}`, tokenSnapshot, projectSnapshot));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      if (projectSnapshot === ($auth.projectId ?? undefined)) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(t('routers.bulkDone', { count: succeeded.length }));
      const failedCount = results.length - succeeded.length;
      if (failedCount > 0) toast.error(t('routers.bulkFailed', { count: failedCount }));
      if (projectSnapshot === ($auth.projectId ?? undefined)) await fetchRouters({ refresh: true });
    } finally {
      busy = false;
    }
  }

  async function fetchRouters(opts?: { refresh?: boolean }) {
    try {
      routers = await api.get<Router[]>('/api/v1/routers', $auth.token ?? undefined, $auth.projectId ?? undefined, opts);
      if (selection.count > 0) selection.retain(routers.map((router) => router.id));
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? t('routers.loadFailed', { status: e.status }) : t('routers.serverError');
    } finally {
      loading = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try { await fetchRouters({ refresh: true }); } finally { refreshing = false; }
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
    try {
      const body: Record<string, unknown> = { name: form.name };
      if (form.external_network_id) body.external_network_id = form.external_network_id;
      await api.post('/api/v1/routers', body, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchRouters();
      return true;
    } catch (e) {
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

  $effect(() => {
    const projectId = $auth.projectId;
    if (!projectId) return;
    untrack(() => {
      selection.clear();
      loading = true;
      void fetchRouters();
    });
  });
</script>
<RouterCreateModal bind:open={showModal} {externalNetworks} onCreate={createRouter} />

<div class="bulk-selection-page p-4 md:p-8">
  <PageHeader breadcrumb={t('routers.breadcrumb')} title={t('routers.title')}>
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing}
        onManualRefresh={forceRefresh}
      />
      <Button onclick={openCreate} onintent={prefetchNetworks} variant="primary">{t('routers.createButton')}</Button>
    {/snippet}
  </PageHeader>

  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  {#if loading}
    <LoadingSkeleton variant="card" rows={4} />
  {:else if routers.length === 0}
    <RouterEmptyState />
  {:else}
    <RouterCardGrid
      {routers} {externalNetworkName}
      selectedIds={selection.ids}
      selectableIds={selectableIds}
      selectionDisabled={busy}
      onToggleSelect={(id) => selection.toggle(id)}
      onToggleAll={() => selection.toggleAll(selectableIds)}
      onOpen={openRouterPanel}
    />
  {/if}
</div>

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
      onClose={closeRouterPanel}
      onDeleted={() => { fetchRouters(); closeRouterPanel(); }}
    />
  </SlidePanel>
{/if}
