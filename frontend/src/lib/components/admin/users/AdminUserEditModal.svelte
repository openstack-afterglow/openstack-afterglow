<script lang="ts">
  import type { User } from '$lib/types/common';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';

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
    return new Date(unixTs * 1000).toLocaleString('ko-KR', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  function deviceLabel(sess: AdminSession): string {
    const os = sess.os && sess.os !== 'unknown' ? sess.os : '';
    const dt = sess.device_type && sess.device_type !== 'unknown' ? sess.device_type : '';
    if (os && dt) return `${os} · ${dt}`;
    if (os) return os;
    if (dt) return dt;
    return '알 수 없음';
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
      revokeSuccess = `세션 ${res.revoked_count}개가 폐기되었습니다.`;
    } catch (e) {
      error = e instanceof ApiError ? e.message : '세션 폐기 실패';
    } finally {
      revoking = false;
    }
  }
</script>

{#if user}
  <div
    class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
    onclick={(event) => { if (event.target === event.currentTarget) (() => { user = null; })(); }}
    role="dialog"
    onkeydown={(e) => e.key === 'Escape' && (user = null)}
    tabindex="-1"
  >
    <div class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
      <h2 class="text-lg font-semibold text-ink-0 mb-5">사용자 수정</h2>
      {#if error}<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">{error}</div>{/if}
      {#if revokeSuccess}<div class="bg-green-900/40 border border-green-700 text-green-300 rounded-lg px-4 py-3 text-sm mb-4">{revokeSuccess}</div>{/if}
      <div class="space-y-4">
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusereditmodal-132">이름</label><input id="field-adminusereditmodal-132" bind:value={name} type="text" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusereditmodal-133">이메일</label><input id="field-adminusereditmodal-133" bind:value={email} type="email" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div><label class="block text-xs text-ink-2 mb-1.5 uppercase tracking-wide" for="field-adminusereditmodal-134">새 패스워드 <span class="text-ink-3">(변경 시에만 입력)</span></label><input id="field-adminusereditmodal-134" bind:value={password} type="password" placeholder="변경하지 않으면 비워두세요" class="w-full bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-ink-0 text-sm focus:outline-none focus:border-action-warm" /></div>
        <div class="flex items-center gap-3">
          <button type="button" role="switch" aria-label="사용자 활성 상태" aria-checked={enabled} onclick={() => enabled = !enabled} class="relative w-11 h-6 rounded-full transition-colors {enabled ? 'bg-action-warm' : 'bg-surface-selected'}">
            <span class="absolute top-0.5 left-0.5 w-5 h-5 bg-surface-base rounded-full transition-transform {enabled ? 'translate-x-5' : ''}"></span>
          </button>
          <span class="text-sm text-ink-2">{enabled ? '활성' : '비활성'}</span>
        </div>
        <div class="text-xs text-ink-3">ID: {user.id}</div>
      </div>

      <!-- 활성 세션 목록 -->
      <div class="mt-5 pt-4 border-t border-line">
        <div class="flex items-center justify-between mb-2">
          <p class="text-xs font-medium text-ink-2">활성 세션</p>
          {#if loadingSessions}
            <span class="text-[10px] text-ink-3">로딩...</span>
          {:else}
            <span class="text-[10px] text-ink-3">{sessions.length}개</span>
          {/if}
        </div>
        {#if sessions.length > 0}
          <div class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-line-2 text-ink-3 uppercase tracking-wide text-[10px]">
                  <th class="text-left py-1 pr-3">출처 IP</th>
                  <th class="text-left py-1 pr-3">기기</th>
                  <th class="text-left py-1 pr-3">마지막 사용</th>
                  <th class="text-left py-1">상태</th>
                </tr>
              </thead>
              <tbody>
                {#each sessions as sess (sess.jti)}
                  <tr class="border-b border-line/50">
                    <td class="py-1.5 pr-3 font-mono text-ink-2">{sess.origin_ip || '—'}</td>
                    <td class="py-1.5 pr-3 text-ink-2">{deviceLabel(sess)}</td>
                    <td class="py-1.5 pr-3 text-ink-3">{formatSessionTime(sess.last_seen)}</td>
                    <td class="py-1.5">
                      {#if sess.blacklisted}
                        <span class="text-red-400 font-semibold">차단</span>
                      {:else}
                        <span class="text-green-500">활성</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else if !loadingSessions}
          <p class="text-xs text-ink-3">활성 세션 없음</p>
        {/if}
      </div>

      <!-- 세션 강제 폐기 -->
      <div class="mt-3 pt-3 border-t border-line">
        {#if showRevokeConfirm}
          <div class="bg-red-950/40 border border-red-800/60 rounded-lg px-3 py-3 mb-3">
            <p class="text-xs text-red-300 mb-2">이 사용자의 모든 세션을 강제 폐기합니까?<br>Keystone 토큰도 즉시 폐기됩니다.</p>
            <div class="flex gap-2">
              <button
                onclick={revokeAllSessions}
                disabled={revoking}
                class="px-3 py-1.5 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-ink-0 text-xs rounded-lg transition-colors"
              >{revoking ? '폐기 중...' : '확인'}</button>
              <button
                onclick={() => { showRevokeConfirm = false; }}
                class="px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-0 text-xs rounded-lg transition-colors"
              >취소</button>
            </div>
          </div>
        {:else}
          <button
            onclick={() => { showRevokeConfirm = true; }}
            disabled={revoking}
            class="w-full px-3 py-2 bg-red-900/40 hover:bg-red-900/70 border border-red-800/60 text-red-300 text-xs rounded-lg transition-colors disabled:opacity-50"
          >전체 세션 강제 폐기 (Keystone 직접 폐기 포함)</button>
        {/if}
      </div>

      <div class="flex justify-end gap-3 mt-4">
        <button onclick={() => { user = null; }} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">취소</button>
        <button onclick={submit} disabled={updating} class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-ink-0 text-sm font-medium rounded-lg disabled:opacity-30">{updating ? '수정 중...' : '수정'}</button>
      </div>
    </div>
  </div>
{/if}
