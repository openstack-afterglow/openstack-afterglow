<script lang="ts">
  import { auth, authReady } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  let currentPassword = $state('');
  let newPassword = $state('');
  let confirmPassword = $state('');
  let error = $state('');
  let success = $state('');
  let saving = $state(false);

  async function changePassword() {
    error = '';
    success = '';
    if (!currentPassword || !newPassword || !confirmPassword) {
      error = '모든 항목을 입력해 주세요';
      return;
    }
    if (newPassword !== confirmPassword) {
      error = '새 패스워드가 일치하지 않습니다';
      return;
    }
    if (newPassword.length < 8) {
      error = '새 패스워드는 8자 이상이어야 합니다';
      return;
    }
    saving = true;
    try {
      await api.post('/api/v1/profile/password', { current_password: currentPassword, new_password: newPassword }, token, projectId);
      success = '패스워드가 변경되었습니다';
      currentPassword = '';
      newPassword = '';
      confirmPassword = '';
    } catch (e) {
      error = e instanceof ApiError ? e.message : '패스워드 변경 실패';
    } finally {
      saving = false;
    }
  }
</script>

{#if $authReady && !$auth.federated}
<div class="bg-surface-base border border-line rounded-xl p-5">
  <h3 class="text-sm font-semibold text-ink-0 mb-4">패스워드 변경</h3>

  {#if error}
    <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-3 py-2 text-xs mb-3">{error}</div>
  {/if}
  {#if success}
    <div class="bg-green-900/40 border border-green-700 text-green-300 rounded-lg px-3 py-2 text-xs mb-3">{success}</div>
  {/if}

  <div class="space-y-3">
    <div>
      <label class="block text-xs text-ink-2 mb-1" for="field-passwordsection-58">현재 패스워드</label>
      <input id="field-passwordsection-58" type="password" bind:value={currentPassword} class="w-full bg-surface-sunken border border-line-2 focus:border-action-warm text-ink-0 text-sm rounded-lg px-3 py-2 outline-none transition-colors" placeholder="현재 패스워드" />
    </div>
    <div>
      <label class="block text-xs text-ink-2 mb-1" for="field-passwordsection-62">새 패스워드</label>
      <input id="field-passwordsection-62" type="password" bind:value={newPassword} class="w-full bg-surface-sunken border border-line-2 focus:border-action-warm text-ink-0 text-sm rounded-lg px-3 py-2 outline-none transition-colors" placeholder="8자 이상" />
    </div>
    <div>
      <label class="block text-xs text-ink-2 mb-1" for="field-passwordsection-66">새 패스워드 확인</label>
      <input id="field-passwordsection-66" type="password" bind:value={confirmPassword} class="w-full bg-surface-sunken border border-line-2 focus:border-action-warm text-ink-0 text-sm rounded-lg px-3 py-2 outline-none transition-colors" placeholder="패스워드 재입력" />
    </div>
  </div>

  <div class="mt-4 flex justify-end">
    <button
      onclick={changePassword}
      disabled={saving}
      class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover disabled:opacity-50 text-action-on-warm text-sm rounded-lg transition-colors"
    >{saving ? '변경 중...' : '패스워드 변경'}</button>
  </div>
</div>
{/if}
