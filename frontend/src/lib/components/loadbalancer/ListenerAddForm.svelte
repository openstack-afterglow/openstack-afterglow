<script lang="ts">
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  const s = useLoadbalancerDetailController();
</script>

{#if s.showAddListener}
  <div class="mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg grid grid-cols-1 @lg/panel:grid-cols-3 gap-2">
    <input
      bind:value={s.listenerForm.name}
      placeholder="이름 (선택)"
      class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
    />
    <select
      bind:value={s.listenerForm.protocol}
      class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
    >
      {#each ['HTTP', 'HTTPS', 'TCP', 'UDP'] as p}
        <option value={p}>{p}</option>
      {/each}
    </select>
    <input
      bind:value={s.listenerForm.protocol_port}
      type="number"
      min="1"
      max="65535"
      placeholder="포트"
      class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
    />
    <Button onclick={() => s.createListener()} disabled={s.saving} class="col-span-2" size="sm">생성</Button>
    <button onclick={() => s.toggleAddListener()} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center">취소</button>
  </div>
{/if}
