<script lang="ts">
	import type { Snippet } from 'svelte';
	let { name, identity = name, description, badge }: { name: string; identity?: string; description?: string; badge?: Snippet } = $props();
	const initial = $derived(name.trim().match(/^./u)?.[0].toUpperCase() ?? '');
	const tone = $derived.by(() => {
		let hash = 0;
		for (let i = 0; i < identity.length; i++) hash = (hash * 31 + identity.charCodeAt(i)) >>> 0;
		return hash % 4;
	});
</script>

<span class="name" title={name}>
	<span class="tile" data-tone={tone} aria-hidden="true">{initial}</span>
	<span class="copy">
		<span class="label"><strong>{name}</strong>{@render badge?.()}</span>
		{#if description}<span class="description" title={description}>{description}</span>{/if}
	</span>
</span>

<style>
	.name { display: inline-flex; align-items: center; gap: 0.625rem; max-inline-size: 100%; min-inline-size: 0; color: var(--color-ink-0); }
	.copy { display: grid; min-inline-size: 0; gap: 0.125rem; }
	.label { display: flex; flex-wrap: wrap; align-items: center; gap: 0.125rem 0.375rem; min-inline-size: 0; }
	.description { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--type-support); color: var(--color-ink-2); }
	strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--type-body); font-weight: 600; }
	.tile { display: grid; flex: none; place-items: center; inline-size: 2rem; block-size: 2rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: color-mix(in oklab, var(--tile-color, var(--color-accent)) 13%, var(--color-surface-base)); font-weight: 650; font-size: var(--type-body); }
	.tile[data-tone='1'] { --tile-color: var(--color-state-info); }
	.tile[data-tone='2'] { --tile-color: var(--color-state-success); }
	.tile[data-tone='3'] { --tile-color: var(--color-ink-2); }
</style>
