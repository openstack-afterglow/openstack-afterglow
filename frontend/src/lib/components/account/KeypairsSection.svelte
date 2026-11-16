<script lang="ts">
  import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
  import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Pill from '$lib/components/ui/Pill.svelte';
  import { t } from '$lib/i18n/ns/account';
  import { t as tc } from '$lib/i18n/ns/common';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import { confirmDialog } from '$lib/stores/confirm.svelte';
  import { toast } from '$lib/stores/toast';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import TableColumnControl from '$lib/components/ui/TableColumnControl.svelte';
  import { createTableView } from '$lib/utils/tableView.svelte';
  import { sessionScopeKey } from '$lib/utils/authSession';
  import { rowChanged, rowEnter, rowExit, rowReflow } from '$lib/utils/rowMotion';

  interface Keypair {
    name: string;
    fingerprint: string;
    type: string;
    public_key?: string;
    private_key?: string;
  }


  let keypairs = $state<Keypair[]>([]);
  let loading = $state(true);
  let error = $state('');
  let deleting = $state<string | null>(null);
  let copiedFingerprint = $state<string | null>(null);
  let defaultKey = $state<string | null>(null);
  let preferenceLoaded = $state(false);
  let savingDefault = $state(false);
  let preferenceError = $state('');
  let epoch = 0;
  let mounted = false;
  let showModal = $state(false);
  let creating = $state(false);
  let createError = $state('');
  let createdPrivateKey = $state<string | null>(null);
  let form = $state({ name: '', public_key: '' });
  const uid = $props.id();
  let search = $state('');
  const view = createTableView<Keypair>({
    locale: () => intlLocale(),
    rows: () => keypairs,
    search: () => search,
    columns: () => [
      { key: 'name', label: t('keypairs.name'), value: row => row.name },
      { key: 'fingerprint', label: tc('table.fingerprint'), value: row => row.fingerprint },
      { key: 'type', label: t('keypairs.type'), value: row => row.type },
    ],
  });
  function capture() {
    const state = get(auth), ticket = epoch;
    if (!mounted || !state.token || !state.projectId || !get(authReady) || get(logoutInProgress) || get(projectSwitching)) return null;
    return { token: state.token, projectId: state.projectId,
      current: () => mounted && ticket === epoch };
  }

  async function fetchKeypairs() {
    const owner = capture(); if (!owner) return;
    await Promise.all([
      (async () => {
        try {
          const rows = await api.get<Keypair[]>('/api/v1/keypairs', owner.token, owner.projectId);
          if (owner.current()) { keypairs = rows; error = ''; }
        } catch (e) {
          if (owner.current()) error = e instanceof ApiError ? e.message : t('keypairs.loadFailed');
        } finally { if (owner.current()) loading = false; }
      })(),
      (async () => {
        try {
          const result = await api.get<{ keypair_name: string | null }>('/api/v1/profile/ssh-key-preference', owner.token, owner.projectId, { cache: 'no-store' });
          if (owner.current()) { defaultKey = result.keypair_name; preferenceLoaded = true; preferenceError = ''; }
        } catch {
          if (owner.current()) { preferenceLoaded = false; preferenceError = t('keypairs.defaultFailed'); }
        }
      })(),
    ]);
  }

  async function setDefault(name: string | null) {
    if (!preferenceLoaded || savingDefault || deleting) return;
    const owner = capture(); if (!owner) return;
    savingDefault = true; preferenceError = '';
    try {
      const result = await api.put<{ keypair_name: string | null }>('/api/v1/profile/ssh-key-preference', { keypair_name: name }, owner.token, owner.projectId, { cache: 'no-store', replayOnUnauthorized: false });
      if (owner.current()) defaultKey = result.keypair_name;
    } catch {
      if (owner.current()) { preferenceLoaded = false; preferenceError = t('keypairs.defaultFailed'); }
    } finally { if (owner.current()) savingDefault = false; }
  }

  async function createKeypair() {
    if (!form.name.trim()) return;
    const owner = capture(); if (!owner) return;
    creating = true;
    createError = '';
    try {
      const result = await api.post<Keypair>('/api/v1/keypairs', {
        name: form.name,
        public_key: form.public_key.trim() || null,
      }, owner.token, owner.projectId);
      if (!owner.current()) return;
      if (result.private_key) {
        createdPrivateKey = result.private_key;
      } else {
        showModal = false;
      }
      form = { name: '', public_key: '' };
      await fetchKeypairs();
    } catch (e) {
      if (owner.current()) createError = e instanceof ApiError ? e.message : t('keypairs.createFailed');
    } finally {
      if (owner.current()) creating = false;
    }
  }

  async function deleteKeypair(name: string) {
    const owner = capture(); if (!owner || savingDefault || deleting) return;
    if (!(await confirmDialog(t('keypairs.deleteConfirm', { name }))) || !owner.current()) return;
    deleting = name;
    try {
      await api.delete(`/api/v1/keypairs/${encodeURIComponent(name)}`, owner.token, owner.projectId);
      if (!owner.current()) return;
      if (defaultKey === name) defaultKey = null;
      await fetchKeypairs();
    } catch (e) {
      if (owner.current()) toast.error(t('keypairs.deleteFailed', { error: e instanceof ApiError ? e.message : String(e) }));
    } finally {
      if (owner.current()) deleting = null;
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

  onMount(() => {
    mounted = true; let previous = '';
    const changed = () => {
      const next = JSON.stringify([sessionScopeKey(get(auth)), get(authReady), get(logoutInProgress), get(projectSwitching)]);
      if (previous === next) return;
      previous = next; epoch++;
      keypairs = []; defaultKey = null; preferenceLoaded = false; savingDefault = false;
      preferenceError = ''; error = ''; deleting = null; loading = true;
      showModal = false; creating = false; createError = ''; createdPrivateKey = null;
      form = { name: '', public_key: '' };
      search = ''; view.reset();
      void fetchKeypairs();
    };
    const stops = [auth.subscribe(changed), authReady.subscribe(changed), logoutInProgress.subscribe(changed), projectSwitching.subscribe(changed)];
    return () => { mounted = false; epoch++; stops.forEach(stop => stop()); };
  });
</script>

{#if showModal}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
		use:dialogFocus={{ enabled: true, onEscape: () => (showModal = false) }} class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50" onclick={() => showModal = false} role="dialog" aria-modal="true" tabindex="-1">
    <div class="motion-pop bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]" onclick={(e) => e.stopPropagation()} role="none">
      {#if createdPrivateKey}
        <h2 class="text-lg font-semibold text-ink-0 mb-3">{t('keypairs.privateKey')}</h2>
        <p class="text-sm text-yellow-300 mb-3">{t('keypairs.privateWarning')}</p>
        <pre class="bg-surface-sunken rounded p-3 text-xs text-green-300 overflow-auto max-h-48 mb-4">{createdPrivateKey}</pre>
        <button onclick={() => { createdPrivateKey = null; showModal = false; }} class="w-full px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors">{t('keypairs.confirm')}</button>
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
          <button onclick={createKeypair} disabled={creating} class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-surface-selected disabled:text-ink-3 text-action-on-warm text-sm font-medium rounded-lg transition-colors">{#if creating}<LoadingState variant="control" label={t('keypairs.creating')}  />{:else}{t('keypairs.createAction')}{/if}</button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<div class="motion-fade bg-surface-base border border-line rounded-xl p-5">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-sm font-semibold text-ink-0">{t('keypairs.title')}</h2>
    <button onclick={() => showModal = true} class="text-xs px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-0 rounded-lg transition-colors">{t('keypairs.add')}</button>
  </div>

  {#if error}
    <div class="text-red-400 text-xs mb-3">{error}</div>
  {/if}
  <p class="mb-3 text-sm text-ink-2">{t('keypairs.defaultHelp')}</p>
  {#if preferenceError}
    <div role="alert" class="mb-3 text-sm text-state-danger-text">{preferenceError} <Button variant="secondary" size="sm" onclick={fetchKeypairs}>{t('keypairs.defaultReload')}</Button></div>
  {/if}
  <RegexSearch id={`${uid}-search`} bind:value={search} />
  <TableViewControls {view} />

  {#if loading}
    <LoadingState variant="section" label={tc('state.loading')}  />
  {:else}
    {#if keypairs.length === 0}<div class="text-ink-2 text-xs text-center py-6">{t('keypairs.empty')}</div>
    {:else if view.rows.length === 0}<p role="status" class="py-4 text-sm text-ink-2">{tc('table.noMatches')}</p>{/if}
    <ResponsiveTable embedded>{#snippet cards()}{#each view.rows as kp (kp.name)}<CompactResourceCard>
      <div class="flex flex-wrap justify-between gap-2"><h3 class="text-sm font-medium">{kp.name}</h3>{#if defaultKey === kp.name}<Pill tone="neutral" size="xs">{t('keypairs.default')}</Pill>{/if}<Pill tone="neutral" size="xs" class="font-mono">{kp.type}</Pill></div>
      {#snippet details()}<code class="text-xs break-all">{kp.fingerprint}</code>{/snippet}
      {#snippet actions()}<Button variant="secondary" size="sm" disabled={!preferenceLoaded || savingDefault || !!deleting} ariaBusy={savingDefault} onclick={() => setDefault(defaultKey === kp.name ? null : kp.name)}>{defaultKey === kp.name ? t('keypairs.clearDefault') : t('keypairs.setDefault')}</Button><Button variant="secondary" size="sm" onclick={() => copyFingerprint(kp.fingerprint)}>{copiedFingerprint === kp.fingerprint ? t('keypairs.copied') : t('keypairs.copy')}</Button><Button variant="danger-outline" size="sm" onclick={() => deleteKeypair(kp.name)} disabled={!!deleting || savingDefault} ariaBusy={deleting === kp.name}>{t('keypairs.delete')}</Button>{/snippet}
    </CompactResourceCard>{/each}{/snippet}
    <div class="border-y border-line overflow-hidden">
      <div class="grid grid-cols-[1fr_100px_160px] px-3 py-2 border-b border-line text-xs uppercase tracking-wider text-ink-2">
        <div class="flex flex-wrap gap-2"><TableColumnControl {view} columnKey="name" /><TableColumnControl {view} columnKey="fingerprint" /></div>
        <div><TableColumnControl {view} columnKey="type" /></div>
        <div class="text-right">{t('keypairs.actions')}</div>
      </div>
      {#each view.rows as kp, i (kp.name)}
        <div class="grid grid-cols-[1fr_100px_160px] px-3 py-2.5 text-xs items-center {i < view.rows.length - 1 ? 'border-b border-line' : ''} hover:bg-surface-sunken/30 transition-colors" in:rowEnter out:rowExit animate:rowReflow use:rowChanged={kp}>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2 text-ink-0 font-medium"><span class="truncate">{kp.name}</span>{#if defaultKey === kp.name}<Pill tone="neutral" size="xs">{t('keypairs.default')}</Pill>{/if}</div>
            <div class="text-xs text-ink-2 font-mono truncate mt-0.5">{kp.fingerprint}</div>
          </div>
          <div>
            <Pill tone="neutral" size="xs" class="font-mono">{kp.type}</Pill>
          </div>
          <div class="flex flex-wrap gap-1 justify-end">
            <Button variant="secondary" size="sm" disabled={!preferenceLoaded || savingDefault || !!deleting} ariaBusy={savingDefault} onclick={() => setDefault(defaultKey === kp.name ? null : kp.name)}>{defaultKey === kp.name ? t('keypairs.clearDefault') : t('keypairs.setDefault')}</Button>
            <button
              onclick={() => copyFingerprint(kp.fingerprint)}
              class="text-xs px-1.5 py-1 rounded bg-surface-sunken hover:bg-surface-selected text-ink-2 border border-line-2 transition-colors"
            >{copiedFingerprint === kp.fingerprint ? t('keypairs.copied') : t('keypairs.copy')}</button>
            <button
              onclick={() => deleteKeypair(kp.name)}
              disabled={!!deleting || savingDefault}
              class="text-xs px-1.5 py-1 rounded text-state-danger-text border border-line-2 hover:bg-surface-selected disabled:text-ink-3 transition-colors"
            >{#if deleting === kp.name}<LoadingState variant="control" label={tc('state.processing')}  />{:else}{t('keypairs.delete')}{/if}</button>
          </div>
        </div>
      {/each}
    </div>
    </ResponsiveTable>
  {/if}
</div>
