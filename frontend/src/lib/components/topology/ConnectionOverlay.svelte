<script lang="ts">
	import { enterStep } from './firstArrival.svelte.ts';
	import type { ConnectionSpec, LBCurve } from './topologyDerivedController.svelte.ts';

	interface AnchorPos { x: number; y: number; }

	interface Props {
		width: number;
		height: number;
		connections: ConnectionSpec[];
		laneXMap: Map<string, number>;  // netId → center X in overlay coords
		anchors: Map<string, AnchorPos>; // key → {x, y} in overlay coords
		lbCurves: LBCurve[];
		selectedKey: string | null;      // selected resource id
		hoveredKey: string | null;       // hovered resource id
		/** 스코프 첫 도착의 진입 창. 참이면 연결선이 카드 순서대로 그려지고 LB 곡선·흐름은 그 뒤에 나타난다. */
		entering?: boolean;
	}

	let { width, height, connections, laneXMap, anchors, lbCurves, selectedKey, hoveredKey, entering = false }: Props = $props();

	interface Line {
		x1: number; y1: number; x2: number; y2: number;
		color: string; opacity: number; width: number; key: string;
		order: number; flowing: boolean;
	}

	const lines = $derived.by((): Line[] => {
		const result: Line[] = [];
		// selected takes priority over hover for highlighting
		const activeKey = selectedKey || hoveredKey;
		const dimOpacity = selectedKey ? 0.12 : 0.20;

		for (const conn of connections) {
			const anchor = anchors.get(conn.key);
			const laneX = laneXMap.get(conn.netId);
			if (!anchor || laneX === undefined) continue;

			let opacity = conn.opacity;
			if (activeKey) {
				const isActive =
					conn.key.startsWith(activeKey + '|') ||
					conn.key === activeKey ||
					conn.key.startsWith('lb|' + activeKey + '|');
				opacity = isActive ? Math.min(1, conn.opacity * 1.4) : dimOpacity;
			}

			result.push({
				x1: anchor.x, y1: anchor.y,
				x2: laneX, y2: anchor.y,
				color: conn.color,
				opacity,
				width: conn.width,
				key: conn.key,
				order: conn.order,
				flowing: conn.flowing,
			});
		}
		return result;
	});

	// 실측 트래픽이 0 이 아닌 연결만 흐른다. 호버·선택은 흐름을 만들지 않는다.
	const flowLines = $derived(lines.filter((line) => line.flowing));
</script>

<!--
	Two-layer SVG:
	- 하위 레이어(z-auto): 일반 connection lines. 사이드바(z-20) 카드 뒤에 깔려야 카드를 가리지 않음.
	- 상위 레이어(z-25): LB 곡선 + 끝점 dot. 카드 위로 올라와 시작/끝점이 가려지지 않음.
-->
<svg
	{width}
	{height}
	style="position:absolute;inset:0;pointer-events:none;overflow:visible"
	xmlns="http://www.w3.org/2000/svg"
>
	<!-- Normal connection lines: card interface row → network lane. 첫 도착에만 카드 순서대로 그려진다. -->
	{#each lines as line (line.key)}
		<line
			x1={line.x1} y1={line.y1}
			x2={line.x2} y2={line.y2}
			stroke={line.color}
			stroke-width={line.width}
			opacity={line.opacity}
			stroke-linecap="round"
			pathLength={entering ? 1 : undefined}
			class:motion-draw={entering}
			style:--motion-index={entering ? enterStep(line.order) : undefined}
		/>
	{/each}

	<!-- 측정된 트래픽이 있는 연결 위로 흐르는 점선. reduced-motion 이면 멈춘 점선으로 남는다. -->
	<g class="flow" class:after-lines={entering}>
		{#each flowLines as line (line.key)}
			<line
				class="motion-flow"
				x1={line.x1} y1={line.y1}
				x2={line.x2} y2={line.y2}
				stroke-width={line.width}
				opacity={line.opacity}
				stroke-linecap="butt"
			/>
		{/each}
	</g>
</svg>

<svg
	{width}
	{height}
	style="position:absolute;inset:0;pointer-events:none;overflow:visible;z-index:25"
	xmlns="http://www.w3.org/2000/svg"
>
	<!-- LB → member instance curves: dashed amber bezier. 점선이라 그리지 않고 페이드한다. -->
	{#each lbCurves as curve (curve.key)}
		<path
			class:motion-fade={entering}
			class:after-lines={entering}
			d="M {curve.x1} {curve.y1} C {curve.x1 + 60} {curve.y1} {curve.x2 + 60} {curve.y2} {curve.x2} {curve.y2}"
			fill="none"
			stroke="#f59e0b"
			stroke-width="1.5"
			stroke-dasharray="4 3"
			opacity="0.75"
			stroke-linecap="round"
		/>
	{/each}

	<!-- LB curve endpoint markers: amber dots so start/end stay visible above cards -->
	{#each lbCurves as curve (curve.key + '-mk')}
		<g class:motion-fade={entering} class:after-lines={entering}>
			<circle cx={curve.x1} cy={curve.y1} r="3" fill="#f59e0b" />
			<circle cx={curve.x2} cy={curve.y2} r="3" fill="#f59e0b" />
		</g>
	{/each}
</svg>

<style>
	/* 흐름 점선은 선 색 위에서 보이도록 sheen 으로 칠한다(표현 속성은 var() 를 받지 못한다) */
	.flow line { stroke: var(--motion-sheen); }
	/* 진입 중에는 연결선 draw-in(cascade 상한 + data)이 끝난 뒤에 나타난다 */
	.after-lines {
		animation-delay: calc(var(--motion-duration-stagger) * 8 + var(--motion-duration-data));
	}
	.flow.after-lines {
		animation: motion-fade var(--motion-duration-panel) var(--motion-ease-out)
			calc(var(--motion-duration-stagger) * 8 + var(--motion-duration-data)) backwards;
	}
</style>
