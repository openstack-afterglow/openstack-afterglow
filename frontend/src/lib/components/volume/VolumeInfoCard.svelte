<script lang="ts">
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import { formatStorage } from '$lib/utils/format';

  const s = useVolumeDetailController();
</script>

<div class="bg-surface-base rounded-xl border border-line-2 p-4 mb-4 space-y-2 text-sm">
  <div class="flex justify-between">
    <span class="text-ink-2">ID</span>
    <span class="text-ink-0 font-mono text-xs">{s.volume!.id}</span>
  </div>
  <div class="flex justify-between">
    <span class="text-ink-2">크기</span>
    <span class="text-ink-0">{formatStorage(s.volume!.size)}</span>
  </div>
  <div class="flex justify-between">
    <span class="text-ink-2">타입</span>
    <span class="text-ink-0">{s.volume!.volume_type ?? '-'}</span>
  </div>
  <div class="flex justify-between">
    <span class="text-ink-2">연결</span>
    <span class="text-ink-0">{s.volume!.attachments.length > 0 ? `${s.volume!.attachments.length}개 인스턴스` : '미연결'}</span>
  </div>
</div>
