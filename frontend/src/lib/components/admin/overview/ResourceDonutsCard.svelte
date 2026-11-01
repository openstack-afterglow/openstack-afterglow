<script lang="ts">
	import { t } from '$lib/i18n/ns/admin-ops';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import QuotaDonut from '$lib/components/QuotaDonut.svelte';
	import type { Overview } from '$lib/types/adminOverview';

	let { overview }: { overview: Overview } = $props();
	function quantity(value: number | null | undefined): string {
		return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString(intlLocale(), { maximumFractionDigits: 1 });
	}
	function ratio(used: number | null, total: number | null): string {
		return used === null || total === null || total <= 0 ? '—' : `${(used / total * 100).toLocaleString(intlLocale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
	}
</script>

<section class="bg-surface-base border border-line rounded-lg p-5" aria-labelledby="overview-capacity-title">
	<div class="mb-4 flex flex-wrap items-baseline justify-between gap-2">
		<h2 id="overview-capacity-title" class="text-ink-0 text-[15px] font-semibold">{t('overview.resources.title')}</h2>
		{#if overview.collected_at}<time datetime={overview.collected_at} class="text-xs text-ink-2">{new Date(overview.collected_at).toLocaleString(intlLocale())}</time>{/if}
	</div>
	<div class="grid grid-cols-1 gap-6 sm:grid-cols-3">
		<div class="flex flex-col items-center gap-3">
			<QuotaDonut label={t('overview.capacity.cpu')} used={overview.vcpus.used} limit={overview.vcpus.total} tone="info" size="lg" />
			<dl class="w-full space-y-1 text-sm"><div class="flex justify-between gap-2"><dt class="text-ink-2">{t('overview.capacity.configured')}</dt><dd class="tabular-nums text-ink-1">{quantity(overview.vcpus.allowed)}</dd></div><div class="flex justify-between gap-2"><dt class="text-ink-2">{t('overview.capacity.configuredRatio')}</dt><dd class="tabular-nums text-ink-1">{ratio(overview.vcpus.used, overview.vcpus.allowed)}</dd></div></dl>
		</div>
		<div class="flex flex-col items-center gap-3">
			<QuotaDonut label={t('overview.capacity.memory')} used={overview.ram_gb.used} limit={overview.ram_gb.total} unit="GiB" tone="info" size="lg" />
			<p class="text-xs text-ink-2">{t('overview.capacity.nova')}</p>
		</div>
		<div class="flex flex-col items-center gap-3">
			<QuotaDonut label={t('overview.capacity.storage')} used={overview.disk_gb.used} limit={overview.disk_gb.total} unit="GiB" tone="info" size="lg" />
			<dl class="w-full space-y-1 text-sm"><div class="flex justify-between gap-2"><dt class="text-ink-2">{t('overview.capacity.volumes')}</dt><dd class="tabular-nums text-ink-1">{quantity(overview.disk_gb.volumes)} GiB</dd></div><div class="flex justify-between gap-2"><dt class="text-ink-2">{t('overview.capacity.images')}</dt><dd class="tabular-nums text-ink-1">{quantity(overview.disk_gb.images)} GiB</dd></div></dl>
		</div>
	</div>
	<details class="mt-4 border-t border-line pt-3 text-sm text-ink-2">
		<summary class="cursor-pointer text-ink-1">{t('overview.capacity.definitions')}</summary>
		<ul class="mt-2 list-disc space-y-2 pl-5"><li>{t('overview.capacity.cpuSource')}</li><li>{t('overview.capacity.memorySource')}</li><li>{t('overview.capacity.storageSource')}</li><li>{t('overview.capacity.collectionSource')}</li></ul>
	</details>
</section>
