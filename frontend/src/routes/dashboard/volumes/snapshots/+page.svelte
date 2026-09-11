<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { Volume, VolumeSnapshot } from '$lib/types/volume';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import { Alert, Button, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
  import VolumeSnapshotCreateModal from '$lib/components/volume/snapshots/VolumeSnapshotCreateModal.svelte';
  import VolumeSnapshotsTable from '$lib/components/volume/snapshots/VolumeSnapshotsTable.svelte';
  import VolumeSnapshotsEmptyState from '$lib/components/volume/snapshots/VolumeSnapshotsEmptyState.svelte';
  import { toast } from '$lib/stores/toast';
  import { betaFeatures } from '$lib/stores/betaFeatures';
  import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations } from '$lib/utils/bulkActions';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';

  let snapshots = $state<VolumeSnapshot[]>([]);
  let volumes = $state<Volume[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let showModal = $state(false);
  let bulkBusy = $state(false);
  const selection = createResourceSelection();
  const volumeSnapshotsEnabled = $derived($betaFeatures.volumeSnapshots);
  const selectableIds = $derived(new Set(snapshots.map((snapshot) => snapshot.id)));

  function retainSelection() {
    selection.retain(selectableIds);
  }

  async function runBulkDelete() {
    const ids = [...selection.ids];
    if (!ids.length) return;
    if (!await confirmDialog(`선택한 스냅샷 ${ids.length}개를 삭제하시겠습니까?`)) return;
    const token = $auth.token ?? undefined;
    const projectId = $auth.projectId ?? undefined;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/volume-snapshots/${id}`, token, projectId));
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failed = results.length - successful.length;
      if (successful.length) toast.success(`${successful.length}개 삭제 요청을 완료했습니다.`);
      if (failed) toast.error(`${failed}개 삭제에 실패했습니다.`);
      if ($auth.projectId !== projectId) return;
      selection.remove(successful);
      await fetchSnapshots();
    } finally {
      bulkBusy = false;
    }
  }

  const bulkActions: BulkSelectionAction[] = [{ key: 'delete', label: '삭제', tone: 'danger', onAction: runBulkDelete }];


  function clearSnapshotsState() {
    snapshots = [];
    volumes = [];
    error = '';
  }


  async function fetchSnapshots() {
    if (!volumeSnapshotsEnabled) {
      clearSnapshotsState();
      loading = false;
      return;
    }
    try {
      snapshots = await api.get<VolumeSnapshot[]>('/api/v1/volume-snapshots', $auth.token ?? undefined, $auth.projectId ?? undefined);
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
    } finally {
      loading = false;
    }
  }

  async function fetchVolumes() {
    if (!volumeSnapshotsEnabled) {
      volumes = [];
      return;
    }
    try {
      volumes = await api.get<Volume[]>('/api/v1/volumes', $auth.token ?? undefined, $auth.projectId ?? undefined);
    } catch { /* ignore */ }
  }

  function prefetchVolumes() {
    if (!volumeSnapshotsEnabled) return;
    void api.prefetch('/api/v1/volumes', $auth.token ?? undefined, $auth.projectId ?? undefined);
  }

  function openCreate() {
    showModal = true;
    void fetchVolumes();
  }

  async function createSnapshot(form: { volume_id: string; name: string; description: string; force: boolean }): Promise<string | true> {
    if (!volumeSnapshotsEnabled) return '볼륨 스냅샷 베타 기능이 꺼져 있습니다.';
    try {
      await api.post('/api/v1/volume-snapshots', form, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchSnapshots();
      return true;
    } catch (e) {
      return e instanceof ApiError ? e.message : '생성 실패';
    }
  }

  async function deleteSnapshot(id: string, name: string) {
    if (!volumeSnapshotsEnabled) return;
    if (!await confirmDialog(`스냅샷 "${name || id.slice(0, 8)}"을 삭제하시겠습니까?`)) return;
    deleting = id;
    try {
      await api.delete(`/api/v1/volume-snapshots/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      selection.remove([id]);
      await fetchSnapshots();
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      deleting = null;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try { await fetchSnapshots(); } finally { refreshing = false; }
  }

  const ar = createAutoRefresh(() => fetchSnapshots(), {
    storageKey: 'dashboard-volume-snapshots',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 15,
    intervalOptions: [10, 15, 30, 60],
  });

  $effect(() => {
    const pid = $auth.projectId;
    if (!volumeSnapshotsEnabled) {
      clearSnapshotsState();
      selection.clear();
      loading = false;
      return;
    }
    if (!pid) return;
    untrack(() => { selection.clear(); fetchSnapshots(); });
  });
  $effect(() => {
    const ids = selectableIds;
    untrack(() => retainSelection());
  });
</script>

{#if !volumeSnapshotsEnabled}
  <PageShell>
    <BetaFeatureGate title="볼륨 스냅샷은 베타 기능입니다" />
  </PageShell>
{:else}
<VolumeSnapshotCreateModal bind:open={showModal} {volumes} onCreate={createSnapshot} />

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb="VOLUMES / SNAPSHOTS" title="볼륨 스냅샷">
    {#snippet actions()}
      <Button onclick={openCreate} onintent={prefetchVolumes} variant="primary">+ 스냅샷 생성</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label="볼륨 스냅샷 목록 도구">
    {#snippet actions()}<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing} onManualRefresh={forceRefresh} />{/snippet}
  </ResourceToolbar>

  {#if error}<Alert tone="danger">{error}</Alert>{/if}
  {#if loading}
    <LoadingSkeleton variant="table" rows={4} />
  {:else if snapshots.length === 0}
    <VolumeSnapshotsEmptyState onCreate={openCreate} onintent={prefetchVolumes} />
  {:else}
    <VolumeSnapshotsTable {snapshots} {deleting} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onDelete={deleteSnapshot} />
    <BulkSelectionOverlay count={selection.count} ariaLabel="선택한 볼륨 스냅샷 일괄 작업" actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
  {/if}
</PageShell>
{/if}
