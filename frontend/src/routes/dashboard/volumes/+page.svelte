<script lang="ts">
 import { authDisplayContext } from '$lib/stores/authDisplayContext';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as tl } from '$lib/i18n/ns/common';
  import { t } from '$lib/i18n/ns/volume';
  import { onDestroy, untrack } from 'svelte';
  import { auth, canWrite } from '$lib/stores/auth';
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
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import VolumesEmptyState from '$lib/components/volume/VolumesEmptyState.svelte';
  import VolumesModalStack from '$lib/components/volume/VolumesModalStack.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import { betaFeatures } from '$lib/stores/betaFeatures';
  import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import type { Volume, VolumeSnapshot } from '$lib/types/volume';
  import { sortResources } from '$lib/utils/resourceSort';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import Field from '$lib/components/ui/Field.svelte';
  import SelectInput from '$lib/components/ui/SelectInput.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import { getStatusLabel } from '$lib/config/statusColors';

  const ctrl = createVolumesController({
    token: () => $auth.token ?? undefined,
    projectId: () => $auth.projectId ?? undefined,
    volumeSnapshotsEnabled: () => $betaFeatures.volumeSnapshots,
  });
  onDestroy(() => ctrl.destroy());
  const volumeSelection = createResourceSelection();
  const snapshotSelection = createResourceSelection();
  let bulkBusy = $state(false);
  let search = $state('');
  let pageSize = $state(20);
  let currentPage = $state(1);
  const volumeColumns = $derived<TableColumn<Volume>[]>([
    { key: 'name', label: t('listTable.name'), value: row => row.name },
    { key: 'size', label: t('listTable.size'), value: row => row.size },
    { key: 'type', label: t('listTable.type'), value: row => row.volume_type },
    { key: 'status', label: t('listTable.status'), value: row => row.status, format: value => getStatusLabel(String(value), 'volume') },
    { key: 'attachments', label: t('listTable.attachments'), value: row => row.attachments.length },
    { key: 'bootable', label: t('listTable.boot'), value: row => row.bootable },
  ]);
  const snapshotColumns = $derived<TableColumn<VolumeSnapshot>[]>([
    { key: 'name', label: t('snapshotListTable.name'), value: row => row.name },
    { key: 'volume', label: t('snapshotListTable.sourceVolume'), value: row => row.volume_id },
    { key: 'size', label: t('snapshotListTable.size'), value: row => row.size },
    { key: 'created', label: t('snapshotListTable.created'), value: row => row.created_at },
    { key: 'status', label: t('snapshotListTable.status'), value: row => row.status },
  ]);
  const volumeView = createTableView({ locale: intlLocale, rows: () => sortResources(ctrl.volumes, 'created_desc'), columns: () => volumeColumns, search: () => search, searchable: row => [row.name,row.id] });
  const snapshotView = createTableView({ locale: intlLocale, rows: () => ctrl.snapshots, columns: () => snapshotColumns, search: () => search, searchable: row => [row.name,row.id,row.volume_id] });
  const sortedVolumes = $derived(volumeView.rows);
  const pageVolumes = $derived(sortedVolumes.slice((currentPage - 1) * pageSize, currentPage * pageSize));
  const pageSnapshots = $derived(snapshotView.rows.slice((currentPage - 1) * pageSize, currentPage * pageSize));
  const resultCount = $derived(ctrl.tab === 'volumes' ? sortedVolumes.length : snapshotView.rows.length);
  const selectableVolumeIds = $derived(new Set(pageVolumes.filter((volume) => volume.attachments.length === 0).map((volume) => volume.id)));
  const selectableSnapshotIds = $derived(new Set(pageSnapshots.map((snapshot) => snapshot.id)));

  function resetListPage() {
    currentPage = 1;
    volumeSelection.clear();
    snapshotSelection.clear();
    ctrl.openActionMenu = null;
    ctrl.openSnapshotActionMenu = null;
  }

  function changeTab(tab: 'volumes' | 'snapshots') {
    ctrl.tab = tab;
    const url = new URL(page.url);
    if (tab === 'snapshots') url.searchParams.set('tab', tab);
    else url.searchParams.delete('tab');
    void goto(url, { noScroll: true, keepFocus: true });
  }

  $effect(() => {
    const requested = page.url.searchParams.get('tab');
    ctrl.tab = requested === 'snapshots' && $betaFeatures.volumeSnapshots ? 'snapshots' : 'volumes';
    untrack(resetListPage);
  });
  $effect(() => {
    search; volumeView.sort; volumeView.filters; snapshotView.sort; snapshotView.filters;
    untrack(resetListPage);
  });
  $effect(() => {
    const lastPage = Math.max(1, Math.ceil(resultCount / pageSize));
    if (currentPage > lastPage) currentPage = lastPage;
  });


  async function runBulkDelete(kind: 'volume' | 'snapshot') {
    const selection = kind === 'volume' ? volumeSelection : snapshotSelection;
    const ids = [...selection.ids];
    if (ids.length === 0) return;
    const eligible = kind === 'volume'
      ? ids.filter((id) => selectableVolumeIds.has(id))
      : ids.filter((id) => selectableSnapshotIds.has(id));
    const skipped = ids.length - eligible.length;
    if (eligible.length === 0) {
      toast.warning(t('page.bulkSkipped', { count: ids.length }));
      return;
    }
    if (!await confirmDialog(t('page.bulkDeleteConfirm', { kind, count: eligible.length, skipped }))) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(eligible, (id) =>
        api.delete(kind === 'volume' ? `/api/v1/volumes/${id}` : `/api/v1/volume-snapshots/${id}`, tokenSnapshot, projectSnapshot),
      );
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failed = results.length - successful.length;
      if (successful.length > 0) toast.success(t('page.bulkDeleteSuccess', { count: successful.length }));
      if (failed > 0) toast.error(t('page.bulkDeleteFailed', { count: failed }));
      if (skipped > 0) toast.warning(t('page.bulkSkipped', { count: skipped }));
      if ($auth.projectId !== projectSnapshot) return;
      selection.remove(successful);
      if (kind === 'volume') await ctrl.fetchVolumes();
      else await ctrl.fetchSnapshots();
    } finally {
      bulkBusy = false;
    }
  }

  const volumeBulkActions = $derived<BulkSelectionAction[]>([
    { key: 'delete', label: t('page.delete'), tone: 'danger', disabled: [...volumeSelection.ids].every((id) => !selectableVolumeIds.has(id)), onAction: () => runBulkDelete('volume') },
  ]);
  const snapshotBulkActions = $derived<BulkSelectionAction[]>([
    { key: 'delete', label: t('page.delete'), tone: 'danger', disabled: [...snapshotSelection.ids].every((id) => !selectableSnapshotIds.has(id)), onAction: () => runBulkDelete('snapshot') },
  ]);

  const ar = createAutoRefresh((force) => ctrl.fetchAll(force), {
    storageKey: 'dashboard-volumes',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 10,
    intervalOptions: [10, 15, 30, 60],
  });
  $effect(() => {
    const volumeIds = pageVolumes.map((volume) => volume.id);
    const snapshotIds = pageSnapshots.map((snapshot) => snapshot.id);
    untrack(() => {
      volumeSelection.retain(volumeIds);
      snapshotSelection.retain(snapshotIds);
    });
  });

  let lastProjectId: string | null | undefined;
  $effect(() => {
    const projectId = $auth.projectId;
    untrack(() => {
      volumeSelection.clear();
      snapshotSelection.clear();
      if (lastProjectId !== undefined && lastProjectId !== projectId) ctrl.resetProjectScope();
      lastProjectId = projectId;
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
 let viewOwner = '';
 $effect(() => authDisplayContext.subscribe(({ key }) => {
  if (viewOwner === key) return;
  viewOwner = key;
  untrack(() => { search = ''; volumeView.reset(); snapshotView.reset(); });
 }));
</script>

<svelte:window
  onkeydown={(e) => { if (e.key === 'Escape' && ctrl.selectedVolumeId) ctrl.closeVolumePanel(); }}
/>

<VolumeCreateModal bind:open={ctrl.showModal} onCreated={(context, createdVolumeId) => ctrl.fetchVolumes(false, context, createdVolumeId)} />

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb={t('page.breadcrumb')} title={ctrl.loading || ctrl.error ? t('page.title') : t('page.titleWithCount', { title: t('page.title'), count: ctrl.volumes.length })}>
    {#snippet actions()}
      <TutorialStartButton tour="volume" />
      <Button dataTour="volume-create-open" onclick={() => ctrl.showModal = true} variant="primary">{t('page.create')}</Button>
      <Button variant="outline" disabled={!$canWrite} onclick={() => ctrl.openTransferModal('', '', 'receive')}>{t('transferModal.receiveTitle')}</Button>
      <Button variant="outline" disabled={!$canWrite} onclick={() => ctrl.openTransferModal('', '', 'list')}>{t('transferModal.listTitle')}</Button>
    {/snippet}
  </PageHeader>
  {#if !ctrl.loading && !ctrl.error}
    <VolumeSummaryCards volumes={ctrl.volumes} snapshots={ctrl.snapshots} quotas={ctrl.quotas} showSnapshots={$betaFeatures.volumeSnapshots} snapshotsKnown={!ctrl.snapshotsLoading && !ctrl.snapshotsError} />
  {/if}
  <VolumesTabs tab={ctrl.tab} onChange={changeTab} volumeCount={ctrl.loading || ctrl.error ? null : ctrl.volumes.length} snapshotCount={ctrl.snapshotsLoading || ctrl.snapshotsError ? null : ctrl.snapshots.length} showSnapshots={$betaFeatures.volumeSnapshots} />
  <ResourceToolbar label={t('page.toolbar')}>
    {#snippet filters()}
      <RegexSearch id="project-volume-search" bind:value={search} label={t('page.search')} />
      {#if ctrl.tab === 'volumes'}
        <TableViewControls view={volumeView} class={ctrl.volumes.length === 0 ? '' : 'lg:hidden'} />
      {:else}
        <TableViewControls view={snapshotView} class={ctrl.snapshots.length === 0 ? '' : 'lg:hidden'} />
      {/if}
    {/snippet}
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={ctrl.refreshing}
        onManualRefresh={ar.refresh}
      />
    {/snippet}
  </ResourceToolbar>

  {#if ctrl.error}<Alert tone="danger">{ctrl.error}</Alert>{/if}
  {#if ctrl.quotasError}<Alert tone="warning">{ctrl.quotasError}</Alert>{/if}

  {#if ctrl.loading}
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('page.title') })} />
  {:else if ctrl.error && ctrl.volumes.length === 0 && ctrl.tab === 'volumes'}
    <!-- The failed request is represented by the alert, never an empty success. -->
  {:else if ctrl.volumes.length === 0 && ctrl.tab === 'volumes'}
    <VolumesEmptyState onCreate={() => ctrl.showModal = true} />
  {:else}

    {#if ctrl.tab === 'volumes'}
      <div id="volume-resource-panel" role="tabpanel" aria-labelledby="volume-resource-tabs-volumes" tabindex="0" data-tour="volume-list">
      {#if sortedVolumes.length === 0}<p class="py-6 text-sm text-ink-2" role="status">{t('page.noMatches')}</p>{/if}
      <VolumeListTable
        volumes={pageVolumes}
        view={volumeView}
        selectedVolumeId={ctrl.selectedVolumeId}
        deleting={ctrl.deleting}
        openActionMenu={ctrl.openActionMenu}
        selectedIds={volumeSelection.ids}
        selectableIds={selectableVolumeIds}
        selectionDisabled={bulkBusy}
        onToggleSelect={(id) => volumeSelection.toggle(id)}
        onToggleAll={() => volumeSelection.toggleAll(selectableVolumeIds)}
        isSystemAdmin={false}
        onOpenDetail={ctrl.openVolumePanel}
        onActionMenuOpen={(id) => (ctrl.openActionMenu = id)}
        onActionMenuClose={() => (ctrl.openActionMenu = null)}
        onRename={(vol) => (ctrl.renameTargetVol = vol)}
        onBoot={ctrl.bootFromVolume}
        onExtend={(vol) => (ctrl.extendTargetVol = vol)}
        onBackup={(vol) => (ctrl.backupTargetVol = vol)}
        onSnapshot={(vol) => (ctrl.snapshotTargetVol = vol)}
        onTransfer={ctrl.openTransferModal}
        onForceDelete={ctrl.forceDeleteVolume}
        onDelete={ctrl.deleteVolume}
        volumeSnapshotsEnabled={$betaFeatures.volumeSnapshots}
      />
      <BulkSelectionOverlay
        count={volumeSelection.count}
        ariaLabel={t('page.volumeBulkLabel')}
        actions={volumeBulkActions}
        busy={bulkBusy}
        onClear={() => volumeSelection.clear()}
      />
      </div>
    {:else}
      <div id="snapshot-resource-panel" role="tabpanel" aria-labelledby="volume-resource-tabs-snapshots" tabindex="0">
      {#if ctrl.snapshotsLoading}<LoadingState variant="section" label={tl('state.loadingNamed', { name: t('snapshotsPage.title') })} />
      {:else if ctrl.snapshotsError}<Alert tone="danger">{ctrl.snapshotsError}<Button variant="outline" onclick={() => ctrl.fetchSnapshots(true)}>{t('page.retry')}</Button></Alert>
      {:else}
      <BulkSelectionOverlay
        count={snapshotSelection.count}
        ariaLabel={t('page.snapshotBulkLabel')}
        actions={snapshotBulkActions}
        busy={bulkBusy}
        onClear={() => snapshotSelection.clear()}
      />
      <SnapshotListTable
        snapshots={pageSnapshots}
        view={snapshotView}
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
      {/if}
      </div>
    {/if}
    {#if ctrl.tab === 'volumes' || (!ctrl.snapshotsLoading && !ctrl.snapshotsError)}
    <footer class="flex flex-wrap items-end justify-between gap-3" data-testid="project-volume-footer">
      <Field label={t('page.pageSize')} for="project-volume-page-size"><SelectInput id="project-volume-page-size" value={String(pageSize)} onchange={(event) => { pageSize = Number((event.target as HTMLSelectElement).value); resetListPage(); }}>{#each [10, 20, 30] as size}<option value={String(size)}>{size}</option>{/each}</SelectInput></Field>
      <Pagination class="!mt-0" page={currentPage} totalPages={Math.max(1, Math.ceil(resultCount / pageSize))} hasPrev={currentPage > 1} hasNext={currentPage * pageSize < resultCount} note={t('page.resultCount', { filtered: resultCount, total: ctrl.tab === 'volumes' ? ctrl.volumes.length : ctrl.snapshots.length })} onPrev={() => { currentPage -= 1; volumeSelection.clear(); snapshotSelection.clear(); }} onNext={() => { currentPage += 1; volumeSelection.clear(); snapshotSelection.clear(); }} />
    </footer>
    {/if}
  {/if}
</PageShell>

{#if ctrl.selectedVolumeId}
  <SlidePanel onClose={ctrl.closeVolumePanel} ariaLabel={t('page.detailLabel')} width="w-full md:w-[60vw] max-w-2xl">
    <VolumeDetailPanel
      volumeId={ctrl.selectedVolumeId}
      refreshKey={ctrl.detailRefreshKey}
      onClose={ctrl.closeVolumePanel}
      onDeleted={() => { ctrl.fetchVolumes(); ctrl.closeVolumePanel(); }}
      onRenamed={(updated) => ctrl.applyRenamedVolume(updated, 'detail')}
      onChanged={() => { void ctrl.fetchVolumes(); void ctrl.fetchSnapshots(); }}
    />
  </SlidePanel>
{/if}

<VolumesModalStack
  transferVolumeId={ctrl.transferVolumeId}
  transferVolumeName={ctrl.transferVolumeName}
  showTransfer={ctrl.showTransferModal}
  transferMode={ctrl.transferMode}
  extendTarget={ctrl.extendTargetVol}
  projectId={$auth.projectId ?? undefined}
  backupTarget={ctrl.backupTargetVol}
  snapshotTarget={ctrl.snapshotTargetVol}
  renameTarget={ctrl.renameTargetVol}
  onCloseTransfer={() => ctrl.showTransferModal = false}
  onTransferChanged={() => { void ctrl.fetchVolumes(true); ctrl.refreshSelectedDetail(); }}
  onTransferred={() => { ctrl.fetchVolumes(); ctrl.showTransferModal = false; }}
  onCloseExtend={() => ctrl.extendTargetVol = null}
  onExtendSuccess={() => { ctrl.extendTargetVol = null; ctrl.fetchVolumes(true); ctrl.refreshSelectedDetail(); }}
  onCloseBackup={() => ctrl.backupTargetVol = null}
  onCloseSnapshot={() => ctrl.snapshotTargetVol = null}
  onSnapshotSuccess={() => { ctrl.snapshotTargetVol = null; ctrl.fetchSnapshots(); ctrl.refreshSelectedDetail(); }}
  onCloseRename={() => ctrl.renameTargetVol = null}
  onRenamed={(updated) => ctrl.applyRenamedVolume(updated, 'list')}
  volumeSnapshotsEnabled={$betaFeatures.volumeSnapshots}
/>
