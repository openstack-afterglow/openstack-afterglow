<script module lang="ts">
	import { MediaQuery } from 'svelte/reactivity';
	const desktop = new MediaQuery('(min-width: 1024px)', true);
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	let { cards, children, class: className = '' }: {
		cards: Snippet;
		children: Snippet;
		class?: string;
	} = $props();
</script>

<div class="responsive-table {className}" data-responsive-view={desktop.current ? 'table' : 'cards'}>
	{#if desktop.current}
		{@render children()}
	{:else}
		<div class="responsive-card-list">{@render cards()}</div>
	{/if}
</div>

<style>
	.responsive-table { width: 100%; min-width: 0; max-width: 100%; }
	.responsive-card-list {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
		align-items: start;
		gap: 0.5rem;
		min-width: 0;
	}
	.responsive-card-list :global(.responsive-card-toolbar) { grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; min-width: 0; }
</style>
