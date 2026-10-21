<script lang="ts">
	import type { InterfaceCounters, TopologyHost } from '$lib/types/infrastructureTopology';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import TrafficArea from '$lib/components/ui/TrafficArea.svelte';
	import { nicHistory, quantity } from './evidence';
	let { host, name, verified }: { host: TopologyHost; name: string; verified: boolean } = $props();
	const nic = $derived(host.observation?.interfaces.find(item => item.name === name));
	const history = $derived(nicHistory(host, name, verified));
	const keys: (keyof InterfaceCounters)[] = ['rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets'];
	const sources = ['addresses', 'counters', 'lldp', 'neighbors', 'routes', 'flows'] as const;
</script>

{#if nic && host.observation}
	{@const observation = host.observation}
	<section aria-label={t('details')} class="space-y-4">
		<h2 class="text-base font-semibold">{t('details')} · <span class="font-mono">{nic.name}</span></h2>
		<dl class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
			<div><dt class="text-ink-2">{t('addresses')}</dt><dd class="font-mono break-all">{nic.addresses.join(', ') || t('unknown')}</dd></div>
			<div><dt class="text-ink-2">{t('mac')}</dt><dd class="font-mono break-all">{nic.mac ?? t('unknown')}</dd></div>
			<div><dt class="text-ink-2">{t('operstate')}</dt><dd>{nic.operstate}</dd></div>
			<div><dt class="text-ink-2">{t('workspace.nicClassification')}</dt><dd>{t(nic.physical === true ? 'workspace.nicPhysical.yes' : nic.physical === false ? 'workspace.nicPhysical.no' : 'workspace.nicPhysical.unknown')}</dd></div>
		</dl>
		<div><h3 class="text-sm font-semibold mb-2">{t('sources')}</h3><dl class="flex flex-wrap gap-x-5 gap-y-2 text-xs">{#each sources as source}<div><dt>{t(`source.${source}`)}</dt><dd class="text-ink-2">{t(`state.${host.observation.sources[source]}`)}</dd></div>{/each}</dl></div>
		<p class="text-sm text-ink-2">{t('counterHelp')}</p>
		<TrafficArea samples={history} rxLabel={t('rx')} txLabel={t('tx')} fresh={verified && host.observation_state === 'fresh' && host.observation.sources.counters === 'measured'}><p class="text-xs text-ink-2">{t('nicHistory', { nic: name })}</p></TrafficArea>
		<ResponsiveTable>
			{#snippet cards()}{#each keys as key}<CompactResourceCard><p class="font-medium">{t(`metric.${key}`)}</p><dl class="grid grid-cols-2 gap-2 tabular-nums"><div><dt>{t('total')}</dt><dd>{quantity(observation.sources.counters === 'measured' ? nic[key] : null, key)}</dd></div><div><dt>{t('rate')}</dt><dd>{quantity(verified && host.observation_state === 'fresh' && observation.sources.counters === 'measured' ? nic.rates[key] : null, key, true)}</dd></div></dl></CompactResourceCard>{/each}{/snippet}
		<TableShell><table>
			<caption class="text-left text-sm font-semibold pb-2">{t('counters')}</caption>
			<thead><tr><th scope="col">{t('metric')}</th><th scope="col">{t('total')}</th><th scope="col">{t('rate')}</th></tr></thead>
			<tbody>{#each keys as key}<tr><th scope="row">{t(`metric.${key}`)}</th><td class="tabular-nums">{quantity(observation.sources.counters === 'measured' ? nic[key] : null, key)}</td><td class="tabular-nums">{quantity(verified && host.observation_state === 'fresh' && observation.sources.counters === 'measured' ? nic.rates[key] : null, key, true)}</td></tr>{/each}</tbody>
		</table></TableShell>
		</ResponsiveTable>
		<p class="text-xs text-ink-2">{t('workspace.lldpDiagnostic')}</p>
		<ResponsiveTable>
			{#snippet cards()}
				<h3 class="responsive-card-toolbar font-semibold">{t('physical')}</h3>
				{#each observation.sources.lldp === 'measured' ? observation.lldp.filter(edge => edge.interface === name) : [] as edge}<CompactResourceCard><p class="font-mono font-medium">{edge.chassis_id} · {edge.port_id}</p><p>{t('system')}: {edge.system_name ?? t('unknown')}</p>{#snippet details()}<p>{t('workspace.portDescription')}: {edge.port_description ?? t('unknown')}</p><p class="font-mono">{t('workspace.management')}: {edge.management_address ?? t('unknown')}</p>{/snippet}</CompactResourceCard>{:else}<p>{observation.sources.lldp === 'measured' ? t('none') : t(`state.${observation.sources.lldp}`)}</p>{/each}
			{/snippet}
		<TableShell><table><caption class="text-left text-sm font-semibold pb-2">{t('physical')}</caption>
			<thead><tr><th scope="col">{t('chassis')}</th><th scope="col">{t('port')}</th><th scope="col">{t('system')}</th><th scope="col">{t('workspace.portDescription')}</th><th scope="col">{t('workspace.management')}</th></tr></thead>
			<tbody>{#each observation.sources.lldp === 'measured' ? observation.lldp.filter(edge => edge.interface === name) : [] as edge}<tr><td class="font-mono">{edge.chassis_id}</td><td class="font-mono">{edge.port_id}</td><td>{edge.system_name ?? t('unknown')}</td><td>{edge.port_description ?? t('unknown')}</td><td class="font-mono">{edge.management_address ?? t('unknown')}</td></tr>{:else}<tr><td colspan="5">{observation.sources.lldp === 'measured' ? t('none') : t(`state.${observation.sources.lldp}`)}</td></tr>{/each}</tbody>
		</table></TableShell>
		</ResponsiveTable>
		<ResponsiveTable>
			{#snippet cards()}
				<h3 class="responsive-card-toolbar font-semibold">{t('neighbors')}</h3>
				{#each observation.sources.neighbors === 'measured' ? observation.neighbors.filter(edge => edge.interface === name) : [] as edge}<CompactResourceCard><p class="font-mono font-medium">{edge.ip}</p><p>{t('neighborState')}: {edge.state}</p>{#snippet details()}<p class="font-mono">{t('mac')}: {edge.mac ?? t('unknown')}</p>{/snippet}</CompactResourceCard>{:else}<p>{observation.sources.neighbors === 'measured' ? t('none') : t(`state.${observation.sources.neighbors}`)}</p>{/each}
			{/snippet}
		<TableShell><table><caption class="text-left text-sm font-semibold pb-2">{t('neighbors')}</caption>
			<thead><tr><th scope="col">{t('ip')}</th><th scope="col">{t('mac')}</th><th scope="col">{t('neighborState')}</th></tr></thead>
			<tbody>{#each observation.sources.neighbors === 'measured' ? observation.neighbors.filter(edge => edge.interface === name) : [] as edge}<tr><td class="font-mono">{edge.ip}</td><td class="font-mono">{edge.mac ?? t('unknown')}</td><td>{edge.state}</td></tr>{:else}<tr><td colspan="3">{observation.sources.neighbors === 'measured' ? t('none') : t(`state.${observation.sources.neighbors}`)}</td></tr>{/each}</tbody>
		</table></TableShell>
		</ResponsiveTable>
		<ResponsiveTable>
			{#snippet cards()}
				<h3 class="responsive-card-toolbar font-semibold">{t('routes')}</h3>
				{#each observation.sources.routes === 'measured' ? observation.routes.filter(edge => edge.interface === name) : [] as edge}<CompactResourceCard><p class="font-mono font-medium">{edge.destination}</p><p class="font-mono">{t('gateway')}: {edge.gateway ?? '—'}</p><p>{t('metricPriority')}: {edge.metric?.toLocaleString(intlLocale()) ?? '—'}</p></CompactResourceCard>{:else}<p>{observation.sources.routes === 'measured' ? t('none') : t(`state.${observation.sources.routes}`)}</p>{/each}
			{/snippet}
		<TableShell><table><caption class="text-left text-sm font-semibold pb-2">{t('routes')}</caption>
			<thead><tr><th scope="col">{t('destination')}</th><th scope="col">{t('gateway')}</th><th scope="col">{t('metricPriority')}</th></tr></thead>
			<tbody>{#each observation.sources.routes === 'measured' ? observation.routes.filter(edge => edge.interface === name) : [] as edge}<tr><td class="font-mono">{edge.destination}</td><td class="font-mono">{edge.gateway ?? '—'}</td><td>{edge.metric?.toLocaleString(intlLocale()) ?? '—'}</td></tr>{:else}<tr><td colspan="3">{observation.sources.routes === 'measured' ? t('none') : t(`state.${observation.sources.routes}`)}</td></tr>{/each}</tbody>
		</table></TableShell>
		</ResponsiveTable>
	</section>
{/if}
