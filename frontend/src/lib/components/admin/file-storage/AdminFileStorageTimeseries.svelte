<script lang="ts">
	import TimeSeriesChart from '$lib/components/TimeSeriesChart.svelte';
	import type { TsPoint } from '$lib/types/common';

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
		<div class="text-ink-3 text-sm">차트 로딩 중...</div>
	</div>
{:else}
	<TimeSeriesChart
		{data}
		title="파일 스토리지 수 추이"
		mainKey="total"
		currentRange={range}
		onRangeChange={onRangeChange}
	/>
{/if}
