<script lang="ts">
  import type { DbInstance } from '$lib/types/database';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';

  let {
    instances,
    refreshing,
    restarting,
    deleting,
    selectedIds = new Set<string>(),
    selectableIds = new Set<string>(),
    selectionDisabled = false,
    onToggleSelect = () => {},
    onToggleAll = () => {},
    onOpen,
    onRestart,
    onDelete,
  }: {
    instances: DbInstance[];
    refreshing: boolean;
    restarting: string | null;
    deleting: string | null;
    selectedIds?: ReadonlySet<string>;
    selectableIds?: ReadonlySet<string>;
    selectionDisabled?: boolean;
    onToggleSelect?: (id: string) => void;
    onToggleAll?: () => void;
    onOpen: (id: string) => void;
    onRestart: (id: string, name: string) => Promise<void>;
    onDelete: (id: string, name: string) => Promise<void>;
  } = $props();
  const selectableCount = $derived(selectableIds.size);
  const selectedSelectableCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
  const allSelected = $derived(selectableCount > 0 && selectedSelectableCount === selectableCount);
  const indeterminate = $derived(selectedSelectableCount > 0 && !allSelected);
</script>

<div class="overflow-x-auto">
  <table class="w-full text-sm">
    <thead>
      <tr class="db-instances-table__head text-xs uppercase tracking-wide">
        <th class="text-left py-3 px-3"><div class="inline-flex items-center gap-2"><SelectionCheckbox checked={allSelected} indeterminate={indeterminate} disabled={selectionDisabled} ariaLabel="전체 DB 인스턴스 선택" onclick={onToggleAll} /><span>전체 선택</span><span class="db-instances-table__selection-count normal-case" aria-live="polite">{selectedSelectableCount}개 선택됨</span></div></th>
        <th class="text-left py-3 px-4 font-medium">이름</th>
        <th class="text-left py-3 px-4 font-medium">상태</th>
        <th class="text-left py-3 px-4 font-medium">Datastore</th>
        <th class="text-left py-3 px-4 font-medium">크기 (GB)</th>
        <th class="text-left py-3 px-4 font-medium">생성일</th>
        <th class="text-right py-3 px-4 font-medium">액션</th>
      </tr>
    </thead>
    <tbody>
      {#each instances as inst (inst.id)}
        <tr class="resource-selection-surface db-instances-table__row transition-colors" data-selected={selectedIds.has(inst.id)}>
          <td class="py-3 px-3"><SelectionCheckbox checked={selectedIds.has(inst.id)} disabled={selectionDisabled || !selectableIds.has(inst.id)} ariaLabel={`${inst.name} 선택`} onclick={() => onToggleSelect(inst.id)} /></td>
          <td class="py-3 px-4"><button onclick={() => onOpen(inst.id)} class="db-instances-table__name font-medium text-left max-md:block max-md:max-w-[66vw] max-md:truncate" title={inst.name}>{inst.name}</button></td>
          <td class="py-3 px-4"><StatusChip status={inst.status} /></td>
          <td class="db-instances-table__detail py-3 px-4">{inst.datastore?.type ?? '-'} {inst.datastore?.version ?? ''}</td>
          <td class="db-instances-table__detail py-3 px-4">{inst.size || '-'}</td>
          <td class="db-instances-table__selection-count py-3 px-4 text-xs">{inst.created_at ? inst.created_at.slice(0, 10) : '-'}</td>
          <td class="py-3 px-4 text-right">
            <div class="flex justify-end gap-1">
              <button onclick={() => onRestart(inst.id, inst.name)} disabled={restarting === inst.id || selectionDisabled} class="db-instances-table__action db-instances-table__restart text-xs px-2 py-1 rounded">{restarting === inst.id ? '...' : '재시작'}</button>
              <button onclick={(e) => { e.stopPropagation(); onDelete(inst.id, inst.name); }} disabled={deleting === inst.id || selectionDisabled} class="db-instances-table__action db-instances-table__delete text-xs px-2 py-1 rounded">{deleting === inst.id ? '...' : '삭제'}</button>
            </div>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .db-instances-table__head {
    border-bottom: 1px solid var(--color-line);
    color: var(--color-ink-2);
  }

  .db-instances-table__selection-count {
    color: var(--color-ink-2);
  }

  .db-instances-table__row {
    border-bottom: 1px solid color-mix(in oklab, var(--color-line), transparent 45%);
  }

  .db-instances-table__row:hover {
    background-color: color-mix(in oklab, var(--color-surface-sunken), transparent 60%);
  }

  .db-instances-table__row[data-selected='true'] {
    background-color: var(--accent-soft);
  }

  .db-instances-table__name {
    color: var(--color-ink-0);
  }

  .db-instances-table__name:hover {
    color: var(--color-accent);
  }

  .db-instances-table__detail {
    color: var(--color-ink-1);
  }

  .db-instances-table__action {
    border: 1px solid var(--color-line-2);
    transition: color 150ms ease, border-color 150ms ease;
  }

  .db-instances-table__restart {
    color: var(--color-accent);
  }

  .db-instances-table__delete {
    color: var(--color-state-danger);
  }

  .db-instances-table__action:hover {
    border-color: var(--color-accent);
  }

  .db-instances-table__delete:hover {
    color: color-mix(in oklab, var(--color-state-danger) 88%, var(--color-ink-0));
    border-color: var(--color-state-danger);
  }

  .db-instances-table__action:disabled {
    color: var(--color-ink-3);
    border-color: var(--color-line);
  }
</style>
