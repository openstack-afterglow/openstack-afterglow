<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		label: string;
		filters?: Snippet;
		actions?: Snippet;
		children?: Snippet;
		class?: string;
	}

	let { label, filters, actions, children, class: className = '' }: Props = $props();
</script>

<section class="resource-toolbar {className}" aria-label={label}>
	<div class="resource-toolbar-controls">
		{#if children}
			<div class="resource-toolbar-content">{@render children()}</div>
		{/if}
		{#if filters}
			<div class="resource-toolbar-filters">{@render filters()}</div>
		{/if}
	</div>
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
		padding: 0.75rem;
		border: 1px solid var(--color-line);
		border-radius: 0.5rem;
		background: var(--color-surface-base);
	}
	.resource-toolbar-controls,
	.resource-toolbar-content,
	.resource-toolbar-filters,
	.resource-toolbar-actions {
		display: flex;
		flex: 1 1 auto;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
	}
	.resource-toolbar-controls,
	.resource-toolbar-filters {
		width: 100%;
	}
	.resource-toolbar-actions {
		justify-content: flex-start;
	}
	@media (min-width: 1024px) {
		.resource-toolbar {
			flex-direction: row;
			align-items: center;
		}
		.resource-toolbar-controls {
			width: auto;
		}
		.resource-toolbar-actions {
			flex: 0 1 auto;
			justify-content: flex-end;
			margin-left: auto;
		}
	}
</style>
