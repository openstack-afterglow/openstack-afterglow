<script module lang="ts">
	type GraphicKind = 'server' | 'gpu' | 'gateway' | 'mcp' | 'kubernetes' | 'onprem';
	type Icon = 'cpu' | 'memory' | 'disk' | 'network' | 'vm' | 'data' | 'gpu' | 'model' | 'container' | 'node' | 'cloud' | 'team' | 'hub' | 'terminal' | 'plug';

	const paths: Record<Icon, string> = {
		cpu: 'M8 8h8v8H8z M5 10h3 M5 14h3 M16 10h3 M16 14h3 M10 5v3 M14 5v3 M10 16v3 M14 16v3',
		memory: 'M3 8h18v8H3z M7 8v8 M11 8v8 M15 8v8 M6 16v3 M18 16v3',
		disk: 'M5 7c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3z M5 7v10c0 1.7 3.1 3 7 3s7-1.3 7-3V7 M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3',
		network: 'M12 4v5 M12 9H6v4 M12 9h6v4 M10 2h4v3h-4z M4 13h4v4H4z M16 13h4v4h-4z M10 17h4v4h-4z M12 9v8',
		vm: 'M4 5h16v11H4z M9 20h6 M12 16v4 M8 9h3 M8 12h6',
		data: 'M3 7h7l2 2h9v10H3z',
		gpu: 'M3 7h16v10H3z M19 10h2 M19 14h2 M7 10a2 2 0 1 0 0 .01 M13 12a3 3 0 1 0 0 .01 M6 17v3 M10 17v3 M14 17v3',
		model: 'M12 3l8 4.5v9L12 21l-8-4.5v-9z M12 12l8-4.5 M12 12v9 M12 12L4 7.5',
		container: 'M4 8l8-4 8 4v8l-8 4-8-4z M4 8l8 4 8-4 M12 12v8',
		node: 'M4 4h16v6H4z M4 14h16v6H4z M7 7h.01 M7 17h.01 M11 7h6 M11 17h6',
		cloud: 'M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1-1 9z',
		team: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M3 20a6 6 0 0 1 12 0 M16 5a3 3 0 0 1 0 6 M18 20a6 6 0 0 0-3-5.2',
		hub: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M12 3v6 M12 15v6 M3 12h6 M15 12h6',
		terminal: 'M4 5h16v14H4z M7 9l3 3-3 3 M12 15h5',
		plug: 'M9 3v5 M15 3v5 M6 8h12v3a6 6 0 0 1-12 0z M12 17v4',
	};

	// Illustrative values: product units, not live measurements.
	const serverSpec: { icon: Icon; label: 'cpu' | 'memory' | 'storage' | 'network'; value: string; fill?: number }[] = [
		{ icon: 'cpu', label: 'cpu', value: '8 vCPU', fill: 0.5 },
		{ icon: 'memory', label: 'memory', value: '32 GB', fill: 0.62 },
		{ icon: 'disk', label: 'storage', value: '200 GB', fill: 0.4 },
		{ icon: 'network', label: 'network', value: '10.0.12.5' },
	];
	const dataset = [{ name: 'images/', fill: 0.82 }, { name: 'labels/', fill: 0.36 }, { name: 'train.csv', fill: 0.18 }];
	const gpus = [0.92, 0.86, 0.95, 0.8];
	const nodes = [['web', 'api'], ['api', 'worker'], ['web', 'worker']];
	const rack: Icon[] = ['cpu', 'gpu', 'disk', 'network'];
	const teams = [{ name: 'A', cpu: 0.6, gpu: 0.4 }, { name: 'B', cpu: 0.35, gpu: 0.75 }, { name: 'C', cpu: 0.5, gpu: 0.2 }];
	// Lumen gateway: configured provider families and the two agent wire protocols (docs/api/chat.md).
	const providers = ['OpenAI', 'Anthropic', 'Gemini', 'OpenRouter', 'DeepSeek'];
	const agents = [{ name: 'Claude Code', route: '/v1/messages', command: '$ claude' }, { name: 'Codex', route: '/v1/responses', command: '$ codex' }];
	// Real Afterglow MCP tool names; `hit` marks the calls the example agent makes.
	const monitorTools = [{ name: 'afterglow_vm_list', hit: 3.4 }, { name: 'afterglow_quota_get' }, { name: 'afterglow_cloud_overview_get' }];
	const manageTools = [{ name: 'afterglow_vm_action', hit: 6.8 }, { name: 'afterglow_volume_create' }];
