<script lang="ts">
	import type { TopologyHost } from '$lib/types/infrastructureTopology';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	let { host, verified, onselectnic }: { host: TopologyHost; verified: boolean; onselectnic: (nic: string) => void } = $props();
	function date(ts: number) {
		if (!Number.isFinite(ts)) return t('unknown');
		return new Date(ts * 1000).toLocaleString(intlLocale());
	}
</script>

{#snippet gap(label: string)}<span aria-hidden="true">*</span><span class="sr-only">{label}</span>{/snippet}

<div class="space-y-3">
	{#each host.traces as trace, index (trace.id)}
		<details open={index === 0} class="trace-record">
			<summary><span class="font-mono break-all">{trace.target}</span> <Pill tone={trace.status === 'queued' || trace.status === 'running' ? 'warning' : trace.status === 'error' ? 'danger' : 'neutral'}>{t(`trace.${trace.status}`)}</Pill></summary>
			<div class="space-y-4 pt-3">
				<p class="text-xs text-ink-2">{t('created')}: {date(trace.created_at)} · {t('outbound')}</p>
				{#if trace.result}
					<div class="flex flex-wrap gap-2"><Pill tone={trace.result.reached ? 'success' : 'neutral'}>{t(trace.result.reached ? 'reached' : 'unreached')}</Pill>{#if !verified || host.observation_state !== 'fresh'}<Pill tone="neutral">{t('trace.stale')}</Pill>{/if}</div>
					<p class="text-xs text-ink-2">{t('completed')}: {date(trace.result.completed_at)}</p>
					{#if trace.result.error}<p role="status" class="text-sm text-ink-1">{t(`error.${trace.result.error}`)}</p>{/if}
					<dl class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
						<div><dt class="text-ink-2">{t('sourceNic')}</dt><dd>{#if trace.result.source_interface && host.observation?.interfaces.some(nic => nic.name === trace.result?.source_interface)}<Button variant="ghost" size="sm" onclick={() => onselectnic(trace.result!.source_interface!)}>{trace.result.source_interface}</Button>{:else}<span class="font-mono">{trace.result.source_interface ?? t('unknown')}</span>{/if}</dd></div>
						<div><dt class="text-ink-2">{t('nextHop')}</dt><dd class="font-mono break-all">{trace.result.next_hop ?? t('unknown')}</dd></div>
					</dl>
					{#if trace.result.hops.length}
						<ol class="hop-path" aria-label={t('outbound')}>
							<li class="hop-source"><span class="font-mono">{host.name}</span><span>{trace.result.source_interface ?? t('unknown')}</span></li>
							{#each trace.result.hops as hop (hop.hop)}<li data-hop={hop.hop}><span class="text-ink-2">{t('hop')} {hop.hop.toLocaleString(intlLocale())}</span><strong class="font-mono break-all">{#if hop.ip === null}{@render gap(t('state.down'))}{:else}{hop.ip}{/if}</strong><span>{#if hop.rtt_ms === null}{@render gap(t('unknown'))}{:else}{t('rttValue', { value: hop.rtt_ms.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }) })}{/if}</span></li>{/each}
						</ol>
						<TableShell><table><caption class="text-left text-sm font-semibold pb-2">{t('outbound')} · {trace.target}</caption><thead><tr><th scope="col">{t('hop')}</th><th scope="col">{t('ip')}</th><th scope="col">{t('rtt')}</th></tr></thead><tbody>{#each trace.result.hops as hop (hop.hop)}<tr><th scope="row">{hop.hop.toLocaleString(intlLocale())}</th><td class="font-mono">{#if hop.ip === null}{@render gap(t('state.down'))}{:else}{hop.ip}{/if}</td><td class="tabular-nums">{#if hop.rtt_ms === null}{@render gap(t('unknown'))}{:else}{t('rttValue', { value: hop.rtt_ms.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }) })}{/if}</td></tr>{/each}</tbody></table></TableShell>
					{/if}
				{/if}
			</div>
		</details>
	{:else}<p class="text-sm text-ink-2">{t('noTraces')}</p>{/each}
</div>

<style>
	.trace-record { border: 1px solid var(--color-line); border-radius: var(--radius-md); padding: 0.75rem; }
	summary { cursor: pointer; min-height: 2.75rem; overflow-wrap: anywhere; }
	summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.hop-path { display: flex; flex-wrap: wrap; gap: 1.5rem; padding: 0; list-style: none; }
	.hop-path li { position: relative; display: flex; flex-direction: column; gap: 0.25rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-sunken); padding: 0.75rem; font-size: 0.75rem; max-width: 100%; }
	.hop-path li:not(:last-child)::after { content: '→'; position: absolute; right: -1.25rem; top: 50%; color: var(--color-ink-2); }
</style>
