<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { toast } from '$lib/stores/toast';
  import { auth } from '$lib/stores/auth';
  import { untrack } from 'svelte';
  import { api, ApiError } from '$lib/api/client';
  import { createSwr } from '$lib/utils/swr.svelte';
  import { apiMut } from '$lib/api/mutations';
  import type { FileStorage } from '$lib/types/fileStorage';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import SlidePanel from '$lib/components/SlidePanel.svelte';
  import FileStorageDetailPanel from '$lib/components/FileStorageDetailPanel.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
  import FileStorageWizard from '$lib/components/file-storage/wizard/FileStorageWizard.svelte';
  import FileStorageCard from '$lib/components/file-storage/FileStorageCard.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations } from '$lib/utils/bulkActions';
  import { Alert, BulkSelectionOverlay, Button, EmptyState, PageHeader, PageShell, ResourceToolbar, SelectionToolbar } from '$lib/components/ui';

  import type { QuotaItem, ManilaFileQuota as Quota } from '$lib/types/quotas';

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  function prefetchCreateMetadata() {
    void api.prefetch('/api/v1/file-storage/types', token, projectId);
    void api.prefetch('/api/v1/share-networks', token, projectId);
  }

  let fileStorages = $state<FileStorage[]>([]);
  let quota = $state<Quota | null>(null);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let copiedExport = $state<string | null>(null);

  let selectedId = $state<string | null>(null);
  let showWizard = $state(false);
  const selection = createResourceSelection();
  const selectableIds = $derived(new Set(fileStorages.map((storage) => storage.id)));
  let bulkBusy = $state(false);

  function openDetailPanel(id: string) {
    selectedId = id;
    history.pushState({ fileStorageId: id }, '', `/dashboard/file-storage/${id}`);
  }

  function closeDetailPanel() {
    selectedId = null;
    history.pushState({}, '', '/dashboard/file-storage');
  }

  const { swrGet, swrSet } = createSwr(() => $auth.projectId);

  async function fetchFileStorages(opts?: { refresh?: boolean }) {
    const path = '/api/v1/file-storage';
    const cached = swrGet<FileStorage[]>(path);
    if (cached && fileStorages.length === 0) fileStorages = cached;
    try {
      fileStorages = await api.get<FileStorage[]>(path, token, projectId, opts);
      selection.retain(fileStorages.map((storage) => storage.id));
      swrSet(path, fileStorages);
      error = '';
    } catch (e) {
      if (!cached) error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
    } finally {
      loading = false;
    }
  }

  async function fetchQuota() {
    try { quota = await api.get<Quota>('/api/v1/file-storage/quota', token, projectId); }
    catch { quota = null; }
  }

  async function copyExportPath(path: string, id: string) {
    await navigator.clipboard.writeText(path);
    copiedExport = id;
    setTimeout(() => (copiedExport = null), 2000);
  }

  async function deleteFileStorage(id: string, name: string) {
    if (!await confirmDialog(`파일 스토리지 "${name || id.slice(0, 8)}"을 삭제하시겠습니까?`)) return;
    deleting = id;
    try {
      await apiMut('파일 스토리지 삭제', () => api.delete(`/api/v1/file-storage/${id}`, token, projectId));
      await refresh.invalidate();
    } catch {
      // error toast shown by apiMut
    } finally { deleting = null; }
  }

  async function bulkDelete() {
    const ids = [...selection.ids];
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    if (ids.length === 0 || !await confirmDialog(`선택한 파일 스토리지 ${ids.length}개를 삭제하시겠습니까?`)) return;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/file-storage/${id}`, tokenSnapshot, projectSnapshot));
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failed = results.length - successful.length;
      if (successful.length) toast.success(`${successful.length}개 삭제 요청을 완료했습니다.`);
      if (failed) toast.error(`${failed}개 삭제에 실패했습니다.`);
      if ($auth.projectId === projectSnapshot) {
        selection.remove(successful);
        await refresh.invalidate();
      }
    } finally { bulkBusy = false; }
  }

  async function forceRefresh() {
    refreshing = true;
    try { await refresh.run(true); }
    finally { refreshing = false; }
  }

  const refresh = createCoalescedRefresh(async (force) => {
    if (selectedId && !force) return;
    await Promise.allSettled([
      fetchFileStorages(force ? { refresh: true } : undefined),
      fetchQuota(),
    ]);
  });

  const ar = createAutoRefresh(() => refresh.run(false), {
    storageKey: 'dashboard-file-storage-list',
    defaultActive: true,
    defaultInterval: 15,
    intervalOptions: [10, 15, 30, 60],
    invokeOnMount: false,
  });

  $effect(() => {
    const pid = $auth.projectId;
    untrack(() => {
      selection.clear();
      if (!pid) return;
      void refresh.run();
    });
  });
</script>

<FileStorageWizard
  bind:open={showWizard}
  onCreated={() => refresh.invalidate()}
/>

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb="FILE STORAGE" title="파일 스토리지">
    {#snippet actions()}
      <Button onclick={() => (showWizard = true)} onintent={prefetchCreateMetadata} variant="primary">+ 파일 스토리지 생성</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label="파일 스토리지 목록 도구">
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing || loading}
        onManualRefresh={forceRefresh}
      />
    {/snippet}
  </ResourceToolbar>

  {#if error}<Alert tone="danger">{error}</Alert>{/if}

  {#if loading}
    <div class="grid grid-cols-2 gap-3.5">
      {#each [1, 2, 3, 4] as _}
        <div class="animate-pulse bg-surface-base border border-line rounded-lg h-40"></div>
      {/each}
    </div>
  {:else if fileStorages.length === 0}
    <EmptyState headline="파일 스토리지가 없습니다" description="공유 파일 시스템을 생성해 여러 인스턴스에서 사용하세요.">
      {#snippet cta()}<Button onclick={() => (showWizard = true)} variant="primary">파일 스토리지 생성</Button>{/snippet}
    </EmptyState>
  {:else}
    <SelectionToolbar label="파일 스토리지" ariaLabel="파일 스토리지 전체 선택" checked={selectableIds.size > 0 && [...selectableIds].every((id) => selection.has(id))} indeterminate={selection.count > 0 && ![...selectableIds].every((id) => selection.has(id))} selectedCount={selection.count} disabled={bulkBusy} onToggle={() => selection.toggleAll(selectableIds)} />
    <div class="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3.5">
      {#each fileStorages as fs (fs.id)}
        <FileStorageCard
          {fs}
          quotaLimit={quota?.gigabytes?.limit ?? 0}
          {copiedExport}
          {deleting}
          selected={selection.has(fs.id)}
          selectionDisabled={bulkBusy}
          onToggleSelect={() => selection.toggle(fs.id)}
          onOpenDetail={openDetailPanel}
          onCopyExport={copyExportPath}
          onDelete={deleteFileStorage}
        />
      {/each}
    </div>
  {/if}
  <BulkSelectionOverlay count={selection.count} ariaLabel="선택한 파일 스토리지 일괄 작업" actions={[{ key: 'delete', label: '삭제', tone: 'danger', onAction: bulkDelete }]} busy={bulkBusy} onClear={() => selection.clear()} />
</PageShell>

{#if selectedId}
  <SlidePanel onClose={closeDetailPanel} ariaLabel="파일 스토리지 상세" width="w-full md:w-[60vw] max-w-2xl">
    <FileStorageDetailPanel
      fileStorageId={selectedId}
      onClose={closeDetailPanel}
      onDeleted={() => { closeDetailPanel(); void refresh.invalidate(); }}
    />
  </SlidePanel>
{/if}
