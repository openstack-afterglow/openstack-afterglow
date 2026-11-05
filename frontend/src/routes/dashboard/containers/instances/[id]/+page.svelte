<script lang="ts">
	import { t as tl } from '$lib/i18n/ns/common';
  import PageShell from '$lib/components/ui/PageShell.svelte';
  import { t } from '$lib/i18n/ns/containers-shell';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { onDestroy, untrack } from 'svelte';
  import { derived } from 'svelte/store';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import type { ZunContainerDetail } from '$lib/types/zunContainer';
  import ContainerDetailHeader from '$lib/components/dashboard/containers/instances/id/ContainerDetailHeader.svelte';
  import ContainerDetailGrid from '$lib/components/dashboard/containers/instances/id/ContainerDetailGrid.svelte';
  import ContainerTerminalPanel from '$lib/components/dashboard/containers/instances/id/ContainerTerminalPanel.svelte';
  import ContainerLogsPanel from '$lib/components/dashboard/containers/instances/id/ContainerLogsPanel.svelte';
  import { toast } from '$lib/stores/toast';
  import { createDetailReadScope, type DetailReadScope } from '$lib/utils/detailReadScope';
  import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceDiscarded, experienceState } from '$lib/utils/experience';

  let container = $state<ZunContainerDetail | null>(null);
  let logs = $state('');
  let loading = $state(true);
  let logsLoading = $state(false);
  let error = $state('');
  let actioning = $state(false);
  let showConsole = $state(false);

  const readScope = createDetailReadScope(derived(page, value => value.params.id ?? ''));
  const containerId = $derived($readScope.id);
  let activeScope = $state.raw<DetailReadScope | null>(null);
  let live = true;
  let controller = new AbortController();
  let detailGeneration = 0;
  let logsGeneration = 0;
  const scopeCurrent = $derived(activeScope !== null && isCurrentScope(activeScope));
  function isCurrentScope(scope: DetailReadScope) {
    return live && scope.ready && scope.revision === $readScope.revision && scope === activeScope;
  }
  onDestroy(() => { live = false; controller.abort(); detailGeneration += 1; logsGeneration += 1; });

  $effect(() => {
    const revision = $readScope.revision;
    untrack(() => {
      if (activeScope?.revision === revision) return;
      const scope = $readScope;
      controller.abort(); controller = new AbortController();
      activeScope = scope;
      container = null; logs = ''; error = '';
      loading = true; logsLoading = false; actioning = false; showConsole = false;
      detailGeneration += 1; logsGeneration += 1;
      if (isCurrentScope(scope)) {
        void fetchContainer(scope).then(() => {
          if (isCurrentScope(scope) && container) void fetchLogs();
        });
      }
    });
  });

  async function fetchContainer(scope = activeScope) {
    if (!scope || !isCurrentScope(scope)) return;
    const generation = ++detailGeneration;
    const current = () => isCurrentScope(scope) && generation === detailGeneration;
    const experience = beginExperienceLoad('container', 'resource.detail');
    experienceState(experience, 'loading');
    try {
      const next = await api.withExperience(experience).get<ZunContainerDetail>(`/api/v1/containers/${scope.id}`, $auth.token ?? undefined, $auth.projectId ?? undefined, { signal: controller.signal, cache: 'no-store', replayOnUnauthorized: true });
      if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
      container = next;
      error = '';
    } catch (e) {
      if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
      error = e instanceof ApiError ? t('instances.errors.detailLoadFailed', { message: e.message }) : t('instances.errors.server');
    } finally {
      if (current()) {
        loading = false;
        experienceState(experience, error ? 'error' : container ? 'ready' : 'empty');
        void experienceApplied(experience, {}, current);
      }
    }
  }

  async function fetchLogs(force = false) {
    const scope = activeScope;
    if (!scope || !isCurrentScope(scope)) return;
    const generation = ++logsGeneration;
    const current = () => isCurrentScope(scope) && generation === logsGeneration;
    const experience = force ? beginExperienceAction('container', 'refresh', 'resource.detail') : beginExperienceLoad('container', 'resource.detail');
    logsLoading = true;
    experienceState(experience, 'loading');
    let failed = false;
    try {
      const result = await api.withExperience(experience).get<{ logs: string }>(`/api/v1/containers/${scope.id}/logs${force ? '?refresh=true' : ''}`, $auth.token ?? undefined, $auth.projectId ?? undefined, { signal: controller.signal, cache: 'no-store', replayOnUnauthorized: true });
      if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
      logs = result.logs;
    } catch {
      if (!current()) { experienceDiscarded(experience, live ? 'stale' : 'unmounted'); return; }
      failed = true;
      logs = t('instances.logs.loadFailed');
    } finally {
      if (current()) {
        logsLoading = false;
        experienceState(experience, failed ? 'error' : logs ? 'ready' : 'empty');
        void experienceApplied(experience, {}, () => current() && !loading && container !== null);
      }
    }
  }

  async function handleAction(action: 'start' | 'stop') {
    const scope = activeScope;
    if (!scope || !isCurrentScope(scope)) return;
    actioning = true;
    try {
      await api.post(`/api/v1/containers/${scope.id}/${action}`, {}, $auth.token ?? undefined, $auth.projectId ?? undefined);
      if (isCurrentScope(scope)) await fetchContainer(scope);
    } catch (e) {
      if (isCurrentScope(scope)) toast.error(t(action === 'start' ? 'instances.errors.startFailed' : 'instances.errors.stopFailed', { message: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      if (isCurrentScope(scope)) actioning = false;
    }
  }

  async function handleDelete() {
    const scope = activeScope;
    if (!scope || !container || !isCurrentScope(scope)) return;
    if (!await confirmDialog(t('instances.delete.confirm', { name: container.name })) || !isCurrentScope(scope)) return;
    try {
      await api.delete(`/api/v1/containers/${scope.id}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      if (isCurrentScope(scope)) goto('/dashboard/containers/instances');
    } catch (e) {
      if (isCurrentScope(scope)) toast.error(t('instances.errors.deleteFailed', { message: e instanceof ApiError ? e.message : String(e) }));
    }
  }

  const ar = createAutoRefresh(fetchLogs, {
    storageKey: 'dashboard-container-logs',
    defaultInterval: 15,
    intervalOptions: [10, 15, 30, 60],
    invokeOnMount: false,
    enabled: () => scopeCurrent && !loading && container !== null && !logsLoading,
  });

</script>

<PageShell>
  {#if scopeCurrent && error}<div role="alert" class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}

  {#if loading || !scopeCurrent}
    <div class="flex items-center gap-3 mb-6">
      <button onclick={() => goto('/dashboard/containers/instances')} class="text-ink-2 hover:text-ink-0 transition-colors">{t('instances.detail.back')}</button>
    </div>
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('instances.list.title') })} />
  {:else if container}
    <ContainerDetailHeader
      {container}
      {actioning}
      terminalOpen={showConsole}
      onOpenTerminal={() => { showConsole = true; }}
      onStart={() => handleAction('start')}
      onStop={() => handleAction('stop')}
      onDelete={handleDelete}
      onBack={() => goto('/dashboard/containers/instances')}
    />

    <ContainerDetailGrid {container} />

    {#if showConsole}
      <ContainerTerminalPanel
        bind:open={showConsole}
        containerId={containerId ?? ''}
        token={$auth.token ?? undefined}
        projectId={$auth.projectId ?? undefined}
      />
    {/if}

    <ContainerLogsPanel
      {logs}
      {logsLoading}
      {ar}
      onManualRefresh={ar.refresh}
    />
  {:else if !error}
    <p role="status">{t('instances.empty.title')}</p>
  {/if}
</PageShell>
