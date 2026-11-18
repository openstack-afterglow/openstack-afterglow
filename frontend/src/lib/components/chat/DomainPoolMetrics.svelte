<script lang="ts">
	import { displayDomainCredit, type DomainPool } from '$lib/api/chatDomainBilling';
	import { t } from '$lib/i18n/ns/chat-settings';

	let { pool }: { pool: DomainPool } = $props();
	const metrics = $derived([
		{ label: t('domainBilling.balance'), value: displayDomainCredit(pool.balance_credits) },
		{ label: t('domainBilling.reserved'), value: displayDomainCredit(pool.reserved_credits) },
		{ label: t('domainBilling.monthlyUsed'), value: displayDomainCredit(pool.monthly_used_credits) },
		{ label: t('domainBilling.managerLimit'), value: pool.manager_monthly_limit_credits === null ? t('domainBilling.noLimit') : displayDomainCredit(pool.manager_monthly_limit_credits) },
		{ label: t('domainBilling.adminCeiling'), value: pool.admin_ceiling_credits === null ? t('domainBilling.noLimit') : displayDomainCredit(pool.admin_ceiling_credits) }
	]);
</script>

<dl class="grid grid-cols-2 gap-3 sm:grid-cols-3">
	{#each metrics as metric (metric.label)}
		<div class="min-w-0">
			<dt class="text-xs text-ink-2">{metric.label}</dt>
			<dd class="mt-1 break-words text-sm font-medium tabular-nums text-ink-1">{metric.value}</dd>
		</div>
	{/each}
</dl>
