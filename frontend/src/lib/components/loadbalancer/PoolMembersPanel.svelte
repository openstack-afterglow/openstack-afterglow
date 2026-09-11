<script lang="ts">
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  interface Props {
    poolId: string;
  }
  // poolId는 부모가 selectedPoolId === pool.id 분기에서 마운트할 때 식별용으로 전달
  // 실제 API 호출은 store의 selectedPoolId를 사용
  let { poolId: _poolId }: Props = $props();
	const poolId = $derived(_poolId);

  const s = useLoadbalancerDetailController();
</script>

<div class="mt-2 ml-4 bg-surface-sunken/30 rounded-lg p-4 border border-line-2" data-pool-id={poolId}>
  <div class="flex items-center justify-between mb-3">
    <span class="text-sm text-ink-2">멤버 ({s.selectedPoolMembers.length})</span>
    <button
      onclick={() => s.toggleAddMember()}
      class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
    >+ 멤버 추가</button>
  </div>

  {#if s.showAddMember}
    <div class="mb-3 grid grid-cols-1 @lg/panel:grid-cols-2 gap-2">
      <input
        bind:value={s.memberForm.address}
        placeholder="IP 주소"
        class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
      />
      <input
        bind:value={s.memberForm.protocol_port}
        type="number"
        min="1"
        max="65535"
        placeholder="포트"
        class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
      />
      <input
        bind:value={s.memberForm.weight}
        type="number"
        min="1"
        max="256"
        placeholder="가중치"
        class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
      />
      <Button onclick={() => s.addMember()} disabled={s.saving || !s.memberForm.address} size="sm">추가</Button>
      <button onclick={() => s.toggleAddMember()} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center rounded border border-line-2">취소</button>
    </div>
  {/if}

  {#if s.selectedPoolMembers.length === 0}
    <p class="text-xs text-ink-3">멤버가 없습니다.</p>
  {:else}
    <div class="space-y-1.5">
      {#each s.selectedPoolMembers as member}
        <div class="flex items-center justify-between bg-surface-sunken/50 rounded px-3 py-2">
          <div class="text-xs">
            <span class="text-ink-0 font-mono">{member.address}:{member.protocol_port}</span>
            <span class="ml-2 text-ink-3">가중치 {member.weight}</span>
            <span class="ml-2 {member.status === 'ACTIVE' ? 'text-green-400' : 'text-yellow-400'}">{member.status}</span>
          </div>
          <button onclick={() => s.removeMember(member.id)} disabled={s.saving} class="text-red-400 hover:text-red-300 text-xs">제거</button>
        </div>
      {/each}
    </div>
  {/if}
</div>
