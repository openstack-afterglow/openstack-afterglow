<script lang="ts">
	import type { TopologyHost } from '$lib/types/infrastructureTopology';
	import { buildPeerProbeEdges } from './evidence';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	let { hosts, verified, selectedId, onselect }: { hosts: TopologyHost[]; verified: boolean; selectedId: string; onselect: (id: string) => void } = $props();
	const edges = $derived(buildPeerProbeEdges(hosts, verified));
</script>

<section aria-label={t('peers')} class="space-y-4">
	<h2 class="font-semibold">{t('peers')}</h2>
	<p class="text-sm text-ink-2">{t('probeNotice')}</p>
	{#if !edges.length}<p class="text-sm text-ink-2">{t('probeEmpty')}</p>{/if}
	{#each edges as edge (`${edge.source}:${edge.target_host_id}:${edge.address}:${edge.port}`)}
		<div class="probe-edge" data-probe-source={edge.source} data-probe-target={edge.target_host_id}>
			<div class="endpoint"><span class="text-xs text-ink-2">{t('probeSource')}</span><Button variant="secondary" ariaPressed={selectedId === edge.source} onclick={() => onselect(edge.source)}><span class="font-mono break-all">{edge.sourceName}</span></Button></div>
			<div class="connection"><span class="text-xs">{t('probePort')} · {edge.port.toLocaleString(intlLocale(), { useGrouping: false })}</span><svg viewBox="0 0 100 24" aria-hidden="true" data-edge-kind="tcp-probe"><path d="M 0 12 H 100" class="probe-line" /><path d="M 90 5 L 99 12 L 90 19" /></svg><Pill tone={edge.status === 'up' ? 'success' : edge.status === 'down' ? 'warning' : 'neutral'}>{t(`probe.${edge.status}`)}</Pill></div>
			<div class="endpoint"><span class="text-xs text-ink-2">{t('probeTarget')}</span>{#if edge.targetInInventory}<Button variant="secondary" ariaPressed={selectedId === edge.target_host_id} onclick={() => onselect(edge.target_host_id)}><span class="font-mono break-all">{edge.targetName}</span></Button>{:else}<strong class="font-mono break-all">{edge.targetName}</strong><span class="text-xs text-ink-2">{t('probeOutside')}</span>{/if}<span class="text-xs font-mono break-all">{edge.address}:{edge.port}</span></div>
		</div>
	{/each}
	{#if edges.length}<ResponsiveTable>
		{#snippet cards()}{#each edges as edge}<CompactResourceCard><p class="font-mono font-medium">{edge.sourceName} → {edge.targetName}</p><p>{t('probeStatus')}: {t(`probe.${edge.status}`)}</p><p>{t('probeLatency')}: {edge.status !== 'unknown' && edge.latency_ms !== null ? t('rttValue', { value: edge.latency_ms.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }) }) : t('unknown')}</p>{#snippet details()}<p class="font-mono">{t('ip')}: {edge.address} · {t('probePort')}: {edge.port.toLocaleString(intlLocale(), { useGrouping: false })}</p><p>{t('probeTime')}: {edge.checked_at === null ? t('unknown') : new Date(edge.checked_at * 1000).toLocaleString(intlLocale())}</p>{#if edge.error}<p>{t(`probeError.${edge.error}`)}</p>{/if}{/snippet}</CompactResourceCard>{/each}{/snippet}
		<TableShell><table>
		<caption class="text-left text-sm font-semibold pb-2">{t('peers')}</caption>
		<thead><tr><th scope="col">{t('probeSource')}</th><th scope="col">{t('probeTarget')}</th><th scope="col">{t('ip')}</th><th scope="col">{t('probePort')}</th><th scope="col">{t('probeStatus')}</th><th scope="col">{t('probeLatency')}</th><th scope="col">{t('probeTime')}</th></tr></thead>
		<tbody>{#each edges as edge}<tr><th scope="row" class="font-mono">{edge.sourceName}</th><td class="font-mono">{edge.targetName}</td><td class="font-mono">{edge.address}</td><td>{edge.port.toLocaleString(intlLocale(), { useGrouping: false })}</td><td>{t(`probe.${edge.status}`)}{#if edge.error}<p class="text-xs text-ink-2">{t(`probeError.${edge.error}`)}</p>{/if}</td><td class="tabular-nums">{edge.status !== 'unknown' && edge.latency_ms !== null ? t('rttValue', { value: edge.latency_ms.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }) }) : t('unknown')}</td><td>{edge.checked_at === null ? t('unknown') : new Date(edge.checked_at * 1000).toLocaleString(intlLocale())}</td></tr>{/each}</tbody>
	</table></TableShell></ResponsiveTable>{/if}
</section>

<style>
	.probe-edge { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr) minmax(0, 1fr); gap: 0.5rem; align-items: center; border: 1px solid var(--color-line); border-radius: var(--radius-md); padding: 0.75rem; }
	.endpoint { min-width: 0; display: flex; flex-direction: column; gap: 0.5rem; align-items: flex-start; font-size: 0.875rem; }
	.connection { min-width: 0; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 0.25rem; }
	svg { display: block; width: 100%; }
	path { stroke: var(--color-line-2); stroke-width: 1.5; fill: none; }
	.probe-line { stroke-dasharray: 4 3; }
	@media (min-width: 768px) { .probe-edge { grid-template-columns: minmax(0, 1fr) 12rem minmax(0, 1fr); gap: 1rem; } }
</style>
