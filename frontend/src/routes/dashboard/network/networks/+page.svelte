<script lang="ts">
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
  let selectableNetworkIds = $derived(new Set(networks.filter((network) => !network.is_external).map((network) => network.id)));
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
      if (!cached) error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
    } finally { loading = false; }
  }

  async function fetchDefaultNetwork() {
    try {
      const record = await api.get<{ network_id: string }>('/api/v1/networks/default', tok(), pid());
      defaultNetworkId = record.network_id;
    } catch { defaultNetworkId = null; }
  }

  async function setAsDefault(networkId: string) {
    settingDefault = networkId;
    try {
      await api.put('/api/v1/networks/default', { network_id: networkId }, tok(), pid());
      defaultNetworkId = networkId;
    } catch (e) {
      toast.error('기본 네트워크 설정 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally { settingDefault = null; }
  }

  async function fetchFloatingIps(opts?: { refresh?: boolean }) {
    try {
      floatingIps = await api.get<FloatingIp[]>('/api/v1/networks/floating-ips', tok(), pid(), opts);
      if (activeDomain === 'floating-ips') selection.retain(floatingIps.map((fip) => fip.id));
    } catch { /* 오류 무시 */ }
  }
  async function runBulkAction(domain: 'networks' | 'floating-ips', actionLabel: string, eligible: ReadonlySet<string>, mutate: (id: string, token: string | undefined, projectId: string | undefined) => Promise<unknown>) {
    const snapshotIds = [...selection.ids];
    const { eligible: eligibleIds, skipped } = partitionBulkIds(snapshotIds, eligible);
    if (eligibleIds.length === 0) return;
    const suffix = skipped.length > 0 ? `\n${skipped.length}개는 현재 상태에서 제외됩니다.` : '';
    if (!await confirmDialog(`${eligibleIds.length}개 ${actionLabel} 요청을 진행하시겠습니까?${suffix}`)) return;
    const tokenSnapshot = tok();
    const projectSnapshot = pid();
    busy = true;
    try {
      const results = await executeBulkMutations(eligibleIds, (id) => mutate(id, tokenSnapshot, projectSnapshot));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      const failedCount = results.length - succeeded.length;
      const sameProjectDomain = projectSnapshot === pid() && activeDomain === domain;
      if (sameProjectDomain) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(`${succeeded.length}개 ${actionLabel} 요청을 완료했습니다.`);
      if (failedCount > 0) toast.error(`${failedCount}개 ${actionLabel}에 실패했습니다.`);
      if (skipped.length > 0) toast.warning(`${skipped.length}개는 현재 상태에서 ${actionLabel}할 수 없어 제외했습니다.`);
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
        label: '삭제',
        tone: 'danger',
        disabled: partitionBulkIds(selection.ids, selectableNetworkIds).eligible.length === 0,
        onAction: () => runBulkAction('networks', '네트워크 삭제', selectableNetworkIds, (id, token, projectId) => api.delete(`/api/v1/networks/${id}`, token, projectId)),
      }];
    }
    if (activeDomain === 'floating-ips') {
      return [{
        key: 'release-floating-ip',
        label: '해제',
        tone: 'warning',
        disabled: partitionBulkIds(selection.ids, selectableFloatingIpIds).eligible.length === 0,
        onAction: () => runBulkAction('floating-ips', 'Floating IP 해제', selectableFloatingIpIds, (id, token, projectId) => api.delete(`/api/v1/networks/floating-ips/${id}`, token, projectId)),
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
      await apiMut('네트워크 생성', () => api.post('/api/v1/networks', body, tok(), pid()));
      await fetchNetworks();
      return true;
    } catch (e) {
      createError = e instanceof ApiError ? e.message : '생성 실패';
      return false;
    } finally { creating = false; }
  }

  async function deleteNetwork(id: string, name: string, isExternal: boolean) {
    if (isExternal) { toast.warning('외부 네트워크는 삭제할 수 없습니다.'); return; }
    if (!await confirmDialog(`네트워크 "${name || id.slice(0, 8)}"를 삭제하시겠습니까?`)) return;
    deleting = id;
    try {
      await apiMut('네트워크 삭제', () => api.delete(`/api/v1/networks/${id}`, tok(), pid()));
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
  <PageHeader breadcrumb="NETWORK / NETWORKS" title="네트워크">
    {#snippet actions()}
      <Button onclick={() => showModal = true} variant="primary">+ 네트워크 생성</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label="네트워크 목록 도구">
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
    <EmptyState headline="네트워크가 없습니다" description="프로젝트의 첫 네트워크를 생성하세요." />
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
  ariaLabel="선택한 네트워크 리소스 일괄 작업"
  actions={bulkActions()}
  {busy}
  onClear={() => { selection.clear(); activeDomain = null; }}
/>

<FloatingIpAllocateModal
  bind:open={showAllocateModal} {networks}
  token={tok()} projectId={pid()} onAllocated={fetchFloatingIps}
/>

{#if selectedNetworkId}
  <SlidePanel onClose={closeNetworkPanel} ariaLabel="네트워크 상세" width="w-full md:w-[60vw] max-w-2xl">
    <NetworkDetailPanel
      networkId={selectedNetworkId} apiBase="/api/v1/networks"
      onClose={closeNetworkPanel} token={tok()} projectId={pid()}
    />
  </SlidePanel>
{/if}
