<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import UsageBar from '$lib/components/ui/UsageBar.svelte';
	import { MOTION_DURATION_MS, REDUCED_MOTION_QUERY } from '$lib/design/tokens';
	import { prefersReducedMotion } from '$lib/utils/motion';

	type ScenarioKey = 'gpu' | 'cluster' | 'data';
	type PanelKey = 'request' | 'policy' | 'resource' | 'reuse';
	type PanelState = 'ready' | 'waiting' | 'active' | 'done';
	type IconName = 'server' | 'network' | 'share' | 'layer' | 'lock' | 'node';
	type Row = { label: string; value: string; mono?: boolean };
	type Meter = { label: string; used: number; request: number; max: number; unit?: string };
	type Attachment = { icon: IconName; name: string; label: string };

	type Scenario = {
		key: ScenarioKey;
		label: string;
		request: string;
		project: string;
		requestedAt: string;
		route: string;
		requestRows: Row[];
		meters: Meter[];
		checks: Row[];
		policyDone: string;
		resourceWorking: string;
		resourceDone: string;
		reuse: { icons: IconName[]; name: string; kind: string; note: string; working: string; done: string };
	};

	const scenarios: Scenario[] = $derived([
		{
			key: 'gpu',
			label: t('opsBoard.gpu.label'),
			request: t('opsBoard.gpu.request'),
			project: t('opsBoard.gpu.project', { project: 'lab-vision', count: 2 }),
			requestedAt: '09:41',
			route: 'afterglow / compute / instances / new',
			requestRows: [
				{ label: t('opsBoard.preview.image'), value: 'PyTorch 2.4 · CUDA 12' },
				{ label: t('opsBoard.preview.spec'), value: 'GPU 1 · vCPU 16 · 64 GB' },
				{ label: t('opsBoard.policy.network'), value: 'lab-vision-net', mono: true },
			],
			meters: [
				{ label: 'GPU', used: 0, request: 1, max: 2 },
				{ label: 'vCPU', used: 8, request: 16, max: 64 },
			],
			checks: [{ label: t('opsBoard.preview.policy'), value: t('opsBoard.preview.gpuApproval') }],
			policyDone: t('opsBoard.policy.withinQuota'),
			resourceWorking: t('opsBoard.preview.creating'),
			resourceDone: t('opsBoard.preview.running'),
			reuse: { icons: ['lock', 'layer'], name: 'pytorch-vision-lab', kind: t('opsBoard.preview.immutableLayer'), note: t('opsBoard.preview.layerNote'), working: t('opsBoard.preview.saving'), done: t('opsBoard.preview.saved') },
		},
		{
			key: 'cluster',
			label: t('opsBoard.cluster.label'),
			request: t('opsBoard.cluster.request'),
			project: t('opsBoard.cluster.project', { project: 'course-dl', count: 24 }),
			requestedAt: '10:12',
			route: 'afterglow / containers / clusters / new',
			requestRows: [
				{ label: t('opsBoard.preview.template'), value: 'Kubernetes 1.30' },
				{ label: t('opsBoard.preview.workers'), value: '3 × vCPU 8 · 32 GB' },
				{ label: t('opsBoard.preview.labTeam'), value: t('opsBoard.preview.teamDuration') },
			],
			meters: [
				{ label: t('opsBoard.preview.instances'), used: 1, request: 4, max: 8 },
				{ label: 'vCPU', used: 8, request: 24, max: 64 },
			],
			checks: [{ label: t('opsBoard.preview.period'), value: t('opsBoard.preview.labDuration') }],
			policyDone: t('opsBoard.policy.withinQuota'),
			resourceWorking: t('opsBoard.preview.nodesPreparing'),
			resourceDone: t('opsBoard.preview.nodesReady'),
			reuse: { icons: ['layer'], name: 'distributed-training', kind: t('opsBoard.preview.clusterTemplate'), note: t('opsBoard.preview.clusterNote'), working: t('opsBoard.preview.saving'), done: t('opsBoard.preview.templateSaved') },
		},
		{
			key: 'data',
			label: t('opsBoard.data.label'),
			request: t('opsBoard.data.request'),
			project: t('opsBoard.data.project', { project: 'lab-genomics', count: 7 }),
			requestedAt: '11:08',
			route: 'afterglow / file-storage / shares / new',
			requestRows: [
				{ label: t('opsBoard.preview.shareSpace'), value: '2 TB · NFS' },
				{ label: t('opsBoard.preview.members'), value: t('opsBoard.preview.memberCount', { project: 'lab-genomics', count: 7 }) },
				{ label: t('opsBoard.preview.access'), value: t('opsBoard.preview.researchAccess') },
			],
			meters: [{ label: t('opsBoard.preview.storage'), used: 3, request: 2, max: 10, unit: ' TB' }],
			checks: [
				{ label: t('opsBoard.preview.access'), value: t('opsBoard.preview.rulesApproved') },
				{ label: t('opsBoard.preview.retention'), value: t('opsBoard.policy.days', { count: 30 }) },
			],
			policyDone: t('opsBoard.policy.approved'),
			resourceWorking: t('opsBoard.preview.connecting'),
			resourceDone: t('opsBoard.preview.connectionsDone'),
			reuse: { icons: ['share'], name: 'genomics-baseline', kind: t('opsBoard.preview.snapshotSchedule'), note: t('opsBoard.preview.snapshotNote'), working: t('opsBoard.preview.creating'), done: t('opsBoard.preview.snapshotCreated') },
		},
	]);

	const gpuAttachments: Attachment[] = $derived([
		{ icon: 'network', name: 'lab-vision-net', label: t('opsBoard.policy.network') },
		{ icon: 'share', name: 'dataset-shared', label: t('opsBoard.preview.sharedRead') },
	]);
	// The control plane shows its role; each worker shows the Pods scheduled onto it.
	const clusterNodes: Array<{ name: string; role?: string; pods: number }> = $derived([
		{ name: 'control-plane', role: t('opsBoard.preview.control'), pods: 0 },
		{ name: 'worker-1', pods: 4 },
		{ name: 'worker-2', pods: 4 },
		{ name: 'worker-3', pods: 4 },
	]);
	const shareMounts: Attachment[] = $derived([
		{ icon: 'server', name: 'vm-seq-01', label: 'VM' },
		{ icon: 'server', name: 'vm-seq-02', label: 'VM' },
		{ icon: 'server', name: 'notebook-07', label: t('opsBoard.preview.notebook') },
	]);

	// One step holds a full working-dot pulse plus the data transition of its objects.
	const STEP_MS = MOTION_DURATION_MS.statusPulse + MOTION_DURATION_MS.data;

	const scenarioOptions = $derived(scenarios.map(({ key, label }) => ({ value: key, label })));
	let selectedScenario = $state<ScenarioKey>('gpu');
	let activeScenario = $derived(
		scenarios.find((scenario) => scenario.key === selectedScenario) ?? scenarios[0]!,
	);

	const stages = $derived([t('opsBoard.preview.requestStage'), t('opsBoard.preview.policyStage'), t('opsBoard.preview.resourceStage'), t('opsBoard.preview.reuseStage')]);
	const panelKeys: PanelKey[] = ['request', 'policy', 'resource', 'reuse'];
	const descriptions = $derived([
		t('opsBoard.preview.requestDescription'),
		t('opsBoard.preview.policyDescription'),
		t('opsBoard.preview.resourceDescription'),
		t('opsBoard.preview.reuseDescription'),
	]);
	// Hint lines shown while a panel waits; its planned objects stay visible beside them.
	const waitingNotes = $derived({
		policy: t('opsBoard.preview.policyWaitingNote'),
		resource: t('opsBoard.preview.resourceWaitingNote'),
		reuse: t('opsBoard.preview.reuseWaitingNote'),
	});
	let board: HTMLElement;
	let mode = $state<'idle' | 'running' | 'paused' | 'complete'>('idle');
	let completed = $state(0);
	let previewRun = $state(0);
	let reducedMotion = $state(false);
	let mounted = false;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let observer: IntersectionObserver | undefined;
	let generation = 0;
	let currentStep = $derived(Math.min(completed, stages.length - 1));
	let panelStates = $derived(
		panelKeys.map((_, index): PanelState => {
			if (mode === 'idle') return index === 0 ? 'ready' : 'waiting';
			if (mode === 'complete') return 'done';
			return index < currentStep ? 'done' : index === currentStep ? 'active' : 'waiting';
		}),
	);

	function statusText(panel: PanelKey, state: PanelState) {
		const scenario = activeScenario;
		if (panel === 'request') return state === 'active' ? t('opsBoard.preview.applying') : state === 'done' ? t('opsBoard.preview.submitted') : t('opsBoard.preview.drafted');
		if (state === 'waiting') return panel === 'policy' ? t('opsBoard.preview.unchecked') : panel === 'resource' ? t('opsBoard.preview.uncreated') : t('opsBoard.preview.resultWaiting');
		if (panel === 'policy') return state === 'active' ? t('opsBoard.preview.checking') : scenario.policyDone;
		if (panel === 'resource') return state === 'active' ? scenario.resourceWorking : scenario.resourceDone;
		return state === 'active' ? scenario.reuse.working : scenario.reuse.done;
	}

	function cancelPending() {
		generation += 1;
		clearTimeout(timer);
		timer = undefined;
		observer?.disconnect();
		observer = undefined;
	}

	function finish() {
		cancelPending();
		completed = stages.length;
		mode = 'complete';
	}

	function scheduleStep() {
		const run = generation;
		timer = setTimeout(() => {
			if (!mounted || run !== generation || mode !== 'running') return;
			timer = undefined;
			if (document.hidden) {
				pause();
				return;
			}
			completed += 1;
			if (completed === stages.length) finish();
			else scheduleStep();
		}, STEP_MS);
	}

	function run() {
		if (!mounted || document.hidden || mode === 'running') return;
		cancelPending();
		if (mode === 'idle' || mode === 'complete') previewRun += 1;
		if (mode === 'complete') completed = 0;
		reducedMotion = prefersReducedMotion();
		if (reducedMotion) finish();
		else {
			mode = 'running';
			scheduleStep();
			if (typeof IntersectionObserver !== 'undefined') {
				const run = generation;
				observer = new IntersectionObserver((entries) => {
					if (!mounted || run !== generation || mode !== 'running') return;
					if (entries.some((entry) => entry.target === board && !entry.isIntersecting)) pause();
				});
				observer.observe(board);
			}
		}
	}

	function pause() {
		if (mode !== 'running') return;
		cancelPending();
		mode = 'paused';
	}

	// One persistent control keeps keyboard focus while its action changes; every activation toggles.
	function toggleRun() {
		if (mode === 'running') pause();
		else run();
	}

	function selectScenario(value: string) {
		if (value !== 'gpu' && value !== 'cluster' && value !== 'data') return;
		cancelPending();
		selectedScenario = value;
		completed = 0;
		mode = 'idle';
	}

	onMount(() => {
		mounted = true;
		const preference = typeof window.matchMedia === 'function' ? window.matchMedia(REDUCED_MOTION_QUERY) : undefined;
		reducedMotion = prefersReducedMotion();
		const changeMotion = () => {
			reducedMotion = prefersReducedMotion();
			if (reducedMotion && mode === 'running') finish();
		};
		const changeVisibility = () => {
			if (document.hidden) pause();
		};
		preference?.addEventListener('change', changeMotion);
		document.addEventListener('visibilitychange', changeVisibility);
		return () => {
			mounted = false;
			cancelPending();
			preference?.removeEventListener('change', changeMotion);
			document.removeEventListener('visibilitychange', changeVisibility);
		};
	});
