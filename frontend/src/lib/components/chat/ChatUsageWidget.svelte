<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-panel';
	import type { ChatUsage } from '$lib/api/chatTree';
	let { usage }: { usage: ChatUsage } = $props();

	const quotaMax = $derived(usage.quota_max ?? 0);
	const quotaUsed = $derived(usage.quota_used ?? 0);
	const hasQuota = $derived(quotaMax > 0);
	const quotaPct = $derived(hasQuota ? Math.max(0, Math.round((quotaUsed / quotaMax) * 100)) : null);
	const quotaBarPct = $derived(quotaPct === null ? 0 : Math.min(100, quotaPct));
	const quotaTone = $derived(quotaPct !== null && quotaPct >= 90 ? 'danger' : quotaPct !== null && quotaPct >= 70 ? 'warning' : 'ok');

	function fmtPercent(n: number): string {
		return `${Math.max(0, Math.round(n))}%`;
	}
</script>

<div class="usage" title={hasQuota ? t('usage.quotaTitle', { percent: fmtPercent(quotaPct!) }) : t('usage.noQuota')}>
	<div class="usage-line">
		<span class="usage-label">{t('usage.monthQuota')}</span>
		<span class="usage-val">{hasQuota ? t('usage.used', { percent: fmtPercent(quotaPct!) }) : t('usage.notSet')}</span>
	</div>
	{#if hasQuota}
		<div class="bar" aria-label={t('usage.quotaUsage', { percent: fmtPercent(quotaPct!) })}>
			<div class="bar-fill" data-tone={quotaTone} style="width: {quotaBarPct}%"></div>
		</div>
	{/if}
</div>

<style>
	.usage {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.2rem;
		min-width: 0;
	}
	.usage-line {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.72rem;
		color: var(--color-ink-2);
		white-space: nowrap;
	}
	.usage-label {
		color: var(--color-ink-2);
	}
	.usage-val {
		font-variant-numeric: tabular-nums;
	}
	.bar {
		width: 8rem;
		height: 0.3rem;
		border-radius: 999px;
		background: var(--color-surface-sunken);
		overflow: hidden;
	}
	.bar-fill {
		height: 100%;
		border-radius: 999px;
		background: var(--color-accent);
		transition: width 0.3s ease;
	}
	.bar-fill[data-tone='warning'] {
		background: var(--color-state-warning);
	}
	.bar-fill[data-tone='danger'] {
		background: var(--color-state-danger);
	}
</style>
