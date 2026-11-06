<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import type { EndpointGroup } from '$lib/types/adminServices';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	const id = $props.id();
	const endpointFields: TableColumn<EndpointGroup>[] = $derived([
		{ key: 'name', label: t('services.endpoints.name'), value: (endpoint) => endpoint.name },
		{ key: 'service', label: t('services.endpoints.serviceType'), value: (endpoint) => endpoint.service },
		{ key: 'region', label: t('services.endpoints.region'), value: (endpoint) => endpoint.region },
		{ key: 'endpoints', label: t('services.endpoints.endpoints'), value: (endpoint) => Object.entries(endpoint.endpoints).map(([name, url]) => `${name}: ${url}`).join(' ') },
	]);

	let {
		endpoints,
		loading,
		emptyMessage,
		search = $bindable(''),
	}: {
		endpoints: EndpointGroup[];
		loading: boolean;
		emptyMessage: string;
		search?: string;
	} = $props();

	const view = createTableView({ locale: intlLocale, rows: () => endpoints, columns: () => endpointFields, search: () => search,
		searchable: (row) => [row.name, row.service, row.region, ...Object.keys(row.endpoints), ...Object.values(row.endpoints)] });
	const visibleEndpoints = $derived(view.rows);
</script>

<div>
	<RegexSearch id="{id}-search" bind:value={search} placeholder={t('services.endpoints.searchPlaceholder')} />
	<TableViewControls {view} />

	{#if loading && endpoints.length === 0}
		<LoadingState variant="section" />
	{:else if endpoints.length === 0}
		<EmptyState headline={emptyMessage} />
	{:else if visibleEndpoints.length === 0}
		<EmptyState headline={t('services.endpoints.noMatches')} description={t('services.list.adjustFilters')} />
	{/if}
		<ResponsiveTable>
			{#snippet cards()}
				{#each visibleEndpoints as endpoint (endpoint.service_id)}
					<CompactResourceCard>
						<h3 class="break-words text-sm font-medium text-ink-0">{endpoint.name}</h3>
						<dl class="grid gap-1 text-xs text-ink-2">
							<div class="flex flex-wrap justify-between gap-2"><dt>{t('services.endpoints.serviceType')}</dt><dd class="break-all">{endpoint.service}</dd></div>
							<div class="flex flex-wrap justify-between gap-2"><dt>{t('services.endpoints.region')}</dt><dd class="break-all">{endpoint.region}</dd></div>
						</dl>
						{#snippet details()}
							<dl class="grid gap-2 text-xs text-ink-2">
								{#each Object.entries(endpoint.endpoints).sort(([left], [right]) => left.localeCompare(right)) as [interfaceName, url]}
									<div><dt class="font-medium">{t('services.endpoints.interfaceLabel', { interfaceName })}</dt><dd class="break-all font-mono">{url}</dd></div>
								{/each}
							</dl>
						{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
		<TableShell density="compact">
			<table aria-label={t('services.endpoints.listLabel')}>
				<thead>
					<tr>
						{#each endpointFields as field (field.key)}<TableColumnHeader {view} columnKey={field.key} />{/each}
					</tr>
				</thead>
				<tbody>
					{#each visibleEndpoints as endpoint (endpoint.service_id)}
						<tr class="align-top">
							<td class="text-ink-0 font-medium">{endpoint.name}</td>
							<td class="text-ink-2">{endpoint.service}</td>
							<td class="text-ink-2">{endpoint.region}</td>
							<td>
								<div class="space-y-1">
									{#each Object.entries(endpoint.endpoints).sort(([left], [right]) => left.localeCompare(right)) as [interfaceName, url]}
										<div class="flex items-start gap-2">
											<span class="text-ink-2 w-14 shrink-0 font-medium">{t('services.endpoints.interfaceLabel', { interfaceName })}</span>
											<span class="text-ink-2 font-mono break-all">{url}</span>
										</div>
									{/each}
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TableShell>
		</ResponsiveTable>
</div>
