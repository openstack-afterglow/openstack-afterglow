<script lang="ts">
  import { t } from '$lib/i18n/ns/network-pages';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import { createSwr } from '$lib/utils/swr.svelte';
  import { apiMut } from '$lib/api/mutations';
  import type { Network, FloatingIp } from '$lib/types/networks';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import SlidePanel from '$lib/components/SlidePanel.svelte';
  import NetworkDetailPanel from '$lib/components/NetworkDetailPanel.svelte';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import FloatingIpAllocateModal from '$lib/components/network/FloatingIpAllocateModal.svelte';
  import NetworkCreateModal from '$lib/components/dashboard/network/networks/NetworkCreateModal.svelte';
  import NetworksTableCard from '$lib/components/dashboard/network/networks/NetworksTableCard.svelte';
  import FloatingIpCard from '$lib/components/dashboard/network/networks/FloatingIpCard.svelte';
  import { toast } from '$lib/stores/toast';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations, partitionBulkIds } from '$lib/utils/bulkActions';
  import { Alert, Button, EmptyState, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';

  let networks = $state<Network[]>([]);
  let floatingIps = $state<FloatingIp[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let selectedNetworkId = $state<string | null>(null);
  let defaultNetworkId = $state<string | null>(null);
  let settingDefault = $state<string | null>(null);
  let showAllocateModal = $state(false);
  let showModal = $state(false);
  let creating = $state(false);
  let createError = $state('');
  let activeDomain = $state<'networks' | 'floating-ips' | null>(null);
  let selection = createResourceSelection();
  let busy = $state(false);
  let selectableNetworkIds = $derived(new Set(networks.filter((network) => network.project_id === $auth.projectId && !network.is_external).map((network) => network.id)));
  let selectableFloatingIpIds = $derived(new Set(floatingIps.map((fip) => fip.id)));

  function toggleSelect(domain: 'networks' | 'floating-ips', id: string) {
    if (activeDomain !== domain) {
      selection.clear();
      activeDomain = domain;
    }
    selection.toggle(id);
  }
  function toggleAll(domain: 'networks' | 'floating-ips') {
    if (activeDomain !== domain) {
      selection.clear();
      activeDomain = domain;
    }
    selection.toggleAll(domain === 'networks' ? selectableNetworkIds : selectableFloatingIpIds);
  }


  $effect(() => { if (!showModal) createError = ''; });

  const tok = () => $auth.token ?? undefined;
  const pid = () => $auth.projectId ?? undefined;
  const { swrGet, swrSet } = createSwr(() => $auth.projectId);

  async function fetchNetworks(opts?: { refresh?: boolean }) {
    const path = '/api/v1/networks';
    const cached = swrGet<Network[]>(path);
    if (cached && networks.length === 0) networks = cached;
    try {
      networks = await api.get<Network[]>(path, tok(), pid(), opts);
      swrSet(path, networks);
      if (activeDomain === 'networks') selection.retain(networks.map((network) => network.id));
      error = '';
    } catch (e) {
      if (!cached) error = e instanceof ApiError ? t('networks.loadFailed', { status: e.status }) : t('networks.serverError');
    } finally { loading = false; }
  }

  async function fetchDefaultNetwork() {
    try {
      const record = await api.get<{ network_id: string }>('/api/v1/networks/default', tok(), pid());
      defaultNetworkId = record.network_id;
    } catch { defaultNetworkId = null; }
  }

  async function setAsDefault(networkId: string) {
    if (!selectableNetworkIds.has(networkId)) {
      toast.warning(t('networks.onlyOwnedDefault'));
      return;
    }
    settingDefault = networkId;
    try {
      await api.put('/api/v1/networks/default', { network_id: networkId }, tok(), pid());
      defaultNetworkId = networkId;
    } catch (e) {
      toast.error(t('networks.setDefaultFailed', { error: e instanceof ApiError ? e.message : String(e) }));
    } finally { settingDefault = null; }
  }

  async function fetchFloatingIps(opts?: { refresh?: boolean }) {
    try {
      floatingIps = await api.get<FloatingIp[]>('/api/v1/networks/floating-ips', tok(), pid(), opts);
      if (activeDomain === 'floating-ips') selection.retain(floatingIps.map((fip) => fip.id));
    } catch { /* 오류 무시 */ }
  }
  async function runBulkAction(domain: 'networks' | 'floating-ips', eligible: ReadonlySet<string>, mutate: (id: string, token: string | undefined, projectId: string | undefined) => Promise<unknown>) {
    const snapshotIds = [...selection.ids];
    const { eligible: eligibleIds, skipped } = partitionBulkIds(snapshotIds, eligible);
    if (eligibleIds.length === 0) return;
    if (!await confirmDialog(t(domain === 'networks' ? 'networks.bulk.deleteConfirm' : 'networks.bulk.releaseConfirm', { count: eligibleIds.length, skipped: skipped.length }))) return;
    const tokenSnapshot = tok();
    const projectSnapshot = pid();
    busy = true;
    try {
      const results = await executeBulkMutations(eligibleIds, (id) => mutate(id, tokenSnapshot, projectSnapshot));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      const failedCount = results.length - succeeded.length;
      const sameProjectDomain = projectSnapshot === pid() && activeDomain === domain;
      if (sameProjectDomain) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(t(domain === 'networks' ? 'networks.bulk.deleteDone' : 'networks.bulk.releaseDone', { count: succeeded.length }));
      if (failedCount > 0) toast.error(t(domain === 'networks' ? 'networks.bulk.deleteFailed' : 'networks.bulk.releaseFailed', { count: failedCount }));
      if (skipped.length > 0) toast.warning(t(domain === 'networks' ? 'networks.bulk.deleteSkipped' : 'networks.bulk.releaseSkipped', { count: skipped.length }));
      if (sameProjectDomain) {
        if (domain === 'networks') await fetchNetworks({ refresh: true });
        else await fetchFloatingIps();
      }
    } finally {
      busy = false;
    }
  }
  function bulkActions(): BulkSelectionAction[] {
    if (activeDomain === 'networks') {
      return [{
        key: 'delete-network',
        label: t('networks.delete'),
        tone: 'danger',
        disabled: partitionBulkIds(selection.ids, selectableNetworkIds).eligible.length === 0,
        onAction: () => runBulkAction('networks', selectableNetworkIds, (id, token, projectId) => api.delete(`/api/v1/networks/${id}`, token, projectId)),
      }];
    }
    if (activeDomain === 'floating-ips') {
      return [{
        key: 'release-floating-ip',
        label: t('networks.release'),
        tone: 'warning',
        disabled: partitionBulkIds(selection.ids, selectableFloatingIpIds).eligible.length === 0,
        onAction: () => runBulkAction('floating-ips', selectableFloatingIpIds, (id, token, projectId) => api.delete(`/api/v1/networks/floating-ips/${id}`, token, projectId)),
      }];
    }
    return [];
  }

  async function forceRefresh() {
    refreshing = true;
    try { await Promise.all([fetchNetworks({ refresh: true }), fetchFloatingIps({ refresh: true })]); }
    finally { refreshing = false; }
  }

  async function createNetwork(body: Record<string, unknown>): Promise<boolean> {
    creating = true; createError = '';
    try {
      await apiMut(t('networks.create'), () => api.post('/api/v1/networks', body, tok(), pid()));
      await fetchNetworks();
      return true;
    } catch (e) {
      createError = e instanceof ApiError ? e.message : t('networks.createFailed');
      return false;
    } finally { creating = false; }
  }

  async function deleteNetwork(id: string, name: string, isExternal: boolean) {
    if (!selectableNetworkIds.has(id)) { toast.warning(t('networks.onlyOwnedDelete')); return; }
    if (isExternal) { toast.warning(t('networks.externalDelete')); return; }
    if (!await confirmDialog(t('networks.deleteConfirm', { name: name || id.slice(0, 8) }))) return;
    deleting = id;
    try {
      await apiMut(t('networks.deleteAction'), () => api.delete(`/api/v1/networks/${id}`, tok(), pid()));
      await fetchNetworks();
    } catch { /* error toast shown by apiMut */ }
    finally { deleting = null; }
  }

  function openNetworkPanel(id: string) {
    selectedNetworkId = id;
    history.pushState({ networkId: id }, '', `/dashboard/network/networks/${id}`);
  }
  function closeNetworkPanel() {
    selectedNetworkId = null;
    history.pushState({}, '', '/dashboard/network/networks');
  }

  const ar = createAutoRefresh(() => { fetchNetworks(); fetchFloatingIps(); }, {
    storageKey: 'dashboard-network-networks',
    defaultActive: true, defaultInterval: 30, intervalOptions: [10, 15, 30, 60], invokeOnMount: false,
  });

  $effect(() => {
    const projectId = $auth.projectId;
    untrack(() => {
      selection.clear();
      activeDomain = null;
      if (!projectId) return;
      loading = true;
      void fetchNetworks();
      void fetchFloatingIps();
      void fetchDefaultNetwork();
    });
  });
</script>

<NetworkCreateModal bind:open={showModal} {creating} error={createError} onCreate={createNetwork} />

<PageShell class="bulk-selection-page space-y-4">
  <PageHeader breadcrumb={t('networks.breadcrumb')} title={t('networks.title')}>
    {#snippet actions()}
      <Button onclick={() => showModal = true} variant="primary">{t('networks.createButton')}</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label={t('networks.toolbar')}>
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        {refreshing}
        onManualRefresh={forceRefresh}
      />
    {/snippet}
  </ResourceToolbar>

  {#if error}<Alert tone="danger">{error}</Alert>{/if}

  {#if loading}
    <LoadingSkeleton variant="table" rows={5} />
  {:else if networks.length === 0 && floatingIps.length === 0}
    <EmptyState headline={t('networks.empty')} description={t('networks.emptyDescription')} />
  {:else}
    <div class="flex flex-col gap-4">
      <NetworksTableCard
        {networks} {defaultNetworkId} {deleting} {settingDefault}
        selectedIds={selection.ids}
        selectableIds={selectableNetworkIds}
        selectionDisabled={busy}
        onToggleSelect={(id) => toggleSelect('networks', id)}
        onToggleAll={() => toggleAll('networks')}
        onOpenPanel={openNetworkPanel} onSetDefault={setAsDefault} onDelete={deleteNetwork}
      />
      <FloatingIpCard
        {floatingIps}
        hasExternalNetwork={networks.some((n) => n.is_external)}
        selectedIds={selection.ids}
        selectableIds={selectableFloatingIpIds}
        selectionDisabled={busy}
        onToggleSelect={(id) => toggleSelect('floating-ips', id)}
        onToggleAll={() => toggleAll('floating-ips')}
        onAllocateClick={() => (showAllocateModal = true)}
      />
    </div>
  {/if}
</PageShell>

<BulkSelectionOverlay
  count={selection.count}
  ariaLabel={t('networks.bulkAria')}
  actions={bulkActions()}
  {busy}
  onClear={() => { selection.clear(); activeDomain = null; }}
/>

<FloatingIpAllocateModal
  bind:open={showAllocateModal} {networks}
  token={tok()} projectId={pid()} onAllocated={fetchFloatingIps}
/>

{#if selectedNetworkId}
  <SlidePanel onClose={closeNetworkPanel} ariaLabel={t('networks.detail')} width="w-full md:w-[60vw] max-w-2xl">
    <NetworkDetailPanel
      networkId={selectedNetworkId} apiBase="/api/v1/networks"
      onClose={closeNetworkPanel} token={tok()} projectId={pid()}
    />
  </SlidePanel>
{/if}
