<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { untrack } from 'svelte';
	import { pushState } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
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

	let instances = $state<DbInstance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let restarting = $state<string | null>(null);
	let showCreatePanel = $state(false);
	let selectedInstanceId = $state<string | null>(null);
	const selection = createResourceSelection();
	let bulkBusy = $state(false);
	const selectableIds = $derived(new Set(instances.map((instance) => instance.id)));

	function prefetchCreateMetadata() {
		const token = $auth.token ?? undefined;
		const projectId = $auth.projectId ?? undefined;
		void api.prefetch('/api/v1/database-instances/flavors', token, projectId);
		void api.prefetch('/api/v1/database-instances/datastores', token, projectId);
	}

	function openPanel(id: string) {
		selectedInstanceId = id;
		pushState(`/dashboard/database/instances/${id}`, { instanceId: id });
	}

	function closePanel() {
		selectedInstanceId = null;
		pushState('/dashboard/database/instances', {});
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		if (instances.length === 0) loading = true;
		else refreshing = true;
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		try {
			const nextInstances = await api.get<DbInstance[]>('/api/v1/database-instances', tokenSnapshot, projectSnapshot);
			if ($auth.projectId !== projectSnapshot) return;
			instances = nextInstances;
			selection.retain(nextInstances.map((instance) => instance.id));
		} catch {
			if ($auth.projectId === projectSnapshot) {
				instances = [];
				selection.clear();
			}
		} finally {
			if ($auth.projectId === projectSnapshot) {
				loading = false;
				refreshing = false;
			}
		}
	}

	async function forceRefresh() {
		const tokenSnapshot = $auth.token ?? undefined;
		const projectSnapshot = $auth.projectId ?? undefined;
		refreshing = true;
		try {
			const nextInstances = await api.get<DbInstance[]>('/api/v1/database-instances', tokenSnapshot, projectSnapshot, { refresh: true });
			if ($auth.projectId !== projectSnapshot) return;
			instances = nextInstances;
			selection.retain(nextInstances.map((instance) => instance.id));
		} catch {
			if ($auth.projectId === projectSnapshot) instances = [];
		} finally {
			if ($auth.projectId === projectSnapshot) refreshing = false;
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

	$effect(() => {
		const pid = $auth.projectId;
		instances = [];
		selection.clear();
		if (!pid) return;
		untrack(() => load());
	});
</script>

<DbCreatePanel bind:open={showCreatePanel} onCreated={load} />

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
			<Button onclick={() => (showCreatePanel = true)} onintent={prefetchCreateMetadata} variant="primary">{tr('actions.createInstance')}</Button>
		{/snippet}
	</PageHeader>
	<ResourceToolbar label={tr('instances.toolbar')}>
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
		<LoadingSkeleton variant="table" rows={5} />
	{:else if instances.length === 0}
		<EmptyState headline={tr('instances.empty')} description={tr('instances.emptyHelp')} />
	{:else}
		<DbInstancesTable
			{instances}
			{refreshing}
			{restarting}
			{deleting}
			selectedIds={selection.ids}
			selectableIds={selectableIds}
			selectionDisabled={bulkBusy}
			onToggleSelect={(id) => selection.toggle(id)}
			onToggleAll={() => selection.toggleAll(selectableIds)}
			onOpen={openPanel}
			onRestart={restartInstance}
			onDelete={deleteInstance}
		/>
		<BulkSelectionOverlay count={selection.count} ariaLabel={tr('instances.bulkLabel')} actions={bulkActions} busy={bulkBusy} onClear={() => selection.clear()} />
	{/if}
</PageShell>
