<script module lang="ts">
	import { tableDesktop as desktop } from '$lib/utils/tableBreakpoint';
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	let { cards, children, class: className = '', embedded = false }: {
		cards: Snippet;
		children: Snippet;
		class?: string;
		/** Inside a Card: hairlines instead of a second bordered box, so surfaces never nest. */
		embedded?: boolean;
	} = $props();
</script>

<div class="responsive-table {className}" class:responsive-table-embedded={embedded} data-responsive-view={desktop.current ? 'table' : 'cards'}>
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
	.responsive-table-embedded :global(.table-shell) { border: 0; border-block: 1px solid var(--color-line); border-radius: 0; background: transparent; }
	.responsive-table-embedded :global(.table-shell tbody tr:last-child > *) { border-bottom: 0; }
	.responsive-table-embedded .responsive-card-list { gap: 0; }
	.responsive-table-embedded :global(.compact-resource-card) { padding-inline: 0; border: 0; border-top: 1px solid var(--color-line); border-radius: 0; background: transparent; }
	.responsive-table-embedded :global(.compact-resource-card[data-selected='true']) { background: var(--color-surface-selected); }
</style>
