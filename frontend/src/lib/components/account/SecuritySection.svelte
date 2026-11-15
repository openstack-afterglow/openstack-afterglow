<script lang="ts">
  import { t } from '$lib/i18n/ns/account';
  import { intlLocale } from '$lib/i18n/runtime.svelte';
  import RichText from '$lib/i18n/RichText.svelte';
  import { auth, clearAuth, logoutInProgress } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import { startLogout } from '$lib/utils/logout';
  import { goto } from '$app/navigation';
  import { onDestroy, onMount } from 'svelte';
  import { cloudShell } from '$lib/stores/cloudShell.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';
  import { t as tc } from '$lib/i18n/ns/common';
  import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
  import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
  import { createTableView } from '$lib/utils/tableView.svelte';
  import { sessionScopeKey } from '$lib/utils/authSession';

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  interface Session {
    jti: string;
    project_id: string;
    auth_method: string;
    origin_ip: string;
    origin_fp: string;
    last_ip: string;
    last_fp: string;
    last_seen: number;
    blacklisted: boolean;
    exp: number;
    device_type: string;
    os: string;
  }

  let sessions = $state<Session[]>([]);
  let loadingSessions = $state(false);
  let revoking = $state(false);
  let error = $state('');
  let success = $state('');
  let showConfirm = $state(false);
  let deletingJti = $state<string | null>(null); // 삭제 확인 대기 중인 jti
  let removingJti = $state<string | null>(null); // API 요청 진행 중인 jti
  const uid = $props.id();
  let search = $state('');
  const view = createTableView<Session>({
    locale: () => intlLocale(),
    rows: () => sessions,
    search: () => search,
    columns: () => [
      { key: 'ip', label: 'IP', value: row => row.origin_ip },
      { key: 'device', label: tc('table.device'), value: row => deviceLabel(row) },
      { key: 'status', label: tc('table.status'), value: row => row.blacklisted ? t('security.blocked') : t('security.active') },
      { key: 'lastUsed', label: tc('table.lastUsed'), value: row => row.last_seen || null, format: value => formatTime(Number(value)) },
      { key: 'lastIp', label: tc('table.recentIp'), value: row => row.last_ip },
    ],
  });
  let viewOwner = '';
  const unsubscribeView = auth.subscribe(state => {
    const next = sessionScopeKey(state);
    if (viewOwner !== next) { viewOwner = next; search = ''; view.reset(); }
  });
  onDestroy(unsubscribeView);

  function deviceLabel(sess: Session): string {
    const os = sess.os && sess.os !== 'unknown' ? sess.os : '';
    const dt = sess.device_type && sess.device_type !== 'unknown' ? sess.device_type : '';
    if (os && dt) return `${os} · ${dt}`;
    if (os) return os;
    if (dt) return dt;
    return t('security.unknown');
  }

  async function loadSessions() {
    if (!token) return;
    loadingSessions = true;
    error = '';
    try {
      const data = await api.get<{ sessions: Session[]; count: number }>(
        '/api/v1/auth/sessions', token, projectId,
      );
      sessions = data.sessions ?? [];
    } catch {
      // best-effort: 세션 목록 실패는 조용히 무시
    } finally {
      loadingSessions = false;
    }
  }

  async function deleteSession(jti: string) {
    deletingJti = null;
    removingJti = jti;
    error = '';
    try {
      await api.delete(`/api/v1/auth/sessions/${jti}`, token, projectId);
      await loadSessions();
      if (sessions.length === 0) {
        await cloudShell.close('logout', { keepDock: false });
        logoutInProgress.set(true);
        clearAuth();
        try {
          await goto('/login', { replaceState: true });
        } finally {
          logoutInProgress.set(false);
        }
      }
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('security.deleteFailed');
    } finally {
      removingJti = null;
    }
  }

  function logoutAll() {
    showConfirm = false;
    if (revoking || $logoutInProgress) return;
    revoking = true;
    void startLogout({ all: true });
  }

  function formatTime(unixTs: number): string {
    if (!unixTs) return '—';
    return new Date(unixTs * 1000).toLocaleString(intlLocale(), {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  onMount(loadSessions);
</script>

{#snippet sessionCount(_text: string)}<AnimatedNumber value={sessions.length} class="text-ink-2 font-medium" />{/snippet}
{#snippet recentIp(text: string)}<span class="font-mono">{text}</span>{/snippet}

<div class="motion-fade bg-surface-base border border-line rounded-xl p-5">
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-sm font-semibold text-ink-0">{t('security.title')}</h2>
    <button
      onclick={loadSessions}
      class="text-xs text-ink-2 hover:text-ink-2 transition-colors"
      disabled={loadingSessions}
    >{#if loadingSessions}<LoadingState variant="control" label={t('security.loading')}  />{:else}{t('security.refresh')}{/if}</button>
  </div>

  {#if error}
    <Alert flat tone="danger" class="mb-3">{error}</Alert>
  {/if}
  {#if success}
    <Alert flat tone="success" class="mb-3">{success}</Alert>
  {/if}

  <!-- 활성 세션 목록 -->
  {#if removingJti}<LoadingState variant="control" label={t('security.deleting')}  />{/if}
  <RegexSearch id={`${uid}-search`} bind:value={search} />
  <TableViewControls {view} class="" />
  {#if sessions.length > 0}
    <div class="mb-4 space-y-2">
      <p class="text-xs text-ink-2 mb-2"><RichText segments={t.rich('security.count', { count: sessions.length })} tags={{ count: sessionCount }} /></p>
      {#if view.rows.length === 0}<p role="status" class="text-sm text-ink-2">{tc('table.noMatches')}</p>{/if}
      {#each view.rows as sess (sess.jti)}
        <div class="border-t border-line py-3 text-xs">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-col gap-0.5 min-w-0">
              <span class="text-ink-2 font-mono truncate">{sess.origin_ip || '—'}</span>
              <span class="text-ink-2">{deviceLabel(sess)}</span>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              {#if sess.blacklisted}
                <span class="text-red-400 text-xs font-semibold uppercase">{t('security.blocked')}</span>
              {:else}
                <span class="text-green-500 text-xs">{t('security.active')}</span>
              {/if}
              {#if deletingJti === sess.jti}
                <div class="flex items-center gap-1">
                  <Button
                    variant="danger" size="xs"
                    onclick={() => deleteSession(sess.jti)}
                    disabled={removingJti === sess.jti}
                  >{t('security.confirm')}</Button>
                  <button
                    onclick={() => { deletingJti = null; }}
                    class="px-2 py-0.5 bg-surface-selected hover:bg-surface-selected text-ink-0 text-xs rounded transition-colors"
                  >{t('security.cancel')}</button>
                </div>
              {:else}
                <button
                  onclick={() => { deletingJti = sess.jti; }}
                  disabled={removingJti !== null}
                  class="px-2 py-0.5 bg-surface-selected hover:bg-red-900/60 border border-line-2 hover:border-red-700/60 text-ink-2 hover:text-red-300 text-xs rounded transition-colors disabled:opacity-40"
                >{t('security.remove')}</button>
              {/if}
            </div>
          </div>
          <div class="text-ink-2 mt-0.5">
            {t('security.lastUsed', { time: formatTime(sess.last_seen) })}
            {#if sess.last_ip && sess.last_ip !== sess.origin_ip}
              <RichText segments={t.rich('security.recentIp', { ip: sess.last_ip })} tags={{ ip: recentIp }} />
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {:else if !loadingSessions}
    <p class="text-xs text-ink-2 mb-4">{t('security.unavailable')}</p>
  {/if}

  <!-- 전체 로그아웃 -->
  <div class="border-t border-line pt-4">
    <p class="text-xs text-ink-2 mb-3">
      {t('security.logoutHelp')}
    </p>
    {#if showConfirm}
      <Alert flat tone="danger" class="mb-3">
        <p class="text-xs mb-2">
          <RichText segments={t.rich('security.logoutConfirm')} />
        </p>
        <div class="flex flex-wrap gap-2">
          <Button
            variant="danger" size="xs"
            onclick={logoutAll}
            disabled={revoking}
          >{#if revoking}<LoadingState variant="control" label={t('security.revoking')}  />{:else}{t('security.confirm')}{/if}</Button>
          <button
            onclick={() => { showConfirm = false; }}
            class="px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-0 text-xs rounded-lg transition-colors"
          >{t('security.cancel')}</button>
        </div>
      </Alert>
    {:else}
      <Button
        variant="danger"
        onclick={() => { showConfirm = true; }}
        disabled={revoking}
      >{t('security.logoutAll')}</Button>
    {/if}
  </div>
</div>
