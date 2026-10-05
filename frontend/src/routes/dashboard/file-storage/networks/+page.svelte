<script lang="ts">
	import { t } from '$lib/i18n/ns/file-storage';
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
			error = e instanceof ApiError ? t('errors.loadWithStatus', { status: e.status }) : t('errors.server');
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
		if (!enabled || !await confirmDialog(t('networks.deleteConfirm', { name: name || id.slice(0, 8) }))) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/share-networks/${id}`, token, projectId);
			selection.remove([id]);
			await refresh.invalidate();
		} catch (e) {
			toast.error(t('errors.deleteWithMessage', { message: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = null;
		}
	}

	async function runBulkDelete() {
		const ids = [...selection.ids];
		if (!ids.length || !await confirmDialog(t('networks.bulkDeleteConfirm', { count: ids.length }))) return;
		const tokenSnapshot = token;
		const projectSnapshot = projectId;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/share-networks/${id}`, tokenSnapshot, projectSnapshot));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length) toast.success(t('bulk.deleteSuccess', { count: successful.length }));
			if (failed) toast.error(t('bulk.deleteFailed', { count: failed }));
			if ($auth.projectId === projectSnapshot) {
				selection.remove(successful);
				await refresh.invalidate();
			}
		} finally {
			bulkBusy = false;
		}
	}

	const bulkActions = $derived<BulkSelectionAction[]>([{ key: 'delete', label: t('actions.delete'), tone: 'danger', onAction: runBulkDelete }]);
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
	<div class="p-4 md:p-8"><BetaFeatureGate title={t('networks.beta')} /></div>
{:else}
	<ShareNetworkCreateModal bind:open={showModal} {creating} {token} {projectId} onCreate={createNetwork} />
	<div class="bulk-selection-page p-4 md:p-8">
		<PageHeader breadcrumb={t('networks.breadcrumb')} title={t('networks.title')}>
			{#snippet actions()}
				<AutoRefreshControl bind:active={ar.active} bind:intervalSeconds={ar.intervalSeconds} intervalOptions={ar.intervalOptions} refreshing={refreshing || loading} onManualRefresh={forceRefresh} />
				<button onclick={() => showModal = true} class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">{t('networks.create')}</button>
			{/snippet}
		</PageHeader>
		<p class="text-sm text-ink-2 mb-6">{t('networks.description')}</p>
		{#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
		{#if loading}
			<LoadingSkeleton variant="table" rows={4} />
		{:else if networks.length === 0}
			<div class="text-center py-20 text-ink-2"><p class="text-lg">{t('networks.empty')}</p></div>
		{:else}
			<ShareNetworkTable {networks} {deleting} selectedIds={selection.ids} selectableIds={selectableIds} selectionDisabled={bulkBusy} onToggleSelect={(id) => selection.toggle(id)} onToggleAll={() => selection.toggleAll(selectableIds)} onDelete={deleteNetwork} />
			<BulkSelectionOverlay count={selection.count} ariaLabel={t('networks.bulkActions')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
		{/if}
	</div>
{/if}
