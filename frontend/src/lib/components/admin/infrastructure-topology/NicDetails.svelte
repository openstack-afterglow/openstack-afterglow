<script lang="ts">
	import type { InterfaceCounters, TopologyHost } from '$lib/types/infrastructureTopology';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import { quantity } from './evidence';
	let { host, name, verified }: { host: TopologyHost; name: string; verified: boolean } = $props();
	const nic = $derived(host.observation?.interfaces.find(item => item.name === name));
	const keys: (keyof InterfaceCounters)[] = ['rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets'];
	const sources = ['addresses', 'counters', 'lldp', 'neighbors', 'routes'] as const;
</script>

{#if nic && host.observation}
	<section aria-label={t('details')} class="space-y-4">
		<h2 class="text-base font-semibold">{t('details')} · <span class="font-mono">{nic.name}</span></h2>
		<dl class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
			<div><dt class="text-ink-2">{t('addresses')}</dt><dd class="font-mono break-all">{nic.addresses.join(', ') || t('unknown')}</dd></div>
			<div><dt class="text-ink-2">{t('mac')}</dt><dd class="font-mono break-all">{nic.mac ?? t('unknown')}</dd></div>
			<div><dt class="text-ink-2">{t('operstate')}</dt><dd>{nic.operstate}</dd></div>
		</dl>
		<div><h3 class="text-sm font-semibold mb-2">{t('sources')}</h3><dl class="flex flex-wrap gap-x-5 gap-y-2 text-xs">{#each sources as source}<div><dt>{t(`source.${source}`)}</dt><dd class="text-ink-2">{t(`state.${host.observation.sources[source]}`)}</dd></div>{/each}</dl></div>
		<p class="text-sm text-ink-2">{t('counterHelp')}</p>
		<TableShell><table>
			<caption class="text-left text-sm font-semibold pb-2">{t('counters')}</caption>
			<thead><tr><th scope="col">{t('metric')}</th><th scope="col">{t('total')}</th><th scope="col">{t('rate')}</th></tr></thead>
			<tbody>{#each keys as key}<tr><th scope="row">{t(`metric.${key}`)}</th><td class="tabular-nums">{quantity(host.observation.sources.counters === 'measured' ? nic[key] : null, key)}</td><td class="tabular-nums">{quantity(verified && host.observation_state === 'fresh' && host.observation.sources.counters === 'measured' ? nic.rates[key] : null, key, true)}</td></tr>{/each}</tbody>
		</table></TableShell>
		<TableShell><table><caption class="text-left text-sm font-semibold pb-2">{t('physical')}</caption>
			<thead><tr><th scope="col">{t('chassis')}</th><th scope="col">{t('port')}</th><th scope="col">{t('system')}</th></tr></thead>
			<tbody>{#each host.observation.sources.lldp === 'measured' ? host.observation.lldp.filter(edge => edge.interface === name) : [] as edge}<tr><td class="font-mono">{edge.chassis_id}</td><td class="font-mono">{edge.port_id}</td><td>{edge.system_name ?? t('unknown')}</td></tr>{:else}<tr><td colspan="3">{host.observation.sources.lldp === 'measured' ? t('none') : t(`state.${host.observation.sources.lldp}`)}</td></tr>{/each}</tbody>
		</table></TableShell>
		<TableShell><table><caption class="text-left text-sm font-semibold pb-2">{t('neighbors')}</caption>
			<thead><tr><th scope="col">{t('ip')}</th><th scope="col">{t('mac')}</th><th scope="col">{t('neighborState')}</th></tr></thead>
			<tbody>{#each host.observation.sources.neighbors === 'measured' ? host.observation.neighbors.filter(edge => edge.interface === name) : [] as edge}<tr><td class="font-mono">{edge.ip}</td><td class="font-mono">{edge.mac ?? t('unknown')}</td><td>{edge.state}</td></tr>{:else}<tr><td colspan="3">{host.observation.sources.neighbors === 'measured' ? t('none') : t(`state.${host.observation.sources.neighbors}`)}</td></tr>{/each}</tbody>
		</table></TableShell>
		<TableShell><table><caption class="text-left text-sm font-semibold pb-2">{t('routes')}</caption>
			<thead><tr><th scope="col">{t('destination')}</th><th scope="col">{t('gateway')}</th><th scope="col">{t('metricPriority')}</th></tr></thead>
			<tbody>{#each host.observation.sources.routes === 'measured' ? host.observation.routes.filter(edge => edge.interface === name) : [] as edge}<tr><td class="font-mono">{edge.destination}</td><td class="font-mono">{edge.gateway ?? '—'}</td><td>{edge.metric?.toLocaleString(intlLocale()) ?? '—'}</td></tr>{:else}<tr><td colspan="3">{host.observation.sources.routes === 'measured' ? t('none') : t(`state.${host.observation.sources.routes}`)}</td></tr>{/each}</tbody>
		</table></TableShell>
	</section>
{/if}
