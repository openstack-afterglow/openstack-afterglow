<script lang="ts">
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { t as tl } from '$lib/i18n/ns/common';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { onDestroy, untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import type { Keypair } from '$lib/types/keypair';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
  import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
  import { Alert, Button, PageHeader, PageShell, ResourceToolbar } from '$lib/components/ui';
  import KeypairCreateModal from '$lib/components/keypair/KeypairCreateModal.svelte';
  import KeypairListTable from '$lib/components/keypair/KeypairListTable.svelte';
  import KeypairEmptyState from '$lib/components/keypair/KeypairEmptyState.svelte';
  import { toast } from '$lib/stores/toast';
  import { t } from '$lib/i18n/ns/images-keys';
  import { beginExperienceAction, beginExperienceLoad, experienceApplied, experienceState, type ExperienceContext } from '$lib/utils/experience';

  let keypairs = $state<Keypair[]>([]);
  let search = $state('');
  const columns = $derived<TableColumn<Keypair>[]>([
    { key: 'name', label: t('keypairTable.columns.name'), value: row => row.name },
    { key: 'type', label: t('keypairTable.columns.type'), value: row => row.type },
    { key: 'fingerprint', label: t('keypairTable.columns.fingerprint'), value: row => row.fingerprint },
  ]);
  const view = createTableView({ rows: () => keypairs, columns: () => columns, search: () => search });
  let loading = $state(true);
  let refreshing = $state(false);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let copiedFingerprint = $state<string | null>(null);
  let showModal = $state(false);
  let stateVersion = 0;
  let live = true;
  onDestroy(() => { live = false; });

  async function fetchKeypairs(opts?: { refresh?: boolean }, experience: ExperienceContext | undefined = beginExperienceLoad('compute', 'resource.list')) {
    const projectId = $auth.projectId, userId = $auth.userId;
    let appliedVersion = 0;
    const current = () => live && appliedVersion === stateVersion && $auth.projectId === projectId && $auth.userId === userId;
    if (loading || refreshing) experienceState(experience, 'loading');
    try {
      keypairs = await api.withExperience(experience).get<Keypair[]>('/api/v1/keypairs', $auth.token ?? undefined, $auth.projectId ?? undefined, opts);
      error = '';
      appliedVersion = ++stateVersion;
      if (experience?.action !== 'create') experienceState(experience, keypairs.length ? 'ready' : 'empty');
      if (experience) void experienceApplied(experience, {}, current);
    } catch (e) {
      error = e instanceof ApiError ? t('keypairPage.error.fetchFailed', { status: e.status }) : t('keypairPage.error.server');
      appliedVersion = ++stateVersion;
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience, {}, current);
    } finally {
      loading = false;
    }
  }

  async function forceRefresh() {
    refreshing = true;
    try {
      await fetchKeypairs({ refresh: true }, beginExperienceAction('compute', 'refresh', 'resource.list'));
    } finally {
      refreshing = false;
    }
  }

  const ar = createAutoRefresh(() => fetchKeypairs(), {
    storageKey: 'dashboard-compute-keypairs',
    invokeOnMount: false,
    defaultActive: true,
    defaultInterval: 60,
    intervalOptions: [10, 15, 30, 60],
  });

  async function createKeypair(form: { name: string; public_key: string }): Promise<{ private_key?: string } | string> {
    const experience = beginExperienceAction('compute', 'create', 'resource.list');
    try {
      const result = await api.withExperience(experience).post<Keypair>('/api/v1/keypairs', {
        name: form.name,
        public_key: form.public_key.trim() || null,
      }, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchKeypairs(undefined, experience);
      return { private_key: result.private_key };
    } catch (e) {
      experienceState(experience, 'error');
      return e instanceof ApiError ? e.message : t('keypairPage.error.createFailed');
    }
  }

  async function deleteKeypair(name: string) {
    if (!await confirmDialog(t('keypairPage.deleteDialog.body', { name }))) return;
    deleting = name;
    const experience = beginExperienceAction('compute', 'delete', 'resource.list');
    try {
      await api.withExperience(experience).delete(`/api/v1/keypairs/${name}`, $auth.token ?? undefined, $auth.projectId ?? undefined);
      await fetchKeypairs(undefined, experience);
    } catch (e) {
      toast.error(t('keypairPage.toast.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
      experienceState(experience, 'error');
      if (experience) void experienceApplied(experience);
    } finally {
      deleting = null;
    }
  }

  async function copyFingerprint(fingerprint: string) {
    try {
      await navigator.clipboard.writeText(fingerprint);
      copiedFingerprint = fingerprint;
      setTimeout(() => (copiedFingerprint = null), 2000);
    } catch {
      // 비보안 컨텍스트(HTTP) 또는 권한 거부 시 조용히 무시
    }
  }

  $effect(() => {
    const pid = $auth.projectId;
    if (!pid) return;
    untrack(() => fetchKeypairs());
  });
</script>

<KeypairCreateModal bind:open={showModal} onCreate={createKeypair} />

<PageShell class="space-y-4">
  <PageHeader breadcrumb={t('keypairPage.breadcrumb')} title={t('keypairPage.title')}>
    {#snippet actions()}
      <Button onclick={() => showModal = true} variant="primary">{t('keypairPage.actions.create')}</Button>
    {/snippet}
  </PageHeader>
  <ResourceToolbar label={t('keypairPage.toolbar.label')}>
    {#snippet filters()}<RegexSearch id="compute-keypairs-search" bind:value={search} />{/snippet}
    {#snippet actions()}
      <AutoRefreshControl
        bind:active={ar.active}
        bind:intervalSeconds={ar.intervalSeconds}
        intervalOptions={ar.intervalOptions}
        refreshing={refreshing}
        onManualRefresh={forceRefresh}
      />
    {/snippet}
  </ResourceToolbar>
  <TableViewControls {view} />

  {#if error}<Alert tone="danger">{error}</Alert>{/if}

  {#if loading}
    <LoadingState variant="surface" label={tl('state.loadingNamed', { name: t('keypairPage.title') })} />
  {:else if keypairs.length === 0}
    <KeypairEmptyState onCreate={() => (showModal = true)} />
  {/if}
  {#if !loading}
    <KeypairListTable
      keypairs={view.rows}
      {view}
      {deleting}
      {copiedFingerprint}
      onCopy={copyFingerprint}
      onDelete={deleteKeypair}
    />
  {/if}
</PageShell>
