<script lang="ts">
  import { t } from '$lib/i18n/ns/admin-network';

  let {
    search = $bindable(),
  }: {
    search: string;
  } = $props();
</script>

<div class="flex flex-wrap gap-3 mb-4">
  <input
    type="text"
    bind:value={search}
    placeholder={t('portsFilterBar.searchPlaceholder')}
    class="text-xs bg-surface-sunken border border-line-2 rounded px-3 py-1.5 text-ink-2 placeholder-ink-3 w-56"
  />
</div>
