<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores/auth';
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
        error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
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
    void api.prefetch('/api/v1/clusters/templates', $auth.token ?? undefined, $auth.projectId ?? undefined);
  }

  function openCreate() {
    showModal = true;
    void fetchTemplates();
  }

  async function createCluster(form: CreateClusterForm): Promise<string | true> {
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
      return e instanceof ApiError ? e.message : '생성 실패';
    }
  }

  async function deleteCluster(id: string, name: string) {
    if (!await confirmDialog(`클러스터 "${name}"을 삭제하시겠습니까?`)) return;
    deleting = id;
    try {
      await apiMut('K8s 클러스터 삭제', () => api.delete(`/api/v1/clusters/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined));
      await fetchClusters();
    } catch {
      // error toast shown by apiMut
    } finally {
      deleting = null;
    }
  }
  async function runBulkDelete() {
    const snapshot = [...selection.ids];
    if (snapshot.length === 0) return;
    if (!await confirmDialog(`선택한 클러스터 ${snapshot.length}개를 삭제하시겠습니까?`)) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(snapshot, (id) => api.delete(`/api/v1/clusters/${id}`, tokenSnapshot, projectSnapshot));
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failed = results.length - successful.length;
      if (successful.length > 0) toast.success(`${successful.length}개 삭제 요청을 완료했습니다.`);
      if (failed > 0) toast.error(`${failed}개 삭제에 실패했습니다.`);
      if ($auth.projectId === projectSnapshot) {
        selection.remove(successful);
        await fetchClusters();
      }
    } finally {
      bulkBusy = false;
    }
  }

  const bulkActions: BulkSelectionAction[] = [
    { key: 'delete', label: '삭제', tone: 'danger', onAction: runBulkDelete },
  ];

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
  <PageHeader breadcrumb="CONTAINERS / K8S CLUSTERS" title="K8s 클러스터">
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={loading}
        onManualRefresh={() => fetchClusters()}
      />
      <button onclick={openCreate} onpointerenter={prefetchTemplates} onfocus={prefetchTemplates} class="bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ 클러스터 생성</button>
    {/snippet}
  </PageHeader>

  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  {#if serviceUnavailable}
    <div class="text-center py-20 text-ink-3">
      <div class="text-5xl mb-4">⚠️</div>
      <p class="text-lg mb-2 text-action-warm">Magnum 서비스에 연결할 수 없습니다</p>
      <p class="text-sm text-ink-3">K8s 클러스터 관리 서비스가 현재 응답하지 않습니다.<br/>잠시 후 다시 시도해주세요.</p>
    </div>
  {:else if loading}
    <LoadingSkeleton variant="table" rows={4} />
  {:else if clusters.length === 0}
    <div class="text-center py-20 text-ink-3">
      <p class="text-lg mb-2">K8s 클러스터가 없습니다</p>
      <p class="text-sm">Magnum을 통해 새 클러스터를 생성하세요</p>
    </div>
  {:else}
    <K3sClusterListTable
      {clusters}
      {deleting}
      selectedIds={selection.ids}
      selectableIds={selectableIds}
      selectionDisabled={bulkBusy}
      onToggleSelect={(id) => selection.toggle(id)}
      onToggleAll={() => selection.toggleAll(selectableIds)}
      onDelete={deleteCluster}
      onNavigate={(id) => goto(`/dashboard/containers/clusters/${id}`)}
    />
    <BulkSelectionOverlay count={selection.count} ariaLabel="선택한 클러스터 일괄 작업" actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
  {/if}
</div>
