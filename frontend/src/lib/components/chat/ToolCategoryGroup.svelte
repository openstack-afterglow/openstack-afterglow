<script lang="ts">
	import type { ToolActivityItem } from '$lib/api/chatToolActivity';
	import ToolCallCard from './ToolCallCard.svelte';

	interface Props {
		category: string;
		items: ToolActivityItem[];
		active?: boolean;
	}
	let { category, items, active = false }: Props = $props();
	let open = $state(false);
	let wasActive = false;

	$effect(() => {
		if (active && !wasActive) open = true;
		wasActive = active;
	});

	const running = $derived(items.some((item) => item.running));
</script>

<details class="tool-category" bind:open>
	<summary>
		<span class:active={running} class="category-dot" aria-hidden="true"></span>
		<span class="category-title">{category}</span>
		<span class="category-count">{items.length}개</span>
		<svg class="chevron" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
			<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
		</svg>
	</summary>
	<div class="tool-list">
		{#each items as item (item.id ?? item.name)}
			<ToolCallCard {item} />
		{/each}
	</div>
</details>

<style>
	.tool-category {
		border: 1px solid var(--color-line);
		border-radius: 0.5rem;
		background: color-mix(in oklab, var(--color-surface-sunken) 76%, transparent);
	}
	summary {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.45rem 0.55rem;
		cursor: pointer;
		list-style: none;
		color: var(--color-ink-2);
		font-size: 0.75rem;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	.category-dot {
		width: 0.4rem;
		height: 0.4rem;
		border-radius: 50%;
		background: var(--color-state-info);
	}
	.category-dot.active {
		background: var(--color-warm);
		box-shadow: 0 0 0 3px color-mix(in oklab, var(--color-warm) 20%, transparent);
	}
	.category-title {
		font-weight: 600;
		color: var(--color-ink-1);
	}
	.category-count {
		color: var(--color-ink-2);
	}
	.chevron {
		margin-left: auto;
		color: var(--color-ink-2);
		transition: transform var(--motion-duration-fast) var(--motion-ease-standard);
	}
	details[open] .chevron {
		transform: rotate(180deg);
	}
	.tool-list {
		display: grid;
		gap: 0.35rem;
		border-top: 1px solid var(--color-line);
		padding: 0.45rem;
	}
	@media (prefers-reduced-motion: reduce) {
		.chevron {
			transition: none;
		}
	}
</style>
