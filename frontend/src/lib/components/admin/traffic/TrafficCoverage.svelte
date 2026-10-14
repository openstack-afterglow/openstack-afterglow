<script lang="ts">
	import { Card } from '$lib/components/ui';
	import { t } from '$lib/i18n/ns/traffic-analytics';
	import type { TrafficSnapshot, TrafficSource } from '$lib/types/trafficAnalytics';
	import { formatTrafficTime, formatTrafficValue } from '$lib/utils/trafficFormat';
	let { snapshot, source }: { snapshot: TrafficSnapshot | null; source: TrafficSource } = $props();
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
		{#if snapshot}
			<p>{t('coverage.retention', { days: formatTrafficValue(snapshot.retention_days) })}</p>
			<p>{t('coverage.unlocated', { count: formatTrafficValue(snapshot.totals?.unlocated ?? null), total: formatTrafficValue(snapshot.totals?.requests ?? null) })}</p>
			<dl class="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
				<div><dt>{t('coverage.description')}</dt><dd class="text-ink-1 break-words">{snapshot.coverage.description}</dd></div>
				<div><dt>{t('coverage.geo')}</dt><dd class="text-ink-1">{t(`geo.${snapshot.coverage.geo_source}`)}</dd></div>
				<div><dt>{t('coverage.unique')}</dt><dd class="text-ink-1 break-words">{snapshot.coverage.unique_method}</dd></div>
				<div><dt>{t('coverage.lastObserved')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficTime(snapshot.coverage.last_observed_at)}</dd></div>
				<div><dt>{t('coverage.since')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficTime(snapshot.coverage.observed_since)}</dd></div>
				<div><dt>{t('coverage.dropped')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficValue(snapshot.coverage.dropped_events)}</dd></div>
				<div><dt>{t('coverage.reporterDropped')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficValue(snapshot.coverage.reporter_dropped_events)}</dd></div>
				<div><dt>{t('coverage.generated')}</dt><dd class="text-ink-1 tabular-nums">{formatTrafficTime(snapshot.generated_at)}</dd></div>
			</dl>
		{/if}
	</div>
</Card>
