<script lang="ts">
	import TrafficArea from '$lib/components/ui/TrafficArea.svelte';
	import { t } from '$lib/i18n/ns/waygate';
	import type { WaygateClient } from '$lib/types/waygate';
	import {
		clientTrafficTotals,
		currentClientTraffic,
		formatTrafficBytes,
		waygateTrafficFreshnessMs,
		WAYGATE_TRAFFIC_STALE_MS,
		type ClientTrafficHistory,
	} from '$lib/utils/waygateTraffic';

	interface Props { client: WaygateClient; history?: ClientTrafficHistory; now: number; pollIntervalSeconds?: number; }
	let { client, history, now, pollIntervalSeconds }: Props = $props();
	const freshnessMs = $derived(pollIntervalSeconds === undefined ? WAYGATE_TRAFFIC_STALE_MS : waygateTrafficFreshnessMs(client.report_interval_seconds, pollIntervalSeconds));
	const current = $derived(currentClientTraffic(history, now, freshnessMs));
	const totals = $derived(clientTrafficTotals(client));
	const reportAge = $derived.by(() => {
		if (!client.last_reported_at) return null;
		const reportedAt = Date.parse(client.last_reported_at);
		return Number.isFinite(reportedAt) ? Math.max(0, Math.floor((now - reportedAt) / 1000)) : null;
	});
	const reportState = $derived.by(() => {
		if (!client.enabled) return t('traffic.disabled');
		if (!history?.samples.length) return t('traffic.waiting');
		if (!current.fresh) return t('traffic.delayed');
		if (client.online === false) return t('traffic.noHandshake');
		return current.rxRate === null && current.txRate === null ? t('traffic.awaitingRate') : t('traffic.recent');
	});
	const rows = $derived([
		{ key: 'rx', label: t('traffic.rxRow'), total: totals.rxBytes, rate: current.rxRate },
		{ key: 'tx', label: t('traffic.txRow'), total: totals.txBytes, rate: current.txRate },
	]);
</script>

<section class="mt-4 min-w-0 border-t border-line pt-3" aria-label={t('traffic.ariaLabel', { name: client.name })}>
	<div class="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-ink-2">
		<span class="font-medium text-ink-1">{t('traffic.title')}</span>
		<span role="status">{reportState}</span>
	</div>
	{#if pollIntervalSeconds !== undefined}
		<p class="mb-3 text-xs text-ink-2">
			{t('traffic.reportSummary', { ageKnown: reportAge === null ? 'no' : 'yes', age: reportAge ?? 0, intervalKnown: client.report_interval_seconds == null ? 'no' : 'yes', interval: client.report_interval_seconds ?? 0 })}
		</p>
	{/if}
	{#snippet metrics()}
	<dl class="mb-3 grid grid-cols-1 gap-3 text-sm tabular-nums md:grid-cols-2">
		{#each rows as row (row.key)}
			<div class="min-w-0">
				<dt class="text-xs text-ink-2">{row.label}</dt>
				<dd class="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-ink-0">
					<span>{formatTrafficBytes(row.total)} <span class="text-xs text-ink-2">{t('traffic.total')}</span></span>
					<span>{row.rate === null ? t('traffic.unknownRate') : `${formatTrafficBytes(row.rate)}/s`}</span>
				</dd>
			</div>
		{/each}
	</dl>
	{/snippet}
	{#if client.enabled}
		<TrafficArea samples={history?.samples ?? []} rxLabel={t('traffic.rxLabel')} txLabel={t('traffic.txLabel')} fresh={current.fresh}>
			{@render metrics()}
		</TrafficArea>
	{:else}
		{@render metrics()}
	{/if}
	<p class="mt-2 text-xs text-ink-2">
		{t('traffic.countersHelp')}
	</p>
</section>
