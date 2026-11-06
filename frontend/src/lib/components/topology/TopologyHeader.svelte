<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import { formatBps } from './topologyHelpers.ts';
	import type { TopologyTraffic } from './types.ts';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

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
	<RegexSearch id="topology-lane-search" bind:value={searchTerm} label={t('toolbar.searchLabel')} placeholder={t('header.search')} class="min-w-0 flex-1" />
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
				<span class="text-xs text-ink-2">{t('header.live')}</span>
			{/if}
		</div>
	{/if}
</div>
