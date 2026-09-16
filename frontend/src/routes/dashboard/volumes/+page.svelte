<script lang="ts">
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api } from '$lib/api/client';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { toast } from '$lib/stores/toast';
  import { executeBulkMutations } from '$lib/utils/bulkActions';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import { createVolumesController } from '$lib/stores/volumesController.svelte';
  import VolumeDetailPanel from '$lib/components/VolumeDetailPanel.svelte';
  import VolumeCreateModal from '$lib/components/volume/VolumeCreateModal.svelte';
  import VolumeSummaryCards from '$lib/components/volume/VolumeSummaryCards.svelte';
  import VolumeListTable from '$lib/components/volume/VolumeListTable.svelte';
  import SnapshotListTable from '$lib/components/volume/SnapshotListTable.svelte';
  import SlidePanel from '$lib/components/SlidePanel.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import { Alert, Button, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
  import VolumesTabs from '$lib/components/volume/VolumesTabs.svelte';
  import VolumesLoadingState from '$lib/components/volume/VolumesLoadingState.svelte';
  import VolumesEmptyState from '$lib/components/volume/VolumesEmptyState.svelte';
  import VolumesModalStack from '$lib/components/volume/VolumesModalStack.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import { betaFeatures } from '$lib/stores/betaFeatures';

  const ctrl = createVolumesController({
    token: () => $auth.token ?? undefined,
    projectId: () => $auth.projectId ?? undefined,
    volumeBackupsEnabled: () => $betaFeatures.volumeBackups,
    volumeSnapshotsEnabled: () => $betaFeatures.volumeSnapshots,
  });
  const volumeSelection = createResourceSelection();
  const snapshotSelection = createResourceSelection();
  let bulkBusy = $state(false);
  const selectableVolumeIds = $derived(new Set(ctrl.volumes.filter((volume) => volume.attachments.length === 0).map((volume) => volume.id)));
  const selectableSnapshotIds = $derived(new Set(ctrl.snapshots.map((snapshot) => snapshot.id)));

  function retainSelections() {
    volumeSelection.retain(ctrl.volumes.map((volume) => volume.id));
    snapshotSelection.retain(ctrl.snapshots.map((snapshot) => snapshot.id));
  }

  async function runBulkDelete(kind: 'volume' | 'snapshot') {
    const selection = kind === 'volume' ? volumeSelection : snapshotSelection;
    const ids = [...selection.ids];
    if (ids.length === 0) return;
    const eligible = kind === 'volume'
      ? ids.filter((id) => selectableVolumeIds.has(id))
      : ids.filter((id) => selectableSnapshotIds.has(id));
    const skipped = ids.length - eligible.length;
    if (eligible.length === 0) {
      toast.warning(`${ids.length}개는 현재 상태에서 삭제할 수 없어 제외했습니다.`);
      return;
    }
    const label = kind === 'volume' ? '볼륨' : '스냅샷';
    const warning = skipped > 0 ? `\n${skipped}개는 현재 상태에서 제외됩니다.` : '';
    if (!await confirmDialog(`선택한 ${label} ${eligible.length}개를 삭제하시겠습니까?${warning}`)) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(eligible, (id) =>
        api.delete(kind === 'volume' ? `/api/v1/volumes/${id}` : `/api/v1/volume-snapshots/${id}`, tokenSnapshot, projectSnapshot),
      );
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failed = results.length - successful.length;
      if (successful.length > 0) toast.success(`${successful.length}개 삭제 요청을 완료했습니다.`);
      if (failed > 0) toast.error(`${failed}개 삭제에 실패했습니다.`);
      if (skipped > 0) toast.warning(`${skipped}개는 현재 상태에서 삭제할 수 없어 제외했습니다.`);
      if ($auth.projectId !== projectSnapshot) return;
      selection.remove(successful);
      if (kind === 'volume') await ctrl.fetchVolumes();
      else await ctrl.fetchSnapshots();
    } finally {
      bulkBusy = false;
    }
  }

  const volumeBulkActions = $derived<BulkSelectionAction[]>([
    { key: 'delete', label: '삭제', tone: 'danger', disabled: [...volumeSelection.ids].every((id) => !selectableVolumeIds.has(id)), onAction: () => runBulkDelete('volume') },
  ]);
  const snapshotBulkActions = $derived<BulkSelectionAction[]>([
    { key: 'delete', label: '삭제', tone: 'danger', disabled: [...snapshotSelection.ids].every((id) => !selectableSnapshotIds.has(id)), onAction: () => runBulkDelete('snapshot') },
  ]);

  const ar = createAutoRefresh(() => ctrl.fetchAll(), {
    storageKey: 'dashboard-volumes',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 10,
    intervalOptions: [10, 15, 30, 60],
  });
  $effect(() => {
    const volumeIds = ctrl.volumes.map((volume) => volume.id);
    const snapshotIds = ctrl.snapshots.map((snapshot) => snapshot.id);
    untrack(() => {
      volumeSelection.retain(volumeIds);
      snapshotSelection.retain(snapshotIds);
    });
  });

  $effect(() => {
    const projectId = $auth.projectId;
    untrack(() => {
      volumeSelection.clear();
      snapshotSelection.clear();
      if (!projectId) return;
      ctrl.loading = true;
      void ctrl.fetchAll();
    });
  });

  $effect(() => {
    const tab = ctrl.tab;
    const snapshotsEnabled = $betaFeatures.volumeSnapshots;
    untrack(() => {
      if (!snapshotsEnabled && tab === 'snapshots') ctrl.tab = 'volumes';
      if (!snapshotsEnabled || tab === 'volumes') snapshotSelection.clear();
      else volumeSelection.clear();
    });
  });
