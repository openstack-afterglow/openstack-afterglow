<script lang="ts">
	import type { Snapshot, Volume } from '$lib/types/volume';

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
		<div class="text-[11px] uppercase tracking-wider text-ink-3 font-medium mb-2">총 할당 용량</div>
		<div class="text-[26px] font-bold text-ink-0 leading-none mb-1">
			{totalGb}
			{#if quotas?.storage.gigabytes.limit && quotas.storage.gigabytes.limit > 0}
				<span class="text-[14px] font-normal text-ink-2">/ {quotas.storage.gigabytes.limit} GB</span>
			{:else if quotas?.storage.gigabytes.limit === -1}
				<span class="text-[14px] font-normal text-ink-2">/ 무제한 GB</span>
			{:else}
				<span class="text-[14px] font-normal text-ink-2">GB</span>
			{/if}
		</div>
		<div class="text-[11px] text-ink-3 mb-3">
			{#if quotas?.storage.gigabytes.limit && quotas.storage.gigabytes.limit > 0}
				사용률 {Math.round(totalGb / quotas.storage.gigabytes.limit * 100)}%
			{:else}
				&nbsp;
			{/if}
		</div>
		<div class="h-1.5 bg-surface-sunken rounded-full overflow-hidden">
			{#if quotas?.storage.gigabytes.limit && quotas.storage.gigabytes.limit > 0}
				{@const vpct = totalGb / quotas.storage.gigabytes.limit * 100}
				<div class="h-full rounded-full transition-all" style="width: {Math.min(100, Math.round(vpct))}%; background: {vpct >= 95 ? 'var(--gradient-usage-danger)' : vpct >= 80 ? 'var(--gradient-usage-warning)' : 'var(--gradient-usage)'}"></div>
			{/if}
		</div>
	</div>
	<!-- 볼륨 개수 -->
	<div class="bg-surface-base border border-line rounded-lg p-5">
		<div class="text-[11px] uppercase tracking-wider text-ink-3 font-medium mb-2">볼륨</div>
		<div class="text-[26px] font-bold text-ink-0 leading-none mb-1">
			{volumes.length}
			{#if quotas?.storage.volumes.limit && quotas.storage.volumes.limit > 0}
				<span class="text-[14px] font-normal text-ink-2">/ {quotas.storage.volumes.limit}</span>
			{:else if quotas?.storage.volumes.limit === -1}
				<span class="text-[14px] font-normal text-ink-2">/ 무제한</span>
			{/if}
		</div>
		<div class="text-[11px] text-ink-3 mb-3">
			{#if quotas?.storage.volumes.limit && quotas.storage.volumes.limit > 0}
				사용률 {Math.round(volumes.length / quotas.storage.volumes.limit * 100)}%
			{:else}
				&nbsp;
			{/if}
		</div>
		<div class="h-1.5 bg-surface-sunken rounded-full overflow-hidden">
			{#if quotas?.storage.volumes.limit && quotas.storage.volumes.limit > 0}
				{@const cpct = volumes.length / quotas.storage.volumes.limit * 100}
				<div class="h-full rounded-full transition-all" style="width: {Math.min(100, Math.round(cpct))}%; background: {cpct >= 95 ? 'var(--gradient-usage-danger)' : cpct >= 80 ? 'var(--gradient-usage-warning)' : 'var(--gradient-usage)'}"></div>
			{/if}
		</div>
		<div class="text-[11px] text-ink-3 mt-2">연결됨 {attachedCount}개</div>
	</div>
	{#if showSnapshots}
		<!-- 스냅샷 -->
		<div class="bg-surface-base border border-line rounded-lg p-5">
			<div class="text-[11px] uppercase tracking-wider text-ink-3 font-medium mb-2">스냅샷</div>
			<div class="text-[26px] font-bold text-ink-0 leading-none mb-1">{snapshots.length}</div>
			<div class="text-[11px] text-ink-3">최근 24시간 {recentSnapshots.length}개</div>
		</div>
	{/if}
</div>
