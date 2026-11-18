<script lang="ts">
	import { statusIcons } from './appearance';
	import { pillWidth } from './layout';
	import type { Caption } from './captionLayout';
	import type { IsoStatus } from './types';
	let { caption, status, active }: { caption: Caption; status?: IsoStatus; active: boolean } = $props();
	const icon = $derived(status && statusIcons[status]);
</script>

<g class="caption" class:active transform="translate({caption.position.x} {caption.position.y}) scale({caption.scale})">
	<rect x={-caption.width / 2} width={caption.width} height={caption.height} rx="5" />
	<text class="name" x={caption.status ? -caption.width / 2 + 10 : 0} text-anchor={caption.status ? 'start' : 'middle'} y="17">{caption.name}</text>
	{#if icon}
		<text class="status" text-anchor="end" x={caption.width / 2 - 9} y="17">{caption.status}</text>
		<path d={icon.path} transform="translate({caption.width / 2 - 20 - pillWidth(caption.status, 0)} 9)"
			style:--status-ink="var(--color-state-{icon.tone}-text)" />
	{/if}
	{#if caption.meta}<text class="meta" text-anchor="middle" y="32">{caption.meta}</text>{/if}
</g>

<style>
	rect { fill: var(--color-surface-base); stroke: var(--color-line-2); stroke-width: .9; }
	.active rect { fill: var(--color-surface-selected); stroke: var(--color-ink-0); stroke-width: 1.7; }
	.name { fill: var(--color-ink-0); font-size: 14px; font-weight: 650; }
	.status { fill: var(--color-ink-2); font-size: 13px; font-weight: 550; }
	.meta { fill: var(--color-ink-2); font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums; }
	path { fill: none; stroke: var(--status-ink); stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
</style>
