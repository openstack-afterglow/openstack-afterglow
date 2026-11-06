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
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
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
	import { createTableView } from '$lib/utils/tableView.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';

	let fileStorages = $state<AdminFileStorage[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let tsData = $state<TsPoint[]>([]);
	let tsRange = $state('7d');
	let tsLoading = $state(true);
	let pageSize = $state(20);
	let currentPage = $state(0);
	let selectedFileStorageId = $state<string | null>(null);
	let search = $state('');
	const view = createTableView<AdminFileStorage>({
		rows: () => fileStorages,
		search: () => search,
		searchable: (row) => [row.id, row.name, row.status, row.share_proto, row.metadata?.union_type ?? '', row.project_id ?? '', ...row.export_locations],
		columns: () => [
			{ key: 'name', label: t('fileTable.column.name'), value: (row) => row.name },
			{ key: 'status', label: t('fileTable.column.status'), value: (row) => row.status },
			{ key: 'size', label: t('fileTable.column.size'), value: (row) => row.size },
			{ key: 'protocol', label: t('fileTable.column.protocol'), value: (row) => row.share_proto },
			{ key: 'type', label: t('fileTable.column.type'), value: (row) => row.metadata?.union_type },
			{ key: 'project', label: t('fileTable.column.project'), value: (row) => row.project_id ? ($projectNames.get(row.project_id) ?? row.project_id) : null },
			{ key: 'created', label: t('fileTable.column.createdAt'), value: (row) => row.created_at },
			{ key: 'export', label: t('fileTable.column.exportPath'), value: (row) => row.export_locations.join(', ') },
		],
	});
	$effect(() => { void search; void view.filters; void view.sort; currentPage = 0; });
	$effect(() => { if (currentPage >= totalPages) currentPage = Math.max(0, totalPages - 1); });

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	const totalPages = $derived(Math.max(1, Math.ceil(view.rows.length / pageSize)));
	const displayedStorages = $derived(
		view.rows.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
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

	<RegexSearch id="admin-file-storage-search" bind:value={search} />
	<TableViewControls {view} class={loading || inventoryError ? '' : 'lg:hidden'} />
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
		<LoadingState variant="surface" />
	{:else}
		{#if view.rows.length === 0}<div class="text-ink-2 text-sm">{t('filePage.empty')}</div>{/if}
			<AdminFileStorageTable storages={displayedStorages} {view} selectedId={selectedFileStorageId} onOpen={openDetail} />
			{#if totalPages > 1}
				<Pagination
					page={currentPage + 1}
					{totalPages}
					total={view.rows.length}
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
