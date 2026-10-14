<script lang="ts">
	import type { TopologyHost } from '$lib/types/infrastructureTopology';
	import { buildNetworkMap, collapseHops, type NetworkEdge, type NetworkNode } from './evidence';
	import { t } from '$lib/i18n/ns/infra-topology';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	let { hosts, verified, selectedId, onselect }: { hosts: TopologyHost[]; verified: boolean; selectedId: string; onselect: (id: string) => void } = $props();
	const graph = $derived(buildNetworkMap(hosts, verified));
	const componentId = $props.id();
	type ProbeState = 'up' | 'down' | 'unknown';
	type PendingTraceState = 'queued' | 'running' | 'error' | 'unsupported' | 'expired';
	// Probe edges carry probe states; non-observed trace edges carry diagnosis states.
	const probeState = (state: NetworkEdge['state']): ProbeState => state === 'up' || state === 'down' ? state : 'unknown';
	const traceState = (state: NetworkEdge['state']): PendingTraceState =>
		state === 'queued' || state === 'running' || state === 'unsupported' || state === 'expired' ? state : 'error';
	function edgeLabel(edge: NetworkEdge, compact = false): string {
		const status = probeState(edge.state);
		const label = edge.kind === 'probe' ? t('network.probeLabel', { port: edge.probe!.port.toLocaleString(intlLocale(), { useGrouping: false }), status: compact ? t(`network.probe.${status}`) : t(`probe.${status}`) })
			: edge.state === 'observed' ? t('outbound') : edge.state === 'unconfirmed' ? t(compact ? 'network.unconfirmedShort' : 'network.unconfirmed') : t(`trace.${traceState(edge.state)}`);
		return edge.stale ? `${label} · ${t('trace.stale')}` : label;
	}
	function hopDetail(node: NetworkNode): string {
		if (node.kind === 'gap' && node.minHop !== null && node.maxHop !== null && node.maxHop !== node.minHop) {
			return t('network.gapRun', { from: node.minHop, to: node.maxHop, count: node.maxHop - node.minHop + 1 });
		}
		const hop = t('network.hopRange', { hop: node.minHop ?? 0 });
		if (node.kind === 'gap') return hop;
		return `${hop} · ${t('rtt')} ${rtt(node.rttMin)}${node.rttMax !== node.rttMin ? ` – ${rtt(node.rttMax)}` : ''}`;
	}
	function rtt(value: number | null): string {
		return value !== null && Number.isFinite(value) ? t('rttValue', { value: value.toLocaleString(intlLocale(), { maximumFractionDigits: 2 }) }) : t('unknown');
	}
</script>

