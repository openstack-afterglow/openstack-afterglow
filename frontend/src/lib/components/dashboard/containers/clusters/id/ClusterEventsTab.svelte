<script lang="ts">
  import { t } from '$lib/i18n/ns/containers-shell';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import type { StackEvent } from '$lib/types/cluster';
  import { resourceStatusColor } from '$lib/types/cluster';
 import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
 import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import { t as tc } from '$lib/i18n/ns/common';
  import type { TableView } from '$lib/utils/tableView.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';

  let { events, view, search = $bindable(''), loading, onRefresh }: {
    events: StackEvent[]; view: TableView<StackEvent>; search?: string; loading: boolean; onRefresh: () => void;
  } = $props();
</script>

<div class="flex items-center justify-between mb-3">
  <div class="text-sm text-ink-2">{tc('table.loadedScope')}</div>
  <button onclick={onRefresh} class="text-xs text-ink-2 hover:text-ink-0 transition-colors">{t('clusters.actions.refresh')}</button>
</div>
<RegexSearch id="legacy-cluster-events-search" bind:value={search} class="mb-3" />
<TableViewControls {view} />
{#if loading && events.length > 0}<LoadingState variant="inline" />{/if}
{#if loading && events.length === 0}
  <LoadingState variant="section" />
{:else if events.length === 0}
  <div class="text-ink-2 text-sm">{t('clusters.events.unavailable')}</div>
{:else if view.rows.length === 0}
  <p role="status" class="text-ink-2 text-sm">{tc('table.noMatches')}</p>
{/if}
 <ResponsiveTable>
  {#snippet cards()}
   {#each view.rows as e}
    <CompactResourceCard>
     <strong class="text-sm break-all">{e.resource_name}</strong><span class="text-xs {resourceStatusColor(e.resource_status)}">{e.resource_status}</span><p class="text-xs text-ink-2">{e.event_time?.slice(0, 19).replace('T', ' ') ?? t('clusters.placeholder')}</p>
     {#snippet details()}<p class="text-xs break-all">{t('clusters.events.reason')}: {e.resource_status_reason ?? t('clusters.placeholder')}</p>{/snippet}
    </CompactResourceCard>
   {/each}
  {/snippet}
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
          {#each view.columns as column (column.key)}
            <TableColumnHeader {view} columnKey={column.key} />
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each view.rows as e}
          <tr class="border-b border-line/50 text-xs">
            <td class="py-2 pr-4 text-ink-2 font-mono whitespace-nowrap">{e.event_time?.slice(0, 19).replace('T', ' ') ?? t('clusters.placeholder')}</td>
            <td class="py-2 pr-4 text-ink-0">{e.resource_name}</td>
            <td class="py-2 pr-4">
              <span class="{resourceStatusColor(e.resource_status)} font-medium">{e.resource_status}</span>
            </td>
            <td class="py-2 text-ink-2">{e.resource_status_reason ?? t('clusters.placeholder')}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
 </ResponsiveTable>
