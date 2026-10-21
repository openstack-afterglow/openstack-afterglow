<script lang="ts">
	import { t } from '$lib/i18n/ns/network-resources';
	import type { RouterInfo } from '$lib/types/networks';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

	let { routers }: { routers: RouterInfo[] } = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-6">
	<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">{t('network.routers.title')}</h2>
	<ResponsiveTable>
		{#snippet cards()}
			{#each routers as router (router.id)}
				<CompactResourceCard>
					<p class="font-medium">{router.name || router.id.slice(0, 12)}</p>
					<p class="text-xs text-ink-2">{t('network.routers.subnetCount', { count: router.connected_subnet_ids.length })}</p>
					{#snippet details()}<dl><div><dt>{t('network.labels.id')}</dt><dd>{router.id}</dd></div><div><dt>{t('network.routers.externalGateway')}</dt><dd>{router.external_gateway_network_id || '-'}</dd></div></dl>{/snippet}
				</CompactResourceCard>
			{/each}
		{/snippet}
	<div class="overflow-x-auto">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
				<th class="text-left py-2 pr-6">{t('network.labels.name')}</th>
				<th class="text-left py-2 pr-6">{t('network.routers.externalGateway')}</th>
				<th class="text-left py-2">{t('network.routers.connectedSubnets')}</th>
			</tr>
		</thead>
		<tbody>
			{#each routers as router}
				<tr class="border-b border-line/50">
					<td class="py-2 pr-6 text-ink-2"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={router.name || router.id}>{router.name || router.id.slice(0, 12) + '…'}</span></td>
					<td class="py-2 pr-6">
						{#if router.external_gateway_network_id}
							<span class="text-orange-300 text-xs font-mono">{router.external_gateway_network_id.slice(0, 12)}…</span>
						{:else}
							<span class="text-ink-2 text-xs">-</span>
						{/if}
					</td>
					<td class="py-2 text-ink-2 text-xs">
						{t('network.routers.subnetCount', { count: router.connected_subnet_ids.length })}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
	</div>
	</ResponsiveTable>
</div>
