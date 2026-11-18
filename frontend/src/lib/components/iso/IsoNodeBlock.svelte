<script lang="ts">
	import { t } from '$lib/i18n/ns/iso-view';
	import { glyphs, statusIcons, toneVars } from './appearance';
	import { isoLabel, nodeScale, pillWidth, type PlacedNode } from './layout';

	let { placed, active, dimmed }: {
		placed: PlacedNode;
		active: boolean;
		dimmed: boolean;
	} = $props();
	const { node, point } = $derived(placed);
	const name = $derived(isoLabel(node.label));
	const status = $derived(node.status && statusIcons[node.status]);
	const meta = $derived([node.sublabel && isoLabel(node.sublabel, 25), node.status && t(`status.${node.status}`)].filter(Boolean).join(' · '));
	const nameWidth = $derived(pillWidth(name, 26));
	const metaWidth = $derived(pillWidth(meta, status ? 30 : 18));
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
	<g class="labels">
		<rect class="name" x={-nameWidth / 2} y="24" width={nameWidth} height="22" rx="5" />
		<text class="name-text" y="39">{name}</text>
		{#if meta}
			<rect class="meta" x={-metaWidth / 2} y="49" width={metaWidth} height="19" rx="4" />
			{#if status}
				<path class="status" d={status.path} transform="translate({-metaWidth / 2 + 8} 54.5)" style:--status-ink="var(--color-state-{status.tone}-text)" />
			{/if}
			<text class="meta-text" x={status ? 7 : 0} y="62">{meta}</text>
		{/if}
		{#each node.badges?.slice(0, 2) ?? [] as badge, index}
			{@const text = isoLabel(badge.text, 28)}
			{@const width = pillWidth(text, 20)}
			<rect class="badge" style:--badge-tone={toneVars[badge.tone]} x={-width / 2} y={(meta ? 71 : 49) + index * 20} {width} height="18" rx="4" />
			<text class="meta-text" y={(meta ? 84 : 62) + index * 20}>{text}</text>
		{/each}
	</g>
</g>

<style>
	.block { --outline: color-mix(in oklab, var(--tone) 55%, var(--color-line-2)); }
	.footprint { fill: var(--color-surface-sunken); stroke: var(--color-line); stroke-width: 1; }
	.face { stroke: var(--outline); stroke-width: 1.15; stroke-linejoin: round; }
	.top { fill: color-mix(in oklab, var(--tone) 23%, var(--color-surface-raised)); }
	.left { fill: color-mix(in oklab, var(--tone) 35%, var(--color-surface-base)); }
	.right { fill: color-mix(in oklab, var(--tone) 51%, var(--color-surface-base)); }
	.glyph, .status { fill: none; stroke-linecap: round; stroke-linejoin: round; }
	.glyph { stroke: var(--color-ink-0); stroke-width: 1.55; }
	.status { stroke: var(--status-ink); stroke-width: 1.5; }
	.dimmed .face { --tone: var(--color-ink-2); }
	.dimmed .glyph { stroke: var(--color-ink-2); }
	.active .face { --tone: var(--color-ink-2); stroke: var(--color-ink-0); stroke-width: 1.8; }
	.name, .meta, .badge { fill: var(--color-surface-base); stroke: var(--color-line); }
	.active .name { fill: var(--color-surface-selected); stroke: var(--color-ink-0); }
	.badge { stroke: color-mix(in oklab, var(--badge-tone) 48%, var(--color-line)); }
	text { text-anchor: middle; }
	.name-text { fill: var(--color-ink-0); font-size: 13px; font-weight: 650; }
	.meta-text { fill: var(--color-ink-2); font-size: 11px; font-weight: 500; }
</style>
