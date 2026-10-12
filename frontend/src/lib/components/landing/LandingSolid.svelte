<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { SceneMotionState } from './sceneMotion';

	interface Props {
		x?: number;
		y?: number;
		width: number;
		depth: number;
		height: number;
		tone?: 'neutral' | 'accent';
		state?: SceneMotionState;
		dx?: number;
		dy?: number;
		angle?: number;
		step?: number;
		children?: Snippet;
	}

	let { x = 0, y = 0, width, depth, height, tone = 'neutral', state = 'static', dx = 0, dy = 0, angle = 0, step = 0, children }: Props = $props();
</script>

<g transform={`translate(${x} ${y})`}>
	<g class="solid" class:accent={tone === 'accent'} class:motion-assemble={state !== 'static'} data-solid data-motion={state} style={`--motion-assemble-x: ${dx}px; --motion-assemble-y: ${dy}px; --motion-assemble-angle: ${angle}deg; --motion-index: ${step}`}>
		<path class="solid-top" d={`M0 0 ${depth} ${-depth * 0.55} ${width + depth} ${width * 0.24 - depth * 0.55} ${width} ${width * 0.24}Z`} />
		<path class="solid-side" d={`M${width} ${width * 0.24} ${width + depth} ${width * 0.24 - depth * 0.55}v${height}l${-depth} ${depth * 0.55}Z`} />
		<path class="solid-front" d={`M0 0 ${width} ${width * 0.24}v${height}L0 ${height}Z`} />
		{@render children?.()}
	</g>
</g>

<style>
	.solid { transform-box: fill-box; transform-origin: center; }
	.solid[data-motion='paused'] { animation-play-state: paused; }
	.solid path { stroke: var(--color-line-2); stroke-width: 1.5; stroke-linejoin: round; }
	.solid-top { fill: var(--color-surface-sunken); }
	.solid-side { fill: var(--color-surface-base); }
	.solid-front { fill: var(--color-surface-raised); }
	.accent path { stroke: var(--color-accent); }
	.accent .solid-top { fill: var(--color-accent); }
	.accent .solid-front { fill: color-mix(in oklab, var(--color-accent) 26%, var(--color-surface-raised)); }
	.accent .solid-side { fill: color-mix(in oklab, var(--color-accent) 12%, var(--color-surface-base)); }
	@media (prefers-reduced-motion: reduce) { .solid { animation: none; transform: none; } }
</style>
