<script module lang="ts">
	import { t } from '$lib/i18n/ns/common';

	export interface ProgressStepItem {
		id: string;
		label: string;
		/** Shown once the step is reached. */
		description?: string;
		/** Short trailing fact such as an elapsed time. */
		meta?: string;
	}

	export type StepProgressStatus = 'running' | 'done' | 'failed';
	export type StepVisualState = 'done' | 'active' | 'pending' | 'failed';

	/**
	 * Visual state of the step at `index`. `currentIndex` is the step being worked on, or -1 before
	 * the first progress report; a finished operation shows every step done, and a failed operation
	 * marks the step it stopped at.
	 */
	export function stepVisualState(index: number, currentIndex: number, status: StepProgressStatus): StepVisualState {
		if (status === 'done') return 'done';
		if (currentIndex < 0 || index > currentIndex) return 'pending';
		if (index < currentIndex) return 'done';
		return status === 'failed' ? 'failed' : 'active';
	}

	export const STEP_STATE_TEXT: Record<StepVisualState, string> = {
		get done() { return t('stepProgress.done'); },
		get active() { return t('stepProgress.active'); },
		get pending() { return t('stepProgress.pending'); },
		get failed() { return t('stepProgress.failed'); },
	};
</script>

<script lang="ts">
	interface Props {
		steps: ProgressStepItem[];
		/** Id of the step being worked on; `null` or an unknown id before the first report. */
		current: string | null;
		status?: StepProgressStatus;
		/** Accessible name of the step list. */
		label: string;
		class?: string;
	}

	let { steps, current, status = 'running', label, class: className = '' }: Props = $props();

	const currentIndex = $derived(current === null ? -1 : steps.findIndex((step) => step.id === current));
</script>

