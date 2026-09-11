<script lang="ts">
	import type { IpAddress } from '$lib/types/compute';

	let { addresses }: { addresses: IpAddress[] } = $props();
</script>

{#if addresses.length > 0}
	{@const fixedIps = addresses.filter(ip => ip.type === 'fixed')}
	{@const floatingIps = addresses.filter(ip => ip.type === 'floating')}
	<div class="flex flex-col gap-0.5">
		{#each fixedIps as fip}
			{@const paired = floatingIps.find(fl => fl.network_name === fip.network_name)}
			<div class="flex items-center gap-1 flex-wrap">
				<span class="font-mono text-ink-2 whitespace-nowrap">{fip.addr}</span>
				{#if paired}<span class="font-mono text-green-400 bg-green-900/20 px-1.5 py-0.5 rounded whitespace-nowrap">{paired.addr}</span>{/if}
			</div>
		{/each}
	</div>
{:else}
	<span class="text-ink-3">-</span>
{/if}
