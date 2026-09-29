<script lang="ts">
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  const s = useVolumeDetailController();
</script>

<div class="flex gap-2 flex-wrap">
  <Button onclick={() => s.openRenameModal()} size="sm" variant="secondary">이름 변경</Button>
  {#if s.volume!.status === 'available'}
    <Button onclick={() => s.openAttachModal()} size="sm">인스턴스에 연결</Button>
  {/if}
  <button
    onclick={() => s.deleteVolume()}
    disabled={!s.canDelete}
    class="px-3 py-1.5 text-xs bg-red-900/40 hover:bg-red-900/60 disabled:opacity-40 text-red-400 border border-red-900 rounded-lg transition-colors"
    title={s.volume!.attachments.length > 0 ? '연결된 볼륨은 삭제할 수 없습니다' : ''}
  >{s.deleting ? '삭제 중...' : '볼륨 삭제'}</button>
</div>
