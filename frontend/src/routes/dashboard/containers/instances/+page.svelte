<script lang="ts">
  import { goto } from '$app/navigation';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations, partitionBulkIds } from '$lib/utils/bulkActions';
  import { buildContainerCreatePayload } from '$lib/utils/containerCreatePayload';
  import type { ZunContainer, ContainerListResponse, EnvVar, PortMapping } from '$lib/types/zunContainer';
  import ZunServiceBanner from '$lib/components/dashboard/containers/instances/ZunServiceBanner.svelte';
  import ZunServiceUnavailable from '$lib/components/dashboard/containers/instances/ZunServiceUnavailable.svelte';
  import ContainersTable from '$lib/components/dashboard/containers/instances/ContainersTable.svelte';
  import ContainerCreateModal from '$lib/components/dashboard/containers/instances/ContainerCreateModal.svelte';
  import { toast } from '$lib/stores/toast';
  let containers = $state<ZunContainer[]>([]);
  let serviceAvailable = $state(true);
  let serviceMessage = $state('');
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let actionTarget = $state<string | null>(null);
  let showModal = $state(false);
  let creating = $state(false);
  let createError = $state('');
  const selection = createResourceSelection();
  let bulkBusy = $state(false);
  const selectableIds = $derived(new Set(containers.map((container) => container.uuid)));
  const startIds = $derived(new Set(containers.filter((container) => container.status === 'Stopped' || container.status === 'Created').map((container) => container.uuid)));
  const stopIds = $derived(new Set(containers.filter((container) => container.status === 'Running').map((container) => container.uuid)));

  async function fetchContainers(opts?: { refresh?: boolean }) {
    try {
      const resp = await api.get<ContainerListResponse>('/api/v1/containers', $auth.token ?? undefined, $auth.projectId ?? undefined, opts);
      containers = resp.items;
      selection.retain(resp.items.map((container) => container.uuid));
      serviceAvailable = resp.service_available;
      serviceMessage = resp.message;
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
    } finally {
      loading = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try {
      await fetchContainers({ refresh: true });
    } finally {
      refreshing = false;
    }
  }

  async function createContainer(payload: {
    name: string; image: string; command: string;
    cpu: number; memory: string;
    environment: EnvVar[]; ports: PortMapping[];
  }): Promise<boolean> {
    if (!payload.name.trim() || !payload.image.trim()) return false;
    creating = true;
    createError = '';
    try {
      await api.post('/api/v1/containers', buildContainerCreatePayload(payload), $auth.token ?? undefined, $auth.projectId ?? undefined);
      showModal = false;
      await fetchContainers();
      return true;
    } catch (e) {
      createError = e instanceof ApiError ? e.message : '생성 실패';
      return false;
    } finally {
      creating = false;
    }
  }

  async function startContainer(uuid: string) {
    actionTarget = uuid;
    try {
      await api.post(`/api/v1/containers/${uuid}/start`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchContainers();
    } catch (e) {
      toast.error('시작 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      actionTarget = null;
    }
  }

  async function stopContainer(uuid: string) {
    actionTarget = uuid;
    try {
      await api.post(`/api/v1/containers/${uuid}/stop`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchContainers();
    } catch (e) {
      toast.error('중지 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      actionTarget = null;
    }
  }

  async function deleteContainer(uuid: string, name: string) {
    if (!await confirmDialog(`컨테이너 "${name}"을 삭제하시겠습니까?`)) return;
    actionTarget = uuid;
    try {
      await api.delete(`/api/v1/containers/${uuid}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchContainers();
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      actionTarget = null;
    }
  }
  async function runBulk(action: 'start' | 'stop' | 'delete') {
    const snapshot = [...selection.ids];
    if (snapshot.length === 0) return;
    const eligible = action === 'start' ? startIds : action === 'stop' ? stopIds : selectableIds;
    const { eligible: applicable, skipped } = partitionBulkIds(snapshot, eligible);
    const label = action === 'start' ? '시작' : action === 'stop' ? '중지' : '삭제';
    if (applicable.length === 0) {
      if (skipped.length > 0) toast.warning(`${skipped.length}개는 현재 상태에서 ${label}할 수 없어 제외했습니다.`);
      return;
    }
    const note = skipped.length > 0 ? `\n${skipped.length}개는 현재 상태에서 제외됩니다.` : '';
    if (action === 'delete' || skipped.length > 0) {
      const prompt = action === 'delete'
        ? `선택한 컨테이너 ${applicable.length}개를 삭제하시겠습니까?${note}`
        : `선택한 컨테이너 ${applicable.length}개를 ${label}하시겠습니까?${note}`;
      if (!await confirmDialog(prompt)) return;
    }
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(applicable, (id) => {
        if (action === 'start') return api.post(`/api/v1/containers/${id}/start`, {}, tokenSnapshot, projectSnapshot);
        if (action === 'stop') return api.post(`/api/v1/containers/${id}/stop`, {}, tokenSnapshot, projectSnapshot);
        return api.delete(`/api/v1/containers/${id}`, tokenSnapshot, projectSnapshot);
      });
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failedCount = results.length - successful.length;
      if (skipped.length > 0) toast.warning(`${skipped.length}개는 현재 상태에서 ${label}할 수 없어 제외했습니다.`);
      if (successful.length > 0) toast.success(`${successful.length}개 ${label} 요청을 완료했습니다.`);
      if (failedCount > 0) toast.error(`${failedCount}개 ${label}에 실패했습니다.`);
      if ($auth.projectId === projectSnapshot) {
        selection.remove(successful);
        await fetchContainers();
      }
    } finally {
      bulkBusy = false;
    }
  }

  const bulkActions = $derived<BulkSelectionAction[]>([
    { key: 'start', label: '시작', tone: 'success', disabled: ![...selection.ids].some((id) => startIds.has(id)), onAction: () => runBulk('start') },
    { key: 'stop', label: '중지', tone: 'warning', disabled: ![...selection.ids].some((id) => stopIds.has(id)), onAction: () => runBulk('stop') },
    { key: 'delete', label: '삭제', tone: 'danger', onAction: () => runBulk('delete') },
  ]);

  const ar = createAutoRefresh(() => fetchContainers(), {
    storageKey: 'dashboard-zun-containers',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 10,
    intervalOptions: [10, 15, 30, 60],
  });

  $effect(() => {
    const projectId = $auth.projectId;
    untrack(() => {
      selection.clear();
      if (!projectId) return;
      loading = true;
      void fetchContainers();
    });
  });

  $effect(() => {
    if (!showModal) createError = '';
  });
</script>

<ContainerCreateModal
  bind:open={showModal}
  {creating}
  error={createError}
  onCreate={createContainer}
/>

<div class="bulk-selection-page p-4 md:p-8">
  <PageHeader breadcrumb="CONTAINERS / INSTANCES" title="컨테이너">
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing || loading}
        onManualRefresh={forceRefresh}
      />
      <button onclick={() => showModal = true} class="bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ 컨테이너 생성</button>
    {/snippet}
  </PageHeader>

  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  <ZunServiceBanner available={serviceAvailable} message={serviceMessage} />

  {#if loading}
    <LoadingSkeleton variant="table" rows={4} />
  {:else if !serviceAvailable}
    <ZunServiceUnavailable />
  {:else}
    <ContainersTable
      {containers}
      {actionTarget}
      selectedIds={selection.ids}
      selectableIds={selectableIds}
      selectionDisabled={bulkBusy}
      onToggleSelect={(id) => selection.toggle(id)}
      onToggleAll={() => selection.toggleAll(selectableIds)}
      onStart={startContainer}
      onStop={stopContainer}
      onDelete={deleteContainer}
      onOpen={(id) => goto(`/dashboard/containers/instances/${id}`)}
    />
    <BulkSelectionOverlay
      count={selection.count}
      ariaLabel="선택한 컨테이너 일괄 작업"
      actions={bulkActions}
      busy={bulkBusy}
      onClear={() => selection.clear()}
    />
  {/if}
</div>
