<script lang="ts">
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import { TONE_CSS_VAR, usageTone, type DesignTone } from '$lib/design/tokens';
	import { t } from '$lib/i18n/ns/common';

	interface Props {
		percent: number;
		thresholds?: { warning: number; danger: number };
		tone?: DesignTone;
		label: string;
		valueText: string;
		class?: string;
	}

	let {
		percent,
		thresholds = { warning: 80, danger: 95 },
		tone: requestedTone,
		label,
		valueText,
		class: className = ''
	}: Props = $props();

	const observedPercent = $derived(Number.isFinite(percent) ? percent : null);
	const clampedPercent = $derived(observedPercent == null ? 0 : Math.max(0, Math.min(100, observedPercent)));
	const tone = $derived(requestedTone ?? (observedPercent == null ? 'neutral' : usageTone(observedPercent, thresholds)));
</script>

<span
	class="usage-ring {className}"
	data-tone={tone}
	role={observedPercent == null ? 'group' : 'meter'}
	aria-label={observedPercent == null ? `${label}: ${valueText} · ${t('quota.unknown')}` : label}
	aria-valuemin={observedPercent == null ? undefined : Math.min(0, observedPercent)}
	aria-valuemax={observedPercent == null ? undefined : Math.max(100, observedPercent)}
	aria-valuenow={observedPercent ?? undefined}
	aria-valuetext={observedPercent == null ? undefined : valueText}
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
