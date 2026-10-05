<script lang="ts">
  import type { VolumeSnapshot } from '$lib/types/volume';
  import { formatStorage } from '$lib/utils/format';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import { t } from '$lib/i18n/ns/volume';
  import { intlLocale } from '$lib/i18n/runtime.svelte';

  let { snapshots, deleting, selectedIds, selectableIds, selectionDisabled, onToggleSelect, onToggleAll, onDelete }: {
    snapshots: VolumeSnapshot[]; deleting: string | null; selectedIds: ReadonlySet<string>;
    selectableIds: ReadonlySet<string>; selectionDisabled: boolean;
    onToggleSelect: (id: string) => void; onToggleAll: () => void;
    onDelete: (id: string, name: string) => Promise<void>;
  } = $props();
  const selectedSelectableCount = $derived([...selectedIds].filter((id) => selectableIds.has(id)).length);
</script>

<div class="overflow-x-auto">
  <table class="w-full text-sm">
    <thead>
      <tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
        <th class="text-left py-3 pr-3"><SelectionCheckbox checked={selectableIds.size > 0 && selectedSelectableCount === selectableIds.size} indeterminate={selectedSelectableCount > 0 && selectedSelectableCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('snapshotsTable.selectAll')} /></th>
        <th class="text-left py-3 pr-6">{t('snapshotsTable.name')}</th>
        <th class="text-left py-3 pr-6">{t('snapshotsTable.status')}</th>
        <th class="text-left py-3 pr-6">{t('snapshotsTable.size')}</th>
        <th class="text-left py-3 pr-6">{t('snapshotsTable.volumeId')}</th>
        <th class="text-left py-3 pr-6">{t('snapshotsTable.description')}</th>
        <th class="text-left py-3 pr-6">{t('snapshotsTable.createdAt')}</th>
        <th class="text-right py-3">{t('snapshotsTable.actions')}</th>
      </tr>
    </thead>
    <tbody>
      {#each snapshots as snap (snap.id)}
        <tr class="resource-selection-surface border-b border-line/50 hover:bg-surface-sunken/50 transition-colors" data-selected={selectedIds.has(snap.id)}>
          <td class="py-3 pr-3"><SelectionCheckbox checked={selectedIds.has(snap.id)} disabled={selectionDisabled} onclick={() => onToggleSelect(snap.id)} ariaLabel={t('snapshotsTable.selectSnapshot', { name: snap.name || snap.id })} /></td>
          <td class="py-3 pr-6 font-medium text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={snap.name || snap.id}>{snap.name || snap.id.slice(0, 8)}</span></td>
          <td class="py-3 pr-6"><StatusChip status={snap.status} /></td>
          <td class="py-3 pr-6 text-ink-2">{formatStorage(snap.size)}</td>
          <td class="py-3 pr-6 text-ink-2 font-mono text-xs">{t('snapshotsTable.shortVolumeId', { id: snap.volume_id.slice(0, 8) })}</td>
          <td class="py-3 pr-6 text-ink-2 text-xs">{snap.description || t('snapshotsTable.missingValue')}</td>
          <td class="py-3 pr-6 text-ink-2 text-xs">{snap.created_at ? new Date(snap.created_at).toLocaleDateString(intlLocale()) : t('snapshotsTable.missingValue')}</td>
          <td class="py-3 text-right">
            <button
              onclick={() => onDelete(snap.id, snap.name)}
              disabled={deleting === snap.id}
              class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors"
            >
              {deleting === snap.id ? t('snapshotsTable.deleting') : t('snapshotsTable.delete')}
            </button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
