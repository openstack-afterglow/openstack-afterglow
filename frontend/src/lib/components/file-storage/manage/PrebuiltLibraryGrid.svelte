<script lang="ts">
  import { t } from '$lib/i18n/ns/file-storage';
  import RichText from '$lib/i18n/RichText.svelte';
  import type { FileStorage } from '$lib/types/fileStorage';
  import type { LibraryConfig } from '$lib/types/library';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';

  let {
    libraries,
    fileStorages,
    building,
    onBuild,
  }: {
    libraries: LibraryConfig[];
    fileStorages: FileStorage[];
    building: string | null;
    onBuild: (libraryId: string) => Promise<void>;
  } = $props();
</script>

{#snippet storageId(text: string)}<span class="font-mono">{text}</span>{/snippet}

<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
  {#each libraries as lib}
    {@const prebuilt = fileStorages.find(s => s.library_name === lib.id && s.metadata?.union_type === 'prebuilt')}
    <div class="bg-surface-base border border-line-2 rounded-xl p-4">
      <div class="flex items-start justify-between mb-2">
        <div>
          <div class="font-medium text-ink-0 text-sm">{lib.name}</div>
          <div class="text-xs text-ink-2">v{lib.version}</div>
        </div>
        {#if prebuilt}
          <StatusChip status={prebuilt.status} />
        {:else}
          <span class="text-xs text-ink-2">{t('prebuiltGrid.notBuilt')}</span>
        {/if}
      </div>
      {#if prebuilt}
        <div class="text-xs text-ink-2 mb-3">
          <RichText segments={t.rich('prebuiltGrid.storageId', { id: prebuilt.id.slice(0, 8) })} tags={{ id: storageId }} />
          {#if prebuilt.built_at}• {prebuilt.built_at.split('T')[0]}{/if}
        </div>
      {/if}
      <button
        onclick={() => onBuild(lib.id)}
        disabled={building === lib.id || !!prebuilt}
        class="w-full text-xs py-1.5 rounded-lg border transition-colors {prebuilt ? 'border-line-2 text-ink-2 cursor-not-allowed' : 'border-action-warm text-warm-text hover:bg-surface-selected/20'}"
      >
        {building === lib.id ? t('actions.creating') : prebuilt ? t('prebuiltGrid.built') : t('list.createCta')}
      </button>
    </div>
  {/each}
  {#if libraries.length === 0}
    <div class="col-span-2 text-ink-2 text-sm">{t('prebuiltGrid.librariesUnavailable')}</div>
  {/if}
</div>
