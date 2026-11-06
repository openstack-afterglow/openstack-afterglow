<script lang="ts">
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { t } from '$lib/i18n/ns/drover';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { untrack } from 'svelte';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import { k3sPermissions } from '$lib/stores/k3sPermissions';
	import { SectionHeader } from '$lib/components/ui';
 import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
 import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	const s = useK3sClusterDetailController();

	let loading = $state(false);
	let loadError = $state('');

	$effect(() => {
		const ns = s.selectedNamespace;
		if (!ns) return;
		if (s.servicesLoaded) return;
		loading = true;
		loadError = '';
		untrack(() => s.loadServices())
			.catch(() => { loadError = t('services.loadFailed'); })
			.finally(() => { loading = false; });
	});
	const tableState = s.tableState('services');
	const viewColumns = $derived<TableColumn<(typeof s.services)[number]>[]>([
		{ key: 'name', label: t('services.name'), value: row => row.name },
		{ key: 'type', label: t('services.type'), value: row => row.type },
		{ key: 'cluster_ip', label: t('services.clusterIp'), value: row => row.cluster_ip },
		{ key: 'ports', label: t('services.ports'), value: row => row.ports.map(p => `${p.port}${p.node_port ? ":" + p.node_port : ""}/${p.protocol}`).join(", ") },
		{ key: 'created_at', label: t('services.createdAt'), value: row => row.created_at ? Date.parse(row.created_at) : null, filterValues: row => [row.created_at?.slice(0, 10)], format: value => typeof value === 'number' ? new Date(value).toISOString().slice(0, 10) : String(value ?? '') },
	]);
	const view = createTableView({ rows: () => s.services, columns: () => viewColumns, search: () => tableState.search, state: tableState.state });
</script>

<div class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<SectionHeader title="Service" meta={t('services.count', { count: s.services.length })} />
	<RegexSearch id="cluster-services-search" bind:value={tableState.search} />
	<TableViewControls view={view} />

	{#if loading}
		<div class="mt-4 text-sm text-ink-2 text-center py-6"><LoadingState variant="section" label={t('services.loading')} /></div>
	{:else if loadError}
		<div class="mt-4 text-sm text-red-400">{loadError}</div>
	{:else if s.services.length === 0}
		<div class="mt-4 text-sm text-ink-2 text-center py-6">{t('services.empty')}</div>
	{/if}
	{#if !loading && !loadError}
  <ResponsiveTable>
   {#snippet cards()}
    {#each view.rows as svc (svc.name)}
     {@const actioning = s.workloadActioning === `${s.selectedNamespace}:svc:${svc.name}`}
     <CompactResourceCard>
      <strong class="text-sm font-mono break-all">{svc.name}</strong>
      <p class="text-xs text-ink-2">{svc.type} · {svc.cluster_ip ?? '—'}</p>
      <p class="text-xs break-all">{t('services.ports')}: {svc.ports.map(p => `${p.port}${p.node_port ? ':' + p.node_port : ''}/${p.protocol}`).join(', ') || '—'}</p>
      {#snippet details()}<p class="text-xs">{t('services.createdAt')}: {svc.created_at ? svc.created_at.slice(0, 10) : '—'}</p>{/snippet}
      {#snippet actions()}<button onclick={() => s.removeSvc(svc.name)} disabled={!$k3sPermissions.workloads || !!s.workloadActioning} class="px-2 py-1 rounded text-xs bg-surface-sunken text-state-danger-text disabled:opacity-40">{#if actioning}<LoadingState variant="control" label={t('services.deleting')} />{:else}{t('services.delete')}{/if}</button>{/snippet}
     </CompactResourceCard>
    {/each}
   {/snippet}
		<div class="mt-4 overflow-x-auto">
			<table class="w-full text-xs">
				<thead>
					<tr class="border-b border-line">
						<TableColumnHeader class="text-left pb-2 text-xs tracking-wide text-ink-2 font-medium" view={view} columnKey="name" />
						<TableColumnHeader class="text-left pb-2 text-xs tracking-wide text-ink-2 font-medium" view={view} columnKey="type" />
						<TableColumnHeader class="text-left pb-2 text-xs tracking-wide text-ink-2 font-medium" view={view} columnKey="cluster_ip" />
						<TableColumnHeader class="text-left pb-2 text-xs tracking-wide text-ink-2 font-medium" view={view} columnKey="ports" />
						<TableColumnHeader class="text-left pb-2 text-xs tracking-wide text-ink-2 font-medium" view={view} columnKey="created_at" />
						<th class="pb-2"></th>
					</tr>
				</thead>
				<tbody>
					{#each view.rows as svc}
						{@const actioning = s.workloadActioning === `${s.selectedNamespace}:svc:${svc.name}`}
						<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
							<td class="py-2.5 text-ink-0 font-medium font-mono"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={svc.name}>{svc.name}</span></td>
							<td class="py-2.5 text-ink-2">{svc.type}</td>
							<td class="py-2.5 text-ink-2 font-mono">{svc.cluster_ip ?? '—'}</td>
							<td class="py-2.5 text-ink-2">
								{svc.ports.map(p => `${p.port}${p.node_port ? ':' + p.node_port : ''}/${p.protocol}`).join(', ') || '—'}
							</td>
							<td class="py-2.5 text-ink-2">{svc.created_at ? svc.created_at.slice(0, 10) : '—'}</td>
							<td class="py-2.5 text-right">
								<button
									onclick={() => s.removeSvc(svc.name)}
									disabled={!$k3sPermissions.workloads || !!s.workloadActioning}
									class="px-2 py-1 rounded text-xs bg-red-900/40 text-red-300 hover:bg-red-900/70 disabled:opacity-40 transition-colors"
								>
									{#if actioning}<LoadingState variant="control" label={t('services.deleting')} />{:else}{t('services.delete')}{/if}
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
  </ResponsiveTable>
	{/if}
</div>
