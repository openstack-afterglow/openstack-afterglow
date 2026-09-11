<script lang="ts">
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';

  const s = useVolumeDetailController();
</script>

{#if s.volume!.attachments.length > 0}
  <div class="mb-4">
    <h3 class="text-xs text-ink-2 uppercase tracking-wide mb-2">연결된 인스턴스</h3>
    <div class="space-y-1">
      {#each s.volume!.attachments as att}
        <div class="bg-surface-base rounded-lg border border-line-2 px-3 py-2 text-xs text-ink-2">
          <span class="font-mono">{(att as Record<string, unknown>).server_id as string ?? '-'}</span>
          {#if (att as Record<string, unknown>).device}
            <span class="text-ink-3 ml-2">{(att as Record<string, unknown>).device as string}</span>
          {/if}
        </div>
      {/each}
    </div>
  </div>
{/if}
