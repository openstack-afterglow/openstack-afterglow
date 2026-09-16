<script lang="ts">
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import type { Service } from '$lib/types/adminServices';
	import ServiceListControls from './ServiceListControls.svelte';
	import ServiceSortHeader from './ServiceSortHeader.svelte';
	import { fmtTime, type ServiceColumn } from './serviceColumns.js';
	import {
		buildServiceFilters,
		createServiceListState,
		filterAndSortRows,
		serviceTimestamp,
		type ServiceListField,
		type ServiceListState,
	} from './serviceList';

	let {
		services,
		columns,
		loading,
		emptyMessage,
		view = $bindable(createServiceListState()),
	}: {
		services: Service[];
		columns: ServiceColumn[];
		loading: boolean;
		emptyMessage: string;
		view?: ServiceListState;
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

	const fields = $derived([
		...columns.map((column): ServiceListField<Service> => ({
			key: column.type,
			label: column.label,
			value: (service) => serviceValue(service, column.type),
			filter: ['binary', 'host', 'zone', 'status', 'state'].includes(column.type),
			sortValue: column.type === 'updated' ? (service) => serviceTimestamp(service.updated_at) : undefined,
		})),
		...(['disabledReason', 'updated'] as const)
			.filter((type) => !columns.some((column) => column.type === type))
			.map((type): ServiceListField<Service> => ({
				key: type,
				label: type === 'disabledReason' ? 'Disabled Reason' : 'Updated',
				value: (service) => serviceValue(service, type),
				sortValue: type === 'updated' ? (service) => serviceTimestamp(service.updated_at) : undefined,
			})),
	]);
	const filters = $derived(buildServiceFilters(services, fields));
	const sortOptions = $derived(columns.map(({ type, label }) => ({ key: type, label })));
	const displayedServices = $derived(filterAndSortRows(services, fields, view));
</script>

<ServiceListControls
	bind:view
	{filters}
	{sortOptions}
	total={services.length}
	count={displayedServices.length}
	{loading}
	searchPlaceholder="Binary, Host, Zone, Disabled Reason, Updated 검색"
/>

{#if services.length === 0}
	{#if loading}
		<LoadingSkeleton variant="table" rows={8} />
	{:else}
		<EmptyState headline={emptyMessage} />
	{/if}
{:else if displayedServices.length === 0}
	<EmptyState headline="일치하는 서비스가 없습니다" description="필터나 검색어를 조정해 보세요." />
{:else}
	<TableShell density="compact">
		<table aria-label="서비스 목록">
			<thead>
				<tr>
					{#each columns as column (column.type)}
						<ServiceSortHeader bind:view column={column.type} label={column.label} />
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
{/if}
