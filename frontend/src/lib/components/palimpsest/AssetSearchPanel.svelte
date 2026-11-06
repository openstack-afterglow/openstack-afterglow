<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import type { PackageIdentity, PackageSummary } from '$lib/api/palimpsestPackages';
  import type { ReusableAsset, CloudEnvironment, AssetIdentity } from '$lib/api/palimpsestAssets';
  import { localAssetCommands, hubAssetCommands, packageAssetCommands, sameAssetActor, MAX_ASSET_DOWNLOAD_BYTES } from '$lib/api/palimpsestAssets';
  import { createPalimpsestAssetsController, type AssetSource } from '$lib/stores/palimpsestAssetsController.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
  import { projectPermissions, serviceCapabilities } from '$lib/stores/servicePermissions';
  import { t } from '$lib/i18n/ns/palimpsest-assets';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Card from '$lib/components/ui/Card.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import SearchSelect from '$lib/components/ui/SearchSelect.svelte';
  import SelectInput from '$lib/components/ui/SelectInput.svelte';
  import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import TableShell from '$lib/components/ui/TableShell.svelte';
  import FormModal from '$lib/components/ui/FormModal.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import UsageScheduleFields from '$lib/components/instance/UsageScheduleFields.svelte';
  import { t as usageText } from '$lib/i18n/ns/usage-schedule';
  import { defaultUsageDraft, requiresUsageSchedule, usageDraftError, usagePayload } from '$lib/utils/instanceUsage';
  import { sessionScopeKey } from '$lib/utils/authSession';
  import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import { t as commonText } from '$lib/i18n/ns/common';

  let { identity, onGuide }: { identity: AssetIdentity | null; onGuide: () => void } = $props();
  const permissionReady = $derived(!!$projectPermissions.permissions && !$projectPermissions.loading && !$projectPermissions.error);
  const allowed = $derived($authReady && !$logoutInProgress && !$projectSwitching && permissionReady && $serviceCapabilities('palimpsest-inventory_reader'));
  const downloadable = $derived(allowed && $serviceCapabilities('palimpsest-download_user'));
  const writable = $derived(downloadable && !!$auth.canWrite);
  const assets = createPalimpsestAssetsController(() => identity, () => allowed, () => downloadable, () => !!$auth.canWrite);
  let localSearch = $state('');
  const hubColumns = $derived<TableColumn<ReusableAsset>[]>([
    { key: 'name', label: t('name'), value: row => row.name,
      filterMode: 'single', filterFreeValue: true,
      filterOptions: () => [...new Set((assets.hub?.items ?? []).map(row => row.name))].map(value => ({ value, label: value, count: null })),
      filterSelection: () => assets.query ? [assets.query] : null,
      onFilterChange: values => { if (!values || values.length === 1) { const query = values?.[0] ?? ''; if (query !== assets.query) void assets.search(query); } } },
    { key: 'platform', label: t('platform'), value: row => row.arch },
    { key: 'access', label: t('access'), value: row => row.visibility, format: (_value, row) => t(`visibility.${row.visibility}`) },
    { key: 'size', label: t('size'), value: row => row.size_bytes, format: (_value, row) => bytes(row.size_bytes) },
  ]);
  const packageColumns = $derived<TableColumn<PackageSummary>[]>([
    { key: 'name', label: t('name'), value: row => `${row.namespace}/${row.name}`,
      filterMode: 'single', filterFreeValue: true,
      filterOptions: () => [...new Set((assets.packages?.items ?? []).map(row => row.name))].map(value => ({ value, label: value, count: null })),
      filterSelection: () => assets.query ? [assets.query] : null,
      onFilterChange: values => { if (!values || values.length === 1) { const query = values?.[0] ?? ''; if (query !== assets.query) void assets.search(query); } } },
    { key: 'type', label: commonText('table.type'), value: row => row.package_type, format: (_value, row) => t(row.package_type === 'runtime-bundle' ? 'type.bundle' : 'type.oci') },
    { key: 'version', label: t('version.label'), value: row => row.tags.map(tag => tag.tag).join(', ') },
  ]);
  const environmentColumns = $derived<TableColumn<CloudEnvironment>[]>([
    { key: 'name', label: t('name'), value: row => row.name,
      filterMode: 'single', filterFreeValue: true,
      filterOptions: () => [...new Set((assets.environments?.items ?? []).map(row => row.name))].map(value => ({ value, label: value, count: null })),
      filterSelection: () => assets.query ? [assets.query] : null,
      onFilterChange: values => { if (!values || values.length === 1) { const query = values?.[0] ?? ''; if (query !== assets.query) void assets.search(query); } } },
    { key: 'platform', label: t('platform'), value: row => row.ubuntu_base },
    { key: 'size', label: t('size'), value: row => row.size_bytes, format: (_value, row) => bytes(row.size_bytes) },
    { key: 'cloud', label: t('cloud.supported'), value: row => row.cloud_supported, format: value => t(value ? 'cloud.supported' : 'cloud.unsupported') },
  ]);
  const hubView = createTableView({ rows: () => assets.hub?.items ?? [], columns: () => hubColumns, search: () => localSearch,
    searchable: row => [row.name, row.arch ?? '', row.ubuntu_base ?? '', row.visibility, row.blob_digest], locale: intlLocale });
  const packageView = createTableView({ rows: () => assets.packages?.items ?? [], columns: () => packageColumns, search: () => localSearch,
    searchable: row => [row.namespace, row.name, `${row.namespace}/${row.name}`, row.package_type, ...row.tags.flatMap(tag => [tag.tag, tag.digest])], locale: intlLocale });
  const environmentView = createTableView({ rows: () => assets.environments?.items ?? [], columns: () => environmentColumns, search: () => localSearch,
    searchable: row => [row.name, row.ubuntu_base ?? ''], locale: intlLocale });
  let notice = $state<'copied' | 'copyFailed' | ''>('');
  let cloudOpen = $state(false);
  let flavor = $state(''), network = $state(''), key = $state(''), serverName = $state('');
  let usageSchedule = $state(defaultUsageDraft());
  const selectedFlavor = $derived(assets.resources?.flavors.find(item => item.id === flavor));
  const scheduleRequired = $derived(requiresUsageSchedule(selectedFlavor));
  const scheduleReady = $derived(!scheduleRequired || !usageDraftError(usageSchedule));
  function selectFlavor(value: string) {
    if (flavor !== value) usageSchedule = defaultUsageDraft();
    flavor = value;
  }
  let localMethod = $state('cli');
  let unpackConfirmed = $state(false);
  const requiresUnpack = $derived(!!assets.selection && assets.selection.source !== 'environments'
    && (assets.selection.source === 'packages' ? assets.selection.asset.package_type === 'runtime-bundle' : localMethod === 'browser' && assets.selection.asset.local_supported));
  const filename = $derived.by(() => {
    const selected = assets.selection;
    if (!selected || selected.source === 'environments') return '';
    const digest = selected.source === 'packages' ? assets.version?.root_digest : selected.asset.blob_digest;
    if (!digest || digest.length !== 71 || !/^sha256:[0-9a-f]{64}$/.test(digest)) return '';
    const kind = selected.source === 'packages' && selected.asset.package_type === 'oci-image' ? 'image' : 'runtime';
    return `palimpsest-${kind}-${digest.slice(7)}.oci.tar`;
  });
  const localCommand = $derived.by(() => {
    const selected = assets.selection;
    if (!selected || selected.source === 'environments' || !filename) return '';
    if (selected.source === 'hub' && (!selected.asset.local_supported || !selected.asset.base_image_digest)) return '';
    if (requiresUnpack && !unpackConfirmed) return '';
    if (localMethod === 'browser') return localAssetCommands(selected.source === 'packages' ? selected.asset.package_type : 'runtime-bundle', filename);
    if (selected.source === 'hub') return hubAssetCommands(selected.asset.blob_digest);
    return assets.version ? packageAssetCommands(assets.context?.package_authority ?? null, selected.asset.namespace, selected.asset.name, assets.version.root_digest, selected.asset.package_type, filename) : '';
  });
  const selectionKey = $derived(assets.selection ? `${assets.selection.source}:${assets.selection.source === 'packages' ? assets.selection.asset.package_id : assets.selection.asset.id}` : '');
  const canDownloadSelection = $derived(downloadable && !!assets.selection && assets.selection.source !== 'environments'
    && (assets.selection.source === 'packages' ? !!assets.version && assets.version.archive_size_bytes <= MAX_ASSET_DOWNLOAD_BYTES : assets.selection.asset.download_allowed && assets.selection.asset.local_supported && !!assets.selection.asset.base_image_digest && assets.selection.asset.chain_complete && (assets.selection.asset.size_bytes ?? Infinity) + 64 * 1024 <= MAX_ASSET_DOWNLOAD_BYTES));
  $effect(() => {
    identity?.token; identity?.projectId; identity?.userId; identity?.sessionId; allowed; downloadable; writable;
    untrack(() => assets.bind());
    if (!allowed || !identity) cloudOpen = false;
  });
  $effect(() => { selectionKey; untrack(() => { notice = ''; cloudOpen = false; flavor = ''; network = ''; key = ''; serverName = ''; usageSchedule = defaultUsageDraft(); unpackConfirmed = false; }); });
  onMount(() => {
    let active = true, lastOwner: string | null = null;
    const stopOwner = auth.subscribe((state) => {
      const owner = sessionScopeKey(state);
      if (lastOwner !== null && owner !== lastOwner) { assets.invalidateActor(); localSearch = ''; hubView.reset(); packageView.reset(); environmentView.reset(); cloudOpen = false; flavor = ''; network = ''; key = ''; serverName = ''; usageSchedule = defaultUsageDraft(); }
      lastOwner = owner;
      queueMicrotask(() => { if (active) assets.bind(); });
    });
    const stopPermissions = projectPermissions.subscribe((state) => {
      if (!state.permissions || state.loading || state.error) assets.pauseAuthority();
      queueMicrotask(() => { if (active) assets.bind(); });
    });
    return () => { active = false; stopOwner(); stopPermissions(); assets.dispose(); };
  });
  createAutoRefresh(async () => {
    if (assets.consume && !['active', 'error', 'indeterminate'].includes(assets.consume.status)) await assets.refreshConsume();
  }, { storageKey: 'palimpsest-asset-consume', defaultInterval: 5, invokeOnMount: false });
  function bytes(value: number | null | undefined) {
    if (value == null || !Number.isFinite(value) || value < 0) return t('unknown');
    const unit = value >= 1024 ** 3 ? 3 : value >= 1024 ** 2 ? 2 : value >= 1024 ? 1 : 0;
    return `${(value / 1024 ** unit).toLocaleString(intlLocale(), { maximumFractionDigits: 1 })} ${['B', 'KiB', 'MiB', 'GiB'][unit]}`;
  }
  async function selectHub(asset: ReusableAsset) { await assets.select({ source: 'hub', asset }); await focusUse(); }
  async function selectPackage(asset: PackageSummary) { const selecting = assets.select({ source: 'packages', asset }); await focusUse(); await selecting; }
  async function selectEnvironment(asset: CloudEnvironment) { await assets.select({ source: 'environments', asset }); await focusUse(); }
  async function focusUse() { await tick(); document.getElementById('palimpsest-asset-use-heading')?.focus({ preventScroll: false }); }
  async function save() {
    const selected = assets.selection, version = assets.version, expectedIdentity = identity;
    const blob = await assets.download();
    if (!blob || selected !== assets.selection || version !== assets.version || !sameAssetActor(identity, expectedIdentity) || !downloadable) return;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function copy() {
    const command = localCommand, selected = assets.selection;
    try { await navigator.clipboard.writeText(command); if (selected === assets.selection) notice = 'copied'; }
    catch { if (selected === assets.selection) notice = 'copyFailed'; }
  }
  async function openCloud() {
    if (!writable || assets.consumeLocked || assets.selection?.source !== 'environments' || !assets.selection.asset.cloud_supported) return;
    cloudOpen = true; await assets.loadResources();
  }
  async function create() {
    const selected = assets.selection;
    if (!writable || assets.consumeLocked || selected?.source !== 'environments' || !selectedFlavor || !scheduleReady || !network || !key || !serverName.trim() || assets.busy.consume || assets.busy.resources || assets.errors.resources) return;
    if (scheduleRequired && usageDraftError(usageSchedule)) {
      // Refresh the shared field error after an idle form's deadline passes.
      usageSchedule = { ...usageSchedule };
      return;
    }
    const submittedDraft = usageSchedule, actor = identity;
    await assets.create({ revision: selected.asset.revision, flavor_id: flavor, network_id: network, key_name: key, server_name: serverName.trim(), ssh_username: 'ubuntu', ...(scheduleRequired ? { usage_schedule: usagePayload(usageSchedule) } : {}) });
    if (assets.consume && assets.selection === selected && sameAssetActor(actor, identity)) {
      if (usageSchedule === submittedDraft) usageSchedule = defaultUsageDraft();
      cloudOpen = false;
    }
  }
  async function cleanupOperation() {
    const actor = identity, operation = assets.consume;
    if (!actor || !operation || !$auth.canWrite || assets.busy.cleanup) return;
    if (await confirmDialog(t('cloud.cleanupConfirm', { id: operation.consume_id }), { confirmLabel: t('cloud.cleanup') })
      && sameAssetActor(actor, identity) && assets.consume?.consume_id === operation.consume_id && $auth.canWrite) await assets.cleanup();
  }
  function previous(source: AssetSource, offset: number) { void assets.load(source, Math.max(0, offset - 20)); }
</script>

<section class="space-y-6 min-w-0" aria-label={t('heading')}>
  <div class="flex justify-end"><Button variant="secondary" disabled={!allowed} onclick={() => assets.search(assets.query)}>{commonText('autoRefresh.refresh')}</Button></div>
  <RegexSearch id="asset-loaded-regex" bind:value={localSearch} />
  <p class="text-xs text-ink-2">{commonText('table.mixedScope')}</p>
  {#if !identity}<Alert tone="info">{t('identity')}</Alert>
  {:else if $projectPermissions.error}<Alert tone="danger">{$projectPermissions.error}</Alert>
  {:else if !permissionReady}<LoadingState variant="section" />
  {:else if !allowed}<Alert tone="warning">{t('denied')}</Alert>
  {:else}
    <section class="space-y-3" aria-labelledby="asset-shared-heading">
      <div class="flex flex-wrap items-baseline justify-between gap-2"><h3 id="asset-shared-heading" class="text-sm font-semibold">{t('source.hub')}</h3><p class="text-xs text-ink-2">{t('source.hubHelp')}</p></div>
      <TableViewControls view={hubView} class={assets.hub?.items.length ? 'lg:hidden' : ''} />
      {#if assets.hub?.items.length && !hubView.rows.length}<p class="text-sm text-ink-2">{commonText('table.noMatches')}</p>{/if}
      {#if assets.errors.hub}{@render failure('hub')}{:else if assets.busy.hub && !assets.hub}<LoadingState variant="section" />
      {:else if assets.hub}
        {#if assets.busy.hub}<LoadingState variant="inline" />{/if}
        {#if !assets.hub.items.length}{@render empty(assets.hub.has_more)}{:else}
          <ResponsiveTable>{#snippet cards()}{#each hubView.rows as asset (asset.id)}<CompactResourceCard><h4 class="text-sm font-medium break-words">{asset.name}</h4><p class="text-xs text-ink-2">{asset.arch ?? t('unknown')} · {bytes(asset.size_bytes)}</p><p class="text-xs">{asset.chain_complete ? t('dependencies.ready') : t('dependencies.incomplete')}</p>{#snippet details()}<p class="text-xs">{t(`visibility.${asset.visibility}`)} · {asset.ubuntu_base ?? t('unknown')}</p>{/snippet}{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => selectHub(asset)}>{t('use')}</Button>{/snippet}</CompactResourceCard>{/each}{/snippet}
            <TableShell><table><thead><tr>{#each hubView.columns as column (column.key)}<TableColumnHeader view={hubView} columnKey={column.key} />{/each}<th>{t('actions')}</th></tr></thead><tbody>{#each hubView.rows as asset (asset.id)}<tr><td><span class="font-medium">{asset.name}</span><p class="text-xs text-ink-2">{asset.ubuntu_base ?? t('unknown')}</p></td><td>{asset.arch ?? t('unknown')}</td><td>{t(`visibility.${asset.visibility}`)}</td><td>{bytes(asset.size_bytes)}</td><td><Button variant="secondary" size="sm" onclick={() => selectHub(asset)}>{t('use')}</Button></td></tr>{/each}</tbody></table></TableShell>
          </ResponsiveTable>
        {/if}{@render paging('hub', assets.hub.offset, assets.hub.next_offset, assets.hub.items.length)}
      {/if}
    </section>
    <section class="space-y-3" aria-labelledby="asset-packages-heading">
      <div class="flex flex-wrap items-baseline justify-between gap-2"><h3 id="asset-packages-heading" class="text-sm font-semibold">{t('source.packages')}</h3><p class="text-xs text-ink-2">{t('source.packagesHelp')}</p></div>
      <TableViewControls view={packageView} class="" />
      {#if assets.packages?.items.length && !packageView.rows.length}<p class="text-sm text-ink-2">{commonText('table.noMatches')}</p>{/if}
      {#if assets.errors.packages}{@render failure('packages')}{:else if assets.busy.packages && !assets.packages}<LoadingState variant="section" />
      {:else if assets.packages}
        {#if assets.busy.packages}<LoadingState variant="inline" />{/if}
        {#if !assets.context?.namespace}<Alert tone="info">{t('packages.unregistered')}</Alert>
        {:else if !assets.packages.items.length}{@render empty()}
        {:else}<div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">{#each packageView.rows as asset (asset.package_id)}<CompactResourceCard><h4 class="text-sm font-medium break-words">{asset.name}</h4><p class="text-xs text-ink-2">{asset.namespace} · {t(asset.package_type === 'runtime-bundle' ? 'type.bundle' : 'type.oci')}</p><p class="break-words text-xs">{asset.tags.map((tag) => tag.tag).join(', ') || t('version.untagged')}</p>{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => selectPackage(asset)}>{t('use')}</Button>{/snippet}</CompactResourceCard>{/each}</div>{/if}
        {#if assets.packages.next_cursor}<Button variant="secondary" size="sm" onclick={() => assets.load('packages', assets.packages!.next_cursor!)}>{t('next')}</Button>{/if}
      {/if}
    </section>
    <section class="space-y-3" aria-labelledby="asset-cloud-heading">
      <div class="flex flex-wrap items-baseline justify-between gap-2"><h3 id="asset-cloud-heading" class="text-sm font-semibold">{t('source.environments')}</h3><p class="text-xs text-ink-2">{t('source.environmentsHelp')}</p></div>
      <TableViewControls view={environmentView} class="" />
      {#if assets.environments?.items.length && !environmentView.rows.length}<p class="text-sm text-ink-2">{commonText('table.noMatches')}</p>{/if}
      {#if assets.errors.environments}{@render failure('environments')}{:else if assets.busy.environments && !assets.environments}<LoadingState variant="section" />
      {:else if assets.environments}
        {#if assets.busy.environments}<LoadingState variant="inline" />{/if}
        {#if !assets.environments.items.length}{@render empty(assets.environments.has_more)}
        {:else}<div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">{#each environmentView.rows as asset (asset.id)}<CompactResourceCard><h4 class="text-sm font-medium break-words">{asset.name}</h4><p class="text-xs text-ink-2">{asset.ubuntu_base ?? t('unknown')} · {bytes(asset.size_bytes)}</p><p class="text-xs">{asset.cloud_supported ? t('cloud.supported') : t('cloud.unsupported')}</p>{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => selectEnvironment(asset)}>{t('use')}</Button>{/snippet}</CompactResourceCard>{/each}</div>{/if}
        {@render paging('environments', assets.environments.offset, assets.environments.next_offset, assets.environments.items.length)}
      {/if}
    </section>
    {#if assets.selection}<Card surface="base" class="space-y-4">
      <div class="flex flex-wrap items-start justify-between gap-3"><h3 id="palimpsest-asset-use-heading" tabindex="-1" class="break-words text-sm font-semibold">{t('selected', { name: assets.selection.asset.name })}</h3><Button variant="ghost" size="sm" onclick={() => assets.close()}>{t('close')}</Button></div>
      {#if assets.selection.source === 'environments'}
        <p class="text-sm text-ink-2">{t('cloud.description')}</p>
        {#if !assets.selection.asset.cloud_supported}<Alert tone="warning">{assets.selection.asset.cloud_reason ?? t('cloud.unsupported')}</Alert>{/if}
        <Button variant="primary" disabled={!writable || assets.consumeLocked || !assets.selection.asset.cloud_supported || !!assets.busy.consume} onclick={openCloud}>{t('cloud.create')}</Button>
        {#if !writable}<p class="text-sm text-ink-2">{t('cloud.denied')}</p>{/if}
        <p class="text-xs text-ink-2">{t('local.managed')}</p><Button variant="link" onclick={onGuide}>{t('local.guide')}</Button>
      {:else}
        {#if assets.selection.source === 'packages'}
          {#if assets.busy.versions}<LoadingState variant={assets.versions ? 'inline' : 'section'} />{/if}
          {#if assets.errors.versions}<Alert tone="danger">{assets.errors.versions}</Alert>{/if}
          {#if assets.versions?.items.length}<Field label={t('version.label')} for="asset-package-version"><SelectInput id="asset-package-version" value={assets.version?.root_digest ?? ''} onchange={(event) => { assets.version = assets.versions!.items.find((item) => item.root_digest === (event.target as HTMLSelectElement).value) ?? null; }}>
            {#each assets.versions.items as version}<option value={version.root_digest}>{assets.selection.asset.tags.filter((tag) => tag.digest === version.root_digest).map((tag) => tag.tag).join(', ') || t('version.untagged')} · {version.root_digest.slice(7, 19)} · {bytes(version.total_bytes)}</option>{/each}
          </SelectInput></Field>{/if}
          {#if assets.versions?.next_cursor}<Button variant="ghost" size="sm" onclick={() => assets.moreVersions()}>{t('version.more')}</Button>{/if}
          {#if assets.selection.asset.package_type === 'oci-image'}<Alert tone="warning">{t('local.oci')}</Alert>{/if}
        {:else if !assets.selection.asset.chain_complete}<Alert tone="warning">{t('dependencies.incomplete')}</Alert>
        {:else if !assets.selection.asset.local_supported || !assets.selection.asset.base_image_digest}<Alert tone="warning">{t('local.incompatible')}</Alert>{/if}
        <ToggleGroup value={localMethod} ariaLabel={t('local.method')} options={[{ value: 'cli', label: t('local.cliMethod') }, { value: 'browser', label: t('local.browserMethod') }]} onchange={(value) => localMethod = value} />
        <p class="text-sm text-ink-2">{t('local.cliHelp')}</p>
        {#if requiresUnpack}
          <Alert tone="warning">{t('local.unpackPrerequisite')}</Alert>
          <label class="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" bind:checked={unpackConfirmed} />{t('local.unpackConfirmed')}</label>
        {/if}
        <div class="flex flex-wrap gap-2">{#if localMethod === 'browser'}<Button variant="secondary" disabled={!canDownloadSelection || !!assets.busy.download} onclick={save}>{#if assets.busy.download}<LoadingState variant="control" label={t('downloading')} />{:else}{t('download')}{/if}</Button>{/if}<Button variant="link" onclick={onGuide}>{t('local.guide')}</Button></div>
        {#if assets.errors.download}<Alert tone="danger">{assets.errors.download}</Alert>{/if}
        {#if localMethod === 'browser'}<p class="text-sm text-ink-2">{t('local.help')}</p>{/if}
        {#if localCommand}
          <div class="min-w-0 rounded-md border border-line bg-surface-sunken p-3">
            <div class="mb-2 flex flex-wrap items-center justify-between gap-2"><h4 class="text-xs font-medium">{t('local.commands')}</h4><Button variant="ghost" size="sm" onclick={copy}>{t('copy')}</Button></div>
            <!-- svelte-ignore a11y_no_noninteractive_tabindex (Named horizontally scrollable code region must remain keyboard reachable per DESIGN.md.) -->
            <pre role="region" aria-label={t('local.commands')} tabindex="0" class="overflow-x-auto text-xs"><code>{localCommand}</code></pre>
          </div>
        {:else if assets.selection.source === 'packages' && (!requiresUnpack || unpackConfirmed)}<Alert tone="info">{t('local.noReference')}</Alert>{/if}
        {#if notice}<p role="status" class="text-xs text-ink-2">{t(notice)}</p>{/if}
        <p class="text-xs text-ink-2">{t('cloud.hubPrerequisite')}</p>
      {/if}
    </Card>{/if}
    {#if assets.errors.consume}<Alert tone="danger">{assets.errors.consume} {t('cloud.uncertain')}</Alert>{/if}
    {#if assets.consume}
      <Card surface="base" class="space-y-3">
        <h3 class="text-sm font-semibold">{t('cloud.operation', { id: assets.consume.consume_id })}</h3>
        <StatusChip status={assets.consume.status} />
        <p class="text-sm text-ink-2">{assets.consume.ready ? t('cloud.ready') : t('cloud.pending')}</p>
        <div class="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" disabled={!!assets.busy.status || !!assets.busy.cleanup} onclick={() => assets.refreshConsume()}>{t('refresh')}</Button>
          <Button variant="link" href={assets.consume.server_id ? `/dashboard/compute/instances/${encodeURIComponent(assets.consume.server_id)}` : '/dashboard/compute/instances'}>{t('cloud.instances')}</Button>
          {#if ['error', 'indeterminate'].includes(assets.consume.status)}<Button variant="danger-outline" size="sm" disabled={!$auth.canWrite || !!assets.busy.cleanup} onclick={cleanupOperation}>{t('cloud.cleanup')}</Button>{/if}
        </div>
        {#if assets.errors.status}<Alert tone="warning">{assets.errors.status}</Alert>{/if}
        {#if assets.errors.cleanup}<Alert tone="warning">{assets.errors.cleanup}</Alert>{/if}
      </Card>
    {/if}
  {/if}
</section>

{#snippet empty(hasMore = false)}<p class="rounded-md border border-line p-4 text-sm text-ink-2">{t(hasMore ? 'emptyPage' : 'empty')}</p>{/snippet}
{#snippet failure(source: AssetSource)}<Alert tone="danger"><p>{t('source.failed', { source: t(`source.${source}`) })}</p><p class="mt-2 break-words text-xs">{assets.errors[source]}</p><Button variant="secondary" size="sm" onclick={() => assets.load(source)}>{t('retry')}</Button></Alert>{/snippet}
{#snippet paging(source: AssetSource, offset: number, next: number | null, count: number)}<div class="flex flex-wrap items-center justify-between gap-3"><p class="text-xs text-ink-2">{t('page', { count })}</p><div class="flex gap-2"><Button variant="secondary" size="sm" disabled={offset === 0 || !!assets.busy[source]} onclick={() => previous(source, offset)}>{t('previous')}</Button><Button variant="secondary" size="sm" disabled={next === null || !!assets.busy[source]} onclick={() => assets.load(source, next!)}>{t('next')}</Button></div></div>{/snippet}

<FormModal bind:open={cloudOpen} title={t('cloud.create')} submitting={!!assets.busy.consume} onClose={() => cloudOpen = false}>
  <form onsubmit={(event) => { event.preventDefault(); void create(); }} class="space-y-4">
    <p class="text-sm text-ink-2">{t('cloud.project', { project: $auth.projectName ?? identity?.projectId ?? '' })}</p>
    <p class="break-words text-sm font-medium">{assets.selection?.asset.name}</p>
    {#if assets.busy.resources}<LoadingState variant={assets.resources ? 'inline' : 'section'} />{/if}
    {#if assets.errors.resources}<Alert tone="danger">{assets.errors.resources}</Alert><Button variant="secondary" size="sm" onclick={() => assets.loadResources()}>{t('retry')}</Button>{/if}
    <Field label={t('cloud.name')} for="asset-vm-name"><TextInput id="asset-vm-name" bind:value={serverName} maxlength={64} required disabled={!!assets.busy.consume} /></Field>
    <Field label={t('cloud.flavor')} for="asset-vm-flavor"><SearchSelect id="asset-vm-flavor" value={flavor} options={(assets.resources?.flavors ?? []).map((item) => ({ value: item.id, label: item.display_name ?? item.name, description: `${item.name} · ${item.id} · ${item.vcpus} vCPU · ${item.ram} MiB` }))} onchange={selectFlavor} disabled={!!assets.busy.consume || !writable} /></Field>
    {#if scheduleRequired}
      <section class="min-w-0 space-y-3" aria-label={usageText('title')}>
        <h3 class="text-sm font-semibold">{usageText('title')}</h3>
        <p class="text-sm text-ink-2">{usageText('required')}</p>
        <UsageScheduleFields value={usageSchedule} onchange={(value) => usageSchedule = value} disabled={!!assets.busy.consume || !writable} idPrefix="asset-usage" />
      </section>
    {/if}
    <Field label={t('cloud.network')} for="asset-vm-network"><SearchSelect id="asset-vm-network" value={network} options={(assets.resources?.networks ?? []).filter((item) => !item.external).map((item) => ({ value: item.id, label: item.name }))} onchange={(value) => network = value} disabled={!!assets.busy.consume || !writable} /></Field>
    <Field label={t('cloud.key')} for="asset-vm-key"><SearchSelect id="asset-vm-key" value={key} options={(assets.resources?.keys ?? []).map((item) => ({ value: item.name, label: item.name }))} onchange={(value) => key = value} disabled={!!assets.busy.consume || !writable} /></Field>
    <p class="text-xs text-ink-2">{t('cloud.consent')}</p>
  </form>
  {#snippet actions()}<Button variant="secondary" disabled={!!assets.busy.consume} onclick={() => cloudOpen = false}>{t('close')}</Button><Button variant="primary" disabled={!writable || assets.consumeLocked || !selectedFlavor || !scheduleReady || !network || !key || !serverName.trim() || !!assets.busy.consume || !!assets.busy.resources || !!assets.errors.resources} onclick={create}>{t('cloud.create')}</Button>{/snippet}
</FormModal>
