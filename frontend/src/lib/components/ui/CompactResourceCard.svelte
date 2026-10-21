<script lang="ts">
	import type { Snippet } from 'svelte';
	import { t } from '$lib/i18n/ns/common';
	let { children, actions, details, selected = false, class: className = '' }: {
		children: Snippet;
		actions?: Snippet;
		details?: Snippet;
		selected?: boolean;
		class?: string;
	} = $props();
</script>

<article class="compact-resource-card {className}" data-selected={selected}>
	<div class="compact-resource-body">{@render children()}</div>
	{#if details || actions}
		<div class="compact-resource-footer">
			{#if details}
				<details class="compact-resource-details">
					<summary>{t('resource.details')}</summary>
					<div class="compact-resource-detail-body">{@render details()}</div>
				</details>
			{/if}
			{#if actions}<div class="compact-resource-actions" class:compact-resource-actions-only={!details}>{@render actions()}</div>{/if}
		</div>
	{/if}
</article>

<style>
	.compact-resource-card { min-width: 0; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-base); color: var(--color-ink-0); font-size: 0.8125rem; overflow-wrap: anywhere; }
	.compact-resource-card[data-selected='true'] { border-color: var(--color-accent); background: var(--color-surface-selected); }
	.compact-resource-body { display: grid; gap: 0.5rem; min-width: 0; }
	.compact-resource-card :global(dl) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.5rem 0.75rem; margin: 0; }
	.compact-resource-card :global(dt) { color: var(--color-ink-2); font-size: 0.75rem; }
	.compact-resource-card :global(dd) { min-width: 0; margin: 0; font-variant-numeric: tabular-nums; }
	.compact-resource-card :global(p) { margin-block: 0; }
	.compact-resource-footer { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 0 0.5rem; margin-top: 0.5rem; min-width: 0; }
	.compact-resource-details { min-width: 0; color: var(--color-ink-2); font-size: 0.75rem; }
	.compact-resource-details[open] { grid-column: 1 / -1; }
	.compact-resource-details > summary { display: list-item; min-height: 2.75rem; line-height: 2.75rem; cursor: pointer; list-style: disclosure-closed inside; }
	.compact-resource-details[open] > summary { list-style-type: disclosure-open; }
	.compact-resource-detail-body { min-width: 0; padding-top: 0.25rem; color: var(--color-ink-1); }
	.compact-resource-actions { grid-column: 2; display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 0.5rem; min-width: 0; }
	.compact-resource-actions-only { grid-column: 1 / -1; }
	@media (max-width: 1023px) { .compact-resource-actions :global(button), .compact-resource-actions :global(a) { min-height: 2.75rem; } }
</style>
