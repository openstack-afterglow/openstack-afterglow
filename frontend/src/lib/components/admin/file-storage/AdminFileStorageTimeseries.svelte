<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
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
		<ActivityIndicator size="sm" label={t('fileTimeseries.loading')} />
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
