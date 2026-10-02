<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';
	import { t } from '$lib/i18n/ns/shared';

	interface Props extends HTMLAttributes<HTMLDivElement> {
		size?: 'sm' | 'md' | 'lg';
		color?: 'white' | 'blue' | 'gray';
		children?: Snippet;
	}

	let { size = 'md', color = 'white', children, ...restProps }: Props = $props();
	const loadingFrames = $derived(JSON.stringify(t('spinner.frames')).replaceAll('\\n', '\\A '));

	const sizeClasses = {
		sm: 'text-xs',
		md: 'text-sm',
		lg: 'text-base',
	};

	const colorClasses = {
		white: 'text-ink-0',
		blue:  'text-warm-text',
		gray:  'text-ink-2',
	};
</script>

<div class="inline-flex items-center gap-2" {...restProps}>
	<span
		class="af-loader font-mono font-semibold {sizeClasses[size]} {colorClasses[color]}"
		aria-label={t('spinner.ariaLabel')}
		style:--loader-frames={loadingFrames}
		role="status"
	></span>
	{#if children}
		{@render children()}
	{/if}
</div>

<style>
	.af-loader {
		display: inline-block;
		line-height: 1.2em;
		height: 1.2em;
		overflow: hidden;
		white-space: pre;
	}
	.af-loader::before {
		content: var(--loader-frames);
		display: inline-block;
		white-space: pre;
		animation: af-loader 1s steps(6) infinite;
	}
	@keyframes af-loader {
		100% { transform: translateY(-100%); }
	}
	@media (prefers-reduced-motion: reduce) {
		.af-loader::before { animation: none; }
	}
</style>