</script>

<script lang="ts">
	import { t } from '$lib/i18n/ns/public-entry';
	import type { SceneMotionState } from './sceneMotion';

	interface Props { kind: GraphicKind; state?: SceneMotionState; }
	let { kind, state = 'static' }: Props = $props();
	const specLabel = (label: (typeof serverSpec)[number]['label']) =>
		label === 'cpu' ? 'CPU' : label === 'memory' ? t('landing.story.visual.memory') : t(`landing.story.diagram.${label}`);
</script>

{#snippet glyph(name: Icon)}
	<svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d={paths[name]} /></svg>
{/snippet}

{#snippet link(delay: number)}
	<span class="link" style:--d={delay}><span class="pulse"></span></span>
{/snippet}

{#snippet status(delay: number, before: string, after: string)}
	<span class="status" style:--d={delay}><span class="was"><i></i>{before}</span><span class="now"><i></i>{after}</span></span>
{/snippet}

<div class="landing-motion-graphic" data-graphic={kind} data-motion={state} role="img" aria-label={t(`landing.story.${kind}.graphic`)}>
	<div class="window" aria-hidden="true">
		<div class="window-bar"><span class="dots"><i></i><i></i><i></i></span><span>{t(`landing.story.${kind}.label`)}</span></div>
		<div class="canvas">
			{#if kind === 'server'}
				<div class="panel spec">
					{#each serverSpec as row, index}
						<div class="spec-row enter" style:--d={index * 0.8}>
							<span class="tile">{@render glyph(row.icon)}</span>
							<span class="spec-name">{specLabel(row.label)}</span>
							{#if row.fill !== undefined}<span class="meter"><span class="fill" style:--v={row.fill} style:--d={index * 0.8 + 0.4}></span></span>{/if}
							<strong class="mono">{row.value}</strong>
						</div>
					{/each}
				</div>
				{@render link(3.4)}
				<div class="panel result framed enter" style:--d={4.2}>
					<span class="frame-label">{t('landing.story.diagram.project')}</span>
					<div class="result-head"><span class="tile big">{@render glyph('vm')}</span><div><strong>{t('landing.story.diagram.research')}</strong><span class="mono muted">research-01</span></div></div>
					{@render status(5.4, t('landing.story.visual.preparing'), t('landing.story.visual.running'))}
					<code class="terminal"><span class="type" style:--d={6.4} style:--chars={26}>$ ssh researcher@10.0.12.5</span></code>
				</div>
			{:else if kind === 'gpu'}
				<div class="panel column enter" style:--d={0}>
					<div class="panel-head">{@render glyph('data')}<strong>{t('landing.story.visual.dataset')}</strong></div>
					{#each dataset as file, index}
						<div class="file"><span class="mono">{file.name}</span><span class="meter"><span class="fill" style:--v={file.fill} style:--d={0.6 + index * 0.5}></span></span></div>
					{/each}
				</div>
				{@render link(2.2)}
				<div class="panel column enter" style:--d={3}>
					<div class="panel-head">{@render glyph('gpu')}<strong>GPU × {gpus.length}</strong></div>
					<div class="gpu-grid">
						{#each gpus as load, index}
							<div class="gpu"><span class="util"><span class="level" style:--v={load} style:--d={3.6 + index * 0.2}></span></span><span class="mono">GPU{index}</span></div>
						{/each}
					</div>
				</div>
				{@render link(7)}
				<div class="panel column framed enter" style:--d={7.8}>
					<span class="frame-label">{t('landing.story.diagram.research')}</span>
					<div class="panel-head">{@render glyph('model')}<strong>{t('landing.story.diagram.model')}</strong></div>
					<svg class="chart" viewBox="0 0 120 64">
						<path class="axis" d="M4 4v56h112" />
						<path class="curve" style:--d={8.4} pathLength="1" d="M6 10C20 14 26 34 40 38S66 46 80 50 104 54 114 55" />
					</svg>
					{@render status(11, t('landing.story.visual.training'), t('landing.story.visual.trained'))}
					<span class="mono muted">model.pt</span>
				</div>
			{:else if kind === 'kubernetes'}
				<div class="cluster">
					{#each nodes as apps, column}
						<div class="panel node-box enter" style:--d={column * 0.6}>
							<div class="panel-head">{@render glyph('node')}<strong>{t('landing.story.visual.node', { index: column + 1 })}</strong></div>
							{#each apps as app, slot}
								<span class="pod drop" style:--d={2 + (slot * 3 + column) * 0.6}>{@render glyph('container')}<span class="mono">{app}</span></span>
							{/each}
						</div>
					{/each}
				</div>
				<div class="cluster-foot enter" style:--d={6}>
					{@render status(6.4, t('landing.story.visual.preparing'), t('landing.story.visual.containersRunning', { count: nodes.flat().length }))}
				</div>
			{:else if kind === 'gateway'}
				<div class="panel column enter" style:--d={0}>
					<div class="panel-head">{@render glyph('cloud')}<strong>{t('landing.story.visual.providers')}</strong></div>
					{#each providers as name, index}
						<span class="row-item"><span>{name}</span><i class="led" style:--d={0.4 + index * 0.3}></i></span>
					{/each}
				</div>
				{@render link(2.2)}
				<div class="panel column enter" style:--d={3}>
					<div class="panel-head">{@render glyph('hub')}<strong>Lumen</strong></div>
					{#each agents as agent}
						<span class="row-item"><span class="mono">{agent.route}</span><span class="muted">{agent.name}</span></span>
					{/each}
					<span class="field"><span class="muted">{t('landing.story.visual.routing')}</span><span class="mono">lumen/anthropic/sonnet</span></span>
					<span class="field"><span class="muted">{t('landing.story.visual.researcherKeys')}</span><span class="mono">sk-lumen-••••</span></span>
					<span class="field"><span class="muted">{t('landing.story.visual.usage')}</span><span class="meter"><span class="fill warm" style:--v={0.46} style:--d={4.4}></span></span></span>
				</div>
				{@render link(6)}
				<div class="panel column framed enter" style:--d={6.8}>
					<span class="frame-label">{t('landing.story.visual.agents')}</span>
					{#each agents as agent, index}
						<div class="agent">
							<div class="panel-head">{@render glyph('terminal')}<strong>{agent.name}</strong></div>
							<code class="terminal"><span class="type" style:--d={7.6 + index * 1.6} style:--chars={agent.command.length}>{agent.command}</span></code>
						</div>
					{/each}
				</div>
			{:else if kind === 'mcp'}
				<div class="panel column enter" style:--d={0}>
					<div class="panel-head">{@render glyph('terminal')}<strong>Claude Code</strong></div>
					<code class="terminal transcript">
						<span class="enter" style:--d={0.6}>› {t('landing.story.mcp.prompt')}</span>
						<span class="call enter" style:--d={2.4}>⏺ afterglow_vm_list</span>
						<span class="call enter" style:--d={5.8}>⏺ afterglow_vm_action</span>
						<span class="reply enter" style:--d={9.2}>{t('landing.story.mcp.reply')}</span>
					</code>
				</div>
				{@render link(2.4)}
				<div class="panel column enter" style:--d={1.2}>
					<div class="panel-head">{@render glyph('plug')}<strong>MCP</strong></div>
					<span class="tool-group muted">{t('landing.story.visual.monitor')}</span>
					{#each monitorTools as tool}<span class="tool mono" class:hit={tool.hit} style:--d={tool.hit}>{tool.name}</span>{/each}
					<span class="tool-group muted">{t('landing.story.visual.manage')}</span>
					{#each manageTools as tool}<span class="tool mono" class:hit={tool.hit} style:--d={tool.hit}>{tool.name}</span>{/each}
				</div>
				{@render link(6.6)}
				<div class="panel column framed enter" style:--d={2}>
					<span class="frame-label">{t('landing.story.diagram.platform')}</span>
					<span class="vm-row">{@render glyph('vm')}<span class="mono">research-01</span><span class="muted">GPU</span><span class="status"><span class="badge"><i></i>{t('landing.story.visual.running')}</span></span></span>
					<span class="vm-row">{@render glyph('vm')}<span class="mono">research-02</span><span class="muted">GPU</span>{@render status(8, t('landing.story.visual.stopped'), t('landing.story.visual.running'))}</span>
					<span class="vm-row">{@render glyph('vm')}<span class="mono">research-03</span><span class="muted">CPU</span><span class="status"><span class="badge"><i></i>{t('landing.story.visual.running')}</span></span></span>
				</div>
			{:else}
				<div class="panel column enter" style:--d={0}>
					<div class="rack">
						{#each rack as unit, index}
							<span class="unit">{@render glyph(unit)}<span class="rails"></span><i class="led" style:--d={index * 0.4}></i></span>
						{/each}
					</div>
					<span class="caption">{t('landing.story.diagram.institution')}</span>
				</div>
				{@render link(2)}
				<div class="panel column cloud enter" style:--d={2.8}>
					<span class="tile big">{@render glyph('cloud')}</span>
					<strong>{t('landing.story.diagram.platform')}</strong>
					<span class="muted">{t('landing.story.visual.shared')}</span>
				</div>
				{@render link(4.2)}
				<div class="panel column framed teams enter" style:--d={5}>
					<span class="frame-label">{t('landing.story.diagram.project')}</span>
					{#each teams as team, index}
						<div class="team">
							<span class="team-name">{@render glyph('team')}{t('landing.story.visual.team', { name: team.name })}</span>
							<span class="quota"><span class="mono">CPU</span><span class="meter"><span class="fill" style:--v={team.cpu} style:--d={5.6 + index * 0.5}></span></span></span>
							<span class="quota"><span class="mono">GPU</span><span class="meter"><span class="fill warm" style:--v={team.gpu} style:--d={5.8 + index * 0.5}></span></span></span>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	/* The base frame is the finished picture; motion only replays how it got there. */
	.landing-motion-graphic { --unit: 0.42s; container-type: inline-size; width: 100%; min-width: 0; padding-block: 1rem 0.5rem; }
	.window { border: 1px solid var(--color-line-2); border-radius: var(--radius-xl); background: var(--color-surface-canvas); color: var(--color-ink-0); overflow: hidden; }
	.window-bar { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1rem; border-bottom: 1px solid var(--color-line); color: var(--color-ink-2); font-size: 0.8125rem; }
	.dots { display: inline-flex; gap: 0.375rem; }
	.dots i { width: 0.625rem; height: 0.625rem; border-radius: 50%; background: var(--color-line-2); }
	.canvas { display: flex; align-items: stretch; justify-content: center; gap: 0.5rem; min-height: 19rem; padding: 2rem 1.5rem; font-size: 0.875rem; }
	.canvas:has(.cluster) { flex-direction: column; gap: 1rem; }

	.panel { position: relative; display: grid; align-content: start; gap: 0.75rem; min-width: 0; padding: 1rem; border: 1px solid var(--color-line-2); border-radius: var(--radius-lg); background: var(--color-surface-raised); }
	.column { flex: 1 1 0; }
	.framed { border: 1px dashed var(--color-warm); background: color-mix(in oklab, var(--color-warm) 7%, var(--color-surface-raised)); }
	.frame-label { position: absolute; top: 0; left: 1rem; translate: 0 -50%; padding-inline: 0.375rem; background: var(--color-surface-canvas); color: var(--color-warm-text); font-size: 0.75rem; font-weight: 600; white-space: nowrap; }
	.panel-head { display: flex; align-items: center; gap: 0.5rem; }
	.panel-head .glyph { color: var(--color-warm); }
	.glyph { flex: none; width: 1.125rem; height: 1.125rem; }
	.tile { display: inline-grid; place-items: center; width: 2rem; height: 2rem; border: 1px solid var(--color-line); border-radius: var(--radius-md, 0.5rem); color: var(--color-warm); }
	.tile.big { width: 2.75rem; height: 2.75rem; }
	.tile.big .glyph { width: 1.5rem; height: 1.5rem; }
	.mono { font-family: var(--font-mono); font-size: 0.8125rem; }
	.muted, .caption { color: var(--color-ink-2); font-size: 0.8125rem; }
	.caption { margin-top: auto; padding-top: 0.25rem; border-top: 1px solid var(--color-line); text-align: center; }
	.meter { position: relative; display: block; height: 0.375rem; border-radius: 999px; background: var(--color-line); overflow: hidden; }
	.fill { position: absolute; inset: 0 auto 0 0; width: calc(var(--v) * 100%); border-radius: inherit; background: var(--color-ink-2); transform-origin: left; }
	.fill.warm { background: var(--color-warm); }

	.spec { flex: 1.2 1 0; gap: 0.875rem; }
	.spec-row { display: grid; grid-template-columns: auto 5rem minmax(3rem, 1fr) auto; align-items: center; gap: 0.75rem; }
	.spec-row:not(:has(.meter)) strong { grid-column: 3 / 5; justify-self: end; }
	.spec-row strong { text-align: right; }
	.result { flex: 1 1 0; align-content: center; gap: 1rem; }
	.result-head { display: flex; align-items: center; gap: 0.75rem; }
	.result-head div { display: grid; }
	.terminal { display: block; padding: 0.625rem 0.75rem; border-radius: var(--radius-md, 0.5rem); background: var(--color-surface-sunken); color: var(--color-ink-1); font-family: var(--font-mono); font-size: 0.75rem; white-space: nowrap; overflow: hidden; }
	.type { display: inline-block; overflow: hidden; vertical-align: bottom; }

	.status { display: inline-grid; justify-self: start; font-size: 0.8125rem; font-weight: 600; }
	.status > span { grid-area: 1 / 1; display: inline-flex; align-items: center; gap: 0.375rem; padding: 0.25rem 0.625rem; border-radius: 999px; white-space: nowrap; }
	.status i { width: 0.5rem; height: 0.5rem; border-radius: 50%; background: currentColor; }
	.was { color: var(--color-state-warning-text); background: color-mix(in oklab, var(--color-state-warning) 14%, transparent); opacity: 0; }
	.now, .badge { color: var(--color-state-success-text); background: color-mix(in oklab, var(--color-state-success) 14%, transparent); }

	.file { display: grid; grid-template-columns: 5.5rem minmax(2rem, 1fr); align-items: center; gap: 0.5rem; }
	.gpu-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; }
	.gpu { display: grid; justify-items: center; gap: 0.375rem; }
	.util { position: relative; width: 100%; height: 5.5rem; border: 1px solid var(--color-line); border-radius: var(--radius-md, 0.5rem); overflow: hidden; }
	.level { position: absolute; inset: auto 0 0; height: calc(var(--v) * 100%); background: linear-gradient(to top, var(--color-warm), color-mix(in oklab, var(--color-warm) 35%, transparent)); transform-origin: bottom; }
	.gpu .mono { font-size: 0.6875rem; color: var(--color-ink-2); }
	.chart { width: 100%; max-height: 5rem; overflow: visible; }
	.chart path { fill: none; }
	.axis { stroke: var(--color-line-2); stroke-width: 1; }
	.curve { stroke: var(--color-warm); stroke-width: 2; stroke-dasharray: 1; }

	.cluster { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem; flex: 1; }
	.node-box { align-content: start; }
	.pod { display: flex; align-items: center; gap: 0.5rem; padding: 0.625rem 0.75rem; border: 1px solid color-mix(in oklab, var(--color-warm) 45%, var(--color-line)); border-radius: var(--radius-md, 0.5rem); background: var(--color-surface-canvas); }
	.pod .glyph { color: var(--color-warm); }
	.cluster-foot { display: flex; justify-content: center; }

	.rack { display: grid; gap: 0.5rem; }
	.unit { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 0.75rem; padding: 0.5rem 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-md, 0.5rem); background: var(--color-surface-sunken); color: var(--color-ink-1); }
	.rails { height: 0.375rem; border-block: 1px solid var(--color-line-2); }
	.led { width: 0.5rem; height: 0.5rem; border-radius: 50%; background: var(--color-state-success); }
	.cloud { flex: 0.9 1 0; justify-items: center; align-content: center; text-align: center; }
	.teams { gap: 0.75rem; }
	.team { display: grid; gap: 0.375rem; }
	.team + .team { padding-top: 0.75rem; border-top: 1px solid var(--color-line); }
	.team-name { display: flex; align-items: center; gap: 0.5rem; font-weight: 600; }
	.team-name .glyph { color: var(--color-warm); }
	.quota { display: grid; grid-template-columns: 2.25rem 1fr; align-items: center; gap: 0.5rem; }
	.quota .mono { font-size: 0.6875rem; color: var(--color-ink-2); }

	.row-item { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.5rem 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-md, 0.5rem); background: var(--color-surface-sunken); min-width: 0; }
	.row-item .led { flex: none; }
	.field { display: grid; gap: 0.25rem; min-width: 0; overflow-wrap: anywhere; }
	.agent { display: grid; gap: 0.5rem; }
	.agent + .agent { padding-top: 0.75rem; border-top: 1px solid var(--color-line); }
	.transcript { display: grid; gap: 0.5rem; white-space: normal; overflow-wrap: anywhere; line-height: 1.5; }
	.transcript .call { color: var(--color-warm-text); }
	.transcript .reply { color: var(--color-ink-0); }
	.tool-group { margin-top: 0.25rem; font-size: 0.75rem; }
	.tool { padding: 0.375rem 0.625rem; border: 1px solid var(--color-line); border-radius: var(--radius-md, 0.5rem); color: var(--color-ink-1); font-size: 0.75rem; overflow-wrap: anywhere; }
	.tool.hit { border-color: var(--color-warm); background: color-mix(in oklab, var(--color-warm) 12%, transparent); color: var(--color-warm-text); }
	.vm-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 0.25rem 0.5rem; padding-block: 0.5rem; }
	.vm-row + .vm-row { border-top: 1px solid var(--color-line); }
	.vm-row .glyph { color: var(--color-warm); }
	.vm-row .status { grid-column: 2 / 4; }

	.link { position: relative; flex: none; align-self: center; width: clamp(1.75rem, 5cqi, 3.5rem); height: 2px; background: var(--color-line-2); transform-origin: left; }
	.link::after { content: ''; position: absolute; right: 0; top: 50%; width: 0.5rem; height: 0.5rem; border-top: 2px solid var(--color-line-2); border-right: 2px solid var(--color-line-2); transform: translate(0, -50%) rotate(45deg); }
	.pulse { position: absolute; top: 50%; left: 0; width: 0.5rem; height: 0.5rem; border-radius: 50%; background: var(--color-warm); box-shadow: 0 0 0.75rem var(--color-warm); translate: -50% -50%; opacity: 0; }

	@container (max-width: 40rem) {
		.canvas { flex-direction: column; align-items: stretch; padding: 1.75rem 1rem 1.25rem; gap: 0.5rem; }
		.link { align-self: center; width: 2px; height: 2rem; transform-origin: top; }
		.link::after { top: auto; bottom: 0; right: 50%; transform: translate(50%, 0) rotate(135deg); }
		.framed { margin-top: 0.75rem; }
		.spec-row { grid-template-columns: auto 4.5rem minmax(2rem, 1fr) auto; }
	}

	@container (max-width: 28rem) { .cluster { grid-template-columns: minmax(0, 1fr); } }
	/* Motion: finite, unit-staggered, paused with the scene. */
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) :is(.enter, .drop, .fill, .level, .curve, .type, .led, .was, .now, .link, .pulse, .hit) {
		animation-delay: calc(var(--d, 0) * var(--unit));
		animation-timing-function: var(--motion-ease-emphasized, ease-out);
		animation-fill-mode: backwards;
		animation-duration: 0.6s;
	}
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .enter { animation-name: graphic-enter; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .drop { animation-name: graphic-drop; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .fill { animation-name: graphic-fill; animation-duration: 0.9s; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .level { animation-name: graphic-load; animation-duration: 2.6s; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .curve { animation-name: graphic-draw; animation-duration: 2.6s; animation-timing-function: ease-in-out; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .type { animation-name: graphic-type; animation-duration: 1.4s; animation-timing-function: steps(var(--chars)); }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .led { animation-name: graphic-blink; animation-duration: 0.5s; animation-iteration-count: 4; animation-timing-function: steps(2); }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .was { animation-name: graphic-was; animation-fill-mode: both; animation-delay: 0s; animation-duration: calc((var(--d) + 1) * var(--unit)); animation-timing-function: linear; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .now { animation-name: graphic-now; animation-delay: 0s; animation-duration: calc((var(--d) + 1) * var(--unit)); animation-timing-function: linear; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .link { animation-name: graphic-link; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .hit { animation-name: graphic-hit; animation-duration: 0.5s; }
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .pulse { animation-name: graphic-pulse; animation-duration: 1s; animation-iteration-count: 2; animation-delay: calc((var(--d) + 1) * var(--unit)); animation-timing-function: ease-in-out; }
	.landing-motion-graphic[data-motion='paused'] * { animation-play-state: paused; }

	@keyframes graphic-enter { from { opacity: 0; transform: translateY(0.75rem); } }
	@keyframes graphic-drop { from { opacity: 0; transform: translateY(-1.5rem); } }
	@keyframes graphic-fill { from { transform: scaleX(0); } }
	@keyframes graphic-load { 0% { transform: scaleY(0); } 30% { transform: scaleY(0.75); } 50% { transform: scaleY(0.45); } 75% { transform: scaleY(1.05); } }
	@keyframes graphic-draw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
	@keyframes graphic-link-y { from { transform: scaleY(0); } }
	@keyframes graphic-pulse-y { 0% { left: 50%; top: 0; opacity: 0; } 15%, 85% { opacity: 1; } 100% { left: 50%; top: 100%; opacity: 0; } }
	@container (max-width: 40rem) {
		.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .link { animation-name: graphic-link-y; }
		.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .pulse { animation-name: graphic-pulse-y; }
	}
	@keyframes graphic-link { from { transform: scaleX(0); } }
	@keyframes graphic-pulse { 0% { left: 0; top: 50%; opacity: 0; } 15%, 85% { opacity: 1; } 100% { left: 100%; top: 50%; opacity: 0; } }
	@keyframes graphic-type { from { max-width: 0; } to { max-width: calc(var(--chars) * 1ch); } }
	@keyframes graphic-blink { 50% { opacity: 0.2; } }
	@keyframes graphic-was { 0%, 90% { opacity: 1; } 100% { opacity: 0; } }
	@keyframes graphic-now { 0%, 90% { opacity: 0; } 100% { opacity: 1; } }
	@keyframes graphic-hit { from { border-color: var(--color-line); background: transparent; color: var(--color-ink-1); } }

	@media (forced-colors: active) {
		.glyph, .tile { color: CanvasText; }
		.pulse, .fill, .level, .led { background: CanvasText; box-shadow: none; }
		.curve { stroke: CanvasText; }
	}
</style>
