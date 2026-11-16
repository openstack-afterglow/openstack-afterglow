<script lang="ts">
 import { authDisplayContext } from '$lib/stores/authDisplayContext';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
 import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
 import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
 import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

	import { t as tl } from '$lib/i18n/ns/common';
	import { t } from '$lib/i18n/ns/volume';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import RecoveryVolumeCard from '$lib/components/volume/RecoveryVolumeCard.svelte';
	import { groupRecoveryPoints, recoveryVolumeName, recoveryVolumeUrl, type RecoveryGroup } from '$lib/components/volume/recoveryPoints';
	import { projectAuthority } from '$lib/api/projectAuthority';
	import VolumeBackupPolicies from '$lib/components/volume/backups/VolumeBackupPolicies.svelte';
	import { createVolumeBackupPoliciesController } from '$lib/stores/volumeBackupPoliciesController.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { auth, canWrite, projectSwitching } from '$lib/stores/auth';
	import { derived } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import type { VolumeBackup } from '$lib/types/volume';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { Alert, Button, EmptyState, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
	import VolumeBackupCreateModal from '$lib/components/volume/backups/VolumeBackupCreateModal.svelte';
	import VolumeBackupRestoreModal from '$lib/components/volume/backups/VolumeBackupRestoreModal.svelte';
	import VolumeBackupListTable from '$lib/components/volume/backups/VolumeBackupListTable.svelte';
	import { toast } from '$lib/stores/toast';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';

	let backups = $state<VolumeBackup[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let deleting = $state<string | null>(null);
	let showModal = $state(false);
	let showRestoreModal = $state(false);
	let selectedBackup = $state<VolumeBackup | null>(null);
	// Id of the backup created on this page; the tutorial delete anchor follows only this row.
	let lastCreatedId = $state<string | null>(null);
	let bulkBusy = $state(false);
	const policies = createVolumeBackupPoliciesController();
	const volumes = $derived(policies.volumes);
	const selectedVolumeId = $derived(page.url.searchParams.get('volume') ?? page.url.searchParams.get('auto-backup'));
	const groups = $derived(groupRecoveryPoints(volumes, backups, policies.policies));
	const selectedGroup = $derived(groups.find(group => group.id === selectedVolumeId));
	const volumeColumns = $derived<TableColumn<RecoveryGroup>[]>([
		{ key: 'name', label: t('backupGroups.volume'), value: group => recoveryVolumeName(group, policies.settled && !policies.volumesError) },
		{ key: 'status', label: t('listTable.status'), value: group => group.volume?.status },
		{ key: 'size', label: t('backupGroups.volumeSize'), value: group => group.volume?.size },
		{ key: 'count', label: t('backupGroups.count'), value: group => group.points.length },
		{ key: 'latest', label: t('backupGroups.latest'), value: group => group.latest },
		{ key: 'policy', label: t('backupGroups.policy'), value: group => policies.error ? null : group.policy ? group.policy.enabled ? t('backupGroups.policyActive') : t('backupGroups.policyPaused') : t('backupGroups.noPolicy') },
	]);
	const groupView = createTableView({ locale: intlLocale, rows: () => groups, columns: () => volumeColumns, search: () => search, searchable: group => [group.id, recoveryVolumeName(group, policies.settled && !policies.volumesError)] });
	let creatorNames = $state<Record<string, string>>({});
	function selectVolume(id: string | null) {
		selection.clear();
		void goto(recoveryVolumeUrl(page.url, id), { keepFocus: true, noScroll: true });
	}
	async function fetchCreators() {
		const state = $auth;
		const projectId = state.projectId;
		const requestGeneration = generation;
		if (!state.token || !projectId) return;
		const current = () => generation === requestGeneration && $auth.projectId === projectId && $auth.userId === state.userId;
		try {
			const result = await projectAuthority({ token: () => $auth.token ?? '', domainId: state.domainId ?? '', userId: state.userId ?? '', isCurrent: current, canSubmit: () => false }, projectId).members(projectId);
			if (current()) creatorNames = Object.fromEntries(result.items.map(member => [member.user_id, member.username]));
		} catch { /* Project member lookup may be denied; retain short native creator IDs. */ }
	}
	let generation = 0;
	let consumedLink = $state('');
	const selection = createResourceSelection();
	let search = $state('');
 const columns = $derived<TableColumn<VolumeBackup>[]>([
  { key: 'name', label: t('backupListTable.name'), value: row => row.name },
  { key: 'status', label: t('backupListTable.status'), value: row => row.status },
  { key: 'size', label: t('backupListTable.size'), value: row => row.size },
  { key: 'incremental', label: t('backupListTable.incremental'), value: row => row.is_incremental },
  { key: 'created', label: t('backupListTable.createdAt'), value: row => row.created_at },
 ]);
 const view = createTableView({ locale: intlLocale, rows: () => [...backups.filter(backup => backup.volume_id === selectedVolumeId)].sort((a, b) => (Date.parse(b.created_at ?? '') || 0) - (Date.parse(a.created_at ?? '') || 0)), columns: () => columns });
 const selectableIds = $derived(new Set(view.rows.map((backup) => backup.id)));

	async function fetchBackups(force = false) {
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId;
		const requestGeneration = generation;
		if (!projectId || !token || $projectSwitching) return;
		try {
			const next = await api.get<VolumeBackup[]>('/api/v1/volumes/backups', token, projectId, { refresh: force });
			if ($auth.projectId !== projectId || $auth.token !== token || generation !== requestGeneration) return;
			backups = next;
			error = '';
		} catch (e) {
			if ($auth.projectId === projectId && $auth.token === token && generation === requestGeneration) error = e instanceof ApiError ? t('backupsPage.fetchFailed', { status: e.status }) : t('backupsPage.serverError');
		} finally {
			if ($auth.projectId === projectId && $auth.token === token && generation === requestGeneration) loading = false;
		}
	}

	function openCreate() {
		showModal = true;
	}

	async function createBackup(form: { volume_id: string; name: string; description: string; incremental: boolean; force: boolean }): Promise<string | true> {
		const token = $auth.token;
		const projectId = $auth.projectId;
		const owner = generation;
		try {
			const created = await api.post<VolumeBackup>('/api/v1/volumes/backups', form, token ?? undefined, projectId ?? undefined);
			if (owner !== generation || $auth.projectId !== projectId) return true;
			lastCreatedId = created.id;
			await fetchBackups();
			if (owner === generation && $auth.projectId === projectId) selectVolume(form.volume_id);
			return true;
		}
		catch (e) { return e instanceof ApiError ? e.message : t('backupsPage.createFailed'); }
	}

	async function restoreBackup(backupId: string): Promise<{ volume_id: string; volume_name: string } | string> {
		try { return await api.post<{ volume_id: string; volume_name: string }>(`/api/v1/volumes/backups/${backupId}/restore`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined); }
		catch (e) { return e instanceof ApiError ? e.message : t('backupsPage.restoreFailed'); }
	}

	async function deleteBackup(id: string, name: string) {
		if (!await confirmDialog(t('backupsPage.deleteConfirm', { name: name || id.slice(0, 8) }))) return;
		deleting = id;
		try { await api.delete(`/api/v1/volumes/backups/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined); selection.remove([id]); await fetchBackups(); }
		catch (e) { toast.error(t('backupsPage.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) })); }
		finally { deleting = null; }
	}

	async function runBulkDelete() {
		const ids = [...selection.ids];
		if (!ids.length || !await confirmDialog(t('backupsPage.bulkDeleteConfirm', { count: ids.length }))) return;
		const token = $auth.token ?? undefined; const projectId = $auth.projectId ?? undefined;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/volumes/backups/${id}`, token, projectId));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length) toast.success(t('backupsPage.bulkDeleteSuccess', { count: successful.length }));
			if (failed) toast.error(t('backupsPage.bulkDeleteFailed', { count: failed }));
			if ($auth.projectId === projectId) { selection.remove(successful); await fetchBackups(); }
		} finally { bulkBusy = false; }
	}

	const bulkActions = $derived<BulkSelectionAction[]>([{ key: 'delete', label: t('backupsPage.delete'), tone: 'danger', onAction: runBulkDelete }]);
	async function forceRefresh() { refreshing = true; try { await Promise.all([fetchBackups(true), policies.refresh(), fetchCreators()]); } finally { refreshing = false; } }
	const ar = createAutoRefresh(async () => { await Promise.all([fetchBackups(), policies.refresh()]); }, { storageKey: 'dashboard-volume-backups', defaultActive: true, defaultInterval: 15, intervalOptions: [10, 15, 30, 60], invokeOnMount: false });

	$effect(() => {
		let previous = '';
		return derived([auth, projectSwitching], ([value, switching]) => ({ value, switching })).subscribe(({ value, switching }) => {
			const key = JSON.stringify([value.token, value.projectId, value.userId, switching]);
			if (key === previous) return;
			previous = key;
			untrack(() => {
				generation++;
				selection.clear(); backups = []; creatorNames = {}; error = ''; selectedBackup = null; lastCreatedId = null;
				showModal = false; showRestoreModal = false;
				loading = Boolean(value.projectId && value.token);
				if (value.projectId && value.token && !switching) void Promise.all([fetchBackups(), fetchCreators()]);
			});
		});
	});
	$effect(() => {
		const volumeId = page.url.searchParams.get('auto-backup');
		const linkKey = `${policies.generation}:${volumeId}`;
		if (volumeId && consumedLink !== linkKey && !policies.loading && !policies.error && !policies.volumesError && $canWrite && policies.volumes.some((volume) => volume.id === volumeId)) {
			consumedLink = linkKey;
			untrack(() => policies.open(volumeId));
		}
	});
	$effect(() => { const ids = selectableIds; untrack(() => selection.retain(ids)); });
 let viewOwner = '';
 $effect(() => authDisplayContext.subscribe(({ key }) => {
  if (viewOwner === key) return;
  viewOwner = key;
  untrack(() => { search = ''; view.reset(); groupView.reset(); });
 }));
