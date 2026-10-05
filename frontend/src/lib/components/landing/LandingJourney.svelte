<script lang="ts">
	import { onMount } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import UsageBar from '$lib/components/ui/UsageBar.svelte';
	import { MOTION_DURATION_MS, REDUCED_MOTION_QUERY } from '$lib/design/tokens';
	import { prefersReducedMotion } from '$lib/utils/motion';
	import { t } from '$lib/i18n/ns/public-entry';

	const steps = $derived([
		{
			key: 'request', label: t('landing.journey.request.label'), title: t('landing.journey.request.title'),
			body: t('landing.journey.request.body'),
			items: [t('landing.journey.request.item1'), t('landing.journey.request.item2'), t('landing.journey.request.item3')],
			caption: t('landing.journey.request.caption'),
			artifact: t('landing.journey.request.artifact')
		},
		{
			key: 'allocate', label: t('landing.journey.allocate.label'), title: t('landing.journey.allocate.title'),
			body: t('landing.journey.allocate.body'),
			items: [t('landing.journey.allocate.item1'), t('landing.journey.allocate.item2'), t('landing.journey.allocate.item3')],
			caption: t('landing.journey.allocate.caption'),
			artifact: t('landing.journey.allocate.artifact')
		},
		{
			key: 'observe', label: t('landing.journey.observe.label'), title: t('landing.journey.observe.title'),
			body: t('landing.journey.observe.body'),
			items: [t('landing.journey.observe.item1'), t('landing.journey.observe.item2'), t('landing.journey.observe.item3')],
			caption: t('landing.journey.observe.caption'),
			artifact: t('landing.journey.observe.artifact')
		},
		{
			key: 'reuse', label: t('landing.journey.reuse.label'), title: t('landing.journey.reuse.title'),
			body: t('landing.journey.reuse.body'),
			items: [t('landing.journey.reuse.item1'), t('landing.journey.reuse.item2'), t('landing.journey.reuse.item3')],
			caption: t('landing.journey.reuse.caption'),
			artifact: t('landing.journey.reuse.artifact')
		}
	]);

	const members = $derived([
		{ initial: t('landing.journey.member.instructorInitial'), name: t('landing.journey.member.instructor'), role: t('landing.journey.member.manage') },
		{ initial: t('landing.journey.member.researcherInitial'), name: t('landing.journey.member.researcher'), role: t('landing.journey.member.use') },
		{ initial: t('landing.journey.member.studentInitial'), name: t('landing.journey.member.student'), role: t('landing.journey.member.view') }
	]);
	const links = $derived([
		{ icon: 'network', name: 'lab-net', kind: t('landing.journey.scene.network') },
		{ icon: 'share', name: 'shared-dataset', kind: t('landing.journey.scene.sharedDataRead') }
	] as const);
	const requestRows = $derived([
		{ label: t('landing.journey.scene.image'), value: 'PyTorch 2.4' },
		{ label: t('landing.journey.scene.size'), value: 'GPU 1 · vCPU 16' },
		{ label: t('landing.journey.scene.network'), value: 'lab-net', ident: true },
		{ label: t('landing.journey.scene.data'), value: t('landing.journey.scene.sharedRead') }
	]);
	const vmRows = $derived(requestRows.slice(0, 2));
	const requestItems = $derived([t('landing.journey.scene.image'), t('landing.journey.scene.computeSize'), t('landing.journey.scene.network'), t('landing.journey.scene.dataAccess')]);
	// The request (GPU 1 · vCPU 16 · 64 GB) is added to what the project already uses.
	const quotas = $derived([
		{ label: 'GPU', used: 0, request: 1, max: 2, unit: '' },
		{ label: 'vCPU', used: 8, request: 16, max: 64, unit: '' },
		{ label: t('landing.journey.scene.memory'), used: 32, request: 64, max: 256, unit: ' GB' }
	]);
	const activity = $derived([
		{ time: '09:41', text: t('landing.journey.scene.activityVmRequest') },
		{ time: '09:42', text: t('landing.journey.scene.activityNetwork') },
		{ time: '10:05', text: t('landing.journey.scene.activityQuota') }
	]);
	const environments = $derived([t('landing.journey.scene.newEnvironment', { name: 'A' }), t('landing.journey.scene.newEnvironment', { name: 'B' })]);

	const uid = $props.id();
	let root: HTMLElement;
	let articleList: HTMLDivElement;
	let active = $state(0);
	let motionEnabled = $state(false);
	let quotaApplied = $state(false);
	let selectionHeld = false;
	let scrollToStage: ((index: number) => void) | undefined;
	const connected = $derived(active > 0);

	function selectStage(index: number) {
		selectionHeld = true;
		active = index;
		if (motionEnabled) scrollToStage?.(index);
	}

	// The meters take the requested share once the 배정 detail has entered, so the fill is seen.
	$effect(() => {
		if (active !== 1) {
			quotaApplied = false;
			return;
		}
		if (prefersReducedMotion()) {
			quotaApplied = true;
			return;
		}
		const timer = window.setTimeout(() => { quotaApplied = true; }, MOTION_DURATION_MS.fast + MOTION_DURATION_MS.panel + MOTION_DURATION_MS.base * 3);
		return () => window.clearTimeout(timer);
	});

	onMount(() => {
		if (typeof window.matchMedia !== 'function') return;
		let frame = 0;
		let listening = false;
		const roomy = window.matchMedia('(min-width: 1024px) and (min-height: 700px)');
		const reduced = window.matchMedia(REDUCED_MOTION_QUERY);
		const articles = Array.from(articleList.querySelectorAll<HTMLElement>('article'));
		// Resolve the inherited CSS length (including calc/rem), not just a numeric prefix.
		const offsetProbe = document.createElement('span');
		offsetProbe.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none;height:var(--landing-nav-height, 0px);width:0';
		root.append(offsetProbe);
		const headerOffset = () => offsetProbe.getBoundingClientRect().height;

		function activateFromGeometry() {
			if (selectionHeld || !motionEnabled) return;
			const line = headerOffset() + (window.innerHeight - headerOffset()) * 0.32;
			let next = 0;
			for (let index = 0; index < articles.length; index++) {
				if (articles[index].getBoundingClientRect().top <= line) next = index;
			}
			active = next;
		}

		function scheduleActivation() {
			if (frame) return;
			frame = window.requestAnimationFrame(() => {
				frame = 0;
				activateFromGeometry();
			});
		}

		function cancelActivation() {
			window.cancelAnimationFrame(frame);
			frame = 0;
		}

		function listen(enabled: boolean) {
			if (enabled === listening) return;
			listening = enabled;
			if (enabled) {
				window.addEventListener('scroll', scheduleActivation, { passive: true });
				window.addEventListener('resize', scheduleActivation, { passive: true });
			} else {
				window.removeEventListener('scroll', scheduleActivation);
				window.removeEventListener('resize', scheduleActivation);
			}
		}

		function configure() {
			const enabled = roomy.matches && !reduced.matches;
			motionEnabled = enabled;
			listen(enabled);
			// The frame runs after the roomy layout is applied, so the articles are measured in place.
			if (enabled) scheduleActivation();
			else cancelActivation();
		}

		function resumeReading() { selectionHeld = false; }
		function onKey(event: KeyboardEvent) {
			if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End'].includes(event.key)
				|| (event.key === ' ' && (event.target === document.body || event.target === document.documentElement))) resumeReading();
		}
		function onPointer(event: PointerEvent) {
			if (event.target === document.documentElement) resumeReading();
		}
		scrollToStage = (index) => {
			const top = window.scrollY + articles[index].getBoundingClientRect().top - headerOffset() - 24;
			window.scrollTo({ top: Math.max(0, top), behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
		};
		roomy.addEventListener('change', configure);
		reduced.addEventListener('change', configure);
		window.addEventListener('wheel', resumeReading, { passive: true });
		window.addEventListener('touchmove', resumeReading, { passive: true });
		window.addEventListener('keydown', onKey);
		window.addEventListener('pointerdown', onPointer);
		configure();

		return () => {
			listen(false);
			cancelActivation();
			scrollToStage = undefined;
			offsetProbe.remove();
			roomy.removeEventListener('change', configure);
			reduced.removeEventListener('change', configure);
			window.removeEventListener('wheel', resumeReading);
			window.removeEventListener('touchmove', resumeReading);
			window.removeEventListener('keydown', onKey);
			window.removeEventListener('pointerdown', onPointer);
		};
	});
</script>

{#snippet icon(name: 'server' | 'network' | 'share' | 'layer' | 'lock' | 'check')}
	<svg class="icon" class:check-icon={name === 'check'} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
		{#if name === 'server'}
			<rect x="2.5" y="2.5" width="11" height="4.5" rx="1" /><rect x="2.5" y="9" width="11" height="4.5" rx="1" /><path d="M5 4.75h.01M5 11.25h.01" />
		{:else if name === 'network'}
			<circle cx="8" cy="3.5" r="1.75" /><circle cx="3.5" cy="12.5" r="1.75" /><circle cx="12.5" cy="12.5" r="1.75" /><path d="M7.1 5L4.4 11M8.9 5l2.7 6M5.25 12.5h5.5" />
		{:else if name === 'share'}
			<ellipse cx="8" cy="3.75" rx="5" ry="1.75" /><path d="M3 3.75v8.5c0 1 2.25 1.75 5 1.75s5-.75 5-1.75v-8.5M3 8c0 1 2.25 1.75 5 1.75S13 9 13 8" />
		{:else if name === 'layer'}
			<path d="M8 2l6 3-6 3-6-3zM2 8l6 3 6-3M2 11l6 3 6-3" />
		{:else if name === 'lock'}
			<rect x="3" y="7" width="10" height="7" rx="1.25" /><path d="M5.25 7V5a2.75 2.75 0 0 1 5.5 0v2" />
		{:else}
			<path d="M3 8.5l3.25 3.25L13 4.75" />
		{/if}
	</svg>
{/snippet}

<div bind:this={root} class="journey" class:motion-enabled={motionEnabled} data-stage={active}>
	<div class="journey-layout">
		<div class="visual-rail">
			<figure class="scene-frame">
				<div class="scene-header"><span>{t('landing.journey.heading')}</span><span class="example-label">{t('landing.journey.example')}</span></div>
				<div class="stage-choices" role="group" aria-label={t('landing.journey.stageSelection')}>
					{#each steps as step, index}
						<Button variant="outline" ariaPressed={active === index} onclick={() => selectStage(index)} class="stage-choice">
							{step.label}
						</Button>
					{/each}
				</div>

				<div class="scene-window" aria-hidden="true">
					<div class="scene-bar"><span class="scene-route">afterglow / projects / lab-vision</span><span>{t('landing.journey.scene.exampleScreen')}</span></div>
					<div class="scene-body">
						<div class="boundary">
							<p class="boundary-label">{t('landing.journey.scene.project', { name: 'lab-vision' })}</p>
							<div class="scene-grid">
								<div class="panel members">
									<ul class="member-list">
										{#each members as member}
											<li class="member"><span class="avatar">{member.initial}</span><span class="member-role"><b>{member.name}</b> · {member.role}</span></li>
										{/each}
									</ul>
								</div>

								<div class="panel core" data-state="done">
									<span class="conn conn-member drawn"></span>
									<div class="core-variant" class:on={active === 0}>
										<div class="card-head">{@render icon('server')}<span class="panel-title">{t('landing.journey.scene.environmentRequest')}</span></div>
										<span class="status" data-tone="done"><span class="dot"></span>{t('landing.journey.scene.submitted')}</span>
										<dl class="rows">
											{#each requestRows as row}
												<div><dt>{row.label}</dt><dd class:ident={row.ident}>{row.value}</dd></div>
											{/each}
										</dl>
									</div>
									{#each [1, 2, 3] as stage}
										<div class="core-variant" class:on={active === stage}>
											<div class="card-head">{@render icon('server')}<span class="ident panel-ident">vision-train-01</span><span class="kind">VM</span></div>
											<span class="status" data-tone="done"><span class="dot"></span>{stage === 3 ? t('landing.journey.scene.layerSaved') : t('landing.journey.scene.running')}</span>
											<dl class="rows">
												{#each vmRows as row}
													<div><dt>{row.label}</dt><dd>{row.value}</dd></div>
												{/each}
												{#if stage === 2}
													<div><dt>{t('landing.journey.scene.metrics')}</dt><dd>{t('landing.journey.scene.metricValues')}</dd></div>
												{:else if stage === 3}
													<div><dt>{t('landing.journey.scene.layer')}</dt><dd>{t('landing.journey.scene.layerVersion', { version: 'v1' })}</dd></div>
												{/if}
											</dl>
										</div>
									{/each}
								</div>

								<div class="links">
									<span class="conn conn-links" class:drawn={connected}></span>
									<ul class="link-list">
										{#each links as link}
											<li class="panel link" data-state={connected ? 'done' : 'waiting'}>
												<span class="conn conn-link" class:drawn={connected}></span>
												<span class="ident">{link.name}</span>
												<span class="link-kind">{@render icon(link.icon)}<span>{link.kind}</span></span>
												<span class="status" data-tone={connected ? 'done' : 'waiting'}><span class="dot"></span>{connected ? t('landing.journey.scene.connected') : t('landing.journey.scene.notConnected')}</span>
											</li>
										{/each}
									</ul>
								</div>

								<div class="details">
									<div class="panel detail" class:on={active === 0}>
										<p class="panel-title enter" style="--i: 0">{t('landing.journey.scene.requestItems')}</p>
										<ul class="chips">
											{#each requestItems as item, index}
												<li class="chip enter" style="--i: {index + 1}">{@render icon('check')}{item}</li>
											{/each}
										</ul>
									</div>

									<div class="panel detail allocate" class:on={active === 1}>
										<p class="panel-title enter" style="--i: 0">{t('landing.journey.scene.createAfterPolicy')}</p>
										<div class="quota-list">
											{#each quotas as quota, index}
												<div class="enter" style="--i: {index + 1}">
													<UsageBar size="sm" label={quota.label} value={quotaApplied ? quota.used + quota.request : quota.used} max={quota.max} unit={quota.unit} />
												</div>
											{/each}
										</div>
										<p class="detail-note enter" style="--i: 4">{t('landing.journey.scene.policyNote')}</p>
									</div>

									<div class="panel detail" class:on={active === 2}>
										<div class="observe">
											<div class="observe-column">
												<p class="panel-title enter" style="--i: 0">{t('landing.journey.scene.usageExample')}</p>
												<div class="spark enter" style="--i: 1">
													<svg viewBox="0 0 120 40" preserveAspectRatio="none" focusable="false">
														<polyline points="0,32 12,28 24,30 36,22 48,24 60,15 72,18 84,11 96,14 108,9 120,12" vector-effect="non-scaling-stroke" />
													</svg>
													<span class="spark-cover"></span>
												</div>
											</div>
											<div class="observe-column">
												<p class="panel-title enter" style="--i: 0">{t('landing.journey.scene.activityExample')}</p>
												<ul class="activity">
													{#each activity as entry, index}
														<li class="enter" style="--i: {index + 1}"><span class="ident">{entry.time}</span><span>{entry.text}</span></li>
													{/each}
												</ul>
											</div>
										</div>
									</div>

									<div class="panel detail" class:on={active === 3}>
										<div class="branch">
											<div class="panel layer-card enter" style="--i: 0">
												<span class="layer-icons">{@render icon('lock')}{@render icon('layer')}</span>
												<span class="panel-title">{t('landing.journey.scene.immutableLayer', { version: 'v1' })}</span>
											</div>
											{#each environments as environment, index}
												<div class="panel environment enter" style="--i: {index + 1}">
													<span class="conn conn-branch"></span>
													<span class="environment-name">{environment}</span>
													<span class="chip">{t('landing.journey.scene.separateChanges')}</span>
												</div>
											{/each}
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>

				<figcaption>
					<p class="caption-stage">{steps[active].label}<span class="caption-separator" aria-hidden="true">/</span>{steps[active].artifact}</p>
					<p class="caption-copy">{steps[active].caption}</p>
					<p class="illustration-note">{t('landing.journey.illustrationNote')}</p>
				</figcaption>
			</figure>
		</div>

		<div bind:this={articleList} class="step-articles">
			{#each steps as step, index}
				<article id="{uid}-{step.key}" aria-labelledby="{uid}-{step.key}-title" data-active={active === index}>
					<div class="step-label"><span class="step-mark" aria-hidden="true"></span>{step.label}</div>
					<h3 id="{uid}-{step.key}-title">{step.title}</h3>
					<p>{step.body}</p>
					<ul>{#each step.items as item}<li>{item}</li>{/each}</ul>
				</article>
			{/each}
		</div>
	</div>
</div>

<style>
	.journey { min-width: 0; color: var(--color-ink-0); overflow-wrap: anywhere; word-break: var(--landing-word-break, keep-all); }
	.journey:lang(ja), .journey:lang(zh-CN) { --landing-word-break: normal; }
	h3 { font-family: var(--font-display); font-weight: 500; letter-spacing: -0.035em; word-break: var(--landing-word-break, keep-all); overflow-wrap: anywhere; }
	.journey-layout { display: grid; gap: 2rem; min-width: 0; }
	.visual-rail, .step-articles { min-width: 0; }

	.scene-frame { display: grid; gap: 0.5rem; min-width: 0; margin: 0; }
	.scene-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 0.5rem; color: var(--color-ink-1); font-size: 0.75rem; font-weight: 500; line-height: 1.4; }
	.example-label { color: var(--color-ink-2); }
	.stage-choices { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.25rem; }
	.stage-choices :global(.stage-choice) { width: 100%; min-width: 44px; min-height: 44px; height: auto; padding-inline: 0.25rem; white-space: normal; overflow-wrap: anywhere; border-color: var(--color-line-2); }
	.stage-choices :global(.stage-choice[aria-pressed='true']) { background: var(--color-surface-selected); color: var(--color-ink-0); border-color: var(--color-ink-1); font-weight: 600; box-shadow: inset 0 -3px 0 var(--color-accent); }

	/* Scene window (D1). Text is HTML at 0.75rem or larger; SVG carries only icons and lines. */
	.scene-window { min-width: 0; word-break: var(--landing-word-break, keep-all); border: 1px solid var(--color-line-2); border-radius: var(--radius-lg); background: var(--color-surface-canvas); overflow: hidden; container-type: inline-size; }
	.scene-bar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 0.75rem; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--color-line); color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.4; }
	.scene-bar > span:last-child { min-width: 0; }
	.scene-route { min-width: 0; font-family: var(--font-mono); overflow-wrap: anywhere; }
	.scene-body { padding: 0.75rem; }
	/* The label sits on the dashed boundary line, like a fieldset legend, so it costs no row. */
	.boundary { position: relative; min-width: 0; padding: 1rem 0.75rem 0.75rem; border: 1px dashed var(--color-line-2); border-radius: var(--radius-md); }
	.boundary-label { position: absolute; top: 0; left: 0.5rem; max-width: calc(100% - 1rem); margin: 0; padding-inline: 0.375rem; background: var(--color-surface-canvas); color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.75rem; line-height: 1.4; transform: translateY(-50%); }
	.scene-grid { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-areas: 'members' 'core' 'links' 'detail'; row-gap: 1rem; min-width: 0; }
	ul, dl { margin: 0; padding: 0; list-style: none; }

	.panel { position: relative; min-width: 0; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-raised); }
	.panel[data-state='waiting'] { border-style: dashed; border-color: var(--color-line-2); background: var(--color-surface-base); }
	.panel-title { margin: 0; color: var(--color-ink-0); font-size: 0.8125rem; font-weight: 600; line-height: 1.4; overflow-wrap: anywhere; }
	.ident { color: var(--color-ink-1); font-family: var(--font-mono); font-size: 0.75rem; overflow-wrap: anywhere; }
	.icon { flex: none; width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; color: var(--color-ink-1); }
	.check-icon { width: 0.875rem; height: 0.875rem; stroke: var(--color-state-success); stroke-width: 2; }
	.status { display: inline-flex; align-items: center; gap: 0.375rem; color: var(--color-ink-2); font-size: 0.75rem; font-weight: 500; line-height: 1.4; }
	.status .dot { flex: none; width: 0.375rem; height: 0.375rem; border-radius: 50%; background: var(--color-line-2); }
	.status[data-tone='done'] { color: var(--color-state-success-text); }
	.status[data-tone='done'] .dot { background: var(--color-state-success); }

	/* Connectors live in the fixed 1rem row gap (narrow) or 1.5rem column gap (wide). */
	.conn { position: absolute; z-index: 1; left: 50%; bottom: 100%; width: 2px; height: 1rem; margin-left: -1px; background: var(--color-line-2); transform: scaleY(0); transform-origin: center top; transition: transform var(--motion-duration-data) var(--motion-ease-out); }
	.conn::after { content: ''; position: absolute; left: -3px; bottom: 0; width: 8px; height: 6px; background: inherit; clip-path: polygon(0 0, 100% 0, 50% 100%); }
	.conn.drawn { background: var(--color-accent); transform: none; }
	.conn-link { display: none; }

	.members { grid-area: members; }
	.member-list { display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; }
	.member { display: flex; align-items: center; gap: 0.5rem; min-width: 0; }
	.avatar { display: grid; flex: none; place-items: center; width: 1.5rem; height: 1.5rem; border: 1px solid var(--color-line-2); border-radius: 50%; background: var(--color-surface-sunken); color: var(--color-ink-1); font-size: 0.75rem; font-weight: 600; line-height: 1; }
	.member-role { min-width: 0; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.4; }
	.member-role b { color: var(--color-ink-0); font-weight: 600; }

	.core { grid-area: core; display: grid; }
	/* Fade through: outgoing text clears before the incoming variant becomes visible. */
	.core-variant { display: grid; grid-area: 1 / 1; align-content: start; gap: 0.375rem; min-width: 0; opacity: 0; visibility: hidden; transition: opacity var(--motion-duration-fast) var(--motion-ease-standard), visibility 0s var(--motion-ease-standard) var(--motion-duration-fast); }
	.core-variant.on { opacity: 1; visibility: visible; transition-duration: var(--motion-duration-base), 0s; transition-delay: var(--motion-duration-fast); }
	.card-head { display: flex; flex-wrap: wrap; align-items: center; gap: 0.25rem 0.5rem; min-width: 0; }
	.panel-ident { color: var(--color-ink-0); font-weight: 600; }
	.kind { color: var(--color-ink-2); font-size: 0.75rem; }
	.rows { display: grid; gap: 0.25rem; margin-top: 0.125rem; }
	.rows > div { display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; min-width: 0; }
	.rows dt { min-width: 0; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.4; }
	.rows dd { min-width: 0; margin: 0; color: var(--color-ink-0); font-size: 0.75rem; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.4; text-align: right; overflow-wrap: anywhere; }
	.rows dd.ident { color: var(--color-ink-1); font-weight: 400; }

	.links { grid-area: links; position: relative; min-width: 0; }
	.link-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.link { display: grid; flex: 1 1 8.5rem; gap: 0.125rem; }
	.link-kind { display: flex; align-items: center; gap: 0.375rem; min-width: 0; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.4; }

	.details { grid-area: detail; display: grid; min-width: 0; }
	.detail { display: grid; grid-area: 1 / 1; align-content: start; gap: 0.625rem; opacity: 0; visibility: hidden; transition: opacity var(--motion-duration-fast) var(--motion-ease-standard), visibility 0s var(--motion-ease-standard) var(--motion-duration-fast); }
	.detail.on { opacity: 1; visibility: visible; transition-duration: var(--motion-duration-base), 0s; transition-delay: var(--motion-duration-fast); }
	.enter { opacity: 0; transform: translateY(0.5rem); transition: opacity var(--motion-duration-fast) var(--motion-ease-out), transform var(--motion-duration-fast) var(--motion-ease-out); }
	.detail.on .enter { opacity: 1; transform: none; transition-duration: var(--motion-duration-panel); transition-delay: calc(var(--motion-duration-fast) + var(--motion-duration-base) * var(--i, 0)); }

	.chips { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.chip { display: inline-flex; align-items: center; gap: 0.375rem; min-width: 0; padding: 0.25rem 0.5rem; border: 1px solid var(--color-line); border-radius: var(--radius-sm); background: var(--color-surface-base); color: var(--color-ink-1); font-size: 0.75rem; font-weight: 500; line-height: 1.4; }
	.quota-list { display: grid; gap: 0.5rem; }
	.quota-list :global(.usage-meta) { flex-wrap: wrap; }
	.quota-list :global(.usage-label) { white-space: normal; overflow: visible; text-overflow: clip; }
	.quota-list :global(.usage-value) { min-width: 0; flex-shrink: 1; }
	.detail-note { margin: 0; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.5; }

	.observe { display: grid; gap: 1rem; }
	.observe-column { display: grid; align-content: start; gap: 0.5rem; min-width: 0; }
	.spark { position: relative; height: 3rem; overflow: hidden; border-bottom: 1px solid var(--color-line); }
	.spark svg { display: block; width: 100%; height: 100%; }
	.spark polyline { fill: none; stroke: var(--color-accent); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
	.spark-cover { position: absolute; inset: 0; background: var(--color-surface-raised); transform-origin: right center; transition: transform var(--motion-duration-data) var(--motion-ease-out); }
	.detail.on .spark-cover { transform: scaleX(0); transition-delay: calc(var(--motion-duration-fast) + var(--motion-duration-base) * 2); }
	.activity { display: grid; gap: 0.375rem; }
	.activity li { display: flex; gap: 0.625rem; min-width: 0; color: var(--color-ink-1); font-size: 0.75rem; line-height: 1.4; }
	.activity li > span:last-child { min-width: 0; overflow-wrap: anywhere; }

	.branch { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 0.5rem 1.5rem; }
	.layer-card { display: flex; flex-direction: column; justify-content: center; gap: 0.375rem; grid-row: 1 / 3; grid-column: 1; }
	.layer-icons { display: flex; gap: 0.25rem; }
	.environment { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.375rem 0.5rem; grid-column: 2; padding-block: 0.5rem; }
	.environment-name { color: var(--color-ink-0); font-size: 0.8125rem; font-weight: 600; line-height: 1.4; }
	.conn-branch { top: 50%; bottom: auto; left: auto; right: calc(100% + 1px); width: 1.5rem; height: 2px; margin: -1px 0 0; transform: scaleX(0); transform-origin: left center; }
	.conn-branch::after { left: auto; right: 0; top: -3px; bottom: auto; width: 6px; height: 8px; clip-path: polygon(0 0, 100% 50%, 0 100%); }
	.detail.on .conn-branch { background: var(--color-accent); transform: none; transition-delay: calc(var(--motion-duration-fast) + var(--motion-duration-base) * var(--i, 0)); }

	@container (min-width: 32rem) {
		.scene-grid { grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.25fr) minmax(0, 0.9fr); grid-template-areas: 'members core links' 'detail detail detail'; column-gap: 1.5rem; row-gap: 0.75rem; }
		.members, .links { align-self: center; }
		.member-list { flex-direction: column; gap: 0.5rem; }
		.link-list { flex-direction: column; }
		.link { flex: none; }
		.conn { top: 50%; bottom: auto; left: auto; right: calc(100% + 1px); width: 1.5rem; height: 2px; margin: -1px 0 0; transform: scaleX(0); transform-origin: left center; }
		.conn::after { left: auto; right: 0; top: -3px; bottom: auto; width: 6px; height: 8px; clip-path: polygon(0 0, 100% 50%, 0 100%); }
		.conn.drawn { transform: none; }
		.conn-links { display: none; }
		.conn-link { display: block; }
		/* Meters stay one per row so each label, value and percentage keeps its full width. */
		.allocate { grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr); grid-template-rows: auto 1fr; column-gap: 1.5rem; }
		.allocate .panel-title, .allocate .detail-note { grid-column: 1; }
		.allocate .panel-title { align-self: start; }
		.allocate .quota-list { grid-column: 2; grid-row: 1 / 3; }
		.allocate .detail-note { grid-row: 2; align-self: start; }
		.observe { grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 1.5rem; }
	}

	figcaption { display: grid; gap: 0.375rem; word-break: var(--landing-word-break, keep-all); overflow-wrap: anywhere; }
	.caption-stage { margin: 0; color: var(--color-warm-text); font-size: 0.75rem; font-weight: 500; line-height: 1.5; }
	.caption-separator { margin-inline: 0.375rem; color: var(--color-ink-2); }
	.caption-copy { margin: 0; color: var(--color-ink-1); font-size: 0.875rem; line-height: 1.6; }
	.illustration-note { margin: 0.25rem 0 0; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.5; }

	.step-articles article { padding-block: 2rem; border-top: 1px solid var(--color-line); scroll-margin-top: calc(var(--landing-nav-height, 0px) + 1.5rem); }
	.step-label { display: flex; align-items: center; gap: 0.75rem; color: var(--color-ink-1); font-size: 0.8125rem; font-weight: 500; }
	.step-mark { flex: none; width: 0.75rem; height: 0.75rem; border: 1px solid var(--color-line-2); transform: rotate(45deg); }
	article[data-active='true'] .step-mark { background: var(--color-accent); border-color: var(--color-accent); }
	h3 { font-size: clamp(1.25rem, 2.3vw, 2rem); line-height: 1.45; margin: 1rem 0; }
	article > p { color: var(--color-ink-1); line-height: 1.8; font-size: 0.9375rem; margin: 0; word-break: var(--landing-word-break, keep-all); overflow-wrap: anywhere; }
	article ul { padding-left: 1.25rem; margin: 1.25rem 0 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.8; list-style: disc; }
	article li + li { margin-top: 0.5rem; }
	@media (min-width: 768px) {
		.step-articles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 2rem; }
		.scene-frame { max-width: 40rem; margin-inline: auto; }
	}
	@media (min-width: 1024px) and (min-height: 700px) and (prefers-reduced-motion: no-preference) {
		.motion-enabled .journey-layout { grid-template-columns: minmax(0, 0.75fr) minmax(0, 1.25fr); gap: clamp(2rem, 5vw, 5rem); align-items: start; }
		.motion-enabled .visual-rail { grid-column: 2; grid-row: 1; position: sticky; top: calc(var(--landing-nav-height, 0px) + 0.75rem); }
		.motion-enabled .step-articles { grid-column: 1; grid-row: 1; display: block; }
		.motion-enabled .step-articles article { min-height: 55vh; display: flex; flex-direction: column; justify-content: center; padding-block: 3rem; }
		/* Leave room for the complete figure beside the final article, not a pin spacer. */
		.motion-enabled .step-articles article:last-child { min-height: max(55vh, 36rem); }
		.motion-enabled .scene-frame { max-width: none; }
	}
</style>
