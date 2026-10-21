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
  import ProfileImage from './ProfileImage.svelte';
  import { profileImage } from '$lib/stores/profileImage';

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
  let imageError = $state('');
  let imageSuccess = $state(false);
  let uploadInput = $state<HTMLInputElement>();
  let live = true;
  let generation = 0;
  let authorityGeneration = 0;
  const blocked = $derived(!$auth.token || !$authReady || $logoutInProgress || $projectSwitching || !profile.id || loading || saving || sending);
  const imageBlocked = $derived(blocked || $profileImage.loading || $profileImage.busy);
  onMount(() => {
    let previous = '';
    const unsubscribe = auth.subscribe(state => {
      const key = sessionScopeKey(state);
      if (key === previous) return;
      previous = key; generation++;
      currentPassword = ''; emailSent = false; emailError = ''; success = ''; error = ''; saving = false; sending = false;
      imageError = ''; imageSuccess = false;
      profile = { id: '', name: '', email: '', description: '' }; editName = ''; editEmail = ''; editDescription = '';
      if (state.token) void load(generation, state.token, state.projectId ?? undefined);
      else loading = false;
    });
    let authority = '';
    const unsubscribeAuthority = derived([authReady, logoutInProgress, projectSwitching], values => JSON.stringify(values)).subscribe(key => {
      if (key !== authority) { authority = key; authorityGeneration++; currentPassword = ''; emailSent = false; success = ''; imageSuccess = false; imageError = ''; }
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
      if (live && boundary === generation && authority === authorityGeneration) { profile = res; success = t('profile.saved'); void profileImage.refresh(); }
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
  async function saveImage(kind: 'gravatar' | 'generated' | 'upload', file?: File) {
    if (imageBlocked) return;
    const boundary = generation;
    const authority = authorityGeneration;
    imageError = ''; imageSuccess = false;
    try {
      const saved = await profileImage.save(kind, file);
      if (saved && live && boundary === generation && authority === authorityGeneration) imageSuccess = true;
    } catch {
      if (live && boundary === generation && authority === authorityGeneration) imageError = t('profile.image.saveFailed');
    }
  }
  function uploadImage(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0]; input.value = '';
    if (!file || imageBlocked) return;
    if (file.size > 2 * 1024 * 1024 || !/^(image\/(png|jpeg|webp|gif))$/.test(file.type)) {
      imageError = t('profile.image.invalid'); imageSuccess = false; return;
    }
    void saveImage('upload', file);
  }
</script>

<Card class="p-5 space-y-4">
  <h3 class="text-sm font-semibold text-ink-0">{t('profile.title')}</h3>
  {#if error}<Alert tone="danger">{error}</Alert>{/if}
  {#if success}<Alert tone="success">{success}</Alert>{/if}
  {#if loading}<ActivityIndicator label={tc('state.loading')} />{:else}
    <div class="text-sm text-ink-2 break-all"><span>{t('profile.userId')}: </span><span class="font-mono">{profile.id}</span></div>
    <section class="space-y-3 border-b border-line pb-4" aria-label={t('profile.image.title')}>
      <div class="flex flex-wrap items-center gap-4">
        <ProfileImage name={profile.name} label={t('profile.image.alt')} large />
        <div class="min-w-0 flex-1 space-y-1"><h4 class="text-sm font-medium text-ink-0">{t('profile.image.title')}</h4><p class="text-sm text-ink-2">{t('profile.image.help')}</p></div>
      </div>
      {#if imageError}<Alert tone="danger">{imageError} <Button variant="secondary" size="sm" disabled={imageBlocked} onclick={() => { imageError = ''; void profileImage.refresh(); }}>{t('profile.image.retry')}</Button></Alert>{/if}
      {#if imageSuccess}<Alert tone="success">{t('profile.image.saved')}</Alert>{/if}
      {#if $profileImage.failed}<Alert tone="warning">{t('profile.image.loadFailed')} <Button variant="secondary" size="sm" disabled={imageBlocked} onclick={() => profileImage.refresh()}>{t('profile.image.retry')}</Button></Alert>{/if}
      <div class="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={imageBlocked} ariaPressed={$profileImage.image?.kind === 'gravatar'} onclick={() => saveImage('gravatar')}>{t('profile.image.gravatar')}</Button>
        <Button variant="secondary" disabled={imageBlocked} ariaPressed={$profileImage.image?.kind === 'generated'} onclick={() => saveImage('generated')}>{t($profileImage.image?.kind === 'generated' ? 'profile.image.regenerate' : 'profile.image.generate')}</Button>
        <Button variant="secondary" disabled={imageBlocked} ariaPressed={$profileImage.image?.kind === 'upload'} onclick={() => uploadInput?.click()}>{t('profile.image.upload')}</Button>
        <input bind:this={uploadInput} type="file" accept="image/png,image/jpeg,image/webp,image/gif" aria-label={t('profile.image.upload')} class="sr-only" tabindex="-1" disabled={imageBlocked} onchange={uploadImage} />
      </div>
      {#if $profileImage.loading || $profileImage.busy}<ActivityIndicator label={tc('state.loading')} />{/if}
    </section>
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
