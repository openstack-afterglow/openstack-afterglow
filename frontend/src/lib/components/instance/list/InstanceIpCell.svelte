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
				<span class="min-w-0 max-w-full break-all font-mono text-ink-2">{fip.addr}</span>
				{#if paired}<span class="min-w-0 max-w-full break-all rounded bg-surface-selected px-1.5 py-0.5 font-mono text-state-success-text">{paired.addr}</span>{/if}
			</div>
		{/each}
		{#each floatingIps.filter(ip => !fixedIps.some(fixed => fixed.network_name === ip.network_name)) as ip}
			<span class="min-w-0 max-w-full break-all rounded bg-surface-selected px-1.5 py-0.5 font-mono text-state-success-text">{ip.addr}</span>
		{/each}
	</div>
{:else}
	<span class="text-ink-2">-</span>
{/if}
