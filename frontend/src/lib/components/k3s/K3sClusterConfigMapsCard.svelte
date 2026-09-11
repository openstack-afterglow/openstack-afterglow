<script lang="ts">
  import { untrack } from 'svelte';
  import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
  import K3sResourceEditor from './K3sResourceEditor.svelte';
  import K3sYamlView from './K3sYamlView.svelte';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { toConfigMapYaml } from '$lib/utils/k8sYaml';

  const s = useK3sClusterDetailController();

  let showCreate = $state(false);
  let newName = $state('');
  let editingCm = $state<{ name: string; data: Record<string, string> } | null>(null);
  let saving = $state(false);
  let createError = $state('');
  let loadError = $state('');

  $effect(() => {
    const ns = s.selectedNamespace;
    if (!ns) return;
    loadError = '';
    untrack(() => s.loadConfigMaps()).catch(() => { loadError = 'ConfigMap 로드 실패'; });
  });

  async function handleCreate(data: Record<string, string>) {
    if (!newName.trim()) { createError = '이름을 입력하세요'; return; }
    saving = true;
    createError = '';
    try {
      await s.saveConfigMap(newName.trim(), data, true);
      showCreate = false;
      newName = '';
    } catch (e) {
      createError = e instanceof Error ? e.message : '생성 실패';
    } finally {
      saving = false;
    }
  }

  async function handleEdit(data: Record<string, string>) {
    if (!editingCm) return;
    saving = true;
    try {
      await s.saveConfigMap(editingCm.name, data, false);
      editingCm = null;
    } finally {
      saving = false;
    }
  }

  async function handleDelete(name: string) {
    if (!(await confirmDialog(`ConfigMap "${name}"을 삭제하시겠습니까?`))) return;
    await s.deleteCm(name);
  }
</script>

<div class="bg-surface-base border border-line rounded-xl p-4 mt-3">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-xs text-ink-3 uppercase tracking-wide">ConfigMaps</h3>
    <button
      onclick={() => { showCreate = !showCreate; newName = ''; createError = ''; }}
      class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
    >{showCreate ? '닫기' : '+ 생성'}</button>
  </div>

  {#if showCreate}
    <div class="mb-3 bg-surface-sunken rounded-lg p-3">
      <input
        bind:value={newName}
        placeholder="ConfigMap 이름"
        class="w-full bg-surface-selected border border-line-2 text-ink-1 text-xs rounded px-2 py-1.5 font-mono mb-2 focus:outline-none focus:border-action-warm"
      />
      {#if createError}
        <p class="text-xs text-red-400 mb-1">{createError}</p>
      {/if}
      <K3sResourceEditor
        title="ConfigMap 생성"
        mode="configmap"
        resourceName={newName}
        namespace={s.selectedNamespace ?? ''}
        onSave={handleCreate}
        onClose={() => { showCreate = false; }}
        {saving}
      />
    </div>
  {/if}

  {#if loadError}
    <p class="text-xs text-red-400">{loadError}</p>
  {:else if s.configMaps.length === 0}
    <p class="text-xs text-ink-3">ConfigMap 없음</p>
  {:else}
    <div class="space-y-2">
      {#each s.configMaps as cm}
        {@const actionKey = `${s.selectedNamespace}:${cm.name}`}
        <div class="bg-surface-sunken/50 rounded-lg p-3">
          <div class="flex items-center justify-between gap-3 mb-2">
            <span class="text-xs text-ink-1 font-mono font-medium">{cm.name}</span>
            <div class="flex gap-1 shrink-0">
              <button
                onclick={() => { editingCm = { name: cm.name, data: { ...cm.data } }; }}
                class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors"
              >편집</button>
              <button
                onclick={() => handleDelete(cm.name)}
                disabled={s.cmActioning === actionKey}
                class="text-xs text-orange-400 hover:text-orange-300 px-2 py-1 border border-orange-900 hover:border-orange-700 rounded transition-colors disabled:text-ink-3 disabled:border-line-2 disabled:cursor-not-allowed"
              >{s.cmActioning === actionKey ? '삭제 중...' : '삭제'}</button>
            </div>
          </div>
          <K3sYamlView
            text={toConfigMapYaml(cm.name, s.selectedNamespace ?? '', cm.data)}
          />
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if editingCm}
  <K3sResourceEditor
    title={`ConfigMap 편집 — ${editingCm.name}`}
    mode="configmap"
    resourceName={editingCm.name}
    namespace={s.selectedNamespace ?? ''}
    initialData={editingCm.data}
    onSave={handleEdit}
    onClose={() => { editingCm = null; }}
    {saving}
  />
{/if}
