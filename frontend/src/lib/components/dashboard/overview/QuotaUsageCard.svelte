<script lang="ts">
	import { t } from '$lib/i18n/ns/dashboard-home';
	import { t as tc } from '$lib/i18n/ns/common';
	import type { DashboardOverviewQuotas } from '$lib/types/quotas';
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
</script>

<Card padding="lg">
	<div class="text-[var(--color-ink-0)] text-[15px] font-semibold mb-3.5">{t('quota.title')}</div>

	{#if error && quotas}
		<Alert tone="danger" class="mb-3">
			<span>{t('quota.loadFailed')}</span>
		</Alert>
	{/if}

	{#if pending && !quotas}
		<div class="space-y-4" role="status" aria-busy="true">
			<span class="sr-only">{tc('state.loadingNamed', { name: t('quota.title') })}</span>
			{#each Array(5) as _}
				<div class="h-8 motion-skeleton rounded"></div>
			{/each}
		</div>
	{:else if error && !quotas}
		<Alert tone="danger">
			<span>{t('quota.loadFailed')}</span>
		</Alert>
	{:else if quotas}
		<div class="flex flex-col gap-3.5">
			<QuotaBar
				label="vCPU"
				used={quotas.compute.cores.in_use}
				limit={quotas.compute.cores.limit}
			/>
			<QuotaBar
				label={t('quota.memory')}
				used={quotas.compute.ram.in_use / 1024}
				limit={quotas.compute.ram.limit === -1 ? -1 : quotas.compute.ram.limit / 1024}
			/>
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
