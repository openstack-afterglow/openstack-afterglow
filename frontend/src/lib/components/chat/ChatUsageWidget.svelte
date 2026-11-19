<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-panel';
	import { t as settingsT } from '$lib/i18n/ns/chat-settings';
	import { currentDomainPool, displayDomainCredit } from '$lib/api/chatDomainBilling';
	import { auth } from '$lib/stores/auth';
	import type { ChatUsage } from '$lib/api/chatTree';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	let { usage }: { usage: ChatUsage } = $props();
	const pool = $derived(currentDomainPool(usage, $auth.domainId));
	// Lumen's `domain_pool` leaves quota_* to the caller; older Lumen put the paying pool there.
	const poolSummary = $derived(pool && !pool.legacy ? pool : null);

	function usedPercent(used: unknown, limit: unknown): number | null {
		const max = Number(limit ?? 0);
		const spent = Number(used ?? 0);
		return max > 0 && Number.isFinite(max) && Number.isFinite(spent) ? Math.max(0, Math.round((spent / max) * 100)) : null;
	}
	const quotaPct = $derived(usedPercent(usage.quota_used, usage.quota_max));
	const poolPct = $derived(poolSummary ? usedPercent(poolSummary.monthly_used_credits, poolSummary.effective_monthly_limit_credits) : null);
	// Dashboard chat draws on the pool when one exists, so the bar follows the pool limit.
	const barPct = $derived(poolSummary ? poolPct : quotaPct);
	const barTone = $derived(barPct !== null && barPct >= 90 ? 'danger' : barPct !== null && barPct >= 70 ? 'warning' : 'ok');

	function fmtPercent(n: number): string {
		return `${Math.max(0, Math.round(n))}%`;
	}
</script>

<div class="usage" title={barPct !== null ? t('usage.quotaTitle', { percent: fmtPercent(barPct) }) : t('usage.noQuota')}>
	{#if pool}
		<div class="usage-line flex-wrap">
			<span class="usage-label">{settingsT('domainBilling.balance')}</span>
			<span class="usage-val">{displayDomainCredit(pool.balance_credits)}</span>
			{#if pool.is_active === false}<span class="usage-label">{settingsT('domainBilling.inactiveLabel')}</span>{/if}
		</div>
	{/if}
	{#if poolSummary}
		<div class="usage-line">
			<span class="usage-label">{t('usage.poolLimit')}</span>
			<span class="usage-val">{poolPct !== null ? t('usage.used', { percent: fmtPercent(poolPct) }) : settingsT('domainBilling.noLimit')}</span>
		</div>
	{:else}
		<div class="usage-line">
			<span class="usage-label">{t('usage.monthQuota')}</span>
			<span class="usage-val">{quotaPct !== null ? t('usage.used', { percent: fmtPercent(quotaPct) }) : t('usage.notSet')}</span>
		</div>
	{/if}
	{#if barPct !== null}
		<div class="bar" aria-label={poolSummary ? t('usage.poolUsage', { percent: fmtPercent(barPct) }) : t('usage.quotaUsage', { percent: fmtPercent(barPct) })}>
			<BklitChart spec={{ kind: 'gauge', value: Math.min(100, barPct), color: barTone === 'danger' ? 'var(--color-state-danger)' : barTone === 'warning' ? 'var(--color-state-warning)' : 'var(--color-accent)', track: 'var(--color-surface-sunken)' }} height={5} decorative />
		</div>
	{/if}
	{#if poolSummary && quotaPct !== null}
		<!-- The caller's own monthly limit still guards every payer. -->
		<div class="usage-line">
			<span class="usage-label">{t('usage.personalLimit')}</span>
			<span class="usage-val">{t('usage.used', { percent: fmtPercent(quotaPct) })}</span>
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
	}
</style>
