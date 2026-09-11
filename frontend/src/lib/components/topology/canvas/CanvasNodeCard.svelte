<script lang="ts">
	// 캔버스 노드 카드. 크기·위치는 layout pos 로만 결정하고, 텔레메트리는 문자열 prop 으로 받아 재배치 없이 갱신한다.
	import Pill from '$lib/components/ui/Pill.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { colorOfNet } from './topologyGraph';
	import { KIND_LABEL, r1 } from './canvasHelpers';
	import type { CanvasGraph, CanvasNode, Rect } from './types';

	interface Props {
		node: CanvasNode;
		rect: Rect;
		graph: CanvasGraph;
		selected?: boolean;
		/** 검색 비매칭(0.15) */
		dim?: boolean;
		/** 활성 노드와 무관(0.45) */
		faded?: boolean;
		dragging?: boolean;
		armed?: boolean;
		/** VM NIC key → 축약 속도 문자열 */
		nicRates?: ReadonlyMap<string, string>;
		/** 스위치·LB 카드용 양방향 속도 문자열 */
		rateText?: string | null;
		dataTour?: string;
		onselect?: (id: string) => void;
		onhover?: (id: string | null) => void;
		onfocusnode?: (id: string) => void;
		onblurnode?: (id: string) => void;
	}

	let {
		node,
		rect,
		graph,
		selected = false,
		dim = false,
		faded = false,
		dragging = false,
		armed = false,
		nicRates,
		rateText = null,
		dataTour,
		onselect,
		onhover,
		onfocusnode,
		onblurnode,
	}: Props = $props();

	// 외부(프로바이더) 네트워크의 가상 스위치는 인터넷 경계이므로 구름 글리프로 표시한다
	const isExternal = $derived(node.kind === 'switch' && graph.netById.get(node.netId)?.kind === 'external');

	const netColor = $derived.by(() => {
		switch (node.kind) {
			case 'vm': return node.nics[0] ? colorOfNet(graph, node.nics[0].netId) : 'var(--color-state-neutral)';
			case 'switch': return colorOfNet(graph, node.netId);
			case 'lb': return node.vipNetId ? colorOfNet(graph, node.vipNetId) : 'var(--color-state-neutral)';
			default: return 'var(--color-topology-gateway)';
		}
	});

	const ariaLabel = $derived.by(() => {
		let ips = '';
		if (node.kind === 'vm') ips = node.nics.map((n) => n.ip).join(', ');
		else if (node.kind === 'router') ips = node.ports.map((p) => p.ip).filter(Boolean).join(', ');
		else if (node.kind === 'lb') ips = node.vip ?? '';
		else if (node.kind === 'switch') ips = graph.netById.get(node.netId)?.cidrs.join(', ') ?? '';
		return `${KIND_LABEL[node.kind]} ${node.name} · ${node.status || '—'}${ips ? ' · ' + ips : ''}`;
	});

	const switchNet = $derived(node.kind === 'switch' ? graph.netById.get(node.netId) ?? null : null);

	function handleClick(e: MouseEvent) {
		// 포인터 선택은 뷰포트 pointerup 히트테스트가 담당한다. detail 0 은 키보드(Enter/Space)·프로그램 click 이다.
		if (e.detail === 0) onselect?.(node.id);
	}
</script>

<button
	type="button"
	class="node node-{node.kind}"
	class:is-selected={selected}
	class:is-dim={dim}
	class:is-faded={faded}
	class:is-dragging={dragging}
	class:is-armed={armed}
	class:is-error={node.status === 'ERROR'}
	data-node-id={node.id}
	data-tour={dataTour}
	aria-pressed={selected}
	aria-label={ariaLabel}
	style:--net={netColor}
	style:width="{rect.w}px"
	style:height="{rect.h}px"
	style:transform="translate({r1(rect.x)}px, {r1(rect.y)}px)"
	onclick={handleClick}
	onpointerenter={() => onhover?.(node.id)}
	onpointerleave={() => onhover?.(null)}
	onfocus={() => onfocusnode?.(node.id)}
	onblur={() => onblurnode?.(node.id)}
