<script lang="ts">
	import { createTableView, type TableColumn } from '$lib/utils/tableView.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import { t as tableT } from '$lib/i18n/ns/common';
  import { t } from '$lib/i18n/ns/drover';
  import { t as commonT } from '$lib/i18n/ns/common';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { untrack } from 'svelte';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import { k3sPermissions } from '$lib/stores/k3sPermissions';
  import K3sResourceEditor from './K3sResourceEditor.svelte';
  import K3sYamlView from './K3sYamlView.svelte';
  import { toSecretReadYaml } from '$lib/utils/k8sYaml';

  const s = useK3sClusterDetailController();

  let showCreate = $state(false);
  let newName = $state('');
  let newType = $state('Opaque');
  let editingSecret = $state<{ name: string; type: string; data: Record<string, string> } | null>(null);
  let saving = $state(false);
  let createError = $state('');
  let loadError = $state('');
  let loading = $state(false);

  $effect(() => {
    const ns = s.selectedNamespace;
    if (!ns || !$k3sPermissions.workloads) { loading = false; return; }
    let current = true;
    loading = true;
    loadError = '';
    untrack(() => s.loadSecrets())
      .catch(() => { if (current) loadError = t('secrets.loadFailed'); })
      .finally(() => { if (current) loading = false; });
    return () => { current = false; };
  });

  async function handleCreate(data: Record<string, string>) {
    if (!$k3sPermissions.workloads || (newType !== 'Opaque' && !$k3sPermissions.adminCredentials)) return;
    if (!newName.trim()) { createError = t('secrets.nameRequired'); return; }
    saving = true;
    createError = '';
    try {
      await s.saveSecret(newName.trim(), newType, data, true);
      showCreate = false;
      newName = '';
      newType = 'Opaque';
    } catch (e) {
      createError = e instanceof Error ? e.message : t('secrets.createFailed');
    } finally {
      saving = false;
    }
  }

  async function handleEdit(data: Record<string, string>) {
    if (!$k3sPermissions.workloads || !editingSecret || (editingSecret.type !== 'Opaque' && !$k3sPermissions.adminCredentials)) return;
    saving = true;
    try {
      await s.saveSecret(editingSecret.name, editingSecret.type, data, false);
      editingSecret = null;
    } finally {
      saving = false;
    }
  }

  async function handleDelete(name: string) {
    if (!$k3sPermissions.workloads) return;
    await s.deleteSecretItem(name);
  }
	const tableState = s.tableState('secrets');
	const columns = $derived<TableColumn<(typeof s.secrets)[number]>[]>([
		{ key: 'name', label: tableT('table.name'), value: row => row.name },
		{ key: 'type', label: tableT('table.type'), value: row => row.type },
	]);
	const view = createTableView({ rows: () => s.secrets, columns: () => columns, search: () => tableState.search, state: tableState.state });
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mt-3">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-xs text-ink-2 uppercase tracking-wide">Secrets</h3>
    <button
      onclick={() => { showCreate = !showCreate; newName = ''; createError = ''; newType = 'Opaque'; }}
      disabled={!$k3sPermissions.workloads || !s.selectedNamespace}
      class="text-xs text-warm-text hover:text-warm-text-hover transition-colors"
    >{showCreate ? t('secrets.close') : t('secrets.create')}</button>
  </div>

  {#if showCreate && $k3sPermissions.workloads}
    <div class="mb-3 bg-surface-sunken rounded-lg p-3">
      <div class="flex gap-2 mb-2">
        <input
          bind:value={newName}
          placeholder={t('secrets.namePlaceholder')}
          class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 font-mono focus:outline-none focus:border-action-warm"
        />
        <select
          bind:value={newType}
          class="bg-surface-selected border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
        >
          <option value="Opaque">Opaque</option>
          {#if $k3sPermissions.adminCredentials}
          <option value="kubernetes.io/tls">kubernetes.io/tls</option>
          <option value="kubernetes.io/dockerconfigjson">dockerconfigjson</option>
          {/if}
        </select>
      </div>
      {#if createError}
        <p class="text-xs text-red-400 mb-1">{createError}</p>
      {/if}
      <K3sResourceEditor
        title={t('secrets.createTitle')}
        mode="secret"
        resourceName={newName}
        namespace={s.selectedNamespace ?? ''}
        secretType={newType}
        onSave={handleCreate}
        onClose={() => { showCreate = false; }}
        {saving}
      />
    </div>
  {/if}

  <RegexSearch id="k3s-secrets-search" bind:value={tableState.search} />
	<TableViewControls {view} class="" />
	{#if loading}
    <LoadingState variant="inline" label={commonT('state.loadingNamed', { name: 'Secrets' })} />
  {/if}
  {#if loadError}
    <p class="text-xs text-red-400">{loadError}</p>
  {:else if s.secrets.length === 0 && !loading}
    <p class="text-xs text-ink-2">{t('secrets.empty')}</p>
  {:else}
    <div class="space-y-2">
      {#each view.rows as secret (JSON.stringify([s.projectId, s.cluster?.id, s.selectedNamespace, secret.name]))}
        {@const actionKey = `${s.selectedNamespace}:${secret.name}`}
        {@const { text, maskedKeys } = toSecretReadYaml(
          secret.name,
          s.selectedNamespace ?? '',
          secret.type,
          secret.data
        )}
        <div class="bg-surface-sunken/50 rounded-lg p-3" data-testid="k3s-secret" data-secret-name={secret.name}>
          <div class="flex items-center justify-between gap-3 mb-2">
            <div>
              <span class="text-xs text-ink-1 font-mono font-medium">{secret.name}</span>
              <span class="text-xs text-ink-2 ml-2">{secret.type}</span>
            </div>
            <div class="flex gap-1 shrink-0">
              <button
                onclick={() => { editingSecret = { name: secret.name, type: secret.type, data: {} }; }}
                disabled={!$k3sPermissions.workloads || !s.selectedNamespace || (secret.type !== 'Opaque' && !$k3sPermissions.adminCredentials)}
                class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors"
              >{t('secrets.edit')}</button>
              <button
                onclick={() => handleDelete(secret.name)}
                disabled={!$k3sPermissions.workloads || !s.selectedNamespace || s.cmActioning === actionKey}
                class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3 disabled:border-line-2 disabled:cursor-not-allowed"
              >{#if s.cmActioning === actionKey}<LoadingState variant="control" label={t('secrets.deleting')} />{:else}{t('secrets.delete')}{/if}</button>
            </div>
          </div>
          <K3sYamlView {text} {maskedKeys} />
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if editingSecret && $k3sPermissions.workloads && (editingSecret.type === 'Opaque' || $k3sPermissions.adminCredentials)}
  <K3sResourceEditor
    title={t('secrets.editTitle', { name: editingSecret.name })}
    mode="secret"
    resourceName={editingSecret.name}
    namespace={s.selectedNamespace ?? ''}
    secretType={editingSecret.type}
    onSave={handleEdit}
    onClose={() => { editingSecret = null; }}
    {saving}
  />
{/if}
