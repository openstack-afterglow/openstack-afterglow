<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t as scopeT } from '$lib/i18n/ns/domain-admin';
	let inventoryError = $state('');
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	import type { TsPoint } from '$lib/types/common';
	import type { AdminFileStorage } from '$lib/types/fileStorage';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import AdminFileStorageTimeseries from '$lib/components/admin/file-storage/AdminFileStorageTimeseries.svelte';
	import AdminFileStorageTable from '$lib/components/admin/file-storage/AdminFileStorageTable.svelte';
	import Pagination from '$lib/components/ui/Pagination.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import AdminFileStorageDetailPanel from '$lib/components/admin/file-storage/AdminFileStorageDetailPanel.svelte';
	import { t } from '$lib/i18n/ns/admin-storage';

	let fileStorages = $state<AdminFileStorage[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let tsData = $state<TsPoint[]>([]);
	let tsRange = $state('7d');
	let tsLoading = $state(true);
	let pageSize = $state(20);
	let currentPage = $state(0);
	let selectedFileStorageId = $state<string | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	const totalPages = $derived(Math.ceil(fileStorages.length / pageSize));
	const displayedStorages = $derived(
		fileStorages.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
	);

	async function loadTimeseries(range: string, opts?: { background?: boolean; refresh?: boolean }) {
		if (!opts?.background) tsLoading = true;
		try {
			tsData = await api.get<TsPoint[]>(
				`/api/v1/admin/timeseries/file_storage?range=${range}`,
				token,
				projectId,
				opts?.refresh ? { refresh: true } : undefined
			);
		} catch {
			if (!opts?.background) tsData = [];
		} finally {
			if (!opts?.background) tsLoading = false;
		}
	}

	async function load(opts?: { refresh?: boolean }) {
		if (fileStorages.length === 0) loading = true;
		else refreshing = true;
		currentPage = 0;
		inventoryError = '';
		try {
			fileStorages = await api.get<AdminFileStorage[]>('/api/v1/admin/all-file-storages', token, projectId, opts);
		} catch (reason) {
			fileStorages = []; inventoryError = reason instanceof Error ? reason.message : scopeT('state.unavailable');
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	function openDetail(fs: AdminFileStorage) {
		selectedFileStorageId = fs.id;
	}

	function closeDetail() {
		selectedFileStorageId = null;
	}

	async function handleDeleted() {
		closeDetail();
		await refresh.invalidate();
	}

	const refresh = createCoalescedRefresh(async (force) => {
		if (selectedFileStorageId && !force) return;
		await Promise.allSettled([
			load(force ? { refresh: true } : undefined),
			loadTimeseries(tsRange, { background: true, refresh: force }),
		]);
	});

	$effect(() => () => refresh.dispose());
	const ar = createAutoRefresh(
		() => refresh.run(false),
		{ storageKey: 'admin-file-storage', defaultInterval: 30, intervalOptions: [15, 30, 60], invokeOnMount: false }
	);

	onMount(() => {
		void refresh.run();
		void projectNames.load(token, projectId);
	});
</script>

<PageShell>
	<PageHeader breadcrumb={t('filePage.breadcrumb')} title={t('filePage.title')}>
		{#snippet actions()}
			<select
				bind:value={pageSize}
				onchange={() => { currentPage = 0; }}
				class="text-xs bg-surface-sunken border border-line-2 text-ink-2 rounded px-2 py-1.5"
			>
				{#each [10, 20, 30, 50] as s}
					<option value={s}>{t('filePage.pageSize', { count: s })}</option>
				{/each}
			</select>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={() => refresh.run(true)}
			/>
		{/snippet}
	</PageHeader>

	{#if !api.scoped}
	<div class="mb-6">
		<AdminFileStorageTimeseries
			data={tsData}
			loading={tsLoading}
			range={tsRange}
			onRangeChange={(r) => { tsRange = r; loadTimeseries(r); }}
		/>
	</div>
	{/if}

	{#if inventoryError}<Alert tone="danger">{inventoryError}</Alert>
	{:else if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if fileStorages.length === 0}
		<div class="text-ink-2 text-sm">{t('filePage.empty')}</div>
	{:else}
			<AdminFileStorageTable storages={displayedStorages} selectedId={selectedFileStorageId} onOpen={openDetail} />
			{#if totalPages > 1}
				<Pagination
					page={currentPage + 1}
					{totalPages}
					total={fileStorages.length}
					{pageSize}
					hasPrev={currentPage > 0}
					hasNext={currentPage < totalPages - 1}
					onPrev={() => { currentPage--; }}
					onNext={() => { currentPage++; }}
				/>
			{/if}
	{/if}
</PageShell>

{#if selectedFileStorageId}
	<SlidePanel onClose={closeDetail} ariaLabel={t('filePage.detailAriaLabel')} width="w-full md:w-[60vw] max-w-4xl" storageKey="admin.fileStorage.detail.width">
		<AdminFileStorageDetailPanel fileStorageId={selectedFileStorageId} onClose={closeDetail} onDeleted={handleDeleted} />
	</SlidePanel>
{/if}
