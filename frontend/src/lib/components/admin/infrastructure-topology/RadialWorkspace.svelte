<script lang="ts">
	import { untrack } from 'svelte';
	import type { TopologySelection } from '$lib/types/infrastructureTopology';
	import { Viewport } from '$lib/components/topology/canvas/viewport.svelte';
	import { fitTransform } from '$lib/components/topology/canvas/topologyLayout';
	import Button from '$lib/components/ui/Button.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { curve, edgeRate, edgeWindow, magnitude, visibleGraph, SCALE, LAYERS, type EvidenceLayer, type FlowMetric, type RadialGraph } from './radialGraph';
	import { edgeLabel, rateLabel, stateLabel, windowLabel } from './presentation';
	let { graph, selection, onselect }: { graph: RadialGraph; selection: TopologySelection | null; onselect: (next: TopologySelection) => void } = $props();
	let metric = $state<FlowMetric>('pps');
	let layers = $state<Record<EvidenceLayer, boolean>>({ flow: true, physical: true, route: false, probe: false, trace: false });
	let width = $state(0), height = $state(0);
	const viewport = new Viewport();
	const componentId = $props.id();
	const rendered = $derived(visibleGraph(graph, layers));
	const visibleNodes = $derived(rendered.nodes);
	const visibleEdges = $derived(rendered.edges);
	const positions = $derived(new Map(graph.nodes.map(node => [node.id, viewport.toScreen(node.x, node.y)])));
	const windows = $derived(visibleEdges.flatMap(edge => { const value = edgeWindow(edge); return value === null ? [] : [value]; }));
	const selectedEdge = $derived(selection?.kind === 'edge' ? graph.edges.find(edge => edge.id === selection?.id) : undefined);
	// Labels never overlap nodes or other labels at overview zoom. Full names remain in the native navigator.
	const labeled = $derived.by(() => {
		const boxes = visibleNodes.map(node => { const p = positions.get(node.id)!; return { x: p.x - 24, y: p.y - 24, w: 48, h: 48 }; });
		const names = new Set<string>();
		const ordered = [...visibleNodes].sort((a, b) => Number(selection?.kind === 'node' && selection.id === b.id) - Number(selection?.kind === 'node' && selection.id === a.id));
		for (const node of ordered) {
			const p = positions.get(node.id)!, w = node.kind === 'port' ? 96 : 130;
			const box = { x: p.x - w / 2, y: p.y + 27, w, h: 32 };
			if (width > 0 && (box.x < 4 || box.x + box.w > width - 4 || box.y < 4 || box.y + box.h > height - 4)) continue;
			if (boxes.some(other => box.x < other.x + other.w && box.x + box.w > other.x && box.y < other.y + other.h && box.y + box.h > other.y)) continue;
			names.add(node.id); boxes.push(box);
		}
		return names;
	});
	function fit() {
		viewport.set(fitTransform(rendered.bounds, width || 640, height || 520, 32, 0.1, 1.25));
	}
	function zoom(sx: number, sy: number, next: number) {
		const fixed = viewport.toCanvas(sx, sy), k = Math.max(0.1, Math.min(2.2, next));
		viewport.set({ k, panX: sx - fixed.x * k, panY: sy - fixed.y * k });
	}
	// Resize fits the workspace once; polling/rate changes never move the camera.
	$effect(() => { if (width > 0 && height > 0) untrack(fit); });
	function gestures(element: HTMLElement) {
		const pointers = new Map<number, { x: number; y: number }>();
		let press: { id: number; edgeId: string | null; x: number; y: number; moved: boolean } | null = null;
		function down(event: PointerEvent) {
			if (event.button !== 0 || (event.target as Element).closest('button,[role="button"]')) return;
			if (pointers.size === 0) press = { id: event.pointerId, edgeId: (event.target as Element).closest('[data-edge-hit]')?.getAttribute('data-edge-hit') ?? null, x: event.clientX, y: event.clientY, moved: false };
			else if (press) press.moved = true;
			pointers.set(event.pointerId, { x: event.clientX, y: event.clientY }); element.setPointerCapture?.(event.pointerId);
		}
		function move(event: PointerEvent) {
			if (!pointers.has(event.pointerId)) return;
			if (press && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 8) press.moved = true;
			const before = [...pointers.values()]; const old = pointers.get(event.pointerId)!;
			pointers.set(event.pointerId, { x: event.clientX, y: event.clientY }); const after = [...pointers.values()];
			if (before.length === 1) viewport.panBy(event.clientX - old.x, event.clientY - old.y);
			else if (before.length === 2) {
				const distance = Math.hypot(before[0].x - before[1].x, before[0].y - before[1].y);
				const nextDistance = Math.hypot(after[0].x - after[1].x, after[0].y - after[1].y);
				const rect = element.getBoundingClientRect();
				const x = (before[0].x + before[1].x) / 2 - rect.left, y = (before[0].y + before[1].y) / 2 - rect.top;
				if (distance > 0) zoom(x, y, viewport.k * nextDistance / distance);
				viewport.panBy((after[0].x + after[1].x - before[0].x - before[1].x) / 2, (after[0].y + after[1].y - before[0].y - before[1].y) / 2);
			}
		}
		function up(event: PointerEvent) {
			if (event.type === 'pointerup' && press?.id === event.pointerId && !press.moved && press.edgeId) onselect({ kind: 'edge', id: press.edgeId });
			pointers.delete(event.pointerId); if (press?.id === event.pointerId) press = null;
		}
		function wheel(event: WheelEvent) {
			event.preventDefault();
			if (event.shiftKey) viewport.panBy(-event.deltaX, -event.deltaY);
			else { const rect = element.getBoundingClientRect(); zoom(event.clientX - rect.left, event.clientY - rect.top, viewport.k * Math.exp(-event.deltaY * 0.002)); }
		}
		function key(event: KeyboardEvent) {
			if (event.target !== element) return;
			const directions: Record<string, [number, number]> = { ArrowLeft: [48, 0], ArrowRight: [-48, 0], ArrowUp: [0, 48], ArrowDown: [0, -48] };
			if (directions[event.key]) { event.preventDefault(); viewport.panBy(...directions[event.key]); }
			else if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(width / 2, height / 2, viewport.k * 1.2); }
			else if (event.key === '-') { event.preventDefault(); zoom(width / 2, height / 2, viewport.k / 1.2); }
			else if (event.key === '0' || event.key === 'Home') { event.preventDefault(); fit(); }
		}
		element.addEventListener('pointerdown', down); element.addEventListener('pointermove', move);
		element.addEventListener('pointerup', up); element.addEventListener('pointercancel', up);
		element.addEventListener('wheel', wheel, { passive: false }); element.addEventListener('keydown', key);
		return { destroy() { element.removeEventListener('pointerdown', down); element.removeEventListener('pointermove', move); element.removeEventListener('pointerup', up); element.removeEventListener('pointercancel', up); element.removeEventListener('wheel', wheel); element.removeEventListener('keydown', key); } };
	}
