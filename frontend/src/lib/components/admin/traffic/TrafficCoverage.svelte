<script lang="ts">
	import { Card } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/traffic-analytics';
	import type { TrafficSnapshot, TrafficSource } from '$lib/types/trafficAnalytics';
	import { formatTrafficTime, formatTrafficValue } from '$lib/utils/trafficFormat';
	let { snapshot, source }: { snapshot: TrafficSnapshot | null; source: TrafficSource } = $props();
	type UnknownReason = keyof TrafficSnapshot['coverage']['geo_unknown_reasons'] | keyof TrafficSnapshot['coverage']['origin_unknown_reasons'];
	const reasonKinds = ['geo_unknown_reasons', 'origin_unknown_reasons'] as const;
</script>

<Card surface="base">
	<h2 class="text-sm font-semibold">{t('coverage.title')}</h2>
	<div class="mt-3 space-y-2 text-xs text-ink-2 leading-relaxed">
		<p>{t('coverage.source')}</p>
		<p>{t('coverage.freshness')}</p>
		<p>{source === 'frontend' ? t('coverage.frontend') : t('coverage.backend')}</p>
		<p>{t('coverage.proxy')}</p>
		<p>{t('coverage.privacy')}</p>
		<p>{t('coverage.bytes')}</p>
		<p>{t('coverage.latency')}</p>
        <p>{t('coverage.originPolicy')}</p>
        <p>{t('coverage.legacy')}</p>
		{#if snapshot}
			<p>{t('coverage.retention', { days: formatTrafficValue(snapshot.retention_days) })}</p>
			<p>{t('coverage.unlocated', { count: formatTrafficValue(snapshot.totals?.unlocated ?? null), total: formatTrafficValue(snapshot.totals?.requests ?? null) })}</p>
			<dl class="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
				<div><dt>{t('coverage.description')}</dt><dd class="text-ink-1 break-words">{snapshot.coverage.description}</dd></div>
				<div><dt>{t('coverage.geo')}</dt><dd class="text-ink-1">{t(`geo.${snapshot.coverage.geo_source}`)}</dd></div>
                <div><dt>{t('coverage.geoDataset')}</dt><dd class="text-ink-1">{snapshot.coverage.geo_provider ?? t('unknown')} · {snapshot.coverage.geo_version ?? t('unknown')}</dd></div>
                {#if snapshot.coverage.geo_attribution}<div><dt>{t('coverage.geoAttribution')}</dt><dd class="text-ink-1"><a class="underline" href="https://db-ip.com" target="_blank" rel="noreferrer">{snapshot.coverage.geo_attribution}</a></dd></div>{/if}
                <div><dt>{t('coverage.classified')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficValue(snapshot.coverage.classified_requests)}</dd></div>
                <div><dt>{t('origins.legacy_unclassified')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficValue(snapshot.coverage.legacy_unclassified_requests)}</dd></div>
				<div><dt>{t('coverage.unique')}</dt><dd class="text-ink-1 break-words">{snapshot.coverage.unique_method}</dd></div>
				<div><dt>{t('coverage.lastObserved')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficTime(snapshot.coverage.last_observed_at)}</dd></div>
				<div><dt>{t('coverage.since')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficTime(snapshot.coverage.observed_since)}</dd></div>
				<div><dt>{t('coverage.dropped')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficValue(snapshot.coverage.dropped_events)}</dd></div>
				<div><dt>{t('coverage.reporterDropped')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficValue(snapshot.coverage.reporter_dropped_events)}</dd></div>
				<div><dt>{t('coverage.generated')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficTime(snapshot.generated_at)}</dd></div>
			</dl>
            {#each reasonKinds as kind (kind)}
                <h3 class="font-medium text-ink-1">{t(`coverage.${kind}`)}</h3>
                {#if Object.keys(snapshot.coverage[kind]).length === 0}<p>{t('coverage.noUnknownReasons')}</p>
                {:else}<ul class="space-y-1">{#each Object.entries(snapshot.coverage[kind]) as [reason, count] (reason)}<li>{t(`reasons.${reason as UnknownReason}`)}: <span class="tabular-nums">{formatTrafficValue(count ?? null)}</span></li>{/each}</ul>{/if}
            {/each}
		{/if}
	</div>
</Card>
