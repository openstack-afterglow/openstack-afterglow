<script lang="ts">
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import type { StoragePool } from '$lib/types/adminServices';
	import ServiceListControls from './ServiceListControls.svelte';
	import {
		buildServiceFilters,
		createServiceListState,
		filterAndSortRows,
		type ServiceListField,
		type ServiceListState,
	} from './serviceList';

	const poolFields: ServiceListField<StoragePool>[] = [
		{ key: 'name', label: '풀 이름', value: (pool) => pool.name },
		{ key: 'backend', label: '백엔드', value: (pool) => pool.volume_backend_name, filter: true },
		{ key: 'protocol', label: '프로토콜', value: (pool) => pool.storage_protocol, filter: true },
		{ key: 'vendor', label: '벤더', value: (pool) => pool.vendor_name, filter: true },
		{ key: 'driver', label: '드라이버', value: (pool) => pool.driver_version },
		{
			key: 'total_capacity',
			label: '총 용량',
			value: (pool) => pool.total_capacity_gb,
			search: false,
		},
		{
			key: 'free_capacity',
			label: '여유 용량',
			value: (pool) => pool.free_capacity_gb,
			search: false,
		},
		{
			key: 'allocated_capacity',
			label: '할당 용량',
			value: (pool) => pool.allocated_capacity_gb,
			search: false,
		},
	];

	const sortOptions = [
		{ key: 'name', label: '풀 이름' },
		{ key: 'backend', label: '백엔드' },
		{ key: 'protocol', label: '프로토콜' },
		{ key: 'vendor', label: '벤더' },
		{ key: 'total_capacity', label: '총 용량' },
		{ key: 'free_capacity', label: '여유 용량' },
		{ key: 'allocated_capacity', label: '할당 용량' },
	];

	let {
		pools,
		loading,
		emptyMessage,
		view = $bindable<ServiceListState>(createServiceListState()),
	}: {
		pools: StoragePool[];
		loading: boolean;
		emptyMessage: string;
		view?: ServiceListState;
	} = $props();

	const filters = $derived(buildServiceFilters(pools, poolFields));
	const visiblePools = $derived(filterAndSortRows(pools, poolFields, view));
</script>

<div>
	<ServiceListControls
		bind:view
		{filters}
		{sortOptions}
		total={pools.length}
		count={visiblePools.length}
		{loading}
		searchPlaceholder="풀 이름, 백엔드, 프로토콜, 벤더, 드라이버 검색"
	/>
	{#if loading && pools.length === 0}
		<LoadingSkeleton variant="table" rows={4} />
	{:else if pools.length === 0}
		<EmptyState headline={emptyMessage} />
	{:else if visiblePools.length === 0}
		<EmptyState headline="일치하는 스토리지 풀이 없습니다" description="필터나 검색어를 조정해 보세요." />
	{:else}
		<div class="space-y-4">
			{#each visiblePools as pool (pool.name)}
				{@const usedGb = pool.total_capacity_gb - pool.free_capacity_gb}
				{@const pct = pool.total_capacity_gb > 0 ? Math.min(100, (usedGb / pool.total_capacity_gb) * 100) : 0}
				<article aria-label={`${pool.name} 스토리지 풀`} class="bg-surface-base border border-line rounded-xl p-5">
					<div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
						<div>
							<div class="text-sm font-medium text-ink-0">{pool.name}</div>
							<div class="text-xs text-ink-2 mt-0.5">
								{#if pool.storage_protocol}<span class="mr-3">Protocol: {pool.storage_protocol}</span>{/if}
								{#if pool.volume_backend_name}<span class="mr-3">Backend: {pool.volume_backend_name}</span>{/if}
								{#if pool.vendor_name}<span>Vendor: {pool.vendor_name}</span>{/if}
							</div>
						</div>
						<div class="text-right">
							<div class="text-sm text-ink-0">
								<span class="font-medium">{usedGb.toFixed(1)}</span>
								<span class="text-ink-2"> / {pool.total_capacity_gb.toFixed(1)} GiB</span>
							</div>
							<div class="text-xs text-ink-2">여유: {pool.free_capacity_gb.toFixed(1)} GiB</div>
						</div>
					</div>
					<div class="w-full h-2 bg-surface-sunken rounded-full overflow-hidden">
						<div
							class="h-full rounded-full transition-all"
							style="width: {pct.toFixed(1)}%; background: {pct > 85 ? 'var(--gradient-usage-danger)' : pct > 65 ? 'var(--gradient-usage-warning)' : 'var(--gradient-usage)'}"
						></div>
					</div>
					<div class="text-xs text-ink-2 mt-1">{pct.toFixed(1)}% 사용 중</div>
				</article>
			{/each}
		</div>
	{/if}
</div>
