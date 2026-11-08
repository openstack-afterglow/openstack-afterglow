<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { sessionScopeKey } from '$lib/utils/authSession';
  import { api, ApiError } from '$lib/api/client';
  import type { FloatingIp, Network } from '$lib/types/networks';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations, partitionBulkIds } from '$lib/utils/bulkActions';
  import { toast } from '$lib/stores/toast';
  import { t } from '$lib/i18n/ns/network-pages';
  import RichText from '$lib/i18n/RichText.svelte';
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import FloatingIpAllocateModal from '$lib/components/network/FloatingIpAllocateModal.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';

  let fips = $state<FloatingIp[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let networks = $state<Network[]>([]);
  let showAllocateModal = $state(false);
  let lastCreated = $state<string | null>(null);

  let selection = createResourceSelection();
  let busy = $state(false);
  let search = $state('');
  const columns = (): TableColumn<FloatingIp>[] => [
    { key: 'address', label: t('floatingIps.title'), value: row => row.floating_ip_address },
    { key: 'fixed', label: t('floatingIps.columns.fixedIp'), value: row => row.fixed_ip_address },
    { key: 'instance', label: t('floatingIps.columns.instance'), value: row => row.instance_name || row.instance_id },
    { key: 'status', label: t('floatingIps.columns.status'), value: row => row.status },
  ];
  const view = createTableView({ rows: () => fips, columns, search: () => search, searchable: row => [row.id, row.floating_ip_address, row.fixed_ip_address ?? '', row.instance_name ?? '', row.instance_id ?? '', row.status] });
  const visibleSelectableIds = $derived(new Set(view.rows.map(row => row.id)));
  $effect(() => { const ids = visibleSelectableIds; untrack(() => selection.retain(ids)); });
  let selectableIds = $derived(new Set(fips.map((fip) => fip.id)));
  const selectedCount = $derived([...visibleSelectableIds].filter((id) => selection.ids.has(id)).length);
  const allSelected = $derived(visibleSelectableIds.size > 0 && selectedCount === visibleSelectableIds.size);
  const indeterminate = $derived(selectedCount > 0 && !allSelected);

  async function bulkRelease() {
    const snapshotIds = [...selection.ids];
    const { eligible, skipped } = partitionBulkIds(snapshotIds, selectableIds);
    if (eligible.length === 0) return;
    if (!await confirmDialog(skipped.length > 0
      ? t('floatingIps.bulk.confirmSkipped', { count: eligible.length, skipped: skipped.length })
      : t('floatingIps.bulk.confirm', { count: eligible.length }))) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    busy = true;
    try {
      const results = await executeBulkMutations(eligible, (id) => api.delete(`/api/v1/networks/floating-ips/${id}`, tokenSnapshot, projectSnapshot));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      if (projectSnapshot === ($auth.projectId ?? undefined)) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(t('floatingIps.toast.releaseRequested', { count: succeeded.length }));
      const failedCount = results.length - succeeded.length;
      if (failedCount > 0) toast.error(t('floatingIps.toast.releaseFailed', { count: failedCount }));
      if (skipped.length > 0) toast.warning(t('floatingIps.toast.releaseSkipped', { count: skipped.length }));
      if (projectSnapshot === ($auth.projectId ?? undefined)) await load({ refresh: true });
    } finally {
      busy = false;
    }
  }
  async function load(opts?: { refresh?: boolean }) {
    error = '';
    try {
      fips = await api.get<FloatingIp[]>(
        '/api/v1/networks/floating-ips',
        $auth.token ?? undefined,
        $auth.projectId ?? undefined,
        opts,
      );
      if (selection.count > 0) selection.retain(fips.map((fip) => fip.id));
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('floatingIps.error.loadFailed');
    } finally {
      loading = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try {
      await load({ refresh: true });
    } finally {
      refreshing = false;
    }
  }

  async function deleteFip(id: string, addr: string) {
    if (!await confirmDialog(t('floatingIps.release.confirm', { address: addr }))) return;
    deleting = id;
    try {
      await api.delete(`/api/v1/networks/floating-ips/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await load();
    } catch (e) {
      toast.error(t('floatingIps.error.deleteFailed', { message: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      deleting = null;
    }
  }

  async function openAllocate() {
    showAllocateModal = true;
    try {
      networks = await api.get<Network[]>('/api/v1/networks', $auth.token ?? undefined, $auth.projectId ?? undefined);
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('floatingIps.error.loadFailed');
    }
  }

  async function onAllocated(created: FloatingIp) {
    lastCreated = created.id;
    await load();
  }

  const ar = createAutoRefresh(() => load(), {
    storageKey: 'network-floating-ips',
    defaultActive: false,
    defaultInterval: 30,
    intervalOptions: [10, 15, 30, 60],
    invokeOnMount: false,
  });

  const viewOwner = $derived(sessionScopeKey($auth));
  $effect(() => {
    viewOwner;
    const pid = untrack(() => $auth.projectId);
    if (!pid) return;
    untrack(() => {
      selection.clear();
      search = ''; view.reset();
      void load();
    });
  });
</script>

<PageShell class="bulk-selection-page">
  <PageHeader breadcrumb={t('floatingIps.breadcrumb')} title={t('floatingIps.title')}>
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing}
        onManualRefresh={forceRefresh}
      />
      <TutorialStartButton tour="floating-ips" compactOnMobile />
      <Button variant="primary" onclick={openAllocate} dataTour="floating-ips-allocate-open">{t('floatingIpCard.allocate')}</Button>
    {/snippet}
  </PageHeader>

  <div class="mb-4 text-sm text-ink-2">
    {#snippet networkLink(text: string)}
      <a href="/dashboard/network/networks" class="text-warm-text hover:text-warm-text-hover underline">{text}</a>
    {/snippet}
    <RichText segments={t.rich('floatingIps.allocationHelp')} tags={{ network: networkLink }} />
  </div>
  <RegexSearch id="floating-ip-search" bind:value={search} />
  <TableViewControls {view} />
  {#if fips.length > 0 && view.rows.length === 0}<p class="text-sm text-ink-2">{tl('table.noMatches')}</p>{/if}

  {#if error}
    <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>
  {/if}

  {#if loading}
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('floatingIps.title') })} />
  {:else}
    <div data-tour="floating-ips-list">
    <ResponsiveTable>
      {#snippet cards()}
        <div class="responsive-card-toolbar"><SelectionToolbar label={t('floatingIps.title')} ariaLabel={t('floatingIps.selection.selectAll')} checked={allSelected} {indeterminate} {selectedCount} disabled={busy || visibleSelectableIds.size === 0} onToggle={() => selection.toggleAll(visibleSelectableIds)} /></div>
        {#each view.rows as fip (fip.id)}
          <CompactResourceCard selected={selection.has(fip.id)}>
            <div class="flex items-center gap-2"><SelectionCheckbox checked={selection.has(fip.id)} disabled={busy} ariaLabel={t('floatingIps.selection.select', { address: fip.floating_ip_address })} onclick={() => selection.toggle(fip.id)} /><span class="font-mono font-medium">{fip.floating_ip_address}</span><StatusChip status={fip.status} /></div>
            <dl><div><dt>{t('floatingIps.columns.fixedIp')}</dt><dd>{fip.fixed_ip_address ?? '—'}</dd></div><div><dt>{t('floatingIps.columns.instance')}</dt><dd>{fip.instance_name || (fip.instance_id ? fip.instance_id.slice(0, 8) + '…' : '—')}</dd></div></dl>
            {#snippet details()}<p class="font-mono">{fip.id}</p>{#if fip.instance_id}<p class="font-mono">{fip.instance_id}</p>{/if}{/snippet}
            {#snippet actions()}<button data-tour={fip.id === lastCreated ? 'floating-ips-release' : undefined} onclick={() => deleteFip(fip.id, fip.floating_ip_address)} disabled={deleting === fip.id} aria-busy={deleting === fip.id} class="inline-flex items-center gap-1.5 text-state-danger-text">{#if deleting === fip.id}<LoadingState variant="control"  label="" aria-hidden="true" />{/if}{deleting === fip.id ? t('floatingIps.actions.processing') : t('floatingIps.actions.release')}</button>{/snippet}
          </CompactResourceCard>
        {:else}<p class="responsive-card-toolbar text-center text-ink-2 py-8">{t('floatingIps.empty')}</p>{/each}
      {/snippet}
    <div class="bg-surface-base border border-line rounded-lg overflow-hidden">
      <div class="grid grid-cols-[1fr_160px_1fr_140px_90px] px-5 py-3 border-b border-line text-xs uppercase tracking-wider text-ink-2 font-medium">
        <div>
          <SelectionToolbar
            label={t('floatingIps.title')}
            ariaLabel={t('floatingIps.selection.selectAll')}
            checked={allSelected}
            indeterminate={indeterminate}
            selectedCount={selectedCount}
            disabled={busy || visibleSelectableIds.size === 0}
            onToggle={() => selection.toggleAll(visibleSelectableIds)}
          />
          <TableColumnControl {view} columnKey="address" />
        </div>
        <TableColumnControl {view} columnKey="fixed" />
        <TableColumnControl {view} columnKey="instance" />
        <TableColumnControl {view} columnKey="status" />
        <div></div>
      </div>

      <div class="motion-stagger">
      {#each view.rows as fip (fip.id)}
        <div class="resource-selection-surface grid grid-cols-[1fr_160px_1fr_140px_90px] px-5 py-3.5 border-b border-line last:border-b-0 items-center hover:bg-surface-sunken/20 transition-colors" data-selected={selection.has(fip.id)}>
          <div class="flex items-center gap-2">
            <SelectionCheckbox
              checked={selection.has(fip.id)}
              disabled={busy}
              ariaLabel={t('floatingIps.selection.select', { address: fip.floating_ip_address })}
              onclick={() => selection.toggle(fip.id)}
            />
            <div class="font-mono text-[13px] text-ink-0">{fip.floating_ip_address}</div>
          </div>
          <div class="text-xs text-ink-2 font-mono truncate">
            {fip.fixed_ip_address ?? '—'}
          </div>
          <div class="text-xs truncate">
            {#if fip.instance_name}
              <span class="text-warm-text">{fip.instance_name}</span>
            {:else if fip.instance_id}
              <span class="text-ink-2 font-mono">{fip.instance_id.slice(0, 8)}…</span>
            {:else}
              <span class="text-ink-2">—</span>
            {/if}
          </div>
          <div><StatusChip status={fip.status} /></div>
          <div class="flex justify-end">
            <button
              data-tour={fip.id === lastCreated ? 'floating-ips-release' : undefined}
              onclick={() => deleteFip(fip.id, fip.floating_ip_address)}
              disabled={deleting === fip.id}
              aria-busy={deleting === fip.id}
              class="inline-flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-40"
            >
              {#if deleting === fip.id}<LoadingState variant="control"  label="" aria-hidden="true" />{/if}{deleting === fip.id ? t('floatingIps.actions.processing') : t('floatingIps.actions.release')}
            </button>
          </div>
        </div>
      {/each}
      </div>

      {#if fips.length === 0}
        <div class="text-ink-2 text-sm text-center py-12">{t('floatingIps.empty')}</div>
      {/if}
    </div>
    </ResponsiveTable>
    </div>
  {/if}
</PageShell>
<FloatingIpAllocateModal
  bind:open={showAllocateModal} {networks}
  token={$auth.token ?? undefined} projectId={$auth.projectId ?? undefined} {onAllocated}
/>
<BulkSelectionOverlay
  count={selection.count}
  ariaLabel={t('floatingIps.bulk.ariaLabel')}
  actions={[{ key: 'release', label: t('floatingIps.actions.release'), tone: 'warning', disabled: partitionBulkIds(selection.ids, selectableIds).eligible.length === 0, onAction: bulkRelease }]}
  {busy}
  onClear={() => selection.clear()}
/>
