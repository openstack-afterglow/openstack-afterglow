<script lang="ts">
	import { t as tr } from '$lib/i18n/ns/database';
  import type { DbBackup, DbInstance } from '$lib/types/database';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

  let {
    backups,
    instances,
    selectedIds = new Set<string>(),
    selectableIds = new Set<string>(),
    selectionDisabled = false,
    deleting = null,
    onToggleSelect = () => {},
    onToggleAll = () => {},
    onRestore,
    onRestoreIntent,
    onDelete,
  }: {
    backups: DbBackup[];
    instances: DbInstance[];
    selectedIds?: ReadonlySet<string>;
    selectableIds?: ReadonlySet<string>;
    selectionDisabled?: boolean;
    deleting?: string | null;
    onToggleSelect?: (id: string) => void;
    onToggleAll?: () => void;
    onRestore: (backup: DbBackup) => void;
    onRestoreIntent?: () => void;
    onDelete: (id: string, name: string, stuck: boolean) => void;
  } = $props();

  const selectedSelectableCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
  const allSelected = $derived(selectableIds.size > 0 && selectedSelectableCount === selectableIds.size);
  const indeterminate = $derived(selectedSelectableCount > 0 && !allSelected);
  const STUCK_MS = 6 * 3600 * 1000;

  function isStuck(backup: DbBackup): boolean {
    return backup.status === 'BUILDING' && (Date.now() - new Date(backup.created_at).getTime()) > STUCK_MS;
  }

  function findInstance(backup: DbBackup): DbInstance | undefined {
    return backup.instance_id ? instances.find((instance) => instance.id === backup.instance_id) : undefined;
  }

  function formatSize(size: number | undefined): string {
    return size ? `${size} GB` : '-';
  }

  function formatDate(value: string | undefined): string {
    return value ? value.slice(0, 10) : '-';
  }

  function datastoreLabel(backup: DbBackup): string {
    const datastore = backup.datastore;
    if (!datastore) return '-';
    const parts = [datastore.type, datastore.version].filter(Boolean);
    return parts.length > 0 ? parts.join(' ') : '-';
  }
</script>

