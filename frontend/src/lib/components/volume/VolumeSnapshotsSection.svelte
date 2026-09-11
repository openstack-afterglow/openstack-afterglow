<script lang="ts">
  import { useVolumeDetailController, statusColor } from '$lib/stores/volumeDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import { formatStorage } from '$lib/utils/format';

  const s = useVolumeDetailController();
</script>

<div class="mb-4">
  <div class="flex items-center justify-between mb-2">
    <h3 class="text-xs text-ink-2 uppercase tracking-wide">스냅샷</h3>
    <button
      onclick={() => { s.showSnapshotForm = !s.showSnapshotForm; }}
      class="text-action-warm hover:text-action-warm-hover text-xs transition-colors"
    >+ 스냅샷 생성</button>
  </div>

  {#if s.showSnapshotForm}
    <div class="bg-surface-base border border-line-2 rounded-lg p-3 mb-3 space-y-2">
      <input
        bind:value={s.snapshotName}
        type="text"
        placeholder="스냅샷 이름"
        class="w-full bg-surface-sunken border border-line-2 rounded px-2 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
      />
      <input
        bind:value={s.snapshotDesc}
        type="text"
        placeholder="설명 (선택)"
        class="w-full bg-surface-sunken border border-line-2 rounded px-2 py-1.5 text-sm text-ink-0 focus:outline-none focus:border-action-warm"
      />
      {#if s.snapshotError}<p class="text-xs text-red-400">{s.snapshotError}</p>{/if}
      <div class="flex gap-2 justify-end">
        <button onclick={() => s.cancelSnapshot()} class="text-xs text-ink-2 hover:text-ink-0 transition-colors">취소</button>
        <Button onclick={() => s.createSnapshot()} disabled={s.creatingSnapshot || !s.snapshotName.trim()} size="sm">
          {s.creatingSnapshot ? '생성 중...' : '생성'}
        </Button>
      </div>
    </div>
  {/if}

  {#if s.snapshots.length === 0}
    <p class="text-xs text-ink-3">스냅샷이 없습니다.</p>
  {:else}
    <div class="space-y-1">
      {#each s.snapshots as snap}
        <div class="bg-surface-base rounded-lg border border-line-2 px-3 py-2 flex items-center justify-between text-xs">
          <div>
            <span class="text-ink-0 font-medium">{snap.name || snap.id.slice(0, 8)}</span>
            <span class="text-ink-3 ml-2">{formatStorage(snap.size)}</span>
            <span class="ml-2 px-1.5 py-0.5 rounded text-xs {statusColor[snap.status] ?? 'text-ink-2 bg-surface-sunken'}">{snap.status}</span>
          </div>
          <button
            onclick={() => s.deleteSnapshot(snap.id, snap.name)}
            disabled={s.deletingSnapshot === snap.id}
            class="text-red-400 hover:text-red-300 disabled:text-ink-3 transition-colors ml-2"
          >{s.deletingSnapshot === snap.id ? '...' : '삭제'}</button>
        </div>
      {/each}
    </div>
  {/if}
</div>
