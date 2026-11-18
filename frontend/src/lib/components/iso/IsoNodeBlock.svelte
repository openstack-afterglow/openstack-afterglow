<script lang="ts">
	import { t } from '$lib/i18n/ns/iso-view';
	import { glyphs, toneVars } from './appearance';
	import { nodeScale, type PlacedNode } from './layout';

	let { placed, active, dimmed }: {
		placed: PlacedNode;
		active: boolean;
		dimmed: boolean;
	} = $props();
	const { node, point } = $derived(placed);
</script>

<g transform="translate({point.x} {point.y})" style:--tone={toneVars[node.tone]} class:active>
	<title>{[node.label, node.sublabel, node.status && t(`status.${node.status}`), ...(node.badges ?? []).map((badge) => badge.text)].filter(Boolean).join(' · ')}</title>
	<g transform="scale({nodeScale(node)})" class:dimmed class="block">
		<path class="footprint" d="M0 -24 42 0 0 24 -42 0Z" />
		<path class="face left" d="M-37 -24 0 -3V18L-37 -3Z" />
		<path class="face right" d="M37 -24 0 -3V18L37 -3Z" />
		<path class="face top" d="M0 -45 37 -24 0 -3 -37 -24Z" />
		<path class="glyph" d={glyphs[node.kind]} transform="translate(-11 -35) scale(.9167)" />
	</g>
</g>

<style>
	.block { --outline: color-mix(in oklab, var(--tone) 55%, var(--color-line-2)); }
	.footprint { fill: var(--color-surface-sunken); stroke: var(--color-line); stroke-width: 1; }
	.face { stroke: var(--outline); stroke-width: 1.15; stroke-linejoin: round; }
	.top { fill: color-mix(in oklab, var(--tone) 23%, var(--color-surface-raised)); }
	.left { fill: color-mix(in oklab, var(--tone) 35%, var(--color-surface-base)); }
	.right { fill: color-mix(in oklab, var(--tone) 51%, var(--color-surface-base)); }
	.glyph { fill: none; stroke-linecap: round; stroke-linejoin: round; }
	.glyph { stroke: var(--color-ink-0); stroke-width: 1.55; }
	.dimmed .face { --tone: var(--color-ink-2); }
	.dimmed .glyph { stroke: var(--color-ink-2); }
	.active .face { --tone: var(--color-ink-2); stroke: var(--color-ink-0); stroke-width: 1.8; }
</style>
