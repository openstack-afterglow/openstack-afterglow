<script lang="ts">
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t as scopeT } from '$lib/i18n/ns/domain-admin';
	let inventoryError = $state('');
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import { t } from '$lib/i18n/ns/admin-system';
	import { onDestroy, onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api as baseApi } from '$lib/api/client';
	import { createAdminInventoryApi } from '$lib/api/adminInventoryScope';
	const api = createAdminInventoryApi(baseApi);
	onDestroy(api.dispose);
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import ContainerDetailPanel from '$lib/components/ContainerDetailPanel.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t as tc } from '$lib/i18n/ns/common';

	interface AdminContainer {
		uuid: string;
		name: string;
		status: string;
		image: string | null;
		cpu: number | null;
		memory: string | null;
		host: string | null;
		created_at: string | null;
		project_id: string | null;
	}

	let containers = $state<AdminContainer[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let selectedContainerId = $state<string | null>(null);
	let search = $state('');
	const view = createTableView<AdminContainer>({
		rows: () => containers,
		search: () => search,
		searchable: (c) => [c.name, c.uuid, c.status, c.image, c.cpu, c.memory, c.host, c.created_at, c.project_id].map((value) => String(value ?? '')),
		locale: intlLocale,
		columns: () => [
			{ key: 'name', label: t('containers.name'), value: (c) => c.name || c.uuid },
			{ key: 'status', label: t('containers.status'), value: (c) => c.status },
			{ key: 'image', label: t('containers.image'), value: (c) => c.image },
			{ key: 'cpu', label: t('containers.cpu'), value: (c) => c.cpu },
			{ key: 'memory', label: t('containers.memory'), value: (c) => c.memory || null },
			{ key: 'host', label: t('containers.host'), value: (c) => c.host },
			{ key: 'created', label: t('containers.created'), value: (c) => c.created_at },
		],
	});

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load(force = false) {
		if (containers.length === 0) loading = true;
		else refreshing = true;
		inventoryError = '';
		try {
			containers = await api.get<AdminContainer[]>('/api/v1/admin/all-containers', token, projectId, { refresh: force });
		} catch (reason) {
			containers = []; inventoryError = reason instanceof Error ? reason.message : scopeT('state.unavailable');
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-containers',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60]
	});

	onMount(load);
</script>

<PageShell>
	<div data-tour="admin-containers-header">
	<PageHeader breadcrumb={t('containers.breadcrumb')} title={t('containers.title')}>
		{#snippet actions()}
			<TutorialStartButton tour="admin-containers" compactOnMobile />
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={ar.refresh}
			/>
		{/snippet}
	</PageHeader>
	</div>

	<div data-tour="admin-containers-list">
	<div class="mb-4 space-y-3">
		<RegexSearch id="admin-containers-search" bind:value={search} label={tc('table.search')} />
		<TableViewControls {view} class={view.rows.length ? 'lg:hidden' : ''} />
	</div>
	{#if inventoryError}<Alert tone="danger">{inventoryError}</Alert>
	{:else if loading}
		<LoadingState variant="surface" />
	{:else if view.rows.length === 0}
		<div class="text-ink-2 text-sm" data-tour="admin-containers-ready">{containers.length ? tc('table.noMatches') : t('containers.empty')}</div>
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				<div class="contents" data-tour="admin-containers-ready">
				{#each view.rows as c, index (c.uuid)}
					<CompactResourceCard selected={selectedContainerId === c.uuid}>
						<div class="flex items-start justify-between gap-2"><button type="button" class="min-h-11 break-all text-left font-medium text-ink-0" data-tour={index === 0 ? 'admin-containers-row' : undefined} onclick={() => selectedContainerId = c.uuid}>{c.name || c.uuid.slice(0, 8)}</button><StatusChip status={c.status} /></div>
						<div class="space-y-1 text-xs text-ink-2"><p>{t('containers.cpu')}: {c.cpu ?? '-'} · {t('containers.memory')}: {c.memory || '-'}</p><p>{t('containers.host')}: {c.host || '-'}</p></div>
						{#snippet details()}<div class="space-y-2 break-all text-xs text-ink-2"><p class="font-mono">{c.uuid}</p><p>{t('containers.image')}: {c.image || '-'}</p><p>{t('containers.created')}: {c.created_at?.slice(0, 10) ?? '-'}</p></div>{/snippet}
					</CompactResourceCard>
				{/each}
				</div>
			{/snippet}
		<div class="overflow-x-auto" data-tour="admin-containers-ready">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<TableColumnHeader {view} columnKey="name" />
						<TableColumnHeader {view} columnKey="status" />
						<TableColumnHeader {view} columnKey="image" />
						<TableColumnHeader {view} columnKey="cpu" />
						<TableColumnHeader {view} columnKey="memory" />
						<TableColumnHeader {view} columnKey="host" />
						<TableColumnHeader {view} columnKey="created" />
					</tr>
				</thead>
				<tbody>
					{#each view.rows as c, index (c.uuid)}
						<tr
							class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors cursor-pointer {selectedContainerId === c.uuid ? 'bg-surface-sunken/50' : ''}"
							onclick={() => (selectedContainerId = c.uuid)}
							onkeydown={(e) => e.key === 'Enter' && (selectedContainerId = c.uuid)}
							role="button"
							tabindex="0"
							data-tour={index === 0 ? 'admin-containers-row' : undefined}
						>
							<td class="py-2 pr-4 text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={c.name || c.uuid}>{c.name || c.uuid.slice(0, 8)}</span></td>
							<td class="py-2 pr-4"><StatusChip status={c.status} /></td>
							<td class="py-2 pr-4 text-ink-2 font-mono text-xs">{c.image || '-'}</td>
							<td class="py-2 pr-4 text-ink-2">{c.cpu ?? '-'}</td>
							<td class="py-2 pr-4 text-ink-2">{c.memory || '-'}</td>
							<td class="py-2 pr-4 text-ink-2">{c.host || '-'}</td>
							<td class="py-2 text-ink-2">{c.created_at?.slice(0, 10) ?? '-'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		</ResponsiveTable>
	{/if}
	</div>
</PageShell>

{#if selectedContainerId}
	<SlidePanel onClose={() => (selectedContainerId = null)} ariaLabel={t('containers.details')} width="w-full md:w-[480px]" dataTour="admin-containers-detail">
		<ContainerDetailPanel
			containerId={selectedContainerId}
			onClose={() => (selectedContainerId = null)}
			adminMode={true}
			onRefresh={load}
		/>
	</SlidePanel>
{/if}