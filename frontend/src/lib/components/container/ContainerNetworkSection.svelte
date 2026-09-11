<script lang="ts">
	import { useContainerDetailController } from '$lib/stores/containerDetailController.svelte';

	const s = useContainerDetailController();
</script>

{#if s.container?.addresses && Object.keys(s.container.addresses).length > 0}
	<div class="bg-surface-base border border-line rounded-xl p-4">
		<h3 class="text-xs text-ink-3 uppercase tracking-wide mb-3">네트워크</h3>
		<div class="space-y-1.5 text-xs">
			{#each Object.entries(s.container.addresses) as [netName, addrs]}
				{#each addrs as a}
					<div class="flex justify-between">
						<span class="text-ink-2">{netName}</span>
						<span class="text-ink-2 font-mono">{a.addr}</span>
					</div>
				{/each}
			{/each}
		</div>
	</div>
{/if}
