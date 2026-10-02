<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import type { EndpointGroup } from '$lib/types/adminServices';
	import ServiceListControls from './ServiceListControls.svelte';
	import ServiceSortHeader from './ServiceSortHeader.svelte';
	import {
		buildServiceFilters,
		createServiceListState,
		filterAndSortRows,
		type ServiceListField,
		type ServiceListState,
	} from './serviceList';

	const endpointFields: ServiceListField<EndpointGroup>[] = $derived([
		{ key: 'name', label: t('services.endpoints.name'), value: (endpoint) => endpoint.name, filter: true },
		{ key: 'service', label: t('services.endpoints.serviceType'), value: (endpoint) => endpoint.service, filter: true },
		{ key: 'region', label: t('services.endpoints.region'), value: (endpoint) => endpoint.region, filter: true },
		{
			key: 'endpoints',
			label: t('services.endpoints.url'),
			value: (endpoint) => Object.values(endpoint.endpoints).join(' '),
			search: true,
		},
	]);

	const sortOptions = $derived([
		{ key: 'name', label: t('services.endpoints.name') },
		{ key: 'service', label: t('services.endpoints.serviceType') },
		{ key: 'region', label: t('services.endpoints.region') },
	]);

	let {
		endpoints,
		loading,
		emptyMessage,
		view = $bindable<ServiceListState>(createServiceListState('name')),
	}: {
		endpoints: EndpointGroup[];
		loading: boolean;
		emptyMessage: string;
		view?: ServiceListState;
	} = $props();

	const filters = $derived(buildServiceFilters(endpoints, endpointFields));
	const visibleEndpoints = $derived(filterAndSortRows(endpoints, endpointFields, view));
</script>

<div>
	<ServiceListControls
		bind:view
		{filters}
		{sortOptions}
		total={endpoints.length}
		count={visibleEndpoints.length}
		{loading}
		searchPlaceholder={t('services.endpoints.searchPlaceholder')}
		defaultSortKey="name"
	/>

	{#if loading && endpoints.length === 0}
		<LoadingSkeleton variant="table" rows={8} />
	{:else if endpoints.length === 0}
		<EmptyState headline={emptyMessage} />
	{:else if visibleEndpoints.length === 0}
		<EmptyState headline={t('services.endpoints.noMatches')} description={t('services.list.adjustFilters')} />
	{:else}
		<TableShell density="compact">
			<table aria-label={t('services.endpoints.listLabel')}>
				<thead>
					<tr>
						<ServiceSortHeader bind:view column="name" label={t('services.endpoints.name')} />
						<ServiceSortHeader bind:view column="service" label={t('services.endpoints.serviceType')} />
						<ServiceSortHeader bind:view column="region" label={t('services.endpoints.region')} />
						<th scope="col">{t('services.endpoints.endpoints')}</th>
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
	{/if}
</div>