</script>

<svelte:window
  onkeydown={(e) => { if (e.key === 'Escape' && ctrl.selectedVolumeId) ctrl.closeVolumePanel(); }}
/>

<VolumeCreateModal bind:open={ctrl.showModal} onCreated={() => ctrl.fetchVolumes()} />

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb="VOLUMES / BLOCK VOLUMES" title="블록 볼륨">
    {#snippet actions()}
      <Button dataTour="volume-create-open" onclick={() => ctrl.showModal = true} variant="primary">+ 볼륨 생성</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label="볼륨 목록 도구">
    {#snippet actions()}
      <TutorialStartButton tour="volume" />
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={ctrl.refreshing}
        onManualRefresh={() => ctrl.fetchAll()}
      />
    {/snippet}
  </ResourceToolbar>

  {#if ctrl.error}<Alert tone="danger">{ctrl.error}</Alert>{/if}

  {#if ctrl.loading}
    <VolumesLoadingState />
  {:else if ctrl.volumes.length === 0}
    <VolumesEmptyState onCreate={() => ctrl.showModal = true} />
  {:else}
    <VolumeSummaryCards volumes={ctrl.volumes} snapshots={ctrl.snapshots} quotas={ctrl.quotas} showSnapshots={$betaFeatures.volumeSnapshots} />
    <VolumesTabs bind:tab={ctrl.tab} volumeCount={ctrl.volumes.length} snapshotCount={ctrl.snapshots.length} showSnapshots={$betaFeatures.volumeSnapshots} />

    {#if ctrl.tab === 'volumes'}
      <div id="volume-resource-panel" role="tabpanel" aria-labelledby="volume-resource-tabs-volumes" tabindex="0" data-tour="volume-list">
      <VolumeListTable
        volumes={ctrl.volumes}
        selectedVolumeId={ctrl.selectedVolumeId}
        deleting={ctrl.deleting}
        autoBackupConfigs={ctrl.autoBackupConfigs}
        autoBackupToggling={ctrl.autoBackupToggling}
        openActionMenu={ctrl.openActionMenu}
        selectedIds={volumeSelection.ids}
        selectableIds={selectableVolumeIds}
        selectionDisabled={bulkBusy}
        onToggleSelect={(id) => volumeSelection.toggle(id)}
        onToggleAll={() => volumeSelection.toggleAll(selectableVolumeIds)}
        isSystemAdmin={!!$auth.isSystemAdmin}
        onOpenDetail={ctrl.openVolumePanel}
        onActionMenuOpen={(id) => (ctrl.openActionMenu = id)}
        onActionMenuClose={() => (ctrl.openActionMenu = null)}
        onBoot={ctrl.bootFromVolume}
        onExtend={(vol) => (ctrl.extendTargetVol = vol)}
        onBackup={(vol) => (ctrl.backupTargetVol = vol)}
        onSnapshot={(vol) => (ctrl.snapshotTargetVol = vol)}
        onTransfer={ctrl.openTransferModal}
        onForceDelete={ctrl.forceDeleteVolume}
        onDelete={ctrl.deleteVolume}
        onToggleAutoBackup={ctrl.toggleAutoBackup}
        volumeBackupsEnabled={$betaFeatures.volumeBackups}
        volumeSnapshotsEnabled={$betaFeatures.volumeSnapshots}
      />
      <BulkSelectionOverlay
        count={volumeSelection.count}
        ariaLabel="선택한 볼륨 일괄 작업"
        actions={volumeBulkActions}
        busy={bulkBusy}
        onClear={() => volumeSelection.clear()}
      />
      </div>
    {:else}
      <div id="snapshot-resource-panel" role="tabpanel" aria-labelledby="volume-resource-tabs-snapshots" tabindex="0">
      <BulkSelectionOverlay
        count={snapshotSelection.count}
        ariaLabel="선택한 스냅샷 일괄 작업"
        actions={snapshotBulkActions}
        busy={bulkBusy}
        onClear={() => snapshotSelection.clear()}
      />
      <SnapshotListTable
        snapshots={ctrl.snapshots}
        deleting={ctrl.deleting}
        selectedIds={snapshotSelection.ids}
        selectableIds={selectableSnapshotIds}
        selectionDisabled={bulkBusy}
        onToggleSelect={(id) => snapshotSelection.toggle(id)}
        onToggleAll={() => snapshotSelection.toggleAll(selectableSnapshotIds)}
        openSnapshotActionMenu={ctrl.openSnapshotActionMenu}
        onActionMenuOpen={(id) => (ctrl.openSnapshotActionMenu = id)}
        onActionMenuClose={() => (ctrl.openSnapshotActionMenu = null)}
        onDelete={ctrl.deleteSnapshot}
      />
      </div>
    {/if}
  {/if}
</PageShell>

{#if ctrl.selectedVolumeId}
  <SlidePanel onClose={ctrl.closeVolumePanel} ariaLabel="볼륨 상세" width="w-full md:w-[60vw] max-w-2xl">
    <VolumeDetailPanel
      volumeId={ctrl.selectedVolumeId}
      onClose={ctrl.closeVolumePanel}
      onDeleted={() => { ctrl.fetchVolumes(); ctrl.closeVolumePanel(); }}
    />
  </SlidePanel>
{/if}

<VolumesModalStack
  transferVolumeId={ctrl.transferVolumeId}
  transferVolumeName={ctrl.transferVolumeName}
  showTransfer={ctrl.showTransferModal}
  extendTarget={ctrl.extendTargetVol}
  backupTarget={ctrl.backupTargetVol}
  snapshotTarget={ctrl.snapshotTargetVol}
  onCloseTransfer={() => ctrl.showTransferModal = false}
  onTransferred={() => { ctrl.fetchVolumes(); ctrl.showTransferModal = false; }}
  onCloseExtend={() => ctrl.extendTargetVol = null}
  onExtendSuccess={() => { ctrl.extendTargetVol = null; ctrl.fetchVolumes(true); }}
  onCloseBackup={() => ctrl.backupTargetVol = null}
  onCloseSnapshot={() => ctrl.snapshotTargetVol = null}
  onSnapshotSuccess={() => { ctrl.snapshotTargetVol = null; ctrl.fetchSnapshots(); }}
  volumeBackupsEnabled={$betaFeatures.volumeBackups}
  volumeSnapshotsEnabled={$betaFeatures.volumeSnapshots}
/>
