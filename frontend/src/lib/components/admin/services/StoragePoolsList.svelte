<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { t } from '$lib/i18n/ns/admin-ops';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import type { StoragePool } from '$lib/types/adminServices';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	const id = $props.id();
	const poolFields: TableColumn<StoragePool>[] = $derived([
		{ key: 'name', label: t('services.pools.name'), value: (pool) => pool.name },
		{ key: 'backend', label: t('services.pools.backend'), value: (pool) => pool.volume_backend_name },
		{ key: 'protocol', label: t('services.pools.protocol'), value: (pool) => pool.storage_protocol },
		{ key: 'vendor', label: t('services.pools.vendor'), value: (pool) => pool.vendor_name },
		{ key: 'driver', label: t('services.pools.driver'), value: (pool) => pool.driver_version },
		{ key: 'total_capacity', label: t('services.pools.totalCapacity'), value: (pool) => pool.total_capacity_gb },
		{ key: 'free_capacity', label: t('services.pools.freeCapacity'), value: (pool) => pool.free_capacity_gb },
		{ key: 'allocated_capacity', label: t('services.pools.allocatedCapacity'), value: (pool) => pool.allocated_capacity_gb },
	]);

	let {
		pools,
		loading,
		emptyMessage,
		search = $bindable(''),
	}: {
		pools: StoragePool[];
		loading: boolean;
		emptyMessage: string;
		search?: string;
	} = $props();

	const view = createTableView({ locale: intlLocale, rows: () => pools, columns: () => poolFields, search: () => search });
	const visiblePools = $derived(view.rows);
</script>

<div>
	<RegexSearch id="{id}-search" bind:value={search} placeholder={t('services.pools.searchPlaceholder')} />
	<TableViewControls {view} class="" />
	{#if loading && pools.length === 0}
		<LoadingState variant="section" />
	{:else if pools.length === 0}
		<EmptyState headline={emptyMessage} />
	{:else if visiblePools.length === 0}
		<EmptyState headline={t('services.pools.noMatches')} description={t('services.list.adjustFilters')} />
	{:else}
		<ResponsiveTable>
			{#snippet cards()}
				{#each visiblePools as pool (pool.name)}
					{@const usedGb = pool.total_capacity_gb - pool.free_capacity_gb}
					{@const pct = pool.total_capacity_gb > 0 ? Math.min(100, (usedGb / pool.total_capacity_gb) * 100) : 0}
					<CompactResourceCard>
						<h3 class="break-all text-sm font-medium text-ink-0">{pool.name}</h3>
						<dl class="grid gap-1 text-xs text-ink-2">
							<div class="flex flex-wrap justify-between gap-2"><dt>{t('services.pools.totalCapacity')}</dt><dd class="tabular-nums">{pool.total_capacity_gb.toFixed(1)} GiB</dd></div>
							<div class="flex flex-wrap justify-between gap-2"><dt>{t('services.pools.freeCapacity')}</dt><dd class="tabular-nums">{pool.free_capacity_gb.toFixed(1)} GiB</dd></div>
						</dl>
						<p class="text-xs text-ink-2">{t('services.pools.usedPercent', { percent: pct.toFixed(1) })}</p>
						{#snippet details()}
							<p class="text-xs text-ink-2 tabular-nums">{usedGb.toFixed(1)} / {pool.total_capacity_gb.toFixed(1)} GiB</p>
							<dl class="grid gap-2 text-xs text-ink-2">
								<div><dt>{t('services.pools.protocol')}</dt><dd class="break-all">{pool.storage_protocol || '-'}</dd></div>
								<div><dt>{t('services.pools.backend')}</dt><dd class="break-all">{pool.volume_backend_name || '-'}</dd></div>
								<div><dt>{t('services.pools.vendor')}</dt><dd class="break-all">{pool.vendor_name || '-'}</dd></div>
							</dl>
						{/snippet}
					</CompactResourceCard>
				{/each}
			{/snippet}
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
					<BklitChart
						spec={{ kind: 'gauge', value: Math.max(0, pct), color: pct > 85 ? 'var(--color-state-danger)' : pct > 65 ? 'var(--color-state-warning)' : 'var(--color-accent)', track: 'var(--color-surface-sunken)' }}
						height={8}
						decorative
					/>
					<div class="text-xs text-ink-2 mt-1">{t('services.pools.usedPercent', { percent: pct.toFixed(1) })}</div>
				</article>
			{/each}
		</div>
		</ResponsiveTable>
	{/if}
</div>
