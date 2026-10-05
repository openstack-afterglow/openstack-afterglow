<script lang="ts">
	import type { TsPoint } from '$lib/types/common';
	import TimeSeriesChart from '$lib/components/TimeSeriesChart.svelte';
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

<div class="mb-6">
	{#if loading}
		<div class="bg-surface-base border border-line rounded-xl p-5 h-48 flex items-center justify-center">
			<div class="text-ink-2 text-sm">{t('volumeList.chartLoading')}</div>
		</div>
	{:else}
		<TimeSeriesChart
			{data}
			title={t('volumeList.chartTitle')}
			mainKey="total"
			extraKeys={['in_use', 'available']}
			currentRange={range}
			onRangeChange={onRangeChange}
		/>
	{/if}
</div>
