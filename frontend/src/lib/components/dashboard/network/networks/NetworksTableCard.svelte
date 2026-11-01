<script lang="ts">
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n/ns/network-pages';
  import { ActionMenu, Button, ResourceIdentifier, StatusChip } from '$lib/components/ui';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import type { Network } from '$lib/types/networks';

  let { networks, defaultNetworkId, deleting, settingDefault, selectedIds, selectableIds, selectionDisabled, onToggleSelect, onToggleAll, onOpenPanel, onSetDefault, onDelete }: {
    networks: Network[]; defaultNetworkId: string | null; deleting: string | null; settingDefault: string | null;
    selectedIds: ReadonlySet<string>; selectableIds: ReadonlySet<string>; selectionDisabled: boolean;
    onToggleSelect: (id: string) => void; onToggleAll: () => void; onOpenPanel: (id: string) => void;
    onSetDefault: (id: string) => void; onDelete: (id: string, name: string, isExternal: boolean) => void;
  } = $props();
  let openMenu = $state<string | null>(null);
  const selectedCount = $derived([...selectableIds].filter((id) => selectedIds.has(id)).length);
  const allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
  const indeterminate = $derived(selectedCount > 0 && !allSelected);
</script>

{#snippet selection(net: Network)}
  <SelectionCheckbox checked={selectedIds.has(net.id)} disabled={selectionDisabled || !selectableIds.has(net.id)} unavailable={!selectableIds.has(net.id)} title={!selectableIds.has(net.id) ? t('networksTable.onlyOwned') : undefined} ariaLabel={t('networksTable.select', { name: net.name || net.id })} onclick={() => onToggleSelect(net.id)} />
{/snippet}
{#snippet networkActions(net: Network, surface: string)}
  <ActionMenu open={openMenu === `${surface}:${net.id}`} ariaLabel={t('networksTable.actions', { name: net.name || net.id })} onopen={() => openMenu = `${surface}:${net.id}`} onclose={() => openMenu = null}>
    <Button variant="ghost" class="w-full justify-start" onclick={() => { openMenu = null; onOpenPanel(net.id); }}>{t('list.details')}</Button>
    {#if selectableIds.has(net.id)}
      {#if net.id !== defaultNetworkId}<Button variant="ghost" class="w-full justify-start" disabled={selectionDisabled || settingDefault === net.id || deleting === net.id} onclick={() => { openMenu = null; onSetDefault(net.id); }}>{#if settingDefault === net.id}<LoadingState variant="control" label="" />{/if}{settingDefault === net.id ? t('networksTable.setting') : t('networksTable.setDefault')}</Button>{/if}
      <Button variant="danger" class="w-full justify-start" disabled={selectionDisabled || deleting === net.id || settingDefault === net.id} onclick={() => { openMenu = null; onDelete(net.id, net.name, net.is_external); }}>{#if deleting === net.id}<LoadingState variant="control" label="" />{/if}{deleting === net.id ? t('networksTable.deleting') : t('networksTable.delete')}</Button>
    {/if}
  </ActionMenu>
{/snippet}
{#snippet networkType(net: Network)}
  <span class="text-ink-2">{net.is_external ? t('networksTable.external') : net.is_shared ? t('networksTable.shared') : t('networksTable.internal')}</span>
  {#if net.id === defaultNetworkId}<span class="ml-2 text-[13px] text-ink-1">{t('networksTable.default')}</span>{/if}
{/snippet}

<ResponsiveTable>
  {#snippet cards()}
    <div class="responsive-card-toolbar"><SelectionToolbar label={t('networksTable.title')} ariaLabel={t('networksTable.selectAll')} checked={allSelected} {indeterminate} {selectedCount} disabled={selectionDisabled || selectableIds.size === 0} onToggle={onToggleAll} /></div>
    {#each networks as net (net.id)}
      <CompactResourceCard selected={selectedIds.has(net.id)}>
        <div class="flex items-center gap-2 min-w-0" aria-busy={deleting === net.id || settingDefault === net.id}>
          {@render selection(net)}<button type="button" onclick={() => onOpenPanel(net.id)} class="min-h-11 min-w-0 flex-1 text-left font-medium text-ink-0 hover:text-warm-text">{net.name || net.id.slice(0, 12)}</button><StatusChip status={net.status} />
        </div>
        <ResourceIdentifier id={net.id} />
        <div class="flex flex-wrap gap-2 text-sm">{@render networkType(net)}<span class="tabular-nums text-ink-2">{t('networksTable.subnetCount', { count: net.subnets.length })}</span></div>
        <p class="font-mono text-xs text-ink-2 break-all">{net.cidrs?.length ? net.cidrs.join(', ') : '—'}</p>
        {#snippet actions()}{@render networkActions(net, 'card')}{/snippet}
      </CompactResourceCard>
    {/each}
  {/snippet}
  <div class="rounded-lg border border-line bg-surface-base overflow-x-auto">
    <table class="w-full text-sm">
      <thead><tr class="border-b border-line text-left text-[13px] text-ink-2">
        <th class="px-4 py-2 font-medium"><SelectionToolbar label={t('networksTable.title')} ariaLabel={t('networksTable.selectAll')} checked={allSelected} {indeterminate} {selectedCount} disabled={selectionDisabled || selectableIds.size === 0} onToggle={onToggleAll} /></th>
        <th class="px-4 py-2 font-medium">CIDR</th><th class="px-4 py-2 font-medium">{t('networksTable.type')}</th><th class="px-4 py-2 text-right font-medium">{t('networksTable.subnets')}</th><th class="px-4 py-2 font-medium">{t('networksTable.status')}</th><th class="px-4 py-2"></th>
      </tr></thead>
      <tbody>
        {#each networks as net (net.id)}
          <tr class="resource-selection-surface border-b border-line last:border-b-0" data-selected={selectedIds.has(net.id)} aria-busy={deleting === net.id || settingDefault === net.id}>
            <td class="px-4 py-2"><div class="flex items-center gap-2">{@render selection(net)}<div class="min-w-0"><button type="button" onclick={() => onOpenPanel(net.id)} class="text-left font-medium text-ink-0 hover:text-warm-text">{net.name || net.id.slice(0, 12)}</button><ResourceIdentifier id={net.id} /></div></div></td>
            <td class="px-4 py-2 font-mono text-xs text-ink-2" title={net.cidrs?.length ? net.cidrs.join(', ') : undefined}>{net.cidrs?.length ? net.cidrs.join(', ') : '—'}</td>
            <td class="px-4 py-2">{@render networkType(net)}</td><td class="px-4 py-2 text-right tabular-nums text-ink-2">{net.subnets.length}</td><td class="px-4 py-2"><StatusChip status={net.status} /></td><td class="px-4 py-2">{@render networkActions(net, 'row')}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</ResponsiveTable>
