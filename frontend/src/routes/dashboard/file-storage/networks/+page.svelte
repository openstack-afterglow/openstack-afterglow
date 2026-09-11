<script lang="ts">
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
	import type { ShareNetwork } from '$lib/types/shareNetwork';
	import ShareNetworkCreateModal from '$lib/components/dashboard/file-storage/networks/ShareNetworkCreateModal.svelte';
	import ShareNetworkTable from '$lib/components/dashboard/file-storage/networks/ShareNetworkTable.svelte';
	import { toast } from '$lib/stores/toast';
	import { betaFeatures } from '$lib/stores/betaFeatures';
	import BetaFeatureGate from '$lib/components/ui/BetaFeatureGate.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';

	let networks = $state<ShareNetwork[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let error = $state('');
	let showModal = $state(false);
	let creating = $state(false);
	let bulkBusy = $state(false);
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const enabled = $derived($betaFeatures.fileStorageShareNetworks);
	const shareNetworksEnabled = $derived($betaFeatures.fileStorageShareNetworks);
	const selection = createResourceSelection();
	const selectableIds = $derived(new Set(networks.map((network) => network.id)));

	function clearState() {
		networks = [];
		error = '';
	}

	async function fetchNetworks(opts?: { refresh?: boolean }) {
		if (!enabled) {
			clearState();
			loading = false;
			return;
		}
		try {
			networks = await api.get<ShareNetwork[]>('/api/v1/share-networks', token, projectId, opts);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function createNetwork(form: { name: string; description: string; neutron_net_id: string; neutron_subnet_id: string }): Promise<boolean> {
		if (!enabled) return false;
		creating = true;
		try {
			await api.post('/api/v1/share-networks', form, token, projectId);
			await refresh.invalidate();
			return true;
		} finally {
			creating = false;
		}
	}

	async function deleteNetwork(id: string, name: string) {
		if (!enabled || !await confirmDialog(`Share 네트워크 "${name || id.slice(0, 8)}"을 삭제하시겠습니까?\n이 네트워크를 사용 중인 파일 스토리지가 있으면 삭제할 수 없습니다.`)) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/share-networks/${id}`, token, projectId);
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
		if (!ids.length || !await confirmDialog(`선택한 Share 네트워크 ${ids.length}개를 삭제하시겠습니까?\n사용 중인 파일 스토리지가 있으면 삭제할 수 없습니다.`)) return;
		const tokenSnapshot = token;
		const projectSnapshot = projectId;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/share-networks/${id}`, tokenSnapshot, projectSnapshot));
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
	const refresh = createCoalescedRefresh((force) => fetchNetworks(force ? { refresh: true } : undefined));
	async function forceRefresh() {
		refreshing = true;
		try {
			await refresh.run(true);
		} finally {
			refreshing = false;
		}
	}
	const ar = createAutoRefresh(() => refresh.run(false), {
		storageKey: 'dashboard-file-storage-networks',
		defaultActive: true,
		defaultInterval: 30,
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
	<div class="p-4 md:p-8"><BetaFeatureGate title="Share 네트워크는 베타 기능입니다" /></div>
{:else}
	<ShareNetworkCreateModal bind:open={showModal} {creating} {token} {projectId} onCreate={createNetwork} />
	<div class="bulk-selection-page p-4 md:p-8">
		<PageHeader breadcrumb="FILE STORAGE / NETWORKS" title="Share 네트워크">
			{#snippet actions()}
				<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing || loading} onManualRefresh={forceRefresh} />
				<button onclick={() => showModal = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ Share 네트워크 생성</button>
			{/snippet}
		</PageHeader>
		<p class="text-sm text-ink-3 mb-6">파일 스토리지를 Neutron 네트워크에 연결하는 Share Network를 관리합니다.</p>
		{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
		{#if loading}
			<LoadingSkeleton variant="table" rows={4} />
		{:else if networks.length === 0}
			<div class="text-center py-20 text-ink-3"><p class="text-lg">Share 네트워크가 없습니다</p></div>
		{:else}
			<ShareNetworkTable {networks} {deleting} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onDelete={deleteNetwork} />
			<BulkSelectionOverlay count={selection.count} ariaLabel="선택한 Share 네트워크 일괄 작업" actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
		{/if}
	</div>
{/if}
