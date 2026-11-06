<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { createPalimpsestCatalogController } from '$lib/stores/palimpsestCatalogController.svelte';
  import type { CatalogLayer, CatalogSource } from '$lib/api/palimpsestCatalog';
  import { t } from '$lib/i18n/ns/palimpsest-catalog';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import Card from '$lib/components/ui/Card.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import { t as commonText } from '$lib/i18n/ns/common';
  import { auth } from '$lib/stores/auth';
  import { sessionScopeKey } from '$lib/utils/authSession';

  let { onbundle }: { onbundle?: (name: string) => void } = $props();
  const catalog = createPalimpsestCatalogController();
  let localSearch = $state('');
  const columns = $derived<TableColumn<CatalogLayer>[]>([
    { key: 'name', label: t('name'), value: row => row.name,
      filterMode: 'single', filterFreeValue: true,
      filterOptions: () => [...new Set((catalog.page?.items ?? []).map(row => row.name))].map(value => ({ value, label: value, count: null })),
      filterSelection: () => catalog.query ? [catalog.query] : null,
      onFilterChange: values => { if (!values || values.length === 1) { const query = values?.[0] ?? ''; if (query !== catalog.query) void catalog.search(query); } } },
    { key: 'origin', label: t('origin'), value: row => row.origin.kind },
    { key: 'digest', label: t('digest'), value: row => row.blob_digest },
    { key: 'chain', label: t('chain'), value: row => row.chain_complete, format: value => t(value ? 'chain.complete' : 'chain.incomplete') },
    { key: 'visibility', label: t('visibility'), value: row => row.visibility, format: (_value, row) => t(`visibility.${row.visibility}`) },
  ]);
  const view = createTableView({ rows: () => catalog.page?.items ?? [], columns: () => columns, search: () => localSearch,
    searchable: row => [row.name, row.kind, row.arch ?? '', row.blob_digest ?? '', row.origin.kind, row.origin.source, row.visibility], locale: intlLocale });
  let inspector = $state<HTMLElement | null>(null);
  let opener: HTMLElement | null = null;
  const sourceOptions = $derived([{ value: 'managed', label: t('source.managed') }, { value: 'hub', label: t('source.hub') }]);
  onMount(() => {
    let owner: string | null = null, active = true;
    const stop = auth.subscribe(state => {
      const next = sessionScopeKey(state);
      if (owner !== next) {
        localSearch = '';
        // Let the controller synchronously retire its old credential scope first.
        queueMicrotask(() => { if (active && owner === next) view.reset(); });
      }
      owner = next;
    });
    catalog.start();
    return () => { active = false; stop(); catalog.dispose(); };
  });
  async function inspect(id: string, event?: MouseEvent) {
    if (!catalog.selected && event?.currentTarget instanceof HTMLElement) opener = event.currentTarget;
    const pending = catalog.openDetail(id);
    await tick();
    inspector?.focus();
    await pending;
  }
  function closeInspector() {
    catalog.closeDetail();
    if (opener?.isConnected) opener.focus();
    opener = null;
  }
  function bytes(value: number | null) {
    if (value === null || !Number.isFinite(value) || value < 0) return t('unknown');
    const unit = value >= 1024 ** 3 ? 3 : value >= 1024 ** 2 ? 2 : value >= 1024 ? 1 : 0;
    return `${(value / 1024 ** unit).toLocaleString(intlLocale(), { maximumFractionDigits: 1 })} ${['B', 'KiB', 'MiB', 'GiB'][unit]}`;
  }
  function timestamp(value: string | null) {
    if (!value) return t('unknown');
    const normalized = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? `${value}Z` : value;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? t('unknown') : date.toLocaleString(intlLocale());
  }
</script>

