<script lang="ts">
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import { TONE_CSS_VAR, usageTone } from '$lib/design/tokens';

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
	<BklitChart
		spec={{
			kind: 'ring',
			value: clampedPercent,
			max: 100,
			size: 18,
			stroke: 2.25,
			color: TONE_CSS_VAR[tone],
			track: 'var(--color-line-2)',
		}}
		height={18}
		width={18}
		decorative
	/>
</span>

<style>
	.usage-ring {
		display: inline-flex;
		width: 1.125rem;
		height: 1.125rem;
		flex: 0 0 auto;
	}
</style>
