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
	import K3sScaleModal from './K3sScaleModal.svelte';
	import type { DeploymentInfo } from '$lib/types/k3s';
 import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
 import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	const s = useK3sClusterDetailController();

	let loading = $state(false);
	let loadError = $state('');
	let scalingDeploy = $state<DeploymentInfo | null>(null);

	$effect(() => {
		const ns = s.selectedNamespace;
		if (!ns) return;
		if (s.deploymentsLoaded) return;
		loading = true;
		loadError = '';
		untrack(() => s.loadDeployments())
			.catch(() => { loadError = t('deployments.loadFailed'); })
			.finally(() => { loading = false; });
	});
	const tableState = s.tableState('deployments');
	const columns = $derived<TableColumn<DeploymentInfo>[]>([
		{ key: 'name', label: t('deployments.name'), value: row => row.name },
		{ key: 'replicas', label: t('deployments.replicas'), value: row => row.replicas },
		{ key: 'strategy', label: t('deployments.strategy'), value: row => row.strategy },
		{ key: 'images', label: t('deployments.image'), value: row => row.images.join(', ') },
	]);
	const view = createTableView({ rows: () => s.deployments, columns: () => columns, search: () => tableState.search, state: tableState.state });
	const replicaState = s.tableState('replicasets');
	const replicaColumns = $derived<TableColumn<(typeof s.replicasets)[number]>[]>([
		{ key: 'name', label: t('deployments.name'), value: row => row.name },
		{ key: 'replicas', label: t('deployments.replicas'), value: row => row.replicas },
		{ key: 'owner', label: t('deployments.owner'), value: row => [row.owner_kind, row.owner_name].filter(Boolean).join(' ') || null },
		{ key: 'images', label: t('deployments.image'), value: row => row.images.join(', ') },
	]);
	const replicaView = createTableView({ rows: () => s.replicasets, columns: () => replicaColumns, search: () => replicaState.search, state: replicaState.state });
</script>

