<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { DbBackup, DbInstance, DbFlavor } from '$lib/types/database';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { Alert, EmptyState, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
	import DbBackupsTable from '$lib/components/database/DbBackupsTable.svelte';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import DbRestoreModal from '$lib/components/database/DbRestoreModal.svelte';
	let backups = $state<DbBackup[]>([]);
	let instances = $state<DbInstance[]>([]);
	let flavors = $state<DbFlavor[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let deleting = $state<string | null>(null);

	let showRestoreModal = $state(false);
	let selectedBackup = $state<DbBackup | null>(null);
	const selection = createResourceSelection();
	let bulkBusy = $state(false);
	const selectableIds = $derived(new Set(backups.map((backup) => backup.id)));
	const STUCK_MS = 6 * 3600 * 1000;
	function isStuck(backup: DbBackup): boolean {
		return backup.status === 'BUILDING' && (Date.now() - new Date(backup.created_at).getTime()) > STUCK_MS;
	}

	function clearBackupsState() {
		backups = [];
		instances = [];
		flavors = [];
		error = '';
		selection.clear();
		selectedBackup = null;
		showRestoreModal = false;
	}



	async function fetchBackups() {
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		try {
			const nextBackups = await api.get<DbBackup[]>('/api/v1/database-instances/backups', tokenSnapshot, projectSnapshot);
			if ($auth.projectId !== projectSnapshot) return;
			backups = nextBackups;
			selection.retain(nextBackups.map((backup) => backup.id));
			error = '';
		} catch (e) {
			if ($auth.projectId === projectSnapshot) error = e instanceof ApiError ? tr('errors.lookupStatus', { status: e.status }) : tr('errors.server');
		} finally {
			if ($auth.projectId === projectSnapshot) loading = false;
		}
	}

	async function fetchInstances() {
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		try {
			const nextInstances = await api.get<DbInstance[]>('/api/v1/database-instances', tokenSnapshot, projectSnapshot);
			if ($auth.projectId === projectSnapshot) instances = nextInstances;
		} catch { /* ignore */ }
	}

	function prefetchFlavors() {
		void api.prefetch('/api/v1/database-instances/flavors', $auth.token ?? undefined, $auth.projectId ?? undefined);
	}

	async function restoreBackup(backupId: string, name: string, flavorId: string, volumeSize: number) {
		await api.post('/api/v1/database-instances/restore', {
			backup_id: backupId, name, flavor_id: flavorId, volume_size: volumeSize,
		}, $auth.token ?? undefined, $auth.projectId ?? undefined);
		toast.success(tr('restore.started'));
		await fetchBackups();
	}

	async function deleteBackup(id: string, name: string, stuck: boolean) {
		if (!await confirmDialog(stuck ? tr('backups.deleteNamedStuck', { name: name || id.slice(0, 8) }) : tr('backups.deleteNamed', { name: name || id.slice(0, 8) }))) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/database-instances/backups/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchBackups();
		} catch (e) {
			toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = null;
		}
	}
	async function runBulkDelete() {
		const snapshot = [...selection.ids];
		if (snapshot.length === 0) return;
		const stuckCount = backups.filter((backup) => snapshot.includes(backup.id) && isStuck(backup)).length;
		if (!await confirmDialog(stuckCount > 0 ? tr('backups.bulkConfirmStuck', { count: snapshot.length, stuckCount }) : tr('backups.bulkConfirm', { count: snapshot.length }))) return;
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(snapshot, (id) => api.delete(`/api/v1/database-instances/backups/${id}`, tokenSnapshot, projectSnapshot));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length > 0) toast.success(tr('backups.bulkSuccess', { count: successful.length }));
			if (failed > 0) toast.error(tr('backups.bulkFailed', { count: failed }));
			if ($auth.projectId === projectSnapshot) {
				selection.remove(successful);
				await fetchBackups();
			}
		} finally {
			bulkBusy = false;
		}
	}

	const bulkActions: BulkSelectionAction[] = [
		{ key: 'delete', label: tr('actions.delete'), tone: 'danger', onAction: runBulkDelete },
	];

	async function forceRefresh() {
		refreshing = true;
		try {
			await fetchBackups();
		} finally {
			refreshing = false;
		}
	}

	const ar = createAutoRefresh(() => fetchBackups(), {
		storageKey: 'dashboard-db-backups',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		const pid = $auth.projectId;
		clearBackupsState();
		loading = Boolean(pid);
		if (!pid) return;
		untrack(() => {
			void fetchBackups();
			void fetchInstances();
			// Restore-only flavors remain lazy until restore intent.
		});
	});
</script>

<DbRestoreModal
	bind:open={showRestoreModal}
	backup={selectedBackup}
	{flavors}
	onRestore={restoreBackup}
	onClose={() => { showRestoreModal = false; }}
/>

<PageShell class="bulk-selection-page space-y-4">
	<PageHeader breadcrumb={tr('breadcrumbs.backups')} title={tr('backups.title')} />
	<ResourceToolbar label={tr('backups.toolbar')}>
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing}
				onManualRefresh={forceRefresh}
			/>
		{/snippet}
	</ResourceToolbar>

	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={4} />
	{:else if backups.length === 0}
		<EmptyState headline={tr('backups.listEmpty')} description={tr('backups.emptyHelp')} />
	{:else}
		<DbBackupsTable
			{backups}
			{instances}
			selectedIds={selection.ids}
			selectableIds={selectableIds}
			selectionDisabled={bulkBusy}
			{deleting}
			onToggleSelect={(id) => selection.toggle(id)}
			onToggleAll={() => selection.toggleAll(selectableIds)}
			onRestore={(backup) => { selectedBackup = backup; showRestoreModal = true; }}
			onRestoreIntent={prefetchFlavors}
			onDelete={deleteBackup}
		/>
		<BulkSelectionOverlay count={selection.count} ariaLabel={tr('backups.bulkLabel')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
	{/if}
</PageShell>
