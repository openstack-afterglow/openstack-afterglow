<script lang="ts">
	import { t } from '$lib/i18n/ns/volume';
	import type { Snapshot, Volume } from '$lib/types/volume';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';
	import UsageBar from '$lib/components/ui/UsageBar.svelte';

	interface QuotaItem { limit: number; in_use: number; }
	interface VolumeQuotas { storage: { volumes: QuotaItem; gigabytes: QuotaItem; }; }

	let {
		volumes,
		snapshots,
		quotas,
		showSnapshots = true,
	}: {
		volumes: Volume[];
		snapshots: Snapshot[];
		quotas: VolumeQuotas | null;
		showSnapshots?: boolean;
	} = $props();

	let totalGb = $derived(volumes.reduce((s, v) => s + v.size, 0));
	let attachedCount = $derived(volumes.filter((v) => v.attachments.length > 0).length);
	let recentSnapshots = $derived(
		snapshots.filter((s) => {
			if (!s.created_at) return false;
			return Date.now() - new Date(s.created_at).getTime() < 86400000;
		}),
	);

</script>

<div class={`grid ${showSnapshots ? 'grid-cols-3' : 'grid-cols-2'} gap-3.5 mb-5`}>
	<!-- 총 할당 용량 -->
	<div class="bg-surface-base border border-line rounded-lg p-5">
		<div class="text-xs uppercase tracking-wider text-ink-2 font-medium mb-2">{t('summaryCards.allocatedStorage')}</div>
		<div class="text-[26px] font-bold text-ink-0 leading-none mb-1">
			<AnimatedNumber value={totalGb} />
			{#if quotas?.storage.gigabytes.limit && quotas.storage.gigabytes.limit > 0}
				<span class="text-sm font-normal text-ink-2">/ {quotas.storage.gigabytes.limit} GB</span>
			{:else if quotas?.storage.gigabytes.limit === -1}
				<span class="text-sm font-normal text-ink-2">{t('summaryCards.unlimitedStorage')}</span>
			{:else}
				<span class="text-sm font-normal text-ink-2">GB</span>
			{/if}
		</div>
		<div class="text-xs text-ink-2 mb-3">
			{#if quotas?.storage.gigabytes.limit && quotas.storage.gigabytes.limit > 0}
				{t('summaryCards.storageUsage', { percent: Math.round(totalGb / quotas.storage.gigabytes.limit * 100) })}
			{:else}
				&nbsp;
			{/if}
		</div>
		{#if quotas?.storage.gigabytes.limit && quotas.storage.gigabytes.limit > 0}
			<div role="meter" aria-label={t('summaryCards.allocatedStorage')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.max(0, Math.min(100, Math.round(totalGb / quotas.storage.gigabytes.limit * 100)))}>
				<UsageBar value={totalGb} max={quotas.storage.gigabytes.limit} showValue={false} />
			</div>
		{:else}
			<div class="h-1.5 bg-surface-sunken rounded-full"></div>
		{/if}
	</div>
	<!-- 볼륨 개수 -->
	<div class="bg-surface-base border border-line rounded-lg p-5">
		<div class="text-xs uppercase tracking-wider text-ink-2 font-medium mb-2">{t('summaryCards.volumes')}</div>
		<div class="text-[26px] font-bold text-ink-0 leading-none mb-1">
			<AnimatedNumber value={volumes.length} />
			{#if quotas?.storage.volumes.limit && quotas.storage.volumes.limit > 0}
				<span class="text-sm font-normal text-ink-2">/ {quotas.storage.volumes.limit}</span>
			{:else if quotas?.storage.volumes.limit === -1}
				<span class="text-sm font-normal text-ink-2">{t('summaryCards.unlimitedVolumes')}</span>
			{/if}
		</div>
		<div class="text-xs text-ink-2 mb-3">
			{#if quotas?.storage.volumes.limit && quotas.storage.volumes.limit > 0}
				{t('summaryCards.volumeUsage', { percent: Math.round(volumes.length / quotas.storage.volumes.limit * 100) })}
			{:else}
				&nbsp;
			{/if}
		</div>
		{#if quotas?.storage.volumes.limit && quotas.storage.volumes.limit > 0}
			<div role="meter" aria-label={t('summaryCards.volumes')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.max(0, Math.min(100, Math.round(volumes.length / quotas.storage.volumes.limit * 100)))}>
				<UsageBar value={volumes.length} max={quotas.storage.volumes.limit} showValue={false} />
			</div>
		{:else}
			<div class="h-1.5 bg-surface-sunken rounded-full"></div>
		{/if}
		<div class="text-xs text-ink-2 mt-2">{t('summaryCards.attachedCount', { count: attachedCount })}</div>
	</div>
	{#if showSnapshots}
		<!-- 스냅샷 -->
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<div class="text-xs uppercase tracking-wider text-ink-2 font-medium mb-2">{t('summaryCards.snapshots')}</div>
			<div class="text-[26px] font-bold text-ink-0 leading-none mb-1"><AnimatedNumber value={snapshots.length} /></div>
			<div class="text-xs text-ink-2">{t('summaryCards.recentSnapshots', { count: recentSnapshots.length })}</div>
		</div>
	{/if}
</div>

