<script module lang="ts">
	export const connectionTabs = ['browse', 'connected', 'manage'] as const;
	export type ConnectionTab = typeof connectionTabs[number];
</script>

<script lang="ts">
	import { t } from '$lib/i18n/ns/mcp-gallery';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	let { selected, count, id, onchange }: {
		selected: ConnectionTab; count: number; id: string; onchange: (tab: ConnectionTab) => void;
	} = $props();

	function moveFocus(event: KeyboardEvent, index: number) {
		const last = connectionTabs.length - 1;
		const next = event.key === 'Home' ? 0 : event.key === 'End' ? last
			: event.key === 'ArrowRight' ? (index + 1) % connectionTabs.length
			: event.key === 'ArrowLeft' ? (index + last) % connectionTabs.length : undefined;
		if (next === undefined) return;
		event.preventDefault();
		document.getElementById(`${id}-tab-${connectionTabs[next]}`)?.focus();
	}
</script>

<div class="connection-tabs" role="tablist" aria-label={t('workspace.title')}>
	{#each connectionTabs as tab, index (tab)}
		<button id={`${id}-tab-${tab}`} type="button" role="tab" aria-selected={selected === tab} aria-controls={`${id}-panel-${tab}`}
			tabindex={selected === tab ? 0 : -1} onkeydown={(event) => moveFocus(event, index)} onclick={() => onchange(tab)}>
			{t(`workspace.${tab}`)}
			{#if tab === 'connected'}<span class="count">{count.toLocaleString(intlLocale())}</span>{/if}
		</button>
	{/each}
</div>

<style>
	.connection-tabs { display: flex; gap: 0.25rem; inline-size: max-content; max-inline-size: 100%; overflow-x: auto; padding: 0.1875rem; border-radius: var(--radius-lg); background: var(--color-surface-sunken); }
	button { position: relative; display: inline-flex; flex: none; align-items: center; gap: 0.375rem; min-block-size: var(--control-height); padding-inline: 0.625rem; border-radius: var(--radius-md); white-space: nowrap; font-size: var(--type-support); font-weight: 600; color: var(--color-ink-2); }
	button:hover, button[aria-selected='true'] { color: var(--color-ink-0); background: var(--color-surface-raised); }
	button[aria-selected='true']::after { content: ''; position: absolute; inset: auto 0.625rem 0.1875rem; border-block-end: 2px solid var(--color-accent); }
	button:focus-visible { outline: 2px solid var(--color-accent); outline-offset: -2px; }
	.count { min-inline-size: 1.125rem; border-radius: var(--radius-sm); padding-inline: 0.25rem; background: var(--color-surface-base); text-align: center; font-variant-numeric: tabular-nums; }
	@media (max-width: 767px), (pointer: coarse) { button { min-block-size: var(--control-touch-height); } }
</style>
