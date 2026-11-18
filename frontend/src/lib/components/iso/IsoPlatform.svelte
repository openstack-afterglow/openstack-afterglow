<script lang="ts">
	import { toneVars } from './appearance';
	import { isoLabel, pillWidth, pointString, type PlacedPlatform } from './layout';

	let { placed, active, labels = false }: {
		placed: PlacedPlatform;
		active: boolean;
		labels?: boolean;
	} = $props();
	const { platform, corners, label } = $derived(placed);
	const zone = $derived(platform.style === 'zone');
	const name = $derived(isoLabel(platform.label, 26));
	const meta = $derived(isoLabel(platform.sublabel ?? '', 30));
	const width = $derived(Math.max(pillWidth(name, 28), pillWidth(meta, 20)));
</script>

<g style:--tone={toneVars[platform.tone]} class:active>
	{#if labels}
		<g transform="translate({label.x} {label.y})">
			<title>{[platform.label, platform.sublabel].filter(Boolean).join(' · ')}</title>
			<rect class="pill" x={-width / 2} y={zone ? -19 : 1} {width} height={meta ? 38 : 23} rx="5" />
			<path class="notch" d="M0 2 4 0 8 2 4 4z" transform="translate({-width / 2 + 8} {zone ? -9 : 11})" />
			<text class="name" x={-width / 2 + 23} y={zone ? -4 : 16}>{name}</text>
			{#if meta}<text class="meta" x={-width / 2 + 8} y={zone ? 11 : 31}>{meta}</text>{/if}
		</g>
	{:else}
		{#if !zone}
			<polygon class="rim left" points={pointString([corners[3], corners[2], { ...corners[2], y: corners[2].y + 7 }, { ...corners[3], y: corners[3].y + 7 }])} />
			<polygon class="rim right" points={pointString([corners[2], corners[1], { ...corners[1], y: corners[1].y + 7 }, { ...corners[2], y: corners[2].y + 7 }])} />
		{/if}
		<polygon class="surface" class:zone points={pointString(corners)} />
	{/if}
</g>

<style>
	.surface, .rim, .pill { stroke: color-mix(in oklab, var(--tone) 62%, var(--color-line)); stroke-width: 1.1; stroke-linejoin: round; }
	.surface { fill: color-mix(in oklab, var(--tone) 9%, var(--color-surface-raised)); }
	.surface.zone { fill: color-mix(in oklab, var(--tone) 4%, transparent); stroke-dasharray: 5 5; }
	.left { fill: color-mix(in oklab, var(--tone) 20%, var(--color-surface-base)); }
	.right { fill: color-mix(in oklab, var(--tone) 35%, var(--color-surface-base)); }
	.pill { fill: var(--color-surface-base); }
	.notch { fill: var(--tone); }
	.active { --tone: var(--color-ink-2); }
	.active .surface, .active .pill { fill: var(--color-surface-selected); stroke: var(--color-ink-0); stroke-width: 1.7; }
	.name { fill: var(--color-ink-0); font-size: 12px; font-weight: 650; }
	.meta { fill: var(--color-ink-2); font-size: 11px; font-variant-numeric: tabular-nums; }
</style>
