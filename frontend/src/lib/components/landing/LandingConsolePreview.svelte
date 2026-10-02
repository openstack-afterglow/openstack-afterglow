<script module lang="ts">
	export type ConsolePreviewView = 'project' | 'cluster' | 'network';
</script>

<script lang="ts">
	import UsageBar from '$lib/components/ui/UsageBar.svelte';

	interface Props {
		view: ConsolePreviewView;
		class?: string;
	}

	let { view, class: className = '' }: Props = $props();

	type IconName = 'overview' | 'server' | 'cluster' | 'network' | 'storage' | 'external' | 'router';

	const views: ConsolePreviewView[] = ['project', 'cluster', 'network'];

	const screenLabels: Record<ConsolePreviewView, string> = {
		project: '프로젝트 개요 예시 화면',
		cluster: '클러스터 예시 화면',
		network: '네트워크 토폴로지 예시 화면',
	};

	const railItems: IconName[] = ['overview', 'server', 'cluster', 'network', 'storage'];
	const railCurrent: Record<ConsolePreviewView, IconName> = {
		project: 'overview',
		cluster: 'cluster',
		network: 'network',
	};

	const counters = [
		{ label: '인스턴스', value: 4 },
		{ label: '볼륨', value: 6 },
		{ label: '클러스터', value: 1 },
	];

	const quotas = [
		{ label: 'vCPU', value: 40, max: 64, unit: '' },
		{ label: '메모리', value: 160, max: 256, unit: ' GB' },
		{ label: 'GPU', value: 1, max: 2, unit: '' },
		{ label: '스토리지', value: 3.2, max: 10, unit: ' TB' },
	];

	const activity = [
		{ time: '09:41', text: '연구원 · VM 생성 요청' },
		{ time: '09:42', text: '시스템 · 네트워크 연결' },
		{ time: '10:05', text: '교수자 · 쿼터 조정' },
	];

	const nodes = [
		{ name: 'control-plane', role: '제어', cpu: 18, pods: 6 },
		{ name: 'worker-1', role: '워커', cpu: 62, pods: 8 },
		{ name: 'worker-2', role: '워커', cpu: 55, pods: 8 },
		{ name: 'worker-3', role: '워커', cpu: 48, pods: 8 },
	];

	const chain: Array<{ kind: 'external' | 'router' | 'internal'; kindLabel: string; name: string; mono: boolean; icon: IconName }> = [
		{ kind: 'external', kindLabel: '외부', name: '외부망', mono: false, icon: 'external' },
		{ kind: 'router', kindLabel: '라우터', name: 'router-lab', mono: true, icon: 'router' },
		{ kind: 'internal', kindLabel: '내부', name: 'lab-net', mono: true, icon: 'network' },
	];

	const instances = [
		{ name: 'vm-a', address: '10.10.0.11' },
		{ name: 'vm-b', address: '10.10.0.12' },
		{ name: 'vm-c', address: '10.10.0.13' },
	];

	const legend = [
		{ kind: 'external', label: '외부' },
		{ kind: 'router', label: '라우터' },
		{ kind: 'internal', label: '내부' },
	];
</script>

