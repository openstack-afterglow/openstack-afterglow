<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import type { ZunContainerDetail } from '$lib/types/zunContainer';
  import ContainerDetailHeader from '$lib/components/dashboard/containers/instances/id/ContainerDetailHeader.svelte';
  import ContainerDetailGrid from '$lib/components/dashboard/containers/instances/id/ContainerDetailGrid.svelte';
  import ContainerTerminalPanel from '$lib/components/dashboard/containers/instances/id/ContainerTerminalPanel.svelte';
  import ContainerLogsPanel from '$lib/components/dashboard/containers/instances/id/ContainerLogsPanel.svelte';
  import { toast } from '$lib/stores/toast';

  let container = $state<ZunContainerDetail | null>(null);
  let logs = $state('');
  let loading = $state(true);
  let logsLoading = $state(false);
  let error = $state('');
  let actioning = $state(false);
  let showConsole = $state(false);

  const containerId = $derived($page.params.id);

  async function fetchContainer() {
    try {
      container = await api.get<ZunContainerDetail>(`/api/v1/containers/${containerId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? `조회 실패: ${e.message}` : '서버 오류';
    } finally {
      loading = false;
    }
  }

  async function fetchLogs() {
    logsLoading = true;
    try {
      const result = await api.get<{ logs: string }>(`/api/v1/containers/${containerId}/logs`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      logs = result.logs;
    } catch {
      logs = '로그를 가져올 수 없습니다';
    } finally {
      logsLoading = false;
    }
  }

  async function handleAction(action: 'start' | 'stop') {
    actioning = true;
    try {
      await api.post(`/api/v1/containers/${containerId}/${action}`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchContainer();
    } catch (e) {
      toast.error(`${action === 'start' ? '시작' : '중지'} 실패: ` + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      actioning = false;
    }
  }

  async function handleDelete() {
    if (!container) return;
    if (!await confirmDialog(`컨테이너 "${container.name}"을 삭제하시겠습니까?`)) return;
    try {
      await api.delete(`/api/v1/containers/${containerId}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      goto('/dashboard/containers/instances');
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    }
  }

  const ar = createAutoRefresh(fetchLogs, {
    storageKey: 'dashboard-container-logs',
    defaultInterval: 15,
    intervalOptions: [10, 15, 30, 60]
  });

  onMount(fetchContainer);
</script>

<div class="p-4 md:p-8 max-w-3xl">
  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  {#if loading}
    <div class="flex items-center gap-3 mb-6">
      <button onclick={() => goto('/dashboard/containers/instances')} class="text-ink-2 hover:text-ink-0 transition-colors">← 컨테이너 목록</button>
    </div>
    <LoadingSkeleton variant="detail" />
  {:else if container}
    <ContainerDetailHeader
      {container}
      {actioning}
      terminalOpen={showConsole}
      onOpenTerminal={() => { showConsole = true; }}
      onStart={() => handleAction('start')}
      onStop={() => handleAction('stop')}
      onDelete={handleDelete}
      onBack={() => goto('/dashboard/containers/instances')}
    />

    <ContainerDetailGrid {container} />

    {#if showConsole}
      <ContainerTerminalPanel
        bind:open={showConsole}
        containerId={containerId ?? ''}
        token={$auth.token ?? undefined}
        projectId={$auth.projectId ?? undefined}
      />
    {/if}

    <ContainerLogsPanel
      {logs}
      {logsLoading}
      {ar}
      onManualRefresh={fetchLogs}
    />
  {/if}
</div>
