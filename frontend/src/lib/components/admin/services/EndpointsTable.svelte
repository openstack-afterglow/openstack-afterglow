<script lang="ts">
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

	const endpointFields: ServiceListField<EndpointGroup>[] = [
		{ key: 'name', label: '이름', value: (endpoint) => endpoint.name, filter: true },
		{ key: 'service', label: '서비스 유형', value: (endpoint) => endpoint.service, filter: true },
		{ key: 'region', label: '리전', value: (endpoint) => endpoint.region, filter: true },
		{
			key: 'endpoints',
			label: '엔드포인트 URL',
			value: (endpoint) => Object.values(endpoint.endpoints).join(' '),
			search: true,
		},
	];

	const sortOptions = [
		{ key: 'name', label: '이름' },
		{ key: 'service', label: '서비스 유형' },
		{ key: 'region', label: '리전' },
	];

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
		searchPlaceholder="이름, 서비스 유형, 리전, 엔드포인트 URL 검색"
		defaultSortKey="name"
	/>

	{#if loading && endpoints.length === 0}
		<LoadingSkeleton variant="table" rows={8} />
	{:else if endpoints.length === 0}
		<EmptyState headline={emptyMessage} />
	{:else if visibleEndpoints.length === 0}
		<EmptyState headline="일치하는 엔드포인트가 없습니다" description="필터나 검색어를 조정해 보세요." />
	{:else}
		<TableShell density="compact">
			<table aria-label="엔드포인트 목록">
				<thead>
					<tr>
						<ServiceSortHeader bind:view column="name" label="이름" />
						<ServiceSortHeader bind:view column="service" label="서비스 유형" />
						<ServiceSortHeader bind:view column="region" label="리전" />
						<th scope="col">엔드포인트</th>
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
											<span class="text-ink-2 w-14 shrink-0 font-medium">{interfaceName}:</span>
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
