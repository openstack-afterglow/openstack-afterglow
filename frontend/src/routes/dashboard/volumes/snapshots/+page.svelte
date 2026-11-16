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
  import { goto } from '$app/navigation';
  import RecoveryVolumeCard from '$lib/components/volume/RecoveryVolumeCard.svelte';
  import { groupRecoveryPoints, recoveryVolumeName, recoveryVolumeUrl, type RecoveryGroup } from '$lib/components/volume/recoveryPoints';
  import VolumeBackupPolicies from '$lib/components/volume/backups/VolumeBackupPolicies.svelte';
  import { createVolumeBackupPoliciesController } from '$lib/stores/volumeBackupPoliciesController.svelte';
  import { projectAuthority } from '$lib/api/projectAuthority';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import { api, ApiError } from '$lib/api/client';
  import type { VolumeSnapshot } from '$lib/types/volume';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import { Alert, Button, EmptyState, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
  import VolumeSnapshotCreateModal from '$lib/components/volume/snapshots/VolumeSnapshotCreateModal.svelte';
  import VolumeSnapshotsTable from '$lib/components/volume/snapshots/VolumeSnapshotsTable.svelte';
  import { toast } from '$lib/stores/toast';
  import { betaFeatures } from '$lib/stores/betaFeatures';
  import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations } from '$lib/utils/bulkActions';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';

  let snapshots = $state<VolumeSnapshot[]>([]);
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
  const policies = createVolumeBackupPoliciesController('snapshot', () => volumeSnapshotsEnabled);
  const volumes = $derived(policies.volumes);
  const selectedVolumeId = $derived(page.url.searchParams.get('volume'));
  const groups = $derived(groupRecoveryPoints(volumes, snapshots, policies.policies));
  const selectedGroup = $derived(groups.find(group => group.id === selectedVolumeId));
  const volumeColumns = $derived<TableColumn<RecoveryGroup>[]>([
    { key: 'name', label: t('backupGroups.volume'), value: group => recoveryVolumeName(group, policies.settled && !policies.volumesError) },
    { key: 'status', label: t('listTable.status'), value: group => group.volume?.status },
    { key: 'size', label: t('backupGroups.volumeSize'), value: group => group.volume?.size },
    { key: 'count', label: t('snapshotGroups.count'), value: group => group.points.length },
    { key: 'latest', label: t('backupGroups.latest'), value: group => group.latest },
    { key: 'policy', label: t('backupGroups.policy'), value: group => policies.error ? null : group.policy ? group.policy.enabled ? t('backupGroups.policyActive') : t('backupGroups.policyPaused') : t('backupGroups.noPolicy') },
  ]);
  const groupView = createTableView({ locale: intlLocale, rows: () => groups, columns: () => volumeColumns, search: () => search, searchable: group => [group.id, recoveryVolumeName(group, policies.settled && !policies.volumesError)] });
  let creatorNames = $state<Record<string, string>>({});
  let generation = 0;
  function selectVolume(id: string | null) {
    selection.clear();
    void goto(recoveryVolumeUrl(page.url, id), { keepFocus: true, noScroll: true });
  }
  async function fetchCreators() {
    const state = $auth;
    const requestGeneration = generation;
    if (!state.token || !state.projectId || !volumeSnapshotsEnabled) return;
    const current = () => volumeSnapshotsEnabled && generation === requestGeneration && $auth.projectId === state.projectId && $auth.userId === state.userId;
    try {
      const result = await projectAuthority({ token: () => $auth.token ?? '', domainId: state.domainId ?? '', userId: state.userId ?? '', isCurrent: current, canSubmit: () => false }, state.projectId).members(state.projectId);
      if (current()) creatorNames = Object.fromEntries(result.items.map(member => [member.user_id, member.username]));
    } catch { /* Denied member lookup leaves the native short-ID fallback. */ }
  }
  let search = $state('');
 const columns = $derived<TableColumn<VolumeSnapshot>[]>([
  { key: 'name', label: t('snapshotsTable.name'), value: row => row.name },
  { key: 'status', label: t('snapshotsTable.status'), value: row => row.status },
  { key: 'size', label: t('snapshotsTable.size'), value: row => row.size },
  { key: 'volume', label: t('snapshotsTable.volumeId'), value: row => row.volume_id },
  { key: 'description', label: t('snapshotsTable.description'), value: row => row.description },
  { key: 'created', label: t('snapshotsTable.createdAt'), value: row => row.created_at },
 ]);
 const view = createTableView({ locale: intlLocale, rows: () => [...snapshots.filter(snapshot => snapshot.volume_id === selectedVolumeId)].sort((a, b) => (Date.parse(b.created_at ?? '') || 0) - (Date.parse(a.created_at ?? '') || 0)), columns: () => columns });
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
    error = '';
    creatorNames = {};
  }


  async function fetchSnapshots(force = false) {
    if (!volumeSnapshotsEnabled) {
      clearSnapshotsState();
      loading = false;
      return;
    }
    const projectId = $auth.projectId;
    const token = $auth.token;
    const requestGeneration = generation;
    if (!projectId || !token) return;
    const current = () => volumeSnapshotsEnabled && generation === requestGeneration && $auth.projectId === projectId && $auth.token === token;
    try {
      const next = await api.get<VolumeSnapshot[]>('/api/v1/volume-snapshots', token, projectId, { refresh: force });
      if (current()) { snapshots = next; error = ''; }
    } catch (e) {
      if (current()) error = e instanceof ApiError ? t('snapshotsPage.fetchFailed', { status: e.status }) : t('snapshotsPage.serverError');
    } finally {
      if (current()) loading = false;
    }
  }

  function openCreate() {
    showModal = true;
  }

  async function createSnapshot(form: { volume_id: string; name: string; description: string; force: boolean }): Promise<string | true> {
    if (!volumeSnapshotsEnabled) return t('snapshotsPage.betaDisabled');
    const token = $auth.token;
    const projectId = $auth.projectId;
    const owner = generation;
    try {
      const created = await api.post<VolumeSnapshot>('/api/v1/volume-snapshots', form, token ?? undefined, projectId ?? undefined);
      if (owner !== generation || $auth.projectId !== projectId || !volumeSnapshotsEnabled) return true;
      lastCreatedId = created.id;
      await fetchSnapshots();
      if (owner === generation && $auth.projectId === projectId && volumeSnapshotsEnabled) selectVolume(form.volume_id);
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
    try { await Promise.all([fetchSnapshots(true), policies.refresh(), fetchCreators()]); } finally { refreshing = false; }
  }

  const ar = createAutoRefresh(async () => { await Promise.all([fetchSnapshots(), policies.refresh()]); }, {
    storageKey: 'dashboard-volume-snapshots',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 15,
    intervalOptions: [10, 15, 30, 60],
  });

  $effect(() => {
    const enabled = volumeSnapshotsEnabled;
    let previous = '';
    return authDisplayContext.subscribe(({ key, ready }) => {
      if (key === previous) return;
      previous = key;
      untrack(() => {
        generation++;
        clearSnapshotsState(); selection.clear(); showModal = false;
        loading = enabled && ready;
        if (loading) void Promise.all([fetchSnapshots(), fetchCreators()]);
      });
    });
  });
  $effect(() => {
    const ids = selectableIds;
    untrack(() => retainSelection());
  });
 let viewOwner = '';
 $effect(() => authDisplayContext.subscribe(({ key }) => {
  if (viewOwner === key) return;
  viewOwner = key;
  untrack(() => { search = ''; view.reset(); groupView.reset(); });
 }));
</script>

{#if !volumeSnapshotsEnabled}
  <PageShell>
    <BetaFeatureGate title={t('snapshotsPage.betaTitle')} />
  </PageShell>
{:else}
<VolumeSnapshotCreateModal bind:open={showModal} {volumes} initialVolumeId={selectedVolumeId ?? ''} onCreate={createSnapshot} />

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb={t('snapshotsPage.breadcrumb')} title={t('snapshotsPage.title')}>
    {#snippet actions()}
      <TutorialStartButton tour="volume-snapshots" compactOnMobile />
      <Button onclick={openCreate} variant="primary" dataTour="volume-snapshots-create-open">{t('snapshotsPage.create')}</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label={t('snapshotsPage.toolbar')}>
 {#snippet filters()}{#if !selectedVolumeId}<RegexSearch id="VolumeSnapshotsTable-search" bind:value={search} /><TableViewControls view={groupView} />{/if}{/snippet}
    {#snippet actions()}<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing} onManualRefresh={forceRefresh} />{/snippet}
  </ResourceToolbar>

  {#if error}<Alert tone="danger">{error}</Alert>{/if}
  <div data-tour="volume-snapshots-list" class="space-y-4">
  {#if loading || (!policies.settled && !!$auth.projectId && !!$auth.token)}
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('snapshotsPage.title') })} />
  {:else if selectedVolumeId}
    <div class="flex flex-wrap items-center gap-3">
      <Button variant="ghost" onclick={() => selectVolume(null)}>{t('backupGroups.back')}</Button>
      <h2 class="min-w-0 break-all text-lg font-semibold">{selectedGroup ? recoveryVolumeName(selectedGroup, policies.settled && !policies.volumesError) : selectedVolumeId}</h2>
    </div>
    <p class="text-sm text-ink-2">{t('snapshotGroups.methodHelp')}</p>
    {#key selectedVolumeId}<VolumeBackupPolicies controller={policies} volumeId={selectedVolumeId} resource="snapshot" />{/key}
    <VolumeSnapshotsTable snapshots={view.rows} {view} {deleting} {creatorNames} currentUserId={$auth.userId} highlightId={lastCreatedId} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onDelete={deleteSnapshot} />
    <BulkSelectionOverlay count={selection.count} ariaLabel={t('snapshotsPage.bulkLabel')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
  {:else}
    {#if policies.volumesError}<Alert tone="danger">{policies.volumesError}</Alert>{/if}
    {#if policies.error}<Alert tone="danger">{policies.error}</Alert>{/if}
    {#if groupView.rows.length === 0 && !error && !policies.error && !policies.volumesError && policies.settled}<EmptyState headline={t('backupGroups.empty')} />{/if}
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
      {#each groupView.rows as group (group.id)}<RecoveryVolumeCard {group} kind="snapshot" inventoryKnown={policies.settled && !policies.volumesError} policyKnown={policies.settled && !policies.error} onOpen={() => selectVolume(group.id)} />{/each}
    </div>
  {/if}
  </div>
</PageShell>
{/if}