</script>

{#snippet icon(name: IconName)}
	<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
		{#if name === 'server'}
			<rect x="3.5" y="4" width="17" height="7" rx="1.5" /><rect x="3.5" y="13" width="17" height="7" rx="1.5" /><path d="M7.5 7.5h2M7.5 16.5h2" />
		{:else if name === 'network'}
			<circle cx="12" cy="5" r="2" /><circle cx="5" cy="19" r="2" /><circle cx="19" cy="19" r="2" /><path d="M12 7v5M12 12l-5.6 5.4M12 12l5.6 5.4" />
		{:else if name === 'share'}
			<ellipse cx="12" cy="6" rx="7" ry="2.5" /><path d="M5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
		{:else if name === 'layer'}
			<path d="M12 3.5 3.5 8 12 12.5 20.5 8Z" /><path d="m3.5 12 8.5 4.5 8.5-4.5M3.5 16l8.5 4.5 8.5-4.5" />
		{:else if name === 'lock'}
			<rect x="5" y="11" width="14" height="9" rx="1.5" /><path d="M8 11V8a4 4 0 0 1 8 0v3" />
		{:else}
			<path d="M12 3 19.8 7.5v9L12 21l-7.8-4.5v-9Z" /><circle cx="12" cy="12" r="2.5" />
		{/if}
	</svg>
{/snippet}

{#snippet check()}
	<svg class="check" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
{/snippet}

{#snippet status(panel: PanelKey, state: PanelState)}
	<p class="status" data-tone={state === 'waiting' ? 'waiting' : state === 'active' ? 'working' : 'done'}><span class="dot" aria-hidden="true"></span>{statusText(panel, state)}</p>
{/snippet}

{#snippet rows(items: Row[], revealRow: boolean)}
	{#each items as item, index}
		<div class="row" class:enter={revealRow} style={`--i: ${index + 1}`}>
			<span class="check-slot" class:enter={!revealRow}>{@render check()}</span>
			<dt>{item.label}</dt>
			<dd class:mono={item.mono}>{item.value}</dd>
		</div>
	{/each}
{/snippet}

<!-- Every scenario's body shares one grid cell so a panel keeps the tallest scenario's height and
     switching scenarios never moves the page; only the selected body is visible, the rest are inert sizers. -->
{#snippet sized(body: Snippet<[Scenario, boolean]>)}
	<div class="stack">
		{#each scenarios as scenario (scenario.key)}
			{@const live = scenario.key === selectedScenario}
			<div class="body" class:sizer={!live} aria-hidden={live ? undefined : 'true'} inert={!live}>{@render body(scenario, live)}</div>
		{/each}
	</div>
{/snippet}

{#snippet requestBody(scenario: Scenario)}
	<dl class="rows">{@render rows(scenario.requestRows, false)}</dl>
{/snippet}

{#snippet policyBody(scenario: Scenario)}
	<div class="meters">
		{#each scenario.meters as meter}
			<UsageBar size="sm" label={meter.label} value={panelStates[1] === 'waiting' ? meter.used : meter.used + meter.request} max={meter.max} unit={meter.unit ?? ''} />
		{/each}
	</div>
	<div class="stack">
		<dl class="rows" aria-hidden={panelStates[1] === 'waiting' ? 'true' : undefined}>{@render rows(scenario.checks, true)}</dl>
		{#if panelStates[1] === 'waiting'}<p class="wait-note">{waitingNotes.policy}</p>{/if}
	</div>
{/snippet}

{#snippet tree(items: Attachment[], live: boolean)}
	<span class="stub link draw-y" style="--i: 1" aria-hidden="true"></span>
	<ul class="tree">
		{#each items as item, index}
			<li class="branch" class:last={index === items.length - 1} data-link={live ? item.name : undefined}>
				<span class="elbow" aria-hidden="true"><span class="link v draw-y" style={`--i: ${index + 1}`}></span><span class="link h draw-x" style={`--i: ${index + 2}`}></span></span>
				<div class="thing chip" style={`--i: ${index + 2}`}>
					{@render icon(item.icon)}
					<span class="chip-text"><span class="mono">{item.name}</span><span class="chip-label">{item.label}</span></span>
				</div>
			</li>
		{/each}
	</ul>
{/snippet}

{#snippet resourceBody(scenario: Scenario, live: boolean)}
	<div class="objects" data-resource={live ? scenario.key : undefined}>
		{#if scenario.key === 'gpu'}
			<div class="thing object" style="--i: 0">
				{@render icon('server')}
				<span class="object-text"><span class="mono">vision-train-01</span><span class="object-spec">GPU 1 · vCPU 16 · 64 GB</span></span>
			</div>
			{@render tree(gpuAttachments, live)}
		{:else if scenario.key === 'cluster'}
			<div class="thing object" style="--i: 0">
				{@render icon('node')}
				<span class="object-text"><span class="mono">course-dl-k8s</span><span class="object-spec">Kubernetes 1.30</span></span>
				<span class="object-count">{t('opsBoard.preview.podCount', { count: clusterNodes.reduce((total, node) => total + node.pods, 0) })}</span>
			</div>
			<ul class="nodes">
				{#each clusterNodes as node}
					<li class="thing node" style="--i: 0" data-node={live ? node.name : undefined}>
						<span class="mono">{node.name}</span>
						{#if node.role}
							<span class="node-role">{node.role}</span>
						{:else}
							<span class="sr-only">{t('opsBoard.preview.podCount', { count: node.pods })}</span>
							<span class="pods" aria-hidden="true">
								{#each Array.from({ length: node.pods }, (_, pod) => pod) as pod}<span class="pod-slot"><span class="pod" style={`--i: ${pod + 1}`} data-pod={live || undefined}></span></span>{/each}
							</span>
						{/if}
					</li>
				{/each}
			</ul>
		{:else}
			<div class="thing object" style="--i: 0">
				{@render icon('share')}
				<span class="object-text"><span class="mono">genomics-share</span><span class="object-spec">2 TB · NFS</span></span>
			</div>
			{@render tree(shareMounts, live)}
		{/if}
	</div>
{/snippet}

{#snippet reuseBody(scenario: Scenario, live: boolean)}
	<div class="thing result" style="--i: 0" data-result={live ? scenario.reuse.name : undefined}>
		<span class="result-icons">{#each scenario.reuse.icons as name}{@render icon(name)}{/each}</span>
		<span class="object-text"><span class="mono">{scenario.reuse.name}</span><span class="result-kind">{scenario.reuse.kind}</span></span>
	</div>
	<div class="stack">
		<p class="result-note enter" style="--i: 2" aria-hidden={panelStates[3] === 'waiting' ? 'true' : undefined}>{scenario.reuse.note}</p>
		{#if panelStates[3] === 'waiting'}<p class="wait-note">{waitingNotes.reuse}</p>{/if}
	</div>
{/snippet}

<section bind:this={board} class="ops-board" class:running={mode === 'running'} class:paused={mode === 'paused'} class:complete={mode === 'complete'} class:reduced={reducedMotion} data-scenario={selectedScenario} data-mode={mode} aria-labelledby="ops-board-title">
	<header class="board-header">
		<div><span class="board-kicker">{t('opsBoard.preview.kicker')}</span><h2 id="ops-board-title">{t('opsBoard.preview.title')}</h2></div>
		<p class="disclaimer">{t('opsBoard.preview.disclaimer')}</p>
	</header>
	<ToggleGroup value={selectedScenario} options={scenarioOptions} onchange={selectScenario} size="sm" fullWidth class="scenario-switcher" ariaLabel={t('opsBoard.scenarioAriaLabel')} />

	<div class="request-summary">
		<div>
			<div class="request-meta"><span>{t('opsBoard.preview.exampleRequest', { time: activeScenario.requestedAt })}</span><span>{activeScenario.project}</span></div>
			<h3>{activeScenario.request}</h3>
		</div>
		<Button variant={mode === 'running' ? 'secondary' : 'accent'} size="md" class="board-action" onclick={toggleRun}>
			{mode === 'running' ? t('opsBoard.preview.pause') : mode === 'complete' ? t('opsBoard.preview.replay') : mode === 'paused' ? t('opsBoard.preview.resume') : t('opsBoard.preview.start')}
		</Button>
	</div>

	{#key `${selectedScenario}:${previewRun}`}
		<div class="scene">
			<div class="scene-bar" aria-hidden="true"><span class="scene-route">{activeScenario.route}</span><span class="scene-tag">{t('landing.product.exampleScreen')}</span></div>
			<div class="panels">
				<section class="panel" data-panel="request" data-state={panelStates[0]} aria-labelledby="ops-panel-request">
					<header class="panel-head"><h4 id="ops-panel-request">{t('opsBoard.preview.requestPanel')}</h4>{@render status('request', panelStates[0])}</header>
					{@render sized(requestBody)}
				</section>

				<section class="panel" data-panel="policy" data-state={panelStates[1]} aria-labelledby="ops-panel-policy">
					<header class="panel-head"><h4 id="ops-panel-policy">{t('opsBoard.preview.policyStage')}</h4>{@render status('policy', panelStates[1])}</header>
					{@render sized(policyBody)}
				</section>

				<section class="panel" data-panel="resource" data-state={panelStates[2]} aria-labelledby="ops-panel-resource">
					<header class="panel-head"><h4 id="ops-panel-resource">{t('opsBoard.preview.resourceStage')}</h4>{@render status('resource', panelStates[2])}</header>
					{@render sized(resourceBody)}
					<p class="wait-note" class:spent={panelStates[2] !== 'waiting'} aria-hidden={panelStates[2] === 'waiting' ? undefined : 'true'}>{waitingNotes.resource}</p>
				</section>

				<section class="panel" data-panel="reuse" data-state={panelStates[3]} aria-labelledby="ops-panel-reuse">
					<header class="panel-head"><h4 id="ops-panel-reuse">{t('opsBoard.preview.reuseStage')}</h4>{@render status('reuse', panelStates[3])}</header>
					{@render sized(reuseBody)}
				</section>
			</div>
		</div>
	{/key}

	<div class="progress-summary" role="status" aria-live="polite" aria-atomic="true">
		<strong>{mode === 'idle' ? t('opsBoard.preview.idleTitle') : mode === 'complete' ? t('opsBoard.preview.completeTitle') : t(mode === 'paused' ? 'opsBoard.preview.pausedTitle' : 'opsBoard.preview.workingTitle', { number: currentStep + 1, stage: stages[currentStep] })}</strong>
		<span>{t('opsBoard.preview.completedCount', { completed, total: stages.length })}</span>
		<p>{mode === 'idle' ? (reducedMotion ? t('opsBoard.preview.reducedHint') : t('opsBoard.preview.idleHint')) : mode === 'complete' ? t('opsBoard.preview.completeHint') : mode === 'paused' ? t('opsBoard.preview.pausedHint') : descriptions[currentStep]}</p>
	</div>
	<progress aria-label={t('opsBoard.preview.progressAriaLabel')} max={stages.length} value={completed}></progress>
	<ol class="stages" aria-label={t('opsBoard.preview.stagesAriaLabel')}>
		{#each stages as stage, index}
			<li class:done={completed > index} aria-current={mode !== 'idle' && mode !== 'complete' && currentStep === index ? 'step' : undefined}>
				<span class="stage-mark" aria-hidden="true">{#if completed > index}{@render check()}{:else}0{index + 1}{/if}</span>{stage}
			</li>
		{/each}
	</ol>
</section>

<style>
	.ops-board { min-width: 0; overflow-wrap: anywhere; padding-bottom: 0.625rem; border: 1px solid var(--color-line-2); border-radius: var(--radius-xl); background: var(--color-surface-base); color: var(--color-ink-0); }
	.board-header { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 0.25rem 1rem; padding: 0.625rem 1rem 0.5rem; }
	.board-kicker { display: block; font-size: 0.75rem; font-weight: 600; line-height: 1.5; color: var(--color-warm-text); }
	.board-header h2 { margin: 0; font-size: 1rem; line-height: 1.5; }
	.disclaimer { margin: 0; color: var(--color-ink-2); font-size: 0.75rem; }
	.ops-board :global(.scenario-switcher) { margin-inline: 1rem; width: calc(100% - 2rem); }
	.ops-board :global(.scenario-switcher .toggle-option) { min-width: 0; min-height: 2.75rem; padding-inline: 0.25rem; white-space: normal; overflow-wrap: anywhere; text-wrap: balance; }
	.request-summary { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 0.5rem 0.75rem; padding: 0.5rem 1rem 0; }
	.request-summary > div { flex: 1 1 11rem; min-width: 0; }
	.request-meta { display: flex; flex-wrap: wrap; gap: 0.25rem 0.75rem; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.5; font-variant-numeric: tabular-nums; }
	.request-summary h3 { margin: 0.125rem 0 0; font-size: 1.25rem; font-weight: 600; line-height: 1.4; text-wrap: balance; }
	.ops-board :global(.board-action) { min-height: 2.75rem; }

	/* Scene window (shared landing vocabulary). */
	.scene { margin: 0.5rem 1rem 0; border: 1px solid var(--color-line-2); border-radius: var(--radius-lg); background: var(--color-surface-canvas); overflow: hidden; container-type: inline-size; }
	.scene-bar { display: flex; align-items: baseline; justify-content: space-between; gap: 0.75rem; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--color-line); font-size: 0.75rem; line-height: 1.5; color: var(--color-ink-2); }
	.scene-route { min-width: 0; font-family: var(--font-mono); overflow-wrap: anywhere; }
	.scene-tag { flex-shrink: 0; font-family: var(--font-sans); }
	.panels { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.5rem; padding: 0.375rem; }
	@container (min-width: 26rem) {
		.panels { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	}

	.panel { display: flex; flex-direction: column; gap: 0.5rem; min-width: 0; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-raised); }
	.panel[data-state='waiting'] { border-style: dashed; border-color: var(--color-line-2); background: var(--color-surface-base); }
	.panel[data-state='active'] { border-color: var(--color-accent); box-shadow: 0 0 0 3px var(--accent-soft); }
	.panel-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.25rem 0.5rem; }
	h4 { margin: 0; font-size: 0.8125rem; font-weight: 600; line-height: 1.4; color: var(--color-ink-0); }
	.status { display: inline-flex; align-items: center; gap: 0.375rem; margin: 0; font-size: 0.75rem; font-weight: 500; line-height: 1.4; }
	.dot { flex-shrink: 0; width: 0.375rem; height: 0.375rem; border-radius: 50%; }
	.status[data-tone='waiting'] { color: var(--color-ink-2); }
	.status[data-tone='waiting'] .dot { background: var(--color-line-2); }
	.status[data-tone='working'] { color: var(--color-ink-1); }
	.status[data-tone='working'] .dot { background: var(--color-accent); animation: ops-pulse var(--motion-duration-status-pulse) var(--motion-ease-in-out) infinite; }
	.paused .status[data-tone='working'] .dot { animation-play-state: paused; }
	.status[data-tone='done'] { color: var(--color-state-success-text); }
	.status[data-tone='done'] .dot { background: var(--color-state-success); }

	.icon { flex-shrink: 0; width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
	.check { flex-shrink: 0; width: 0.875rem; height: 0.875rem; fill: none; stroke: var(--color-state-success); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
	.mono { min-width: 0; font-family: var(--font-mono); font-size: 0.75rem; font-weight: 500; line-height: 1.5; color: var(--color-ink-1); overflow-wrap: anywhere; }

	dl { display: grid; gap: 0.375rem; margin: 0; }
	.row { display: grid; grid-template-columns: 0.875rem minmax(0, auto) minmax(0, 1fr); align-items: center; column-gap: 0.375rem; }
	.check-slot { display: flex; }
	dt { font-size: 0.75rem; line-height: 1.5; color: var(--color-ink-2); }
	dd { min-width: 0; margin: 0; font-size: 0.75rem; font-weight: 600; line-height: 1.5; color: var(--color-ink-0); font-variant-numeric: tabular-nums; text-align: right; overflow-wrap: anywhere; }
	dd.mono { font-weight: 500; color: var(--color-ink-1); }
	.meters { display: grid; gap: 0.375rem; margin-bottom: 0.5rem; }

	.stack { display: grid; min-width: 0; }
	.stack > * { grid-area: 1 / 1; min-width: 0; }
	.body { display: flex; flex-direction: column; min-width: 0; }
	.sizer { visibility: hidden; }
	.sizer *, .sizer .thing::before, .sizer .thing::after { animation: none !important; }
	.wait-note { margin: 0; font-size: 0.75rem; line-height: 1.5; color: var(--color-ink-2); }
	.wait-note.spent { visibility: hidden; }
	.objects { display: flex; flex-direction: column; min-width: 0; }

	/* Planned objects: dashed outline (::after) and muted text until their panel is reached. The solid
	   frame and surface (::before) fade in above the outline, so the object itself never fades. */
	.thing { position: relative; isolation: isolate; display: flex; align-items: center; gap: 0.5rem; min-width: 0; border: 1px solid transparent; border-radius: var(--radius-md); color: var(--color-ink-2); }
	.thing::before, .thing::after { content: ''; position: absolute; inset: -1px; border-radius: inherit; }
	.thing::after { z-index: -2; border: 1px dashed var(--color-line-2); }
	.thing::before { z-index: -1; border: 1px solid var(--color-line); background: var(--color-surface-base); opacity: 0; }
	.panel[data-state='waiting'] .thing :is(.mono, .object-spec, .object-count) { color: var(--color-ink-2); }
	.panel:is([data-state='active'], [data-state='done']) .thing { color: var(--color-ink-1); }
	.panel:is([data-state='active'], [data-state='done']) .thing::before { opacity: 1; animation: ops-fade var(--motion-duration-panel) var(--motion-ease-out) calc(var(--motion-duration-base) * var(--i, 0)) both; }
	.panel:is([data-state='active'], [data-state='done']) .thing::after { opacity: 0; animation: ops-unplan var(--motion-duration-panel) var(--motion-ease-out) calc(var(--motion-duration-base) * var(--i, 0)) both; }
	.panel:is([data-state='active'], [data-state='done']) .result::before { animation-name: ops-slide; }
	.object { padding: 0.375rem 0.625rem; }
	.object-text { display: grid; flex: 1 1 auto; min-width: 0; }
	.object-spec { font-size: 0.75rem; font-weight: 600; line-height: 1.5; color: var(--color-ink-0); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
	.object-count { flex-shrink: 0; align-self: flex-start; font-size: 0.75rem; font-weight: 600; line-height: 1.5; color: var(--color-ink-0); font-variant-numeric: tabular-nums; }

	/* Connector tree: a 1rem drop below the source object, then a 1.5rem elbow into each attachment. */
	.link { display: block; background: var(--color-line-2); }
	.panel[data-state='done'] .link { background: var(--color-accent); }
	.stub { width: 2px; height: 0.875rem; margin-left: 1.125rem; transform-origin: top; }
	.tree { display: grid; margin: 0; padding: 0 0 0 1.125rem; list-style: none; }
	.branch { display: grid; grid-template-columns: 1.5rem minmax(0, 1fr); min-width: 0; }
	.elbow { position: relative; }
	.elbow .v { position: absolute; top: 0; bottom: 0; left: 0; width: 2px; transform-origin: top; }
	.branch.last .elbow .v { bottom: auto; height: calc(50% + 1px); }
	.elbow .h { position: absolute; top: calc(50% - 1px); left: 0; width: calc(100% - 0.375rem); height: 2px; transform-origin: left; }
	.elbow .h::after { content: ''; position: absolute; top: 50%; left: 100%; width: 0.375rem; height: 0.5rem; margin-top: -0.25rem; background: inherit; clip-path: polygon(0 0, 100% 50%, 0 100%); }
	.chip { min-height: 1.75rem; margin-block: 0.125rem; padding: 0.125rem 0.5rem; }
	.chip-text { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 0.5rem; min-width: 0; }
	.chip-label, .result-kind { font-size: 0.75rem; line-height: 1.5; }

	/* Node rows form one bordered list: neighbours share a border instead of a gap. */
	.nodes { display: grid; margin: 0.375rem 0 0; padding: 0; list-style: none; }
	.node { justify-content: space-between; min-height: 1.75rem; padding: 0.125rem 0.5rem; border-radius: 0; }
	.node + .node { margin-top: -1px; }
	.node:first-child { border-radius: var(--radius-md) var(--radius-md) 0 0; }
	.node:last-child { border-radius: 0 0 var(--radius-md) var(--radius-md); }
	.node-role { font-size: 0.75rem; line-height: 1.5; }
	.pods { display: flex; gap: 0.25rem; }
	.pod-slot { position: relative; width: 0.625rem; height: 0.625rem; border: 1px dashed var(--color-line-2); border-radius: 2px; }
	.pod { position: absolute; inset: -1px; border-radius: 2px; background: var(--color-accent); }

	.result { flex-wrap: wrap; row-gap: 0.25rem; padding: 0.375rem 0.625rem; }
	.result-icons { display: inline-flex; gap: 0.25rem; }
	.result-note { margin: 0.5rem 0 0; font-size: 0.75rem; line-height: 1.5; color: var(--color-ink-1); }

	/* Connectors, Pods and check marks of a panel that has not been reached are not drawn yet. */
	.panel:is([data-state='ready'], [data-state='waiting']) :is(.enter, .pod, .draw-x, .draw-y) { visibility: hidden; }
	.panel:is([data-state='active'], [data-state='done']) .enter { animation: ops-enter var(--motion-duration-panel) var(--motion-ease-out) calc(var(--motion-duration-base) * var(--i, 0)) both; }
	.panel:is([data-state='active'], [data-state='done']) .pod { animation: ops-pod var(--motion-duration-panel) var(--motion-ease-out) calc(var(--motion-duration-base) * var(--i, 0)) both; }
	.panel:is([data-state='active'], [data-state='done']) .draw-x { animation: ops-draw-x var(--motion-duration-data) var(--motion-ease-out) calc(var(--motion-duration-base) * var(--i, 0)) both; }
	.panel:is([data-state='active'], [data-state='done']) .draw-y { animation: ops-draw-y var(--motion-duration-data) var(--motion-ease-out) calc(var(--motion-duration-base) * var(--i, 0)) both; }
	.reduced :is(.enter, .pod, .draw-x, .draw-y, .dot), .reduced .thing::before, .reduced .thing::after { animation: none !important; }

	.progress-summary { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0 0.75rem; margin: 0.5rem 1rem 0.375rem; font-size: 0.8125rem; line-height: 1.5; }
	.progress-summary span { color: var(--color-ink-2); font-variant-numeric: tabular-nums; }
	.progress-summary p { grid-column: 1 / -1; margin: 0; color: var(--color-ink-1); font-size: 0.8125rem; line-height: 1.5; }
	progress { display: block; appearance: none; width: calc(100% - 2rem); height: 0.25rem; margin-inline: 1rem; border: 0; border-radius: var(--radius-sm); overflow: hidden; background: var(--color-surface-sunken); }
	progress::-webkit-progress-bar { background: var(--color-surface-sunken); }
	progress::-webkit-progress-value { background: var(--color-warm); }
	progress::-moz-progress-bar { background: var(--color-warm); }
	.stages { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.5rem; list-style: none; padding: 0; margin: 0.375rem 1rem 0; }
	.stages li { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 0 0.375rem; min-width: 0; font-size: 0.75rem; line-height: 1.5; color: var(--color-ink-2); word-break: keep-all; overflow-wrap: anywhere; }
	.stage-mark { display: inline-flex; align-items: center; min-width: 0.875rem; height: 1.125rem; font-family: var(--font-mono); }
	.stages li[aria-current], .stages li.done { color: var(--color-warm-text); }
	.stages li[aria-current] { font-weight: 600; }

	@keyframes ops-enter { from { opacity: 0; transform: translateY(0.5rem); } }
	@keyframes ops-fade { from { opacity: 0; } }
	@keyframes ops-unplan { from { opacity: 1; } }
	@keyframes ops-slide { from { opacity: 0; transform: translateX(-0.5rem); } }
	@keyframes ops-pod { from { opacity: 0; transform: scale(0.5); } }
	@keyframes ops-draw-x { from { transform: scaleX(0); } }
	@keyframes ops-draw-y { from { transform: scaleY(0); } }
	@keyframes ops-pulse { 50% { opacity: 0.35; } }
	@media (prefers-reduced-motion: reduce) {
		.ops-board :global(*), .ops-board :global(*::before), .ops-board :global(*::after) { animation: none !important; transition: none !important; }
	}
</style>
