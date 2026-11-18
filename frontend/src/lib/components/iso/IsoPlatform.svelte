<script lang="ts">
	import { toneVars } from './appearance';
	import { pointString, type PlacedPlatform } from './layout';

	let { placed, active }: {
		placed: PlacedPlatform;
		active: boolean;
	} = $props();
	const { platform, corners } = $derived(placed);
	const zone = $derived(platform.style === 'zone');
</script>

<g style:--tone={toneVars[platform.tone]} class:active>
	{#if !zone}
		<polygon class="rim left" points={pointString([corners[3], corners[2], { ...corners[2], y: corners[2].y + 7 }, { ...corners[3], y: corners[3].y + 7 }])} />
		<polygon class="rim right" points={pointString([corners[2], corners[1], { ...corners[1], y: corners[1].y + 7 }, { ...corners[2], y: corners[2].y + 7 }])} />
	{/if}
	<polygon class="surface" class:zone points={pointString(corners)} />
</g>

<style>
	.surface, .rim { stroke: color-mix(in oklab, var(--tone) 62%, var(--color-line)); stroke-width: 1.1; stroke-linejoin: round; }
	.surface { fill: color-mix(in oklab, var(--tone) 9%, var(--color-surface-raised)); }
	.surface.zone { fill: color-mix(in oklab, var(--tone) 4%, transparent); stroke-dasharray: 5 5; }
	.left { fill: color-mix(in oklab, var(--tone) 20%, var(--color-surface-base)); }
	.right { fill: color-mix(in oklab, var(--tone) 35%, var(--color-surface-base)); }
	.active .surface { fill: var(--color-surface-selected); stroke: var(--color-ink-0); stroke-width: 1.7; }
</style>
