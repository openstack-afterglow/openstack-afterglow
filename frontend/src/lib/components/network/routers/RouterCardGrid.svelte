<script lang="ts">
  import type { Router } from '$lib/types/networks';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';

  let {
    routers,
    externalNetworkName,
    selectedIds,
    selectableIds,
    selectionDisabled,
    onToggleSelect,
    onToggleAll,
    onOpen,
  }: {
    routers: Router[];
    externalNetworkName: (id: string | null) => string;
    selectedIds: ReadonlySet<string>;
    selectableIds: ReadonlySet<string>;
    selectionDisabled: boolean;
    onToggleSelect: (id: string) => void;
    onToggleAll: () => void;
    onOpen: (id: string) => void;
  } = $props();
  const selectedCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
  const allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
  const indeterminate = $derived(selectedCount > 0 && !allSelected);
</script>

<div class="flex items-center justify-end mb-3">
  <SelectionToolbar
    label="라우터"
    ariaLabel="라우터 전체 선택"
    checked={allSelected}
    indeterminate={indeterminate}
    selectedCount={selectedCount}
    disabled={selectionDisabled || selectableIds.size === 0}
    onToggle={onToggleAll}
  />
</div>
<div class="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
  {#each routers as router (router.id)}
    <article
      class="resource-selection-surface router-card transition-colors"
      data-selected={selectedIds.has(router.id)}
    >
      <div class="flex items-center gap-2.5 mb-3.5">
        <SelectionCheckbox
          checked={selectedIds.has(router.id)}
          disabled={selectionDisabled}
          ariaLabel={`${router.name || router.id.slice(0, 12)} 선택`}
          onclick={() => onToggleSelect(router.id)}
        />
        <div class="router-card__icon w-10 h-10 rounded-lg flex items-center justify-center shrink-0">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="2" y1="12" x2="22" y2="12"/>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
          </svg>
        </div>
        <div class="flex-1 min-w-0">
          <div class="router-card__name text-[14px] font-semibold truncate">{router.name || router.id.slice(0, 12)}</div>
          <div class="router-card__subtitle text-[11px] mt-0.5">SNAT {router.external_gateway_network_id ? '활성' : '비활성'}</div>
        </div>
        <StatusChip status={router.status} />
      </div>
      <button type="button" onclick={() => onOpen(router.id)} class="router-card__detail ml-auto px-2.5 py-1 text-xs rounded-lg">상세</button>

      <div class="flex flex-col gap-2 text-[13px]">
        <div class="router-card__section flex items-center gap-3 p-2.5 rounded-lg">
          <div class="router-card__label text-[11px] uppercase tracking-wider font-medium w-16 shrink-0">외부</div>
          {#if router.external_gateway_network_id}
            <div class="router-card__gateway font-mono text-xs truncate">{externalNetworkName(router.external_gateway_network_id)}</div>
          {:else}
            <div class="router-card__empty text-xs">없음</div>
          {/if}
        </div>
        <div class="router-card__section flex items-start gap-3 p-2.5 rounded-lg">
          <div class="router-card__label text-[11px] uppercase tracking-wider font-medium w-16 pt-0.5 shrink-0">내부</div>
          <div class="flex-1 flex flex-wrap gap-1.5">
            {#if router.connected_subnet_ids.length === 0}
              <span class="router-card__empty text-xs">인터페이스 없음</span>
            {:else}
              {#each router.connected_subnet_ids as subnetId}
                <span class="router-card__subnet px-1.5 py-0.5 rounded text-[10px] font-mono">{subnetId.slice(0, 8)}…</span>
              {/each}
            {/if}
          </div>
        </div>
      </div>
    </article>
  {/each}
</div>

<style>
  .router-card {
    background-color: var(--color-surface-raised);
    border: 1px solid var(--color-line);
  }

  .router-card[data-selected='true'] {
    background-color: var(--accent-soft);
    border-color: var(--accent-ring);
  }

  .router-card__icon {
    color: var(--color-accent-2);
    background-color: color-mix(in oklab, var(--color-accent-2), transparent 85%);
    border: 1px solid color-mix(in oklab, var(--color-accent-2), transparent 70%);
  }

  .router-card__name {
    color: var(--color-ink-0);
  }

  .router-card__subtitle,
  .router-card__label {
    color: var(--color-ink-3);
  }

  .router-card__detail {
    color: var(--color-ink-1);
    border: 1px solid var(--color-line-2);
  }

  .router-card__detail:hover {
    color: var(--color-ink-0);
    border-color: var(--color-ink-3);
  }

  .router-card__section {
    background-color: var(--color-surface-sunken);
    border: 1px solid var(--color-line);
  }

  .router-card__gateway {
    color: var(--color-state-warning);
  }

  .router-card__empty {
    color: var(--color-ink-3);
  }

  .router-card__subnet {
    color: var(--color-ink-2);
    background-color: color-mix(in oklab, var(--color-surface-sunken), black 15%);
    border: 1px solid var(--color-line-2);
  }
</style>