{#snippet origin(row: CatalogLayer)}
  <span>{t(row.origin.kind === 'image-export' ? 'origin.imageExport' : `origin.${row.origin.kind}`)}</span>
  <span class="block text-xs text-ink-2">{t(({ 'hub-build': 'provenance.hubBuild', 'dockerfile-inline': 'provenance.dockerfileInline', 'github-dockerfile': 'provenance.githubDockerfile', 'upload-or-import': 'provenance.uploadOrImport', recipe: 'provenance.recipe', glance: 'provenance.glance', unknown: 'provenance.unknown' } as const)[row.origin.source])}</span>
{/snippet}

{#snippet relation(row: CatalogLayer)}
  <li class="min-w-0 space-y-1 border-b border-line py-2 last:border-0">
    <Button variant="link" size="sm" class="palimpsest-catalog-link" onclick={(event) => inspect(row.id, event)}>{row.name}</Button>
    <code class="block break-all text-xs text-ink-2 select-all">{row.blob_digest ?? row.id}</code>
    <p class="text-xs text-ink-2">{t(row.chain_complete ? 'chain.complete' : 'chain.incomplete')}</p>
  </li>
{/snippet}

<section class="mb-6 min-w-0 space-y-3" aria-labelledby="palimpsest-catalog-heading" data-testid="palimpsest-admin-catalog">
  <Card surface="base">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 space-y-1">
        <h2 id="palimpsest-catalog-heading" class="text-sm font-semibold text-ink-0">{t('heading')}</h2>
        <p class="text-sm text-ink-2">{t('description')}</p>
      </div>
      <Button variant="secondary" size="sm" ariaLabel={t('refreshLabel')} disabled={!catalog.authorized || catalog.loading} onclick={() => catalog.refresh()}>{t('refreshLabel')}</Button>
    </div>
    <div class="mt-4 space-y-3">
      <ToggleGroup value={catalog.source} options={sourceOptions} ariaLabel={t('source.label')} onchange={(value) => catalog.setSource(value as CatalogSource)} />
      <p class="text-xs text-ink-2">{t(catalog.source === 'managed' ? 'source.managedHelp' : 'source.hubHelp')}</p>
    </div>
  </Card>
  <RegexSearch id="palimpsest-catalog-regex" bind:value={localSearch} />
  <p class="text-xs text-ink-2">{commonText('table.mixedScope')}</p>
  <TableViewControls {view} class={catalog.page?.items.length ? 'lg:hidden' : ''} />
  {#if catalog.page?.items.length && !view.rows.length}<p class="text-sm text-ink-2">{commonText('table.noMatches')}</p>{/if}
  {#if !catalog.authorized}
    <Alert tone="info">{t('authority')}</Alert>
  {:else if catalog.loading}
    <LoadingState variant="surface" label={t('loading')} />
  {:else if catalog.error}
    <Alert tone="danger">{t(`error.${catalog.error}`)}
      {#snippet actions()}<Button variant="secondary" size="sm" onclick={() => catalog.refresh()}>{t('retry')}</Button>{/snippet}
    </Alert>
  {:else if catalog.page}
    <p class="text-xs text-ink-2" role="status">{t('page', { offset: catalog.page.offset, count: catalog.page.items.length })}</p>
    {#if catalog.page.items.length === 0}
      <EmptyState headline={t(catalog.query ? 'empty.search' : 'empty.title')} description={t(catalog.query ? 'empty.searchHelp' : 'empty.help')} />
    {:else}
      <ResponsiveTable>
        {#snippet cards()}
          {#each view.rows as row (row.id)}
            <CompactResourceCard selected={catalog.selected === row.id}>
              <h3 class="text-sm font-medium break-all">{row.name}</h3>
              <p class="text-xs text-ink-2">{row.kind} · {row.arch ?? t('unknown')}</p>
              <div class="text-sm">{@render origin(row)}</div>
              <p class="text-xs text-ink-2">{t(row.chain_complete ? 'chain.complete' : 'chain.incomplete')}</p>
              {#snippet details()}<dl><div><dt>{t('visibility')}</dt><dd>{t(`visibility.${row.visibility}`)}</dd></div><div><dt>{t('size')}</dt><dd>{bytes(row.size_bytes)}</dd></div></dl><code class="block break-all mt-2">{row.blob_digest ?? t('unknown')}</code>{/snippet}
              {#snippet actions()}<Button variant="secondary" size="sm" onclick={(event) => inspect(row.id, event)}>{t('details')}</Button>{/snippet}
            </CompactResourceCard>
          {/each}
        {/snippet}
        <TableShell density="compact"><table>
          <thead><tr>{#each view.columns as column (column.key)}<TableColumnHeader {view} columnKey={column.key} />{/each}<th>{t('details')}</th></tr></thead>
          <tbody>{#each view.rows as row (row.id)}<tr data-selected={catalog.selected === row.id}>
            <td><span class="block max-w-64 truncate" title={row.name}>{row.name}</span><span class="text-xs text-ink-2">{row.kind} · {row.arch ?? t('unknown')}</span></td>
            <td>{@render origin(row)}</td><td><code title={row.blob_digest ?? undefined}>{row.blob_digest ? `${row.blob_digest.slice(0, 19)}…` : t('unknown')}</code></td>
            <td>{t(row.chain_complete ? 'chain.complete' : 'chain.incomplete')}</td><td>{t(`visibility.${row.visibility}`)}</td>
            <td><Button variant="secondary" size="sm" onclick={(event) => inspect(row.id, event)}>{t('details')}</Button></td>
          </tr>{/each}</tbody>
        </table></TableShell>
      </ResponsiveTable>
    {/if}
    <div class="flex flex-wrap gap-2" aria-label={t('pagination')}>
      <Button variant="secondary" size="sm" disabled={!catalog.canBack} onclick={() => catalog.back()}>{t('previous')}</Button>
      <Button variant="secondary" size="sm" disabled={!catalog.page.has_more} onclick={() => catalog.next()}>{t('next')}</Button>
    </div>
  {/if}
  {#if catalog.authorized && catalog.selected}
    <section bind:this={inspector} tabindex="-1" aria-label={t('details')} data-testid="palimpsest-catalog-inspector" class="catalog-inspector min-w-0">
      <Card surface="base">
        <div class="flex items-center justify-between gap-3"><h3 class="text-sm font-semibold">{t('details')}</h3><Button variant="ghost" size="sm" onclick={closeInspector}>{t('close')}</Button></div>
        {#if catalog.detailLoading}<LoadingState variant="section" label={t('loading')} class="mt-3" />
        {:else if catalog.detailError}<Alert tone="danger" class="mt-3">{t(`error.${catalog.detailError}`)}{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => inspect(catalog.selected!)}>{t('retry')}</Button>{/snippet}</Alert>
        {:else if catalog.detail}
          {@const item = catalog.detail}
          <div class="mt-3 space-y-4">
            <h4 class="text-sm font-semibold break-all">{item.name}</h4>
            {#if !item.chain_complete}<Alert tone="warning">{t('chain.warning')}</Alert>{/if}
            {#if item.origin.evidence === 'unrecorded'}<Alert tone="info">{t('origin.unrecorded')}</Alert>{/if}
            <dl class="grid min-w-0 grid-cols-1 gap-3 text-sm md:grid-cols-2">
              <div class="min-w-0 md:col-span-2"><dt class="text-xs text-ink-2">{t('digest')}</dt><dd class="break-all font-mono select-all">{item.blob_digest ?? t('unknown')}</dd></div>
              <div><dt class="text-xs text-ink-2">{t('origin')}</dt><dd>{@render origin(item)}</dd></div>
              <div><dt class="text-xs text-ink-2">{t('evidence')}</dt><dd>{t(`evidence.${item.origin.evidence}`)}</dd></div>
              <div class="min-w-0"><dt class="text-xs text-ink-2">{t('id')}</dt><dd class="break-all font-mono select-all">{item.id}</dd></div>
              <div class="min-w-0"><dt class="text-xs text-ink-2">{t('project')}</dt><dd class="break-all font-mono">{item.project_id ?? t('unknown')}</dd></div>
              <div><dt class="text-xs text-ink-2">{t('visibility')}</dt><dd>{t(`visibility.${item.visibility}`)}</dd></div>
              <div><dt class="text-xs text-ink-2">{t('size')}</dt><dd>{bytes(item.size_bytes)}</dd></div>
              <div><dt class="text-xs text-ink-2">{t('platform')}</dt><dd>{item.arch ?? t('unknown')} · {item.ubuntu_base ?? t('unknown')}</dd></div>
              <div><dt class="text-xs text-ink-2">{t('created')}</dt><dd>{timestamp(item.created_at)}</dd></div>
              <div><dt class="text-xs text-ink-2">{t('buildId')}</dt><dd class="break-all font-mono">{item.origin.build_id ?? t('unknown')}</dd></div>
              <div><dt class="text-xs text-ink-2">{t('jobId')}</dt><dd class="break-all font-mono">{item.origin.job_id ?? t('unknown')}</dd></div>
              <div class="min-w-0 md:col-span-2"><dt class="text-xs text-ink-2">{t('revision')}</dt><dd class="break-all font-mono select-all">{item.origin.revision ?? t('unknown')}</dd></div>
            </dl>
            <section class="space-y-2"><h4 class="text-sm font-semibold">{t('parent')}</h4>
              {#if item.parent_id}<Button variant="link" size="sm" class="palimpsest-catalog-link" onclick={(event) => inspect(item.parent_id!, event)}>{item.parent_id}</Button><code class="block break-all text-xs select-all">{item.parent_digest ?? t('unknown')}</code>
              {:else}<p class="text-sm text-ink-2">{t(item.chain_complete ? 'parent.none' : 'parent.unknown')}</p>{/if}
            </section>
            <div class="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
              <section><h4 class="text-sm font-semibold">{t('ancestors')}</h4><p class="text-xs text-ink-2">{t('ancestors.help')}</p>{#if item.ancestors.length}<ol class="mt-2">{#each item.ancestors as row (row.id)}{@render relation(row)}{/each}</ol>{:else}<p class="mt-2 text-sm text-ink-2">{t('relations.none')}</p>{/if}</section>
              <section><h4 class="text-sm font-semibold">{t('children')}</h4>{#if item.children.length}<ul class="mt-2">{#each item.children as row (row.id)}{@render relation(row)}{/each}</ul>{:else}<p class="mt-2 text-sm text-ink-2">{t('relations.none')}</p>{/if}{#if item.children_has_more}<p class="mt-2 text-xs text-ink-2">{t('children.more')}</p>{/if}</section>
            </div>
            <section><h4 class="text-sm font-semibold">{t('bundles')}</h4><p class="text-xs text-ink-2">{t('bundles.help')}</p>{#if item.bundles.length}<ul class="mt-2 space-y-2">{#each item.bundles as bundle}<li class="text-sm break-all"><Button variant="link" size="sm" class="palimpsest-catalog-link" onclick={() => onbundle?.(bundle)}>{bundle}</Button></li>{/each}</ul>{:else}<p class="mt-2 text-sm text-ink-2">{t('bundles.none')}</p>{/if}</section>
          </div>
        {/if}
      </Card>
    </section>
  {/if}
</section>

<style>
  .catalog-inspector :global(.palimpsest-catalog-link) { max-width: 100%; white-space: normal; overflow-wrap: anywhere; text-align: left; }
  .catalog-inspector:focus-visible { outline: none; box-shadow: var(--focus-ring); }
</style>
