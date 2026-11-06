<script lang="ts">
	import { t as commonT } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t } from '$lib/i18n/ns/admin-network';
	import type { RouterInfo } from '$lib/types/networks';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	const id = $props.id();
	let search = $state('');
	const columns: TableColumn<RouterInfo>[] = $derived([
		{ key: 'name', label: t('routerTable.name'), value: (row) => row.name || row.id },
		{ key: 'gateway', label: t('routerTable.externalGateway'), value: (row) => row.external_gateway_network_id },
		{ key: 'subnets', label: t('routerTable.connectedSubnets'), value: (row) => row.connected_subnet_ids.length },
	]);
	const view = createTableView({ locale: intlLocale, rows: () => routers, columns: () => columns, search: () => search,
		searchable: (row) => [row.id, row.name, row.external_gateway_network_id, ...row.connected_subnet_ids].filter((value) => value != null).map(String) });

	let { routers }: { routers: RouterInfo[] } = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-6">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('routerTable.title')}</h2>
	<RegexSearch id="{id}-search" bind:value={search} />
	<TableViewControls {view} />
	{#if routers.length > 0 && view.rows.length === 0}<p class="my-3 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
	<ResponsiveTable>
		{#snippet cards()}
			{#each view.rows as router (router.id)}
				<CompactResourceCard>
					<h3 class="break-all font-medium text-ink-0">{router.name || router.id.slice(0, 12)}</h3><p class="text-xs text-ink-2">{t('routerTable.subnetCount', { count: router.connected_subnet_ids.length })}</p><p class="break-all text-xs text-ink-2">{t('routerTable.externalGateway')}: {router.external_gateway_network_id?.slice(0, 12) ?? '-'}</p>
					{#snippet details()}<div class="space-y-2 break-all font-mono text-xs text-ink-2"><p>{router.id}</p><p>{router.external_gateway_network_id ?? '-'}</p>{#each router.connected_subnet_ids as id}<p>{id}</p>{/each}</div>{/snippet}
				</CompactResourceCard>
			{/each}
		{/snippet}
	<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				{#each columns as column (column.key)}<TableColumnHeader {view} columnKey={column.key} />{/each}
			</tr>
		</thead>
		<tbody>
			{#each view.rows as router (router.id)}
				<tr class="border-b border-line/50">
					<td class="py-2 pr-6 text-ink-2"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={router.name || router.id.slice(0, 12) + '...'}>{router.name || router.id.slice(0, 12) + '...'}</span></td>
					<td class="py-2 pr-6">
						{#if router.external_gateway_network_id}
							<span class="text-orange-300 text-xs font-mono">{router.external_gateway_network_id.slice(0, 12)}...</span>
						{:else}
							<span class="text-ink-2 text-xs">-</span>
						{/if}
					</td>
					<td class="py-2 text-ink-2 text-xs">
						{t('routerTable.subnetCount', { count: router.connected_subnet_ids.length })}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
	</div>
	</ResponsiveTable>
</div>