</script>

<VolumeBackupCreateModal bind:open={showModal} {volumes} {backups} initialVolumeId={selectedVolumeId ?? ''} onCreate={createBackup} />
<VolumeBackupRestoreModal bind:open={showRestoreModal} backup={selectedBackup} onRestore={restoreBackup} />
<PageShell class="bulk-selection-page space-y-4">
	<PageHeader breadcrumb={t('backupsPage.breadcrumb')} title={t('backupsPage.title')}>
		{#snippet actions()}
			<TutorialStartButton tour="volume-backups" compactOnMobile />
			<Button onclick={openCreate} variant="primary" dataTour="volume-backups-create-open">{t('backupsPage.create')}</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label={t('backupsPage.toolbar')}>
 {#snippet filters()}{#if !selectedVolumeId}<RegexSearch id="VolumeBackupListTable-search" bind:value={search} /><TableViewControls view={groupView} />{/if}{/snippet}
		{#snippet actions()}<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing} onManualRefresh={forceRefresh} />{/snippet}
	</ResourceToolbar>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	<div data-tour="volume-backups-list">
	{#if loading || (!policies.settled && !!$auth.projectId && !!$auth.token)}
		<LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('backupsPage.title') })} />
	{:else if selectedVolumeId}
		<div class="flex flex-wrap items-center gap-3">
			<Button variant="ghost" onclick={() => selectVolume(null)}>{t('backupGroups.back')}</Button>
			<h2 class="min-w-0 break-all text-lg font-semibold">{selectedGroup ? recoveryVolumeName(selectedGroup, policies.settled && !policies.volumesError) : selectedVolumeId}</h2>
		</div>
		{#key selectedVolumeId}<VolumeBackupPolicies controller={policies} volumeId={selectedVolumeId} />{/key}
		<VolumeBackupListTable backups={view.rows} {view} {creatorNames} currentUserId={$auth.userId} deletingId={deleting} highlightId={lastCreatedId} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onRestore={(b) => { selectedBackup = b; showRestoreModal = true; }} onDelete={deleteBackup} />
		<BulkSelectionOverlay count={selection.count} ariaLabel={t('backupsPage.bulkLabel')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
	{:else}
		{#if policies.volumesError}<Alert tone="danger">{policies.volumesError}</Alert>{/if}
		{#if policies.error}<Alert tone="danger">{policies.error}</Alert>{/if}
		{#if groupView.rows.length === 0 && !error && !policies.error && !policies.volumesError && policies.settled}<EmptyState headline={t('backupGroups.empty')} />{/if}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
			{#each groupView.rows as group (group.id)}<RecoveryVolumeCard {group} kind="backup" inventoryKnown={policies.settled && !policies.volumesError} policyKnown={policies.settled && !policies.error} onOpen={() => selectVolume(group.id)} />{/each}
		</div>
	{/if}
	</div>
</PageShell>
