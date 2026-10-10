<script lang="ts">
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { LoadBalancer } from '$lib/types/loadbalancer';
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
  import { t } from '$lib/i18n/ns/network-pages';


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
    if (!await confirmDialog(t('loadBalancers.bulk.confirmDelete', { count: ids.length }))) return;
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    busy = true;
    try {
      const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/loadbalancers/${id}`, tokenSnapshot, projectSnapshot));
      const succeeded = results.filter((result) => result.ok).map((result) => result.id);
      if (projectSnapshot === ($auth.projectId ?? undefined)) selection.remove(succeeded);
      if (succeeded.length > 0) toast.success(t('loadBalancers.toast.deleteRequested', { count: succeeded.length }));
      const failedCount = results.length - succeeded.length;
      if (failedCount > 0) toast.error(t('loadBalancers.toast.deleteFailed', { count: failedCount }));
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
      error = e instanceof ApiError ? t('loadBalancers.error.fetchFailed', { status: e.status }) : t('loadBalancers.error.server');
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
  <PageHeader breadcrumb={t('loadBalancers.breadcrumb')} title={t('loadBalancers.title')}>
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={loading}
        onManualRefresh={() => fetchLoadbalancers({ refresh: true })}
      />
      <a href="/dashboard/network/loadbalancers/new" class="bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">{t('loadBalancers.actions.create')}</a>
    {/snippet}
  </PageHeader>

  {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  {#if loading}
    <div class="flex flex-col gap-3.5" role="status" aria-busy="true">
      <span class="sr-only">{t('loadBalancers.loading')}</span>
      {#each [1, 2, 3] as _}
        <div class="bg-surface-base border border-line rounded-lg p-5" aria-hidden="true">
          <div class="flex items-center gap-4">
            <div class="motion-skeleton w-10 h-10 rounded-lg"></div>
            <div class="flex-1">
              <div class="motion-skeleton h-4 w-32 rounded mb-2"></div>
              <div class="motion-skeleton h-3 w-48 rounded"></div>
            </div>
            <div class="motion-skeleton h-6 w-16 rounded-full"></div>
          </div>
        </div>
      {/each}
    </div>
  {:else if loadbalancers.length === 0}
    <div class="text-center py-20 text-ink-2">
      <div class="text-5xl mb-4">⚖️</div>
      <p class="text-lg">{t('loadBalancers.empty.title')}</p>
      <a href="/dashboard/network/loadbalancers/new" class="text-warm-text hover:text-warm-text-hover text-sm mt-2 inline-block">{t('loadBalancers.empty.create')}</a>
    </div>
  {:else}
    <div class="motion-stagger flex flex-col gap-3.5">
    <div class="flex justify-end mb-3">
      <SelectionToolbar
        label={t('loadBalancers.title')}
        ariaLabel={t('loadBalancers.selection.selectAll')}
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
              title={isProtected ? t('loadBalancers.selection.protected') : undefined}
              ariaLabel={t('loadBalancers.selection.select', { name: lb.name || lb.id.slice(0, 12) })}
              onclick={() => selection.toggle(lb.id)}
            />
            <!-- Blue icon chip -->
            <div class="shrink-0 w-10 h-10 rounded-lg bg-action-warm/15 border border-action-warm/30 flex items-center justify-center">
              <svg class="w-5 h-5 text-warm-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="9" stroke-width="2"/>
                <path stroke-linecap="round" stroke-width="2" d="M8 12h8M12 8v8"/>
              </svg>
            </div>
            <!-- Name + subtitle -->
            <div class="flex-1 min-w-0">
              <div class="text-ink-0 text-[15px] font-semibold truncate">{lb.name || lb.id.slice(0, 12)}</div>
              <div class="text-xs text-ink-2 mt-0.5 font-mono">
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
            >{t('loadBalancers.actions.detail')}</button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
<BulkSelectionOverlay
  count={selectedCount}
  ariaLabel={t('loadBalancers.bulk.ariaLabel')}
  actions={[{ key: 'delete', label: t('loadBalancers.actions.delete'), tone: 'danger', onAction: bulkDelete }]}
  {busy}
  onClear={() => selection.clear()}
/>

{#if selectedLbId}
  <SlidePanel onClose={closeLbPanel} ariaLabel={t('loadBalancers.detail.ariaLabel')}>
    <LoadBalancerDetailPanel
      lbId={selectedLbId}
      onClose={closeLbPanel}
      onDeleted={() => { fetchLoadbalancers(); closeLbPanel(); }}
    />
  </SlidePanel>
{/if}
