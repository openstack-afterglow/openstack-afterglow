<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import DbCreatePanel from '$lib/components/database/DbCreatePanel.svelte';
	import type { DbInstance } from '$lib/types/database';
	import { toast } from '$lib/stores/toast';

	let instances = $state<DbInstance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let restarting = $state<string | null>(null);
	let loadError = $state<string | null>(null);

	let showCreatePanel = $state(false);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);


	async function load() {
		if (instances.length === 0) loading = true;
		else refreshing = true;
		loadError = null;
		try {
			instances = await api.get<DbInstance[]>('/api/v1/database-instances?all_projects=true', token, projectId);
		} catch (error) {
			loadError = error instanceof ApiError ? error.message : tr('instances.listFailed');
		} finally {
			loading = false;
			refreshing = false;
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
		if (!await confirmDialog(tr('instances.restartConfirm', { name: name || id.slice(0, 8) }))) return;
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

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-database-instances',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60]
	});

	onMount(load);
</script>

<DbCreatePanel bind:open={showCreatePanel} onCreated={load} />

<div class="p-4 md:p-8 max-w-7xl mx-auto">
	<PageHeader breadcrumb={tr('breadcrumbs.admin')} title={tr('instances.title')}>
		{#snippet actions()}
			<button onclick={() => (showCreatePanel = true)}
				class="text-xs text-action-on-warm bg-action-warm hover:bg-action-warm-hover transition-colors px-3 py-1.5 rounded border border-action-warm">{tr('actions.createInstance')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>
	{#if loadError}
		<Alert tone="danger" title={tr('instances.loadFailed')}>
			{loadError}
		</Alert>
	{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if instances.length === 0 && !loadError}
		<div class="text-ink-2 text-sm">{tr('instances.empty')}</div>
	{:else if instances.length > 0}
		<div class="overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<th class="text-left py-3 px-4 font-medium">{tr('labels.name')}</th>
						<th class="text-left py-3 px-4 font-medium">{tr('labels.status')}</th>
						<th class="text-left py-3 px-4 font-medium">{tr('labels.datastoreEnglish')}</th>
						<th class="text-left py-3 px-4 font-medium">{tr('labels.project')}</th>
						<th class="text-left py-3 px-4 font-medium">{tr('labels.sizeGb')}</th>
						<th class="text-left py-3 px-4 font-medium">ID</th>
						<th class="text-left py-3 px-4 font-medium">{tr('labels.created')}</th>
						<th class="text-right py-3 px-4 font-medium">{tr('labels.actions')}</th>
					</tr>
				</thead>
				<tbody>
					{#each instances as inst}
						<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
							<td class="py-3 px-4">
								<a href="/admin/database-instances/{inst.id}" class="text-warm-text hover:text-warm-text-hover font-medium max-md:block max-md:max-w-[66vw] max-md:truncate" title={inst.name}>{inst.name}</a>
							</td>
							<td class="py-3 px-4"><StatusChip status={inst.status} /></td>
							<td class="py-3 px-4 text-ink-2">{inst.datastore?.type ?? '-'} {inst.datastore?.version ?? ''}</td>
							<td class="py-3 px-4 text-ink-2 font-mono text-xs">{inst.project_id || '-'}</td>
							<td class="py-3 px-4 text-ink-2">{inst.size || '-'}</td>
							<td class="py-3 px-4 text-ink-2 font-mono text-xs">{inst.id.slice(0, 8)}…</td>
							<td class="py-3 px-4 text-ink-2 text-xs">{inst.created_at ? inst.created_at.slice(0, 10) : '-'}</td>
							<td class="py-3 px-4 text-right">
								<div class="flex justify-end gap-1">
									<button onclick={() => restartInstance(inst.id, inst.name)} disabled={restarting === inst.id}
										class="text-warm-text hover:text-warm-text-hover disabled:text-ink-3 text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm disabled:border-line-2 transition-colors">
										{#if restarting === inst.id}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{tr('state.restarting')}</span></span>{:else}{tr('actions.restart')}{/if}
									</button>
									<button onclick={(e) => { e.stopPropagation(); deleteInstance(inst.id, inst.name); }} disabled={deleting === inst.id}
										class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">
										{#if deleting === inst.id}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" tone="ink" /><span>{tr('state.deleting')}</span></span>{:else}{tr('actions.delete')}{/if}
									</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

</div>
