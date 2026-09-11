<script lang="ts">
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';

	interface StoragePool {
		name: string;
		volume_backend_name: string;
		driver_version: string;
		storage_protocol: string;
		vendor_name: string;
		total_capacity_gb: number;
		free_capacity_gb: number;
		allocated_capacity_gb: number;
	}

	let {
		pools,
		loading,
		emptyMessage,
	}: {
		pools: StoragePool[];
		loading: boolean;
		emptyMessage: string;
	} = $props();
</script>

{#if loading}
	<LoadingSkeleton variant="table" rows={4} />
{:else if pools.length === 0}
	<div class="text-ink-3 text-sm py-8 text-center">{emptyMessage}</div>
{:else}
	<div class="space-y-4">
		{#each pools as pool (pool.name)}
			{@const usedGb = pool.total_capacity_gb - pool.free_capacity_gb}
			{@const pct = pool.total_capacity_gb > 0 ? Math.min(100, (usedGb / pool.total_capacity_gb) * 100) : 0}
			<div class="bg-surface-base border border-line rounded-xl p-5">
				<div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
					<div>
						<div class="text-sm font-medium text-ink-0">{pool.name}</div>
						<div class="text-xs text-ink-3 mt-0.5">
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
						<div class="text-xs text-ink-3">여유: {pool.free_capacity_gb.toFixed(1)} GiB</div>
					</div>
				</div>
				<div class="w-full h-2 bg-surface-sunken rounded-full overflow-hidden">
					<div
						class="h-full rounded-full transition-all"
						style="width: {pct.toFixed(1)}%; background: {pct > 85 ? 'var(--gradient-usage-danger)' : pct > 65 ? 'var(--gradient-usage-warning)' : 'var(--gradient-usage)'}"
					></div>
				</div>
				<div class="text-xs text-ink-3 mt-1">{pct.toFixed(1)}% 사용 중</div>
			</div>
		{/each}
	</div>
{/if}
