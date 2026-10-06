<script lang="ts">
  import { t } from '$lib/i18n/ns/network-resources';
  import { useLoadbalancerDetailController } from '$lib/stores/loadbalancerDetailController.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import { createPendingAction } from '$lib/components/network/pendingAction.svelte';

  const s = useLoadbalancerDetailController();
  const pending = createPendingAction();
  const creatingListener = $derived(pending.isActive('create', s.saving));
</script>

{#if s.showAddListener}
  <div class="mb-4 p-4 bg-surface-sunken/60 border border-line-2 rounded-lg grid grid-cols-1 @lg/panel:grid-cols-3 gap-2">
    <input
      bind:value={s.listenerForm.name}
      placeholder={t('lb.form.optionalName')}
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
      placeholder={t('lb.form.port')}
      class="bg-surface-sunken border border-line-2 rounded px-3 py-2 text-sm text-ink-1"
    />
    <Button onclick={() => pending.run('create', () => s.createListener())} disabled={s.saving} ariaBusy={creatingListener} class="col-span-2" size="sm">{#if creatingListener}<ActivityIndicator size="xs" tone="ink" />{/if}{creatingListener ? t('lb.actions.creating') : t('lb.actions.create')}</Button>
    <button onclick={() => s.toggleAddListener()} class="text-ink-2 hover:text-ink-1 text-sm px-2 text-center">{t('lb.actions.cancel')}</button>
  </div>
{/if}
