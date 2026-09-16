<script lang="ts">
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
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
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
	const volumeBackupsEnabled = $derived($betaFeatures.volumeBackups);

	function clearBackupsState() {
		backups = [];
		volumes = [];
		error = '';
	}

	async function fetchBackups() {
		if (!volumeBackupsEnabled) { clearBackupsState(); loading = false; return; }
		try {
			backups = await api.get<VolumeBackup[]>('/api/v1/volumes/backups', $auth.token ?? undefined, $auth.projectId ?? undefined);
			error = '';
		} catch (e) { error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류'; }
		finally { loading = false; }
	}

	async function fetchVolumes() {
		if (!volumeBackupsEnabled) { volumes = []; return; }
		try { volumes = await api.get<Volume[]>('/api/v1/volumes', $auth.token ?? undefined, $auth.projectId ?? undefined); } catch { volumes = []; }
	}

	function prefetchVolumes() {
		if (!volumeBackupsEnabled) return;
		void api.prefetch('/api/v1/volumes', $auth.token ?? undefined, $auth.projectId ?? undefined);
	}

	function openCreate() {
		showModal = true;
		void fetchVolumes();
	}

	async function createBackup(form: { volume_id: string; name: string; description: string; incremental: boolean }): Promise<string | true> {
		if (!volumeBackupsEnabled) return '볼륨 백업 베타 기능이 꺼져 있습니다.';
		try { await api.post('/api/v1/volumes/backups', form, $auth.token ?? undefined, $auth.projectId ?? undefined); await fetchBackups(); return true; }
		catch (e) { return e instanceof ApiError ? e.message : '생성 실패'; }
	}

	async function restoreBackup(backupId: string): Promise<{ volume_id: string; volume_name: string } | string> {
		if (!volumeBackupsEnabled) return '볼륨 백업 베타 기능이 꺼져 있습니다.';
		try { return await api.post<{ volume_id: string; volume_name: string }>(`/api/v1/volumes/backups/${backupId}/restore`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined); }
		catch (e) { return e instanceof ApiError ? e.message : '복원 실패'; }
	}

	async function deleteBackup(id: string, name: string) {
		if (!volumeBackupsEnabled || !await confirmDialog(`백업 "${name || id.slice(0, 8)}"을 삭제하시겠습니까?`)) return;
		deleting = id;
		try { await api.delete(`/api/v1/volumes/backups/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined); selection.remove([id]); await fetchBackups(); }
		catch (e) { toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e))); }
		finally { deleting = null; }
	}

	async function runBulkDelete() {
		const ids = [...selection.ids];
		if (!ids.length || !await confirmDialog(`선택한 백업 ${ids.length}개를 삭제하시겠습니까?`)) return;
		const token = $auth.token ?? undefined; const projectId = $auth.projectId ?? undefined;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/volumes/backups/${id}`, token, projectId));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length) toast.success(`${successful.length}개 삭제 요청을 완료했습니다.`);
			if (failed) toast.error(`${failed}개 삭제에 실패했습니다.`);
			if ($auth.projectId === projectId) { selection.remove(successful); await fetchBackups(); }
		} finally { bulkBusy = false; }
	}

	const bulkActions: BulkSelectionAction[] = [{ key: 'delete', label: '삭제', tone: 'danger', onAction: runBulkDelete }];
	async function forceRefresh() { refreshing = true; try { await fetchBackups(); } finally { refreshing = false; } }
	const ar = createAutoRefresh(() => fetchBackups(), { storageKey: 'dashboard-volume-backups', defaultActive: true, defaultInterval: 15, intervalOptions: [10, 15, 30, 60], invokeOnMount: false });

	$effect(() => {
		const pid = $auth.projectId;
		if (!volumeBackupsEnabled) { clearBackupsState(); selection.clear(); loading = false; return; }
		if (!pid) return;
		untrack(() => { selection.clear(); fetchBackups(); });
	});
	$effect(() => { const ids = selectableIds; untrack(() => selection.retain(ids)); });
</script>

{#if !volumeBackupsEnabled}
	<PageShell><BetaFeatureGate title="볼륨 백업은 베타 기능입니다" /></PageShell>
{:else}
	<VolumeBackupCreateModal bind:open={showModal} {volumes} onCreate={createBackup} />
	<VolumeBackupRestoreModal bind:open={showRestoreModal} backup={selectedBackup} onRestore={restoreBackup} />
	<PageShell class="bulk-selection-page space-y-4">
		<PageHeader breadcrumb="VOLUMES / BACKUPS" title="볼륨 백업">
			{#snippet actions()}
				<Button onclick={openCreate} onintent={prefetchVolumes} variant="primary">+ 백업 생성</Button>
			{/snippet}
		</PageHeader>
		<ResourceToolbar label="볼륨 백업 목록 도구">
			{#snippet actions()}<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing} onManualRefresh={forceRefresh} />{/snippet}
		</ResourceToolbar>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if loading}
			<LoadingSkeleton variant="table" rows={4} />
		{:else if backups.length === 0}
			<EmptyState headline="볼륨 백업이 없습니다" description="필요한 볼륨의 복구 지점을 생성하세요." />
		{:else}
			<VolumeBackupListTable {backups} deletingId={deleting} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onRestore={(b) => { selectedBackup = b; showRestoreModal = true; }} onDelete={deleteBackup} />
			<BulkSelectionOverlay count={selection.count} ariaLabel="선택한 볼륨 백업 일괄 작업" actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
		{/if}
	</PageShell>
{/if}
