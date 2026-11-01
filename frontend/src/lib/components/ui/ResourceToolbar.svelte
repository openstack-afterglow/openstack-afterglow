<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		label: string;
		filters?: Snippet;
		actions?: Snippet;
		children?: Snippet;
		class?: string;
		controlsHidden?: boolean;
	}

	let { label, filters, actions, children, controlsHidden = false, class: className = '' }: Props = $props();
</script>

<section class="resource-toolbar {className}" aria-label={label}>
	{#if children || filters}
		<div class="resource-toolbar-controls" hidden={controlsHidden}>
			{#if children}
				<div class="resource-toolbar-content">{@render children()}</div>
			{/if}
			{#if filters}
				<div class="resource-toolbar-filters">{@render filters()}</div>
			{/if}
		</div>
	{/if}
	{#if actions}
		<div class="resource-toolbar-actions">{@render actions()}</div>
	{/if}
</section>

<style>
	.resource-toolbar {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		width: 100%;
		min-width: 0;
		max-width: 100%;
		overflow-wrap: anywhere;
		padding: 0.75rem;
		border: 1px solid var(--color-line);
		border-radius: var(--radius-lg);
		background: var(--color-surface-base);
	}
	.resource-toolbar-controls,
	.resource-toolbar-content,
	.resource-toolbar-filters,
	.resource-toolbar-actions {
		display: flex;
		flex: 1 1 auto;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 0.5rem;
		min-width: 0;
		max-width: 100%;
	}
	.resource-toolbar-controls,
	.resource-toolbar-content,
	.resource-toolbar-filters {
		width: 100%;
	}
	.resource-toolbar-actions {
		width: 100%;
		justify-content: flex-start;
	}
	.resource-toolbar-controls[hidden] { display: none; }
	.resource-toolbar-actions :global(.auto-refresh-control) {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: flex-end;
		width: 100%;
	}
	.resource-toolbar-actions :global(.refresh-frequency .field) {
		flex-direction: column;
		align-items: stretch;
	}
	.resource-toolbar-actions :global(.refresh-frequency select) { width: 100%; }
	@media (min-width: 768px) {
		.resource-toolbar-actions :global(.auto-refresh-control) { width: auto; }
	}
	@media (min-width: 1024px) {
		.resource-toolbar {
			flex-direction: row;
			flex-wrap: wrap;
			align-items: flex-end;
		}
		.resource-toolbar-controls {
			width: auto;
			flex-basis: 32rem;
		}
		.resource-toolbar-actions {
			flex: 0 1 auto;
			width: auto;
			justify-content: flex-end;
			margin-left: auto;
		}
	}
</style>
