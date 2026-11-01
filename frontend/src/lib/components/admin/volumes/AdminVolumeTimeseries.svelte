<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import type { TsPoint } from '$lib/types/common';
	import TimeSeriesChart from '$lib/components/TimeSeriesChart.svelte';
	import { t } from '$lib/i18n/ns/admin-storage';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';

	let {
		data,
		loading,
		range,
		error = '',
		onRetry,
		onRangeChange,
	}: {
		data: TsPoint[];
		loading: boolean;
		range: string;
		error?: string;
		onRetry?: () => void;
		onRangeChange: (r: string) => void;
	} = $props();
</script>

<div>
	{#if loading}
		<LoadingState variant="section" label={t('volumeList.chartLoading')} />
	{:else if error}
		<Alert tone="danger">{error}</Alert>
		{#if onRetry}<Button variant="outline" onclick={onRetry}>{t('volumeList.retryChart')}</Button>{/if}
	{:else if data.length === 0}
		<p class="py-4 text-sm text-ink-2" role="status">{t('volumeList.chartEmpty')}</p>
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
