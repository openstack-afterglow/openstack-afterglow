<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import { t } from '$lib/i18n/ns/iso-view';
	import { toneVars } from './appearance';
	import { placeCaptions } from './captionLayout';
	import IsoCaption from './IsoCaption.svelte';
	import { CELL_X, CELL_Y, layoutScene, type Point } from './layout';
	import IsoNodeBlock from './IsoNodeBlock.svelte';
	import IsoPlatform from './IsoPlatform.svelte';
	import { packetCohort, PACKET_COHORT_MS, PACKET_LIMIT, visiblePacketEdges } from './packets';
	import type { IsoNodeKind, IsoScene } from './types';

	const nodeKinds = {
		instance: 'instance', router: 'router', loadbalancer: 'loadbalancer', database: 'database',
		gateway: 'gateway', 'vpn-server': 'vpnServer', peer: 'peer', 'peer-group': 'peerGroup',
		internet: 'internet', cidr: 'cidr', 'floating-ip': 'floatingIp', port: 'port',
		'security-group': 'securityGroup', volume: 'volume', 'file-share': 'fileShare', 'k8s-service': 'k8sService',
	} as const satisfies Record<IsoNodeKind, string>;
	const networkKinds = {
		'external-network': 'externalNetwork', 'shared-network': 'sharedNetwork', 'internal-network': 'internalNetwork',
	} as const;

	interface Props {
		scene: IsoScene;
		selectedId?: string | null;
		onselect?: (id: string) => void;
		onclear?: () => void;
		onintent?: (id: string) => void;
		oncancelintent?: () => void;
		label: string;
		caption?: string;
		height?: string;
		fitKey?: string;
		emptyText?: string;
	}
	interface Camera extends Point { k: number }
	const MAX_ZOOM = 3;
	const uid = $props.id();
	let { scene, selectedId = null, onselect, onclear, onintent, oncancelintent, label, caption, height, fitKey, emptyText }: Props = $props();
	let viewport = $state<HTMLDivElement>();
	let width = $state(0);
	let viewHeight = $state(0);
	let pose = $state.raw<Camera>();
	let focusedId = $state<string>();
	let hoveredId = $state<string>();
	let reduced = $state(true);
	let visible = $state(false);
	let inView = $state(false);
	let paused = $state(false);
	let dragging = $state(false);
	let packetTurn = $state(0);
	let dragged = false;
	let origin: Point | undefined;
	const pointers = new Map<number, Point>();

	const layout = $derived(layoutScene(scene));
	const empty = $derived(layout.items.length === 0);
	const bounds = $derived(layout.bounds);
	const rawFit = $derived(Math.min(1.2, (width - 20) / bounds.w, (viewHeight - 20) / bounds.h));
	const fitScale = $derived(Math.max(0.02, rawFit));
	function centeredCamera(k: number): Camera {
		return { k, x: -(bounds.x + bounds.w / 2) * k, y: -(bounds.y + bounds.h / 2) * k };
	}
	const fitPose = $derived(centeredCamera(fitScale));
	const readableScale = $derived(width < 768 && layout.items.length <= 48 ? Math.max(fitScale, 0.62) : fitScale);
	const camera = $derived(pose ?? centeredCamera(readableScale));
	const captionZoom = $derived(Math.min(0.8, Math.round(camera.k * 20) / 20));
	const captions = $derived(placeCaptions(layout.nodes, layout.platforms, layout.edges, captionZoom, (status) => t(`status.${status}`)));
	const translateX = $derived(width / 2 + camera.x);
	const translateY = $derived(viewHeight / 2 + camera.y);
	const stageTransform = $derived(`translate(${translateX}px, ${translateY}px) scale(${camera.k})`);
	const activeIds = $derived(new Set([selectedId, focusedId, hoveredId].filter(Boolean)));
	const relatedPlatforms = $derived.by(() => {
		const related = new Set(activeIds);
		for (const id of activeIds) {
			const platformId = id ? layout.nodesById.get(id)?.platformId : undefined;
			if (platformId) related.add(platformId);
		}
		return related;
	});
	const relatedIds = $derived.by(() => {
		const related = new Set(activeIds);
		if (!activeIds.size) return related;
		for (const { node } of layout.nodes) {
			if (node.platformId && activeIds.has(node.platformId)) related.add(node.id);
		}
		for (const { edge } of layout.edges) {
			if (activeIds.has(edge.from) || activeIds.has(edge.to)) {
				related.add(edge.from);
				related.add(edge.to);
			}
		}
		return related;
	});
	const canAnimate = $derived(layout.edges.some(({ edge }) => edge.flow !== false));
	const hasInactivePaths = $derived(layout.edges.some(({ edge }) => edge.inactive));
	const moving = $derived(visible && inView && !reduced && !paused && !dragging);
	const visibleRoutes = $derived(moving && width > 0 && viewHeight > 0 ? visiblePacketEdges(layout.edges, {
		x: (-translateX - 6) / camera.k, y: (-translateY - 6) / camera.k,
		w: (width + 12) / camera.k, h: (viewHeight + 12) / camera.k,
	}) : []);
	const rotating = $derived(visibleRoutes.length > PACKET_LIMIT);
	const packetIds = $derived(packetCohort(visibleRoutes, packetTurn));
	const itemLabels = $derived(new Map(layout.items.map((item) => [item.id, item.label])));
	const interactive = $derived(onselect ? layout.items.filter(({ id }) => (layout.nodesById.get(id) ?? layout.platformsById.get(id))?.interactive !== false) : []);

	let fittedKey: string | undefined;
	$effect(() => {
		if (fittedKey !== fitKey) {
			fittedKey = fitKey;
			pose = undefined;
		}
	});

	$effect(() => {
		if (!rotating) return;
		const timer = setInterval(() => { packetTurn++; }, PACKET_COHORT_MS);
		return () => clearInterval(timer);
	});

	$effect(() => {
		const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
		const update = () => {
			reduced = query?.matches ?? false;
			visible = !document.hidden;
		};
		update();
		query?.addEventListener('change', update);
		document.addEventListener('visibilitychange', update);
		return () => {
			query?.removeEventListener('change', update);
			document.removeEventListener('visibilitychange', update);
		};
	});

	$effect(() => {
		if (!viewport) return;
		const canvas = viewport;
		inView = !('IntersectionObserver' in window);
		const observer = 'IntersectionObserver' in window
			? new IntersectionObserver((entries) => { inView = entries.at(-1)?.isIntersecting ?? false; }) : null;
		observer?.observe(canvas);
		canvas.addEventListener('wheel', wheel, { passive: false });
		return () => {
			observer?.disconnect();
			canvas.removeEventListener('wheel', wheel);
		};
	});

	function zoom(factor: number, x = 0, y = 0, dx = 0, dy = 0) {
		const k = Math.max(Math.min(fitScale, 0.24), Math.min(MAX_ZOOM, camera.k * factor));
		const ratio = k / camera.k;
		pose = { k, x: x + (camera.x - x) * ratio + dx, y: y + (camera.y - y) * ratio + dy };
	}

	function wheel(event: WheelEvent) {
		// Leave normal page scrolling alone before the visitor engages the diagram.
		if (!viewport?.contains(document.activeElement) && !event.ctrlKey && !event.metaKey) return;
		event.preventDefault();
		const rect = viewport!.getBoundingClientRect();
		if (!event.deltaY) {
			pose = { ...camera, x: camera.x - event.deltaX };
			return;
		}
		const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewHeight : 1;
		const bounded = Math.max(-100, Math.min(100, event.deltaY * unit));
		zoom(Math.exp(-bounded * 0.007), event.clientX - rect.left - width / 2, event.clientY - rect.top - viewHeight / 2);
	}

	function pointerDown(event: PointerEvent) {
		if (event.button !== 0 || pointers.size >= 2) return;
		const point = { x: event.clientX, y: event.clientY };
		if (!pointers.size) {
			origin = point;
			dragged = false;
			if (event.pointerType === 'mouse' && event.target === viewport) viewport?.focus({ preventScroll: true });
		}
		pointers.set(event.pointerId, point);
	}

	function pointerMove(event: PointerEvent) {
		const before = pointers.get(event.pointerId);
		if (!before || !viewport) return;
		const after = { x: event.clientX, y: event.clientY };
		const dx = after.x - before.x, dy = after.y - before.y;
		if (!dragged && pointers.size === 1 && origin && Math.hypot(after.x - origin.x, after.y - origin.y) < 4) return;
		pointers.set(event.pointerId, after);
		if (!dragged) {
			dragging = dragged = true;
			oncancelintent?.();
		}
		if (!viewport.hasPointerCapture?.(event.pointerId)) viewport.setPointerCapture?.(event.pointerId);
		if (pointers.size === 2) {
			const other = [...pointers].find(([id]) => id !== event.pointerId)?.[1];
			if (!other) return;
			const oldDistance = Math.hypot(before.x - other.x, before.y - other.y);
			const newDistance = Math.hypot(after.x - other.x, after.y - other.y);
			const rect = viewport.getBoundingClientRect();
			if (oldDistance > 0) zoom(newDistance / oldDistance,
				(before.x + other.x) / 2 - rect.left - width / 2,
				(before.y + other.y) / 2 - rect.top - viewHeight / 2, dx / 2, dy / 2);
		} else {
			pose = { ...camera, x: camera.x + dx, y: camera.y + dy };
		}
	}

	function pointerEnd(event: PointerEvent) {
		pointers.delete(event.pointerId);
		if (pointers.size === 0) dragging = false;
	}

	function pointerCaptureLost(event: PointerEvent) {
		// Implicit touch capture moves from a target button to the viewport when dragging starts.
		// The button's bubbling lostpointercapture is not the end of that pointer.
		if (event.target === viewport) pointerEnd(event);
	}

	function keys(event: KeyboardEvent) {
		if (event.altKey || event.metaKey || event.ctrlKey) return;
		switch (event.key) {
			case 'Escape':
				if (!onclear) return;
				onclear();
				break;
			case '+': case '=': zoom(1.25); break;
			case '-': zoom(0.8); break;
			case '0': pose = fitPose; break;
			case 'ArrowLeft': pose = { ...camera, x: camera.x + 40 }; break;
			case 'ArrowRight': pose = { ...camera, x: camera.x - 40 }; break;
			case 'ArrowUp': pose = { ...camera, y: camera.y + 40 }; break;
			case 'ArrowDown': pose = { ...camera, y: camera.y - 40 }; break;
			default: return;
		}
		event.preventDefault();
	}

	function focusItem(event: FocusEvent, id: string, point: Point, lift: number) {
		if (event.currentTarget instanceof HTMLElement && event.currentTarget.matches(':focus-visible')) {
			focusedId = id;
			const x = translateX + point.x * camera.k;
			const y = translateY + (point.y + lift) * camera.k;
			if (x < 50 || x > width - 50 || y < 45 || y > viewHeight - 45) {
				pose = { k: camera.k, x: -point.x * camera.k, y: -(point.y + lift) * camera.k };
			}
		}
		onintent?.(id);
	}

	function itemName(id: string) {
		const node = layout.nodesById.get(id);
		if (node) return [
			t(`kind.${nodeKinds[node.kind]}`), node.ariaLabel ?? [node.label, node.sublabel].filter(Boolean).join(', '),
			node.status && t(`status.${node.status}`), ...(node.badges ?? []).map(({ text }) => text),
		].filter(Boolean).join(', ');
		const platform = layout.platformsById.get(id);
		if (!platform) return '';
		const kind = platform.kind ? networkKinds[platform.kind] : platform.style === 'zone' ? 'zone' : 'platform';
		return [t(`kind.${kind}`), platform.label, platform.sublabel].filter(Boolean).join(', ');
	}
