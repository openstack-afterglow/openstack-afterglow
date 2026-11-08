<script lang="ts">
 import { authDisplayContext } from '$lib/stores/authDisplayContext';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
 import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
 import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
 import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

	import { t as tl } from '$lib/i18n/ns/common';
  import { t } from '$lib/i18n/ns/volume';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth, isMockAuthActive } from '$lib/stores/auth';
  import { page } from '$app/state';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import { api, ApiError } from '$lib/api/client';
  import type { Volume, VolumeSnapshot } from '$lib/types/volume';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
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
  // Only the snapshot created in this page session gets the tutorial delete anchor.
  let lastCreatedId = $state<string | null>(null);
  let bulkBusy = $state(false);
  const selection = createResourceSelection();
  // Tutorial mode (synthetic mockup session) shows volume snapshots without touching the stored beta flag.
  const volumeSnapshotsEnabled = $derived($betaFeatures.volumeSnapshots || (page.data?.mockup?.active === true && isMockAuthActive()));
  let search = $state('');
 const columns = $derived<TableColumn<VolumeSnapshot>[]>([
  { key: 'name', label: t('snapshotsTable.name'), value: row => row.name },
  { key: 'status', label: t('snapshotsTable.status'), value: row => row.status },
  { key: 'size', label: t('snapshotsTable.size'), value: row => row.size },
  { key: 'volume', label: t('snapshotsTable.volumeId'), value: row => row.volume_id },
  { key: 'description', label: t('snapshotsTable.description'), value: row => row.description },
  { key: 'created', label: t('snapshotsTable.createdAt'), value: row => row.created_at },
 ]);
 const view = createTableView({ locale: intlLocale, rows: () => snapshots, columns: () => columns, search: () => search, searchable: row => [row.id, ...columns.map(column => column.value(row))].map(value => String(value ?? '')) });
 const selectableIds = $derived(new Set(view.rows.map((snapshot) => snapshot.id)));

  function retainSelection() {
    selection.retain(selectableIds);
  }

  async function runBulkDelete() {
    const ids = [...selection.ids];
    if (!ids.length) return;
    if (!await confirmDialog(t('snapshotsPage.bulkDeleteConfirm', { count: ids.length }))) return;
    const token = $auth.token ?? undefined;
    const projectId = $auth.projectId ?? undefined;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/volume-snapshots/${id}`, token, projectId));
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failed = results.length - successful.length;
      if (successful.length) toast.success(t('snapshotsPage.bulkDeleteSuccess', { count: successful.length }));
      if (failed) toast.error(t('snapshotsPage.bulkDeleteFailed', { count: failed }));
      if ($auth.projectId !== projectId) return;
      selection.remove(successful);
      await fetchSnapshots();
    } finally {
      bulkBusy = false;
    }
  }

  const bulkActions = $derived<BulkSelectionAction[]>([{ key: 'delete', label: t('snapshotsPage.delete'), tone: 'danger', onAction: runBulkDelete }]);


  function clearSnapshotsState() {
    snapshots = [];
    lastCreatedId = null;
    volumes = [];
    error = '';
  }


  async function fetchSnapshots(force = false) {
    if (!volumeSnapshotsEnabled) {
      clearSnapshotsState();
      loading = false;
      return;
    }
    try {
      snapshots = await api.get<VolumeSnapshot[]>('/api/v1/volume-snapshots', $auth.token ?? undefined, $auth.projectId ?? undefined, { refresh: force });
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? t('snapshotsPage.fetchFailed', { status: e.status }) : t('snapshotsPage.serverError');
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
    if (!volumeSnapshotsEnabled) return t('snapshotsPage.betaDisabled');
    try {
      const created = await api.post<VolumeSnapshot>('/api/v1/volume-snapshots', form, $auth.token ?? undefined, $auth.projectId ?? undefined);
      lastCreatedId = created.id;
      await fetchSnapshots();
      return true;
    } catch (e) {
      return e instanceof ApiError ? e.message : t('snapshotsPage.createFailed');
    }
  }

  async function deleteSnapshot(id: string, name: string) {
    if (!volumeSnapshotsEnabled) return;
    if (!await confirmDialog(t('snapshotsPage.deleteConfirm', { name: name || id.slice(0, 8) }))) return;
    deleting = id;
    try {
      await api.delete(`/api/v1/volume-snapshots/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      selection.remove([id]);
      await fetchSnapshots();
    } catch (e) {
      toast.error(t('snapshotsPage.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      deleting = null;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try { await fetchSnapshots(true); } finally { refreshing = false; }
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
    untrack(() => { selection.clear(); lastCreatedId = null; fetchSnapshots(); });
  });
  $effect(() => {
    const ids = selectableIds;
    untrack(() => retainSelection());
  });
 let viewOwner = '';
 $effect(() => authDisplayContext.subscribe(({ key }) => {
  if (viewOwner === key) return;
  viewOwner = key;
  untrack(() => { search = ''; view.reset(); });
 }));
</script>

{#if !volumeSnapshotsEnabled}
  <PageShell>
    <BetaFeatureGate title={t('snapshotsPage.betaTitle')} />
  </PageShell>
{:else}
<VolumeSnapshotCreateModal bind:open={showModal} {volumes} onCreate={createSnapshot} />

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb={t('snapshotsPage.breadcrumb')} title={t('snapshotsPage.title')}>
    {#snippet actions()}
      <TutorialStartButton tour="volume-snapshots" compactOnMobile />
      <Button onclick={openCreate} onintent={prefetchVolumes} variant="primary" dataTour="volume-snapshots-create-open">{t('snapshotsPage.create')}</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label={t('snapshotsPage.toolbar')}>
 {#snippet filters()}<RegexSearch id="VolumeSnapshotsTable-search" bind:value={search} />
 <TableViewControls {view} class={snapshots.length === 0 ? '' : 'lg:hidden'} />
 {/snippet}
    {#snippet actions()}<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing} onManualRefresh={forceRefresh} />{/snippet}
  </ResourceToolbar>

  {#if error}<Alert tone="danger">{error}</Alert>{/if}
  <div data-tour="volume-snapshots-list" class="space-y-4">
  {#if loading}
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('snapshotsPage.title') })} />
  {:else if snapshots.length === 0}
    <VolumeSnapshotsEmptyState onCreate={openCreate} onintent={prefetchVolumes} />
  {:else}
    <VolumeSnapshotsTable snapshots={view.rows} {view} {deleting} highlightId={lastCreatedId} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onDelete={deleteSnapshot} />
    <BulkSelectionOverlay count={selection.count} ariaLabel={t('snapshotsPage.bulkLabel')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
  {/if}
  </div>
</PageShell>
{/if}
