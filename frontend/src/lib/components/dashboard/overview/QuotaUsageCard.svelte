<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { DashboardOverviewQuotas, QuotaItem } from '$lib/types/quotas';
	import { t as tp } from '$lib/i18n/ns/compute-pools';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import QuotaBar from '$lib/components/ui/QuotaBar.svelte';

	let {
		quotas,
		pending,
		error,
	}: {
		quotas: DashboardOverviewQuotas | null;
		pending: boolean;
		error: string | null;
	} = $props();
	function value(amount: number | null | undefined, scale = 1) { return amount == null ? tp('unknown') : amount === -1 ? tp('unlimited') : new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 2 }).format(amount / scale); }
</script>

{#snippet computeRow(label: string, item: QuotaItem | null, scale = 1)}
	{#if item}
		<div class="min-w-0 space-y-1.5">
			<QuotaBar {label} used={item.in_use / scale} limit={item.limit === -1 ? -1 : item.limit / scale} />
			{#if item.quota_scope === 'domain'}
				<p class="break-words text-xs text-ink-2">{tp('domainQuotaTitle')}</p>
				<dl class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
					<div><dt class="inline">{tp('remaining')}: </dt><dd class="inline tabular-nums">{value(item.available, scale)}</dd></div>
					{#if item.project_limit != null}<div><dt class="inline">{tp('projectCaps')}: </dt><dd class="inline tabular-nums">{value(item.project_in_use, scale)} / {value(item.project_limit, scale)}</dd></div>{/if}
				</dl>
			{/if}
		</div>
	{:else}<p class="text-xs text-ink-2">{label}: {tp('unknown')}</p>{/if}
{/snippet}

<Card padding="lg">
	<div class="text-[var(--color-ink-0)] text-[15px] font-semibold mb-3.5">{t('quota.title')}</div>

	{#if error && quotas}
		<Alert tone="danger" class="mb-3">
			<span>{t('quota.loadFailed')}</span>
		</Alert>
	{/if}

	{#if pending && !quotas}
		<LoadingState variant="section" label={tc('state.loadingNamed', { name: t('quota.title') })} />
	{:else if error && !quotas}
		<Alert tone="danger">
			<span>{t('quota.loadFailed')}</span>
		</Alert>
	{:else if quotas}
		<div class="flex flex-col gap-3.5">
			{#if quotas.compute_pool && quotas.compute_pool.state !== 'active' && quotas.compute_pool.state !== 'unmanaged'}
				<Alert tone="warning">{tp(quotas.compute_pool.state === 'paused' ? 'pauseHelp' : 'domainUnavailable')}</Alert>
			{:else}
				{@render computeRow(quotas.compute.cores?.quota_scope === 'domain' ? tp('cpu') : 'vCPU', quotas.compute.cores)}
				{@render computeRow(t('quota.memory'), quotas.compute.ram, 1024)}
			{/if}
			<QuotaBar
				label={t('quota.storage')}
				used={quotas.storage.gigabytes.in_use}
				limit={quotas.storage.gigabytes.limit}
			/>
			<QuotaBar
				label={t('quota.floatingIp')}
				used={quotas.network.floatingip.in_use}
				limit={quotas.network.floatingip.limit}
			/>
			{#if quotas.file_storage}
				<QuotaBar
					label={t('quota.shares')}
					used={quotas.file_storage.shares.in_use}
					limit={quotas.file_storage.shares.limit}
				/>
			{/if}
		</div>
	{/if}
</Card>
