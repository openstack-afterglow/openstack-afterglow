<script lang="ts">
 import { untrack } from 'svelte';
 import { authDisplayContext } from '$lib/stores/authDisplayContext';
 import { intlLocale } from '$lib/i18n/runtime.svelte';
 import { t as commonT } from '$lib/i18n/ns/common';
 import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
 import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
 import RegexSearch from '$lib/components/ui/RegexSearch.svelte';

  import { t } from '$lib/i18n/ns/volume';
  import { attachmentServerId, useVolumeDetailController } from '$lib/stores/volumeDetailController.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';

  const s = useVolumeDetailController();
 let search = $state('');
 const searchId = $props.id();
 const columns = $derived<TableColumn<Record<string,unknown>>[]>([
 {key:'instance',label:t('attachmentsList.title'),value:row=>{const id=attachmentServerId(row);const name=s.attachmentName(id);return name.state==='resolved'?name.name:id||null;}},
 {key:'device',label:commonT('table.device'),value:row=>typeof row.device==='string'?row.device:null}
 ]);
 const view = createTableView({ locale: intlLocale,rows:()=>s.volume?.attachments??[],columns:()=>columns,search:()=>search,searchable:row=>columns.map(column=>String(column.value(row) ?? ''))});
 let viewOwner = '';
 $effect(() => authDisplayContext.subscribe(({ key }) => {
  if (viewOwner === key) return;
  viewOwner = key;
  untrack(() => { search = ''; view.reset(); });
 }));
</script>

{#if s.volume!.attachments.length > 0 || search || Object.keys(view.filters).length > 0 || view.sort}
  <div class="mb-4">
    <h3 class="text-xs text-ink-2 uppercase tracking-wide mb-2">{t('attachmentsList.title')}</h3>
    <RegexSearch id={searchId} bind:value={search} />
    <TableViewControls {view} class="" />
{#if view.rows.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{commonT('table.noMatches')}</p>{/if}
    <ResponsiveTable>
      {#snippet cards()}
        {#each view.rows as att}
          {@const serverId = attachmentServerId(att)}
          {@const instance = s.attachmentName(serverId)}
          {@const device = typeof att.device === 'string' ? att.device : ''}
          {#snippet attachmentDetails()}<p class="font-mono break-all">{serverId}</p>{/snippet}
          <CompactResourceCard details={serverId && (instance.state === 'resolved' || instance.state === 'loading') ? attachmentDetails : undefined}>
            {#if !serverId}
              <p class="text-ink-2">{t('attachmentsList.unknownInstance')}</p>
            {:else if instance.state === 'resolved'}
              <a href="/dashboard/instances/{serverId}" class="inline-flex items-center min-h-11 min-w-0 font-medium break-all text-warm-text hover:text-warm-text-hover">{instance.name}</a>
            {:else if instance.state === 'loading'}
              <p class="inline-flex items-center gap-1.5 text-ink-2"><LoadingState variant="control" label="" />{t('attachmentsList.resolvingName')}</p>
            {:else}
              <p class="font-mono break-all">{serverId}</p>
              <p class="text-ink-2">{t('attachmentsList.nameUnavailable')}</p>
            {/if}
            {#if device}<p class="font-mono text-ink-2 break-all">{device}</p>{/if}
          </CompactResourceCard>
        {/each}
      {/snippet}
    <ul class="space-y-1" aria-label={t('attachmentsList.title')}>
      {#each view.rows as att}
        {@const serverId = attachmentServerId(att)}
        {@const instance = s.attachmentName(serverId)}
        {@const device = typeof att.device === 'string' ? att.device : ''}
        <li class="bg-surface-base rounded-lg border border-line-2 px-3 py-2 text-xs text-ink-2 flex items-start justify-between gap-3">
          <div class="min-w-0">
            {#if !serverId}
              <span class="text-ink-2">{t('attachmentsList.unknownInstance')}</span>
            {:else if instance.state === 'resolved'}
              <a href="/dashboard/instances/{serverId}" class="block truncate text-sm text-warm-text hover:text-warm-text-hover transition-colors">{instance.name}</a>
              <span class="block font-mono break-all">{serverId}</span>
            {:else if instance.state === 'loading'}
              <span class="inline-flex items-center gap-1.5 text-ink-2"><LoadingState variant="control" label="" />{t('attachmentsList.resolvingName')}</span>
              <span class="block font-mono break-all">{serverId}</span>
            {:else}
              <span class="block font-mono text-ink-0 break-all">{serverId}</span>
              <span class="block text-ink-2">{t('attachmentsList.nameUnavailable')}</span>
            {/if}
          </div>
          {#if device}
            <span class="shrink-0 font-mono text-ink-2">{device}</span>
          {/if}
        </li>
      {/each}
    </ul>
    </ResponsiveTable>
  </div>
{/if}
