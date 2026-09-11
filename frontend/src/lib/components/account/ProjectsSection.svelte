<script lang="ts">
  import { auth, logoutInProgress, setAuth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';

  interface Project {
    id: string;
    name: string;
    description?: string;
    enabled?: boolean;
  }

  const token = $derived($auth.token ?? undefined);

  let projects = $state<Project[]>([]);
  let loading = $state(true);
  let switching = $state(false);
  let settingDefault = $state(false);
  let defaultProjectId = $state('');
  let error = $state('');
  let defaultMsg = $state('');

  async function load() {
    loading = true;
    error = '';
    try {
      const [projs, profile] = await Promise.all([
        api.get<Project[]>('/api/v1/auth/projects', token),
        api.get<{ default_project_id: string }>('/api/v1/profile', token).catch(() => null),
      ]);
      projects = projs;
      defaultProjectId = profile?.default_project_id ?? '';
    } catch (e) {
      error = e instanceof ApiError ? e.message : '조회 실패';
    } finally {
      loading = false;
    }
  }

  async function selectProject(proj: Project) {
    const currentToken = $auth.token;
    if (!currentToken || switching) return;
    if (proj.id === $auth.projectId) return;

    switching = true;
    try {
      const resp = await api.post<{
        token: string;
        refresh_token: string;
        expires_at: string;
        project_id: string;
        project_name: string;
        user_id: string;
        username: string;
        roles: string[];
        is_system_admin: boolean;
      }>('/api/v1/auth/token/project', { project_id: proj.id }, currentToken);

      if ($logoutInProgress || !$auth.token) return;

      setAuth({
        token: resp.token,
        refreshToken: resp.refresh_token,
        accessExpiresAt: resp.expires_at
          ? Math.floor(new Date(resp.expires_at).getTime() / 1000)
          : null,
        projectId: resp.project_id,
        projectName: resp.project_name,
        roles: resp.roles ?? [],
        isSystemAdmin: !!resp.is_system_admin,
      });

      api.post('/api/v1/networks/ensure-default', {}, resp.token, resp.project_id).catch(() => {});
    } catch (e) {
      error = e instanceof ApiError ? `전환 실패: ${e.message}` : '프로젝트 전환 실패';
    } finally {
      switching = false;
    }
  }

  async function setDefault(proj: Project) {
    if (!token || settingDefault) return;
    settingDefault = true;
    defaultMsg = '';
    try {
      await api.patch('/api/v1/profile', { default_project_id: proj.id }, token);
      defaultProjectId = proj.id;
      defaultMsg = `'${proj.name}'이(가) 기본 프로젝트로 설정되었습니다.`;
    } catch (e) {
      error = e instanceof ApiError ? e.message : '기본 프로젝트 설정 실패';
    } finally {
      settingDefault = false;
    }
  }

  async function clearDefault() {
    if (!token || settingDefault) return;
    settingDefault = true;
    defaultMsg = '';
    try {
      await api.patch('/api/v1/profile', { default_project_id: '' }, token);
      defaultProjectId = '';
      defaultMsg = '기본 프로젝트가 해제되었습니다.';
    } catch (e) {
      error = e instanceof ApiError ? e.message : '기본 프로젝트 해제 실패';
    } finally {
      settingDefault = false;
    }
  }

  $effect(() => {
    if ($auth.token) load();
  });
</script>

<div class="bg-surface-base border border-line rounded-xl p-5">
  <h3 class="text-sm font-semibold text-ink-0 mb-4">소속 프로젝트</h3>

  {#if error}
    <div class="text-red-400 text-xs mb-2">{error}</div>
  {/if}
  {#if defaultMsg}
    <div class="text-green-400 text-xs mb-2">{defaultMsg}</div>
  {/if}

  {#if loading}
    <div class="space-y-2">
      {#each [1, 2] as _}
        <div class="h-8 bg-surface-sunken rounded animate-pulse"></div>
      {/each}
    </div>
  {:else if projects.length === 0}
    <div class="text-ink-3 text-xs text-center py-4">소속 프로젝트가 없습니다</div>
  {:else}
    <div class="space-y-2">
      {#each projects as proj (proj.id)}
        {@const isActive = $auth.projectId === proj.id}
        {@const isDefault = defaultProjectId === proj.id}
        <div
          class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg
            {isActive ? 'bg-action-warm/10 border border-action-warm/30' : 'bg-surface-sunken/50 border border-transparent'}"
        >
          <button
            onclick={() => selectProject(proj)}
            disabled={switching || isActive}
            class="flex-1 min-w-0 text-left disabled:cursor-default"
          >
            <div class="text-sm font-medium truncate {isActive ? 'text-action-warm' : 'text-ink-0'}">{proj.name}</div>
            {#if proj.description}
              <div class="text-[11px] text-ink-3 truncate">{proj.description}</div>
            {/if}
          </button>

          <div class="flex items-center gap-1.5 shrink-0">
            {#if isDefault}
              <span class="text-[10px] text-action-warm font-medium px-1.5 py-0.5 rounded bg-action-warm/10 border border-action-warm/25">기본</span>
            {/if}
            {#if isActive}
              <span class="text-[10px] text-action-warm font-medium px-1.5 py-0.5 rounded bg-action-warm/15 border border-action-warm/30">활성</span>
            {:else if switching}
              <svg class="w-3.5 h-3.5 text-ink-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
              </svg>
            {/if}
            {#if isDefault}
              <button
                onclick={() => clearDefault()}
                disabled={settingDefault}
                class="text-[11px] text-ink-3 hover:text-red-400 transition-colors disabled:opacity-40"
              >해제</button>
            {:else}
              <button
                onclick={() => setDefault(proj)}
                disabled={settingDefault}
                class="text-[11px] text-ink-3 hover:text-action-warm-hover transition-colors disabled:opacity-40"
              >기본 설정</button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
