<script lang="ts">
  import { t } from '$lib/i18n/ns/volume';
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import { formatStorage } from '$lib/utils/format';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';

  const s = useVolumeDetailController();
</script>

<ResponsiveTable class="mb-4 lg:mb-0">
  {#snippet cards()}
    <CompactResourceCard>
      <div class="flex items-start justify-between gap-2 min-w-0">
        <span class="min-w-0 font-medium break-all">{s.volume!.name || t('infoCard.unnamed')}</span>
        <StatusChip status={s.volume!.status} />
      </div>
      <dl>
        <div><dt>{t('infoCard.size')}</dt><dd>{formatStorage(s.volume!.size)}</dd></div>
        <div><dt>{t('infoCard.type')}</dt><dd>{s.volume!.volume_type ?? '-'}</dd></div>
        <div><dt>{t('infoCard.attachments')}</dt><dd>{s.volume!.attachments.length > 0 ? t('infoCard.instanceCount', { count: s.volume!.attachments.length }) : t('infoCard.unattached')}</dd></div>
      </dl>
      {#snippet details()}
        <p class="font-mono break-all">{s.volume!.id}</p>
        <dl><div><dt>{t('infoCard.bootable')}</dt><dd>{s.volume!.bootable ? t('infoCard.yes') : t('infoCard.no')}</dd></div></dl>
      {/snippet}
    </CompactResourceCard>
  {/snippet}
<div class="bg-surface-base rounded-xl border border-line-2 p-4 mb-4 space-y-2 text-sm">
  <div class="flex justify-between gap-4">
    <span class="text-ink-2 shrink-0">{t('infoCard.name')}</span>
    <span class="text-ink-0 text-right break-all">{s.volume!.name || t('infoCard.unnamed')}</span>
  </div>
  <div class="flex justify-between gap-4">
    <span class="text-ink-2 shrink-0">ID</span>
    <span class="text-ink-0 font-mono text-xs text-right break-all">{s.volume!.id}</span>
  </div>
  <div class="flex justify-between">
    <span class="text-ink-2">{t('infoCard.size')}</span>
    <span class="text-ink-0">{formatStorage(s.volume!.size)}</span>
  </div>
  <div class="flex justify-between">
    <span class="text-ink-2">{t('infoCard.type')}</span>
    <span class="text-ink-0">{s.volume!.volume_type ?? '-'}</span>
  </div>
  <div class="flex justify-between">
    <span class="text-ink-2">{t('infoCard.bootable')}</span>
    <span class="text-ink-0">{s.volume!.bootable ? t('infoCard.yes') : t('infoCard.no')}</span>
  </div>
  <div class="flex justify-between">
    <span class="text-ink-2">{t('infoCard.attachments')}</span>
    <span class="text-ink-0">{s.volume!.attachments.length > 0 ? t('infoCard.instanceCount', { count: s.volume!.attachments.length }) : t('infoCard.unattached')}</span>
  </div>
</div>
</ResponsiveTable>
