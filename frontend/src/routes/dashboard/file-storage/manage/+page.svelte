<script lang="ts">
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { FileStorage } from '$lib/types/fileStorage';
  import type { LibraryConfig } from '$lib/types/library';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import PrebuiltLibraryGrid from '$lib/components/file-storage/manage/PrebuiltLibraryGrid.svelte';
  import FileStorageManageGrid from '$lib/components/file-storage/manage/FileStorageManageGrid.svelte';

  let fileStorages = $state<FileStorage[]>([]);
  let libraries = $state<LibraryConfig[]>([]);
  let building = $state<string | null>(null);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let message = $state('');
  let autoInstall = $state(true);

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  async function loadData(opts?: { refresh?: boolean }) {
    if (fileStorages.length === 0) loading = true;
    else refreshing = true;
    await Promise.allSettled([
      api.get<FileStorage[]>('/api/v1/admin/file-storage', token, projectId, opts)
        .then(v => { fileStorages = v; loading = false; })
        .catch(e => {
          error = e instanceof ApiError ? `로드 실패: ${e.message}` : '서버 오류';
          fileStorages = [];
          loading = false;
        }),
      api.get<LibraryConfig[]>('/api/v1/libraries', token, projectId, opts)
        .then(v => { libraries = v; })
        .catch(() => {}),
    ]);
    loading = false;
    refreshing = false;
  }

  async function buildFileStorage(libId: string) {
    building = libId;
    message = '';
    error = '';
    try {
      const params = new URLSearchParams({ library_id: libId });
      if (autoInstall) params.set('auto_install', 'true');
      const res = await api.post<{ file_storage_id: string; server_id?: string }>(
        `/api/v1/admin/file-storage/build?${params}`, {}, token, projectId
      );
      if (autoInstall && res.server_id) {
        message = `자동 빌드 시작됨 (Share: ${res.file_storage_id}, VM: ${res.server_id})`;
      } else {
        message = `파일 스토리지 생성 시작됨 (ID: ${res.file_storage_id})`;
      }
      await refresh.invalidate();
    } catch (e) {
      error = e instanceof ApiError ? `빌드 실패: ${e.message}` : '서버 오류';
    } finally {
      building = null;
    }
  }

  const refresh = createCoalescedRefresh((force) => loadData(force ? { refresh: true } : undefined));

  $effect(() => {
    if (!$auth.projectId) return;
    fileStorages = [];
    untrack(() => void refresh.run(false));
  });

  const ar = createAutoRefresh(() => refresh.run(false), {
    storageKey: 'dashboard-file-storage',
    defaultActive: true,
    defaultInterval: 30,
    intervalOptions: [15, 30, 60],
    invokeOnMount: false
  });
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
  <PageHeader breadcrumb="FILE STORAGE / MANAGE" title="사전 빌드 파일 스토리지" subtitle="구 prebuilt 라이브러리 share를 확인하거나 수동으로 빌드합니다.">
    {#snippet actions()}
      <label class="flex items-center gap-2 text-xs text-ink-2 cursor-pointer">
        <input type="checkbox" bind:checked={autoInstall} class="rounded border-line-2 bg-surface-sunken text-action-warm focus:ring-line-2 focus:ring-offset-0" />
        자동 패키지 설치
      </label>
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={loading || refreshing}
        onManualRefresh={() => refresh.run(true)}
      />
    {/snippet}
  </PageHeader>

  {#if error}
    <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>
  {/if}
  {#if message}
    <div class="bg-green-900/40 border border-green-700 text-green-300 rounded-lg px-4 py-3 text-sm mb-4">{message}</div>
  {/if}

  {#if loading}
    <LoadingSkeleton variant="list" rows={4} />
  {:else}
      <div class="mb-8">
        <h2 class="text-base font-semibold text-ink-0 mb-3">사전 빌드 상태</h2>
        <PrebuiltLibraryGrid {libraries} {fileStorages} {building} onBuild={buildFileStorage} />
      </div>

      <div class="flex items-center justify-between mb-3">
        <h2 class="text-base font-semibold text-ink-0">전체 파일 스토리지 목록</h2>
      </div>
      {#if fileStorages.length === 0}
        <div class="text-ink-3 text-sm py-8 text-center">파일 스토리지가 없습니다</div>
      {:else}
        <FileStorageManageGrid {fileStorages} />
      {/if}
  {/if}
</div>
