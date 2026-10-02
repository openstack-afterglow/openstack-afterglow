<script lang="ts">
	import { t } from '$lib/i18n/ns/volume';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { Volume, VolumeBackup } from '$lib/types/volume';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
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

	let backups = $state<VolumeBackup[]>([]);
	let volumes = $state<Volume[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let deleting = $state<string | null>(null);
	let showModal = $state(false);
	let showRestoreModal = $state(false);
	let selectedBackup = $state<VolumeBackup | null>(null);
	let bulkBusy = $state(false);
	const selection = createResourceSelection();
	const selectableIds = $derived(new Set(backups.map((backup) => backup.id)));

	async function fetchBackups() {
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId;
		if (!projectId) return;
		try {
			const next = await api.get<VolumeBackup[]>('/api/v1/volumes/backups', token, projectId);
			if ($auth.projectId !== projectId) return;
			backups = next;
			error = '';
		} catch (e) {
			if ($auth.projectId === projectId) error = e instanceof ApiError ? t('backupsPage.fetchFailed', { status: e.status }) : t('backupsPage.serverError');
		} finally {
			if ($auth.projectId === projectId) loading = false;
		}
	}

	async function fetchVolumes() {
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId;
		if (!projectId) return;
		try {
			const next = await api.get<Volume[]>('/api/v1/volumes', token, projectId);
			if ($auth.projectId === projectId) volumes = next;
		} catch {
			if ($auth.projectId === projectId) volumes = [];
		}
	}

	function prefetchVolumes() {
		void api.prefetch('/api/v1/volumes', $auth.token ?? undefined, $auth.projectId ?? undefined);
	}

	function openCreate() {
		showModal = true;
		void fetchVolumes();
	}

	async function createBackup(form: { volume_id: string; name: string; description: string; incremental: boolean }): Promise<string | true> {
		try { await api.post('/api/v1/volumes/backups', form, $auth.token ?? undefined, $auth.projectId ?? undefined); await fetchBackups(); return true; }
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
	async function forceRefresh() { refreshing = true; try { await fetchBackups(); } finally { refreshing = false; } }
	const ar = createAutoRefresh(() => fetchBackups(), { storageKey: 'dashboard-volume-backups', defaultActive: true, defaultInterval: 15, intervalOptions: [10, 15, 30, 60], invokeOnMount: false });

	$effect(() => {
		const pid = $auth.projectId;
		untrack(() => {
			selection.clear();
			backups = [];
			volumes = [];
			error = '';
			selectedBackup = null;
			showModal = false;
			showRestoreModal = false;
			loading = Boolean(pid);
			if (pid) void fetchBackups();
		});
	});
	$effect(() => { const ids = selectableIds; untrack(() => selection.retain(ids)); });
</script>

<VolumeBackupCreateModal bind:open={showModal} {volumes} onCreate={createBackup} />
<VolumeBackupRestoreModal bind:open={showRestoreModal} backup={selectedBackup} onRestore={restoreBackup} />
<PageShell class="bulk-selection-page space-y-4">
	<PageHeader breadcrumb={t('backupsPage.breadcrumb')} title={t('backupsPage.title')}>
		{#snippet actions()}
			<Button onclick={openCreate} onintent={prefetchVolumes} variant="primary">{t('backupsPage.create')}</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label={t('backupsPage.toolbar')}>
		{#snippet actions()}<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing} onManualRefresh={forceRefresh} />{/snippet}
	</ResourceToolbar>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if loading}
		<LoadingSkeleton variant="table" rows={4} />
	{:else if backups.length === 0}
		<EmptyState headline={t('backupsPage.emptyTitle')} description={t('backupsPage.emptyDescription')} />
	{:else}
		<VolumeBackupListTable {backups} deletingId={deleting} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onRestore={(b) => { selectedBackup = b; showRestoreModal = true; }} onDelete={deleteBackup} />
		<BulkSelectionOverlay count={selection.count} ariaLabel={t('backupsPage.bulkLabel')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
	{/if}
</PageShell>
