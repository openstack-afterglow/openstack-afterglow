<script lang="ts">
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import { SURFACE_CSS_VAR, TONE_CSS_VAR, usageTone } from '$lib/design/tokens';
	import { t } from '$lib/i18n/ns/common';

	interface Props {
		value?: number;
		max?: number;
		percent?: number;
		thresholds?: { warning: number; danger: number };
		size?: 'xs' | 'sm' | 'md';
		label?: string;
		unit?: string;
		showValue?: boolean;
		class?: string;
	}

	let {
		value,
		max,
		percent,
		thresholds = { warning: 80, danger: 95 },
		size = 'sm',
		label,
		unit = '',
		showValue = true,
		class: className = '',
	}: Props = $props();

	const rawPercent = $derived(percent ?? (max && max > 0 && value != null ? (value / max) * 100 : 0));
	const pct = $derived(
		Number.isFinite(rawPercent)
			? Math.max(0, Math.min(100, Math.round(rawPercent)))
			: 0,
	);
	const tone = $derived(usageTone(pct, thresholds));
	const isUnlimited = $derived(max === -1);
	const valueText = $derived(value == null ? '' : unit ? `${value}${unit}` : `${value}`);
	const maxText = $derived(max === -1 ? t('quota.unlimited') : max == null ? '' : unit ? `${max}${unit}` : `${max}`);
	const height = $derived(size === 'xs' ? 4 : size === 'md' ? 8 : 6);
	const accessibleValue = $derived(
		isUnlimited
			? value == null ? t('quota.unlimited') : `${valueText} / ${maxText}`
			: value == null ? `${pct}%` : `${valueText}${maxText ? ` / ${maxText}` : ''} · ${pct}%`,
	);
</script>

<div
	class="usage-bar {className}"
	data-tone={tone}
	style:--usage-tone={TONE_CSS_VAR[tone]}
	role={isUnlimited ? 'group' : 'meter'}
	aria-label={label || accessibleValue}
	aria-valuemin={isUnlimited ? undefined : 0}
	aria-valuemax={isUnlimited ? undefined : 100}
	aria-valuenow={isUnlimited ? undefined : pct}
	aria-valuetext={isUnlimited ? undefined : accessibleValue}
>
	{#if showValue || label}
		<div class="usage-meta">
			{#if label}
				<span class="usage-label">{label}</span>
			{/if}
			{#if showValue}
				<span class="usage-value">
					{#if value != null}
						<span class="usage-current">{valueText}</span>{#if maxText} / {maxText}{/if}
					{:else if isUnlimited}
						<span class="usage-current">{t('quota.unlimited')}</span>
					{/if}
					{#if !isUnlimited}
						<span class="usage-percent">{pct}%</span>
					{/if}
				</span>
			{/if}
		</div>
	{/if}
	{#if isUnlimited}
		<div class="usage-unlimited" style:height={`${height}px`} aria-hidden="true"></div>
	{:else}
		<BklitChart
			spec={{ kind: 'gauge', value: pct, color: TONE_CSS_VAR[tone], track: SURFACE_CSS_VAR.sunken }}
			{height}
			decorative
		/>
	{/if}
</div>

<style>
	@layer components {
		.usage-bar { width: 100%; min-width: 0; }
	}
	.usage-meta {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.5rem;
		margin-bottom: 0.375rem;
		font-size: 0.75rem;
	}
	.usage-label {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--color-ink-2);
	}
	.usage-value {
		flex-shrink: 0;
		color: var(--color-ink-2);
	}
	.usage-current {
		font-weight: 600;
		color: var(--color-ink-0);
	}
	.usage-percent {
		margin-left: 0.25rem;
		font-weight: 600;
		color: var(--usage-tone);
	}
	.usage-unlimited {
		border: 1px dashed var(--color-line-2);
		border-radius: 999px;
		background: var(--color-surface-base);
	}
</style>
