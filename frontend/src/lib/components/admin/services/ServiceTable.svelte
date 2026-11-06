<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import type { Service } from '$lib/types/adminServices';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import { fmtTime, type ServiceColumn } from './serviceColumns.js';
	import { serviceTimestamp } from './serviceList';
	const id = $props.id();

	let {
		services,
		columns,
		loading,
		emptyMessage,
		search = $bindable(''),
	}: {
		services: Service[];
		columns: ServiceColumn[];
		loading: boolean;
		emptyMessage: string;
		search?: string;
	} = $props();

	function serviceValue(service: Service, column: ServiceColumn['type']): string | null {
		switch (column) {
			case 'binary': return service.binary;
			case 'host': return service.host;
			case 'zone': return service.zone;
			case 'status': return service.status;
			case 'state': return service.state;
			case 'disabledReason': return service.disabled_reason;
			case 'updated': return service.updated_at;
		}
	}

	const fields: TableColumn<Service>[] = $derived(columns.map((column) => ({
		key: column.type,
		label: t(`services.columns.${column.type}`),
		value: (service: Service) => column.type === 'updated' ? serviceTimestamp(service.updated_at) : serviceValue(service, column.type),
		format: (_value: unknown, service: Service) => column.type === 'updated' ? fmtTime(service.updated_at) : serviceValue(service, column.type) ?? t('services.state.unknown'),
	})));
	const view = createTableView({ locale: intlLocale, rows: () => services, columns: () => fields, search: () => search,
		searchable: (service) => [service.binary, service.host, service.zone, service.status, service.state, service.disabled_reason, service.updated_at].filter((value) => value != null).map(String) });
	const displayedServices = $derived(view.rows);
</script>

<RegexSearch id="{id}-search" bind:value={search} placeholder={t('services.table.searchPlaceholder')} />
<TableViewControls {view} />

{#if services.length === 0}
	{#if loading}
		<LoadingState variant="section" />
	{:else}
		<EmptyState headline={emptyMessage} />
	{/if}
{:else if displayedServices.length === 0}
	<EmptyState headline={t('services.table.noMatches')} description={t('services.list.adjustFilters')} />
{/if}
	<ResponsiveTable>
		{#snippet cards()}
			{#each displayedServices as service (service.id || service.binary + service.host)}
				<CompactResourceCard>
					<div class="flex flex-wrap items-start justify-between gap-2">
						<h3 class="min-w-0 break-all font-mono text-sm font-medium text-ink-0">{service.binary}</h3>
						<div class="flex flex-wrap gap-1">
							{#if columns.some((column) => column.type === 'state')}<StatusChip status={service.state} />{/if}
							{#if columns.some((column) => column.type === 'status')}<StatusChip status={service.status} />{/if}
						</div>
					</div>
					<dl class="grid gap-1 text-xs text-ink-2">
						<div class="flex flex-wrap justify-between gap-2"><dt>{t('services.columns.host')}</dt><dd class="break-all">{service.host}</dd></div>
						{#if columns.some((column) => column.type === 'zone')}<div class="flex flex-wrap justify-between gap-2"><dt>{t('services.columns.zone')}</dt><dd class="break-all">{service.zone || '-'}</dd></div>{/if}
					</dl>
					{#snippet details()}
						<dl class="grid gap-2 text-xs text-ink-2">
							<div><dt>{t('services.columns.disabledReason')}</dt><dd class="break-words">{service.disabled_reason || '-'}</dd></div>
							<div><dt>{t('services.columns.updated')}</dt><dd class="tabular-nums">{fmtTime(service.updated_at)}</dd></div>
						</dl>
					{/snippet}
				</CompactResourceCard>
			{/each}
		{/snippet}
	<TableShell density="compact">
		<table aria-label={t('services.table.listLabel')}>
			<thead>
				<tr>
					{#each columns as column (column.type)}
						<TableColumnHeader {view} columnKey={column.type} />
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each displayedServices as service (service.id || service.binary + service.host)}
					<tr>
						{#each columns as column (column.type)}
							<td>
								{#if column.type === 'binary'}
									<span class="font-mono text-ink-0">{service.binary}</span>
								{:else if column.type === 'host'}
									<span class="text-ink-2">{service.host}</span>
								{:else if column.type === 'zone'}
									<span class="text-ink-2">{service.zone}</span>
								{:else if column.type === 'status'}
									<StatusChip status={service.status} />
								{:else if column.type === 'state'}
									<StatusChip status={service.state} />
								{:else if column.type === 'disabledReason'}
									<span class="text-ink-2">{service.disabled_reason || '-'}</span>
								{:else if column.type === 'updated'}
									<span class="tabular-nums text-ink-2">{fmtTime(service.updated_at)}</span>
								{/if}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</TableShell>
	</ResponsiveTable>
