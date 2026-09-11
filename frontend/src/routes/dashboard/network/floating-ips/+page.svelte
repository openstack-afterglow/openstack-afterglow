<script lang="ts">
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { FloatingIp } from '$lib/types/networks';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
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

  let fips = $state<FloatingIp[]>([]);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);

  let selection = createResourceSelection();
  let busy = $state(false);
  let selectableIds = $derived(new Set(fips.map((fip) => fip.id)));
  const selectedCount = $derived([...selectableIds].filter((id) => selection.ids.has(id)).length);
  const allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
  const indeterminate = $derived(selectedCount > 0 && !allSelected);

  async function bulkRelease() {
    const snapshotIds = [...selection.ids];
    const { eligible, skipped } = partitionBulkIds(snapshotIds, selectableIds);
    if (eligible.length === 0) return;
    const suffix = skipped.length > 0 ? `\n${skipped.length}개는 현재 상태에서 제외됩니다.` : '';
    if (!await confirmDialog(`${eligible.length}개 Floating IP 해제를 진행하시겠습니까?${suffix}`)) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    busy = true;
    try {
      const results = await executeBulkMutations(eligible, (id) => api.delete(`/api/v1/networks/floating-ips/${id}`, tokenSnapshot, projectSnapshot));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      if (projectSnapshot === ($auth.projectId ?? undefined)) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(`${succeeded.length}개 Floating IP 해제 요청을 완료했습니다.`);
      const failedCount = results.length - succeeded.length;
      if (failedCount > 0) toast.error(`${failedCount}개 Floating IP 해제에 실패했습니다.`);
      if (skipped.length > 0) toast.warning(`${skipped.length}개는 현재 상태에서 Floating IP 해제할 수 없어 제외했습니다.`);
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
      error = e instanceof ApiError ? e.message : '목록을 불러올 수 없습니다';
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
    if (!await confirmDialog(`Floating IP "${addr}"를 해제하시겠습니까?`)) return;
    deleting = id;
    try {
      await api.delete(`/api/v1/networks/floating-ips/${id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await load();
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof ApiError ? e.message : String(e)));
    } finally {
      deleting = null;
    }
  }

  const ar = createAutoRefresh(() => load(), {
    storageKey: 'network-floating-ips',
    defaultActive: false,
    defaultInterval: 30,
    intervalOptions: [10, 15, 30, 60],
    invokeOnMount: false,
  });

  $effect(() => {
    const pid = $auth.projectId;
    if (!pid) return;
    untrack(() => {
      selection.clear();
      void load();
    });
  });
</script>

<div class="bulk-selection-page p-4 md:p-8 max-w-7xl mx-auto">
  <PageHeader breadcrumb="네트워크" title="Floating IP">
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing}
        onManualRefresh={forceRefresh}
      />
    {/snippet}
  </PageHeader>

  <div class="mb-4 text-sm text-ink-3">
    Floating IP 할당은
    <a href="/dashboard/network/networks" class="text-action-warm hover:text-action-warm-hover underline">네트워크 페이지</a>에서 수행할 수 있습니다.
  </div>

  {#if error}
    <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>
  {/if}

  {#if loading}
    <LoadingSkeleton rows={4} />
  {:else}
    <div class="bg-surface-base border border-line rounded-lg overflow-hidden">
      <div class="grid grid-cols-[1fr_160px_1fr_140px_90px] px-5 py-3 border-b border-line text-[11px] uppercase tracking-wider text-ink-3 font-medium">
        <div>
          <SelectionToolbar
            label="Floating IP"
            ariaLabel="Floating IP 전체 선택"
            checked={allSelected}
            indeterminate={indeterminate}
            selectedCount={selectedCount}
            disabled={busy || selectableIds.size === 0}
            onToggle={() => selection.toggleAll(selectableIds)}
          />
        </div>
        <div>연결된 Fixed IP</div>
        <div>인스턴스</div>
        <div>상태</div>
        <div></div>
      </div>

      {#each fips as fip (fip.id)}
        <div class="resource-selection-surface grid grid-cols-[1fr_160px_1fr_140px_90px] px-5 py-3.5 border-b border-line last:border-b-0 items-center hover:bg-surface-sunken/20 transition-colors" data-selected={selection.has(fip.id)}>
          <div class="flex items-center gap-2">
            <SelectionCheckbox
              checked={selection.has(fip.id)}
              disabled={busy}
              ariaLabel={`${fip.floating_ip_address} 선택`}
              onclick={() => selection.toggle(fip.id)}
            />
            <div class="font-mono text-[13px] text-ink-0">{fip.floating_ip_address}</div>
          </div>
          <div class="text-[12px] text-ink-2 font-mono truncate">
            {fip.fixed_ip_address ?? '—'}
          </div>
          <div class="text-[12px] truncate">
            {#if fip.instance_name}
              <span class="text-action-warm">{fip.instance_name}</span>
            {:else if fip.instance_id}
              <span class="text-ink-2 font-mono">{fip.instance_id.slice(0, 8)}…</span>
            {:else}
              <span class="text-ink-3">—</span>
            {/if}
          </div>
          <div><StatusChip status={fip.status} /></div>
          <div class="flex justify-end">
            <button
              onclick={() => deleteFip(fip.id, fip.floating_ip_address)}
              disabled={deleting === fip.id}
              class="text-[11px] text-red-400 hover:text-red-300 transition-colors disabled:opacity-40"
            >
              {deleting === fip.id ? '처리 중...' : '해제'}
            </button>
          </div>
        </div>
      {/each}

      {#if fips.length === 0}
        <div class="text-ink-3 text-sm text-center py-12">할당된 Floating IP가 없습니다</div>
      {/if}
    </div>
  {/if}
</div>
<BulkSelectionOverlay
  count={selection.count}
  ariaLabel="선택한 Floating IP 일괄 작업"
  actions={[{ key: 'release', label: '해제', tone: 'warning', disabled: partitionBulkIds(selection.ids, selectableIds).eligible.length === 0, onAction: bulkRelease }]}
  {busy}
  onClear={() => selection.clear()}
/>
