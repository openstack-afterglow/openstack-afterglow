<script lang="ts">
  import { t } from '$lib/i18n/ns/volume';
  import { useVolumeDetailController, statusColor } from '$lib/stores/volumeDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { formatStorage } from '$lib/utils/format';

  const s = useVolumeDetailController();
</script>

<div class="mb-4">
  <div class="flex items-center justify-between mb-2">
    <h3 class="text-xs text-ink-2 uppercase tracking-wide">{t('snapshotsSection.title')}</h3>
    <button
      onclick={() => { s.showSnapshotForm = !s.showSnapshotForm; }}
      class="text-warm-text hover:text-warm-text-hover text-xs transition-colors"
    >{t('snapshotsSection.createSnapshot')}</button>
  </div>

  {#if s.showSnapshotForm}
    <div class="bg-surface-base border border-line-2 rounded-lg p-3 mb-3 space-y-2">
      <input
        bind:value={s.snapshotName}
        type="text"
        placeholder={t('snapshotsSection.namePlaceholder')}
        class="w-full bg-surface-sunken border border-line-2 rounded px-2 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
      />
      <input
        bind:value={s.snapshotDesc}
        type="text"
        placeholder={t('snapshotsSection.descriptionPlaceholder')}
        class="w-full bg-surface-sunken border border-line-2 rounded px-2 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
      />
      {#if s.snapshotError}<p class="text-xs text-red-400">{s.snapshotError}</p>{/if}
      <div class="flex gap-2 justify-end">
        <button onclick={() => s.cancelSnapshot()} class="text-xs text-ink-2 hover:text-ink-0 transition-colors">{t('snapshotsSection.cancel')}</button>
        <Button onclick={() => s.createSnapshot()} disabled={s.creatingSnapshot || !s.snapshotName.trim()} size="sm">
          {#if s.creatingSnapshot}<ActivityIndicator size="xs" tone="ink" />{/if}{s.creatingSnapshot ? t('snapshotsSection.creating') : t('snapshotsSection.create')}
        </Button>
      </div>
    </div>
  {/if}

  {#if s.snapshots.length === 0}
    <p class="text-xs text-ink-2">{t('snapshotsSection.empty')}</p>
  {:else}
    <div class="space-y-1">
      {#each s.snapshots as snap}
        <div class="bg-surface-base rounded-lg border border-line-2 px-3 py-2 flex items-center justify-between text-xs">
          <div>
            <span class="text-ink-0 font-medium">{snap.name || snap.id.slice(0, 8)}</span>
            <span class="text-ink-2 ml-2">{formatStorage(snap.size)}</span>
            <span class="ml-2 px-1.5 py-0.5 rounded text-xs {statusColor[snap.status] ?? 'text-ink-2 bg-surface-sunken'}">{snap.status}</span>
          </div>
          <button
            onclick={() => s.deleteSnapshot(snap.id, snap.name)}
            disabled={s.deletingSnapshot === snap.id}
            class="inline-flex items-center gap-1.5 text-state-danger-text hover:opacity-80 disabled:text-ink-3 transition-colors ml-2"
          >{#if s.deletingSnapshot === snap.id}<ActivityIndicator size="xs" tone="danger" />{t('snapshotListTable.deleting')}{:else}{t('snapshotsSection.delete')}{/if}</button>
        </div>
      {/each}
    </div>
  {/if}
</div>
