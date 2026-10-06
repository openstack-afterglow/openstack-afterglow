<script lang="ts">
	import { usageTone } from '$lib/design/tokens';

	interface Props {
		percent: number;
		thresholds?: { warning: number; danger: number };
		label: string;
		valueText: string;
		class?: string;
	}

	let {
		percent,
		thresholds = { warning: 80, danger: 95 },
		label,
		valueText,
		class: className = ''
	}: Props = $props();

	const clampedPercent = $derived(
		Number.isFinite(percent) ? Math.max(0, Math.min(100, Math.round(percent))) : 0
	);
	const tone = $derived(usageTone(clampedPercent, thresholds));
</script>

<span
	class="usage-ring {className}"
	data-tone={tone}
	role="meter"
	aria-label={label}
	aria-valuemin="0"
	aria-valuemax="100"
	aria-valuenow={clampedPercent}
	aria-valuetext={valueText}
>
	<svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
		<circle class="track" cx="10" cy="10" r="8" pathLength="100" />
		<circle
			class="fill"
			cx="10"
			cy="10"
			r="8"
			pathLength="1"
			stroke-dasharray="1"
			stroke-dashoffset={1 - clampedPercent / 100}
		/>
	</svg>
</span>

<style>
	.usage-ring {
		display: inline-flex;
		width: 1.125rem;
		height: 1.125rem;
		flex: 0 0 auto;
		color: var(--color-accent);
	}
	.usage-ring[data-tone='warning'] { color: var(--color-state-warning); }
	.usage-ring[data-tone='danger'] { color: var(--color-state-danger); }
	.usage-ring svg {
		display: block;
		width: 100%;
		height: 100%;
		transform: rotate(-90deg);
	}
	.track,
	.fill {
		fill: none;
		stroke-width: 2.5;
	}
	.track { stroke: var(--color-line-2); }
	.fill {
		stroke: currentColor;
		stroke-linecap: round;
		animation: motion-draw var(--motion-duration-data) var(--motion-ease-emphasized) backwards;
		transition: stroke-dashoffset var(--motion-duration-data) var(--motion-ease-emphasized), stroke var(--motion-duration-fast) var(--motion-ease-standard);
	}
</style>
