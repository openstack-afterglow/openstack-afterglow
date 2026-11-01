<script lang="ts">
	import { t } from '$lib/i18n/ns/volume';
	import type { Snapshot, Volume } from '$lib/types/volume';

	interface QuotaItem { limit: number; in_use: number; }
	interface VolumeQuotas { storage: { volumes: QuotaItem; gigabytes: QuotaItem; }; }

	let {
		volumes,
		snapshots,
		quotas,
		showSnapshots = true,
		snapshotsKnown = true,
	}: {
		volumes: Volume[];
		snapshots: Snapshot[];
		quotas: VolumeQuotas | null;
		showSnapshots?: boolean;
		snapshotsKnown?: boolean;
	} = $props();

	let totalGb = $derived(volumes.reduce((s, v) => s + v.size, 0));
	let attachedCount = $derived(volumes.filter((v) => v.attachments.length > 0).length);

</script>

<section class="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-line bg-surface-base px-4 py-3 text-sm" aria-label={t('page.provisioned')}>
	<p class="text-ink-2">{t('page.provisioned')} <strong class="font-medium tabular-nums text-ink-0">{totalGb} GiB</strong></p>
	<p class="text-ink-2">{t('summaryCards.volumes')} <strong class="font-medium tabular-nums text-ink-0">{volumes.length}</strong></p>
	<p class="text-ink-2">{t('summaryCards.attachedCount', { count: attachedCount })}</p>
	<p class="text-ink-2">{t('page.storageLimit')} <strong class="font-medium tabular-nums text-ink-0">{quotas === null ? '—' : quotas.storage.gigabytes.limit === -1 ? t('summaryCards.unlimitedStorage') : `${quotas.storage.gigabytes.limit} GiB`}</strong></p>
	{#if showSnapshots}<p class="text-ink-2">{t('summaryCards.snapshots')} <strong class="font-medium tabular-nums text-ink-0">{snapshotsKnown ? snapshots.length : '—'}</strong></p>{/if}
</section>