{#snippet icon(name: IconName)}
	<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
		{#if name === 'overview'}
			<rect x="4" y="4" width="7" height="7" rx="1" /><rect x="13" y="4" width="7" height="7" rx="1" /><rect x="4" y="13" width="7" height="7" rx="1" /><rect x="13" y="13" width="7" height="7" rx="1" />
		{:else if name === 'server'}
			<rect x="4" y="4" width="16" height="7" rx="1.5" /><rect x="4" y="13" width="16" height="7" rx="1.5" /><path d="M8 7.5h.01M8 16.5h.01" />
		{:else if name === 'cluster'}
			<path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z" /><circle cx="12" cy="12" r="2.5" />
		{:else if name === 'network'}
			<circle cx="12" cy="5" r="2" /><circle cx="5" cy="19" r="2" /><circle cx="19" cy="19" r="2" /><path d="M12 7v5M12 12l-5.5 5.5M12 12l5.5 5.5" />
		{:else if name === 'storage'}
			<ellipse cx="12" cy="6" rx="7" ry="2.5" /><path d="M5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
		{:else if name === 'external'}
			<circle cx="12" cy="12" r="8" /><path d="M4 12h16M12 4c2.5 2.6 2.5 13.4 0 16M12 4c-2.5 2.6-2.5 13.4 0 16" />
		{:else}
			<rect x="4" y="13" width="16" height="6" rx="1.5" /><path d="M8 16h.01M12 16h.01M9 9.5a4.2 4.2 0 0 1 6 0M6.5 7a7.8 7.8 0 0 1 11 0" />
		{/if}
	</svg>
{/snippet}

<div class={`console-preview ${className}`.trim()} data-view={view} role="group" aria-label={screenLabels[view]}>
	<ul class="rail" aria-hidden="true">
		{#each railItems as item}
			<li class:current={item === railCurrent[view]}>{@render icon(item)}</li>
		{/each}
	</ul>

	<div class="screens">
		{#each views as screen}
			{@const inactive = screen !== view}
			<div class="screen" class:inactive data-screen={screen} aria-hidden={inactive ? 'true' : undefined} inert={inactive}>
				{#if screen === 'project'}
					<p class="screen-head enter" style="--i: 0"><span class="ident">lab-vision</span><span class="head-sep" aria-hidden="true">·</span><span class="screen-title">프로젝트 개요</span></p>
					<dl class="counters">
						{#each counters as counter, index}
							<div class="panel counter enter" style={`--i: ${index}`}><dt>{counter.label}</dt><dd>{counter.value}</dd></div>
						{/each}
					</dl>
					<div class="project-detail">
						<section class="panel enter" style="--i: 3" aria-label="쿼터 사용량">
							<p class="panel-title">쿼터 사용량</p>
							<div class="meters">
								{#each quotas as quota}
									<UsageBar size="sm" label={quota.label} value={quota.value} max={quota.max} unit={quota.unit} />
								{/each}
							</div>
						</section>
						<section class="panel enter" style="--i: 4" aria-label="최근 활동">
							<p class="panel-title">최근 활동</p>
							<ol class="activity">
								{#each activity as entry}
									<li><span class="time">{entry.time}</span><span class="row-text">{entry.text}</span></li>
								{/each}
							</ol>
						</section>
					</div>
				{:else if screen === 'cluster'}
					<div class="screen-head enter" style="--i: 0">
						<p class="cluster-title"><span class="ident">course-dl-k8s</span><span class="row-label">Kubernetes 1.30 · 노드 4</span></p>
						<span class="status" data-status="done"><i class="dot" aria-hidden="true"></i>Ready</span>
					</div>
					<ul class="nodes" aria-label="노드">
						{#each nodes as node, index}
							<li class="panel node enter" style={`--i: ${Math.min(index + 1, 4)}`}>
								<span class="node-name">{@render icon('cluster')}<span class="ident">{node.name}</span></span>
								<span class="row-label node-role">{node.role}</span>
								<span class="status node-status" data-status="done"><i class="dot" aria-hidden="true"></i>Ready</span>
								<span class="node-cpu"><span class="row-label">CPU</span><UsageBar size="xs" showValue={false} value={node.cpu} max={100} /><b class="row-value">{node.cpu}%</b></span>
								<span class="node-pods"><span class="row-label">Pod</span><b class="row-value">{node.pods}</b></span>
							</li>
						{/each}
					</ul>
					<p class="cluster-foot enter" style="--i: 4"><span class="row-label">Pod</span> <b class="row-value">30</b><span class="head-sep" aria-hidden="true">·</span><span class="row-label">네임스페이스</span> <b class="row-value">24</b></p>
				{:else}
					<p class="screen-head enter" style="--i: 0"><span class="ident">lab-vision</span><span class="head-sep" aria-hidden="true">·</span><span class="screen-title">네트워크 토폴로지</span></p>
					<ol class="topology" aria-label="연결 순서">
						{#each chain as hop, index}
							<li class="hop" style={`--i: ${index}`}>
								<div class="panel topo-node enter" data-kind={hop.kind}>
									<span class="topo-kind">{@render icon(hop.icon)}<span class="row-label">{hop.kindLabel}</span></span>
									<span class:ident={hop.mono} class:topo-name={!hop.mono}>{hop.name}</span>
								</div>
								<span class="link" aria-hidden="true"></span>
							</li>
						{/each}
						<li class="hop hop-instances" style="--i: 3">
							<ul class="instances" aria-label="lab-net 연결 인스턴스">
								{#each instances as instance}
									<li class="panel topo-node instance enter" data-kind="internal">
										<span class="stub" aria-hidden="true"></span>
										<span class="topo-kind">{@render icon('server')}<span class="ident">{instance.name}</span></span>
										<span class="address">{instance.address}</span>
									</li>
								{/each}
							</ul>
						</li>
					</ol>
					<ul class="legend enter" style="--i: 4" aria-label="범례">
						{#each legend as item}
							<li><i class="swatch" data-kind={item.kind} aria-hidden="true"></i><span class="row-label">{item.label}</span></li>
						{/each}
					</ul>
				{/if}
			</div>
		{/each}
	</div>
</div>

<style>
	.console-preview {
		container: console-preview / inline-size;
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		min-width: 0;
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
		font-family: var(--font-sans);
		font-size: 0.75rem;
		letter-spacing: 0;
		line-height: 1.45;
	}
	.console-preview :where(p, ul, ol, dl, dd) {
		margin: 0;
		padding: 0;
	}
	.console-preview :where(ul, ol) {
		list-style: none;
	}

	.icon {
		width: 1rem;
		height: 1rem;
		flex: 0 0 auto;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.5;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.rail {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.5rem 0.375rem;
		border-right: 1px solid var(--color-line);
		background: var(--color-surface-base);
		color: var(--color-ink-2);
	}
	.rail li {
		display: grid;
		width: 1.75rem;
		height: 1.75rem;
		place-items: center;
		border-radius: var(--radius-md);
	}
	.rail li.current {
		background: var(--color-surface-selected);
		color: var(--color-ink-0);
	}

	.screens {
		display: grid;
		min-width: 0;
	}
	.screen {
		grid-area: 1 / 1;
		display: flex;
		min-width: 0;
		flex-direction: column;
		gap: 0.75rem;
		padding: 0.75rem;
	}
	.screen.inactive {
		visibility: hidden;
	}

	/* D1 shared vocabulary */
	.panel {
		min-width: 0;
		padding: 0.75rem;
		border: 1px solid var(--color-line);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
	}
	.panel-title,
	.screen-title {
		color: var(--color-ink-0);
		font-size: 0.8125rem;
		font-weight: 600;
	}
	.panel-title {
		margin-bottom: 0.625rem;
	}
	.row-label,
	.counter dt {
		color: var(--color-ink-2);
		font-size: 0.75rem;
	}
	.row-value {
		color: var(--color-ink-0);
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		font-weight: 600;
	}
	.ident {
		min-width: 0;
		overflow: hidden;
		color: var(--color-ink-1);
		font-family: var(--font-mono);
		font-size: 0.75rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.head-sep {
		margin-inline: 0.375rem;
		color: var(--color-ink-2);
	}
	.status {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.75rem;
		font-weight: 500;
		white-space: nowrap;
	}
	.status[data-status='done'] {
		color: var(--color-state-success-text);
	}
	.dot {
		width: 0.375rem;
		height: 0.375rem;
		flex: 0 0 auto;
		border-radius: 999px;
	}
	.status[data-status='done'] .dot {
		background: var(--color-state-success);
	}

	.screen-head {
		display: flex;
		min-width: 0;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.25rem 0.75rem;
	}
	p.screen-head {
		justify-content: flex-start;
		gap: 0;
	}
	.screen-head > p {
		display: flex;
		min-width: 0;
		flex-wrap: wrap;
		align-items: center;
	}
	.cluster-title {
		gap: 0 0.625rem;
	}

	/* project */
	.counters {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.5rem;
	}
	.counter dt {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.counter dd {
		margin-top: 0.25rem;
		color: var(--color-ink-0);
		font-size: 1.25rem;
		font-variant-numeric: tabular-nums;
		font-weight: 600;
		line-height: 1.2;
	}
	.project-detail {
		display: grid;
		gap: 0.75rem;
	}
	.meters {
		display: grid;
		gap: 0.75rem;
	}
	.activity {
		display: grid;
		gap: 0.5rem;
	}
	.activity li {
		display: flex;
		min-width: 0;
		gap: 0.625rem;
	}
	.time {
		flex: 0 0 auto;
		color: var(--color-ink-1);
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
	}
	.row-text {
		min-width: 0;
		color: var(--color-ink-1);
		font-size: 0.75rem;
	}

	/* cluster */
	.nodes {
		display: grid;
		gap: 0.5rem;
	}
	.node {
		display: grid;
		grid-template-areas: 'name name status' 'role cpu pods';
		grid-template-columns: auto minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.5rem 0.75rem;
		padding-block: 0.625rem;
	}
	.node-name {
		grid-area: name;
		display: flex;
		min-width: 0;
		align-items: center;
		gap: 0.375rem;
		color: var(--color-ink-2);
	}
	.node-role { grid-area: role; }
	.node-status { grid-area: status; }
	.node-cpu {
		grid-area: cpu;
		display: flex;
		min-width: 0;
		align-items: center;
		gap: 0.375rem;
	}
	.node-cpu :global(.usage-bar) {
		min-width: 0;
		flex: 1 1 auto;
	}
	.node-cpu .row-value {
		min-width: 2.25rem;
		text-align: right;
	}
	.node-pods {
		grid-area: pods;
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 0.375rem;
		min-width: 2.75rem;
	}
	.cluster-foot {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0 0.25rem;
		margin-top: auto;
		padding-top: 0.25rem;
	}

	/* network */
	.topology {
		display: flex;
		flex-direction: column;
	}
	.hop {
		display: flex;
		min-width: 0;
		flex-direction: column;
		align-items: stretch;
	}
	.topo-node {
		display: flex;
		min-width: 0;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem 0.75rem;
		padding-left: 1rem;
		position: relative;
	}
	.topo-node::before {
		content: '';
		position: absolute;
		inset: 0.5rem auto 0.5rem 0.375rem;
		width: 0.1875rem;
		border-radius: 999px;
		background: var(--kind-color);
	}
	[data-kind='external'] { --kind-color: var(--color-warm); }
	[data-kind='router'] { --kind-color: var(--color-accent); }
	[data-kind='internal'] { --kind-color: var(--color-state-success); }
	.topo-kind {
		display: flex;
		min-width: 0;
		align-items: center;
		gap: 0.375rem;
		color: var(--color-ink-2);
	}
	.topo-name {
		color: var(--color-ink-0);
		font-size: 0.8125rem;
		font-weight: 600;
	}
	.address {
		color: var(--color-ink-2);
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
	}

	/* Connector: 2px line bound to the layout gap, arrowhead via clip-path. */
	.link {
		position: relative;
		align-self: flex-start;
		width: 2px;
		height: 1rem;
		flex: 0 0 auto;
		margin-left: calc(1.25rem - 1px);
		background: var(--color-accent);
		transform-origin: top;
		--draw-from: scaleY(0);
		animation: draw var(--motion-duration-data) var(--motion-ease-out) both;
		animation-delay: calc(var(--motion-duration-base) * (var(--i) + 1));
	}
	.link::after {
		content: '';
		position: absolute;
		bottom: -1px;
		left: 50%;
		width: 0.5rem;
		height: 0.4375rem;
		background: inherit;
		clip-path: polygon(0 0, 100% 0, 50% 100%);
		transform: translateX(-50%);
	}
	.hop:nth-child(3) .link {
		display: none;
	}

	.hop-instances {
		margin-top: 1rem;
		padding-left: 2.25rem;
	}
	.instances {
		position: relative;
		display: grid;
		grid-auto-rows: 1fr;
		gap: 0.5rem;
	}
	/* Bus from lab-net down to the last instance; stubs branch into each instance. */
	.instances::before {
		content: '';
		position: absolute;
		top: -1rem;
		bottom: calc((100% - 1rem) / 6 - 1px);
		left: calc(-1rem - 1px);
		width: 2px;
		background: var(--color-accent);
		transform-origin: top;
		--draw-from: scaleY(0);
		animation: draw var(--motion-duration-data) var(--motion-ease-out) both;
		animation-delay: calc(var(--motion-duration-base) * 3);
	}
	.stub {
		position: absolute;
		top: calc(50% - 1px);
		right: calc(100% + 1px);
		width: 1rem;
		height: 2px;
		background: var(--color-accent);
		transform-origin: left;
		--draw-from: scaleX(0);
		animation: draw var(--motion-duration-data) var(--motion-ease-out) both;
		animation-delay: calc(var(--motion-duration-base) * 4);
	}
	.stub::after,
	.link::after {
		content: '';
		position: absolute;
		background: inherit;
	}
	.stub::after {
		top: 50%;
		right: -1px;
		width: 0.4375rem;
		height: 0.5rem;
		clip-path: polygon(0 0, 100% 50%, 0 100%);
		transform: translateY(-50%);
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1rem;
		margin-top: auto;
		padding-top: 0.25rem;
	}
	.legend li {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
	}
	.swatch {
		width: 0.1875rem;
		height: 0.75rem;
		border-radius: 999px;
		background: var(--kind-color);
	}

	/* D1 enter: once, in sequence, finite. */
	.enter {
		animation: preview-enter var(--motion-duration-panel) var(--motion-ease-out) both;
		animation-delay: calc(var(--motion-duration-base) * var(--i, 0));
	}
	.screen.inactive .enter,
	.screen.inactive .link,
	.screen.inactive .stub,
	.screen.inactive .instances::before {
		animation: none;
	}

	@keyframes preview-enter {
		from { opacity: 0; transform: translateY(0.5rem); }
		to { opacity: 1; transform: translateY(0); }
	}
	/* One keyframe for both orientations: switching animation-name across the container breakpoint left Chromium connectors unpainted. */
	@keyframes draw {
		from { transform: var(--draw-from); }
		to { transform: none; }
	}

	@container console-preview (min-width: 34rem) {
		.counters { gap: 0.75rem; }
		.meters { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.875rem 1rem; }

		.node {
			grid-template-areas: 'name role status cpu pods';
			grid-template-columns: minmax(0, 1.2fr) 2.25rem 4.25rem minmax(0, 1.5fr) 3rem;
			padding-block: 0.5rem;
		}

		.topology {
			flex-direction: row;
			align-items: center;
		}
		.hop {
			flex: 1 1 0;
			flex-direction: row;
			align-items: center;
		}
		.topo-node { flex-direction: column; flex-wrap: nowrap; align-items: stretch; gap: 0.25rem; }
		.hop > .topo-node { flex: 1 1 auto; }
		.link {
			align-self: center;
			width: 1.5rem;
			height: 2px;
			margin-left: 0;
			transform-origin: left;
			--draw-from: scaleX(0);
		}
		.link::after {
			top: 50%;
			right: -1px;
			bottom: auto;
			left: auto;
			width: 0.4375rem;
			height: 0.5rem;
			clip-path: polygon(0 0, 100% 50%, 0 100%);
			transform: translateY(-50%);
		}
		.hop:nth-child(3) .link { display: block; width: 0.75rem; }
		.hop:nth-child(3) .link::after { display: none; }
		.hop-instances {
			margin-top: 0;
			padding-left: 0.75rem;
		}
		.instances::before {
			top: calc((100% - 1rem) / 6 - 1px);
			left: -0.75rem;
		}
		.stub { right: 100%; width: 0.75rem; }
	}

	@container console-preview (min-width: 46rem) {
		.project-detail { grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); }
		.activity { gap: 0.625rem; }
		.activity li { flex-direction: column; gap: 0; }
	}
</style>
