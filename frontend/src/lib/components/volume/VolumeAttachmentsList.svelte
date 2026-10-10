<script lang="ts">
  import { t } from '$lib/i18n/ns/volume';
  import { attachmentServerId, useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

  const s = useVolumeDetailController();
</script>

{#if s.volume!.attachments.length > 0}
  <div class="mb-4">
    <h3 class="text-xs text-ink-2 uppercase tracking-wide mb-2">{t('attachmentsList.title')}</h3>
    <ul class="space-y-1" aria-label={t('attachmentsList.title')}>
      {#each s.volume!.attachments as att}
        {@const serverId = attachmentServerId(att)}
        {@const instance = s.attachmentName(serverId)}
        {@const device = typeof att.device === 'string' ? att.device : ''}
        <li class="bg-surface-base rounded-lg border border-line-2 px-3 py-2 text-xs text-ink-2 flex items-start justify-between gap-3">
          <div class="min-w-0">
            {#if !serverId}
              <span class="text-ink-2">{t('attachmentsList.unknownInstance')}</span>
            {:else if instance.state === 'resolved'}
              <a href="/dashboard/instances/{serverId}" class="block truncate text-sm text-warm-text hover:text-warm-text-hover transition-colors">{instance.name}</a>
              <span class="block font-mono break-all">{serverId}</span>
            {:else if instance.state === 'loading'}
              <span class="inline-flex items-center gap-1.5 text-ink-2"><ActivityIndicator size="xs" tone="ink" />{t('attachmentsList.resolvingName')}</span>
              <span class="block font-mono break-all">{serverId}</span>
            {:else}
              <span class="block font-mono text-ink-0 break-all">{serverId}</span>
              <span class="block text-ink-2">{t('attachmentsList.nameUnavailable')}</span>
            {/if}
          </div>
          {#if device}
            <span class="shrink-0 font-mono text-ink-2">{device}</span>
          {/if}
        </li>
      {/each}
    </ul>
  </div>
{/if}
