<script lang="ts">
	import { Card, Spark, TableShell } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/traffic-analytics';
	import { metricValue, trafficTrend, type TrafficMetric, type TrafficSnapshot } from '$lib/types/trafficAnalytics';
	import { formatTrafficValue, formatTrafficTime } from '$lib/utils/trafficFormat';
	let { snapshot, metric }: { snapshot: TrafficSnapshot; metric: TrafficMetric } = $props();
	const values = $derived(trafficTrend(snapshot.series, metric));
	const current = $derived(metricValue(snapshot.totals, metric));
	const known = $derived(metric === 'request_bytes' ? snapshot.totals?.request_bytes_known : snapshot.totals?.response_bytes_known);
</script>

<Card surface="base">
	<h2 class="text-xs font-medium text-ink-2">{t(`metrics.${metric}`)}</h2>
	<p class="mt-2 text-xl font-semibold tabular-nums text-ink-0">{formatTrafficValue(current, metric)}</p>
	{#if values.length >= 2}
		<Spark data={values} height={48} class="mt-3 w-full" />
		<p class="mt-2 text-xs text-ink-2 tabular-nums">{t('trend.range', { min: formatTrafficValue(Math.min(...values), metric), max: formatTrafficValue(Math.max(...values), metric) })}</p>
	{:else}
		<p class="mt-3 text-xs text-ink-2">{t('trend.awaiting')}</p>
	{/if}
	{#if metric === 'request_bytes' || metric === 'response_bytes'}
		<p class="mt-2 text-xs text-ink-2">{t('bytes.coverage', { known: formatTrafficValue(known ?? null), total: formatTrafficValue(snapshot.totals?.requests ?? null) })}</p>
	{/if}
	{#if metric === 'unique_visitors'}
		<p class="mt-2 text-xs text-ink-2">{t('unique.coverage', { known: formatTrafficValue(snapshot.totals?.visitor_identity_known ?? null), total: formatTrafficValue(snapshot.totals?.requests ?? null) })}</p>
	{/if}
	<details class="mt-3 text-xs text-ink-2">
		<summary class="cursor-pointer min-h-11 flex items-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">{t('trend.samples')}</summary>
		<TableShell>
			<!-- TableShell scrolls horizontally on narrow screens; the table is the keyboard scroll target. -->
			<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
			<table tabindex="0" aria-label={`${t(`metrics.${metric}`)} · ${t('trend.samples')}`} class="w-full text-xs tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"><thead><tr><th class="text-left p-2">{t('trend.time')}</th><th class="text-right p-2">{t('trend.value')}</th></tr></thead>
				<tbody>{#each snapshot.series as bucket (bucket.at)}<tr class="border-t border-line"><td class="p-2 whitespace-nowrap">{formatTrafficTime(bucket.at)}</td><td class="p-2 text-right whitespace-nowrap">{formatTrafficValue(metricValue(bucket.metrics, metric), metric)}</td></tr>{/each}</tbody>
			</table>
		</TableShell>
	</details>
</Card>
