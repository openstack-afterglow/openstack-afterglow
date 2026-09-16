<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { FileStorage, ShareSnapshot } from '$lib/types/fileStorage';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
	import SnapshotCreateModal from '$lib/components/file-storage/SnapshotCreateModal.svelte';
	import SnapshotListTable from '$lib/components/file-storage/SnapshotListTable.svelte';
	import SnapshotsEmptyState from '$lib/components/file-storage/SnapshotsEmptyState.svelte';
	import { toast } from '$lib/stores/toast';
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';

	let snapshots = $state<ShareSnapshot[]>([]);
	let fileStorages = $state<FileStorage[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let error = $state('');
	let showModal = $state(false);
	let bulkBusy = $state(false);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const enabled = $derived($betaFeatures.fileStorageSnapshots);
	const selection = createResourceSelection();
	const selectableIds = $derived(new Set(snapshots.map((snapshot) => snapshot.id)));
	const fileStorageSnapshotsEnabled = $derived($betaFeatures.fileStorageSnapshots);

	function clearState() {
		snapshots = [];
		fileStorages = [];
		error = '';
	}

	async function fetchSnapshots(opts?: { refresh?: boolean }) {
		if (!enabled) {
			clearState();
			loading = false;
			return;
		}
		try {
			snapshots = await api.get<ShareSnapshot[]>('/api/v1/share-snapshots', token, projectId, opts);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	function prefetchFileStorages() {
		void api.prefetch('/api/v1/file-storage', token, projectId);
	}

	async function openCreateModal() {
		if (!enabled) return;
		try {
			fileStorages = await api.get<FileStorage[]>('/api/v1/file-storage', token, projectId);
		} catch {
			fileStorages = [];
		}
		showModal = true;
	}

	async function createSnapshot(form: { share_id: string; name: string; description: string }): Promise<string | true> {
		if (!enabled) return '파일 스토리지 스냅샷은 베타 기능이 꺼져 있습니다.';
		try {
			await api.post('/api/v1/share-snapshots', { share_id: form.share_id, name: form.name, description: form.description || undefined }, token, projectId);
			await refresh.invalidate();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '생성 실패';
		}
	}

	async function deleteSnapshot(id: string, name: string) {
		if (!enabled || !await confirmDialog(`스냅샷 "${name || id.slice(0, 8)}"을 삭제하시겠습니까?`)) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/share-snapshots/${id}`, token, projectId);
			selection.remove([id]);
			await refresh.invalidate();
		} catch (e) {
			toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
		} finally {
			deleting = null;
		}
	}

	async function runBulkDelete() {
		const ids = [...selection.ids];
		if (!ids.length || !await confirmDialog(`선택한 스냅샷 ${ids.length}개를 삭제하시겠습니까?`)) return;
		const tokenSnapshot = token;
		const projectSnapshot = projectId;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/share-snapshots/${id}`, tokenSnapshot, projectSnapshot));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length) toast.success(`${successful.length}개 삭제 요청을 완료했습니다.`);
			if (failed) toast.error(`${failed}개 삭제에 실패했습니다.`);
			if ($auth.projectId === projectSnapshot) {
				selection.remove(successful);
				await refresh.invalidate();
			}
		} finally {
			bulkBusy = false;
		}
	}

	const bulkActions: BulkSelectionAction[] = [{ key: 'delete', label: '삭제', tone: 'danger', onAction: runBulkDelete }];
	const refresh = createCoalescedRefresh((force) => fetchSnapshots(force ? { refresh: true } : undefined));

	async function forceRefresh() {
		refreshing = true;
		try {
			await refresh.run(true);
		} finally {
			refreshing = false;
		}
	}

	const ar = createAutoRefresh(() => refresh.run(false), {
		storageKey: 'dashboard-file-storage-snapshots',
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
		invokeOnMount: false,
	});

	$effect(() => {
		if (!enabled) {
			clearState();
			selection.clear();
			loading = false;
			return;
		}
		if (!$auth.projectId) return;
		untrack(() => {
			selection.clear();
			void refresh.run(false);
		});
	});
	$effect(() => {
		const ids = selectableIds;
		untrack(() => selection.retain(ids));
	});
</script>

{#if !enabled}
	<div class="p-4 md:p-8"><BetaFeatureGate title="파일 스토리지 스냅샷은 베타 기능입니다" /></div>
{:else}
	<SnapshotCreateModal bind:open={showModal} {fileStorages} onCreate={createSnapshot} />
	<div class="bulk-selection-page p-4 md:p-8">
		<PageHeader breadcrumb="FILE STORAGE / SNAPSHOTS" title="스냅샷">
			{#snippet actions()}
				<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing || loading} onManualRefresh={forceRefresh} />
				<button onclick={openCreateModal} onpointerenter={prefetchFileStorages} onfocus={prefetchFileStorages} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ 스냅샷 생성</button>
			{/snippet}
		</PageHeader>
		{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
		{#if loading}
			<LoadingSkeleton variant="table" rows={4} />
		{:else if snapshots.length === 0}
			<SnapshotsEmptyState onCreate={openCreateModal} />
		{:else}
			<SnapshotListTable {snapshots} {deleting} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onDelete={deleteSnapshot} />
			<BulkSelectionOverlay count={selection.count} ariaLabel="선택한 파일 스토리지 스냅샷 일괄 작업" actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
		{/if}
	</div>
{/if}
