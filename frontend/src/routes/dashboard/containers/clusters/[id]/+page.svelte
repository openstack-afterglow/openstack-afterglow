<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import type { Cluster, StackResource, StackEvent } from '$lib/types/cluster';
  import ClusterHeader from '$lib/components/dashboard/containers/clusters/id/ClusterHeader.svelte';
  import ClusterProgressBar from '$lib/components/dashboard/containers/clusters/id/ClusterProgressBar.svelte';
  import ClusterDetailGrid from '$lib/components/dashboard/containers/clusters/id/ClusterDetailGrid.svelte';
  import ClusterResourcesTab from '$lib/components/dashboard/containers/clusters/id/ClusterResourcesTab.svelte';
  import ClusterEventsTab from '$lib/components/dashboard/containers/clusters/id/ClusterEventsTab.svelte';
  import { toast } from '$lib/stores/toast';
  import { PageShell, Tabs } from '$lib/components/ui';

  type Tab = 'detail' | 'resources' | 'events';
  let activeTab = $state<Tab>('detail');

  let cluster = $state<Cluster | null>(null);
  let resources = $state<StackResource[]>([]);
  let events = $state<StackEvent[]>([]);
  const clusterTabs = $derived([
    { value: 'detail', label: '상세', panelId: 'cluster-panel-detail' },
    { value: 'resources', label: cluster?.stack_id ? '스택 리소스' : '스택 리소스 (없음)', panelId: 'cluster-panel-resources', disabled: !cluster?.stack_id },
    { value: 'events', label: cluster?.stack_id ? '스택 이벤트' : '스택 이벤트 (없음)', panelId: 'cluster-panel-events', disabled: !cluster?.stack_id },
  ]);
  let loading = $state(true);
  let resourcesLoading = $state(false);
  let eventsLoading = $state(false);
  let resourcesLoaded = $state(false);
  let eventsLoaded = $state(false);
  let error = $state('');
  let clusterGeneration = 0;
  let resourcesGeneration = 0;
  let eventsGeneration = 0;

  const clusterId = $derived($page.params.id);
  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  const isInProgress = $derived(
    cluster?.status?.includes('IN_PROGRESS') ?? false
  );

  async function fetchCluster() {
    const requestId = clusterId;
    const requestProjectId = projectId;
    const generation = ++clusterGeneration;
    try {
      const value = await api.get<Cluster>(`/api/v1/clusters/${requestId}`, token, requestProjectId);
      if (generation !== clusterGeneration || clusterId !== requestId || projectId !== requestProjectId) return;
      cluster = value;
      error = '';
    } catch (e) {
      if (generation === clusterGeneration && clusterId === requestId && projectId === requestProjectId) {
        error = e instanceof ApiError ? `조회 실패: ${e.message}` : '서버 오류';
      }
    } finally {
      if (generation === clusterGeneration && clusterId === requestId && projectId === requestProjectId) loading = false;
    }
  }

  async function fetchResources() {
    const requestId = clusterId;
    const requestProjectId = projectId;
    const generation = ++resourcesGeneration;
    resourcesLoading = true;
    try {
      const value = await api.get<StackResource[]>(`/api/v1/clusters/${requestId}/stack/resources`, token, requestProjectId);
      if (generation === resourcesGeneration && clusterId === requestId && projectId === requestProjectId) {
        resources = value;
        resourcesLoaded = true;
      }
    } catch {
      if (generation === resourcesGeneration && clusterId === requestId && projectId === requestProjectId) {
        resources = [];
        resourcesLoaded = false;
      }
    } finally {
      if (generation === resourcesGeneration && clusterId === requestId && projectId === requestProjectId) resourcesLoading = false;
    }
  }

  async function fetchEvents() {
    const requestId = clusterId;
    const requestProjectId = projectId;
    const generation = ++eventsGeneration;
    eventsLoading = true;
    try {
      const value = await api.get<StackEvent[]>(`/api/v1/clusters/${requestId}/stack/events`, token, requestProjectId);
      if (generation === eventsGeneration && clusterId === requestId && projectId === requestProjectId) {
        events = value;
        eventsLoaded = true;
      }
    } catch {
      if (generation === eventsGeneration && clusterId === requestId && projectId === requestProjectId) {
        events = [];
        eventsLoaded = false;
      }
    } finally {
      if (generation === eventsGeneration && clusterId === requestId && projectId === requestProjectId) eventsLoading = false;
    }
  }

  async function ensureTab(tab: Tab) {
    if (tab === 'resources' && !resourcesLoaded && !resourcesLoading) await fetchResources();
    if (tab === 'events' && !eventsLoaded && !eventsLoading) await fetchEvents();
  }

  async function switchTab(tab: Tab) {
    activeTab = tab;
    await ensureTab(tab);
  }

  async function refreshVisible() {
    const tasks: Promise<void>[] = [fetchCluster()];
    if (activeTab === 'resources') tasks.push(fetchResources());
    if (activeTab === 'events') tasks.push(fetchEvents());
    await Promise.allSettled(tasks);
  }

  const ar = createAutoRefresh(refreshVisible, {
    storageKey: 'dashboard-cluster-detail',
    defaultActive: true,
    defaultInterval: 10,
    intervalOptions: [10, 15, 30, 60],
    invokeOnMount: false,
  });

  async function handleDelete() {
    if (!cluster) return;
    if (!await confirmDialog(`클러스터 "${cluster.name}"을 삭제하시겠습니까?`)) return;
    try {
      await api.delete(`/api/v1/clusters/${clusterId}`, token, projectId);
      goto('/dashboard/containers/clusters');
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    }
  }

  $effect(() => {
    const requestId = clusterId;
    const requestProject = projectId;
    if (!requestId || !requestProject) return;
    loading = true;
    resources = [];
    events = [];
    activeTab = 'detail';
    untrack(() => void fetchCluster());
    resourcesLoaded = false;
    eventsLoaded = false;
  });
</script>

<PageShell class="max-w-5xl">
  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  {#if loading}
    <div class="flex items-center gap-3 mb-6">
      <button onclick={() => goto('/dashboard/containers/clusters')} class="text-ink-2 hover:text-ink-0 transition-colors text-sm">← 클러스터 목록</button>
    </div>
    <LoadingSkeleton variant="detail" />
  {:else if cluster}
    <ClusterHeader
      {cluster}
      refreshing={loading || resourcesLoading || eventsLoading}
      {ar}
      onManualRefresh={refreshVisible}
      onDelete={handleDelete}
    />

    <ClusterProgressBar {resources} {isInProgress} />

    <Tabs
      id="cluster-detail-tabs"
      value={activeTab}
      items={clusterTabs}
      ariaLabel="클러스터 상세 정보"
      onchange={(value) => { void switchTab(value as Tab); }}
      class="mb-6"
    />

    <div
      id={`cluster-panel-${activeTab}`}
      role="tabpanel"
      aria-labelledby={`cluster-detail-tabs-${activeTab}`}
      tabindex="0"
    >
    {#if activeTab === 'detail'}
      <ClusterDetailGrid {cluster} />
    {:else if activeTab === 'resources'}
      <ClusterResourcesTab {resources} loading={resourcesLoading} onRefresh={fetchResources} />
    {:else if activeTab === 'events'}
      <ClusterEventsTab {events} loading={eventsLoading} onRefresh={fetchEvents} />
    {/if}
    </div>
  {/if}
</PageShell>
