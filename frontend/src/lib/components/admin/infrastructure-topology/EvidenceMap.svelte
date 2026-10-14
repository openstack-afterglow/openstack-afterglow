<script lang="ts">
	import type { TopologyHost } from '$lib/types/infrastructureTopology';
	import { buildNicEvidence, quantity } from './evidence';
	import { t } from '$lib/i18n/ns/infra-topology';
	import Button from '$lib/components/ui/Button.svelte';
	import TrafficArea from '$lib/components/ui/TrafficArea.svelte';
	let { host, verified, selectedNic, onselect }: { host: TopologyHost; verified: boolean; selectedNic: string; onselect: (name: string) => void } = $props();
	const evidence = $derived(buildNicEvidence(host, verified));
</script>

<section aria-label={t('map')} class="space-y-4">
	<h2 class="text-base font-semibold">{t('map')}</h2>
	<p class="text-sm text-ink-2">{t('mapHelp')}</p>
	<p class="text-xs text-ink-2">{t('nicMagnitude')}</p>
	{#if !evidence.length}<p class="text-sm text-ink-2">{t('noNics')}</p>{/if}
	{#each evidence as row (row.interface)}
		<div class="evidence-row" data-nic={row.interface}>
			<div class="local-link">
				<div class="endpoint"><span class="text-xs text-ink-2">{t('host')}</span><strong class="font-mono break-all">{host.name}</strong></div>
				<div class="directions">
					<span class="rx text-xs" data-rate="rx">{t('rx')}<br />{quantity(row.rates.rx_bytes, 'rx_bytes', true)} · {quantity(row.rates.rx_packets, 'rx_packets', true)}{#if row.rateState !== 'fresh'}<br />{t(`rateState.${row.rateState}`)}{/if}</span>
					<svg viewBox="0 0 100 40" aria-hidden="true" data-edge-kind="host-nic">
						<path d="M 95 12 H 5 M 12 7 L 5 12 L 12 17" class="rx-line" class:unknown={row.rates.rx_bytes === null || row.rates.rx_packets === null} style:stroke-width={row.rxWidth} />
						<path d="M 5 28 H 95 M 88 23 L 95 28 L 88 33" class="tx-line" class:unknown={row.rates.tx_bytes === null || row.rates.tx_packets === null} style:stroke-width={row.txWidth} />
						{#if row.rxActive && row.rates.rx_bytes !== null && row.rates.rx_packets !== null}<path d="M 95 12 H 5" class="rx-line motion-flow" data-flow="rx" style:stroke-width={row.rxWidth} />{/if}
						{#if row.txActive && row.rates.tx_bytes !== null && row.rates.tx_packets !== null}<path d="M 5 28 H 95" class="tx-line motion-flow" data-flow="tx" style:stroke-width={row.txWidth} />{/if}
					</svg>
					<span class="tx text-xs" data-rate="tx">{t('tx')}<br />{quantity(row.rates.tx_bytes, 'tx_bytes', true)} · {quantity(row.rates.tx_packets, 'tx_packets', true)}{#if row.rateState !== 'fresh'}<br />{t(`rateState.${row.rateState}`)}{/if}</span>
				</div>
				<div class="endpoint"><span class="text-xs text-ink-2">{t('nic')}</span><Button variant={selectedNic === row.interface ? 'primary' : 'secondary'} ariaPressed={selectedNic === row.interface} size="sm" onclick={() => onselect(row.interface)}>{row.interface}</Button></div>
			</div>
			{#if verified}<div class="nic-history" aria-label={t('nicHistory', { nic: row.interface })}>
				<TrafficArea samples={row.history} rxLabel={t('rx')} txLabel={t('tx')} fresh={row.rateState === 'fresh'}>
					<p class="text-xs text-ink-2">{t('nicHistory', { nic: row.interface })}{#if row.rateState !== 'fresh'} · {t(`rateState.${row.rateState}`)}{/if}</p>
				</TrafficArea>
			</div>{/if}
			<div class="evidence-links">
				<div class="physical" data-edge-kind="lldp"><h3>{t('physical')}</h3>
					{#each row.physical as link}<p class="font-mono break-all">{row.interface} — {link.name ?? link.chassis} · {link.port}</p>{:else}<p>{host.observation?.sources.lldp === 'measured' ? t('none') : t(`state.${host.observation?.sources.lldp ?? 'unmeasured'}`)}</p>{/each}
				</div>
				<details class="neighbors" data-edge-kind="neighbor"><summary>{t('neighbors')} · {row.neighbors.length}</summary>
					{#each row.neighbors as link}<p class="font-mono break-all">{row.interface} ⇢ {link.ip} · {link.state}</p>{:else}<p>{host.observation?.sources.neighbors === 'measured' ? t('none') : t(`state.${host.observation?.sources.neighbors ?? 'unmeasured'}`)}</p>{/each}
				</details>
				<details class="routes" data-edge-kind="route"><summary>{t('routes')} · {row.routes.length}</summary>
					{#each row.routes as link}<p class="font-mono break-all">{row.interface} ⇢ {link.gateway ?? '—'} ⇢ {link.destination}</p>{:else}<p>{host.observation?.sources.routes === 'measured' ? t('none') : t(`state.${host.observation?.sources.routes ?? 'unmeasured'}`)}</p>{/each}
				</details>
			</div>
		</div>
	{/each}
</section>

<style>
	.evidence-row { border: 1px solid var(--color-line); border-radius: var(--radius-md); padding: 0.75rem; display: grid; gap: 1rem; min-width: 0; }
	.local-link { display: grid; grid-template-columns: minmax(0, 1fr) minmax(5rem, 2fr) minmax(0, 1fr); gap: 0.5rem; align-items: center; min-width: 0; }
	.endpoint { display: flex; flex-direction: column; gap: 0.25rem; align-items: flex-start; min-width: 0; font-size: 0.875rem; }
	.directions { text-align: center; }
	svg { display: block; width: 100%; }
	path { fill: none; stroke-width: 1.5; }
	.rx-line { stroke: var(--color-chart-1); }
	.tx-line { stroke: var(--color-chart-2); }
	.unknown { stroke: var(--color-line-2); stroke-dasharray: 4 3; }
	.nic-history { min-width: 0; }
	.motion-flow { stroke: var(--motion-sheen); }
	.rx { color: var(--color-ink-1); }
	.tx { color: var(--color-ink-1); }
	.evidence-links { display: grid; gap: 0.75rem; font-size: 0.75rem; color: var(--color-ink-1); }
	.evidence-links > * { padding-left: 0.75rem; border-left: 2px solid var(--color-line-2); }
	.evidence-links h3, summary { font-weight: 600; }
	summary { cursor: pointer; min-height: 2.75rem; display: list-item; }
	summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.neighbors { border-left-style: dashed; }
	.routes { border-left-style: dotted; }
	@media (min-width: 768px) { .evidence-row { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } .local-link, .nic-history { grid-column: 1; } .evidence-links { grid-column: 2; grid-row: 1 / 3; } }
	@media (prefers-reduced-motion: reduce) { .motion-flow { animation: none; display: none; } }
</style>
