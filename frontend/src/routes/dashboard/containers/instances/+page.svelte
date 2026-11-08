<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import { t } from '$lib/i18n/ns/containers-shell';
  import { goto } from '$app/navigation';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
  import BulkSelectionOverlay, { type BulkSelectionAction } from '$lib/components/ui/BulkSelectionOverlay.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
  import { executeBulkMutations, partitionBulkIds } from '$lib/utils/bulkActions';
  import { buildContainerCreatePayload } from '$lib/utils/containerCreatePayload';
  import { parseContainerListResponse, type ZunContainer, type EnvVar, type PortMapping } from '$lib/types/zunContainer';
  import ZunServiceBanner from '$lib/components/dashboard/containers/instances/ZunServiceBanner.svelte';
  import ZunServiceUnavailable from '$lib/components/dashboard/containers/instances/ZunServiceUnavailable.svelte';
  import ContainersTable from '$lib/components/dashboard/containers/instances/ContainersTable.svelte';
  import ContainerCreateModal from '$lib/components/dashboard/containers/instances/ContainerCreateModal.svelte';
  import { toast } from '$lib/stores/toast';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  const inventoryOwner = $derived(JSON.stringify([$auth.sessionId, $auth.userId, $auth.identityDomainId, $auth.domainId, $auth.projectId, !!$auth.token, $auth.isSystemAdmin, $auth.isDomainManager, $auth.canWrite, [...($auth.roles ?? [])].sort()]));
  let loadGeneration = 0;
  let containers = $state<ZunContainer[]>([]);
  let search = $state('');
  const columns = (): TableColumn<ZunContainer>[] => [
    { key: 'name', label: t('instances.fields.name'), value: row => row.name },
    { key: 'status', label: t('instances.fields.status'), value: row => row.status },
    { key: 'image', label: t('instances.fields.image'), value: row => row.image },
    { key: 'cpu', label: t('instances.fields.cpu'), value: row => row.cpu },
    { key: 'memory', label: t('instances.fields.memory'), value: row => row.memory },
    { key: 'created_at', label: t('instances.fields.createdAt'), value: row => row.created_at },
  ];
  const view = createTableView({ rows: () => containers, columns, search: () => search,
    searchable: row => [row.name, row.uuid, row.status, row.image, row.cpu, row.memory, row.created_at].map(value => String(value ?? '')), locale: intlLocale });
  let serviceAvailable = $state(true);
  let serviceMessage = $state('');
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let loaded = $state(false);
  let actionTarget = $state<string | null>(null);
  let showModal = $state(false);
  let lastCreated = $state<string | null>(null);
  let creating = $state(false);
  let createError = $state('');
  const selection = createResourceSelection();
  let bulkBusy = $state(false);
  const selectableIds = $derived(new Set(view.rows.map((container) => container.uuid)));
  const startIds = $derived(new Set(containers.filter((container) => container.status === 'Stopped' || container.status === 'Created').map((container) => container.uuid)));
  const stopIds = $derived(new Set(containers.filter((container) => container.status === 'Running').map((container) => container.uuid)));
  $effect(() => { selection.retain(view.rows.map(row => row.uuid)); });

  async function fetchContainers(opts?: { refresh?: boolean }) {
    const owner = inventoryOwner;
    const generation = ++loadGeneration;
    const current = () => owner === inventoryOwner && generation === loadGeneration;
    try {
      const resp = parseContainerListResponse(await api.get<unknown>('/api/v1/containers', $auth.token ?? undefined, $auth.projectId ?? undefined, opts));
      if (!current()) return;
      containers = resp.items;
      selection.retain(resp.items.map((container) => container.uuid));
      serviceAvailable = resp.service_available;
      serviceMessage = resp.message;
      loaded = true;
      error = '';
    } catch (e) {
      if (current()) error = e instanceof ApiError ? t('instances.errors.listLoadFailed', { status: e.status, message: e.message }) : t('instances.errors.server');
    } finally {
      if (current()) loading = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try {
      await fetchContainers({ refresh: true });
    } finally {
      refreshing = false;
    }
  }

  async function createContainer(payload: {
    name: string; image: string; command: string;
    cpu: number; memory: string;
    environment: EnvVar[]; ports: PortMapping[];
  }): Promise<boolean> {
    if (!payload.name.trim() || !payload.image.trim()) return false;
    creating = true;
    createError = '';
    try {
      await api.post('/api/v1/containers', buildContainerCreatePayload(payload), $auth.token ?? undefined, $auth.projectId ?? undefined);
      lastCreated = payload.name.trim();
      showModal = false;
      await fetchContainers();
      return true;
    } catch (e) {
      createError = e instanceof ApiError ? e.message : t('instances.errors.createFailed');
      return false;
    } finally {
      creating = false;
    }
  }

  async function startContainer(uuid: string) {
    actionTarget = uuid;
    try {
      await api.post(`/api/v1/containers/${uuid}/start`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchContainers();
    } catch (e) {
      toast.error(t('instances.errors.startFailed', { message: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      actionTarget = null;
    }
  }

  async function stopContainer(uuid: string) {
    actionTarget = uuid;
    try {
      await api.post(`/api/v1/containers/${uuid}/stop`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchContainers();
    } catch (e) {
      toast.error(t('instances.errors.stopFailed', { message: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      actionTarget = null;
    }
  }

  async function deleteContainer(uuid: string, name: string) {
    if (!await confirmDialog(t('instances.delete.confirm', { name }))) return;
    actionTarget = uuid;
    try {
      await api.delete(`/api/v1/containers/${uuid}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchContainers();
    } catch (e) {
      toast.error(t('instances.errors.deleteFailed', { message: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      actionTarget = null;
    }
  }
  async function runBulk(action: 'start' | 'stop' | 'delete') {
    const snapshot = [...selection.ids];
    if (snapshot.length === 0) return;
    const eligible = action === 'start' ? startIds : action === 'stop' ? stopIds : selectableIds;
    const { eligible: applicable, skipped } = partitionBulkIds(snapshot, eligible);
    if (applicable.length === 0) {
      if (skipped.length > 0) toast.warning(t('instances.bulk.skipped', { count: skipped.length, action }));
      return;
    }
    if (action === 'delete' || skipped.length > 0) {
      const prompt = t('instances.bulk.confirm', {
        count: applicable.length,
        action,
        hasSkipped: skipped.length > 0 ? 'yes' : 'no',
        skippedCount: skipped.length,
      });
      if (!await confirmDialog(prompt)) return;
    }
    const tokenSnapshot = $auth.token ?? undefined;
    const projectSnapshot = $auth.projectId ?? undefined;
    bulkBusy = true;
    try {
      const results = await executeBulkMutations(applicable, (id) => {
        if (action === 'start') return api.post(`/api/v1/containers/${id}/start`, {}, tokenSnapshot, projectSnapshot);
        if (action === 'stop') return api.post(`/api/v1/containers/${id}/stop`, {}, tokenSnapshot, projectSnapshot);
        return api.delete(`/api/v1/containers/${id}`, tokenSnapshot, projectSnapshot);
      });
      const successful = results.filter((result) => result.ok).map((result) => result.id);
      const failedCount = results.length - successful.length;
      if (skipped.length > 0) toast.warning(t('instances.bulk.skipped', { count: skipped.length, action }));
      if (successful.length > 0) toast.success(t('instances.bulk.success', { count: successful.length, action }));
      if (failedCount > 0) toast.error(t('instances.bulk.failed', { count: failedCount, action }));
      if ($auth.projectId === projectSnapshot) {
        selection.remove(successful);
        await fetchContainers();
      }
    } finally {
      bulkBusy = false;
    }
  }

  const bulkActions = $derived<BulkSelectionAction[]>([
    { key: 'start', label: t('instances.actions.start'), tone: 'success', disabled: ![...selection.ids].some((id) => startIds.has(id)), onAction: () => runBulk('start') },
    { key: 'stop', label: t('instances.actions.stop'), tone: 'warning', disabled: ![...selection.ids].some((id) => stopIds.has(id)), onAction: () => runBulk('stop') },
    { key: 'delete', label: t('instances.actions.delete'), tone: 'danger', onAction: () => runBulk('delete') },
  ]);

  const ar = createAutoRefresh(() => fetchContainers(), {
    storageKey: 'dashboard-zun-containers',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 10,
    intervalOptions: [10, 15, 30, 60],
  });

  $effect(() => {
    void inventoryOwner;
    untrack(() => {
      loadGeneration += 1;
      selection.clear();
      search = '';
      view.reset();
      containers = [];
      loaded = false;
      error = '';
      serviceAvailable = true;
      serviceMessage = '';
      if (!$auth.projectId || !$auth.token) { loading = false; return; }
      loading = true;
      void fetchContainers();
    });
  });

  $effect(() => {
    if (!showModal) createError = '';
  });
</script>

<ContainerCreateModal
  bind:open={showModal}
  {creating}
  error={createError}
  onCreate={createContainer}
/>

<PageShell class="bulk-selection-page">
  <PageHeader breadcrumb={t('instances.list.breadcrumb')} title={t('instances.list.title')}>
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing || loading}
        onManualRefresh={forceRefresh}
      />
      <TutorialStartButton tour="containers" compactOnMobile />
      <button data-tour="containers-create-open" onclick={() => showModal = true} class="bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium px-4 py-2 rounded-lg transition-colors">{t('instances.list.create')}</button>
    {/snippet}
  </PageHeader>

  {#if error}<div role="alert" class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  <ZunServiceBanner available={serviceAvailable} message={serviceMessage} />
  <RegexSearch id="zun-container-search" bind:value={search} class="mb-4" />

  {#if loading}
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('instances.list.title') })} />
  {:else if !serviceAvailable}
    <ZunServiceUnavailable />
  {:else if error && !loaded}
    <Button variant="secondary" onclick={forceRefresh}>{tl('autoRefresh.refreshNow')}</Button>
  {:else}
    <div data-tour="containers-list">
    <ContainersTable
      {containers}
      highlightName={lastCreated}
      {view}
      {actionTarget}
      selectedIds={selection.ids}
      selectableIds={selectableIds}
      selectionDisabled={bulkBusy}
      onToggleSelect={(id) => selection.toggle(id)}
      onToggleAll={() => selection.toggleAll(selectableIds)}
      onStart={startContainer}
      onStop={stopContainer}
      onDelete={deleteContainer}
      onOpen={(id) => goto(`/dashboard/containers/instances/${id}`)}
    />
    </div>
    <BulkSelectionOverlay
      count={selection.count}
      ariaLabel={t('instances.bulk.aria')}
      actions={bulkActions}
      busy={bulkBusy}
      onClear={() => selection.clear()}
    />
  {/if}
</PageShell>