<div class="db-backups-table rounded-xl overflow-hidden">
  <table class="w-full text-sm">
    <thead>
      <tr class="db-backups-table__head text-xs">
        <th class="text-left px-3 py-3"><div class="inline-flex items-center gap-2"><SelectionCheckbox checked={allSelected} indeterminate={indeterminate} disabled={selectionDisabled} ariaLabel={tr('selection.allBackups')} onclick={onToggleAll} /><span>{tr('selection.all')}</span><span class="db-backups-table__selection-count normal-case" aria-live="polite">{tr('selection.count', { count: selectedSelectableCount })}</span></div></th>
        <th class="text-left px-4 py-3 font-medium">{tr('labels.name')}</th>
        <th class="text-left px-4 py-3 font-medium">{tr('labels.status')}</th>
        <th class="text-left px-4 py-3 font-medium">{tr('backups.source')}</th>
        <th class="text-left px-4 py-3 font-medium">{tr('labels.datastoreEnglish')}</th>
        <th class="text-left px-4 py-3 font-medium">{tr('labels.size')}</th>
        <th class="text-left px-4 py-3 font-medium">{tr('labels.created')}</th>
        <th class="text-right px-4 py-3 font-medium">{tr('labels.actions')}</th>
      </tr>
    </thead>
    <tbody class="motion-stagger">
      {#each backups as backup (backup.id)}
        {@const instance = findInstance(backup)}
        {@const stuck = isStuck(backup)}
        <tr class="resource-selection-surface db-backups-table__row transition-colors" data-selected={selectedIds.has(backup.id)}>
          <td class="px-3 py-3"><SelectionCheckbox checked={selectedIds.has(backup.id)} disabled={selectionDisabled || !selectableIds.has(backup.id)} ariaLabel={tr('selection.item', { name: backup.name || backup.id.slice(0, 8) })} onclick={() => onToggleSelect(backup.id)} /></td>
          <td class="db-backups-table__name px-4 py-3 font-medium">{backup.name || backup.id.slice(0, 8)}</td>
          <td class="px-4 py-3">
            <div class="flex items-center gap-1">
              <StatusChip status={backup.status} />
              {#if stuck}<span class="db-backups-table__stuck text-xs ml-1" title={tr('backups.stuckHelp')}>{tr('backups.stuck')}</span>{/if}
            </div>
          </td>
          <td class="px-4 py-3">
            {#if instance}
              <a href="/dashboard/database/instances/{instance.id}" class="db-backups-table__link transition-colors">{instance.name}</a>
            {:else if backup.instance_id}
              <span class="db-backups-table__muted text-xs">{tr('backups.sourceDeleted')}</span>
              {#if backup.datastore?.type}<span class="db-backups-table__muted text-xs ml-1">({backup.datastore.type})</span>{/if}
            {:else}<span class="db-backups-table__muted">—</span>{/if}
          </td>
          <td class="db-backups-table__meta px-4 py-3 text-xs">{datastoreLabel(backup)}</td>
          <td class="db-backups-table__meta px-4 py-3 text-xs">{formatSize(backup.size)}</td>
          <td class="db-backups-table__selection-count px-4 py-3 text-xs">{formatDate(backup.created_at)}</td>
          <td class="px-4 py-3">
            <div class="flex justify-end gap-1">
              <button onclick={() => onRestore(backup)} onpointerenter={onRestoreIntent} onfocus={onRestoreIntent} disabled={selectionDisabled} class="db-backups-table__action db-backups-table__restore text-xs px-2 py-0.5 rounded transition-colors">{tr('actions.restore')}</button>
              <button onclick={() => onDelete(backup.id, backup.name, stuck)} disabled={deleting === backup.id || selectionDisabled} class="db-backups-table__action db-backups-table__delete inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded transition-colors">{#if deleting === backup.id}<ActivityIndicator size="xs" tone="danger" />{tr('state.deletingShort')}{:else}{tr('actions.delete')}{/if}</button>
            </div>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .db-backups-table {
    background-color: var(--color-surface-raised);
    border: 1px solid var(--color-line);
  }

  .db-backups-table__head {
    border-bottom: 1px solid var(--color-line);
    color: var(--color-ink-2);
  }

  .db-backups-table__selection-count,
  .db-backups-table__meta {
    color: var(--color-ink-2);
  }

  .db-backups-table__row {
    border-top: 1px solid color-mix(in oklab, var(--color-line), transparent 45%);
  }

  .db-backups-table__row:hover {
    background-color: color-mix(in oklab, var(--color-surface-sunken), transparent 60%);
  }

  .db-backups-table__row[data-selected='true'] {
    background-color: var(--accent-soft);
  }

  .db-backups-table__name {
    color: var(--color-ink-0);
  }

  .db-backups-table__stuck,
  .db-backups-table__delete {
    color: var(--color-state-danger);
  }

  .db-backups-table__link,
  .db-backups-table__restore {
    color: var(--color-accent);
  }

  .db-backups-table__link:hover,
  .db-backups-table__restore:hover {
    color: color-mix(in oklab, var(--color-accent) 88%, var(--color-ink-0));
  }

  .db-backups-table__muted {
    color: var(--color-ink-2);
  }

  .db-backups-table__action {
    border: 1px solid var(--color-line-2);
  }

  .db-backups-table__action:hover {
    border-color: var(--color-accent);
  }

  .db-backups-table__delete:hover {
    color: color-mix(in oklab, var(--color-state-danger) 88%, var(--color-ink-0));
    border-color: var(--color-state-danger);
  }

  .db-backups-table__action:disabled {
    color: var(--color-ink-3);
    border-color: var(--color-line);
  }
</style>
