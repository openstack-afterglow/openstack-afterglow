<script module lang="ts">
	export interface PipelineStage {
		id: string;
		label: string;
		/** SVG path data drawn on a 24×24 stroked icon grid. */
		icon: string;
	}
</script>

<script lang="ts">
	import { STEP_STATE_TEXT, stepVisualState, type StepProgressStatus } from './StepProgress.svelte';

	interface Props {
		stages: PipelineStage[];
		/** Id of the stage being worked on; `null` or an unknown id before the first report. */
		current: string | null;
		status?: StepProgressStatus;
		/** Accessible name of the stage list. */
		label: string;
		/**
		 * Hide the graphic from assistive technology when an adjacent `StepProgress` already lists
		 * the same stages, so they are not announced twice.
		 */
		decorative?: boolean;
		class?: string;
	}

	let { stages, current, status = 'running', label, decorative = false, class: className = '' }: Props = $props();

	const currentIndex = $derived(current === null ? -1 : stages.findIndex((stage) => stage.id === current));
	const states = $derived(stages.map((_, index) => stepVisualState(index, currentIndex, status)));
</script>

<ol
	class="pipeline {className}"
	aria-label={decorative ? undefined : label}
	aria-hidden={decorative ? 'true' : undefined}
>
	{#each stages as stage, index (stage.id)}
		{@const state = states[index]}
		<li class="station" data-state={state}>
			{#if index > 0}
				<!-- Conduit from the previous station: filled once that station is done, flowing into an active one. -->
				<span class="conduit" data-filled={states[index - 1] === 'done' ? 'true' : undefined} aria-hidden="true">
					<span class="conduit-fill"></span>
					{#if state === 'active'}
						<span class="conduit-packet"></span>
						<span class="conduit-packet conduit-packet-late"></span>
					{/if}
				</span>
			{/if}
			<span class="station-body">
				<span class="tile" aria-hidden="true">
					{#if state === 'active'}<span class="tile-ripple"></span><span class="tile-arc"></span>{/if}
					<svg class="tile-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
						<path d={stage.icon} pathLength="1" class:motion-draw={state === 'active'} />
					</svg>
					{#if state === 'done' || state === 'failed'}
						<span class="badge motion-pop">
							<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
								{#if state === 'done'}<path d="M3 6.25l2 2 4-4.5" />{:else}<path d="M3.75 3.75l4.5 4.5M8.25 3.75l-4.5 4.5" />{/if}
							</svg>
						</span>
					{/if}
				</span>
				<span class="station-label">{stage.label}<span class="sr-only">{` · ${STEP_STATE_TEXT[state]}`}</span></span>
			</span>
		</li>
	{/each}
</ol>

<style>
	.pipeline {
		--tile: 2.5rem;
		--station: 2.5rem;
		--pipeline-active: var(--color-accent);
		display: flex;
		align-items: flex-start;
		margin: 0;
		padding: 0.375rem 0.375rem 0.25rem;
		overflow-x: auto;
		list-style: none;
		scrollbar-width: thin;
	}
	.station {
		display: flex;
		flex: 1 1 0;
		align-items: flex-start;
		min-width: calc(var(--station) + 1.25rem);
	}
	.station:first-child {
		flex: 0 0 auto;
		min-width: 0;
	}
	.station-body {
		display: flex;
		flex: 0 0 var(--station);
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		width: var(--station);
	}

	.conduit {
		position: relative;
		flex: 1 1 auto;
		min-width: 0.5rem;
		height: 2px;
		margin: calc(var(--tile) / 2 - 1px) 0.5rem 0;
		overflow: hidden;
		border-radius: 999px;
		background: var(--color-line);
	}
	.conduit-fill {
		position: absolute;
		inset: 0;
		background: var(--color-state-success);
		transform: scaleX(0);
		transform-origin: left center;
		transition: transform var(--motion-duration-data) var(--motion-ease-emphasized);
	}
	[data-filled='true'] > .conduit-fill { transform: scaleX(1); }
	/* Work flowing into the active station; the packet rests hidden when motion is reduced. */
	.conduit-packet {
		position: absolute;
		inset: 0;
		opacity: 0;
		animation: motion-travel-x calc(var(--motion-duration-shimmer) * 0.75) var(--motion-ease-in-out) infinite;
	}
	.conduit-packet-late { animation-delay: calc(var(--motion-duration-shimmer) * -0.375); }
	.conduit-packet::before {
		content: '';
		position: absolute;
		top: 0;
		left: -1rem;
		width: 1rem;
		height: 2px;
		border-radius: 999px;
		background: linear-gradient(90deg, transparent, var(--pipeline-active));
	}

	.tile {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: var(--tile);
		height: var(--tile);
		border: 1.5px dashed var(--color-line-2);
		border-radius: var(--radius-lg);
		background: var(--color-surface-base);
		color: var(--color-ink-2);
		transition:
			border-color var(--motion-duration-base) var(--motion-ease-standard),
			background-color var(--motion-duration-base) var(--motion-ease-standard),
			color var(--motion-duration-base) var(--motion-ease-standard);
	}
	.tile-icon { width: 1.25rem; height: 1.25rem; }
	[data-state='active'] .tile {
		border-style: solid;
		border-color: var(--pipeline-active);
		background: color-mix(in oklab, var(--pipeline-active) 14%, var(--color-surface-base));
		color: var(--color-ink-0);
	}
	[data-state='done'] .tile {
		border-style: solid;
		border-color: color-mix(in oklab, var(--color-state-success) 60%, var(--color-line));
		color: var(--color-ink-1);
	}
	[data-state='failed'] .tile {
		border-style: solid;
		border-color: var(--color-state-danger);
		color: var(--color-state-danger-text);
	}
	.tile-ripple {
		position: absolute;
		inset: -1.5px;
		border: 1.5px solid var(--pipeline-active);
		border-radius: inherit;
		opacity: 0;
		animation: motion-ripple var(--motion-duration-status-pulse) var(--motion-ease-out) infinite;
	}
	.tile-arc {
		position: absolute;
		inset: -5px;
		border: 2px solid transparent;
		border-top-color: var(--pipeline-active);
		border-radius: calc(var(--radius-lg) + 5px);
		animation: motion-spin var(--motion-duration-spin) linear infinite;
	}
	.badge {
		position: absolute;
		right: -0.375rem;
		bottom: -0.375rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.125rem;
		height: 1.125rem;
		border: 1.5px solid var(--color-surface-base);
		border-radius: 50%;
		background: var(--color-state-success);
		color: var(--color-surface-base);
	}
	.badge svg { width: 0.75rem; height: 0.75rem; }
	[data-state='failed'] .badge { background: var(--color-state-danger); }

	.station-label {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
	/* Below md the labels live in the adjacent step list; stations keep their screen-reader names. */
	@media (min-width: 768px) {
		.pipeline { --tile: 2.75rem; --station: 5rem; }
		.station-label {
			position: static;
			width: auto;
			height: auto;
			overflow: visible;
			clip: auto;
			white-space: normal;
			max-width: 100%;
			color: var(--color-ink-2);
			font-size: 0.75rem;
			line-height: 1.3;
			text-align: center;
			overflow-wrap: anywhere;
		}
		[data-state='active'] .station-label { color: var(--color-ink-0); font-weight: 600; }
		[data-state='done'] .station-label { color: var(--color-ink-1); }
		[data-state='failed'] .station-label { color: var(--color-state-danger-text); font-weight: 600; }
	}
</style>
