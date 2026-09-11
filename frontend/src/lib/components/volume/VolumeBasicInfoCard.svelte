<script lang="ts">
  import type { Volume } from '$lib/types/volume';
  import { formatStorage } from '$lib/utils/format';

  let { volume }: { volume: Volume } = $props();
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
  <h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide mb-4">기본 정보</h2>
  <dl class="grid grid-cols-2 gap-x-8 gap-y-3">
    <div>
      <dt class="text-xs text-ink-3 mb-0.5">ID</dt>
      <dd class="text-sm text-ink-2 font-mono">{volume.id}</dd>
    </div>
    <div>
      <dt class="text-xs text-ink-3 mb-0.5">크기</dt>
      <dd class="text-sm text-ink-2">{formatStorage(volume.size)}</dd>
    </div>
    <div>
      <dt class="text-xs text-ink-3 mb-0.5">볼륨 타입</dt>
      <dd class="text-sm text-ink-2">{volume.volume_type ?? '-'}</dd>
    </div>
  </dl>
</div>
