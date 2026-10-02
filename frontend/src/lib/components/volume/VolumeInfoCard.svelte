<script lang="ts">
  import { t } from '$lib/i18n/ns/volume';
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import { formatStorage } from '$lib/utils/format';

  const s = useVolumeDetailController();
</script>

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