>
	<span class="node-head">
		<span class="node-glyph" aria-hidden="true">
			{#if node.kind === 'vm' && node.isDatabase}
				<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><ellipse cx="8" cy="4" rx="5" ry="2" /><path d="M3 4v8a5 2 0 0 0 10 0V4M3 8a5 2 0 0 0 10 0" /></svg>
			{:else if node.kind === 'vm'}
				<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3"><ellipse cx="8" cy="5" rx="5" ry="2" /><path d="M3 5v6M13 5v6M3 11a5 2 0 0 0 10 0" /></svg>
			{:else if node.kind === 'switch' && isExternal}
				<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4.6 10.6a2.4 2.4 0 0 1 .3-4.78 3.3 3.3 0 0 1 6.32-.6A2.6 2.6 0 0 1 11.6 10.6z" /><path d="M8 10.6v2.2M4.4 12.8h7.2" /></svg>
			{:else if node.kind === 'switch'}
				<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="5" width="12" height="6" rx="1" /><path d="M5 8h1M8 8h1M11 8h1" /></svg>
			{:else if node.kind === 'router'}
				<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6" /><path d="M8 4v8M4 8h8M5.5 5.5l5 5M10.5 5.5l-5 5" /></svg>
			{:else}
				<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2v12M3 5h10M4 11h8" /></svg>
			{/if}
		</span>
		<span class="node-name" class:mono={node.kind === 'switch'}>{node.name}</span>
		{#if node.kind === 'vm'}
			{#if node.isDatabase}<Pill tone="accent" size="xs">DB</Pill>{/if}
			{#if node.nics.length > 1}<Pill tone="warm" size="xs">{node.nics.length}NIC</Pill>{/if}
			<StatusChip status={node.status} />
		{:else if node.kind === 'switch'}
			{#if node.isolated}<Pill tone="neutral" size="xs">격리</Pill>{/if}
			{#if switchNet && switchNet.status !== 'ACTIVE'}<StatusChip status={switchNet.status} />{/if}
		{:else if node.kind === 'router'}
			<StatusChip status={node.status} />
		{:else}
			<StatusChip status={node.status} />
			<StatusChip status={node.operating} />
		{/if}
	</span>

	{#if node.kind === 'vm'}
		<span class="nic-list">
			{#if node.nics.length === 0}
				<span class="parked-note">미연결 · 네트워크 없음</span>
			{/if}
			{#each node.nics as nic (nic.key)}
				<span
					class="nic-row"
					data-nic={nic.key}
					style:--net={colorOfNet(graph, nic.netId)}
					title="{nic.label} · {graph.netById.get(nic.netId)?.name ?? ''} · {nic.ip}{nic.mac ? ' · ' + nic.mac : ''}"
				>
					<span class="nic-port">{nic.label}</span>
					<span class="nic-ip">{nic.ip}</span>
					<span class="nic-bps mono">{nicRates?.get(nic.key) ?? '—'}</span>
				</span>
				{#each nic.fips as fip (fip.addr)}
					<span class="nic-row nic-fip-row" data-nic={nic.key}>
						<span class="nic-port">✦</span>
						<span class="nic-ip">{fip.addr}</span>
					</span>
				{/each}
			{/each}
		</span>
	{:else if node.kind === 'switch'}
		<span class="node-sub">
			<span>{node.role}</span>
			<span class="rate mono">{rateText ?? '▼ —  ▲ —'}</span>
		</span>
	{:else if node.kind === 'router'}
		<span class="node-sub">
			{#each node.badges as badge (badge)}
				<Pill tone={badge === '게이트웨이 없음' ? 'neutral' : 'accent'} size="xs">{badge}</Pill>
			{/each}
			<span class="rate">포트 {node.ports.length}</span>
		</span>
	{:else}
		<span class="node-sub">
			<span class="mono">VIP {node.vip ?? '—'}</span>
			<span>리스너 {node.listeners.length}</span>
			<span class="rate mono">{rateText ?? '▼ —  ▲ —'}</span>
		</span>
	{/if}
</button>

<style>
	.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
	.node {
		position: absolute;
		left: 0;
		top: 0;
		margin: 0;
		padding: 0;
		text-align: left;
		font: inherit;
		color: var(--color-ink-1);
		background: var(--color-surface-raised);
		border: 1px solid var(--color-line);
		border-radius: 0.5rem;
		cursor: grab;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		touch-action: none;
		transition:
			opacity var(--motion-duration-base) var(--motion-ease-standard),
			box-shadow var(--motion-duration-fast) var(--motion-ease-standard),
			border-color var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.node:hover { z-index: 2; border-color: var(--color-line-2); }
	.node:focus-visible { outline: none; box-shadow: var(--focus-ring); z-index: 3; }
	.node.is-selected { z-index: 3; border-color: var(--color-line-2); box-shadow: 0 0 0 4px var(--accent-ring); }
	.node.is-armed { box-shadow: 0 0 0 4px var(--accent-ring); }
	.node.is-dragging { cursor: grabbing; z-index: 4; }
	.node.is-dim { opacity: 0.15; }
	.node.is-faded { opacity: 0.45; }
	.node.is-error { border-color: color-mix(in oklab, var(--color-state-danger) 60%, var(--color-line)); }
	.node-head {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		height: 40px;
		padding: 0 0.5rem;
		border-left: 3px solid var(--net);
		min-width: 0;
	}
	.node-glyph { display: inline-flex; color: var(--net); flex-shrink: 0; }
	.node-glyph svg { width: 16px; height: 16px; }
	.node-name {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-ink-0);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		min-width: 0;
		flex: 1 1 auto;
	}
	.node-name.mono { font-weight: 500; font-size: 0.75rem; }
	.node-sub {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		height: 24px;
		padding: 0 0.5rem 0 calc(0.5rem + 3px);
		font-size: 0.75rem;
		color: var(--color-ink-2);
		white-space: nowrap;
		overflow: hidden;
		min-width: 0;
	}
	.node-sub .mono { color: var(--color-ink-1); }
	.node-sub .rate { margin-left: auto; color: var(--color-ink-2); font-variant-numeric: tabular-nums; }
	.node-switch .node-head { height: 26px; }
	.node-switch .node-sub { height: 20px; }
	.node-router .node-sub, .node-lb .node-sub { height: 26px; }
	.node-router .node-head { border-left-color: var(--color-topology-gateway); }
	.node-router .node-glyph { color: var(--color-topology-gateway); }
	.nic-list { display: block; padding: 0 0 6px; margin: 0; }
	.nic-row {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		height: 20px;
		padding: 0 0.5rem;
		font-family: var(--font-mono);
		font-variant-numeric: tabular-nums;
		font-size: 0.75rem;
		color: var(--color-ink-1);
		white-space: nowrap;
		min-width: 0;
	}
	.nic-row::before { content: ''; width: 6px; height: 6px; border-radius: 999px; background: var(--net); flex-shrink: 0; }
	.nic-row:hover { background: var(--color-surface-sunken); }
	.nic-port { color: var(--net); font-weight: 500; min-width: 2.25rem; }
	.nic-ip { color: var(--color-ink-0); }
	.nic-bps { margin-left: auto; color: var(--color-ink-2); }
	.nic-fip-row { padding-left: 1.25rem; color: var(--color-topology-external); }
	.nic-fip-row::before { background: transparent; width: 0; }
	.nic-fip-row .nic-ip { color: var(--color-topology-external); }
	.parked-note { display: flex; align-items: center; height: 20px; padding: 0 0.5rem; font-size: 0.75rem; color: var(--color-ink-2); }
	/* LOD: 축소 단계별로 bps → IP → 본문 순으로 숨긴다(부모 .world 의 data-lod) */
	:global(.topology-world[data-lod='nobps']) .nic-bps { display: none; }
	:global(.topology-world[data-lod='noip']) .nic-bps,
	:global(.topology-world[data-lod='noip']) .nic-ip { display: none; }
	:global(.topology-world[data-lod='compact']) .nic-list,
	:global(.topology-world[data-lod='compact']) .node-sub { visibility: hidden; }
	@media (forced-colors: active) {
		.node:focus-visible { outline: 2px solid CanvasText; }
	}
</style>
