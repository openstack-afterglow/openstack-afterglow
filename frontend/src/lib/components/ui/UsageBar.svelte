<script lang="ts">
	import { usageTone } from '$lib/design/tokens';

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
	const maxText = $derived(max === -1 ? '무제한' : max == null ? '' : unit ? `${max}${unit}` : `${max}`);
</script>

<div class="usage-bar usage-size-{size} {className}" data-tone={tone}>
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
						<span class="usage-current">무제한</span>
					{/if}
					{#if !isUnlimited}
						<span class="usage-percent">{pct}%</span>
					{/if}
				</span>
			{/if}
		</div>
	{/if}
	<div class="usage-track" class:usage-track-unlimited={isUnlimited}>
		{#if !isUnlimited}
			<div class="usage-fill usage-fill-{tone}" style={`width: ${pct}%`}></div>
		{/if}
	</div>
</div>

<style>
	.usage-bar { width: 100%; }
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
	.usage-track {
		overflow: hidden;
		border-radius: 999px;
		background: var(--color-surface-sunken);
	}
	.usage-track-unlimited {
		border: 1px dashed var(--color-line-2);
		background: var(--color-surface-base);
	}
	.usage-size-xs .usage-track { height: 0.25rem; }
	.usage-size-sm .usage-track { height: 0.375rem; }
	.usage-size-md .usage-track { height: 0.5rem; }
	.usage-fill {
		height: 100%;
		border-radius: inherit;
		transition: width var(--motion-duration-base) var(--motion-ease-standard);
	}
	.usage-fill-accent { --usage-tone: var(--color-accent); background: var(--gradient-usage); }
	.usage-fill-warning { --usage-tone: var(--color-state-warning); background: var(--gradient-usage-warning); }
	.usage-fill-danger { --usage-tone: var(--color-state-danger); background: var(--gradient-usage-danger); }
	.usage-bar[data-tone='accent'] { --usage-tone: var(--color-accent); }
	.usage-bar[data-tone='warning'] { --usage-tone: var(--color-state-warning); }
	.usage-bar[data-tone='danger'] { --usage-tone: var(--color-state-danger); }
</style>