</script>

<figure aria-label={label} aria-describedby="{uid}-description" class="diagram">
	{#if empty}
		<p class="empty">{emptyText ?? t('diagram.empty')}</p>
	{:else}
		<div class="controls" role="group" aria-label={t('controls.label')}>
			<Button variant="outline" size="icon" ariaLabel={t('controls.zoomOut')} title={t('controls.zoomOut')} disabled={camera.k <= Math.min(fitScale, 0.24)} onclick={() => zoom(0.8)}>
				<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 10h10" /></svg>
			</Button>
			<output aria-hidden="true">{Math.round(camera.k * 100)}%</output>
			<Button variant="outline" size="icon" ariaLabel={t('controls.zoomIn')} title={t('controls.zoomIn')} disabled={camera.k >= MAX_ZOOM} onclick={() => zoom(1.25)}>
				<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 10h10m-5-5v10" /></svg>
			</Button>
			<Button variant="outline" size="icon" ariaLabel={t('controls.fit')} title={t('controls.fit')} onclick={() => { pose = fitPose; }}>
				<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 4H4v3m9-3h3v3m0 6v3h-3m-6 0H4v-3M8 8h4v4H8z" /></svg>
			</Button>
			{#if canAnimate && !reduced}
				{@const motionLabel = paused ? t('controls.play') : t('controls.pause')}
				<Button variant="outline" size="icon" ariaLabel={motionLabel} title={motionLabel} onclick={() => { paused = !paused; }}>
					<svg viewBox="0 0 20 20" aria-hidden="true"><path d={paused ? 'M7 4l8 6-8 6z' : 'M7 5v10m6-10v10'} /></svg>
				</Button>
			{/if}
		</div>
		<!-- The focusable diagram supports keyboard pan/zoom as an alternative to pointer gestures. -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
		<div class="viewport" class:dragging style:--diagram-height={height} role="group" aria-label={label}
			tabindex="0" bind:this={viewport} bind:clientWidth={width} bind:clientHeight={viewHeight}
			onkeydown={keys} onpointerdown={pointerDown} onpointermove={pointerMove} onpointerup={pointerEnd}
			onpointercancel={pointerEnd} onlostpointercapture={pointerCaptureLost} onpointerleave={pointerEnd}>
			<svg class="world" aria-hidden="true" focusable="false">
				<defs>
					<pattern id="{uid}-minor" width=".25" height=".25" patternUnits="userSpaceOnUse"
						patternTransform="translate({translateX} {translateY}) scale({camera.k}) matrix({CELL_X} {CELL_Y} {-CELL_X} {CELL_Y} 0 0)">
						<path class="minor" d="M0 .25V0H.25" />
					</pattern>
					<pattern id="{uid}-major" width="1" height="1" patternUnits="userSpaceOnUse"
						patternTransform="translate({translateX} {translateY}) scale({camera.k}) matrix({CELL_X} {CELL_Y} {-CELL_X} {CELL_Y} 0 0)">
						<path class="major" d="M0 1V0H1" />
					</pattern>
					<marker id="{uid}-arrow" viewBox="0 0 9 8" refX="8" refY="4" markerWidth="9" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
						<path class="arrow" d="M0 0 9 4 0 8 2.5 4Z" />
					</marker>
				</defs>
				<rect width="100%" height="100%" fill="url(#{uid}-minor)" />
				<rect width="100%" height="100%" fill="url(#{uid}-major)" />
				<g transform="translate({translateX} {translateY}) scale({camera.k})">
					{#each layout.platforms as placed (placed.platform.id)}
						<IsoPlatform {placed} active={relatedPlatforms.has(placed.platform.id)} />
					{/each}
					{#each layout.edges as { edge, path, length }, index (edge.id)}
						{@const active = activeIds.has(edge.from) || activeIds.has(edge.to)}
						{@const edgeLabel = captions.edgeLabels.get(edge.id)}
						<g class="edge" class:active class:inactive={edge.inactive} class:muted={!!activeIds.size && !active} style:--tone={toneVars[edge.tone]}>
							<path class="route" class:dashed={edge.dashed || edge.inactive || edge.kind === 'denied' || edge.kind === 'tunnel'}
								d={path} marker-start={edge.bidirectional ? `url(#${uid}-arrow)` : undefined}
								marker-end={edge.directed || edge.bidirectional ? `url(#${uid}-arrow)` : undefined} />
							{#if packetIds.has(edge.id)}
								<circle class="packet" r="3">
									<animateMotion {path} begin="{-((index % 11) * 0.21)}s"
										dur="{Math.max(2.4, Math.min(rotating ? PACKET_COHORT_MS / 1000 : 14, length / 62))}s" repeatCount="indefinite" />
								</circle>
							{/if}
							{#if edgeLabel}
								<g class="edge-label" transform="translate({edgeLabel.point.x} {edgeLabel.point.y}) scale({edgeLabel.scale})">
									<title>{edge.label}</title>
									<rect x={-edgeLabel.width / 2} y="-10.5" width={edgeLabel.width} height="21" rx="5" />
									<text y="4">{edgeLabel.text}</text>
								</g>
							{/if}
						</g>
					{/each}
					{#each layout.nodes as placed (placed.node.id)}
						<IsoNodeBlock {placed} active={activeIds.has(placed.node.id)} dimmed={!!activeIds.size && !relatedIds.has(placed.node.id)} />
					{/each}
					{#each layout.items as { id } (id)}
						{@const caption = captions.items.get(id)}
						{#if caption && (camera.k >= 0.38 || activeIds.has(id))}
							<IsoCaption {caption} active={relatedPlatforms.has(id)} status={layout.nodesById.get(id)?.status} />
						{/if}
					{/each}
				</g>
			</svg>
			<div class="targets" style:transform={stageTransform} style:--zoom={camera.k}>
				{#each interactive as { id, point } (id)}
					{@const node = layout.nodesById.get(id)}
					{@const caption = captions.items.get(id)}
					{@const at = !node && caption && camera.k >= 0.38 ? caption.position : point}
					{@const lift = node ? -10 : caption && camera.k >= 0.38 ? caption.height * caption.scale / 2 : 0}
					<button type="button" class="target" class:node={!!node} aria-label={itemName(id)} title={itemName(id)}
						aria-pressed={selectedId === id} style:left="{at.x}px" style:top="{at.y + lift}px"
						style:--hit-width="{node ? 96 : Math.max(80, (caption?.width ?? 80) * (caption?.scale ?? 1))}px"
						onfocus={(event) => focusItem(event, id, at, lift)} onblur={() => { focusedId = undefined; oncancelintent?.(); }}
						onpointerenter={() => { if (!dragging) { hoveredId = id; onintent?.(id); } }}
						onpointerleave={() => { hoveredId = undefined; oncancelintent?.(); }}
						onclick={(event) => { if (!dragged || event.detail === 0) onselect?.(id); }}></button>
				{/each}
			</div>
		</div>
	{/if}
	{#if !empty}
		<div class="sr-only">
			<ul aria-label={t('diagram.items')}>
				{#each layout.items as { id } (id)}<li>{itemName(id)}</li>{/each}
			</ul>
			{#if layout.edges.length}
				<ul aria-label={t('diagram.paths')}>
					{#each layout.edges as { edge } (edge.id)}
						<li>{t(edge.directed && !edge.bidirectional ? 'diagram.path' : 'diagram.link', { from: itemLabels.get(edge.from) ?? '', to: itemLabels.get(edge.to) ?? '' })}{edge.label ? ` · ${edge.label}` : ''}{edge.inactive ? ` · ${t('status.inactive')}` : ''}</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
	<figcaption id="{uid}-description" class="description">
		{#if caption}<p>{caption}</p>{/if}
		{#if !empty}
			<div class="legend" role="group" aria-label={t('diagram.legend')}>
				<p class="packet-note"><span class="swatch packet-key" aria-hidden="true"></span>{t('diagram.packet')}</p>
				{#if hasInactivePaths || scene.legend?.some(({ kind }) => kind !== 'packet')}
					<details open>
						<summary>{t('diagram.legend')}</summary>
						<ul role="list" class="legend-items">
							{#each (scene.legend ?? []).filter(({ kind }) => kind !== 'packet') as item}
								<li><span class="swatch {item.kind}" style:--tone={toneVars[item.tone]} aria-hidden="true"></span>{item.label}</li>
							{/each}
							{#if hasInactivePaths}
								<li><span class="swatch edge inactive-key" aria-hidden="true"></span>{t('diagram.inactivePath')}</li>
							{/if}
						</ul>
					</details>
				{/if}
			</div>
		{/if}
	</figcaption>
</figure>

<style>
	.diagram { container-type: inline-size; min-inline-size: 0; margin: 0; position: relative; }
	.controls { display: flex; align-items: center; justify-content: flex-end; gap: .375rem; margin-block-end: .5rem; }
	.controls svg { fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; width: 1.125rem; height: 1.125rem; }
	.controls output { min-inline-size: 3.25rem; text-align: center; font-size: var(--type-identifier); color: var(--color-ink-2); font-variant-numeric: tabular-nums; }
	.viewport { position: relative; isolation: isolate; overflow: clip; inline-size: 100%; block-size: var(--diagram-height, clamp(14rem, min(60svh, 72cqi), 39rem)); border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-canvas); cursor: grab; touch-action: none; user-select: none; }
	.viewport.dragging { cursor: grabbing; }
	.viewport:focus-visible { outline: 2px solid var(--color-line-2); outline-offset: 2px; }
	.world, .targets { position: absolute; inset: 0; pointer-events: none; }
	.world { width: 100%; height: 100%; }
	.targets { transform-origin: 0 0; }
	.target { position: absolute; translate: -50% -50%; pointer-events: auto; inline-size: var(--hit-width); block-size: 44px; padding: 0; border: 0; background: transparent; border-radius: var(--radius-lg); cursor: pointer; }
	.target.node { block-size: 110px; }
	.target:focus-visible { outline: calc(2px / var(--zoom)) solid var(--color-ink-0); outline-offset: calc(2px / var(--zoom)); }
	.dragging .target { cursor: grabbing; }
	.minor, .major { fill: none; stroke-width: .02; }
	.minor { stroke: var(--color-topology-grid-minor); }
	.major { stroke: var(--color-topology-grid-major); }
	.route { fill: none; stroke: color-mix(in oklab, var(--edge-ink, var(--tone)) 68%, var(--color-ink-2)); stroke-width: 2; stroke-linecap: round; }
	.route.dashed { stroke-dasharray: 5 5; }
	.edge.muted { opacity: .30; }
	.edge.inactive { --edge-ink: var(--color-ink-2); opacity: .63; }
	.edge.inactive.muted { opacity: .26; }
	.edge.active .route { stroke: var(--color-ink-0); stroke-width: 2.45; }
	.arrow { fill: var(--color-ink-2); fill: context-stroke; }
	.packet { fill: var(--edge-ink, var(--tone)); stroke: var(--color-ink-0); stroke-width: 1.1; }
	.edge-label rect { fill: var(--color-surface-base); stroke: var(--color-line-2); }
	.edge-label text { fill: var(--color-ink-1); text-anchor: middle; font-size: 11px; font-variant-numeric: tabular-nums; }
	.empty { display: grid; place-content: center; min-block-size: 9rem; color: var(--color-ink-2); text-align: center; }
	.description { color: var(--color-ink-2); font-size: var(--type-support); }
	.description p { margin-block: .5rem 0; }
	.legend { padding-block-start: .625rem; }
	.legend summary { cursor: pointer; min-block-size: var(--control-height); align-content: center; inline-size: fit-content; }
	.legend-items { display: flex; flex-wrap: wrap; column-gap: 1rem; row-gap: .375rem; margin: 0; padding: 0; list-style: none; }
	.legend-items li, .packet-note { display: flex; align-items: baseline; gap: .4rem; }
	.swatch { display: inline-block; flex: none; inline-size: .6rem; block-size: .6rem; background: var(--tone); border-radius: .15rem; }
	.swatch.platform { inline-size: .75rem; block-size: .5rem; transform: skewY(-16deg); }
	.swatch.edge { inline-size: .8rem; block-size: 2px; align-self: center; }
	.swatch.inactive-key { block-size: 0; background: none; border-block-start: 2px dashed var(--color-ink-2); border-radius: 0; }
	.packet-key { inline-size: .45rem; block-size: .45rem; border-radius: 50%; background: var(--color-ink-2); }
	@media (prefers-reduced-motion: reduce) { .packet { display: none; } }
</style>
