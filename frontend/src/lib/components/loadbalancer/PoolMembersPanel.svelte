<script lang="ts">
  import { t } from '$lib/i18n/ns/network-resources';
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { createPendingAction } from '$lib/components/network/pendingAction.svelte';
  import { CompactResourceCard, StatusChip } from '$lib/components/ui';

  interface Props {
    poolId: string;
  }
  // poolId는 부모가 selectedPoolId === pool.id 분기에서 마운트할 때 식별용으로 전달
  // 실제 API 호출은 store의 selectedPoolId를 사용
  let { poolId: _poolId }: Props = $props();
	const poolId = $derived(_poolId);

  const s = useLoadbalancerDetailController();
  const pending = createPendingAction();
  const addingMember = $derived(pending.isActive('add', s.saving));
</script>

<div class="mt-2 lg:ml-4 bg-surface-sunken/30 rounded-lg p-3 lg:p-4 border border-line-2 min-w-0" data-pool-id={poolId}>
  <div class="flex items-center justify-between mb-3">
    <span class="text-sm text-ink-2">{t('lb.members.title', { count: s.selectedPoolMembers.length })}</span>
    {#if s.canMutate}
    <button
      onclick={() => s.toggleAddMember()}
      class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors"
    >{t('lb.members.addWithPlus')}</button>
    {/if}
  </div>

  {#if s.showAddMember && s.canMutate}
    <div class="mb-3 grid grid-cols-1 @lg/panel:grid-cols-2 gap-2">
      <input
        bind:value={s.memberForm.address}
        placeholder={t('lb.form.ipAddress')}
        class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
      />
      <input
        bind:value={s.memberForm.protocol_port}
        type="number"
        min="1"
        max="65535"
        placeholder={t('lb.form.port')}
        class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
      />
      <input
        bind:value={s.memberForm.weight}
        type="number"
        min="1"
        max="256"
        placeholder={t('lb.form.weight')}
        class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
      />
      <Button onclick={() => pending.run('add', () => s.addMember())} disabled={s.saving || !s.memberForm.address} ariaBusy={addingMember} size="sm">{#if addingMember}<ActivityIndicator size="xs" tone="ink" />{/if}{addingMember ? t('lb.actions.adding') : t('lb.actions.add')}</Button>
      <button onclick={() => s.toggleAddMember()} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center rounded border border-line-2">{t('lb.actions.cancel')}</button>
    </div>
  {/if}

  {#if s.membersError}
    <p role="alert" class="text-state-danger-text text-sm">{s.membersError}</p>
  {:else if s.selectedPoolMembers.length === 0}
    <p class="text-xs text-ink-2">{t('lb.members.empty')}</p>
  {:else}
    <div class="space-y-1.5">
      {#each s.selectedPoolMembers as member}
        {@const removingMember = pending.isActive(`remove:${member.id}`, s.saving)}
        <CompactResourceCard>
          <div class="flex items-center gap-2"><strong class="min-w-0 flex-1 font-mono break-all">{member.address}:{member.protocol_port}</strong><StatusChip status={member.status} /></div>
          <p class="text-xs text-ink-2">{t('lb.members.weight', { weight: member.weight })}</p>
          {#snippet actions()}{#if s.canMutate}<Button size="sm" variant="danger-outline" onclick={() => pending.run(`remove:${member.id}`, () => s.removeMember(member.id))} disabled={s.saving} ariaBusy={removingMember}>{#if removingMember}<ActivityIndicator size="xs" tone="danger" />{/if}{removingMember ? t('lb.actions.removing') : t('lb.actions.remove')}</Button>{/if}{/snippet}
        </CompactResourceCard>
      {/each}
    </div>
  {/if}
</div>
