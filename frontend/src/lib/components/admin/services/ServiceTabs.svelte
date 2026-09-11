<script lang="ts">
	import Pill from '$lib/components/ui/Pill.svelte';
	type TabKey = 'compute' | 'network' | 'block_storage' | 'shared_file_system' | 'orchestration' | 'container' | 'container_infra' | 'endpoints' | 'storage_pools';

	let {
		tabs,
		activeTab = $bindable(),
		loadingMap,
		loadedMap,
		onIntent,
	}: {
		tabs: { key: TabKey; label: string; count: number }[];
		activeTab: TabKey;
		loadingMap: Record<TabKey, boolean>;
		loadedMap: Record<TabKey, boolean>;
		onIntent: (key: TabKey) => void;
	} = $props();

	function tourAnchor(key: TabKey): string | undefined {
		const anchors: Partial<Record<TabKey, string>> = {
			compute: 'admin-system-compute-tab',
			network: 'admin-system-network-tab',
			endpoints: 'admin-system-endpoints-tab',
			storage_pools: 'admin-system-storage-pools-tab',
		};
		return anchors[key];
	}
</script>

<div class="flex flex-wrap gap-1 mb-6 border-b border-line pb-0" data-tour="admin-system-tabs">
	{#each tabs as tab}
		<button
			onclick={() => { onIntent(tab.key); activeTab = tab.key; }}
			onpointerenter={() => onIntent(tab.key)}
			onfocus={() => onIntent(tab.key)}
			data-tour={tourAnchor(tab.key)}
			class="px-3 py-2 text-xs font-medium rounded-t-lg transition-colors relative -mb-px border-b-2 {activeTab === tab.key
				? 'border-action-warm text-action-warm bg-surface-selected/10'
				: 'border-transparent text-ink-2 hover:text-ink-1 hover:bg-surface-sunken/50'}"
		>
			{tab.label}
			{#if loadingMap[tab.key]}
				<span class="ml-1.5 inline-block w-3 h-3 border border-line-2 border-t-blue-400 rounded-full animate-spin"></span>
			{:else if !loadedMap[tab.key]}
				<Pill class="ml-1.5" tone="neutral" size="xs">—</Pill>
			{:else}
				<Pill class="ml-1.5" tone={activeTab === tab.key ? 'accent' : 'neutral'} size="xs">{tab.count}</Pill>
			{/if}
		</button>
	{/each}
</div>
