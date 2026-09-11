<script lang="ts">
  import { untrack } from 'svelte';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import K3sResourceEditor from './K3sResourceEditor.svelte';
  import K3sYamlView from './K3sYamlView.svelte';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { toSecretReadYaml } from '$lib/utils/k8sYaml';

  const s = useK3sClusterDetailController();

  let showCreate = $state(false);
  let newName = $state('');
  let newType = $state('Opaque');
  let editingSecret = $state<{ name: string; type: string; data: Record<string, string> } | null>(null);
  let saving = $state(false);
  let createError = $state('');
  let loadError = $state('');

  $effect(() => {
    const ns = s.selectedNamespace;
    if (!ns) return;
    loadError = '';
    untrack(() => s.loadSecrets()).catch(() => { loadError = 'Secret 로드 실패'; });
  });

  async function handleCreate(data: Record<string, string>) {
    if (!newName.trim()) { createError = '이름을 입력하세요'; return; }
    saving = true;
    createError = '';
    try {
      await s.saveSecret(newName.trim(), newType, data, true);
      showCreate = false;
      newName = '';
      newType = 'Opaque';
    } catch (e) {
      createError = e instanceof Error ? e.message : '생성 실패';
    } finally {
      saving = false;
    }
  }

  async function handleEdit(data: Record<string, string>) {
    if (!editingSecret) return;
    saving = true;
    try {
      await s.saveSecret(editingSecret.name, editingSecret.type, data, false);
      editingSecret = null;
    } finally {
      saving = false;
    }
  }

  async function handleDelete(name: string) {
    if (!(await confirmDialog(`Secret "${name}"을 삭제하시겠습니까?`))) return;
    await s.deleteSecretItem(name);
  }
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mt-3">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-xs text-ink-3 uppercase tracking-wide">Secrets</h3>
    <button
      onclick={() => { showCreate = !showCreate; newName = ''; createError = ''; newType = 'Opaque'; }}
      class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
    >{showCreate ? '닫기' : '+ 생성'}</button>
  </div>

  {#if showCreate}
    <div class="mb-3 bg-surface-sunken rounded-lg p-3">
      <div class="flex gap-2 mb-2">
        <input
          bind:value={newName}
          placeholder="Secret 이름"
          class="flex-1 bg-surface-selected border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 font-mono focus:outline-none focus:border-action-warm"
        />
        <select
          bind:value={newType}
          class="bg-surface-selected border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
        >
          <option value="Opaque">Opaque</option>
          <option value="kubernetes.io/tls">kubernetes.io/tls</option>
          <option value="kubernetes.io/dockerconfigjson">dockerconfigjson</option>
        </select>
      </div>
      {#if createError}
        <p class="text-xs text-red-400 mb-1">{createError}</p>
      {/if}
      <K3sResourceEditor
        title="Secret 생성"
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

  {#if loadError}
    <p class="text-xs text-red-400">{loadError}</p>
  {:else if s.secrets.length === 0}
    <p class="text-xs text-ink-3">Secret 없음</p>
  {:else}
    <div class="space-y-2">
      {#each s.secrets as secret}
        {@const actionKey = `${s.selectedNamespace}:${secret.name}`}
        {@const { text, maskedKeys } = toSecretReadYaml(
          secret.name,
          s.selectedNamespace ?? '',
          secret.type,
          secret.data
        )}
        <div class="bg-surface-sunken/50 rounded-lg p-3">
          <div class="flex items-center justify-between gap-3 mb-2">
            <div>
              <span class="text-xs text-ink-1 font-mono font-medium">{secret.name}</span>
              <span class="text-xs text-ink-3 ml-2">{secret.type}</span>
            </div>
            <div class="flex gap-1 shrink-0">
              <button
                onclick={() => { editingSecret = { name: secret.name, type: secret.type, data: {} }; }}
                class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors"
              >편집</button>
              <button
                onclick={() => handleDelete(secret.name)}
                disabled={s.cmActioning === actionKey}
                class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3 disabled:border-line-2 disabled:cursor-not-allowed"
              >{s.cmActioning === actionKey ? '삭제 중...' : '삭제'}</button>
            </div>
          </div>
          <K3sYamlView {text} {maskedKeys} />
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if editingSecret}
  <K3sResourceEditor
    title={`Secret 편집 — ${editingSecret.name}`}
    mode="secret"
    resourceName={editingSecret.name}
    namespace={s.selectedNamespace ?? ''}
    secretType={editingSecret.type}
    onSave={handleEdit}
    onClose={() => { editingSecret = null; }}
    {saving}
  />
{/if}
