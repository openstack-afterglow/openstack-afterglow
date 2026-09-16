<script module lang="ts">
	export interface ZoneRenderItem {
		netId: string;
		name: string;
		rect: { x: number; y: number; w: number; h: number };
		/** CSS 변수 문자열 */
		color: string;
		active: boolean;
		dim: boolean;
		match: boolean;
		/** 네트워크 status ≠ ACTIVE */
		down: boolean;
	}
</script>

<script lang="ts">
	// 존 사각형 레이어. 이벤트 핸들러를 두지 않고, 뷰포트의 pointerup 히트테스트가 data-zone-net 으로 선택을 처리한다.
	import { r1 } from './canvasHelpers';

	interface Props {
		zones: readonly ZoneRenderItem[];
		width: number;
		height: number;
	}

	let { zones, width, height }: Props = $props();
</script>

<svg class="layer-zones" aria-hidden="true" {width} {height}>
	<g>
		{#each zones as z (z.netId)}
			<rect
				class="zone-rect"
				class:is-active={z.active}
				class:is-dim={z.dim}
				class:is-match={z.match}
				class:is-down={z.down}
				data-zone-net={z.netId}
				rx="8"
				x={r1(z.rect.x)}
				y={r1(z.rect.y)}
				width={r1(z.rect.w)}
				height={r1(z.rect.h)}
				style:--net={z.color}
			>
				<title>네트워크 {z.name}</title>
			</rect>
		{/each}
	</g>
</svg>

<style>
	.layer-zones { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none; }
	.zone-rect {
		fill: color-mix(in oklab, var(--net) var(--topology-zone-fill-alpha), transparent);
		stroke: color-mix(in oklab, var(--net) 55%, transparent);
		stroke-width: 1;
		pointer-events: fill;
		vector-effect: non-scaling-stroke;
		transition:
			fill var(--motion-duration-base) var(--motion-ease-standard),
			opacity var(--motion-duration-base) var(--motion-ease-standard);
	}
	.zone-rect.is-active {
		fill: color-mix(in oklab, var(--net) var(--topology-zone-fill-alpha-active), transparent);
		stroke: var(--net);
	}
	.zone-rect.is-match { stroke: var(--net); stroke-width: 2; }
	.zone-rect.is-dim { opacity: 0.35; }
	.zone-rect.is-down { stroke-dasharray: 6 4; }
	@supports not (color: color-mix(in oklab, red, blue)) {
		.zone-rect { fill: var(--net); fill-opacity: 0.08; stroke: var(--net); stroke-opacity: 0.55; }
		.zone-rect.is-active { fill-opacity: 0.14; }
	}
</style>
