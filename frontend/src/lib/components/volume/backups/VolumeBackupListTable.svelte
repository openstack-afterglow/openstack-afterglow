<script lang="ts">
 import type { VolumeBackup } from '$lib/types/volume';
 import StatusChip from '$lib/components/ui/StatusChip.svelte';
 import { formatStorage } from '$lib/utils/format';
 import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
 let { backups, deletingId, onRestore, onDelete, selectedIds, selectableIds, selectionDisabled, onToggleSelect, onToggleAll }: {
  backups: VolumeBackup[]; deletingId: string | null; onRestore: (b: VolumeBackup) => void; onDelete: (id: string, name: string) => Promise<void>;
  selectedIds: ReadonlySet<string>; selectableIds: ReadonlySet<string>; selectionDisabled: boolean; onToggleSelect: (id: string) => void; onToggleAll: () => void;
 } = $props();
 const selectedCount = $derived([...selectedIds].filter((id) => selectableIds.has(id)).length);
</script>
<div class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
 <th class="text-left py-3 pr-3"><SelectionCheckbox checked={selectableIds.size > 0 && selectedCount === selectableIds.size} indeterminate={selectedCount > 0 && selectedCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel="전체 선택" /></th>
 <th class="text-left py-3 pr-6">이름</th><th class="text-left py-3 pr-6">상태</th><th class="text-left py-3 pr-6">크기</th><th class="text-left py-3 pr-6">증분</th><th class="text-left py-3 pr-6">생성일</th><th class="text-right py-3">액션</th>
</tr></thead><tbody>
 {#each backups as backup (backup.id)}
  <tr class="resource-selection-surface border-b border-line/50 hover:bg-surface-sunken/50 transition-colors" data-selected={selectedIds.has(backup.id)}>
   <td class="py-3 pr-3"><SelectionCheckbox checked={selectedIds.has(backup.id)} disabled={selectionDisabled} onclick={() => onToggleSelect(backup.id)} ariaLabel={`${backup.name || backup.id} 선택`} /></td>
   <td class="py-3 pr-6 font-medium text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={backup.name || backup.id}>{backup.name || backup.id.slice(0, 8)}</span></td>
   <td class="py-3 pr-6"><StatusChip status={backup.status} /></td><td class="py-3 pr-6 text-ink-2">{formatStorage(backup.size)}</td>
   <td class="py-3 pr-6"><span class="text-xs {backup.is_incremental ? 'text-action-warm' : 'text-ink-3'}">{backup.is_incremental ? '증분' : '전체'}</span></td>
   <td class="py-3 pr-6 text-ink-2 text-xs">{backup.created_at ? new Date(backup.created_at).toLocaleDateString('ko-KR') : '-'}</td>
   <td class="py-3 text-right"><div class="flex items-center justify-end gap-2"><button onclick={() => onRestore(backup)} class="text-action-warm hover:text-action-warm-hover text-xs px-2 py-1 rounded border border-action-warm hover:border-action-warm transition-colors">복원</button><button onclick={() => onDelete(backup.id, backup.name)} disabled={deletingId === backup.id} class="text-red-400 hover:text-red-300 disabled:text-ink-3 text-xs px-2 py-1 rounded border border-red-900 hover:border-red-700 disabled:border-line-2 transition-colors">{deletingId === backup.id ? '삭제 중...' : '삭제'}</button></div></td>
  </tr>
 {/each}
</tbody></table></div>
