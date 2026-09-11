<script lang="ts">
	import type { DashboardOverviewSummary } from '$lib/types/compute';
	import type { DashboardK3sStats } from '$lib/types/k3s';
	import type { DashboardOverviewQuotas, QuotaItem } from '$lib/types/quotas';
	import StatTile from '$lib/components/ui/StatTile.svelte';

	let {
		summary,
		summaryPending,
		summaryError,
		quotas,
		quotasPending,
		quotasError,
		k3sStats,
		k3sPending,
		k3sError,
		k3sDisabled,
	}: {
		summary: DashboardOverviewSummary | null;
		summaryPending: boolean;
		summaryError: string | null;
		quotas: DashboardOverviewQuotas | null;
		quotasPending: boolean;
		quotasError: string | null;
		k3sStats: DashboardK3sStats | null;
		k3sPending: boolean;
		k3sError: string | null;
		k3sDisabled: boolean;
	} = $props();

	function quotaUnit(quota: QuotaItem | undefined): string | undefined {
		if (!quota) return undefined;
		if (quota.limit === -1) return '/ 무제한';
		return `/ ${quota.limit}`;
	}
</script>

<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line lg:grid-cols-4">
	{#if summaryPending && !summary}
		<div class="h-[82px] bg-surface-base animate-pulse"></div>
	{:else}
		<StatTile
			label="인스턴스"
			value={summary?.instances.total ?? '—'}
			unit={quotaUnit(quotas?.compute.instances)}
			accent="blue"
			flat
		>
			{#snippet icon()}
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2"/></svg>
			{/snippet}
			{#snippet footer()}
				{#if summaryError}<span class="text-[11px] text-[var(--color-state-danger)]">갱신 실패</span>{/if}
			{/snippet}
		</StatTile>
	{/if}

	{#if quotasPending && !quotas}
		<div class="h-[82px] bg-surface-base animate-pulse"></div>
	{:else}
		<StatTile
			label="블록 볼륨"
			value={quotas?.storage.volumes.in_use ?? '—'}
			unit={quotaUnit(quotas?.storage.volumes)}
			accent="cyan"
			flat
		>
			{#snippet icon()}
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"/></svg>
			{/snippet}
			{#snippet footer()}
				{#if quotasError}<span class="text-[11px] text-[var(--color-state-danger)]">갱신 실패</span>{/if}
			{/snippet}
		</StatTile>
	{/if}

	{#if quotasPending && !quotas}
		<div class="h-[82px] bg-surface-base animate-pulse"></div>
	{:else}
		<StatTile
			label="Floating IP"
			value={quotas?.network.floatingip.in_use ?? '—'}
			unit={quotaUnit(quotas?.network.floatingip)}
			accent="violet"
			flat
		>
			{#snippet icon()}
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9-9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"/></svg>
			{/snippet}
			{#snippet footer()}
				{#if quotasError}<span class="text-[11px] text-[var(--color-state-danger)]">갱신 실패</span>{/if}
			{/snippet}
		</StatTile>
	{/if}

	{#if k3sDisabled}
		<StatTile label="Drover 클러스터" value="N/A" accent="blue" flat>
			{#snippet icon()}
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linejoin="round" stroke-width="1.8" d="M12 2.4 19.8 6.1 21.7 14.3 16.3 20.8H7.7l-5.4-6.5 1.9-8.2L12 2.4Z"/><circle cx="12" cy="12" r="4.1" stroke-width="1.8"/><circle cx="12" cy="12" r="0.85" fill="currentColor" stroke="none"/><path stroke-linecap="round" stroke-width="1.8" d="M12 9.8V6.2M13.72 10.63l2.81-2.25M14.14 12.49l3.51.8M12.95 13.98l1.57 3.25M11.05 13.98l-1.57 3.25M9.86 12.49l-3.51.8M10.28 10.63 7.47 8.38"/></svg>
			{/snippet}
		</StatTile>
	{:else if k3sPending && !k3sStats}
		<div class="h-[82px] bg-surface-base animate-pulse"></div>
	{:else}
		<StatTile
			label="Drover 클러스터"
			value={k3sStats?.available === false ? '사용할 수 없음' : (k3sStats?.active ?? '—')}
			unit={k3sStats && k3sStats.available !== false ? '활성' : undefined}
			accent="blue"
			flat
		>
			{#snippet icon()}
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linejoin="round" stroke-width="1.8" d="M12 2.4 19.8 6.1 21.7 14.3 16.3 20.8H7.7l-5.4-6.5 1.9-8.2L12 2.4Z"/><circle cx="12" cy="12" r="4.1" stroke-width="1.8"/><circle cx="12" cy="12" r="0.85" fill="currentColor" stroke="none"/><path stroke-linecap="round" stroke-width="1.8" d="M12 9.8V6.2M13.72 10.63l2.81-2.25M14.14 12.49l3.51.8M12.95 13.98l1.57 3.25M11.05 13.98l-1.57 3.25M9.86 12.49l-3.51.8M10.28 10.63 7.47 8.38"/></svg>
			{/snippet}
			{#snippet footer()}
				{#if k3sError}<span class="text-[11px] text-[var(--color-state-danger)]">갱신 실패</span>{/if}
			{/snippet}
		</StatTile>
	{/if}
</div>
