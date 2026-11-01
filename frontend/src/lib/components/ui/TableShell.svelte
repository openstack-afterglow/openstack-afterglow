<script module lang="ts">
	export type TableDensity = 'compact' | 'normal';
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	interface Props {
		density?: TableDensity;
		stickyHeader?: boolean;
		class?: string;
		children: Snippet;
	}

	let { density = 'normal', stickyHeader = false, class: className = '', children }: Props = $props();
</script>

<div class="table-shell motion-enter table-density-{density} {className}" class:table-sticky={stickyHeader}>
	{@render children()}
</div>

<style>
	.table-shell {
		/* Contain absolute sr-only labels inside the horizontal scroll viewport. */
		position: relative;
		overflow-x: auto;
		border: 1px solid var(--color-line);
		border-radius: var(--radius-lg);
		background: var(--color-surface-base);
	}
	.table-shell :global(table) {
		width: 100%;
		min-width: max-content;
		border-collapse: collapse;
		font-family: var(--font-sans);
		font-variant-numeric: tabular-nums;
	}
	.table-shell :global(thead) {
		background: var(--color-surface-sunken);
		color: var(--color-ink-2);
	}
	.table-shell :global(th),
	.table-shell :global(td) {
		border-bottom: 1px solid var(--color-line);
		text-align: left;
	}
	.table-shell :global(th) {
		font-size: var(--type-support);
		font-weight: 500;
	}
	.table-shell :global(td) {
		font-size: var(--type-body);
	}
	.table-density-normal :global(th),
	.table-density-normal :global(td) { height: var(--table-row-height); padding: 0.1875rem 1rem; }
	.table-density-compact :global(th),
	.table-density-compact :global(td) { height: var(--table-row-compact-height); padding: 0 0.75rem; }
	.table-shell :global(tbody tr:hover) { background: var(--color-surface-sunken); }
	.table-shell :global(tbody tr[data-selected='true']) { background: var(--color-surface-selected); }
	.table-sticky :global(thead) {
		position: sticky;
		top: 0;
		z-index: 2;
	}
	@media (pointer: coarse) {
		.table-density-compact :global(th),
		.table-density-compact :global(td) { height: 2.75rem; }
	}
</style>
