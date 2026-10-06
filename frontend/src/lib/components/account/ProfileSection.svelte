<script lang="ts">
  import { t } from '$lib/i18n/ns/account';
  import { t as tc } from '$lib/i18n/ns/common';
  import { auth } from '$lib/stores/auth';
  import { api, ApiError } from '$lib/api/client';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

  interface Profile {
    id: string;
    name: string;
    email: string;
    description: string;
  }

  const token = $derived($auth.token ?? undefined);
  const projectId = $derived($auth.projectId ?? undefined);

  let profile = $state<Profile>({ id: '', name: '', email: '', description: '' });
  let loading = $state(true);
  let saving = $state(false);
  let error = $state('');
  let success = $state('');

  let editName = $state('');
  let editEmail = $state('');
  let editDescription = $state('');

  async function load() {
    loading = true;
    error = '';
    try {
      const res = await api.get<Profile>('/api/v1/profile', token, projectId);
      profile = res;
      editName = res.name;
      editEmail = res.email;
      editDescription = res.description;
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('profile.loadFailed');
    } finally {
      loading = false;
    }
  }

  async function save() {
    error = '';
    success = '';
    saving = true;
    try {
      const body: Record<string, string> = {};
      if (editName !== profile.name) body.name = editName;
      if (editEmail !== profile.email) body.email = editEmail;
      if (editDescription !== profile.description) body.description = editDescription;
      if (Object.keys(body).length === 0) {
        error = t('profile.unchanged');
        return;
      }
      const res = await api.patch<Profile>('/api/v1/profile', body, token, projectId);
      profile = res;
      success = t('profile.saved');
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('profile.saveFailed');
    } finally {
      saving = false;
    }
  }

  $effect(() => {
    if ($auth.token) load();
  });
</script>

<div class="motion-fade bg-surface-base border border-line rounded-xl p-5">
  <h3 class="text-sm font-semibold text-ink-0 mb-4">{t('profile.title')}</h3>

  {#if error}
    <div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-3 py-2 text-xs mb-3">{error}</div>
  {/if}
  {#if success}
    <div class="bg-green-900/40 border border-green-700 text-green-300 rounded-lg px-3 py-2 text-xs mb-3">{success}</div>
  {/if}

  {#if loading}
    <ActivityIndicator label={tc('state.loading')} />
    <div class="space-y-2 mt-2" aria-hidden="true">
      {#each [1, 2, 3] as _}
        <div class="h-9 motion-skeleton rounded"></div>
      {/each}
    </div>
  {:else}
    <div class="space-y-3">
      <div>
        <div class="block text-xs text-ink-2 mb-1">{t('profile.userId')}</div>
        <div class="text-sm text-ink-2 font-mono bg-surface-sunken/50 rounded px-3 py-2">{profile.id}</div>
      </div>
      <div>
        <label class="block text-xs text-ink-2 mb-1" for="field-profilesection-92">{t('profile.name')}</label>
        <input id="field-profilesection-92"
          type="text"
          bind:value={editName}
          class="w-full bg-surface-sunken border border-line-2 focus:border-action-warm text-ink-0 text-sm rounded-lg px-3 py-2 outline-none transition-colors"
          placeholder={t('profile.namePlaceholder')}
        />
      </div>
      <div>
        <label class="block text-xs text-ink-2 mb-1" for="field-profilesection-101">{t('profile.email')}</label>
        <input id="field-profilesection-101"
          type="email"
          bind:value={editEmail}
          class="w-full bg-surface-sunken border border-line-2 focus:border-action-warm text-ink-0 text-sm rounded-lg px-3 py-2 outline-none transition-colors"
          placeholder={t('profile.emailPlaceholder')}
        />
      </div>
      <div>
        <label class="block text-xs text-ink-2 mb-1" for="field-profilesection-110">{t('profile.description')}</label>
        <textarea id="field-profilesection-110"
          bind:value={editDescription}
          rows="2"
          class="w-full bg-surface-sunken border border-line-2 focus:border-action-warm text-ink-0 text-sm rounded-lg px-3 py-2 outline-none transition-colors resize-none"
          placeholder={t('profile.descriptionPlaceholder')}
        ></textarea>
      </div>
    </div>
    <div class="mt-4 flex justify-end">
      <button
        onclick={save}
        disabled={saving}
        class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover disabled:opacity-50 text-action-on-warm text-sm rounded-lg transition-colors"
      >{#if saving}<ActivityIndicator size="xs" label={t('profile.saving')} />{:else}{t('profile.save')}{/if}</button>
    </div>
  {/if}
</div>
