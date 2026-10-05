<script lang="ts">
  import { t } from '$lib/i18n/ns/account';
  import { untrack } from 'svelte';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { toast } from '$lib/stores/toast';
  import { dialogFocus } from '$lib/utils/dialogFocus';

  interface Keypair {
    name: string;
    fingerprint: string;
    type: string;
    public_key?: string;
    private_key?: string;
  }

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  let keypairs = $state<Keypair[]>([]);
  let loading = $state(true);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let copiedFingerprint = $state<string | null>(null);
  let showModal = $state(false);
  let creating = $state(false);
  let createError = $state('');
  let createdPrivateKey = $state<string | null>(null);
  let form = $state({ name: '', public_key: '' });

  async function fetchKeypairs() {
    try {
      keypairs = await api.get<Keypair[]>('/api/v1/keypairs', token, projectId);
      error = '';
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('keypairs.loadFailed');
    } finally {
      loading = false;
    }
  }

  async function createKeypair() {
    if (!form.name.trim()) return;
    creating = true;
    createError = '';
    try {
      const result = await api.post<Keypair>('/api/v1/keypairs', {
        name: form.name,
        public_key: form.public_key.trim() || null,
      }, token, projectId);
      if (result.private_key) {
        createdPrivateKey = result.private_key;
      } else {
        showModal = false;
      }
      form = { name: '', public_key: '' };
      await fetchKeypairs();
    } catch (e) {
      createError = e instanceof ApiError ? e.message : t('keypairs.createFailed');
    } finally {
      creating = false;
    }
  }

  async function deleteKeypair(name: string) {
    if (!(await confirmDialog(t('keypairs.deleteConfirm', { name })))) return;
    deleting = name;
    try {
      await api.delete(`/api/v1/keypairs/${name}`, token, projectId);
      await fetchKeypairs();
    } catch (e) {
      toast.error(t('keypairs.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      deleting = null;
    }
  }

  async function copyFingerprint(fingerprint: string) {
    try {
      await navigator.clipboard.writeText(fingerprint);
      copiedFingerprint = fingerprint;
      setTimeout(() => (copiedFingerprint = null), 2000);
    } catch { /* 비보안 컨텍스트 무시 */ }
  }

  function handleFileUpload(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (file.size > 65536) { createError = t('keypairs.fileTooLarge'); input.value = ''; return; }
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = ((e.target?.result as string) ?? '').trim();
      if (content && !/^(ssh-rsa|ssh-ed25519|ssh-dss|ecdsa-sha2-\S+)\s/.test(content)) {
        createError = t('keypairs.invalidKey');
        return;
      }
      form.public_key = content;
    };
    reader.readAsText(file);
    input.value = '';
  }

  $effect(() => {
    const pid = $auth.projectId;
    if (!pid) return;
    untrack(() => fetchKeypairs());
  });
</script>

{#if showModal}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
		use:dialogFocus={{ enabled: true, onEscape: () => (showModal = false) }} class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50" onclick={() => showModal = false} role="dialog" aria-modal="true" tabindex="-1">
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]" onclick={(e) => e.stopPropagation()} role="none">
      {#if createdPrivateKey}
        <h2 class="text-lg font-semibold text-ink-0 mb-3">{t('keypairs.privateKey')}</h2>
        <p class="text-sm text-yellow-300 mb-3">{t('keypairs.privateWarning')}</p>
        <pre class="bg-surface-sunken rounded p-3 text-xs text-green-300 overflow-auto max-h-48 mb-4">{createdPrivateKey}</pre>
        <button onclick={() => { createdPrivateKey = null; showModal = false; }} class="w-full px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg transition-colors">{t('keypairs.confirm')}</button>
      {:else}
        <h2 class="text-lg font-semibold text-ink-0 mb-5">{t('keypairs.create')}</h2>
        <div class="space-y-4">
          <div>
            <label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide">{t('keypairs.name')}
              <input bind:value={form.name} type="text" placeholder="my-keypair" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm mt-1.5" />
            </label>
          </div>
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-xs text-ink-2 uppercase tracking-wide">{t('keypairs.publicKey')}</span>
              <label class="text-xs text-warm-text hover:text-warm-text-hover cursor-pointer transition-colors">
                {t('keypairs.chooseFile')}<input type="file" accept=".pub,.pem,.txt" class="hidden" onchange={handleFileUpload} />
              </label>
            </div>
            <textarea bind:value={form.public_key} placeholder="ssh-rsa AAAA..." rows="3" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm font-mono resize-none"></textarea>
          </div>
        </div>
        {#if createError}<div class="mt-3 text-red-400 text-xs">{createError}</div>{/if}
        <div class="flex justify-end gap-3 mt-6">
          <button onclick={() => showModal = false} class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">{t('keypairs.cancel')}</button>
          <button onclick={createKeypair} disabled={creating} class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-ink-0 text-sm font-medium rounded-lg transition-colors">{creating ? t('keypairs.creating') : t('keypairs.createAction')}</button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<div class="bg-surface-base border border-line rounded-xl p-5">
  <div class="flex items-center justify-between mb-4">
    <h3 class="text-sm font-semibold text-ink-0">{t('keypairs.title')}</h3>
    <button onclick={() => showModal = true} class="text-xs px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-0 rounded-lg transition-colors">{t('keypairs.add')}</button>
  </div>

  {#if error}
    <div class="text-red-400 text-xs mb-3">{error}</div>
  {/if}

  {#if loading}
    <div class="space-y-2">
      {#each [1, 2] as _}
        <div class="h-10 bg-surface-sunken rounded animate-pulse"></div>
      {/each}
    </div>
  {:else if keypairs.length === 0}
    <div class="text-ink-2 text-xs text-center py-6">{t('keypairs.empty')}</div>
  {:else}
    <div class="bg-[#0B1220] border border-line rounded-lg overflow-hidden">
      <div class="grid grid-cols-[1fr_100px_80px] px-3 py-2 border-b border-line text-xs uppercase tracking-wider text-ink-2">
        <div>{t('keypairs.nameFingerprint')}</div>
        <div>{t('keypairs.type')}</div>
        <div class="text-right">{t('keypairs.actions')}</div>
      </div>
      {#each keypairs as kp, i (kp.name)}
        <div class="grid grid-cols-[1fr_100px_80px] px-3 py-2.5 text-xs items-center {i < keypairs.length - 1 ? 'border-b border-line' : ''} hover:bg-surface-sunken/30 transition-colors">
          <div class="min-w-0">
            <div class="text-ink-0 font-medium truncate">{kp.name}</div>
            <div class="text-xs text-ink-2 font-mono truncate mt-0.5">{kp.fingerprint}</div>
          </div>
          <div>
            <span class="text-xs font-mono px-1.5 py-0.5 rounded bg-violet-900/25 border border-violet-800 text-violet-400">{kp.type}</span>
          </div>
          <div class="flex gap-1 justify-end">
            <button
              onclick={() => copyFingerprint(kp.fingerprint)}
              class="text-xs px-1.5 py-1 rounded bg-surface-sunken hover:bg-surface-selected text-ink-2 border border-line-2 transition-colors"
            >{copiedFingerprint === kp.fingerprint ? t('keypairs.copied') : t('keypairs.copy')}</button>
            <button
              onclick={() => deleteKeypair(kp.name)}
              disabled={deleting === kp.name}
              class="text-xs px-1.5 py-1 rounded text-red-400 border border-red-900 hover:bg-red-950/40 disabled:text-ink-3 disabled:border-line-2 transition-colors"
            >{deleting === kp.name ? '...' : t('keypairs.delete')}</button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
