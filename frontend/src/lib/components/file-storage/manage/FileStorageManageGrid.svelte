<script lang="ts">
  import type { FileStorage } from '$lib/types/fileStorage';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';

  let {
    fileStorages,
  }: {
    fileStorages: FileStorage[];
  } = $props();
</script>

<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
  {#each fileStorages as fs}
    <div class="bg-surface-base border border-line rounded-lg p-5">
      <div class="flex items-center gap-2.5 mb-3">
        <div class="w-10 h-10 rounded-lg bg-teal-500/15 border border-teal-500/30 text-teal-400 flex items-center justify-center shrink-0">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          </svg>
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-ink-0 font-semibold text-sm font-mono truncate">{fs.name}</div>
          <div class="flex items-center gap-1.5 mt-0.5">
            {#if fs.metadata?.union_type}
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-surface-selected/40 text-action-warm border border-action-warm/50">{fs.metadata.union_type}</span>
            {/if}
            {#if fs.library_name}
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/40 text-violet-300 border border-violet-800/50 truncate">{fs.library_name}</span>
            {/if}
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 gap-2 mb-3">
        <div>
          <div class="text-[11px] uppercase tracking-wider font-medium text-ink-3">크기</div>
          <div class="text-ink-0 font-mono text-sm mt-0.5">{fs.size} GB</div>
        </div>
        <div>
          <div class="text-[11px] uppercase tracking-wider font-medium text-ink-3">상태</div>
          <div class="mt-0.5"><StatusChip status={fs.status} /></div>
        </div>
      </div>
      {#if fs.built_at}
        <div class="pt-3 border-t border-line">
          <div class="text-[11px] text-ink-3">빌드: {fs.built_at.split('T')[0]}</div>
        </div>
      {/if}
    </div>
  {/each}
</div>
