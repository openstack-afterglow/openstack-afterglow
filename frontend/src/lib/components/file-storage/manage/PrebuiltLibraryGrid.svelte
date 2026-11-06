<script lang="ts">
 import { untrack } from 'svelte';
 import { authDisplayContext } from '$lib/stores/authDisplayContext';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
 import { t as storageCommonT } from '$lib/i18n/ns/common';
 import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
 import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
 import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

  import { t } from '$lib/i18n/ns/file-storage';
  import { t as ts } from '$lib/i18n/ns/status';
  import RichText from '$lib/i18n/RichText.svelte';
  import type { FileStorage } from '$lib/types/fileStorage';
  import type { LibraryConfig } from '$lib/types/library';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import Button from '$lib/components/ui/Button.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';

  let {
    libraries,
    fileStorages,
    building,
    onBuild,
  }: {
    libraries: LibraryConfig[];
    fileStorages: FileStorage[];
    building: string | null;
    onBuild: (libraryId: string) => Promise<void>;
  } = $props();
 let search = $state('');
 const searchId = $props.id();
 const columns = $derived<TableColumn<LibraryConfig>[]>([
  { key: 'name', label: t('networkTable.name'), value: row => row.name },
  { key: 'version', label: t('info.version'), value: row => row.version },
  { key: 'status', label: t('info.status'), value: row => fileStorages.find(storage => storage.library_name === row.id && storage.metadata?.union_type === 'prebuilt')?.status ?? 'not-built', format: value => value === 'not-built' ? t('prebuiltGrid.notBuilt') : String(value) },
 ]);
 const view = createTableView({ locale: intlLocale,rows: () => libraries, columns: () => columns, search: () => search, searchable: row => [row.id,row.name,row.version].map(value => String(value ?? ''))});
 let viewOwner = '';
 $effect(() => authDisplayContext.subscribe(({ key }) => {
  if (viewOwner === key) return;
  viewOwner = key;
  untrack(() => { search = ''; view.reset(); });
 }));
</script>

{#snippet storageId(text: string)}<span class="font-mono">{text}</span>{/snippet}

<RegexSearch id={searchId} bind:value={search} />
<TableViewControls {view} class="" />
{#if libraries.length > 0 && view.rows.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{storageCommonT('table.noMatches')}</p>{/if}
<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
  {#each view.rows as lib (lib.id)}
    {@const prebuilt = fileStorages.find(s => s.library_name === lib.id && s.metadata?.union_type === 'prebuilt')}
    {@const serverBuilding = prebuilt?.status.toUpperCase() === 'BUILDING'}
    <div class="bg-surface-base border border-line-2 rounded-xl p-4">
      <div class="flex items-start justify-between mb-2">
        <div>
          <div class="font-medium text-ink-0 text-sm">{lib.name}</div>
          <div class="text-xs text-ink-2">v{lib.version}</div>
        </div>
        {#if prebuilt}
          <StatusChip status={prebuilt.status} />
        {:else}
          <span class="text-xs text-ink-2">{t('prebuiltGrid.notBuilt')}</span>
        {/if}
      </div>
      {#if prebuilt}
        <div class="text-xs text-ink-2 mb-3">
          <RichText segments={t.rich('prebuiltGrid.storageId', { id: prebuilt.id.slice(0, 8) })} tags={{ id: storageId }} />
          {#if prebuilt.built_at}• {prebuilt.built_at.split('T')[0]}{/if}
        </div>
      {/if}
      {#if building === lib.id || serverBuilding}
        <div class="mb-3 space-y-2">
          {#if serverBuilding && building !== lib.id}<LoadingState variant="control" label={ts('building')} />{/if}
          <LoadingState variant="inline" label={`${lib.name} · ${t('manage.prebuiltStatus')}`} />
        </div>
      {/if}
      <Button
        variant={prebuilt ? 'secondary' : 'accent'}
        size="sm"
        class="w-full"
        onclick={() => onBuild(lib.id)}
        disabled={building === lib.id || !!prebuilt}
        ariaBusy={building === lib.id}
      >
        {#if building === lib.id}
          <LoadingState variant="control" label="" />
          {t('actions.creating')}
        {:else}
          {serverBuilding ? ts('building') : prebuilt ? t('prebuiltGrid.built') : t('list.createCta')}
        {/if}
      </Button>
    </div>
  {/each}
  {#if libraries.length === 0}
    <div class="col-span-2 text-ink-2 text-sm">{t('prebuiltGrid.librariesUnavailable')}</div>
  {/if}
</div>