<section class="network-map" aria-label={t('network.title')}>
	<h2 class="font-semibold">{t('network.title')}</h2>
	<p class="text-sm text-ink-2">{t('network.help')}</p>
	<!-- The fixed-size diagram can exceed narrow viewports; keyboard users must be able to focus and scroll this region. -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div class="map-scroll" role="region" tabindex="0" aria-label={t('network.diagram')}>
		<div class="canvas" style:width={`${graph.width}px`} style:height={`${graph.height}px`}>
			<svg width={graph.width} height={graph.height} viewBox={`0 0 ${graph.width} ${graph.height}`} aria-hidden="true">
				<defs><marker id={`${componentId}-arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" /></marker></defs>
				{#each graph.edges as edge (edge.id)}
					<g class:stale={edge.stale} class="edge" data-edge-kind={edge.kind} data-edge-state={edge.state}>
						<title>{edgeLabel(edge)}</title>
						<path d={edge.d} class="connection" class:dashed={edge.dashed} class:probe={edge.kind === 'probe'} class:up={edge.state === 'up'} class:down={edge.state === 'down'} class:unknown={edge.state === 'unknown'} marker-end={`url(#${componentId}-arrow)`} />
						<text x={edge.labelX} y={edge.labelY} text-anchor="middle">{edgeLabel(edge, true)}</text>
					</g>
				{/each}
			</svg>
			{#each graph.nodes as node (node.id)}
				<div class="node" class:stale={node.stale} data-node-kind={node.kind} data-node-id={node.id} style:left={`${node.x}px`} style:top={`${node.y}px`}>
					{#if node.kind === 'host'}
						<Button variant={node.hostId === selectedId ? 'primary' : 'secondary'} ariaPressed={node.hostId === selectedId} ariaLabel={node.label} onclick={() => onselect(node.hostId!)} class="w-full min-h-11 min-w-0"><span class="node-name" title={node.label}>{node.label}</span></Button>
					{:else}
						<div class="node-box" title={node.label} aria-label={node.label}><span class="node-name">{node.label}</span></div>
					{/if}
					<p class="node-detail">{#if node.kind === 'host'}{t('host')} · {t(`state.${node.observationState ?? 'unmeasured'}`)}{:else}{node.kind === 'gap' ? t('network.gap') : node.kind === 'peer' ? t('probeOutside') : node.kind === 'router' ? t('network.router') : t('destination')}{#if node.stale} · {t('trace.stale')}{/if}{/if}</p>
					{#if node.minHop !== null}<p class="node-detail">{hopDetail(node)}</p>{/if}
				</div>
			{/each}
		</div>
	</div>
	<ul class="legend text-xs text-ink-2" aria-label={t('network.legend')}>
		<li>{t('network.shared')}</li><li>{t('network.gapHelp')}</li><li>{t('network.dashed')}</li><li>{t('network.outboundLegend')}</li><li>{t('probeNotice')}</li>
	</ul>
	<section aria-label={t('network.paths')} class="path-list">
		<h3 class="text-sm font-semibold">{t('network.paths')}</h3>
		{#each graph.paths as path (path.id)}
			<div class="path-detail" data-path-id={path.id}>
				<p class="text-sm"><strong class="font-mono">{path.hostName} → {path.target}</strong> · {t(`trace.${path.status}`)} · {t(path.reached ? 'reached' : 'unreached')}{#if path.stale} · {t('trace.stale')}{/if}</p>
				{#if path.error}<p class="text-xs text-ink-2">{t(`error.${path.error}`)}</p>{/if}
				<ol aria-label={t('network.pathLabel', { host: path.hostName, target: path.target })}>
					<li><span class="font-mono">{path.hostName}</span> · {t('host')}</li>
					{#each collapseHops(path.hops) as item}
						{#if item.kind === 'gap'}<li><span class="font-mono">*</span> · {item.count > 1 ? t('network.gapRun', { from: item.from, to: item.to, count: item.count }) : `${t('hop')} ${item.from} · ${t('network.gap')}`}</li>
						{:else}<li><span class="font-mono">{item.hop.ip}</span> · {t('hop')} {item.hop.hop} · {t('rtt')} {rtt(item.hop.rtt_ms)}</li>{/if}
					{/each}
					{#if path.hops.at(-1)?.ip !== path.target}<li><span class="font-mono">{path.target}</span> · {t('network.unconfirmed')}</li>{/if}
				</ol>
			</div>
		{:else}<p class="text-sm text-ink-2">{t('noTraces')}</p>{/each}
	</section>
</section>

<style>
	.network-map { min-width: 0; display: grid; gap: 1rem; }
	.map-scroll { min-width: 0; max-width: 100%; overflow-x: auto; border: 1px solid var(--color-line); border-radius: var(--radius-md); }
	.map-scroll:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.canvas { position: relative; }
	svg { display: block; position: absolute; inset: 0; }
	.connection { fill: none; stroke: var(--color-topology-link); stroke-width: 1.5; }
	.probe { stroke: var(--color-topology-internal); }
	.up { stroke: var(--color-state-success); }
	.down { stroke: var(--color-state-warning); }
	.unknown { stroke: var(--color-line-2); }
	.dashed { stroke-dasharray: 5 4; }
	.stale { opacity: 0.55; }
	text { fill: var(--color-ink-2); font-size: 10px; paint-order: stroke; stroke: var(--color-surface-raised); stroke-width: 3px; stroke-linejoin: round; }
	.node { position: absolute; width: 180px; min-width: 0; }
	.node-name { display: block; min-width: 0; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--font-mono); }
	.node-box { min-height: 44px; display: flex; align-items: center; padding: 0.5rem 0.75rem; border: 1px solid var(--color-topology-router); border-radius: var(--radius-md); background: var(--color-surface-raised); font-size: 0.75rem; }
	[data-node-kind='destination'] .node-box, [data-node-kind='peer'] .node-box { border-color: var(--color-topology-external); }
	[data-node-kind='gap'] .node-box { border-color: var(--color-line-2); border-style: dashed; }
	.node-detail { margin: 0.25rem 0 0; color: var(--color-ink-2); font-size: 0.625rem; overflow-wrap: anywhere; }
	.legend { display: grid; gap: 0.35rem; list-style: disc; padding-inline-start: 1rem; }
	.path-list { display: grid; gap: 0.75rem; min-width: 0; }
	.path-detail { min-width: 0; overflow-wrap: anywhere; border-top: 1px solid var(--color-line); padding-block-start: 0.75rem; }
	ol { list-style: decimal; padding-inline-start: 1.5rem; margin-block-start: 0.5rem; font-size: 0.75rem; color: var(--color-ink-1); }
</style>
