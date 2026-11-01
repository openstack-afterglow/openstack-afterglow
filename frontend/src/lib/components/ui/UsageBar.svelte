<script lang="ts">
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	import { SURFACE_CSS_VAR, TONE_CSS_VAR, usageTone, type DesignTone } from '$lib/design/tokens';
	import { t } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface Props {
		value?: number;
		max?: number;
		percent?: number;
		thresholds?: { warning: number; danger: number };
		tone?: DesignTone;
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
		tone: requestedTone,
		size = 'sm',
		label,
		unit = '',
		showValue = true,
		class: className = '',
	}: Props = $props();

	const isUnlimited = $derived(max === -1);
	const zeroQuota = $derived(max === 0 && value != null && Number.isFinite(value) && percent == null);
	const rawPercent = $derived(percent ?? (max != null && max > 0 && value != null ? (value / max) * 100 : null));
	const observedPercent = $derived(!isUnlimited && rawPercent != null && Number.isFinite(rawPercent) ? rawPercent : null);
	const visualPercent = $derived(observedPercent == null ? 0 : Math.max(0, Math.min(100, observedPercent)));
	const tone = $derived(requestedTone ?? (zeroQuota && value! > 0 ? 'danger' : observedPercent == null ? 'neutral' : usageTone(observedPercent, thresholds)));
	const valueText = $derived(value == null || !Number.isFinite(value) ? '' : unit ? `${value}${unit}` : `${value}`);
	const maxText = $derived(isUnlimited ? t('quota.unlimited') : max == null || !Number.isFinite(max) ? '' : unit ? `${max}${unit}` : `${max}`);
	const height = $derived(size === 'xs' ? 4 : size === 'md' ? 8 : 6);
	const displayPercent = $derived(observedPercent == null ? null : (observedPercent > 100 ? Math.ceil(observedPercent * 10) : Math.floor(observedPercent * 10)) / 10);
	const percentText = $derived(zeroQuota ? value! > 0 ? t('quota.overLimit') : '' : displayPercent == null ? t('quota.unknown') : `${displayPercent.toLocaleString(intlLocale(), { maximumFractionDigits: 1 })}%`);
	const accessibleValue = $derived(
		isUnlimited
			? valueText ? `${valueText} / ${maxText}` : maxText
			: `${valueText ? `${valueText}${maxText ? ` / ${maxText}` : ''}` : ''}${percentText ? `${valueText ? ' · ' : ''}${percentText}` : ''}`,
	);
</script>

<div
	class="usage-bar {className}"
	data-tone={tone}
	role={observedPercent == null ? 'group' : 'meter'}
	aria-label={observedPercent == null && label ? `${label}: ${accessibleValue}` : label || accessibleValue}
	aria-valuemin={observedPercent == null ? undefined : Math.min(0, observedPercent)}
	aria-valuemax={observedPercent == null ? undefined : Math.max(100, observedPercent)}
	aria-valuenow={observedPercent ?? undefined}
	aria-valuetext={observedPercent == null ? undefined : accessibleValue}
>
	{#if showValue || label}
		<div class="usage-meta">
			{#if label}
				<span class="usage-label">{label}</span>
			{/if}
			{#if showValue}
				<span class="usage-value">
					{#if valueText}
						<span class="usage-current">{valueText}</span>{#if maxText} / {maxText}{/if}
					{:else if isUnlimited}
						<span class="usage-current">{t('quota.unlimited')}</span>
					{/if}
					{#if !isUnlimited && percentText}
						<span class="usage-percent">{percentText}</span>
					{/if}
				</span>
			{/if}
		</div>
	{/if}
	{#if isUnlimited || observedPercent == null}
		<div class="usage-unlimited" style:height={`${height}px`} aria-hidden="true"></div>
	{:else}
		<BklitChart
			spec={{ kind: 'gauge', value: visualPercent, color: TONE_CSS_VAR[tone], track: SURFACE_CSS_VAR.sunken }}
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
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.5rem;
		margin-bottom: 0.375rem;
		font-size: var(--type-support);
	}
	.usage-label {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--color-ink-2);
	}
	.usage-value {
		min-width: 0;
		overflow-wrap: anywhere;
		color: var(--color-ink-2);
		font-variant-numeric: tabular-nums;
	}
	.usage-current {
		font-weight: 600;
		color: var(--color-ink-0);
	}
	.usage-percent {
		margin-left: 0.25rem;
		font-weight: 600;
		color: var(--color-ink-1);
	}
	.usage-unlimited {
		border: 1px dashed var(--color-line-2);
		border-radius: 999px;
		background: var(--color-surface-base);
	}
</style>
