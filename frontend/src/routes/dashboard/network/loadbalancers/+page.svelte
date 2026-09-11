<script lang="ts">
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { LoadBalancer } from '$lib/types/loadbalancer';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import SlidePanel from '$lib/components/SlidePanel.svelte';
  import LoadBalancerDetailPanel from '$lib/components/LoadBalancerDetailPanel.svelte';
  import StatusChip from '$lib/components/ui/StatusChip.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
  import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations } from '$lib/utils/bulkActions';
  import { toast } from '$lib/stores/toast';
  import { isDroverLoadBalancer } from '$lib/utils/droverLoadBalancer';


  let selectedLbId = $state<string | null>(null);

  function openLbPanel(id: string) {
    selectedLbId = id;
    history.pushState({ lbId: id }, '', `/dashboard/network/loadbalancers/${id}`);
  }
  function closeLbPanel() {
    selectedLbId = null;
    history.pushState({}, '', '/dashboard/network/loadbalancers');
  }

  let loadbalancers = $state<LoadBalancer[]>([]);
  let loading = $state(true);
  let error = $state('');
  let selection = createResourceSelection();
  let busy = $state(false);
  let selectableIds = $derived(new Set(loadbalancers.filter((lb) => !isDroverLoadBalancer(lb)).map((lb) => lb.id)));
  const selectedCount = $derived([...selectableIds].filter((id) => selection.ids.has(id)).length);
  const allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
  const indeterminate = $derived(selectedCount > 0 && !allSelected);

  async function bulkDelete() {
    const ids = [...selection.ids].filter((id) => selectableIds.has(id));
    if (ids.length === 0) return;
    const warning = '리스너·풀·멤버가 함께 삭제될 수 있습니다.';
    if (!await confirmDialog(`${ids.length}개 로드밸런서를 삭제하시겠습니까?\n${warning}`)) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    busy = true;
    try {
      const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/loadbalancers/${id}`, tokenSnapshot, projectSnapshot));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      if (projectSnapshot === ($auth.projectId ?? undefined)) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(`${succeeded.length}개 로드밸런서 삭제 요청을 완료했습니다.`);
      const failedCount = results.length - succeeded.length;
      if (failedCount > 0) toast.error(`${failedCount}개 로드밸런서 삭제에 실패했습니다.`);
      if (projectSnapshot === ($auth.projectId ?? undefined)) await fetchLoadbalancers({ refresh: true });
    } finally {
      busy = false;
    }
  }

  async function fetchLoadbalancers(opts?: { refresh?: boolean }) {
    try {
      loadbalancers = await api.get<LoadBalancer[]>('/api/v1/loadbalancers', $auth.token ?? undefined, $auth.projectId ?? undefined, opts);
      if (selection.count > 0) {
        selection.retain(loadbalancers.filter((lb) => !isDroverLoadBalancer(lb)).map((lb) => lb.id));
      }
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
    } finally {
      loading = false;
    }
  }

  const ar = createAutoRefresh(() => fetchLoadbalancers(), {
    storageKey: 'dashboard-network-lb',
    defaultActive: true,
    defaultInterval: 30,
    intervalOptions: [10, 15, 30, 60],
    invokeOnMount: false,
  });

  $effect(() => {
    const pid = $auth.projectId;
    if (!pid) return;
    untrack(() => {
      selection.clear();
      void fetchLoadbalancers();
    });
  });
</script>

<div class="bulk-selection-page p-4 md:p-8">
  <PageHeader breadcrumb="NETWORK / LOADBALANCERS" title="로드밸런서">
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={loading}
        onManualRefresh={() => fetchLoadbalancers({ refresh: true })}
      />
      <a href="/dashboard/network/loadbalancers/new" class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">+ 로드밸런서 생성</a>
    {/snippet}
  </PageHeader>

  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  {#if loading}
    <div class="flex flex-col gap-3.5">
      {#each [1, 2, 3] as _}
        <div class="bg-surface-base border border-line rounded-lg p-5 animate-pulse">
          <div class="flex items-center gap-4">
            <div class="w-10 h-10 rounded-xl bg-surface-sunken"></div>
            <div class="flex-1">
              <div class="h-4 w-32 bg-surface-sunken rounded mb-2"></div>
              <div class="h-3 w-48 bg-surface-sunken rounded"></div>
            </div>
            <div class="h-6 w-16 bg-surface-sunken rounded-full"></div>
          </div>
        </div>
      {/each}
    </div>
  {:else if loadbalancers.length === 0}
    <div class="text-center py-20 text-ink-3">
      <div class="text-5xl mb-4">⚖️</div>
      <p class="text-lg">로드밸런서가 없습니다</p>
      <a href="/dashboard/network/loadbalancers/new" class="text-action-warm hover:text-action-warm-hover text-sm mt-2 inline-block">첫 로드밸런서를 생성하세요 →</a>
    </div>
  {:else}
    <div class="flex flex-col gap-3.5">
    <div class="flex justify-end mb-3">
      <SelectionToolbar
        label="로드밸런서"
        ariaLabel="로드밸런서 전체 선택"
        checked={allSelected}
        indeterminate={indeterminate}
        selectedCount={selectedCount}
        disabled={busy || selectableIds.size === 0}
        onToggle={() => selection.toggleAll(selectableIds)}
      />
    </div>
      {#each loadbalancers as lb (lb.id)}
        {@const isProtected = isDroverLoadBalancer(lb)}
        <div class="resource-selection-surface bg-surface-base border border-line rounded-lg p-5" data-selected={selection.has(lb.id)}>
          <div class="flex items-center gap-4">
            <SelectionCheckbox
              checked={selection.has(lb.id)}
              disabled={busy || isProtected}
              unavailable={isProtected}
              title={isProtected ? 'Drover가 관리하는 로드밸런서입니다. (일괄 삭제 불가)' : undefined}
              ariaLabel={`${lb.name || lb.id.slice(0, 12)} 선택`}
              onclick={() => selection.toggle(lb.id)}
            />
            <!-- Blue icon chip -->
            <div class="shrink-0 w-10 h-10 rounded-xl bg-action-warm/15 border border-action-warm/30 flex items-center justify-center">
              <svg class="w-5 h-5 text-action-warm" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="9" stroke-width="2"/>
                <path stroke-linecap="round" stroke-width="2" d="M8 12h8M12 8v8"/>
              </svg>
            </div>
            <!-- Name + subtitle -->
            <div class="flex-1 min-w-0">
              <div class="text-ink-0 text-[15px] font-semibold truncate">{lb.name || lb.id.slice(0, 12)}</div>
              <div class="text-[11px] text-ink-3 mt-0.5 font-mono">
                VIP {lb.vip_address ?? '—'}
                {#if lb.operating_status}
                  <span class="ml-2 {lb.operating_status === 'ONLINE' ? 'text-green-400' : 'text-ink-2'}">{lb.operating_status}</span>
                {/if}
              </div>
            </div>
            <!-- Status + action -->
            <StatusChip status={lb.status} />
            <button
              onclick={() => openLbPanel(lb.id)}
              class="px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink-0 border border-line-2 hover:border-line-2 rounded-lg transition-colors shrink-0"
            >상세</button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
<BulkSelectionOverlay
  count={selectedCount}
  ariaLabel="선택한 로드밸런서 일괄 작업"
  actions={[{ key: 'delete', label: '삭제', tone: 'danger', onAction: bulkDelete }]}
  {busy}
  onClear={() => selection.clear()}
/>

{#if selectedLbId}
  <SlidePanel onClose={closeLbPanel} ariaLabel="로드밸런서 상세">
    <LoadBalancerDetailPanel
      lbId={selectedLbId}
      onClose={closeLbPanel}
      onDeleted={() => { fetchLoadbalancers(); closeLbPanel(); }}
    />
  </SlidePanel>
{/if}
