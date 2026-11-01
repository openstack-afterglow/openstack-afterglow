<script module lang="ts">
	export type LoadingIndicator = 'dots' | 'bars' | 'brackets' | 'spinner' | 'wave';
	export type LoadingVariant = 'surface' | 'section' | 'table' | 'inline' | 'control';
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';
	import { t } from '$lib/i18n/ns/shared';
	import AfterglowOrbit from './AfterglowOrbit.svelte';
	import type { AfterglowGeometry } from './afterglowLoadingScene';
	import { characterStep, flowBar, skeletonCell } from './characterTicker';
	import { statusSignal } from '$lib/design/characterFormats.js';

	interface Props extends HTMLAttributes<HTMLDivElement> {
		/**
		 * Visual scale follows output/afterglow-loading:
		 * - `surface`: a whole page/panel or a large primary list — the full authored Afterglow scene.
		 * - `section`: a card/subregion — the character loading bar (`[···###:··]`), no percentage.
		 * - `table`: a table body — column-preserving `··::··` rows; row count stays unconfirmed.
		 * - `inline`/`control`: rows, buttons, pickers — the rotating `[ | ]` status strip.
		 */
		variant?: LoadingVariant;
		/** Compact status glyph; the character spinner is the product default. */
		indicator?: LoadingIndicator;
		label?: string;
		children?: Snippet;
		as?: 'div' | 'span';
		/** `table` only: number of columns to keep (default 5). */
		columns?: number;
		/** `table` only: placeholder rows (default 5). */
		rows?: number;
	}
	let { variant = 'section', indicator = 'spinner', label, children, as, columns = 5, rows = 5, class: className = '', ...rest }: Props = $props();
	const compact = $derived(variant === 'inline' || variant === 'control');
	const tag = $derived(compact ? 'span' : as ?? 'div');
	const copy = $derived(label ?? t('loadingState.label'));
	let geometry = $state<AfterglowGeometry | null>(null);
</script>

<svelte:element this={tag} class="loading-state loading-state--{variant} {className}" role={copy || children ? 'status' : undefined} aria-live={copy || children ? 'polite' : undefined} aria-atomic={copy || children ? 'true' : undefined} {...rest}>
	{#if variant === 'surface'}
		<span class="loading-state__art" aria-hidden="true"><AfterglowOrbit ongeometry={value => { geometry = value; }} /></span>
	{:else if variant === 'section'}
		<span class="loading-state__bar" data-art={flowBar($characterStep)} aria-hidden="true"></span>
	{:else if variant === 'table'}
		<span class="loading-state__grid" style:--columns={columns} aria-hidden="true">
			{#each { length: rows } as _, row}{#each { length: columns } as _, column}<span data-art={skeletonCell($characterStep, row * columns + column)}></span>{/each}{/each}
		</span>
	{:else}
		<span class="loading-state__glyph" data-art={statusSignal(indicator, $characterStep)} aria-hidden="true"></span>
	{/if}
	{#if children || copy}
		<svelte:element this={compact ? 'span' : 'div'} class="loading-state__copy" style:--orbit-center-x={variant === 'surface' && geometry ? `${geometry.centerX}px` : undefined} style:--orbit-center-y={variant === 'surface' && geometry ? `${geometry.centerY}px` : undefined} style:--orbit-radius={variant === 'surface' && geometry ? `${geometry.radius}px` : undefined}>
			{#if variant === 'table'}<span class="loading-state__signal" data-art="[ :: :: :: ]" aria-hidden="true"></span>{/if}
			{#if children}{@render children()}{:else}{copy}{/if}
		</svelte:element>
	{/if}
</svelte:element>

<style>
	.loading-state { position: relative; min-width: 0; }
	.loading-state__bar, .loading-state__grid, .loading-state__glyph, .loading-state__signal { font-family: var(--font-mono); }
	/* Decorative characters are generated content so visible/accessible text stays the owner's copy. */
	[data-art]::before { content: attr(data-art); }

	.loading-state--surface { display: block; isolation: isolate; flex: 1 1 auto; align-self: stretch; width: 100%; height: 100%; overflow: hidden; background: var(--afterglow-artwork-base); color: var(--afterglow-artwork-ink); }
	/* Default size sits below Tailwind's utilities layer: unlayered component CSS would otherwise
	   silently beat a caller's `min-h-*` (e.g. a detail panel asking for the full viewport). */
	@layer components { .loading-state--surface { min-height: 20rem; } }
	.loading-state__art { position: absolute; inset: 0; display: block; overflow: hidden; pointer-events: none; }
	.loading-state--surface .loading-state__copy { position: absolute; top: var(--orbit-center-y, 32%); left: var(--orbit-center-x, 50%); width: min(calc(var(--orbit-radius, 3.5rem) * 1.45), 80%); transform: translate(-50%, -50%); text-align: center; font-size: var(--type-support); line-height: 1.5; text-wrap: balance; overflow-wrap: anywhere; }

	.loading-state--section { display: grid; justify-items: center; gap: 0.75rem; width: 100%; padding: 1.75rem 1rem; color: var(--color-ink-2); font-size: var(--type-support); text-align: center; overflow-wrap: anywhere; }
	.loading-state__bar { display: block; max-width: 100%; margin: 0; overflow: hidden; color: var(--color-warm); font-size: clamp(0.65rem, 1.1vw, 0.9rem); white-space: pre; user-select: none; }

	.loading-state--table { display: grid; gap: 1rem; width: 100%; padding-block: 0.5rem; color: var(--color-ink-2); font-size: 0.6875rem; }
	.loading-state__grid { display: grid; grid-template-columns: repeat(var(--columns), minmax(0, 1fr)); user-select: none; }
	.loading-state__grid > span { padding: 1rem 0.75rem; border-bottom: 1px solid var(--color-line); color: var(--color-warm-2, var(--color-warm)); opacity: 0.5; white-space: pre; overflow: hidden; letter-spacing: 0.1em; }
	.loading-state--table .loading-state__copy { display: flex; flex-wrap: wrap; gap: 0.75rem; }
	.loading-state__signal { color: var(--color-warm); }

	.loading-state--inline, .loading-state--control { display: inline-flex; align-items: center; gap: 0.5rem; max-width: 100%; vertical-align: middle; color: inherit; }
	.loading-state--inline .loading-state__copy, .loading-state--control .loading-state__copy { min-width: 0; }
	.loading-state__glyph { white-space: pre; flex: none; color: var(--color-warm); font-size: 0.85em; }
	:global(:is(.btn-primary, .btn-accent)) .loading-state__glyph { color: inherit; }

	@media (forced-colors: active) {
		.loading-state { color: CanvasText; }
		.loading-state--surface { background: Canvas; }
		.loading-state__bar, .loading-state__grid > span, .loading-state__glyph, .loading-state__signal { color: CanvasText; }
	}
</style>