{#if scalingDeploy && $k3sPermissions.workloads}
	<K3sScaleModal
		deploymentName={scalingDeploy.name}
		currentReplicas={scalingDeploy.replicas}
		onClose={() => { scalingDeploy = null; }}
		onApply={(r) => s.scaleDeploymentTo(scalingDeploy!.name, r)}
	/>
{/if}

<!-- Deployments -->
<div class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<SectionHeader title="Deployment" meta={t('deployments.count', { count: s.deployments.length })} />
	<RegexSearch id="cluster-deployments-search" bind:value={tableState.search} />
	<TableViewControls {view} />

	{#if loading}
		<div class="mt-4 text-sm text-ink-2 text-center py-6"><LoadingState variant="section" label={t('deployments.loading')} /></div>
	{:else if loadError}
		<div class="mt-4 text-sm text-red-400">{loadError}</div>
	{:else if s.deployments.length === 0}
		<div class="mt-4 text-sm text-ink-2 text-center py-6">{t('deployments.empty')}</div>
	{/if}
	{#if !loading && !loadError}
  <ResponsiveTable>
   {#snippet cards()}
    {#each view.rows as dep (dep.name)}
     {@const actioning = s.workloadActioning === `${s.selectedNamespace}:deploy:${dep.name}`}
     <CompactResourceCard>
      <strong class="text-sm font-mono break-all">{dep.name}</strong>
      <p class="text-xs">{t('deployments.replicas')}: {dep.ready}/{dep.replicas} {#if dep.available < dep.replicas}<span class="text-state-warning-text">{t('deployments.available', { count: dep.available })}</span>{/if}</p>
      <p class="text-xs text-ink-2">{t('deployments.strategy')}: {dep.strategy || '—'}</p>
      {#snippet details()}<p class="text-xs break-all">{t('deployments.image')}: {dep.images.join(', ') || '—'}</p>{/snippet}
      {#snippet actions()}<button onclick={() => s.rolloutRestartDeployment(dep.name)} disabled={!$k3sPermissions.workloads || !!s.workloadActioning} class="px-2 py-1 rounded text-xs bg-surface-selected/40 text-warm-text disabled:opacity-40">{#if actioning}<LoadingState variant="control" label={t('deployments.actioning')} />{:else}{t('deployments.restart')}{/if}</button><button onclick={() => { scalingDeploy = dep; }} disabled={!$k3sPermissions.workloads || !!s.workloadActioning} class="px-2 py-1 rounded text-xs bg-surface-sunken text-ink-2 disabled:opacity-40">{t('deployments.scale')}</button>{/snippet}
     </CompactResourceCard>
    {/each}
   {/snippet}
		<div class="mt-4 overflow-x-auto">
			<table class="w-full text-xs">
				<thead>
					<tr class="border-b border-line">{#each columns as column}<TableColumnHeader class="text-left pb-2 text-xs tracking-wide text-ink-2 font-medium" view={view} columnKey={column.key} />{/each}<th></th></tr>
				</thead>
				<tbody>
					{#each view.rows as dep}
						{@const actioning = s.workloadActioning === `${s.selectedNamespace}:deploy:${dep.name}`}
						<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
							<td class="py-2.5 text-ink-0 font-medium font-mono"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={dep.name}>{dep.name}</span></td>
							<td class="py-2.5">
								<span class="tabular-nums text-ink-0">{dep.ready}/{dep.replicas}</span>
								{#if dep.available < dep.replicas}
									<span class="ml-1 text-yellow-400 text-xs">{t('deployments.available', { count: dep.available })}</span>
								{/if}
							</td>
							<td class="py-2.5 text-ink-2">{dep.strategy || '—'}</td>
							<td class="py-2.5 text-ink-2 max-w-[200px] truncate">{dep.images.join(', ') || '—'}</td>
							<td class="py-2.5 text-right">
								<div class="flex items-center justify-end gap-1.5">
									<button
										onclick={() => s.rolloutRestartDeployment(dep.name)}
										disabled={!$k3sPermissions.workloads || !!s.workloadActioning}
										class="px-2 py-1 rounded text-xs bg-surface-selected/40 text-warm-text hover:bg-surface-selected/70 disabled:opacity-40 transition-colors"
									>{#if actioning}<LoadingState variant="control" label={t('deployments.actioning')} />{:else}{t('deployments.restart')}{/if}</button>
									<button
										onclick={() => { scalingDeploy = dep; }}
										disabled={!$k3sPermissions.workloads || !!s.workloadActioning}
										class="px-2 py-1 rounded text-xs bg-surface-sunken text-ink-2 hover:bg-surface-selected disabled:opacity-40 transition-colors"
									>{t('deployments.scale')}</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
  </ResponsiveTable>
	{/if}
</div>

<!-- ReplicaSets -->
{#if !loading && !loadError}
	<div class="bg-surface-base border border-line rounded-lg p-5 mb-4">
		<SectionHeader title="ReplicaSet" meta={t('deployments.count', { count: s.replicasets.length })} />
	<RegexSearch id="cluster-replicas-search" bind:value={replicaState.search} />
	<TableViewControls view={replicaView} />
  <ResponsiveTable>
   {#snippet cards()}
    {#each replicaView.rows as rs (rs.name)}
     <CompactResourceCard>
      <strong class="text-sm font-mono break-all">{rs.name}</strong>
      <p class="text-xs">{t('deployments.replicas')}: {rs.ready}/{rs.replicas}</p>
      <p class="text-xs break-all">{t('deployments.owner')}: {rs.owner_kind && rs.owner_name ? `${rs.owner_kind} ${rs.owner_name}` : '—'}</p>
      {#snippet details()}<p class="text-xs break-all">{t('deployments.image')}: {rs.images.join(', ') || '—'}</p>{/snippet}
     </CompactResourceCard>
    {/each}
   {/snippet}
		<div class="mt-4 overflow-x-auto">
			<table class="w-full text-xs">
				<thead>
					<tr class="border-b border-line">{#each replicaColumns as column}<TableColumnHeader class="text-left pb-2 text-xs tracking-wide text-ink-2 font-medium" view={replicaView} columnKey={column.key} />{/each}</tr>
				</thead>
				<tbody>
					{#each replicaView.rows as rs}
						<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
							<td class="py-2.5 text-ink-2 font-mono"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={rs.name}>{rs.name}</span></td>
							<td class="py-2.5 tabular-nums text-ink-2">{rs.ready}/{rs.replicas}</td>
							<td class="py-2.5 text-ink-2">
								{#if rs.owner_kind && rs.owner_name}
									<span class="text-xs bg-surface-sunken px-1.5 py-0.5 rounded">{rs.owner_kind}</span>
									<span class="ml-1 font-mono">{rs.owner_name}</span>
								{:else}
									—
								{/if}
							</td>
							<td class="py-2.5 text-ink-2 max-w-[200px] truncate">{rs.images.join(', ') || '—'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
  </ResponsiveTable>
	</div>
{/if}
