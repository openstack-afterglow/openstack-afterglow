<script lang="ts">
  import type { Volume } from '$lib/types/volume';
  import type { Snippet } from 'svelte';

  const statusColor: Record<string, string> = {
    available:          'text-green-400 bg-green-900/30',
    in_use:             'text-action-warm bg-surface-selected/30',
    creating:           'text-action-warm bg-surface-selected/30',
    deleting:           'text-orange-400 bg-orange-900/30',
    error:              'text-red-400 bg-red-900/30',
    reserved:           'text-purple-400 bg-purple-900/30',
    attaching:          'text-cyan-400 bg-cyan-900/30',
    detaching:          'text-action-warm bg-surface-selected/30',
    'backing-up':       'text-indigo-400 bg-indigo-900/30',
    'restoring-backup': 'text-teal-400 bg-teal-900/30',
    downloading:        'text-sky-400 bg-sky-900/30',
    uploading:          'text-sky-400 bg-sky-900/30',
    extending:          'text-cyan-400 bg-cyan-900/30',
    error_deleting:     'text-rose-400 bg-rose-900/30',
    error_backing_up:   'text-rose-400 bg-rose-900/30',
    error_restoring:    'text-rose-400 bg-rose-900/30',
    error_extending:    'text-rose-400 bg-rose-900/30',
  };

  let {
    volume,
    deleting,
    onDelete,
    actions,
  }: {
    volume: Volume;
    deleting: boolean;
    onDelete: () => void;
    actions?: Snippet;
  } = $props();
</script>

<div class="flex items-start justify-between mb-6">
  <div>
    <h1 class="text-2xl font-bold text-ink-0">
      {#if volume.name}
        {volume.name}
      {:else}
        <span class="font-mono text-ink-2">{volume.id}</span>
      {/if}
    </h1>
    <span
      class="mt-2 inline-block px-2 py-0.5 rounded text-xs font-medium {statusColor[volume.status] ?? 'text-ink-2 bg-surface-sunken'}"
    >
      {volume.status}
    </span>
  </div>
  <div class="flex items-center gap-2">
    {@render actions?.()}
    <button
      onclick={onDelete}
      disabled={deleting || volume.attachments.length > 0}
      class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-sm px-3 py-1.5 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
      title={volume.attachments.length > 0 ? '연결된 볼륨은 삭제할 수 없습니다' : ''}
    >
      {deleting ? '삭제 중...' : '삭제'}
    </button>
  </div>
</div>
