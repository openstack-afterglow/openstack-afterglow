<script lang="ts">
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

<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
  {#each libraries as lib}
    {@const prebuilt = fileStorages.find(s => s.library_name === lib.id && s.metadata?.union_type === 'prebuilt')}
    <div class="bg-surface-base border border-line-2 rounded-xl p-4">
      <div class="flex items-start justify-between mb-2">
        <div>
          <div class="font-medium text-ink-0 text-sm">{lib.name}</div>
          <div class="text-xs text-ink-3">v{lib.version}</div>
        </div>
        {#if prebuilt}
          <StatusChip status={prebuilt.status} />
        {:else}
          <span class="text-xs text-ink-3">미구축</span>
        {/if}
      </div>
      {#if prebuilt}
        <div class="text-xs text-ink-3 mb-3">
          File Storage ID: <span class="font-mono">{prebuilt.id.slice(0, 8)}...</span>
          {#if prebuilt.built_at}• {prebuilt.built_at.split('T')[0]}{/if}
        </div>
      {/if}
      <button
        onclick={() => onBuild(lib.id)}
        disabled={building === lib.id || !!prebuilt}
        class="w-full text-xs py-1.5 rounded-lg border transition-colors {prebuilt ? 'border-line-2 text-ink-3 cursor-not-allowed' : 'border-action-warm text-action-warm hover:bg-surface-selected/20'}"
      >
        {building === lib.id ? '생성 중...' : prebuilt ? '구축됨' : '파일 스토리지 생성'}
      </button>
    </div>
  {/each}
  {#if libraries.length === 0}
    <div class="col-span-2 text-ink-3 text-sm">라이브러리 정보를 불러올 수 없습니다</div>
  {/if}
</div>
