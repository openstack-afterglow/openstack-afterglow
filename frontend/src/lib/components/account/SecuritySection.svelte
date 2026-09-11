<script lang="ts">
  import { auth, clearAuth, logoutInProgress } from '$lib/stores/auth';
  import { api, ApiError, beginSessionRevocation, endSessionRevocation } from '$lib/api/client';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

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

  function deviceLabel(sess: Session): string {
    const os = sess.os && sess.os !== 'unknown' ? sess.os : '';
    const dt = sess.device_type && sess.device_type !== 'unknown' ? sess.device_type : '';
    if (os && dt) return `${os} · ${dt}`;
    if (os) return os;
    if (dt) return dt;
    return '알 수 없음';
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
        logoutInProgress.set(true);
        clearAuth();
        try {
          await goto('/login', { replaceState: true });
        } finally {
          logoutInProgress.set(false);
        }
      }
    } catch (e) {
      error = e instanceof ApiError ? e.message : '세션 삭제 실패';
    } finally {
      removingJti = null;
    }
  }

  async function logoutAll() {
    showConfirm = false;
    revoking = true;
    error = '';
    success = '';
    logoutInProgress.set(true);
    try {
      const pendingRefresh = beginSessionRevocation();
      await pendingRefresh;
      const logoutToken = $auth.token;
      await api.post('/api/v1/auth/logout-all', {}, logoutToken ?? undefined, projectId);
      success = '모든 세션이 폐기되었습니다. 다시 로그인해 주세요.';
      clearAuth();
      setTimeout(() => {
        void goto('/login', { replaceState: true }).finally(() => logoutInProgress.set(false));
      }, 1500);
    } catch (e) {
      error = e instanceof ApiError ? e.message : '세션 폐기 실패';
      logoutInProgress.set(false);
      revoking = false;
    } finally {
      endSessionRevocation();
    }
  }

  function formatTime(unixTs: number): string {
    if (!unixTs) return '—';
    return new Date(unixTs * 1000).toLocaleString('ko-KR', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  onMount(loadSessions);
</script>

<div class="bg-surface-base border border-line rounded-xl p-5">
  <div class="flex items-center justify-between mb-4">
    <h3 class="text-sm font-semibold text-ink-0">세션 보안</h3>
    <button
      onclick={loadSessions}
      class="text-xs text-ink-3 hover:text-ink-2 transition-colors"
      disabled={loadingSessions}
    >{loadingSessions ? '로딩...' : '새로고침'}</button>
  </div>

  {#if error}
    <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-3 py-2 text-xs mb-3">{error}</div>
  {/if}
  {#if success}
    <div class="bg-green-900/40 border border-green-700 text-green-300 rounded-lg px-3 py-2 text-xs mb-3">{success}</div>
  {/if}

  <!-- 활성 세션 목록 -->
  {#if sessions.length > 0}
    <div class="mb-4 space-y-2">
      <p class="text-xs text-ink-3 mb-2">활성 세션 <span class="text-ink-2 font-medium">{sessions.length}</span>개</p>
      {#each sessions as sess (sess.jti)}
        <div class="bg-surface-sunken/60 rounded-lg px-3 py-2 text-xs {sess.blacklisted ? 'border border-red-800/60' : 'border border-line-2/40'}">
          <div class="flex items-center justify-between gap-2">
            <div class="flex flex-col gap-0.5 min-w-0">
              <span class="text-ink-2 font-mono truncate">{sess.origin_ip || '—'}</span>
              <span class="text-ink-3">{deviceLabel(sess)}</span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              {#if sess.blacklisted}
                <span class="text-red-400 text-[10px] font-semibold uppercase">차단됨</span>
              {:else}
                <span class="text-green-500 text-[10px]">활성</span>
              {/if}
              {#if deletingJti === sess.jti}
                <div class="flex items-center gap-1">
                  <button
                    onclick={() => deleteSession(sess.jti)}
                    disabled={removingJti === sess.jti}
                    class="px-2 py-0.5 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-ink-0 text-[10px] rounded transition-colors"
                  >{removingJti === sess.jti ? '삭제 중...' : '확인'}</button>
                  <button
                    onclick={() => { deletingJti = null; }}
                    class="px-2 py-0.5 bg-surface-selected hover:bg-surface-selected text-ink-0 text-[10px] rounded transition-colors"
                  >취소</button>
                </div>
              {:else}
                <button
                  onclick={() => { deletingJti = sess.jti; }}
                  disabled={removingJti !== null}
                  class="px-2 py-0.5 bg-surface-selected hover:bg-red-900/60 border border-line-2 hover:border-red-700/60 text-ink-2 hover:text-red-300 text-[10px] rounded transition-colors disabled:opacity-40"
                >제거</button>
              {/if}
            </div>
          </div>
          <div class="text-ink-3 mt-0.5">
            마지막 사용: {formatTime(sess.last_seen)}
            {#if sess.last_ip && sess.last_ip !== sess.origin_ip}
              · 최근 IP: <span class="font-mono">{sess.last_ip}</span>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {:else if !loadingSessions}
    <p class="text-xs text-ink-3 mb-4">활성 세션 정보를 불러올 수 없습니다.</p>
  {/if}

  <!-- 전체 로그아웃 -->
  <div class="border-t border-line pt-4">
    <p class="text-xs text-ink-3 mb-3">
      모든 기기에서 로그아웃합니다. Keystone 토큰도 즉시 폐기됩니다.
    </p>
    {#if showConfirm}
      <div class="bg-red-950/40 border border-red-800/60 rounded-lg px-3 py-3 mb-3">
        <p class="text-xs text-red-300 mb-2">
          정말 모든 위치에서 로그아웃하시겠습니까?<br>현재 세션도 종료됩니다.
        </p>
        <div class="flex gap-2">
          <button
            onclick={logoutAll}
            disabled={revoking}
            class="px-3 py-1.5 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-ink-0 text-xs rounded-lg transition-colors"
          >{revoking ? '폐기 중...' : '확인'}</button>
          <button
            onclick={() => { showConfirm = false; }}
            class="px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-0 text-xs rounded-lg transition-colors"
          >취소</button>
        </div>
      </div>
    {:else}
      <button
        onclick={() => { showConfirm = true; }}
        disabled={revoking}
        class="px-4 py-2 bg-red-700/80 hover:bg-red-600 disabled:opacity-50 text-ink-0 text-sm rounded-lg transition-colors"
      >모든 위치에서 로그아웃</button>
    {/if}
  </div>
</div>
