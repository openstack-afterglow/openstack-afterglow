<script lang="ts">
	import { untrack } from 'svelte';
	import type { ToolActivityItem } from '$lib/api/chatToolActivity';
	import type { ToolActivitySource } from '$lib/api/chatContracts';
	import ToolCallCard from './ToolCallCard.svelte';

	interface Props {
		category: string;
		items: ToolActivityItem[];
		source: ToolActivitySource;
		animate?: boolean;
	}
	let { category, items, source, animate = false }: Props = $props();
	const initialIds = untrack(() => new Set(items.map((item) => item.id ?? item.name)));
	const sourceIcon = $derived(items.some((item) => /web_search|web_fetch/.test(item.name))
		? 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M3 12h18M12 3c4 4 4 14 0 18-4-4-4-14 0-18'
		: source === 'mcp' || source === 'plugin' || source === 'custom_http'
			? 'm8 15-2 2a3 3 0 0 1-4-4l5-5a3 3 0 0 1 4 0m2 1 2-2a3 3 0 0 1 4 4l-5 5a3 3 0 0 1-4 0m-2-1 6-6'
			: source === 'managed'
				? 'M7 18h11a4 4 0 0 0 0-8 6 6 0 0 0-12-1 4.5 4.5 0 0 0 1 9'
				: source === 'workspace'
					? 'M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6'
					: 'm8 5-6 7 6 7m8-14 6 7-6 7M14 3l-4 18');
</script>

<div class="tool-category">
	<p class="category-title">
		<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d={sourceIcon} stroke-linecap="round" stroke-linejoin="round" /></svg>
		{category}
	</p>
	<div class="tool-list">
		{#each items as item (item.id ?? item.name)}
			<div class:motion-enter={animate && !initialIds.has(item.id ?? item.name)}><ToolCallCard {item} {animate} /></div>
		{/each}
	</div>
</div>

<style>
	.tool-category { min-width: 0; }
	.category-title { display: flex; align-items: center; gap: 0.375rem; margin: 0.25rem 0 0.5rem; color: var(--color-ink-2); font-size: var(--type-support); overflow-wrap: anywhere; }
	.category-title svg { flex-shrink: 0; }
	.tool-list { display: grid; gap: 0.375rem; min-width: 0; }
</style>
