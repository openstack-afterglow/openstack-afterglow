<script lang="ts">
 import { t } from '$lib/i18n/ns/file-storage';
 import { ResponsiveTable, CompactResourceCard, Button } from '$lib/components/ui';
 import StatusChip from '$lib/components/ui/StatusChip.svelte'; import Pill from '$lib/components/ui/Pill.svelte'; import type { SecurityService } from '$lib/types/securityService'; import { typeLabel } from '$lib/types/securityService'; import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte'; import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
 let { services, deleting, onAttachClick, onDelete, onCreateClick, selectedIds, selectableIds, selectionDisabled, onToggleSelect, onToggleAll }: { services: SecurityService[]; deleting: string | null; onAttachClick: (id: string) => void; onDelete: (id: string, name: string) => void; onCreateClick: () => void; selectedIds: ReadonlySet<string>; selectableIds: ReadonlySet<string>; selectionDisabled: boolean; onToggleSelect: (id: string) => void; onToggleAll: () => void; } = $props(); const selectedCount = $derived([...selectedIds].filter((id) => selectableIds.has(id)).length);
</script>
{#snippet selectAll()}
 <SelectionCheckbox checked={selectableIds.size > 0 && selectedCount === selectableIds.size} indeterminate={selectedCount > 0 && selectedCount < selectableIds.size} disabled={selectionDisabled || selectableIds.size === 0} onclick={onToggleAll} ariaLabel={t('securityTable.selectAll')} />
{/snippet}
{#snippet selectService(svc: SecurityService)}
 <SelectionCheckbox checked={selectedIds.has(svc.id)} disabled={selectionDisabled} onclick={() => onToggleSelect(svc.id)} ariaLabel={t('securityTable.select', { name: svc.name })} />
{/snippet}
{#snippet serviceActions(svc: SecurityService)}
 <Button variant="secondary" size="sm" onclick={() => onAttachClick(svc.id)}>{t('securityTable.attachNetwork')}</Button>
 <Button variant="danger-outline" size="sm" onclick={() => onDelete(svc.id, svc.name)} disabled={deleting === svc.id}>{#if deleting === svc.id}<ActivityIndicator size="xs" tone="danger" />{/if}{deleting === svc.id ? t('securityTable.deleting') : t('securityTable.delete')}</Button>
{/snippet}
{#if services.length === 0}
 <div class="text-center py-20 text-ink-2"><p class="text-lg">{t('securityTable.empty')}</p><button onclick={onCreateClick} class="text-warm-text hover:text-warm-text-hover text-sm mt-2 inline-block">{t('securityTable.create')}</button></div>
{:else}
 <ResponsiveTable>
  {#snippet cards()}
   <div class="responsive-card-toolbar"><label class="flex items-center gap-2 text-xs text-ink-2">{@render selectAll()}{t('securityTable.selectAll')}</label></div>
   {#each services as svc (svc.id)}
    <CompactResourceCard selected={selectedIds.has(svc.id)}>
     <div class="flex items-center gap-2">{@render selectService(svc)}<strong class="min-w-0 flex-1 break-all">{svc.name}</strong><StatusChip status={svc.status || null} /></div>
     <p><Pill tone="accent" size="xs">{typeLabel[svc.type] ?? svc.type}</Pill></p>
     <p class="text-xs text-ink-2">{t('securityTable.domain')}: {svc.domain || '-'}</p>
     {#snippet details()}<dl><div><dt>ID</dt><dd class="font-mono break-all">{svc.id}</dd></div><div><dt>{t('securityTable.dnsIp')}</dt><dd class="font-mono">{svc.dns_ip || '-'}</dd></div><div><dt>{t('securityTable.server')}</dt><dd>{svc.server || '-'}</dd></div></dl>{#if svc.description}<p class="mt-2">{svc.description}</p>{/if}{/snippet}
     {#snippet actions()}{@render serviceActions(svc)}{/snippet}
    </CompactResourceCard>
   {/each}
  {/snippet}
  <div class="overflow-x-auto"><table class="w-full text-sm">
   <thead><tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide"><th class="text-left py-3 pr-3">{@render selectAll()}</th><th class="text-left py-3 pr-4">{t('securityTable.name')}</th><th class="text-left py-3 pr-4">{t('securityTable.type')}</th><th class="text-left py-3 pr-4">{t('securityTable.status')}</th><th class="text-left py-3 pr-4">{t('securityTable.dnsIp')}</th><th class="text-left py-3 pr-4">{t('securityTable.server')}</th><th class="text-left py-3 pr-4">{t('securityTable.domain')}</th><th class="text-right py-3">{t('securityTable.actions')}</th></tr></thead>
   <tbody class="motion-stagger">{#each services as svc (svc.id)}
    <tr class="resource-selection-surface border-b border-line/50 hover:bg-surface-sunken/30 transition-colors" data-selected={selectedIds.has(svc.id)}>
     <td class="py-3 pr-3">{@render selectService(svc)}</td><td class="py-3 pr-4 font-medium text-ink-0"><span>{svc.name}</span>{#if svc.description}<div class="text-xs text-ink-2">{svc.description}</div>{/if}</td><td class="py-3 pr-4"><Pill tone="accent" size="xs">{typeLabel[svc.type] ?? svc.type}</Pill></td><td class="py-3 pr-4"><StatusChip status={svc.status || null} /></td><td class="py-3 pr-4 text-xs text-ink-2 font-mono">{svc.dns_ip || '-'}</td><td class="py-3 pr-4 text-xs text-ink-2">{svc.server || '-'}</td><td class="py-3 pr-4 text-xs text-ink-2">{svc.domain || '-'}</td><td class="py-3 text-right"><div class="flex justify-end gap-1">{@render serviceActions(svc)}</div></td>
    </tr>
   {/each}</tbody>
  </table></div>
 </ResponsiveTable>
{/if}
