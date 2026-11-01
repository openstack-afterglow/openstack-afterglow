<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
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
	<LoadingState variant="section" label={t('fileTimeseries.loading')} />
{:else}
	<TimeSeriesChart
		{data}
		title={t('fileTimeseries.title')}
		mainKey="total"
		currentRange={range}
		onRangeChange={onRangeChange}
	/>
{/if}
