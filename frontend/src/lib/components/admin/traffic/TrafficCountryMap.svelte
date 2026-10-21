<script lang="ts">
	import { Button, Card, SelectInput, TableShell } from '$lib/components/ui';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { t } from '$lib/i18n/ns/traffic-analytics';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import { createTrafficMapSpec, trafficCountryAnchors, trafficGeography } from '$lib/utils/trafficMap';
	import type { TrafficSnapshot } from '$lib/types/trafficAnalytics';
	import { formatTrafficValue, trafficCountryName } from '$lib/utils/trafficFormat';
	let { countries, siteCountry = null }: { countries: TrafficSnapshot['countries']; siteCountry?: string | null } = $props();
	let selected = $state('');
	let hovered = $state<string | null>(null);
	let mapWidth = $state(720);
	const byCountry = $derived(Object.fromEntries(countries.map(row => [row.country, row])));
	const ranking = $derived([...countries].sort((a, b) => b.requests - a.requests || a.country.localeCompare(b.country)));
	const options = $derived([...new Set([...trafficGeography.features.map(feature => feature.properties.country).filter((code): code is string => typeof code === 'string'), ...countries.map(row => row.country)])].sort((a, b) => trafficCountryName(a).localeCompare(trafficCountryName(b))));
	const detailMetrics = ['success', 'errors', 'unique_visitors', 'visitor_identity_known', 'request_bytes', 'response_bytes', 'latency_ms_max'] as const;
	const max = $derived(Math.max(0, ...countries.filter(row => row.country !== 'XX').map(row => row.requests)));
	const active = $derived(hovered ?? selected);
	const detail = $derived(byCountry[active]);
	const site = $derived(siteCountry && siteCountry !== 'XX' ? trafficCountryAnchors[siteCountry] : undefined);
	const siteRequests = $derived(siteCountry ? byCountry[siteCountry]?.requests ?? null : null);
	const mapSpec = $derived(createTrafficMapSpec(countries, siteCountry, selected, active,
		(code) => { selected = code; hovered = null; },
		(code) => { hovered = code; }
	));
</script>

