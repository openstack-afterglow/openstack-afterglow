<script lang="ts">
	import TimeSeriesChart from '$lib/components/TimeSeriesChart.svelte';
	import type { TsPoint } from '$lib/types/common';
	import { t } from '$lib/i18n/ns/admin-storage';

	let {
		data,
		loading,
		range,
		onRangeChange,
	}: {
		data: TsPoint[];
		loading: boolean;
		range: string;
		onRangeChange: (r: string) => void;
	} = $props();
</script>

{#if loading}
	<div class="bg-surface-base border border-line rounded-xl p-5 h-48 flex items-center justify-center">
		<div class="text-ink-2 text-sm">{t('fileTimeseries.loading')}</div>
	</div>
{:else}
	<TimeSeriesChart
		{data}
		title={t('fileTimeseries.title')}
		mainKey="total"
		currentRange={range}
		onRangeChange={onRangeChange}
	/>
{/if}
