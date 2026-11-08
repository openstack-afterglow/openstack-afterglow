<script lang="ts">
 import { authDisplayContext } from '$lib/stores/authDisplayContext';
 import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
 import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
 import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

	import { t as tl } from '$lib/i18n/ns/common';
	import { t } from '$lib/i18n/ns/object-storage';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { SwiftContainer, AccountMeta } from '$lib/types/objectStorage';
	import { Alert, Button, EmptyState, PageHeader, PageShell, ResourceToolbar, StatTile } from '$lib/components/ui';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import BucketCreateDialog from '$lib/components/object-storage/BucketCreateDialog.svelte';
	import BucketCardGrid from '$lib/components/object-storage/BucketCardGrid.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import { toast } from '$lib/stores/toast';
	import { createArrivals } from '$lib/components/object-storage/arrivals';

	let containers = $state<SwiftContainer[]>([]);
	let deletedContainers = $state<SwiftContainer[]>([]);
 let search = $state('');
 let trashSearch = $state('');
 const columns = $derived<TableColumn<SwiftContainer>[]>([
  { key: 'name', label: t('buckets.table.name'), value: row => row.name },
  { key: 'count', label: t('buckets.table.objectCount'), value: row => row.count },
  { key: 'bytes', label: t('buckets.table.capacity'), value: row => row.bytes },
 ]);
 const view = createTableView({ locale: intlLocale,rows: () => containers, columns: () => columns, search: () => search, searchable: row => row.name});
 const trashView = createTableView({ locale: intlLocale,rows: () => deletedContainers, columns: () => columns, search: () => trashSearch, searchable: row => row.name});
 $effect(() => { const names = selectionDomain === 'active' ? view.rows.map(row=>row.name) : trashView.rows.map(row=>row.name); untrack(() => selection.retain(names)); });
	let account = $state<AccountMeta | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let inventoryLoaded = $state(false);
	let trashLoading = $state(true);
	let activeError = $state('');
	let trashError = $state('');
	let accountLoading = $state(true);
	let accountError = $state('');
	let loadGeneration = 0;
	let deleting = $state<string | null>(null);
	let restoring = $state<string | null>(null);
	let showModal = $state(false);
	let busy = $state(false);
	let selectionDomain = $state<'active' | 'trash'>('active');
	let lastCreated = $state<string | null>(null);
	const selection = createResourceSelection();
	// Trash rows fade in on first arrival only; auto-refresh keeps the keyed list mounted.
	const trashArrivals = createArrivals();
	const bucketArrivals = createArrivals();
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	function setSelectionDomain(domain: 'active' | 'trash') {
		if (selectionDomain !== domain) selection.clear();
		selectionDomain = domain;
	}

	function retainSelection() {
		selection.retain(selectionDomain === 'active'
			? view.rows.map((c) => c.name)
			: trashView.rows.map((c) => c.name));
	}

	async function load(refresh = false) {
		const requestToken = token;
		const requestProject = projectId;
		const generation = ++loadGeneration;
		const owns = () => generation === loadGeneration && token === requestToken && projectId === requestProject;
		if (!inventoryLoaded) loading = true;
		else refreshing = true;
		trashLoading = true;
		activeError = '';
		trashError = '';
		accountLoading = true;
		accountError = '';
		const opts = refresh ? { refresh: true } : undefined;
		const activePromise = api.get<SwiftContainer[]>('/api/v1/object-storage', requestToken, requestProject, opts)
			.then((value) => {
				if (!owns()) return;
				containers = value;
				inventoryLoaded = true;
				retainSelection();
			})
			.catch((loadError) => {
				if (!owns()) return;
				activeError = loadError instanceof Error ? loadError.message : t('buckets.dashboardPage.loadFailed');
			})
			.finally(() => {
				if (owns()) loading = false;
			});
		const trashPromise = api.get<SwiftContainer[]>('/api/v1/object-storage/trash/containers', requestToken, requestProject, opts)
			.then((value) => {
				if (!owns()) return;
				deletedContainers = value;
				retainSelection();
			})
			.catch((loadError) => {
				if (!owns()) return;
				trashError = loadError instanceof Error ? loadError.message : t('buckets.dashboardPage.trashLoadFailed');
			})
			.finally(() => {
				if (owns()) trashLoading = false;
			});
		const accountPromise = api.get<AccountMeta>('/api/v1/object-storage/account', requestToken, requestProject, opts)
			.then((value) => {
				if (owns()) account = value;
			})
			.catch((loadError) => {
				if (!owns()) return;
				accountError = loadError instanceof Error ? loadError.message : t('buckets.dashboardPage.accountLoadFailed');
			})
			.finally(() => {
				if (owns()) accountLoading = false;
			});
		await Promise.allSettled([activePromise, trashPromise, accountPromise]);
		if (owns()) refreshing = false;
	}

	async function forceRefresh() {
		await load(true);
	}

	function formatAccountBytes(bytes: number): string {
		if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
		if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
		if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
		return `${bytes} B`;
	}

	async function createContainer(name: string): Promise<string | true> {
		try {
			await api.post('/api/v1/object-storage', { name }, token, projectId);
			lastCreated = name;
			await load(true);
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : t('buckets.dashboardPage.createFailed');
		}
	}

	async function deleteContainer(name: string) {
		if (!await confirmDialog(t('buckets.dashboardPage.deleteConfirm', { name }))) return;
		deleting = name;
		try {
			await api.delete(`/api/v1/object-storage/${encodeURIComponent(name)}`, token, projectId);
			await load(true);
		} catch (e) {
			toast.error(t('buckets.dashboardPage.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = null;
		}
	}

	async function restoreContainer(name: string) {
		restoring = name;
		try {
			await api.post(`/api/v1/object-storage/trash/containers/${encodeURIComponent(name)}/restore`, {}, token, projectId);
			await load(true);
			toast.success(t('buckets.dashboardPage.restoreSuccess', { name }));
		} catch (e) {
			toast.error(t('buckets.dashboardPage.restoreFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			restoring = null;
		}
	}

	async function purgeContainer(name: string) {
		if (!await confirmDialog(t('buckets.dashboardPage.purgeConfirm', { name }))) return;
		deleting = name;
		try {
			await api.delete(`/api/v1/object-storage/trash/containers/${encodeURIComponent(name)}`, token, projectId);
			await load(true);
		} catch (e) {
			toast.error(t('buckets.dashboardPage.purgeFailed', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = null;
		}
	}

	async function runBulk(action: 'delete' | 'restore' | 'purge') {
		const ids = [...selection.ids];
		if (ids.length === 0) return;
		if (action === 'delete' && !await confirmDialog(t('buckets.dashboardPage.bulkDeleteConfirm', { count: ids.length }))) return;
		if (action === 'purge' && !await confirmDialog(t('buckets.dashboardPage.bulkPurgeConfirm', { count: ids.length }))) return;
		busy = true;
		const requestToken = token;
		const requestProject = projectId;
		const endpoint = (id: string) => action === 'delete'
			? `/api/v1/object-storage/${encodeURIComponent(id)}`
			: action === 'restore'
				? `/api/v1/object-storage/trash/containers/${encodeURIComponent(id)}/restore`
				: `/api/v1/object-storage/trash/containers/${encodeURIComponent(id)}`;
		const results = await executeBulkMutations(ids, (id) =>
			action === 'restore'
				? api.post(endpoint(id), {}, requestToken, requestProject)
				: api.delete(endpoint(id), requestToken, requestProject)
		);
		if ($auth.projectId === requestProject) {
			selection.remove(results.filter((r) => r.ok).map((r) => r.id));
			await load(true);
		}
		const successCount = results.filter((r) => r.ok).length;
		const failureCount = results.length - successCount;
		if (successCount) toast.success(t('buckets.dashboardPage.bulkSuccess', { count: successCount, action }));
		if (failureCount) toast.error(t('buckets.dashboardPage.bulkFailed', { count: failureCount, action }));
		busy = false;
	}

	const ar = createAutoRefresh(() => load(), {
		storageKey: 'dashboard-object-storage',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});

	$effect(() => {
		const pid = $auth.projectId;
		selection.clear();
		trashArrivals.reset();
		bucketArrivals.reset();
		containers = [];
		inventoryLoaded = false;
		deletedContainers = [];
		account = null;
		if (!pid) {
			loading = false;
			return;
		}
		untrack(() => load());
	});
 let viewOwner = '';
 $effect(() => authDisplayContext.subscribe(({ key }) => {
  if (viewOwner === key) return;
  viewOwner = key;
  untrack(() => { search = ''; trashSearch = ''; view.reset(); trashView.reset(); });
 }));
</script>

<BucketCreateDialog bind:open={showModal} onCreate={createContainer} />

<PageShell class="bulk-selection-page space-y-4">
	<PageHeader breadcrumb={t('buckets.dashboardPage.breadcrumb')} title={t('buckets.dashboardPage.title')}>
		{#snippet actions()}
			<TutorialStartButton tour="buckets" compactOnMobile />
			<Button onclick={() => (showModal = true)} variant="primary" dataTour="object-storage-create-open">{t('buckets.dashboardPage.create')}</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label={t('buckets.dashboardPage.toolbar')}>
 {#snippet filters()}<RegexSearch id="bucket-search" bind:value={search} /><TableViewControls {view} class="" />{/snippet}
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={refreshing || loading}
				onManualRefresh={forceRefresh}
			/>
		{/snippet}
	</ResourceToolbar>
	<section aria-label={t('buckets.dashboardPage.accountStats')} class="mb-6">
		{#if accountLoading && !account}
			<LoadingState variant="section" label={t('buckets.dashboardPage.accountLoading')} />
		{:else if accountError}
			<Alert tone="danger" title={t('buckets.dashboardPage.accountLoadFailed')}>{accountError}</Alert>
		{:else if account}
			<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
				<StatTile label={t('buckets.dashboardPage.title')} value={account.container_count} accent="indigo" />
				<StatTile label={t('buckets.dashboardPage.objectCount')} value={account.object_count} accent="cyan" />
				<StatTile label={t('buckets.dashboardPage.usage')} value={formatAccountBytes(account.bytes_used)} accent="violet" />
			</div>
		{:else}
			<Alert tone="neutral">{t('buckets.dashboardPage.accountEmpty')}</Alert>
		{/if}
	</section>

	{#if !loading && containers.length > 0 && view.rows.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{tl('table.noMatches')}</p>{/if}
	{#if activeError}
		<Alert tone="danger" class="mb-4" title={t('buckets.dashboardPage.loadFailed')}>{activeError}</Alert>
	{/if}


	{#if loading}
		<LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('buckets.dashboardPage.title') })} />
	{:else if containers.length === 0 && !activeError}
		<EmptyState headline={t('buckets.dashboardPage.emptyTitle')} description={t('buckets.dashboardPage.emptyDescription')} />
	{:else}
		{#if containers.length > 0}
			<div class="mb-3">
				<SelectionToolbar
					label={t('buckets.dashboardPage.title')}
					ariaLabel={t('buckets.dashboardPage.selectAll')}
					checked={selectionDomain === 'active' && selection.count === view.rows.length}
					indeterminate={selectionDomain === 'active' && selection.count > 0 && selection.count < view.rows.length}
					selectedCount={selectionDomain === 'active' ? selection.count : 0}
					disabled={busy}
					onToggle={() => { setSelectionDomain('active'); selection.toggleAll(view.rows.map((c) => c.name)); }}
				/>
			</div>
			<div data-tour="object-storage-list">
			<BucketCardGrid
				containers={view.rows}
				{deleting}
				{refreshing}
				arrivals={bucketArrivals}
				selectedIds={selectionDomain === 'active' ? selection.ids : new Set()}
				selectionDisabled={busy}
				onToggleSelect={(id) => { setSelectionDomain('active'); selection.toggle(id); }}
				highlightName={lastCreated}
				onDelete={deleteContainer}
			/>
			</div>
		{/if}
	{/if}

		{#if trashLoading}
			<LoadingState variant="inline" class="mt-8" label={t('buckets.dashboardPage.trashLoading')} />
		{:else if trashError}
			<Alert tone="danger" class="mt-8" title={t('buckets.dashboardPage.trashLoadFailed')}>{trashError}</Alert>
		{/if}

		{#if deletedContainers.length > 0 || trashSearch || Object.keys(trashView.filters).length > 0 || trashView.sort}
			<div data-tour="object-storage-trash" class="mt-8">
				<h2 class="text-sm font-medium text-ink-2 mb-3 flex items-center gap-2">
					<span class="text-red-400">🗑</span> {t('buckets.dashboardPage.trashTitle')}
				</h2>
				<RegexSearch id="bucket-trash-search" bind:value={trashSearch} /><TableViewControls view={trashView} class="" />
{#if trashView.rows.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{tl('table.noMatches')}</p>{/if}
				<SelectionToolbar
					label={t('buckets.dashboardPage.trashBuckets')}
					ariaLabel={t('buckets.dashboardPage.selectAllTrash')}
					checked={selectionDomain === 'trash' && selection.count === trashView.rows.length}
					indeterminate={selectionDomain === 'trash' && selection.count > 0 && selection.count < trashView.rows.length}
					selectedCount={selectionDomain === 'trash' ? selection.count : 0}
					disabled={busy}
					onToggle={() => { setSelectionDomain('trash'); selection.toggleAll(trashView.rows.map((c) => c.name)); }}
				/>
				<div class="space-y-2 mt-3">
					{#each trashView.rows as c (c.name)}
						{@const deletedAt = (c as SwiftContainer & { deleted_at?: number }).deleted_at}
						{@const entrance = trashArrivals.next(c.name)}
						<div
							class="resource-selection-surface flex items-center justify-between px-4 py-3 rounded-lg border border-state-danger/30 bg-state-danger/5"
							class:motion-fade={entrance !== null}
							style:--motion-index={entrance}
							data-selected={selectionDomain === 'trash' && selection.has(c.name)}
						>
							<div class="flex items-center gap-3">
								<SelectionCheckbox
									checked={selectionDomain === 'trash' && selection.has(c.name)}
									disabled={busy}
									ariaLabel={t('buckets.dashboardPage.selectBucket', { name: c.name })}
									onclick={() => { setSelectionDomain('trash'); selection.toggle(c.name); }}
								/>
								<div>
									<span class="text-sm font-medium text-red-300">{c.name}</span>
									{#if deletedAt}
										<span class="ml-2 text-xs text-ink-2">
											{t('buckets.dashboardPage.deletedDate', { date: new Date(deletedAt * 1000).toLocaleDateString(intlLocale()) })}
										</span>
									{/if}
								</div>
							</div>
							<div class="flex gap-2">
								<button onclick={() => restoreContainer(c.name)} disabled={restoring === c.name || busy} class="text-xs text-emerald-400 hover:text-emerald-300 disabled:text-ink-3 px-2 py-1 rounded border border-emerald-900 hover:border-emerald-700 disabled:border-line-2 transition-colors">{#if restoring === c.name}<LoadingState variant="control" label={t('buckets.dashboardPage.restoring')} />{:else}{t('buckets.dashboardPage.restore')}{/if}</button>
								<button onclick={() => purgeContainer(c.name)} disabled={deleting === c.name || busy} class="text-xs text-red-400 hover:text-red-300 disabled:text-ink-3 px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">{#if deleting === c.name}<LoadingState variant="control" label={t('buckets.dashboardPage.deleting')} />{:else}{t('buckets.dashboardPage.purge')}{/if}</button>
							</div>
						</div>
					{/each}
				</div>
				<p class="mt-2 text-xs text-ink-2">{t('buckets.dashboardPage.trashDescription')}</p>
			</div>
		{/if}

	<BulkSelectionOverlay
		count={selection.count}
		ariaLabel={selectionDomain === 'active' ? t('buckets.dashboardPage.bulkLabel') : t('buckets.dashboardPage.bulkTrashLabel')}
		busy={busy}
		actions={selectionDomain === 'active'
			? [{ key: 'delete', label: t('buckets.dashboardPage.moveToTrash'), tone: 'danger', onAction: () => runBulk('delete') }]
			: [
				{ key: 'restore', label: t('buckets.dashboardPage.restore'), tone: 'success', onAction: () => runBulk('restore') },
				{ key: 'purge', label: t('buckets.dashboardPage.purge'), tone: 'danger', onAction: () => runBulk('purge') },
			]}
		onClear={() => selection.clear()}
	/>
</PageShell>
