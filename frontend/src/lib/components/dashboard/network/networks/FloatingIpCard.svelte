<script lang="ts">
  import { t } from '$lib/i18n/ns/network-pages';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
  import type { FloatingIp } from '$lib/types/networks';

  let {
    floatingIps,
    hasExternalNetwork,
    selectedIds,
    selectableIds,
    selectionDisabled,
    onToggleSelect,
    onToggleAll,
    onAllocateClick,
  }: {
    floatingIps: FloatingIp[];
    hasExternalNetwork: boolean;
    selectedIds: ReadonlySet<string>;
    selectableIds: ReadonlySet<string>;
    selectionDisabled: boolean;
    onToggleSelect: (id: string) => void;
    onToggleAll: () => void;
    onAllocateClick: () => void;
  } = $props();

  const selectedCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
  const allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
  const indeterminate = $derived(selectedCount > 0 && !allSelected);
</script>

<div class="bg-surface-base border border-line rounded-lg p-5">
  <div class="flex items-center mb-3.5">
    <div class="flex items-center gap-3">
      <div class="text-ink-0 text-[15px] font-semibold">{t('floatingIpCard.title')}</div>
      {#if floatingIps.length > 0}
        <SelectionToolbar
          label={t('floatingIpCard.title')}
          ariaLabel={t('floatingIpCard.selectAll')}
          checked={allSelected}
          indeterminate={indeterminate}
          selectedCount={selectedCount}
          disabled={selectionDisabled || selectableIds.size === 0}
          onToggle={onToggleAll}
        />
      {/if}
    </div>
    <div class="ml-auto flex gap-2">
      <button
        onclick={onAllocateClick}
        disabled={!hasExternalNetwork}
        class="px-3 py-1.5 text-[13px] bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm font-medium rounded-lg transition-colors"
        title={!hasExternalNetwork ? t('floatingIpCard.noExternal') : t('floatingIpCard.allocate')}
      >{t('floatingIpCard.allocateButton')}</button>
    </div>
  </div>
  {#if floatingIps.length === 0}
    <div class="text-center py-8 text-ink-2 text-sm">{t('floatingIpCard.empty')}</div>
  {:else}
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
      {#each floatingIps as fip (fip.id)}
        <div
          class="resource-selection-surface bg-[#0B1220] border border-line rounded-lg p-3 flex items-center gap-3"
          data-selected={selectedIds.has(fip.id)}
        >
          <SelectionCheckbox
            checked={selectedIds.has(fip.id)}
            disabled={selectionDisabled}
            ariaLabel={t('floatingIpCard.select', { address: fip.floating_ip_address })}
            onclick={() => onToggleSelect(fip.id)}
          />
          <div class="flex-1 min-w-0">
            <div class="font-mono text-[13px] text-ink-0">{fip.floating_ip_address}</div>
            <div class="text-xs text-ink-2 mt-0.5 truncate">
              {fip.fixed_ip_address ? '→ ' + fip.fixed_ip_address : t('floatingIpCard.unassigned')}
            </div>
          </div>
          <StatusChip status={fip.status} />
        </div>
      {/each}
    </div>
  {/if}
</div>
