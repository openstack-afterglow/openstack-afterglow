<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/drover-pages';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { createPrivateViewScope } from '$lib/utils/privateViewScope';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import K3sClusterDetailPanel from '$lib/components/K3sClusterDetailPanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
 import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
 import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import ClusterFailure from '$lib/components/dashboard/drover/ClusterFailure.svelte';
	import { Alert, Button } from '$lib/components/ui';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as tc } from '$lib/i18n/ns/common';

	interface AdminK3sCluster {
		id: string;
		name: string;
		status: string;
		status_reason: string | null;
		server_ip: string | null;
		api_address: string | null;
		agent_count: number;
		agent_vm_ids: string[];
		k3s_version: string | null;
		created_at: string | null;
		project_id: string | null;
	}

	let clusters = $state<AdminK3sCluster[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');
	let loadGeneration = 0;
	onDestroy(() => { loadGeneration++; });
	const privateScope = createPrivateViewScope();
	let nativeStatuses = $state<string[] | null>(null);
	let search = $state('');
	const view = createTableView<AdminK3sCluster>({
		rows: () => clusters,
		search: () => search,
		searchable: (c) => [c.name, c.id, c.status, c.project_id, c.project_id ? $projectNames.get(c.project_id) : '', c.server_ip, c.agent_count, c.k3s_version, c.created_at, c.status_reason].map((value) => String(value ?? '')),
		locale: intlLocale,
		columns: () => [
			{ key: 'name', label: t('form.name'), value: (c) => c.name },
			{
				key: 'status', label: t('admin.status'), value: (c) => c.status,
				filterMode: 'multiple',
				filterOptions: () => [...new Set([
					'ACTIVE', 'CREATING', 'PROVISIONING', 'SCALING', 'DELETING', 'ERROR', 'FAILED', 'DELETED',
					...clusters.map((cluster) => cluster.status).filter(Boolean),
				])].map((status) => ({ value: status, label: status, count: null })),
				filterSelection: () => nativeStatuses,
				onFilterChange: setNativeStatuses,
			},
			{ key: 'project', label: t('admin.project'), value: (c) => c.project_id ? ($projectNames.get(c.project_id) ?? c.project_id) : null },
			{ key: 'serverIp', label: t('admin.serverIp'), value: (c) => c.server_ip },
			{ key: 'nodes', label: t('admin.nodes'), value: (c) => c.agent_vm_ids?.length ?? 0 },
			{ key: 'version', label: t('admin.version'), value: (c) => c.k3s_version },
			{ key: 'created', label: t('admin.created'), value: (c) => c.created_at },
		],
	});
	// 슬라이드 패널
	let selectedClusterId = $state<string | null>(null);
	let selectedProjectId = $state<string | null>(null);

	function openClusterPanel(id: string) {
		const projectId = clusters.find(cluster => cluster.id === id)?.project_id;
		if (!projectId) return;
		selectedProjectId = projectId;
		selectedClusterId = id;
	}

	function closeClusterPanel() {
		selectedClusterId = null;
		selectedProjectId = null;
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load(force = false) {
		const generation = ++loadGeneration;
		const requestToken = token;
		const requestProject = projectId;
		const requestScope = $privateScope;
		const owns = () => generation === loadGeneration && requestScope === $privateScope && !!token;
		if (clusters.length === 0) loading = true;
		else refreshing = true;
		try {
			let url = '/api/v1/admin/k3s-clusters';
			const params = new URLSearchParams();
			// A nonempty comma is parsed by native Drover as an empty status set.
			if (nativeStatuses !== null) params.set('status', nativeStatuses.length ? nativeStatuses.join(',') : ',');
			if (nativeStatuses?.includes('DELETED')) params.set('include_deleted', 'true');
			if (params.toString()) url += `?${params.toString()}`;
			const response = await api.get<AdminK3sCluster[]>(url, requestToken, requestProject, { refresh: force });
			if (!owns()) return;
			clusters = response;
			error = '';
		} catch (caught) {
			if (owns()) error = caught instanceof ApiError ? caught.message : t('clusterError.loadFailed');
		} finally {
			if (owns()) { loading = false; refreshing = false; }
		}
	}

	function setNativeStatuses(values: string[] | null) {
		nativeStatuses = values === null ? null : [...values];
		clusters = [];
		void load();
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-drover',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60]
	});

	onMount(() => {
		load();
		projectNames.load(token, projectId);
	});
</script>

<!-- 슬라이드 패널 -->
{#if selectedClusterId}
	<SlidePanel onClose={closeClusterPanel} ariaLabel={t('cluster.detailLabel')}>
		<K3sClusterDetailPanel clusterId={selectedClusterId} adminProjectId={selectedProjectId ?? undefined} onClose={closeClusterPanel} adminMode={true} />
	</SlidePanel>
{/if}

<PageShell>
	<PageHeader breadcrumb="Kubernetes · Drover" title={t('cluster.title')}>
		{#snippet actions()}
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
		<RegexSearch id="admin-drover-search" bind:value={search} label={tc('table.search')} />
		<TableViewControls {view} class={view.rows.length ? 'lg:hidden' : ''} />
	</div>

	{#if error}<Alert tone="danger" title={t('clusterError.loadFailed')} class="mb-4">{#if error !== t('clusterError.loadFailed')}{error}{/if}{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => load(true)} disabled={refreshing}>{t('clusterError.reload')}</Button>{/snippet}</Alert>{/if}
	{#if loading}
		<LoadingState variant="surface" />
	{:else if view.rows.length === 0 && !error}
		<EmptyState headline={clusters.length ? tc('table.noMatches') : t('cluster.empty')} />
	{:else if view.rows.length > 0}
  <ResponsiveTable>
   {#snippet cards()}
    {#each view.rows as c (c.id)}
     <CompactResourceCard>
      <div class="flex flex-wrap items-start gap-2"><button onclick={() => openClusterPanel(c.id)} class="min-w-0 break-all text-left font-medium">{c.name}</button><StatusChip status={c.status} /></div>
      <p class="text-xs text-ink-2 break-all">{t('admin.project')}: {c.project_id ? ($projectNames.get(c.project_id) ?? c.project_id.slice(0, 8)) : '-'}</p><p class="text-xs">{t('admin.nodeCount', { current: c.agent_vm_ids?.length ?? 0, total: c.agent_count })} · {c.k3s_version || '-'}</p>
					{#if c.status_reason && (c.status === 'ERROR' || c.status === 'FAILED')}<ClusterFailure reason={c.status_reason} />{/if}
					{#snippet details()}<p class="text-xs font-mono break-all">{t('admin.serverIp')}: {c.server_ip || '-'}</p><p class="text-xs">{t('admin.created')}: {c.created_at ? c.created_at.slice(0, 10) : '-'}</p>{#if c.status_reason && c.status !== 'ERROR' && c.status !== 'FAILED'}<p class="text-xs break-all">{c.status_reason}</p>{/if}{/snippet}
     </CompactResourceCard>
    {/each}
   {/snippet}
		<TableShell density="compact">
			<table class="min-w-[58rem] text-sm">
				<thead>
					<tr class="text-xs uppercase tracking-wide">
						<TableColumnHeader {view} columnKey="name" />
						<TableColumnHeader {view} columnKey="status" />
						<TableColumnHeader {view} columnKey="project" />
						<TableColumnHeader {view} columnKey="serverIp" />
						<TableColumnHeader {view} columnKey="nodes" />
						<TableColumnHeader {view} columnKey="version" />
						<TableColumnHeader {view} columnKey="created" />
					</tr>
				</thead>
				<tbody>
					{#each view.rows as c (c.id)}
						<tr
							class="cursor-pointer text-xs transition-colors focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
							onclick={() => openClusterPanel(c.id)}
							onkeydown={(e) => e.key === 'Enter' && openClusterPanel(c.id)}
							role="button"
							tabindex="0">
							<td>
								<span class="max-md:block max-md:max-w-[66vw] max-md:truncate text-ink-0 transition-colors hover:text-accent" title={c.name}>
									{c.name}
								</span>
								{#if c.status_reason}
									{#if c.status === 'ERROR' || c.status === 'FAILED'}<ClusterFailure reason={c.status_reason} />{:else}<p class="mt-0.5 max-w-prose whitespace-pre-wrap text-[0.8125rem] text-ink-2">{c.status_reason}</p>{/if}
								{/if}
							</td>
							<td>
								<StatusChip status={c.status} />
							</td>
							<td class="text-ink-2">
								{c.project_id ? ($projectNames.get(c.project_id) ?? c.project_id.slice(0, 8)) : '-'}
							</td>
							<td class="font-mono text-ink-2">{c.server_ip || '-'}</td>
							<td class="text-ink-2">{t('admin.nodeCount', { current: c.agent_vm_ids?.length ?? 0, total: c.agent_count })}</td>
							<td class="text-ink-2">{c.k3s_version || '-'}</td>
							<td class="text-ink-2">{c.created_at ? c.created_at.slice(0, 10) : '-'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TableShell>
  </ResponsiveTable>
	{/if}
</PageShell>
