<script lang="ts">
 import { untrack } from 'svelte';
 import { authDisplayContext } from '$lib/stores/authDisplayContext';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
 import { t as storageCommonT } from '$lib/i18n/ns/common';
 import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
 import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
 import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

  import { t } from '$lib/i18n/ns/file-storage';
  import type { FileStorage } from '$lib/types/fileStorage';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import { ResponsiveTable, CompactResourceCard } from '$lib/components/ui';

  let {
    fileStorages,
  }: {
    fileStorages: FileStorage[];
  } = $props();
 let search = $state('');
 const searchId = $props.id();
 const columns = $derived<TableColumn<FileStorage>[]>([
  { key: 'name', label: t('networkTable.name'), value: row => row.name },
  { key: 'status', label: t('info.status'), value: row => row.status },
  { key: 'size', label: t('info.size'), value: row => row.size },
  { key: 'library', label: t('info.library'), value: row => row.library_name },
  { key: 'built', label: t('info.builtAt'), value: row => row.built_at },
 ]);
 const view = createTableView({ locale: intlLocale,rows: () => fileStorages, columns: () => columns, search: () => search, searchable: row => [row.name, row.id, row.library_name, row.status].map(value => String(value ?? ''))});
 let viewOwner = '';
 $effect(() => authDisplayContext.subscribe(({ key }) => {
  if (viewOwner === key) return;
  viewOwner = key;
  untrack(() => { search = ''; view.reset(); });
 }));
</script>

<RegexSearch id={searchId} bind:value={search} />
<TableViewControls {view} class="" />
{#if fileStorages.length > 0 && view.rows.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{storageCommonT('table.noMatches')}</p>{/if}
<ResponsiveTable>
  {#snippet cards()}
    {#each view.rows as fs (fs.id)}
      <CompactResourceCard>
        <div class="flex items-center gap-2"><strong class="min-w-0 flex-1 break-all">{fs.name || fs.id.slice(0, 8)}</strong><StatusChip status={fs.status} /></div>
        <p class="text-xs text-ink-2">{t('manageGrid.size')}: {fs.size} GB{#if fs.metadata?.union_type} · {fs.metadata.union_type}{/if}</p>
        {#if fs.library_name}<p class="text-xs text-ink-2">{fs.library_name}</p>{/if}
        {#snippet details()}<p class="font-mono break-all">ID: {fs.id}</p>{#if fs.built_at}<p>{t('manageGrid.builtOn', { date: fs.built_at.split('T')[0] })}</p>{/if}{/snippet}
      </CompactResourceCard>
    {/each}
  {/snippet}
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
  {#each view.rows as fs}
    <div class="bg-surface-base border border-line rounded-lg p-5">
      <div class="flex items-center gap-2.5 mb-3">
        <div class="w-10 h-10 rounded-lg bg-teal-500/15 border border-teal-500/30 text-teal-400 flex items-center justify-center shrink-0">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          </svg>
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-ink-0 font-semibold text-sm font-mono truncate">{fs.name}</div>
          <div class="flex items-center gap-1.5 mt-0.5">
            {#if fs.metadata?.union_type}
              <span class="text-xs px-1.5 py-0.5 rounded bg-surface-selected/40 text-warm-text border border-action-warm/50">{fs.metadata.union_type}</span>
            {/if}
            {#if fs.library_name}
              <span class="text-xs px-1.5 py-0.5 rounded bg-violet-900/40 text-violet-300 border border-violet-800/50 truncate">{fs.library_name}</span>
            {/if}
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 gap-2 mb-3">
        <div>
          <div class="text-xs uppercase tracking-wider font-medium text-ink-2">{t('manageGrid.size')}</div>
          <div class="text-ink-0 font-mono text-sm mt-0.5">{fs.size} GB</div>
        </div>
        <div>
          <div class="text-xs uppercase tracking-wider font-medium text-ink-2">{t('manageGrid.status')}</div>
          <div class="mt-0.5"><StatusChip status={fs.status} /></div>
        </div>
      </div>
      {#if fs.built_at}
        <div class="pt-3 border-t border-line">
          <div class="text-xs text-ink-2">{t('manageGrid.builtOn', { date: fs.built_at.split('T')[0] })}</div>
        </div>
      {/if}
    </div>
  {/each}
</div>
</ResponsiveTable>
