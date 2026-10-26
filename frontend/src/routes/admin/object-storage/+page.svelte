<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t as scopeT } from '$lib/i18n/ns/domain-admin';
	let inventoryError = $state('');
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/object-storage';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi, ApiError } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	import type { SwiftContainer } from '$lib/types/common';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { formatStorage } from '$lib/utils/format';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import BucketCreateModal from '$lib/components/object-storage/buckets/BucketCreateModal.svelte';
	import BucketTable from '$lib/components/object-storage/buckets/BucketTable.svelte';
	import QuarantineNotice from '$lib/components/object-storage/buckets/QuarantineNotice.svelte';
	import TrashNotice from '$lib/components/object-storage/buckets/TrashNotice.svelte';
	import { toast } from '$lib/stores/toast';
	import { createArrivals } from '$lib/components/object-storage/arrivals';

	interface AccountMeta {
		container_count: number;
		object_count: number;
		bytes_used: number;
	}

	interface UnavailableAccount { project_id: string; project_name: string; reason: 'denied' | 'failed' }
	interface AdminSwiftInventory { items: SwiftContainer[]; project_count: number; partial: boolean; unavailable_projects: UnavailableAccount[] }
	let unavailableAccounts = $state<UnavailableAccount[]>([]);
	let queriedProjects = $state(0);
	let partial = $state(false);

	let containers = $state<SwiftContainer[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let showModal = $state(false);
	const bucketArrivals = createArrivals();

	const account = $derived<AccountMeta>({
		container_count: containers.length,
		object_count: containers.reduce((s, c) => s + (c.count || 0), 0),
		bytes_used: containers.reduce((s, c) => s + (c.bytes || 0), 0),
	});

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load(force = false) {
		if (containers.length === 0) loading = true;
		else refreshing = true;
		inventoryError = '';
		try {
			const result = await api.get<AdminSwiftInventory>(
				'/api/v1/admin/object-storage?include_quarantine=true&include_trash=true&include_deleted=true',
				token, projectId, { refresh: force }
			);
			containers = result.items;
			unavailableAccounts = result.unavailable_projects;
			queriedProjects = result.project_count;
			partial = result.partial;
		} catch (reason) {
			containers = []; unavailableAccounts = []; partial = false;
			inventoryError = reason instanceof Error ? reason.message : scopeT('state.unavailable');
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function createContainer(name: string): Promise<string | true> {
		try {
			if (!projectId) return t('buckets.adminPage.projectActionsOnly');
			await api.post('/api/v1/object-storage', { name }, token, projectId);
			await load();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : t('buckets.adminPage.createFailed');
		}
	}

	function canDelete(container: SwiftContainer) {
		return !!projectId && container.project_id === projectId;
	}

	async function deleteContainer(container: SwiftContainer) {
		if (!canDelete(container)) return;
		const owner = container.project_id;
		const name = container.name;
		if (!await confirmDialog(t('buckets.adminPage.deleteConfirm', { name }))) return;
		if (!canDelete(container)) return;
		deleting = `${owner}/${name}`;
		try {
			await api.delete(`/api/v1/object-storage/${encodeURIComponent(name)}`, token, owner);
			await load();
		} catch (e) {
			if (!api.isCurrent()) return;
			toast.error(t('buckets.adminPage.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = null;
		}
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-object-storage',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	onMount(load);
</script>

<BucketCreateModal bind:open={showModal} onCreate={createContainer} />

<PageShell>
	<PageHeader breadcrumb={t('buckets.adminPage.breadcrumb')} title={t('buckets.adminPage.title')}>
		{#snippet actions()}
			<button
				onclick={() => { showModal = true; }}
				disabled={!projectId}
				class="text-xs text-ink-0 bg-indigo-600 hover:bg-indigo-500 transition-colors px-3 py-1.5 rounded border border-indigo-500"
			>{t('buckets.adminPage.create')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={ar.refresh}
			/>
		{/snippet}
	</PageHeader>

	{#if account && !loading && !inventoryError && !partial}
		<div class="grid grid-cols-3 gap-4 mb-6" data-testid="inventory-totals">
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<div class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('buckets.adminPage.bucketCount')}</div>
				<div class="text-2xl font-bold text-ink-0">{account.container_count}</div>
			</div>
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<div class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('buckets.adminPage.objectCount')}</div>
				<div class="text-2xl font-bold text-ink-0">{account.object_count}</div>
			</div>
			<div class="bg-surface-base border border-line rounded-xl p-4">
				<div class="text-xs text-ink-2 uppercase tracking-wide mb-1">{t('buckets.adminPage.usage')}</div>
				<div class="text-2xl font-bold text-ink-0">{formatStorage(account.bytes_used / 1_000_000_000)}</div>
			</div>
		</div>
	{/if}

	<Alert tone="info">{t('buckets.adminPage.projectActionsOnly')}</Alert>
	{#if partial}
		<Alert tone="warning" class="mt-3">{t('buckets.adminPage.partial', { unavailable: unavailableAccounts.length, total: queriedProjects })}</Alert>
		<details class="my-3 rounded-lg border border-line p-3">
			<summary class="cursor-pointer text-sm text-ink-1">{t('buckets.adminPage.unavailableAccounts')}</summary>
			<ul class="mt-3 max-h-64 space-y-2 overflow-y-auto text-sm text-ink-2">
				{#each unavailableAccounts as account (account.project_id)}
					<li class="break-words">{account.project_name} · <code class="break-all">{account.project_id}</code> · {t(`buckets.adminPage.accountReason.${account.reason}`)}</li>
				{/each}
			</ul>
		</details>
	{/if}

	{#if inventoryError}<Alert tone="danger">{inventoryError}</Alert>
	{:else if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if containers.length === 0}
		<div class="text-ink-2 text-sm">{partial ? t('buckets.adminPage.partialEmpty') : t('buckets.adminPage.empty')}</div>
	{:else}
		<BucketTable {containers} arrivals={bucketArrivals} deletingId={deleting} {refreshing} {canDelete} onDelete={deleteContainer} />
		{#if containers.some((c) => c.is_quarantine)}
			<QuarantineNotice />
		{/if}
		{#if containers.some((c) => c.is_trash || c.is_deleted)}
			<TrashNotice />
		{/if}
	{/if}
</PageShell>
