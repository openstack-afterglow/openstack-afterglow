<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-network';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import type { TsPoint } from '$lib/types/common';
	import TimeSeriesChart from '$lib/components/TimeSeriesChart.svelte';

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

<div class="mb-6">
	{#if loading}
		<LoadingState variant="section" label={t('adminNetworkTimeseries.loading')} />
	{:else}
		<TimeSeriesChart
			{data}
			title={t('adminNetworkTimeseries.title')}
			mainKey="total"
			extraKeys={['routers', 'floating_ips_used']}
			currentRange={range}
			onRangeChange={onRangeChange}
		/>
	{/if}
</div>