<Card surface="base">
	<h2 class="text-sm font-semibold text-ink-0">{t('map.title')}</h2>
	<div class="mt-3 flex flex-wrap items-end gap-2">
		<label class="min-w-0 flex-1 text-xs text-ink-2" for="traffic-country">{t('map.select')}
			<SelectInput id="traffic-country" bind:value={selected} onchange={() => { hovered = null; }}>
				<option value="">{t('map.select')}</option>
				{#each options as code (code)}<option value={code}>{trafficCountryName(code)} ({code})</option>{/each}
			</SelectInput>
		</label>
		<Button variant="secondary" onclick={() => { selected = ''; hovered = null; }}>{t('map.clear')}</Button>
	</div>
	<div class="mt-3 w-full" bind:clientWidth={mapWidth}>
		<BklitChart spec={mapSpec} height={mapWidth / 2} label={t('map.label')} showData={false} />
	</div>
	<div class="flex flex-wrap gap-3 text-xs text-ink-2" aria-label={t('map.legend')}>
		<span class="flex items-center gap-1"><i class="legend-chip no-data"></i>{t('noObservations')}</span>
		<span class="flex items-center gap-1"><i class="legend-chip zero"></i>{t('map.zero')}</span>
		<span class="flex items-center gap-1"><i class="legend-chip low"></i>{t('map.low')}</span>
		<span class="flex items-center gap-1"><i class="legend-chip high"></i>{t('map.high')} ({formatTrafficValue(max)})</span>
	</div>
	<p class="mt-2 text-xs text-ink-2">{t('map.legend')}</p>
	<p class="mt-2 text-xs text-ink-2">{t('map.limit')}</p>
	<p class="mt-2 text-xs text-ink-2">{t('map.flows.note')}</p>
	{#if site}
		<div class="mt-2 flex flex-wrap gap-3 text-xs text-ink-2" aria-label={t('map.flows.legend')}>
			<span class="flex items-center gap-1"><i class="flow-line" aria-hidden="true"></i>{t('map.flows.width')}</span>
			<span class="flex items-center gap-1"><i class="flow-line failure" aria-hidden="true"></i>{t('map.flows.failure')}</span>
			<span class="flex items-center gap-1"><i class="site-chip" aria-hidden="true"></i>{t('map.flows.site', { country: trafficCountryName(siteCountry!) })}</span>
		</div>
		<p class="mt-2 text-xs text-ink-2">{t('map.flows.sameCountry', { count: siteRequests === null ? t('noObservations') : formatTrafficValue(siteRequests) })}</p>
	{:else}
		<p class="mt-2 text-xs text-ink-2">{t(siteCountry ? 'map.flows.noShape' : 'map.flows.unconfigured')}</p>
	{/if}
	<p class="mt-2 text-xs text-ink-2">{t('map.credit')}</p>
	<section class="mt-4 min-h-24" aria-label={t('map.detail')} aria-live="polite">
		{#if detail}
			<h3 class="text-sm font-medium">{trafficCountryName(active)} ({active})</h3>
			<dl class="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs tabular-nums">
				<div><dt class="text-ink-2">{t('metrics.requests')}</dt><dd>{formatTrafficValue(detail.requests)}</dd></div>
				<div><dt class="text-ink-2">{t('metrics.responses')}</dt><dd>{formatTrafficValue(detail.requests)}</dd></div>
				{#each detailMetrics as key}
					<div><dt class="text-ink-2">{t(`metrics.${key}`)}</dt><dd>{formatTrafficValue(detail[key], key)}</dd></div>
				{/each}
			</dl>
			<p class="mt-2 text-xs text-ink-2">{t('map.responsesNote')}</p>
		{:else if active}<h3 class="text-sm font-medium">{trafficCountryName(active)} ({active})</h3><p class="mt-2 text-xs text-ink-2">{t('noObservations')}</p>
		{:else}<p class="text-xs text-ink-2">{t('map.select')}</p>{/if}
	</section>
	<h3 class="mt-3 text-sm font-medium">{t('map.ranking')}</h3>
	<ResponsiveTable class="mt-2">
		{#snippet cards()}
			{#each ranking as row (row.country)}
				<CompactResourceCard selected={selected === row.country}>
					<Button variant="ghost" ariaPressed={selected === row.country} onclick={() => { selected = row.country; hovered = null; }}>{trafficCountryName(row.country)} ({row.country})</Button>
					<dl class="grid grid-cols-2 gap-2 tabular-nums"><div><dt>{t('metrics.requests')}</dt><dd>{formatTrafficValue(row.requests)}</dd></div><div><dt>{t('metrics.errors')}</dt><dd>{formatTrafficValue(row.errors)}</dd></div></dl>
					{#snippet details()}<p>{t('metrics.unique_visitors')}: {formatTrafficValue(row.unique_visitors)}</p>{/snippet}
				</CompactResourceCard>
			{/each}
		{/snippet}
	<TableShell>
		<!-- TableShell scrolls horizontally on narrow screens; the table is the keyboard scroll target. -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<table tabindex="0" aria-label={t('map.ranking')} class="w-full text-xs tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"><thead><tr><th class="p-2 text-left">{t('map.country')}</th><th class="p-2 text-right">{t('metrics.requests')}</th><th class="p-2 text-right">{t('metrics.errors')}</th><th class="p-2 text-right">{t('metrics.unique_visitors')}</th></tr></thead>
			<tbody>{#each ranking as row (row.country)}<tr class="border-t border-line"><td class="p-2" onpointerleave={() => { hovered = null; }} onfocusout={() => { hovered = null; }}><Button variant="ghost" ariaPressed={selected === row.country} onclick={() => { selected = row.country; hovered = null; }} onintent={() => { hovered = row.country; }}>{trafficCountryName(row.country)} ({row.country})</Button></td><td class="p-2 text-right">{formatTrafficValue(row.requests)}</td><td class="p-2 text-right">{formatTrafficValue(row.errors)}</td><td class="p-2 text-right">{formatTrafficValue(row.unique_visitors)}</td></tr>{/each}</tbody>
		</table>
	</TableShell>
	</ResponsiveTable>
</Card>

<style>
	.legend-chip { display: inline-block; width: 1rem; height: 0.75rem; border: 1px solid var(--color-line-2); }
	.no-data { background: var(--color-surface-sunken); }
	.zero { background: color-mix(in oklab, var(--color-accent) 15%, var(--color-surface-base)); }
	.low { background: color-mix(in oklab, var(--color-accent) 35%, var(--color-surface-base)); }
	.high { background: color-mix(in oklab, var(--color-accent) 90%, var(--color-surface-base)); }
	.flow-line { display: inline-block; width: 1.5rem; border-top: 2px solid var(--color-chart-1); }
	.flow-line.failure { border-top: 2px dashed var(--color-chart-3); }
	.site-chip { display: inline-block; width: 0.5rem; height: 0.5rem; background: var(--color-ink-0); transform: rotate(45deg); margin: 0 0.25rem; }
</style>
