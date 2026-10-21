<script lang="ts">
 import type { VolumeBackup } from '$lib/types/volume';
 import StatusChip from '$lib/components/ui/StatusChip.svelte';
 import { formatStorage } from '$lib/utils/format';
 import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
 import { t } from '$lib/i18n/ns/volume';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
 import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
 import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
 import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
 import Button from '$lib/components/ui/Button.svelte';
 let { backups, deletingId, onRestore, onDelete, selectedIds, selectableIds, selectionDisabled, onToggleSelect, onToggleAll }: {
  backups: VolumeBackup[]; deletingId: string | null; onRestore: (b: VolumeBackup) => void; onDelete: (id: string, name: string) => Promise<void>;
  selectedIds: ReadonlySet<string>; selectableIds: ReadonlySet<string>; selectionDisabled: boolean; onToggleSelect: (id: string) => void; onToggleAll: () => void;
 } = $props();
 const selectedCount = $derived([...selectedIds].filter((id) => selectableIds.has(id)).length);
</script>
<ResponsiveTable>
 {#snippet cards()}
  <div class="responsive-card-toolbar">
   <SelectionCheckbox checked={selectableIds.size > 0 && selectedCount === selectableIds.size} indeterminate={selectedCount > 0 && selectedCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('backupListTable.selectAll')} />
   <span class="text-xs text-ink-2">{t('backupListTable.selectAll')}</span>
  </div>
  {#each backups as backup (backup.id)}
   <CompactResourceCard selected={selectedIds.has(backup.id)}>
    <div class="flex items-start gap-2 min-w-0">
     <SelectionCheckbox checked={selectedIds.has(backup.id)} disabled={selectionDisabled} onclick={() => onToggleSelect(backup.id)} ariaLabel={t('backupListTable.selectBackup', { name: backup.name || backup.id })} />
     <span class="min-w-0 flex-1 font-medium break-all">{backup.name || backup.id.slice(0, 8)}</span>
     <StatusChip status={backup.status} />
    </div>
    <dl>
     <div><dt>{t('backupListTable.size')}</dt><dd>{formatStorage(backup.size)}</dd></div>
     <div><dt>{t('backupListTable.incremental')}</dt><dd>{backup.is_incremental ? t('backupListTable.incremental') : t('backupListTable.full')}</dd></div>
    </dl>
    {#snippet details()}
     <p class="font-mono break-all">{backup.id}</p>
     <dl><div><dt>{t('backupListTable.createdAt')}</dt><dd>{backup.created_at ? new Date(backup.created_at).toLocaleDateString(intlLocale()) : t('backupListTable.missingValue')}</dd></div></dl>
    {/snippet}
    {#snippet actions()}
     <Button variant="secondary" size="sm" onclick={() => onRestore(backup)}>{t('backupListTable.restore')}</Button>
     <Button variant="danger-outline" size="sm" onclick={() => onDelete(backup.id, backup.name)} disabled={deletingId === backup.id}>{#if deletingId === backup.id}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingId === backup.id ? t('backupListTable.deleting') : t('backupListTable.delete')}</Button>
    {/snippet}
   </CompactResourceCard>
  {/each}
 {/snippet}
<div class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
 <th class="text-left py-3 pr-3"><SelectionCheckbox checked={selectableIds.size > 0 && selectedCount === selectableIds.size} indeterminate={selectedCount > 0 && selectedCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('backupListTable.selectAll')} /></th>
 <th class="text-left py-3 pr-6">{t('backupListTable.name')}</th><th class="text-left py-3 pr-6">{t('backupListTable.status')}</th><th class="text-left py-3 pr-6">{t('backupListTable.size')}</th><th class="text-left py-3 pr-6">{t('backupListTable.incremental')}</th><th class="text-left py-3 pr-6">{t('backupListTable.createdAt')}</th><th class="text-right py-3">{t('backupListTable.actions')}</th>
</tr></thead><tbody class="motion-stagger">
 {#each backups as backup (backup.id)}
  <tr class="resource-selection-surface border-b border-line/50 hover:bg-surface-sunken/50 transition-colors" data-selected={selectedIds.has(backup.id)}>
   <td class="py-3 pr-3"><SelectionCheckbox checked={selectedIds.has(backup.id)} disabled={selectionDisabled} onclick={() => onToggleSelect(backup.id)} ariaLabel={t('backupListTable.selectBackup', { name: backup.name || backup.id })} /></td>
   <td class="py-3 pr-6 font-medium text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={backup.name || backup.id}>{backup.name || backup.id.slice(0, 8)}</span></td>
   <td class="py-3 pr-6"><StatusChip status={backup.status} /></td><td class="py-3 pr-6 text-ink-2">{formatStorage(backup.size)}</td>
   <td class="py-3 pr-6"><span class="text-xs {backup.is_incremental ? 'text-warm-text' : 'text-ink-2'}">{backup.is_incremental ? t('backupListTable.incremental') : t('backupListTable.full')}</span></td>
   <td class="py-3 pr-6 text-ink-2 text-xs">{backup.created_at ? new Date(backup.created_at).toLocaleDateString(intlLocale()) : t('backupListTable.missingValue')}</td>
   <td class="py-3 text-right"><div class="flex items-center justify-end gap-2"><button onclick={() => onRestore(backup)} class="text-warm-text hover:text-warm-text-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors">{t('backupListTable.restore')}</button><button onclick={() => onDelete(backup.id, backup.name)} disabled={deletingId === backup.id} class="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">{#if deletingId === backup.id}<ActivityIndicator size="xs" tone="danger" />{/if}{deletingId === backup.id ? t('backupListTable.deleting') : t('backupListTable.delete')}</button></div></td>
  </tr>
 {/each}
</tbody></table></div>
</ResponsiveTable>
