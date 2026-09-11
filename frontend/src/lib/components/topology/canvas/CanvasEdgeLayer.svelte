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

<svg class="layer-edges" aria-hidden="true" {width} {height}>
	<g>
		{#each fipEdges as e (e.key)}
			<path class="edge edge-fip" class:is-forced={e.forced} data-key={e.key} d={e.d} style:--net={e.color} style:opacity={e.opacity} style:stroke-width={e.width} style:stroke-dasharray={e.dash ?? undefined} />
		{/each}
	</g>
	<g>
		{#each mainEdges as e (e.key)}
			<path class="edge edge-{e.kind}" data-key={e.key} d={e.d} style:--net={e.color} style:opacity={e.opacity} style:stroke-width={e.width} style:stroke-dasharray={e.dash ?? undefined} />
		{/each}
	</g>
	<g>
		{#each ports as e (e.key)}
			<circle class="port-dot" r="2.5" cx={r1(e.port?.x ?? 0)} cy={r1(e.port?.y ?? 0)} style:--net={e.color} />
		{/each}
	</g>
	<g>
		{#each memberEdges as e (e.key)}
			<path class="edge edge-lbmember" data-key={e.key} d={e.d} style:--net={e.color} style:opacity={e.opacity} style:stroke-width={e.width} style:stroke-dasharray={e.dash ?? undefined} />
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
