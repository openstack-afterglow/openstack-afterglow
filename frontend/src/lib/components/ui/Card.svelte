<script module lang="ts">
	export type CardSurface = 'raised' | 'base' | 'sunken' | 'subtle' | 'modal';
	export type CardPadding = 'none' | 'sm' | 'md' | 'lg';
	export type CardDecoration = 'none' | 'warm-glow';
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	interface Props {
		surface?: CardSurface;
		padding?: CardPadding;
		decorated?: CardDecoration;
		class?: string;
		children: Snippet;
	}

	let {
		surface = 'raised',
		padding = 'md',
		decorated = 'none',
		class: className = '',
		children,
	}: Props = $props();
</script>

<div class="card card-{surface} card-pad-{padding} card-decor-{decorated} {className}">
	{@render children()}
</div>

<style>
	.card {
		position: relative;
		overflow: hidden;
		border: 1px solid var(--color-line);
		border-radius: 0.5rem;
		color: var(--color-ink-0);
	}

	.card-raised,
	.card-modal { background: var(--color-surface-raised); }
	.card-base { background: var(--color-surface-base); }
	.card-sunken { background: var(--color-surface-sunken); }
	.card-subtle { background: color-mix(in oklab, var(--color-surface-raised) 72%, transparent); }
	.card-modal {
		border-radius: 0.75rem;
		box-shadow: 0 24px 72px color-mix(in oklab, var(--color-surface-canvas) 78%, transparent);
	}

	.card-pad-none { padding: 0; }
	.card-pad-sm { padding: 0.75rem; }
	.card-pad-md { padding: 1rem; }
	.card-pad-lg { padding: 1.5rem; }

	.card-decor-warm-glow::before {
		content: '';
		position: absolute;
		top: 0;
		left: 0;
		width: 60%;
		height: 60%;
		background: radial-gradient(ellipse at top left, color-mix(in oklab, var(--color-warm) 5%, transparent) 0%, transparent 70%);
		pointer-events: none;
		border-radius: inherit;
	}
</style>
