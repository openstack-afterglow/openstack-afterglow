<script lang="ts">
  import type { Router } from '$lib/types/networks';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
  import Button from '$lib/components/ui/Button.svelte';

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
          disabled={selectionDisabled || !selectableIds.has(router.id)}
          unavailable={!selectableIds.has(router.id)}
          title={!selectableIds.has(router.id) ? '현재 프로젝트가 소유한 라우터만 선택할 수 있습니다' : undefined}
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
          <div class="router-card__name text-sm font-semibold truncate">{router.name || router.id.slice(0, 12)}</div>
          <div class="router-card__subtitle text-xs mt-0.5">SNAT {router.external_gateway_network_id ? '활성' : '비활성'}</div>
        </div>
        <StatusChip status={router.status} />
      </div>
      <div class="flex justify-end">
        <Button variant="outline" size="xs" onclick={() => onOpen(router.id)}>상세</Button>
      </div>

      <div class="flex flex-col gap-2">
        <div class="router-card__section flex items-center gap-3 p-2.5 rounded-lg">
          <div class="router-card__label text-xs uppercase tracking-wider font-medium w-16 shrink-0">외부</div>
          {#if router.external_gateway_network_id}
            <div class="router-card__gateway font-mono text-xs truncate">{externalNetworkName(router.external_gateway_network_id)}</div>
          {:else}
            <div class="router-card__empty text-xs">없음</div>
          {/if}
        </div>
        <div class="router-card__section flex items-start gap-3 p-2.5 rounded-lg">
          <div class="router-card__label text-xs uppercase tracking-wider font-medium w-16 pt-0.5 shrink-0">내부</div>
          <div class="flex-1 flex flex-wrap gap-1.5">
            {#if router.connected_subnet_ids.length === 0}
              <span class="router-card__empty text-xs">인터페이스 없음</span>
            {:else}
              {#each router.connected_subnet_ids as subnetId}
                <span class="router-card__subnet px-1.5 py-0.5 rounded text-xs font-mono">{subnetId.slice(0, 8)}…</span>
              {/each}
            {/if}
          </div>
        </div>
      </div>
    </article>
  {/each}
</div>

<style>
  /* 같은 도메인의 다른 리소스 카드(NetworksTableCard, FileStorageCard, BucketCardGrid)와
     동일한 껍데기: base 표면 + radius-lg + 20px 안쪽 여백. raised 는 모달·팝오버 전용이다. */
  .router-card {
    background-color: var(--color-surface-base);
    border: 1px solid var(--color-line);
    border-radius: var(--radius-lg);
    padding: 1.25rem;
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
    color: var(--color-ink-2);
  }

  .router-card__section {
    background-color: var(--color-surface-sunken);
    border: 1px solid var(--color-line);
  }

  /* 게이트웨이 네트워크 이름은 식별자이지 경고 상태가 아니다. 한 색은 한 뜻만 가진다. */
  .router-card__gateway {
    color: var(--color-ink-1);
  }

  .router-card__empty {
    color: var(--color-ink-2);
  }

  .router-card__subnet {
    color: var(--color-ink-2);
    background-color: var(--color-surface-sunken);
    border: 1px solid var(--color-line-2);
  }
</style>
