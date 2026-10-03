<script lang="ts">
  import { attachmentServerId, useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';

  const s = useVolumeDetailController();
</script>

{#if s.volume!.attachments.length > 0}
  <div class="mb-4">
    <h3 class="text-xs text-ink-2 uppercase tracking-wide mb-2">연결된 인스턴스</h3>
    <ul class="space-y-1" aria-label="연결된 인스턴스">
      {#each s.volume!.attachments as att}
        {@const serverId = attachmentServerId(att)}
        {@const instance = s.attachmentName(serverId)}
        {@const device = typeof att.device === 'string' ? att.device : ''}
        <li class="bg-surface-base rounded-lg border border-line-2 px-3 py-2 text-xs text-ink-2 flex items-start justify-between gap-3">
          <div class="min-w-0">
            {#if !serverId}
              <span class="text-ink-2">알 수 없는 인스턴스</span>
            {:else if instance.state === 'resolved'}
              <a href="/dashboard/instances/{serverId}" class="block truncate text-sm text-warm-text hover:text-warm-text-hover transition-colors">{instance.name}</a>
              <span class="block font-mono break-all">{serverId}</span>
            {:else if instance.state === 'loading'}
              <span class="block text-ink-2">이름 확인 중…</span>
              <span class="block font-mono break-all">{serverId}</span>
            {:else}
              <span class="block font-mono text-ink-0 break-all">{serverId}</span>
              <span class="block text-ink-2">인스턴스 이름을 확인할 수 없음</span>
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
