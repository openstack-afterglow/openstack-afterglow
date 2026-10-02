<script lang="ts">
  import { t } from '$lib/i18n/ns/file-storage';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { FileStorage } from '$lib/types/fileStorage';
  import type { LibraryConfig } from '$lib/types/library';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import { createCoalescedRefresh } from '$lib/utils/coalescedRefresh';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import PrebuiltLibraryGrid from '$lib/components/file-storage/manage/PrebuiltLibraryGrid.svelte';
  import FileStorageManageGrid from '$lib/components/file-storage/manage/FileStorageManageGrid.svelte';

  let fileStorages = $state<FileStorage[]>([]);
  let libraries = $state<LibraryConfig[]>([]);
  let building = $state<string | null>(null);
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let message = $state('');
  let autoInstall = $state(true);

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  async function loadData(opts?: { refresh?: boolean }) {
    if (fileStorages.length === 0) loading = true;
    else refreshing = true;
    await Promise.allSettled([
      api.get<FileStorage[]>('/api/v1/admin/file-storage', token, projectId, opts)
        .then(v => { fileStorages = v; loading = false; })
        .catch(e => {
          error = e instanceof ApiError ? t('manage.loadFailed', { message: e.message }) : t('errors.server');
          fileStorages = [];
          loading = false;
        }),
      api.get<LibraryConfig[]>('/api/v1/libraries', token, projectId, opts)
        .then(v => { libraries = v; })
        .catch(() => {}),
    ]);
    loading = false;
    refreshing = false;
  }

  async function buildFileStorage(libId: string) {
    building = libId;
    message = '';
    error = '';
    try {
      const params = new URLSearchParams({ library_id: libId });
      if (autoInstall) params.set('auto_install', 'true');
      const res = await api.post<{ file_storage_id: string; server_id?: string }>(
        `/api/v1/admin/file-storage/build?${params}`, {}, token, projectId
      );
      if (autoInstall && res.server_id) {
        message = t('manage.autoBuildStarted', { shareId: res.file_storage_id, serverId: res.server_id });
      } else {
        message = t('manage.createStarted', { id: res.file_storage_id });
      }
      await refresh.invalidate();
    } catch (e) {
      error = e instanceof ApiError ? t('manage.buildFailed', { message: e.message }) : t('errors.server');
    } finally {
      building = null;
    }
  }

  const refresh = createCoalescedRefresh((force) => loadData(force ? { refresh: true } : undefined));

  $effect(() => {
    if (!$auth.projectId) return;
    fileStorages = [];
    untrack(() => void refresh.run(false));
  });

  const ar = createAutoRefresh(() => refresh.run(false), {
    storageKey: 'dashboard-file-storage',
    defaultActive: true,
    defaultInterval: 30,
    intervalOptions: [15, 30, 60],
    invokeOnMount: false
  });
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
  <PageHeader breadcrumb={t('manage.breadcrumb')} title={t('manage.title')} subtitle={t('manage.subtitle')}>
    {#snippet actions()}
      <label class="flex items-center gap-2 text-xs text-ink-2 cursor-pointer">
        <input type="checkbox" bind:checked={autoInstall} class="rounded border-line-2 bg-surface-sunken text-warm-text focus:ring-line-2 focus:ring-offset-0" />
        {t('manage.autoInstall')}
      </label>
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={loading || refreshing}
        onManualRefresh={() => refresh.run(true)}
      />
    {/snippet}
  </PageHeader>

  {#if error}
    <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>
  {/if}
  {#if message}
    <div class="bg-green-900/40 border border-green-700 text-green-300 rounded-lg px-4 py-3 text-sm mb-4">{message}</div>
  {/if}

  {#if loading}
    <LoadingSkeleton variant="list" rows={4} />
  {:else}
      <div class="mb-8">
        <h2 class="text-base font-semibold text-ink-0 mb-3">{t('manage.prebuiltStatus')}</h2>
        <PrebuiltLibraryGrid {libraries} {fileStorages} {building} onBuild={buildFileStorage} />
      </div>

      <div class="flex items-center justify-between mb-3">
        <h2 class="text-base font-semibold text-ink-0">{t('manage.allStorages')}</h2>
      </div>
      {#if fileStorages.length === 0}
        <div class="text-ink-2 text-sm py-8 text-center">{t('list.empty')}</div>
      {:else}
        <FileStorageManageGrid {fileStorages} />
      {/if}
  {/if}
</div>
