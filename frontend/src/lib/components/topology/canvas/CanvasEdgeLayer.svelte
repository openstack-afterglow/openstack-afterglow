<script module lang="ts">
	import type { CanvasEdgeKind } from './types';

	export interface EdgeRenderItem {
		key: string;
		kind: CanvasEdgeKind;
		netId: string;
		d: string;
		/** CSS 변수 문자열 */
		color: string;
		opacity: number;
		width: number;
		dash: string | null;
		/** FIP 링크가 활성 노드에 인접해 LOD 숨김을 무시하는 경우 */
		forced: boolean;
		/** trunk 의 호버·클릭용 투명 히트 경로와 툴팁 */
		hitTitle: string | null;
		/** 스위치 쪽 포트 점(cable/lbvip) */
		port: { x: number; y: number } | null;
		/**
		 * 첫 도착 진입 cascade 단계. null 이면 진입 모션 없음.
		 * 실선은 pathLength=1 로 그려지고(이때 width 는 월드 단위), 점선은 이미 대시가 있으므로 페이드한다.
		 */
		enter: number | null;
	}
</script>

<script lang="ts">
	// 케이블·트렁크·FIP·LB 경로 레이어. 핸들러 없이 data-edge-key / data-edge-net 으로 뷰포트 위임 히트테스트에 참여한다.
	import { r1 } from './canvasHelpers';

	interface Props {
		edges: readonly EdgeRenderItem[];
		width: number;
		height: number;
	}

	let { edges, width, height }: Props = $props();

	const fipEdges = $derived(edges.filter((e) => e.kind === 'fip'));
	const mainEdges = $derived(edges.filter((e) => e.kind !== 'fip' && e.kind !== 'lbmember'));
	const memberEdges = $derived(edges.filter((e) => e.kind === 'lbmember'));
	const hitEdges = $derived(edges.filter((e) => e.hitTitle != null));
	const ports = $derived(edges.filter((e) => e.port != null));
</script>

{#snippet edgePath(e: EdgeRenderItem, kindClass: string)}
	{@const drawing = e.enter !== null && !e.dash}
	<path
		class="edge {kindClass}"
		class:is-forced={e.forced}
		class:is-drawing={drawing}
		class:motion-draw={drawing}
		class:motion-fade={e.enter !== null && Boolean(e.dash)}
		data-key={e.key}
		d={e.d}
		pathLength={drawing ? 1 : undefined}
		style:--net={e.color}
		style:--motion-index={e.enter ?? undefined}
		style:opacity={e.opacity}
		style:stroke-width={e.width}
		style:stroke-dasharray={e.dash ?? undefined}
	/>
{/snippet}

<svg class="layer-edges" aria-hidden="true" {width} {height}>
	<g>
		{#each fipEdges as e (e.key)}
			{@render edgePath(e, 'edge-fip')}
		{/each}
	</g>
	<g>
		{#each mainEdges as e (e.key)}
			{@render edgePath(e, `edge-${e.kind}`)}
		{/each}
	</g>
	<g>
		{#each ports as e (e.key)}
			<circle
				class="port-dot"
				class:motion-fade={e.enter !== null}
				r="2.5"
				cx={r1(e.port?.x ?? 0)}
				cy={r1(e.port?.y ?? 0)}
				style:--net={e.color}
				style:--motion-index={e.enter ?? undefined}
			/>
		{/each}
	</g>
	<g>
		{#each memberEdges as e (e.key)}
			{@render edgePath(e, 'edge-lbmember')}
		{/each}
	</g>
	<g>
		{#each hitEdges as e (e.key)}
			<path class="edge-hit" data-edge-key={e.key} data-edge-net={e.netId} d={e.d}>
				<title>{e.hitTitle}</title>
			</path>
		{/each}
	</g>
</svg>

<style>
	.layer-edges { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none; }
	.edge {
		fill: none;
		stroke: var(--net);
		stroke-linecap: round;
		vector-effect: non-scaling-stroke;
		transition: opacity var(--motion-duration-data) var(--motion-ease-standard);
	}
	/*
	 * draw-in 은 pathLength(월드 길이) 기준 대시라 non-scaling-stroke(화면 공간 대시)와 섞이면 배율이 1 이 아닐 때
	 * 끝까지 그려지지 않는다. 진입 창 동안만 월드 단위로 그리고, 굵기는 TopologyCanvas 가 배율로 나눠 화면 굵기를 맞춘다.
	 */
	.edge.is-drawing { vector-effect: none; }
	.edge-hit {
		fill: none;
		stroke: transparent;
		stroke-width: 14;
		pointer-events: stroke;
		vector-effect: non-scaling-stroke;
		cursor: pointer;
	}
	.port-dot { fill: var(--net); stroke: var(--color-surface-base); stroke-width: 1; }
	:global(.topology-world[data-lod='compact']) .edge-fip:not(.is-forced) { opacity: 0 !important; }
	:global(.topology-world[data-lod='noip']) .port-dot,
	:global(.topology-world[data-lod='compact']) .port-dot { display: none; }
</style>
