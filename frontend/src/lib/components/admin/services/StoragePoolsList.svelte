<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
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

	const poolFields: ServiceListField<StoragePool>[] = $derived([
		{ key: 'name', label: t('services.pools.name'), value: (pool) => pool.name },
		{ key: 'backend', label: t('services.pools.backend'), value: (pool) => pool.volume_backend_name, filter: true },
		{ key: 'protocol', label: t('services.pools.protocol'), value: (pool) => pool.storage_protocol, filter: true },
		{ key: 'vendor', label: t('services.pools.vendor'), value: (pool) => pool.vendor_name, filter: true },
		{ key: 'driver', label: t('services.pools.driver'), value: (pool) => pool.driver_version },
		{
			key: 'total_capacity',
			label: t('services.pools.totalCapacity'),
			value: (pool) => pool.total_capacity_gb,
			search: false,
		},
		{
			key: 'free_capacity',
			label: t('services.pools.freeCapacity'),
			value: (pool) => pool.free_capacity_gb,
			search: false,
		},
		{
			key: 'allocated_capacity',
			label: t('services.pools.allocatedCapacity'),
			value: (pool) => pool.allocated_capacity_gb,
			search: false,
		},
	]);

	const sortOptions = $derived([
		{ key: 'name', label: t('services.pools.name') },
		{ key: 'backend', label: t('services.pools.backend') },
		{ key: 'protocol', label: t('services.pools.protocol') },
		{ key: 'vendor', label: t('services.pools.vendor') },
		{ key: 'total_capacity', label: t('services.pools.totalCapacity') },
		{ key: 'free_capacity', label: t('services.pools.freeCapacity') },
		{ key: 'allocated_capacity', label: t('services.pools.allocatedCapacity') },
	]);

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
		searchPlaceholder={t('services.pools.searchPlaceholder')}
	/>
	{#if loading && pools.length === 0}
		<LoadingSkeleton variant="table" rows={4} />
	{:else if pools.length === 0}
		<EmptyState headline={emptyMessage} />
	{:else if visiblePools.length === 0}
		<EmptyState headline={t('services.pools.noMatches')} description={t('services.list.adjustFilters')} />
	{:else}
		<div class="space-y-4">
			{#each visiblePools as pool (pool.name)}
				{@const usedGb = pool.total_capacity_gb - pool.free_capacity_gb}
				{@const pct = pool.total_capacity_gb > 0 ? Math.min(100, (usedGb / pool.total_capacity_gb) * 100) : 0}
				<article aria-label={t('services.pools.poolLabel', { name: pool.name })} class="bg-surface-base border border-line rounded-xl p-5">
					<div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
						<div>
							<div class="text-sm font-medium text-ink-0">{pool.name}</div>
							<div class="text-xs text-ink-2 mt-0.5">
								{#if pool.storage_protocol}<span class="mr-3">{t('services.pools.protocolValue', { protocol: pool.storage_protocol })}</span>{/if}
								{#if pool.volume_backend_name}<span class="mr-3">{t('services.pools.backendValue', { backend: pool.volume_backend_name })}</span>{/if}
								{#if pool.vendor_name}<span>{t('services.pools.vendorValue', { vendor: pool.vendor_name })}</span>{/if}
							</div>
						</div>
						<div class="text-right">
							<div class="text-sm text-ink-0">
								<span class="font-medium">{usedGb.toFixed(1)}</span>
								<span class="text-ink-2"> / {pool.total_capacity_gb.toFixed(1)} GiB</span>
							</div>
							<div class="text-xs text-ink-2">{t('services.pools.freeValue', { capacity: pool.free_capacity_gb.toFixed(1) })}</div>
						</div>
					</div>
					<div class="w-full h-2 bg-surface-sunken rounded-full overflow-hidden">
						<div
							class="h-full rounded-full transition-all"
							style="width: {pct.toFixed(1)}%; background: {pct > 85 ? 'var(--gradient-usage-danger)' : pct > 65 ? 'var(--gradient-usage-warning)' : 'var(--gradient-usage)'}"
						></div>
					</div>
					<div class="text-xs text-ink-2 mt-1">{t('services.pools.usedPercent', { percent: pct.toFixed(1) })}</div>
				</article>
			{/each}
		</div>
	{/if}
</div>
