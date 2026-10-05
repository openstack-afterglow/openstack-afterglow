<script lang="ts">
  import { t } from '$lib/i18n/ns/network-resources';
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  const s = useLoadbalancerDetailController();
</script>

{#if s.showAddPool}
  <div class="mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg grid grid-cols-1 @lg/panel:grid-cols-3 gap-2">
    <input
      bind:value={s.poolForm.name}
      placeholder={t('lb.form.optionalName')}
      class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
    />
    <select
      bind:value={s.poolForm.protocol}
      class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
    >
      {#each ['HTTP', 'HTTPS', 'TCP', 'UDP'] as p}
        <option value={p}>{p}</option>
      {/each}
    </select>
    <select
      bind:value={s.poolForm.lb_algorithm}
      class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
    >
      {#each ['ROUND_ROBIN', 'LEAST_CONNECTIONS', 'SOURCE_IP'] as a}
        <option value={a}>{t('lb.algorithm.label', { algorithm: a })}</option>
      {/each}
    </select>
    <Button onclick={() => s.createPool()} disabled={s.saving} class="col-span-2" size="sm">{t('lb.actions.create')}</Button>
    <button onclick={() => s.toggleAddPool()} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center">{t('lb.actions.cancel')}</button>
  </div>
{/if}
