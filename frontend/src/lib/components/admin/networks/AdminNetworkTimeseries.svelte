<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-network';
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
		<div class="bg-surface-base border border-line rounded-xl p-5 h-48 flex items-center justify-center">
			<div class="text-ink-2 text-sm">{t('adminNetworkTimeseries.loading')}</div>
		</div>
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
