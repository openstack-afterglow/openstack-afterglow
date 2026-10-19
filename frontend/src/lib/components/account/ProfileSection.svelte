<script lang="ts">
  import { onMount } from 'svelte';
  import { derived } from 'svelte/store';
  import { t } from '$lib/i18n/ns/account';
  import { t as tc } from '$lib/i18n/ns/common';
  import { t as ta } from '$lib/i18n/ns/domain-auth';
  import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
  import { sessionScopeKey } from '$lib/utils/authSession';
  import { api } from '$lib/api/client';
  import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
  import Alert from '$lib/components/ui/Alert.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Field from '$lib/components/ui/Field.svelte';
  import TextInput from '$lib/components/ui/TextInput.svelte';
  import Card from '$lib/components/ui/Card.svelte';

  interface Profile { id: string; name: string; email: string; description: string }
  let profile = $state<Profile>({ id: '', name: '', email: '', description: '' });
  let loading = $state(true);
  let saving = $state(false);
  let sending = $state(false);
  let error = $state('');
  let success = $state('');
  let emailError = $state('');
  let emailSent = $state(false);
  let editName = $state('');
  let editEmail = $state('');
  let editDescription = $state('');
  let currentPassword = $state('');
  let live = true;
  let generation = 0;
  let authorityGeneration = 0;
  const blocked = $derived(!$auth.token || !$authReady || $logoutInProgress || $projectSwitching || !profile.id || loading || saving || sending);
  onMount(() => {
    let previous = '';
    const unsubscribe = auth.subscribe(state => {
      const key = sessionScopeKey(state);
      if (key === previous) return;
      previous = key; generation++;
      currentPassword = ''; emailSent = false; emailError = ''; success = ''; error = ''; saving = false; sending = false;
      profile = { id: '', name: '', email: '', description: '' }; editName = ''; editEmail = ''; editDescription = '';
      if (state.token) void load(generation, state.token, state.projectId ?? undefined);
      else loading = false;
    });
    let authority = '';
    const unsubscribeAuthority = derived([authReady, logoutInProgress, projectSwitching], values => JSON.stringify(values)).subscribe(key => {
      if (key !== authority) { authority = key; authorityGeneration++; currentPassword = ''; emailSent = false; success = ''; }
    });
    return () => { live = false; generation++; currentPassword = ''; unsubscribe(); unsubscribeAuthority(); };
  });
  async function load(boundary: number, token: string, projectId?: string) {
    loading = true;
    try {
      const res = await api.get<Profile>('/api/v1/profile', token, projectId);
      if (!live || boundary !== generation) return;
      profile = res; editName = res.name; editEmail = res.email; editDescription = res.description;
    } catch { if (live && boundary === generation) error = t('profile.loadFailed'); }
    finally { if (live && boundary === generation) loading = false; }
  }
  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (blocked) return;
    const boundary = generation;
    const authority = authorityGeneration;
    const body: Record<string, string> = {};
    if (editName !== profile.name) body.name = editName;
    if (editDescription !== profile.description) body.description = editDescription;
    error = ''; success = '';
    if (!Object.keys(body).length) { error = t('profile.unchanged'); return; }
    saving = true;
    try {
      const res = await api.patch<Profile>('/api/v1/profile', body, $auth.token ?? undefined, $auth.projectId ?? undefined, { replayOnUnauthorized: false });
      if (live && boundary === generation && authority === authorityGeneration) { profile = res; success = t('profile.saved'); }
    } catch { if (live && boundary === generation && authority === authorityGeneration) error = t('profile.saveFailed'); }
    finally { if (live && boundary === generation) saving = false; }
  }
  async function changeEmail(event: SubmitEvent) {
    event.preventDefault();
    if (blocked || !editEmail.trim() || editEmail.trim() === profile.email || !currentPassword) return;
    const boundary = generation;
    const authority = authorityGeneration;
    const body = { email: editEmail.trim(), current_password: currentPassword };
    currentPassword = ''; sending = true; emailError = ''; emailSent = false;
    try {
      await api.post('/api/v1/auth/email/changes', body, $auth.token ?? undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false });
      if (live && boundary === generation && authority === authorityGeneration) emailSent = true;
    } catch { if (live && boundary === generation && authority === authorityGeneration) emailError = ta('emailChange.failed'); }
    finally { if (live && boundary === generation) sending = false; }
  }
</script>

<Card class="p-5 space-y-4">
  <h3 class="text-sm font-semibold text-ink-0">{t('profile.title')}</h3>
  {#if error}<Alert tone="danger">{error}</Alert>{/if}
  {#if success}<Alert tone="success">{success}</Alert>{/if}
  {#if loading}<ActivityIndicator label={tc('state.loading')} />{:else}
    <div class="text-sm text-ink-2 break-all"><span>{t('profile.userId')}: </span><span class="font-mono">{profile.id}</span></div>
    <form onsubmit={save} class="space-y-3">
      <Field for="profile-name" label={t('profile.name')}><TextInput id="profile-name" bind:value={editName} disabled={blocked} /></Field>
      <Field for="profile-description" label={t('profile.description')}><textarea id="profile-description" bind:value={editDescription} disabled={blocked} rows="2" class="w-full bg-surface-sunken border border-line-2 text-ink-0 text-sm rounded-lg px-3 py-2"></textarea></Field>
      <div class="flex justify-end"><Button type="submit" disabled={blocked} ariaBusy={saving}>{t('profile.save')}</Button></div>
    </form>
    <form onsubmit={changeEmail} class="space-y-3 border-t border-line pt-4">
      <p class="text-sm text-ink-2 break-all">{t('profile.email')}: {profile.email}</p>
      {#if emailError}<Alert tone="danger">{emailError}</Alert>{/if}
      {#if emailSent}<Alert tone="info">{ta('emailChange.sent')}</Alert>{/if}
      <Field for="profile-email" label={ta('emailChange.newEmail')} help={ta('emailChange.help')} required><TextInput id="profile-email" type="email" autocomplete="email" bind:value={editEmail} disabled={blocked} required /></Field>
      <Field for="profile-email-password" label={ta('emailChange.currentPassword')} required><TextInput id="profile-email-password" type="password" autocomplete="current-password" bind:value={currentPassword} maxlength={1024} disabled={blocked} required /></Field>
      <Button type="submit" variant="secondary" disabled={blocked || !currentPassword || editEmail.trim() === profile.email} ariaBusy={sending}>{ta('emailChange.submit')}</Button>
    </form>
  {/if}
</Card>
