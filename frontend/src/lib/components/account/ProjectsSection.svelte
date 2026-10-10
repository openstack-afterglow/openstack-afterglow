<script lang="ts">
  import { t } from '$lib/i18n/ns/account';
  import { t as tc } from '$lib/i18n/ns/common';
  import { auth, logoutInProgress, setAuth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import { cloudShell } from '$lib/stores/cloudShell.svelte';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

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
      error = e instanceof ApiError ? e.message : t('projects.loadFailed');
    } finally {
      loading = false;
    }
  }

  async function selectProject(proj: Project) {
    const currentToken = $auth.token;
    if (!currentToken || switching) return;
    if (proj.id === $auth.projectId) return;

    switching = true;
    await cloudShell.close('project-switch', { keepDock: false });
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
        can_write: boolean;
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
        canWrite: resp.can_write,
      });

      api.post('/api/v1/networks/ensure-default', {}, resp.token, resp.project_id).catch(() => {});
    } catch (e) {
      error = e instanceof ApiError ? t('projects.switchError', { error: e.message }) : t('projects.switchFailed');
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
      defaultMsg = t('projects.defaultSet', { name: proj.name });
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('projects.defaultFailed');
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
      defaultMsg = t('projects.defaultCleared');
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('projects.clearFailed');
    } finally {
      settingDefault = false;
    }
  }

  $effect(() => {
    if ($auth.token) load();
  });
</script>

<div class="motion-fade bg-surface-base border border-line rounded-xl p-5">
  <h3 class="text-sm font-semibold text-ink-0 mb-4">{t('projects.title')}</h3>
  {#if switching}<ActivityIndicator label={tc('state.processing')} />{/if}
  {#if settingDefault}<ActivityIndicator label={tc('state.processing')} />{/if}

  {#if error}
    <div class="text-red-400 text-xs mb-2">{error}</div>
  {/if}
  {#if defaultMsg}
    <div class="text-green-400 text-xs mb-2">{defaultMsg}</div>
  {/if}

  {#if loading}
    <ActivityIndicator label={tc('state.loading')} />
    <div class="space-y-2 mt-2" aria-hidden="true">
      {#each [1, 2] as _}
        <div class="h-8 motion-skeleton rounded"></div>
      {/each}
    </div>
  {:else if projects.length === 0}
    <div class="text-ink-2 text-xs text-center py-4">{t('projects.empty')}</div>
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
            <div class="text-sm font-medium truncate {isActive ? 'text-warm-text' : 'text-ink-0'}">{proj.name}</div>
            {#if proj.description}
              <div class="text-xs text-ink-2 truncate">{proj.description}</div>
            {/if}
          </button>

          <div class="flex items-center gap-1.5 shrink-0">
            {#if isDefault}
              <span class="text-xs text-warm-text font-medium px-1.5 py-0.5 rounded bg-action-warm/10 border border-action-warm/25">{t('projects.default')}</span>
            {/if}
            {#if isActive}
              <span class="text-xs text-warm-text font-medium px-1.5 py-0.5 rounded bg-action-warm/15 border border-action-warm/30">{t('projects.active')}</span>
            {/if}
            {#if isDefault}
              <button
                onclick={() => clearDefault()}
                disabled={settingDefault}
                class="text-xs text-ink-2 hover:text-red-400 transition-colors disabled:opacity-40"
              >{t('projects.clear')}</button>
            {:else}
              <button
                onclick={() => setDefault(proj)}
                disabled={settingDefault}
                class="text-xs text-ink-2 hover:text-warm-text-hover transition-colors disabled:opacity-40"
              >{t('projects.setDefault')}</button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
