<script lang="ts">
	import { t } from '$lib/i18n/ns/public-entry';
	import LandingSolid from './LandingSolid.svelte';
	import type { SceneMotionState } from './sceneMotion';

	interface Props {
		kind: 'hero' | 'server' | 'gpu' | 'kubernetes' | 'onprem';
		state?: SceneMotionState;
	}

	let { kind, state = 'static' }: Props = $props();
</script>

<div class="landing-motion-graphic" data-graphic={kind} data-motion={state}>
	<svg viewBox={kind === 'hero' ? '0 0 800 480' : '0 0 800 580'} role="img" aria-label={t(`landing.story.${kind}.graphic`)} focusable="false">
		{#if kind === 'hero'}
			<!-- Four different workloads stand on the same connected infrastructure. -->
			<LandingSolid x={55} y={306} width={600} depth={90} height={18} />
			{#each [{ x: 84, y: 266, count: 4, label: 'VM' }, { x: 250, y: 298, count: 8, label: 'GPU' }, { x: 416, y: 330, count: 5, label: 'AI' }, { x: 582, y: 362, count: 3, label: 'K8s' }] as tower, index}
				{#each Array.from({ length: tower.count }, (_, layer) => layer) as layer}
					<LandingSolid x={tower.x} y={tower.y - layer * 21} width={82} depth={58} height={15} tone={index === 1 || layer === tower.count - 1 ? 'accent' : 'neutral'} {state} dx={(index - 1.5) * (22 + layer * 6)} dy={-layer * 10 - 22} angle={(index % 2 ? -1 : 1) * (8 - layer)} step={layer} />
				{/each}
				<text class="hero-label settle" x={tower.x + 59} y={tower.y - tower.count * 21 - 20} text-anchor="middle">{tower.label}</text>
			{/each}
			<path class="route" pathLength="1" d="M75 322 627 455" />
		{:else if kind === 'server'}
			<!-- Resources align first. The bus only draws after all pieces have settled. -->
			<path class="route" pathLength="1" d="M230 136H316V424H230 M230 280H316 M316 280H480" />
			<text class="code settle" x="158" y="56" text-anchor="middle">CPU</text>
			{#each [{ y: 110, label: 'compute' }, { y: 254, label: 'storage' }, { y: 398, label: 'network' }] as const as resource, index}
				{#each [2, 1, 0] as layer}
					<LandingSolid x={70} y={resource.y + layer * 10} width={112} depth={48} height={8} tone={layer === 0 ? 'accent' : 'neutral'} {state} dx={-35 - layer * 16} dy={-15 - layer * 6} angle={-8 + layer * 2} step={index * 2 + layer} />
				{/each}
				<text class="label" x="158" y={resource.y + 100} text-anchor="middle">{t(`landing.story.diagram.${resource.label}`)}</text>
			{/each}
			<LandingSolid x={428} y={392} width={198} depth={98} height={20} />
			{#each [5, 4, 3, 2, 1, 0] as layer}
				<LandingSolid x={480} y={178 + layer * 33} width={126} depth={88} height={27} tone={layer === 0 ? 'accent' : 'neutral'} {state} dx={layer % 2 ? 44 : -26} dy={-24 - (5 - layer) * 10} angle={layer % 2 ? 7 : -7} step={5 - layer} />
			{/each}
			<text class="code settle" x="561" y="106" text-anchor="middle">VM</text>
			<text class="label" x="570" y="505" text-anchor="middle">{t('landing.story.diagram.project')}</text>
			<text class="label secondary" x="570" y="551" text-anchor="middle">{t('landing.story.diagram.research')}</text>
		{:else if kind === 'gpu'}
			<!-- A fan of data plates converges on an accelerator, then a model lattice. -->
			<path class="route" pathLength="1" d="M228 210H269Q292 210 292 235V320H320 M537 320H594Q616 320 616 298V223" />
			{#each [3, 2, 1, 0] as layer}
				<LandingSolid x={57} y={135 + layer * 23} width={108} depth={63} height={16} {state} dx={-layer * 12} dy={-layer * 14} angle={-10 + layer * 3} step={layer} />
			{/each}
			<text class="label" x="139" y="286" text-anchor="middle">{t('landing.story.diagram.data')}</text>
			<LandingSolid x={242} y={372} width={211} depth={150} height={21} />
			{#each [5, 4, 3, 2, 1, 0] as fin}
				<LandingSolid x={283 + fin * 25} y={332 + fin * 6} width={16} depth={113} height={28} tone="accent" {state} dx={(fin - 2.5) * 17} dy={-40 - fin * 7} angle={(fin - 2.5) * 3} step={fin} />
			{/each}
			<text class="code settle" x="421" y="480" text-anchor="middle">GPU</text>
			<text class="label" x="415" y="538" text-anchor="middle">{t('landing.story.diagram.research')}</text>
			<g class="lattice" class:motion-assemble={state !== 'static'} style="--motion-assemble-y: -45px; --motion-assemble-angle: 10deg; --motion-index: 7">
				<path class="lattice-edge" d="M546 113 616 76 686 113 686 187 616 224 546 187Z M546 113 616 150 686 113 M616 150v74 M616 76v74 M546 187 616 150 686 187" />
				{#each [[546, 113], [616, 76], [686, 113], [546, 187], [616, 150], [686, 187], [616, 224]] as node, index}
					<circle class="lattice-node" class:core={index === 4} cx={node[0]} cy={node[1]} r={index === 4 ? 18 : 9} />
				{/each}
			</g>
			<text class="label" x="618" y="44" text-anchor="middle">{t('landing.story.diagram.model')}</text>
		{:else if kind === 'kubernetes'}
			<!-- One suspended workload per node; the assembly falls into a shared cluster. -->
			<text class="label" x="400" y="48" text-anchor="middle">{t('landing.story.diagram.containers')}</text>
			<path class="cluster-track" d="M88 349H714L748 448H54Z" />
			{#each [124, 346, 568] as x, index}
				<path class="route" pathLength="1" d={`M${x + 68} 232V324`} />
				<LandingSolid {x} y={345} width={92} depth={76} height={65} />
				<LandingSolid x={x + 8} y={322} width={76} depth={60} height={17} tone="accent" />
				<LandingSolid x={x + 13} y={167} width={73} depth={56} height={52} tone="accent" {state} dx={(index - 1) * 55} dy={-54} angle={(index - 1) * 10} step={index * 3}>
					{#each [0, 1, 2] as rib}<path class="groove" d={`M${15 + rib * 17} ${13 + rib * 4}v28`} />{/each}
				</LandingSolid>
			{/each}
			<text class="label" x="402" y="498" text-anchor="middle">{t('landing.story.diagram.nodes')}</text>
			<text class="cluster-name" x="400" y="548" text-anchor="middle">Kubernetes</text>
		{:else}
			<!-- A shared cloud is one laminated sculpture, never transparent intersecting plates. -->
			<text class="label" x="145" y="53" text-anchor="middle">{t('landing.story.diagram.institution')}</text>
			<path class="route" pathLength="1" d="M221 146H275V434H221 M221 290H275 M275 290H326 M534 310H576V153H622 M576 310V427H622" />
			{#each [{ y: 130, label: 'compute' }, { y: 274, label: 'storage' }, { y: 418, label: 'network' }] as const as resource, index}
				<LandingSolid x={67} y={resource.y} width={100} depth={54} height={32} {state} dx={-25 - index * 8} dy={-18} angle={-7} step={index * 2} />
				<text class="label" x="144" y={resource.y + 100} text-anchor="middle">{t(`landing.story.diagram.${resource.label}`)}</text>
			{/each}
			{#each [6, 5, 4, 3, 2, 1, 0] as layer}
				<LandingSolid x={326} y={210 + layer * 22} width={125} depth={83} height={17} tone="accent" {state} dx={layer % 2 ? -35 : 35} dy={-(6 - layer) * 12} angle={(layer - 3) * 3} step={6 - layer} />
			{/each}
			<text class="label" x="430" y="443" text-anchor="middle">{t('landing.story.diagram.platform')}</text>
			<text class="label" x="625" y="83" text-anchor="middle">{t('landing.story.diagram.teams')}</text>
			{#each [141, 415] as y, index}
				<LandingSolid x={622} {y} width={82} depth={52} height={54} tone="accent" {state} dx={34} dy={index ? 36 : -36} angle={index ? -9 : 9} step={7}>
					<text class="vm-mark" x="42" y="44" text-anchor="middle">VM</text>
				</LandingSolid>
			{/each}
			<text class="label secondary" x="625" y="551" text-anchor="middle">{t('landing.story.diagram.project')}</text>
		{/if}
	</svg>
</div>

<style>
	.landing-motion-graphic { width: 100%; min-width: 0; }
	svg { display: block; width: 100%; height: auto; overflow: visible; font-family: var(--font-sans); }
	text { fill: var(--color-ink-0); font-weight: 500; }
	.label { font-size: 2.5rem; }
	.secondary { fill: var(--color-ink-2); }
	.code, .hero-label, .cluster-name, .vm-mark { font-family: var(--font-mono); }
	.code { font-size: 3rem; }
	.hero-label { font-size: 2.5rem; }
	.cluster-name { font-size: 2.5rem; }
	.vm-mark { font-size: 2.25rem; }
	.route { fill: none; stroke: var(--color-accent); stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: 1; }
	.cluster-track { fill: none; stroke: var(--color-line-2); stroke-width: 1.5; stroke-linejoin: round; }
	.groove { fill: none; stroke: var(--color-accent); stroke-width: 2; }
	.lattice { transform-box: fill-box; transform-origin: center; }
	.lattice-edge { fill: none; stroke: var(--color-accent); stroke-width: 3; stroke-linejoin: round; }
	.lattice-node { fill: var(--color-surface-raised); stroke: var(--color-accent); stroke-width: 3; }
	.lattice-node.core { fill: var(--color-accent); }
	/* Every assembly ends by 1.78s. Routes start at 2s, so wires never drift. */
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) .route {
		animation: motion-draw calc(var(--motion-duration-data) * 2) var(--motion-ease-emphasized) backwards;
		animation-delay: calc(var(--motion-duration-data) * 4);
	}
	.landing-motion-graphic:is([data-motion='playing'], [data-motion='paused']) :is(.settle, .label, .cluster-name) {
		animation: motion-fade var(--motion-duration-data) var(--motion-ease-out) backwards;
		animation-delay: calc(var(--motion-duration-data) * 4);
	}
	.landing-motion-graphic[data-motion='paused'] :is(.route, .settle, .label, .cluster-name, .lattice) { animation-play-state: paused; }
	@media (prefers-reduced-motion: reduce) {
		.landing-motion-graphic :is(.route, .settle, .label, .cluster-name, .lattice) { animation: none !important; transform: none; }
	}
</style>
