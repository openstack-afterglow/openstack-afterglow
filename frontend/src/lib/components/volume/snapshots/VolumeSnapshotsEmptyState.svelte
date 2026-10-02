<script lang="ts">
 import { t } from '$lib/i18n/ns/volume';
 let { onCreate, onintent }: { onCreate: () => void; onintent?: () => void } = $props();
</script>

<div class="text-center py-20 text-ink-2">
  <div class="text-5xl mb-4">{t('snapshotsEmptyState.icon')}</div>
  <p class="text-lg">{t('snapshotsEmptyState.title')}</p>
  <button onclick={onCreate} onpointerenter={onintent} onfocus={onintent} class="text-warm-text hover:text-warm-text-hover text-sm mt-2 inline-block">{t('snapshotsEmptyState.createFirst')}</button>
</div>
