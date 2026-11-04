<script module lang="ts">
	export type ProgressShape = 'linear' | 'circular';

	export type ProgressTone = 'accent' | 'warm' | 'success' | 'danger' | 'neutral';

	/** Clamps a percentage to 0–100; non-finite input is indeterminate (`null`). */
	export function clampProgress(value: number | null | undefined): number | null {
		if (value === null || value === undefined || !Number.isFinite(value)) return null;
		return Math.max(0, Math.min(100, value));
	}
</script>

<script lang="ts">
	import { circularProgress } from '$lib/design/characterFormats';
	import { characterStep, flowBar } from './characterTicker';
	interface Props {
		/** 0–100. `null` renders an indeterminate track for work whose amount is unknown. */
		value: number | null;
		/** Accessible name of the progressbar. */
		label: string;
		tone?: ProgressTone;
		/** Text-only track geometry; linear preserves the existing layout by default. */
		shape?: ProgressShape;
		/** Marks work still in flight; unknown amounts use a character signal. */
		active?: boolean;
		size?: 'xs' | 'sm' | 'md';
		/** Human reading of the value, e.g. `3/7 단계` or `12 MB / 40 MB`. */
		valueText?: string;
		class?: string;
	}

	let { value, label, tone = 'accent', shape = 'linear', active = false, size = 'sm', valueText, class: className = '' }: Props = $props();

	const pct = $derived(clampProgress(value));
</script>

<div
	class="progress-track progress-size-{size} {className}"
	data-tone={tone}
	data-shape={shape}
	data-active={active ? 'true' : undefined}
	data-indeterminate={pct === null && active ? 'true' : undefined}
	role="progressbar"
	aria-label={label}
	aria-busy={active}
	aria-valuemin={pct === null ? undefined : 0}
	aria-valuemax={pct === null ? undefined : 100}
	aria-valuenow={pct === null ? undefined : Math.round(pct)}
	aria-valuetext={valueText}
>
	{#if shape === 'circular'}
		<pre class="progress-circle" aria-hidden="true">{circularProgress(pct, $characterStep, active)}</pre>
	{:else if pct === null}
		{#if active}<span class="progress-indeterminate" aria-hidden="true">{#each [...flowBar($characterStep)] as character}<span>{character}</span>{/each}</span>{/if}
	{:else}
		<span class="progress-empty" aria-hidden="true">{#each Array(32) as _}<span>·</span>{/each}</span>
		<span class="progress-fill" aria-hidden="true" style:clip-path={`inset(0 ${100 - pct}% 0 0)`}>{#each Array(32) as _}<span>#</span>{/each}</span>
	{/if}
</div>

<style>
	.progress-track {
		--progress-fill: var(--color-accent);
		position: relative;
		width: 100%;
		min-width: 0;
		overflow: hidden;
		font-family: var(--font-mono);
		font-size: var(--type-identifier);
		line-height: 1rem;
		height: 1rem;
		white-space: nowrap;
		letter-spacing: 0.05em;
	}
	.progress-track[data-shape='circular'] { width: fit-content; max-width: 100%; height: auto; white-space: pre; letter-spacing: 0; }
	.progress-circle { margin: 0; overflow: hidden; max-width: 100%; font: inherit; line-height: 1.3; color: var(--progress-fill); white-space: pre; }
	.progress-track[data-tone='warm'] { --progress-fill: var(--color-action-warm); }
	.progress-track[data-tone='success'] { --progress-fill: var(--color-state-success); }
	.progress-track[data-tone='danger'] { --progress-fill: var(--color-state-danger); }
	.progress-track[data-tone='neutral'] { --progress-fill: var(--color-ink-3); }
	.progress-size-xs { letter-spacing: 0; }
	.progress-size-md { letter-spacing: 0.1em; }
	.progress-empty { color: var(--color-ink-3); }
	.progress-empty, .progress-fill, .progress-indeterminate { display: flex; justify-content: space-between; width: 100%; }
	.progress-empty > span, .progress-fill > span, .progress-indeterminate > span { flex: none; }
	.progress-fill, .progress-indeterminate { position: absolute; inset: 0; color: var(--progress-fill); }
	.progress-fill { transition: clip-path var(--motion-duration-data) var(--motion-ease-emphasized); }
	.progress-indeterminate { overflow: hidden; }
	@media (prefers-reduced-motion: reduce) {
		.progress-fill { transition: none; }
	}
	@media (forced-colors: active) {
		.progress-track { --progress-fill: CanvasText; }
		.progress-empty { color: GrayText; }
	}
</style>
