<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { formatBps } from './topologyHelpers.ts';
	import type { TopologyTraffic } from './types.ts';

	let {
		searchTerm = $bindable(''),
		isLight = false,
		traffic = null,
		totalTraffic,
	}: {
		searchTerm?: string;
		isLight?: boolean;
		traffic?: TopologyTraffic | null;
		totalTraffic: { rx: number; tx: number };
	} = $props();
</script>

<div class="flex items-center gap-3 mb-4 flex-wrap">
	<input
		type="text"
		placeholder={t('header.search')}
		bind:value={searchTerm}
		class="text-xs px-3 py-1.5 rounded-lg focus:outline-none focus:border-action-warm w-52
			{isLight
				? 'bg-gray-100 border border-gray-300 text-gray-900 placeholder-ink-3'
				: 'bg-surface-sunken border border-line-2 text-ink-1 placeholder-ink-3'}"
	/>
	{#if traffic?.interfaces || traffic?.ts}
		<div class="ml-auto flex items-center gap-3 text-xs"
		     style="color: {isLight ? '#6b7280' : '#9ca3af'}">
			{#if traffic?.interfaces}
				<div class="flex items-center gap-1.5 font-mono">
					<span style="color: {isLight ? '#9ca3af' : '#6b7280'}">{t('header.total')}</span>
					<span class="text-warm-text">↓{formatBps(totalTraffic.rx)}</span>
					<span class="text-green-400">↑{formatBps(totalTraffic.tx)}</span>
				</div>
			{/if}
			{#if traffic?.ts}
				<!-- 트래픽 폴링이 표본을 돌려주는 동안의 실시간 상태. reduced-motion 이면 멈춘 점으로 남는다. -->
				<ActivityIndicator variant="pulse" tone="success" size="xs" label={t('header.live')} />
			{/if}
		</div>
	{/if}
</div>
