<script lang="ts">
  import { t } from '$lib/i18n/ns/drover';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import { untrack } from 'svelte';

  const s = useK3sClusterDetailController();

  $effect(() => {
    if (s.isActive) {
      untrack(() => s.loadNamespaces());
    }
  });
</script>

<div class="flex items-center gap-2 mb-3">
  <span class="text-xs text-ink-2">{t('namespace.label')}</span>
  <select
    bind:value={s.selectedNamespace}
    onchange={() => { s.loadConfigMaps(); s.loadSecrets(); }}
    disabled={s.namespaces.length === 0}
    class="bg-surface-sunken border border-line-2 text-ink-1 text-xs rounded px-2 py-1 focus:outline-none focus:border-action-warm"
  >
    {#each s.namespaces as ns}
      <option value={ns}>{ns}</option>
    {/each}
  </select>
</div>
