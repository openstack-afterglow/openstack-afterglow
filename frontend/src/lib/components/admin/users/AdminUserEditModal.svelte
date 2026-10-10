<script lang="ts">
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import type { User } from '$lib/types/common';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import { dialogFocus } from '$lib/utils/dialogFocus';
  import { t } from '$lib/i18n/ns/admin-identity';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import RichText from '$lib/i18n/RichText.svelte';

  let {
    user = $bindable<User | null>(),
    onUpdate,
  }: {
    user: User | null;
    onUpdate: (id: string, form: { name: string; email: string; password: string; enabled: boolean }) => Promise<string | true>;
  } = $props();

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  interface AdminSession {
    jti: string;
    origin_ip: string;
    last_ip: string;
    last_seen: number;
    blacklisted: boolean;
    device_type: string;
    os: string;
    auth_method: string;
    exp: number;
  }

  let name = $state('');
  let email = $state('');
  let password = $state('');
  let enabled = $state(true);
  let updating = $state(false);
  let revoking = $state(false);
  let error = $state('');
  let revokeSuccess = $state('');
  let showRevokeConfirm = $state(false);
  let sessions = $state<AdminSession[]>([]);
  let loadingSessions = $state(false);

  function formatSessionTime(unixTs: number): string {
    if (!unixTs) return '—';
    return new Date(unixTs * 1000).toLocaleString(intlLocale(), {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  function deviceLabel(sess: AdminSession): string {
    const os = sess.os && sess.os !== 'unknown' ? sess.os : '';
    const dt = sess.device_type && sess.device_type !== 'unknown' ? sess.device_type : '';
    if (os && dt) return `${os} · ${dt}`;
    if (os) return os;
    if (dt) return dt;
    return t('userEdit.unknownDevice');
  }

  async function loadUserSessions(userId: string) {
    loadingSessions = true;
    try {
      const data = await api.get<{ sessions: AdminSession[]; count: number }>(
        `/api/v1/admin/users/${userId}/sessions`, token, projectId,
      );
      sessions = data.sessions ?? [];
    } catch {
      sessions = [];
    } finally {
      loadingSessions = false;
    }
  }

  $effect(() => {
    if (user) {
      name = user.name;
      email = user.email;
      enabled = user.enabled;
      password = '';
      error = '';
      revokeSuccess = '';
      showRevokeConfirm = false;
      updating = false;
      revoking = false;
      sessions = [];
      loadUserSessions(user.id);
    }
  });

  async function submit() {
    if (!user) return;
    updating = true;
    error = '';
    const result = await onUpdate(user.id, { name, email, password, enabled });
    updating = false;
    if (result === true) {
      user = null;
    } else {
      error = result;
    }
  }

  async function revokeAllSessions() {
    if (!user) return;
    showRevokeConfirm = false;
    revoking = true;
    error = '';
    revokeSuccess = '';
    try {
      const res = await api.post<{ revoked_count: number }>(
        `/api/v1/admin/users/${user.id}/revoke-sessions`, {}, token, projectId,
      );
      revokeSuccess = t('userEdit.sessionsRevoked', { count: res.revoked_count });
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('userEdit.revokeFailed');
    } finally {
      revoking = false;
    }
  }
</script>

{#snippet passwordHint(text: string)}<span class="text-ink-2">{text}</span>{/snippet}

{#if user}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    use:dialogFocus={{ enabled: true, onEscape: () => (user = null) }}
    class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={(event) => { if (event.target === event.currentTarget) (() => { user = null; })(); }}
    role="dialog" aria-modal="true"
    tabindex="-1"
  >
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
      <h2 class="text-lg font-semibold text-ink-0 mb-5">{t('userEdit.title')}</h2>
      {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
      {#if revokeSuccess}<div class="bg-green-900/40 border border-green-700 text-green-300 rounded-lg px-4 py-3 text-sm mb-4">{revokeSuccess}</div>{/if}
      <div class="space-y-4">
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusereditmodal-132">{t('userEdit.name')}</label><input id="field-adminusereditmodal-132" bind:value={name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusereditmodal-133">{t('userEdit.email')}</label><input id="field-adminusereditmodal-133" bind:value={email} type="email" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusereditmodal-134"><RichText segments={t.rich('userEdit.passwordLabel')} tags={{ hint: passwordHint }} /></label><input id="field-adminusereditmodal-134" bind:value={password} type="password" placeholder={t('userEdit.passwordPlaceholder')} class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div class="flex items-center gap-3">
          <button type="button" role="switch" aria-label={t('userEdit.enabledLabel')} aria-checked={enabled} onclick={() => enabled = !enabled} class="relative w-11 h-6 rounded-full transition-colors {enabled ? 'bg-action-warm' : 'bg-surface-selected'}">
            <span class="absolute top-0.5 left-0.5 w-5 h-5 bg-surface-base rounded-full transition-transform {enabled ? 'translate-x-5' : ''}"></span>
          </button>
          <span class="text-sm text-ink-2">{enabled ? t('userEdit.enabled') : t('userEdit.disabled')}</span>
        </div>
        <div class="text-xs text-ink-2">{t('userEdit.userId', { id: user.id })}</div>
      </div>

      <!-- 활성 세션 목록 -->
      <div class="mt-5 pt-4 border-t border-line">
        <div class="flex items-center justify-between mb-2">
          <p class="text-xs font-medium text-ink-2">{t('userEdit.sessionsTitle')}</p>
          {#if loadingSessions}
            <span class="text-xs text-ink-2"><ActivityIndicator size="xs" label={t('userEdit.loading')} /></span>
          {:else}
            <span class="text-xs text-ink-2">{t('userEdit.sessionCount', { count: sessions.length })}</span>
          {/if}
        </div>
        {#if sessions.length > 0}
          <div class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-line-2 text-ink-2 uppercase tracking-wide text-xs">
                  <th class="text-left py-1 pr-3">{t('userEdit.originIp')}</th>
                  <th class="text-left py-1 pr-3">{t('userEdit.device')}</th>
                  <th class="text-left py-1 pr-3">{t('userEdit.lastUsed')}</th>
                  <th class="text-left py-1">{t('userEdit.status')}</th>
                </tr>
              </thead>
              <tbody>
                {#each sessions as sess (sess.jti)}
                  <tr class="border-b border-line/50">
                    <td class="py-1.5 pr-3 font-mono text-ink-2">{sess.origin_ip || '—'}</td>
                    <td class="py-1.5 pr-3 text-ink-2">{deviceLabel(sess)}</td>
                    <td class="py-1.5 pr-3 text-ink-2">{formatSessionTime(sess.last_seen)}</td>
                    <td class="py-1.5">
                      {#if sess.blacklisted}
                        <span class="text-red-400 font-semibold">{t('userEdit.blocked')}</span>
                      {:else}
                        <span class="text-green-500">{t('userEdit.enabled')}</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else if !loadingSessions}
          <p class="text-xs text-ink-2">{t('userEdit.noSessions')}</p>
        {/if}
      </div>

      <!-- 세션 강제 폐기 -->
      <div class="mt-3 pt-3 border-t border-line">
        {#if showRevokeConfirm}
          <div class="bg-red-950/40 border border-red-800/60 rounded-lg px-3 py-3 mb-3">
            <p class="text-xs text-red-300 mb-2"><RichText segments={t.rich('userEdit.revokeConfirm')} /></p>
            <div class="flex gap-2">
              <button
                onclick={revokeAllSessions}
                disabled={revoking}
                class="px-3 py-1.5 bg-[var(--color-state-danger)]/10 hover:bg-[var(--color-state-danger)]/20 disabled:opacity-50 text-[var(--color-state-danger-text)] text-xs rounded-lg transition-colors"
              >{revoking ? t('userEdit.revoking') : t('userEdit.confirm')}</button>
              <button
                onclick={() => { showRevokeConfirm = false; }}
                class="px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-0 text-xs rounded-lg transition-colors"
              >{t('userEdit.cancel')}</button>
            </div>
          </div>
        {:else}
          <button aria-busy={revoking}
            onclick={() => { showRevokeConfirm = true; }}
            disabled={revoking}
            class="w-full px-3 py-2 bg-[var(--color-state-danger)]/10 hover:bg-[var(--color-state-danger)]/20 border border-[var(--color-state-danger)]/30 text-[var(--color-state-danger-text)] text-xs rounded-lg transition-colors disabled:opacity-50"
          >{#if revoking}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('userEdit.revoking')}</span>{:else}{t('userEdit.revokeAll')}{/if}</button>
        {/if}
      </div>

      <div class="flex justify-end gap-3 mt-4">
        <button onclick={() => { user = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">{t('userEdit.cancel')}</button>
        <button aria-busy={updating} onclick={submit} disabled={updating} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{#if updating}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('userEdit.updating')}</span>{:else}{t('userEdit.update')}{/if}</button>
      </div>
    </div>
  </div>
{/if}
