<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-panel';
	import { t as settingsT } from '$lib/i18n/ns/chat-settings';
	import { displayDomainCredit } from '$lib/api/chatDomainBilling';
	import { auth } from '$lib/stores/auth';
	import type { ChatUsage } from '$lib/api/chatTree';
	import BklitChart from '$lib/components/charts/BklitChart.svelte';
	let { usage }: { usage: ChatUsage } = $props();
	const domainBilled = $derived(usage.billing_scope === 'domain' && !!$auth.domainId && usage.payer_domain_id === $auth.domainId);

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
	{#if domainBilled}
		<div class="usage-line flex-wrap">
			<span class="usage-label">{settingsT('domainBilling.balance')}</span>
			<span class="usage-val">{displayDomainCredit(usage.balance_credits)}</span>
			{#if usage.is_active === false}<span class="usage-label">{settingsT('domainBilling.inactiveLabel')}</span>{/if}
		</div>
	{/if}
	<div class="usage-line">
		<span class="usage-label">{t('usage.monthQuota')}</span>
		<span class="usage-val">{hasQuota ? t('usage.used', { percent: fmtPercent(quotaPct!) }) : t('usage.notSet')}</span>
	</div>
	{#if hasQuota}
		<div class="bar" aria-label={t('usage.quotaUsage', { percent: fmtPercent(quotaPct!) })}>
			<BklitChart spec={{ kind: 'gauge', value: quotaBarPct, color: quotaTone === 'danger' ? 'var(--color-state-danger)' : quotaTone === 'warning' ? 'var(--color-state-warning)' : 'var(--color-accent)', track: 'var(--color-surface-sunken)' }} height={5} decorative />
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
