<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t as tr } from '$lib/i18n/ns/database';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi, ApiError } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import DbCreatePanel from '$lib/components/database/DbCreatePanel.svelte';
	import type { DbInstance } from '$lib/types/database';
	import { toast } from '$lib/stores/toast';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as tc } from '$lib/i18n/ns/common';

	let instances = $state<DbInstance[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let deleting = $state<string | null>(null);
	let restarting = $state<string | null>(null);
	let loadError = $state<string | null>(null);

	let showCreatePanel = $state(false);
	let search = $state('');
	const view = createTableView<DbInstance>({
		rows: () => instances,
		search: () => search,
		searchable: (inst) => [inst.name, inst.id, inst.status, inst.datastore?.type, inst.datastore?.version, inst.project_id, inst.size, inst.created_at].map((value) => String(value ?? '')),
		locale: intlLocale,
		columns: () => [
			{ key: 'name', label: tr('labels.name'), value: (inst) => inst.name },
			{ key: 'status', label: tr('labels.status'), value: (inst) => inst.status },
			{ key: 'datastore', label: tr('labels.datastoreEnglish'), value: (inst) => [inst.datastore?.type, inst.datastore?.version].filter(Boolean).join(' ') || null },
			{ key: 'project', label: tr('labels.project'), value: (inst) => inst.project_id },
			{ key: 'size', label: tr('labels.sizeGb'), value: (inst) => inst.size },
			{ key: 'id', label: 'ID', value: (inst) => inst.id },
			{ key: 'created', label: tr('labels.created'), value: (inst) => inst.created_at },
		],
	});

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);


	async function load(force = false) {
		if (instances.length === 0) loading = true;
		else refreshing = true;
		loadError = null;
		try {
			instances = await api.get<DbInstance[]>('/api/v1/admin/database-instances', token, projectId, { refresh: force });
		} catch (error) {
			loadError = error instanceof ApiError ? error.message : tr('instances.listFailed');
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function deleteInstance(id: string, name: string) {
		if (!instances.some(inst => inst.id === id && !!inst.project_id && inst.project_id === projectId)) return;
		if (!await confirmDialog(tr('instances.deleteConfirm', { name: name || id.slice(0, 8) }))) return;
		deleting = id;
		try {
			await api.delete(`/api/v1/database-instances/${id}`, token, projectId);
			await load();
		} catch (e) {
			if (!api.isCurrent()) return;
			toast.error(tr('errors.delete', { error: e instanceof ApiError ? e.message : String(e) }));
		} finally {
			deleting = null;
		}
	}

	async function restartInstance(id: string, name: string) {
		if (!instances.some(inst => inst.id === id && !!inst.project_id && inst.project_id === projectId)) return;
		if (!await confirmDialog(tr('instances.restartConfirm', { name: name || id.slice(0, 8) }))) return;
		restarting = id;
		try {
			await api.post(`/api/v1/database-instances/${id}/restart`, {}, token, projectId);
			await load();
		} catch (e) {
			if (!api.isCurrent()) return;
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

<PageShell>
	<PageHeader breadcrumb={tr('breadcrumbs.admin')} title={tr('instances.title')}>
		{#snippet actions()}
			<button onclick={() => (showCreatePanel = true)}
				class="text-xs text-action-on-warm bg-action-warm hover:bg-action-warm-hover transition-colors px-3 py-1.5 rounded border border-action-warm">{tr('actions.createInstance')}</button>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={ar.refresh}
			/>
		{/snippet}
	</PageHeader>
	<div class="mb-4 space-y-3">
		<RegexSearch id="admin-database-instances-search" bind:value={search} label={tc('table.search')} />
		<TableViewControls {view} class={view.rows.length ? 'lg:hidden' : ''} />
	</div>
	{#if loadError}
		<Alert tone="danger" title={tr('instances.loadFailed')}>
			{loadError}
		</Alert>
	{/if}

	{#if loading}
		<LoadingState variant="surface" />
	{:else if view.rows.length === 0 && !loadError}
		<div class="text-ink-2 text-sm">{instances.length ? tc('table.noMatches') : tr('instances.empty')}</div>
	{:else if view.rows.length > 0}
		<ResponsiveTable>
			{#snippet cards()}
				{#each view.rows as inst (inst.id)}
					<CompactResourceCard>
						<div class="flex items-start justify-between gap-2"><a class="min-h-11 break-all font-medium text-warm-text" href={`/admin/database-instances/${inst.id}`}>{inst.name || inst.id.slice(0, 8)}</a><StatusChip status={inst.status} /></div>
						<div class="space-y-1 break-all text-xs text-ink-2"><p>{inst.datastore?.type ?? '-'} {inst.datastore?.version ?? ''} · {inst.size ?? '-'} GB</p><p>{tr('labels.project')}: {inst.project_id || '-'}</p></div>
						{#snippet actions()}{#if inst.project_id && inst.project_id === projectId}<Button variant="secondary" size="sm" disabled={restarting === inst.id} onclick={() => restartInstance(inst.id, inst.name)}>{#if restarting === inst.id}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{restarting === inst.id ? tr('state.restarting') : tr('actions.restart')}</Button><Button variant="danger" size="sm" disabled={deleting === inst.id} onclick={() => deleteInstance(inst.id, inst.name)}>{#if deleting === inst.id}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{deleting === inst.id ? tr('state.deleting') : tr('actions.delete')}</Button>{/if}{/snippet}
						{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p class="font-mono">{inst.id}</p><p>{tr('labels.created')}: {inst.created_at?.slice(0, 10) ?? '-'}</p></div>{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<div class="overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<TableColumnHeader {view} columnKey="name" />
						<TableColumnHeader {view} columnKey="status" />
						<TableColumnHeader {view} columnKey="datastore" />
						<TableColumnHeader {view} columnKey="project" />
						<TableColumnHeader {view} columnKey="size" />
						<TableColumnHeader {view} columnKey="id" />
						<TableColumnHeader {view} columnKey="created" />
						<th class="text-right py-3 px-4 font-medium">{tr('labels.actions')}</th>
					</tr>
				</thead>
				<tbody>
					{#each view.rows as inst}
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
								{#if inst.project_id && inst.project_id === projectId}
								<div class="flex justify-end gap-1">
									<button onclick={() => restartInstance(inst.id, inst.name)} disabled={restarting === inst.id}
										class="text-warm-text hover:text-warm-text-hover disabled:text-ink-3 text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm disabled:border-line-2 transition-colors">
										{#if restarting === inst.id}<span class="inline-flex items-center gap-2" role="status"><LoadingState variant="control" label="" aria-hidden="true" /><span>{tr('state.restarting')}</span></span>{:else}{tr('actions.restart')}{/if}
									</button>
									<button onclick={(e) => { e.stopPropagation(); deleteInstance(inst.id, inst.name); }} disabled={deleting === inst.id}
										class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">
										{#if deleting === inst.id}<span class="inline-flex items-center gap-2" role="status"><LoadingState variant="control" label="" aria-hidden="true" /><span>{tr('state.deleting')}</span></span>{:else}{tr('actions.delete')}{/if}
									</button>
								</div>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		</ResponsiveTable>
	{/if}

</PageShell>
