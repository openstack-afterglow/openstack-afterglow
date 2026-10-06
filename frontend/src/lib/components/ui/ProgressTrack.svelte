<script module lang="ts">
	export type ProgressTone = 'accent' | 'warm' | 'success' | 'danger' | 'neutral';

	/** Clamps a percentage to 0–100; non-finite input is indeterminate (`null`). */
	export function clampProgress(value: number | null | undefined): number | null {
		if (value === null || value === undefined || !Number.isFinite(value)) return null;
		return Math.max(0, Math.min(100, value));
	}
</script>

<script lang="ts">
	interface Props {
		/** 0–100. `null` renders an indeterminate track for work whose amount is unknown. */
		value: number | null;
		/** Accessible name of the progressbar. */
		label: string;
		tone?: ProgressTone;
		/** Sweeps a sheen across the fill while the work is still in flight. */
		active?: boolean;
		size?: 'xs' | 'sm' | 'md';
		/** Human reading of the value, e.g. `3/7 단계` or `12 MB / 40 MB`. */
		valueText?: string;
		class?: string;
	}

	let { value, label, tone = 'accent', active = false, size = 'sm', valueText, class: className = '' }: Props = $props();

	const pct = $derived(clampProgress(value));
</script>

<div
	class="progress-track progress-size-{size} {className}"
	data-tone={tone}
	data-active={active ? 'true' : undefined}
	role="progressbar"
	aria-label={label}
	aria-busy={active}
	aria-valuemin={pct === null ? undefined : 0}
	aria-valuemax={pct === null ? undefined : 100}
	aria-valuenow={pct === null ? undefined : Math.round(pct)}
	aria-valuetext={valueText}
>
	{#if pct === null}
		<span class="progress-indeterminate"></span>
	{:else}
		<span class="progress-fill" style:transform={`scaleX(${pct / 100})`}></span>
	{/if}
</div>

<style>
	.progress-track {
		--progress-fill: var(--color-accent);
		position: relative;
		width: 100%;
		overflow: hidden;
		border-radius: 999px;
		background: var(--color-surface-sunken);
	}
	.progress-track[data-tone='warm'] { --progress-fill: var(--color-action-warm); }
	.progress-track[data-tone='success'] { --progress-fill: var(--color-state-success); }
	.progress-track[data-tone='danger'] { --progress-fill: var(--color-state-danger); }
	.progress-track[data-tone='neutral'] { --progress-fill: var(--color-ink-3); }
	.progress-size-xs { height: 0.25rem; }
	.progress-size-sm { height: 0.375rem; }
	.progress-size-md { height: 0.5rem; }

	/* The fill scales instead of resizing; the rounded track clips its square end. */
	.progress-fill {
		position: absolute;
		inset: 0;
		overflow: hidden;
		background: var(--progress-fill);
		transform-origin: left center;
		transition:
			transform var(--motion-duration-data) var(--motion-ease-emphasized),
			background-color var(--motion-duration-base) var(--motion-ease-standard);
		animation: motion-grow-x var(--motion-duration-data) var(--motion-ease-emphasized) backwards;
	}
	.progress-fill::after {
		content: '';
		position: absolute;
		inset: 0;
		opacity: 0;
		transform: translateX(-100%);
		background: linear-gradient(90deg, transparent, var(--motion-sheen), transparent);
	}
	[data-active='true'] .progress-fill::after {
		opacity: 1;
		animation: motion-sweep var(--motion-duration-shimmer) var(--motion-ease-in-out) infinite;
	}

	.progress-indeterminate {
		position: absolute;
		inset: 0 auto 0 0;
		width: 30%;
		border-radius: inherit;
		background: var(--progress-fill);
		animation: motion-indeterminate calc(var(--motion-duration-shimmer) * 0.75) var(--motion-ease-in-out) infinite;
	}
	/* Static frame: a full, quiet track rather than a 30% bar that reads as a measured value. */
	@media (prefers-reduced-motion: reduce) {
		.progress-indeterminate {
			width: 100%;
			opacity: 0.45;
		}
	}
</style>
