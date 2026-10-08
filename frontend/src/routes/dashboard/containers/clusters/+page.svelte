<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
  import RichText from '$lib/i18n/RichText.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { auth, canWrite } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import { apiMut } from '$lib/api/mutations';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations } from '$lib/utils/bulkActions';
  import type { Cluster, ClusterTemplate, CreateClusterForm } from '$lib/types/cluster';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import { toast } from '$lib/stores/toast';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import K3sClusterListTable from '$lib/components/k3s/K3sClusterListTable.svelte';
  import K3sClusterCreateModal from '$lib/components/k3s/K3sClusterCreateModal.svelte';

  let clusters = $state<Cluster[]>([]);
  let templates = $state<ClusterTemplate[]>([]);
  let loading = $state(true);
  let error = $state('');
  let serviceUnavailable = $state(false);
  let deleting = $state<string | null>(null);
  let showModal = $state(false);
  const selection = createResourceSelection();
  let bulkBusy = $state(false);
  const selectableIds = $derived(new Set(clusters.map((cluster) => cluster.id)));
  async function fetchClusters() {
    try {
      clusters = await api.get<Cluster[]>('/api/v1/clusters', $auth.token ?? undefined, $auth.projectId ?? undefined);
      selection.retain(clusters.map((cluster) => cluster.id));
      error = '';
      serviceUnavailable = false;
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        serviceUnavailable = true;
        error = '';
      } else {
        error = e instanceof ApiError ? t('clusters.list.loadFailed', { status: e.status, message: e.message }) : t('clusters.error.server');
      }
    } finally {
      loading = false;
    }
  }

  async function fetchTemplates() {
    try {
      templates = await api.get<ClusterTemplate[]>('/api/v1/clusters/templates', $auth.token ?? undefined, $auth.projectId ?? undefined);
    } catch {
      templates = [];
    }
  }

  function prefetchTemplates() {
    if (!$canWrite) return;
    void api.prefetch('/api/v1/clusters/templates', $auth.token ?? undefined, $auth.projectId ?? undefined);
  }

  function openCreate() {
    if (!$canWrite) return;
    showModal = true;
    void fetchTemplates();
  }

  async function createCluster(form: CreateClusterForm): Promise<string | true> {
    if (!$canWrite) return t('clusters.error.createFailed');
    try {
      const body: Record<string, unknown> = {
        name: form.name,
        cluster_template_id: form.cluster_template_id,
        node_count: form.node_count,
        master_count: form.master_count,
      };
      if (form.keypair.trim()) body.keypair = form.keypair;
      await api.post('/api/v1/clusters', body, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchClusters();
      return true;
    } catch (e) {
      return e instanceof ApiError ? e.message : t('clusters.error.createFailed');
    }
  }

  async function deleteCluster(id: string, name: string) {
    if (!$canWrite) return;
    if (!await confirmDialog(t('clusters.deleteDialog.body', { name }))) return;
    if (!$canWrite) return;
    deleting = id;
    try {
      await apiMut(t('clusters.actions.deleteK8sCluster'), () => api.delete(`/api/v1/clusters/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined));
      await fetchClusters();
    } catch {
      // error toast shown by apiMut
    } finally {
      deleting = null;
    }
  }
  async function runBulkDelete() {
    if (!$canWrite) return;
    const snapshot = [...selection.ids];
    if (snapshot.length === 0) return;
    if (!await confirmDialog(t('clusters.bulk.deleteDialog', { count: snapshot.length }))) return;
    if (!$canWrite) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(snapshot, (id) => api.delete(`/api/v1/clusters/${id}`, tokenSnapshot, projectSnapshot));
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failed = results.length - successful.length;
      if (successful.length > 0) toast.success(t('clusters.bulk.deleteRequested', { count: successful.length }));
      if (failed > 0) toast.error(t('clusters.bulk.deleteFailed', { count: failed }));
      if ($auth.projectId === projectSnapshot) {
        selection.remove(successful);
        await fetchClusters();
      }
    } finally {
      bulkBusy = false;
    }
  }

  const bulkActions: BulkSelectionAction[] = $derived([
    { key: 'delete', label: t('clusters.actions.delete'), tone: 'danger', disabled: !$canWrite, onAction: runBulkDelete },
  ]);

  const ar = createAutoRefresh(() => fetchClusters(), {
    storageKey: 'dashboard-k3s-clusters',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 30,
    intervalOptions: [10, 15, 30, 60],
  });
  $effect(() => {
    if (!$auth.projectId) return;
    selection.clear();
    loading = true;
    untrack(() => { fetchClusters(); });
  });
</script>

<K3sClusterCreateModal bind:open={showModal} {templates} onCreate={createCluster} />

<div class="bulk-selection-page p-4 md:p-8">
  <PageHeader breadcrumb={t('clusters.list.breadcrumb')} title={t('clusters.list.title')}>
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={loading}
        onManualRefresh={() => fetchClusters()}
      />
      <button disabled={!$canWrite} onclick={openCreate} onpointerenter={prefetchTemplates} onfocus={prefetchTemplates} class="bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">{t('clusters.actions.create')}</button>
    {/snippet}
  </PageHeader>

  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  {#if serviceUnavailable}
    <div class="text-center py-20 text-ink-2">
      <div class="text-5xl mb-4">⚠️</div>
      <p class="text-lg mb-2 text-warm-text">{t('clusters.serviceUnavailable.title')}</p>
      <p class="text-sm text-ink-2"><RichText segments={t.rich('clusters.serviceUnavailable.body')} /></p>
    </div>
  {:else if loading}
    <LoadingSkeleton variant="table" rows={4} />
  {:else if clusters.length === 0}
    <div class="text-center py-20 text-ink-2">
      <p class="text-lg mb-2">{t('clusters.empty.title')}</p>
      <p class="text-sm">{t('clusters.empty.body')}</p>
    </div>
  {:else}
    <K3sClusterListTable
      {clusters}
      {deleting}
      selectedIds={selection.ids}
      selectableIds={selectableIds}
      selectionDisabled={bulkBusy || !$canWrite}
      onToggleSelect={(id) => selection.toggle(id)}
      onToggleAll={() => selection.toggleAll(selectableIds)}
      onDelete={deleteCluster}
      onNavigate={(id) => goto(`/dashboard/containers/clusters/${id}`)}
    />
    <BulkSelectionOverlay count={selection.count} ariaLabel={t('clusters.bulk.ariaLabel')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
  {/if}
</div>
