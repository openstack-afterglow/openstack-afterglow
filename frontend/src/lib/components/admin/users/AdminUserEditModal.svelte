<script lang="ts">
  import { untrack } from 'svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Pill from '$lib/components/ui/Pill.svelte';
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

  interface UserPermission {
    scope_type: 'project' | 'domain' | 'system';
    scope_id: string;
    scope_name: string;
    roles: Array<{ id: string; name: string }>;
  }

  interface UserScope {
    userId: string;
    token: string | undefined;
    projectId: string | undefined;
  }

  const scopeLabels = {
    project: 'userEdit.projectScope',
    domain: 'userEdit.domainScope',
    system: 'userEdit.systemScope',
  } as const;

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
  let sessionsError = $state('');
  let permissions = $state<UserPermission[]>([]);
  let permissionsStatus = $state<'loading' | 'ready' | 'error'>('loading');
  let permissionsError = $state('');
  let scope: UserScope | null = null;

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

  function current(requestScope: UserScope): boolean {
    return scope === requestScope && user?.id === requestScope.userId
      && token === requestScope.token && projectId === requestScope.projectId;
  }

  async function loadUserSessions(requestScope: UserScope) {
    if (!current(requestScope)) return;
    loadingSessions = true;
    sessionsError = '';
    sessions = [];
    try {
      const data = await api.get<{ sessions: AdminSession[]; count: number }>(
        `/api/v1/admin/users/${encodeURIComponent(requestScope.userId)}/sessions`,
        requestScope.token, requestScope.projectId,
      );
      if (current(requestScope)) sessions = data.sessions;
    } catch {
      if (current(requestScope)) sessionsError = t('userEdit.sessionsFailed');
    } finally {
      if (current(requestScope)) loadingSessions = false;
    }
  }

  async function loadUserPermissions(requestScope: UserScope) {
    if (!current(requestScope)) return;
    permissionsStatus = 'loading';
    permissionsError = '';
    permissions = [];
    try {
      const data = await api.get<{ items: UserPermission[]; count: number }>(
        `/api/v1/admin/users/${encodeURIComponent(requestScope.userId)}/permissions`,
        requestScope.token, requestScope.projectId,
      );
      if (!current(requestScope)) return;
      permissions = data.items;
      permissionsStatus = 'ready';
    } catch (e) {
      if (!current(requestScope)) return;
      permissionsError = e instanceof ApiError && (e.status === 401 || e.status === 403)
        ? t('userEdit.permissionsUnauthorized') : t('userEdit.permissionsFailed');
      permissionsStatus = 'error';
    }
  }

  $effect(() => {
    const selectedId = user?.id;
    const selectedName = user?.name ?? '';
    const selectedEmail = user?.email ?? '';
    const selectedEnabled = user?.enabled ?? true;
    const accessToken = token;
    const callerProject = projectId;
    untrack(() => {
      scope = selectedId ? { userId: selectedId, token: accessToken, projectId: callerProject } : null;
      name = selectedName;
      email = selectedEmail;
      enabled = selectedEnabled;
      password = '';
      error = '';
      revokeSuccess = '';
      showRevokeConfirm = false;
      updating = false;
      revoking = false;
      sessions = [];
      sessionsError = '';
      loadingSessions = false;
      permissions = [];
      permissionsError = '';
      permissionsStatus = 'loading';
      if (scope) {
        void loadUserSessions(scope);
        void loadUserPermissions(scope);
      }
    });
    return () => { scope = null; };
  });

  async function submit() {
    if (!scope || !current(scope) || updating) return;
    const requestScope = scope;
    updating = true;
    error = '';
    const result = await onUpdate(requestScope.userId, { name, email, password, enabled });
    if (!current(requestScope)) return;
    updating = false;
    if (result === true) {
      user = null;
    } else {
      error = result;
    }
  }

  async function revokeAllSessions() {
    if (!scope || !current(scope) || revoking) return;
    const requestScope = scope;
    showRevokeConfirm = false;
    revoking = true;
    error = '';
    revokeSuccess = '';
    try {
      const res = await api.post<{ revoked_count: number }>(
        `/api/v1/admin/users/${encodeURIComponent(requestScope.userId)}/revoke-sessions`, {}, requestScope.token, requestScope.projectId,
      );
      if (!current(requestScope)) return;
      revokeSuccess = t('userEdit.sessionsRevoked', { count: res.revoked_count });
    } catch (e) {
      if (current(requestScope)) error = e instanceof ApiError ? e.message : t('userEdit.revokeFailed');
    } finally {
      if (current(requestScope)) revoking = false;
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
    role="dialog" aria-modal="true" aria-labelledby="admin-user-edit-title"
    tabindex="-1"
  >
    <div data-testid="admin-user-edit-panel" class="bg-surface-base border border-line-2 rounded-xl p-4 md:p-6 w-full min-w-0 max-w-xl lg:max-w-5xl max-h-[calc(100dvh-2rem)] overflow-y-auto mx-4 shadow-[var(--shadow-restraint)]">
      <h2 id="admin-user-edit-title" class="text-lg font-semibold text-ink-0 mb-5">{t('userEdit.title')}</h2>
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
        <div class="text-xs text-ink-2 [overflow-wrap:anywhere]">{t('userEdit.userId', { id: user.id })}</div>
      </div>

      <div data-testid="admin-user-access-grid" class="mt-5 pt-4 border-t border-line grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section aria-labelledby="admin-user-permissions-title" aria-busy={permissionsStatus === 'loading'} class="min-w-0">
          <h3 id="admin-user-permissions-title" class="text-sm font-medium text-ink-0 mb-2">{t('userEdit.permissionsTitle')}</h3>
          <p class="text-xs text-ink-2 mb-3">{t('userEdit.permissionsHelp')}</p>
          {#if permissionsStatus === 'loading'}
            <ActivityIndicator size="xs" label={t('userEdit.permissionsLoading')} />
          {:else if permissionsStatus === 'error'}
            <Alert>{permissionsError}</Alert>
            <Button variant="secondary" size="sm" class="mt-2" onclick={() => { if (scope) void loadUserPermissions(scope); }}>{t('userEdit.retryPermissions')}</Button>
          {:else if permissions.length === 0}
            <p class="text-xs text-ink-2">{t('userEdit.noPermissions')}</p>
          {:else}
            <ul class="space-y-3">
              {#each permissions as permission (`${permission.scope_type}:${permission.scope_id}`)}
                <li class="bg-surface-sunken border border-line rounded-lg p-3 min-w-0">
                  <p class="text-xs text-ink-2">{t(scopeLabels[permission.scope_type])}</p>
                  <p class="text-sm font-medium text-ink-0 [overflow-wrap:anywhere]">{permission.scope_name}</p>
                  <p class="text-xs font-mono text-ink-2 mt-1 [overflow-wrap:anywhere]">{t('userEdit.scopeId', { id: permission.scope_id })}</p>
                  <ul aria-label={t('userEdit.rolesLabel', { name: permission.scope_name })} class="flex flex-wrap gap-1.5 mt-2">
                    {#each permission.roles as role (role.id)}
                      <li class="min-w-0 max-w-full"><Pill class="max-w-full"><span class="min-w-0 text-xs whitespace-normal [overflow-wrap:anywhere]">{role.name}</span></Pill></li>
                    {/each}
                  </ul>
                </li>
              {/each}
            </ul>
          {/if}
        </section>

        <section aria-labelledby="admin-user-sessions-title" aria-busy={loadingSessions} class="min-w-0">
          <div class="flex items-center justify-between gap-2 mb-2">
            <h3 id="admin-user-sessions-title" class="text-sm font-medium text-ink-0">{t('userEdit.sessionsTitle')}</h3>
            {#if !loadingSessions && !sessionsError}
              <span class="text-xs text-ink-2">{t('userEdit.sessionCount', { count: sessions.length })}</span>
            {/if}
          </div>
          {#if loadingSessions}
            <ActivityIndicator size="xs" label={t('userEdit.loading')} />
          {:else if sessionsError}
            <Alert>{sessionsError}</Alert>
            <Button variant="secondary" size="sm" class="mt-2" onclick={() => { if (scope) void loadUserSessions(scope); }}>{t('userEdit.retrySessions')}</Button>
          {:else if sessions.length > 0}
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
                          <span class="text-[var(--color-state-danger-text)] font-semibold">{t('userEdit.blocked')}</span>
                        {:else}
                          <span class="text-[var(--color-state-success-text)]">{t('userEdit.enabled')}</span>
                        {/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="text-xs text-ink-2">{t('userEdit.noSessions')}</p>
          {/if}
        </section>
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
