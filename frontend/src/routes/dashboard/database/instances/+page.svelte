<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
	import { t as tr } from '$lib/i18n/ns/database';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { pushState } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import DbCreatePanel from '$lib/components/database/DbCreatePanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import DbInstanceDetailPanel from '$lib/components/database/DbInstanceDetailPanel.svelte';
	import DbInstancesTable from '$lib/components/database/DbInstancesTable.svelte';
	import type { DbInstance } from '$lib/types/database';
	import { toast } from '$lib/stores/toast';
	import { Button, EmptyState, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { dbInstanceColumns } from '$lib/utils/databaseTableColumns';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';

	let instances = $state<DbInstance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let restarting = $state<string | null>(null);
	let showCreatePanel = $state(false);
	// The instance this page just created; only its row carries the tutorial delete anchor.
	let lastCreatedId = $state<string | null>(null);
	let selectedInstanceId = $state<string | null>(null);
	const selection = createResourceSelection();
	let bulkBusy = $state(false);
	let search = $state('');
	const view = createTableView({
		rows: () => instances,
		columns: dbInstanceColumns,
		search: () => search,
		searchable: (row) => [row.name, row.id, row.status, row.datastore?.type ?? '', row.datastore?.version ?? '', String(row.size ?? ''), row.created_at],
		locale: intlLocale,
	});
	const selectableIds = $derived(new Set(view.rows.map((instance) => instance.id)));
	$effect(() => {
		const visibleIds = view.rows.map((instance) => instance.id);
		untrack(() => selection.retain(visibleIds));
	});

	function prefetchCreateMetadata() {
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		void api.prefetch('/api/v1/database-instances/flavors', token, projectId);
		void api.prefetch('/api/v1/database-instances/datastores', token, projectId);
	}

	function openPanel(id: string) {
		selectedInstanceId = id;
		pushState(`/dashboard/database/instances/${id}`, {});
	}

	function closePanel() {
		selectedInstanceId = null;
		pushState('/dashboard/database/instances', {});
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let inventoryLoaded = $state(false);
	async function load() {
		if (!inventoryLoaded) loading = true;
		else refreshing = true;
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		const ownerSnapshot = $authDisplayContext.key;
		try {
			const nextInstances = await api.get<DbInstance[]>('/api/v1/database-instances', tokenSnapshot, projectSnapshot);
			if ($auth.projectId !== projectSnapshot || $authDisplayContext.key !== ownerSnapshot) return;
			instances = nextInstances;
			inventoryLoaded = true;
			selection.retain(nextInstances.map((instance) => instance.id));
		} catch {
			if ($auth.projectId === projectSnapshot && $authDisplayContext.key === ownerSnapshot) {
				instances = [];
				selection.clear();
			}
		} finally {
			if ($auth.projectId === projectSnapshot && $authDisplayContext.key === ownerSnapshot) {
				loading = false;
				refreshing = false;
			}
		}
	}

	async function forceRefresh() {
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		const ownerSnapshot = $authDisplayContext.key;
		refreshing = true;
		try {
			const nextInstances = await api.get<DbInstance[]>('/api/v1/database-instances', tokenSnapshot, projectSnapshot, { refresh: true });
			if ($auth.projectId !== projectSnapshot || $authDisplayContext.key !== ownerSnapshot) return;
			instances = nextInstances;
			selection.retain(nextInstances.map((instance) => instance.id));
		} catch {
			if ($auth.projectId === projectSnapshot && $authDisplayContext.key === ownerSnapshot) instances = [];
		} finally {
			if ($auth.projectId === projectSnapshot && $authDisplayContext.key === ownerSnapshot) refreshing = false;
		}
	}

	async function deleteInstance(id: string, name: string) {
		if (!await confirmDialog(tr('instances.deleteConfirm', { name: name || id.slice(0, 8) }))) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/database-instances/${id}`, token, projectId);
			await load();
		} catch (e) {
			toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = null;
		}
	}

	async function restartInstance(id: string, name: string) {
		if (!await confirmDialog(tr('instances.restartConfirm', { name: name || id.slice(0, 8) }), { confirmLabel: tr('actions.restart'), confirmVariant: 'accent' })) return;
		restarting = id;
		try {
			await api.post(`/api/v1/database-instances/${id}/restart`, {}, token, projectId);
			await load();
		} catch (e) {
			toast.error(tr('errors.restart', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			restarting = null;
		}
	}
	async function runBulk(action: 'restart' | 'delete') {
		const snapshot = [...selection.ids];
		if (snapshot.length === 0) return;
		if (!await confirmDialog(action === 'restart' ? tr('bulk.restartConfirm', { count: snapshot.length }) : tr('bulk.deleteConfirm', { count: snapshot.length }))) return;
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		bulkBusy = true;
		try {
			const results = await executeBulkMutations(snapshot, (id) => action === 'restart'
				? api.post(`/api/v1/database-instances/${id}/restart`, {}, tokenSnapshot, projectSnapshot)
				: api.delete(`/api/v1/database-instances/${id}`, tokenSnapshot, projectSnapshot));
			const successful = results.filter((result) => result.ok).map((result) => result.id);
			const failed = results.length - successful.length;
			if (successful.length > 0) toast.success(action === 'restart' ? tr('bulk.restartSuccess', { count: successful.length }) : tr('bulk.deleteSuccess', { count: successful.length }));
			if (failed > 0) toast.error(action === 'restart' ? tr('bulk.restartFailed', { count: failed }) : tr('bulk.deleteFailed', { count: failed }));
			if ($auth.projectId === projectSnapshot) {
				selection.remove(successful);
				await load();
			}
		} finally {
			bulkBusy = false;
		}
	}

	const bulkActions: BulkSelectionAction[] = [
		{ key: 'restart', label: tr('actions.restart'), tone: 'warning', onAction: () => runBulk('restart') },
		{ key: 'delete', label: tr('actions.delete'), tone: 'danger', onAction: () => runBulk('delete') },
	];

	const ar = createAutoRefresh(() => load(), {
		storageKey: 'dashboard-database-instances',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60],
	});
	const displayOwner = $derived($authDisplayContext.key);

	$effect(() => {
		void displayOwner;
		untrack(() => {
			instances = [];
			inventoryLoaded = false;
			search = '';
			view.reset();
			selection.clear();
			if ($authDisplayContext.ready) void load();
		});
	});
</script>

<DbCreatePanel bind:open={showCreatePanel} onCreatedId={(id) => (lastCreatedId = id)} onCreated={load} />

{#if selectedInstanceId}
	<SlidePanel onClose={closePanel} ariaLabel={tr('instances.detail')} width="w-full md:w-[70vw] max-w-4xl">
		<DbInstanceDetailPanel
			instanceId={selectedInstanceId}
			token={$auth.token ?? undefined}
			projectId={$auth.projectId ?? undefined}
			onClose={closePanel}
			onDeleted={() => { closePanel(); load(); }}
		/>
	</SlidePanel>
{/if}

<PageShell class="bulk-selection-page space-y-4">
	<PageHeader breadcrumb={tr('breadcrumbs.instances')} title={tr('instances.title')}>
		{#snippet actions()}
			<TutorialStartButton tour="database-instances" compactOnMobile />
			<Button onclick={() => (showCreatePanel = true)} onintent={prefetchCreateMetadata} variant="primary" dataTour="database-instances-create-open">{tr('actions.createInstance')}</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label={tr('instances.toolbar')}>
		<RegexSearch id="database-instances-search" bind:value={search} />
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

	{#if loading}
		<LoadingState variant="surface" label={tl('state.loadingNamed', { name: tr('instances.title') })} />
	{:else}
		{#if instances.length === 0}
			<EmptyState headline={tr('instances.empty')} description={tr('instances.emptyHelp')} />
		{/if}
		<div data-tour="database-instances-list">
			<DbInstancesTable
				{instances}
				{view}
				{refreshing}
				{restarting}
				{deleting}
				highlightId={lastCreatedId}
				selectedIds={selection.ids}
				selectableIds={selectableIds}
				selectionDisabled={bulkBusy}
				onToggleSelect={(id) => selection.toggle(id)}
				onToggleAll={() => selection.toggleAll(selectableIds)}
				onOpen={openPanel}
				onRestart={restartInstance}
				onDelete={deleteInstance}
			/>
		</div>
		<BulkSelectionOverlay count={selection.count} ariaLabel={tr('instances.bulkLabel')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
	{/if}
</PageShell>
