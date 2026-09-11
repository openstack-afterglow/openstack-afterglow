<script lang="ts">
  import { useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  const s = useVolumeDetailController();
</script>

<div
  class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-[60]"
  onclick={() => s.closeAttachModal()}
  role="dialog"
  aria-modal="true"
  tabindex="-1"
  onkeydown={(e) => e.key === 'Escape' && s.closeAttachModal()}
>
  <div
    class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
    onclick={(e) => e.stopPropagation()}
    role="none"
    onkeydown={(e) => e.stopPropagation()}
  >
    <h3 class="text-base font-semibold text-ink-0 mb-4">인스턴스에 볼륨 연결</h3>
    <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">인스턴스 선택
      <select
        bind:value={s.attachInstanceId}
        class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5"
      >
        <option value="">-- 선택 --</option>
        {#each s.instances as inst}
          <option value={inst.id}>{inst.name || inst.id.slice(0, 8)} ({inst.status})</option>
        {/each}
      </select>
    </label>
    {#if s.attachError}<p class="text-xs text-red-400 mt-2">{s.attachError}</p>{/if}
    <div class="flex justify-end gap-3 mt-5">
      <button onclick={() => s.closeAttachModal()} class="text-sm text-ink-2 hover:text-ink-0 transition-colors">취소</button>
      <Button onclick={() => s.attachVolume()} disabled={s.attaching || !s.attachInstanceId}>
        {s.attaching ? '연결 중...' : '연결'}
      </Button>
    </div>
  </div>
</div>