</script>

<section class="radial-workspace" aria-label={t('workspace.title')}>
	<header class="toolbar">
		<div><h2 class="font-semibold">{t('workspace.title')}</h2><p class="text-xs text-ink-2">{t('workspace.coreHelp')}</p></div>
		<div class="controls"><ToggleGroup value={metric} ariaLabel={t('workspace.metric')} options={[{ value: 'pps', label: t('workspace.pps') }, { value: 'Bps', label: t('workspace.Bps') }]} onchange={(value) => { metric = value as FlowMetric; }} />
			<Button variant="secondary" ariaLabel={t('workspace.zoomOut')} onclick={() => zoom(width / 2, height / 2, viewport.k / 1.2)}>−</Button>
			<span class="text-xs tabular-nums">{Math.round(viewport.k * 100).toLocaleString(intlLocale())}%</span>
			<Button variant="secondary" ariaLabel={t('workspace.zoomIn')} onclick={() => zoom(width / 2, height / 2, viewport.k * 1.2)}>+</Button>
			<Button variant="secondary" onclick={fit}>{t('workspace.fit')}</Button></div>
	</header>
	<div class="layers" role="group" aria-label={t('workspace.layers')}>
		{#each LAYERS as layer}<Button size="sm" variant={layers[layer] ? 'primary' : 'secondary'} ariaPressed={layers[layer]} onclick={() => { layers[layer] = !layers[layer]; }}>{t(`workspace.layer.${layer}`)}</Button>{/each}
	</div>
	<p class="text-xs text-ink-2">{t('workspace.scale', { maximum: rateLabel(SCALE[metric].maximum, metric) })} · {windows.length ? windowLabel(Math.min(...windows)) + (Math.max(...windows) !== Math.min(...windows) ? ` – ${windowLabel(Math.max(...windows))}` : '') : t('workspace.windowUnknown')}</p>
	<div class="scale" aria-label={t('workspace.scaleLegend')}>
		{#each SCALE[metric].ticks as value}<span><svg width="30" height="12" aria-hidden="true"><path d="M 1 6 H 29" stroke="var(--color-accent)" stroke-width={magnitude(value, 'fresh', metric).width} opacity={magnitude(value, 'fresh', metric).opacity} /></svg>{rateLabel(value, metric)}</span>{/each}
	</div>
	<p class="text-xs text-ink-2">{t('workspace.states')}</p>
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div class="canvas" role="region" tabindex="0" aria-label={t('workspace.diagram')} use:gestures bind:clientWidth={width} bind:clientHeight={height}>
		<svg width="100%" height="100%" aria-hidden="true">
			<defs><marker id={`${componentId}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" /></marker></defs>
			<circle cx={viewport.panX} cy={viewport.panY} r={130 * viewport.k} class="core-ring" />
			<circle cx={viewport.panX} cy={viewport.panY} r={graph.hostRadius * viewport.k} class="host-ring" />
			<text x={viewport.panX} y={viewport.panY - 130 * viewport.k - 12} text-anchor="middle" class="core-label">{t('workspace.core')}</text>
			<text x={viewport.panX - graph.hostRadius * viewport.k * 0.75} y={viewport.panY - graph.hostRadius * viewport.k * 0.8} text-anchor="middle" class="core-label">{t('role.compute')}</text>
			<text x={viewport.panX + graph.hostRadius * viewport.k * 0.75} y={viewport.panY - graph.hostRadius * viewport.k * 0.8} text-anchor="middle" class="core-label">{t('role.storage')}</text>
			{#each visibleEdges as edge (edge.id)}
				{@const shape = curve(positions.get(edge.source)!, positions.get(edge.target)!, edge.lane)}
				{@const scaled = magnitude(edgeRate(edge, metric), edge.state, metric)}
				<path d={shape.d} data-edge-id={edge.id} data-edge-kind={edge.layer} data-edge-state={edge.state} data-rate={scaled.rate ?? 'unknown'} class="connection" class:physical={edge.layer === 'physical'} class:probe={edge.layer === 'probe'} class:diagnostic={edge.layer === 'trace' || edge.layer === 'route'} class:unknown={scaled.unknown && (edge.layer === 'flow' || edge.layer === 'physical')} class:error={edge.state === 'error' || edge.state === 'down'} class:selected={selection?.kind === 'edge' && selection.id === edge.id} class:membership={edge.membership} class:zero={scaled.zero}
					stroke-width={edge.flow || edge.port ? scaled.width : 1.5} opacity={edge.flow || edge.port ? scaled.opacity : 0.7} marker-end={edge.membership || edge.link && !edge.port ? undefined : `url(#${componentId}-arrow)`} />
			{/each}
		</svg>
		<!-- SVG hit targets are pointer-only; the native evidence list below is the keyboard equivalent. -->
		<svg class="hits" width="100%" height="100%" aria-hidden="true">
			{#each visibleEdges.filter(edge => !edge.membership) as edge (edge.id)}<path data-edge-hit={edge.id} d={curve(positions.get(edge.source)!, positions.get(edge.target)!, edge.lane).d} stroke="transparent" stroke-width="44" fill="none"><title>{edgeLabel(edge, graph, metric)}</title></path>{/each}
		</svg>
		{#each visibleNodes as node (node.id)}
			{@const point = positions.get(node.id)!}
			<div class="node" data-node-id={node.id} data-node-kind={node.kind} style:transform={`translate(${point.x}px, ${point.y}px)`} style:--node-scale={Math.min(1, viewport.k)}>
				<Button variant={selection?.kind === 'node' && selection.id === node.id ? 'primary' : 'secondary'} ariaPressed={selection?.kind === 'node' && selection.id === node.id} ariaLabel={node.label} onclick={() => onselect({ kind: 'node', id: node.id })} class="node-button">
					<span aria-hidden="true">{node.kind === 'host' ? '▣' : node.kind === 'switch' ? '▤' : node.kind === 'port' ? '○' : node.kind === 'gap' ? '*' : '◇'}</span>
				</Button>
				{#if labeled.has(node.id)}<span class="node-name" title={node.label}>{node.label}</span><span class="node-state">{t(`workspace.kind.${node.kind}`)} · {node.kind === 'peer' ? t(node.state === 'up' ? 'probe.up' : node.state === 'down' ? 'probe.down' : 'probe.unknown') : stateLabel(node.state)}</span>{/if}
			</div>
		{/each}
	</div>
	<p class="text-xs text-ink-2">{t('workspace.navigation')}</p>
	{#if selectedEdge}<p role="status" class="selection-label">{edgeLabel(selectedEdge, graph, metric)}</p>{/if}
	<details class="evidence-list" open={width > 0 && width < 768}><summary>{t('workspace.evidenceList', { nodes: visibleNodes.length.toLocaleString(intlLocale()), edges: visibleEdges.filter(edge => !edge.membership).length.toLocaleString(intlLocale()) })}</summary>
		<div class="list-items">{#each visibleNodes as node (node.id)}<Button variant="ghost" ariaPressed={selection?.kind === 'node' && selection.id === node.id} onclick={() => onselect({ kind: 'node', id: node.id })}>{node.label} · {t(`workspace.kind.${node.kind}`)}</Button>{/each}</div>
		<div class="list-items">{#each visibleEdges.filter(edge => !edge.membership) as edge (edge.id)}<Button variant="ghost" ariaPressed={selection?.kind === 'edge' && selection.id === edge.id} onclick={() => onselect({ kind: 'edge', id: edge.id })}>{edgeLabel(edge, graph, metric)}</Button>{:else}<p class="text-sm text-ink-2">{t('workspace.noEdges')}</p>{/each}</div>
	</details>
</section>
<style>
	.radial-workspace { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.75rem; min-width: 0; }
	.toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 0.75rem; }
	.controls, .layers { display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; }
	.controls :global(button), .layers :global(button) { min-height: 44px; min-width: 44px; }
	.canvas { position: relative; min-width: 0; width: 100%; height: 34rem; max-height: 65dvh; min-height: 24rem; overflow: hidden; touch-action: none; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-sunken); }
	.canvas:focus-visible, summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.canvas > svg { position: absolute; inset: 0; pointer-events: none; }
	.hits path { pointer-events: stroke; cursor: pointer; }
	.core-ring { stroke: var(--color-line-2); stroke-dasharray: 4 6; fill: var(--color-surface-raised); }
	.host-ring { stroke: var(--color-line); fill: none; }
	.core-label { fill: var(--color-ink-2); font-size: 12px; }
	.connection { fill: none; stroke: var(--color-accent); }
	.physical { stroke: var(--color-chart-2); }
	.diagnostic { stroke: var(--color-topology-router); stroke-dasharray: 3 5; }
	.probe { stroke: var(--color-topology-internal); stroke-dasharray: 8 5; }
	.unknown, .membership { stroke: var(--color-line-2); stroke-dasharray: 4 4; }
	.error { stroke: var(--color-state-danger); stroke-dasharray: 4 4; }
	.zero { stroke-dasharray: 1 4; }
	.selected { stroke: var(--color-action-warm); }
	.node { position: absolute; left: 0; top: 0; width: 0; height: 0; display: flex; align-items: center; flex-direction: column; }
	.node :global(.node-button) { min-width: 44px; min-height: 44px; width: 44px; height: 44px; flex-shrink: 0; transform: translateY(-50%) scale(var(--node-scale)); padding: 0; border-radius: var(--radius-md); }
	.node-name, .node-state { position: absolute; top: 25px; width: 130px; text-align: center; font: 11px var(--font-mono); color: var(--color-ink-1); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; pointer-events: none; }
	.node-state { top: 42px; font: 10px var(--font-sans); color: var(--color-ink-2); }
	[data-node-kind='port'] .node-name { width: 96px; }
	.scale { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; font-size: 11px; color: var(--color-ink-2); }
	.scale span { display: inline-flex; align-items: center; gap: 0.3rem; }
	.selection-label { font-size: 0.75rem; overflow-wrap: anywhere; border-inline-start: 2px solid var(--color-action-warm); padding-inline-start: 0.75rem; }
	summary { cursor: pointer; min-height: 44px; padding-block: 0.75rem; font-size: 0.875rem; }
	.list-items { display: grid; grid-template-columns: minmax(0, 1fr); min-width: 0; max-height: 18rem; overflow: auto; gap: 0.25rem; }
	.list-items :global(button) { min-width: 0; max-width: 100%; min-height: 44px; white-space: normal; text-align: start; justify-content: flex-start; overflow-wrap: anywhere; }
	@media (min-width: 768px) { .canvas { height: 40rem; } }
	@media (prefers-reduced-motion: reduce) { .node :global(button) { transition: none; } }
</style>