<ol class="step-progress {className}" aria-label={label}>
	{#each steps as step, index (step.id)}
		{@const state = stepVisualState(index, currentIndex, status)}
		<li class="step" data-state={state} aria-current={state === 'active' || state === 'failed' ? 'step' : undefined}>
			<span class="rail" aria-hidden="true">
				<span class="node">
					{#if state === 'done'}
						<svg class="node-icon motion-pop" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<path class="motion-draw" pathLength="1" d="M3.5 8.5l3 3 6-7" />
						</svg>
					{:else if state === 'failed'}
						<svg class="node-icon motion-pop" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
							<path class="motion-draw" pathLength="1" d="M4.5 4.5l7 7M11.5 4.5l-7 7" />
						</svg>
					{:else if state === 'active'}
						<span class="node-ripple"></span>
						<span class="node-arc"></span>
						<span class="node-core"></span>
					{:else}
						<span class="node-index">{index + 1}</span>
					{/if}
				</span>
				{#if index < steps.length - 1}
					<span class="connector">
						<span class="connector-fill"></span>
						{#if state === 'active'}<span class="connector-packet"></span>{/if}
					</span>
				{/if}
			</span>
			<span class="body">
				<span class="head">
					<span class="step-label">{step.label}</span>
					{#if state === 'active' || state === 'failed'}
						<span class="state-text">{STEP_STATE_TEXT[state]}</span>
					{:else}
						<span class="sr-only">{STEP_STATE_TEXT[state]}</span>
					{/if}
					{#if step.meta}<span class="meta">{step.meta}</span>{/if}
				</span>
				{#if step.description && state !== 'pending'}
					<span class="description motion-enter">{step.description}</span>
				{/if}
			</span>
		</li>
	{/each}
</ol>

<style>
	.step-progress {
		--step-node: 1.75rem;
		--step-active: var(--color-accent);
		display: grid;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.step {
		position: relative;
		display: grid;
		grid-template-columns: var(--step-node) minmax(0, 1fr);
		column-gap: 0.75rem;
		padding-bottom: 1rem;
	}
	.step:last-child { padding-bottom: 0; }

	.rail { position: relative; }
	.node {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: var(--step-node);
		height: var(--step-node);
		border: 1.5px dashed var(--color-line-2);
		border-radius: 50%;
		background: var(--color-surface-base);
		color: var(--color-ink-2);
		transition:
			border-color var(--motion-duration-base) var(--motion-ease-standard),
			background-color var(--motion-duration-base) var(--motion-ease-standard),
			color var(--motion-duration-base) var(--motion-ease-standard);
	}
	.node-index {
		font-size: 0.75rem;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}
	.node-icon { width: 0.875rem; height: 0.875rem; }

	[data-state='active'] .node {
		border-style: solid;
		border-color: var(--step-active);
		background: color-mix(in oklab, var(--step-active) 14%, var(--color-surface-base));
	}
	.node-core {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: var(--step-active);
		animation: motion-breathe var(--motion-duration-status-pulse) var(--motion-ease-in-out) infinite;
	}
	.node-arc {
		position: absolute;
		inset: -4px;
		border: 2px solid transparent;
		border-top-color: var(--step-active);
		border-radius: 50%;
		animation: motion-spin var(--motion-duration-spin) linear infinite;
	}
	.node-ripple {
		position: absolute;
		inset: -1.5px;
		border: 1.5px solid var(--step-active);
		border-radius: 50%;
		opacity: 0;
		animation: motion-ripple var(--motion-duration-status-pulse) var(--motion-ease-out) infinite;
	}
	[data-state='done'] .node {
		border-style: solid;
		border-color: var(--color-state-success);
		background: color-mix(in oklab, var(--color-state-success) 16%, var(--color-surface-base));
		color: var(--color-state-success-text);
	}
	[data-state='failed'] .node {
		border-style: solid;
		border-color: var(--color-state-danger);
		background: color-mix(in oklab, var(--color-state-danger) 16%, var(--color-surface-base));
		color: var(--color-state-danger-text);
	}

	.connector {
		position: absolute;
		top: calc(var(--step-node) + 0.25rem);
		bottom: -0.75rem;
		left: calc(var(--step-node) / 2 - 1px);
		width: 2px;
		overflow: hidden;
		border-radius: 999px;
		background: var(--color-line);
	}
	.connector-fill {
		position: absolute;
		inset: 0;
		background: var(--color-state-success);
		transform: scaleY(0);
		transform-origin: center top;
		transition: transform var(--motion-duration-data) var(--motion-ease-emphasized);
	}
	[data-state='done'] .connector-fill { transform: scaleY(1); }
	/* Work heading toward the next step: a packet travels down the connector, then rests out of sight. */
	.connector-packet {
		position: absolute;
		inset: 0;
		opacity: 0;
		animation: motion-travel-y calc(var(--motion-duration-shimmer) * 0.75) var(--motion-ease-in-out) infinite;
	}
	.connector-packet::before {
		content: '';
		position: absolute;
		top: -0.75rem;
		left: 0;
		width: 2px;
		height: 0.75rem;
		border-radius: 999px;
		background: linear-gradient(180deg, transparent, var(--step-active));
	}

	.body {
		display: grid;
		gap: 0.125rem;
		min-width: 0;
		padding-top: 0.25rem;
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.5rem;
		min-width: 0;
	}
	.step-label {
		min-width: 0;
		color: var(--color-ink-2);
		font-size: 0.8125rem;
		font-weight: 500;
		overflow-wrap: anywhere;
	}
	[data-state='active'] .step-label { color: var(--color-ink-0); font-weight: 600; }
	[data-state='done'] .step-label { color: var(--color-ink-1); }
	[data-state='failed'] .step-label { color: var(--color-state-danger-text); font-weight: 600; }
	.state-text {
		color: var(--color-ink-1);
		font-size: 0.75rem;
	}
	[data-state='failed'] .state-text { color: var(--color-state-danger-text); }
	.meta {
		margin-left: auto;
		color: var(--color-ink-2);
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
	}
	.description {
		color: var(--color-ink-2);
		font-size: 0.75rem;
		line-height: 1.45;
	}
</style>
