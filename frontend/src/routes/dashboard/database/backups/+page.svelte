<script lang="ts">
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
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
	let backups = $state<DbBackup[]>([]);
	let instances = $state<DbInstance[]>([]);
	let flavors = $state<DbFlavor[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let deleting = $state<string | null>(null);

	let showRestoreModal = $state(false);
	let selectedBackup = $state<DbBackup | null>(null);
	const databaseBackupsEnabled = $derived($betaFeatures.databaseBackups);
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
		if (!databaseBackupsEnabled) {
			clearBackupsState();
			loading = false;
			return;
		}
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		try {
			const nextBackups = await api.get<DbBackup[]>('/api/v1/database-instances/backups', tokenSnapshot, projectSnapshot);
			if (!databaseBackupsEnabled || $auth.projectId !== projectSnapshot) return;
			backups = nextBackups;
			selection.retain(nextBackups.map((backup) => backup.id));
			error = '';
		} catch (e) {
			if ($auth.projectId === projectSnapshot) error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			if ($auth.projectId === projectSnapshot) loading = false;
		}
	}

	async function fetchInstances() {
		if (!databaseBackupsEnabled) {
			instances = [];
			return;
		}
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		try {
			const nextInstances = await api.get<DbInstance[]>('/api/v1/database-instances', tokenSnapshot, projectSnapshot);
			if ($auth.projectId === projectSnapshot) instances = nextInstances;
		} catch { /* ignore */ }
	}

	async function fetchFlavors() {
		if (!databaseBackupsEnabled) {
			flavors = [];
			return;
		}
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		try {
			const nextFlavors = await api.get<DbFlavor[]>('/api/v1/database-instances/flavors', tokenSnapshot, projectSnapshot);
			if ($auth.projectId === projectSnapshot) flavors = nextFlavors;
		} catch { /* ignore */ }
	}

	function prefetchFlavors() {
		if (!databaseBackupsEnabled) return;
		void api.prefetch('/api/v1/database-instances/flavors', $auth.token ?? undefined, $auth.projectId ?? undefined);
	}

	async function restoreBackup(backupId: string, name: string, flavorId: string, volumeSize: number) {
		if (!databaseBackupsEnabled) return;
		await api.post('/api/v1/database-instances/restore', {
			backup_id: backupId, name, flavor_id: flavorId, volume_size: volumeSize,
		}, $auth.token ?? undefined, $auth.projectId ?? undefined);
		toast.success('복원 인스턴스 생성이 시작되었습니다.');
		await fetchBackups();
	}

	async function deleteBackup(id: string, name: string, stuck: boolean) {
		if (!databaseBackupsEnabled) return;
		const baseMsg = `백업 "${name || id.slice(0, 8)}"을 삭제하시겠습니까?`;
		const stuckNote = stuck
			? '\n\nTrove 백업 레코드만 제거됩니다. Swift에 저장된 데이터는 이미 없을 수 있습니다.'
			: '';
		if (!await confirmDialog(baseMsg + stuckNote)) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/database-instances/backups/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
			await fetchBackups();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deleting = null;
		}
	}
	async function runBulkDelete() {
		if (!databaseBackupsEnabled) return;
		const snapshot = [...selection.ids];
		if (snapshot.length === 0) return;
		const stuckCount = backups.filter((backup) => snapshot.includes(backup.id) && isStuck(backup)).length;
		const stuckNote = stuckCount > 0 ? `\n\n${stuckCount}개 멈춤 백업은 Trove 레코드만 제거되며 Swift 데이터는 이미 없을 수 있습니다.` : '';
		if (!await confirmDialog(`선택한 백업 ${snapshot.length}개를 삭제하시겠습니까?${stuckNote}`)) return;
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(snapshot, (id) => api.delete(`/api/v1/database-instances/backups/${id}`, tokenSnapshot, projectSnapshot));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length > 0) toast.success(`${successful.length}개 삭제 요청을 완료했습니다.`);
			if (failed > 0) toast.error(`${failed}개 삭제에 실패했습니다.`);
			if ($auth.projectId === projectSnapshot) {
				selection.remove(successful);
				await fetchBackups();
			}
		} finally {
			bulkBusy = false;
		}
	}

	const bulkActions: BulkSelectionAction[] = [
		{ key: 'delete', label: '삭제', tone: 'danger', onAction: runBulkDelete },
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
		if (!databaseBackupsEnabled) {
			clearBackupsState();
			loading = false;
			return;
		}
		if (!pid) return;
		clearBackupsState();
		loading = true;
		untrack(() => {
			fetchBackups();
			fetchInstances();
			// Restore-only flavors remain lazy until restore intent.
		});
	});
</script>

{#if !databaseBackupsEnabled}
	<PageShell>
		<BetaFeatureGate title="DB 백업은 베타 기능입니다" />
	</PageShell>
{:else}
<DbRestoreModal
	bind:open={showRestoreModal}
	backup={selectedBackup}
	{flavors}
	onRestore={restoreBackup}
	onClose={() => { showRestoreModal = false; }}
/>

<PageShell class="bulk-selection-page space-y-4">
	<PageHeader breadcrumb="DATABASE / BACKUPS" title="DB 백업" />
	<ResourceToolbar label="데이터베이스 백업 목록 도구">
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
		<EmptyState headline="DB 백업이 없습니다" description="데이터베이스 인스턴스에서 백업을 생성하면 여기에 표시됩니다." />
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
		<BulkSelectionOverlay count={selection.count} ariaLabel="선택한 DB 백업 일괄 작업" actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
	{/if}
</PageShell>
{/if}
