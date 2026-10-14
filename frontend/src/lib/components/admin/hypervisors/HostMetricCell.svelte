<script lang="ts">
	import Spark from '$lib/components/ui/Spark.svelte';
	import { continuousMetricTail, type HostMetric } from '$lib/types/hostHealth';
	import { t } from '$lib/i18n/ns/admin-compute';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	let { metric, verified, label }: { metric: HostMetric; verified: boolean; label: string } = $props();
	const current = $derived(verified && metric.value !== null && Number.isFinite(metric.value) ? metric.value : null);
	const values = $derived(continuousMetricTail(metric.series));
	function formatValue(value: number): string {
		if (metric.unit === '%') return `${value.toLocaleString(intlLocale(), { maximumFractionDigits: 1 })}%`;
		const scale = value >= 1048576 ? 1048576 : value >= 1024 ? 1024 : 1;
		const unit = scale === 1048576 ? 'MiB/s' : scale === 1024 ? 'KiB/s' : 'B/s';
		return `${(value / scale).toLocaleString(intlLocale(), { maximumFractionDigits: 1 })} ${unit}`;
	}
	const formatted = $derived(current === null ? t('hostHealth.unmeasured') : formatValue(current));
</script>

<div class="min-w-0" aria-label={`${label}: ${formatted}`}>
	<span class="block text-xs text-ink-0 tabular-nums">{formatted}</span>
	{#if current !== null && values.length >= 2}
		<Spark data={values} height={22} area={false} class="mt-1 w-full" />
		<span class="block mt-1 text-xs text-ink-2 tabular-nums">{t('hostHealth.range', { min: formatValue(Math.min(...values)), max: formatValue(Math.max(...values)) })}</span>
	{:else}
		<span class="block h-[26px] text-xs text-ink-2">{current === null ? '—' : t('hostHealth.awaitingTrend')}</span>
	{/if}
</div>
