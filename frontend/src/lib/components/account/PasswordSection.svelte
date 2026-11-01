<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { get } from 'svelte/store';
  import { t } from '$lib/i18n/ns/account';
  import { auth, authReady, clearAuth, logoutInProgress, projectSwitching } from '$lib/stores/auth';
  import { sessionScopeKey } from '$lib/utils/authSession';
  import { api, ApiError } from '$lib/api/client';
  import { Alert, Button, Card, Field, TextInput } from '$lib/components/ui';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { cloudShell } from '$lib/stores/cloudShell.svelte';
  import { toast } from '$lib/stores/toast';

  type PasswordMode = 'create' | 'change' | 'unavailable';
  const sectionId = $props.id();
  let mounted = false;
  let epoch = 0;
  let mode = $state<PasswordMode>('unavailable');
  let loading = $state(false);
  let saving = $state(false);
  let sent = $state(false);
  let recoverySent = $state(false);
  let stateUnknown = $state(false);
  let currentPassword = $state('');
  let newPassword = $state('');
  let confirmPassword = $state('');
  let error = $state('');
  const blocked = $derived(!$auth.token || !$authReady || $logoutInProgress || $projectSwitching || loading || saving);

  function clearPasswords() {
    currentPassword = ''; newPassword = ''; confirmPassword = '';
  }

  function capture() {
    const state = get(auth), ticket = epoch;
    if (!mounted || !state.token || !get(authReady) || get(logoutInProgress) || get(projectSwitching)) return null;
    return { token: state.token, project: state.projectId ?? undefined,
      current: () => mounted && epoch === ticket && get(authReady) && !get(logoutInProgress) && !get(projectSwitching) };
  }

  async function loadCapability() {
    const owner = capture(); if (!owner) return;
    mode = 'unavailable'; loading = true; error = ''; stateUnknown = false;
    try {
      const result = await api.get<{ mode: PasswordMode; reason?: string }>('/api/v1/profile/password/capability', owner.token, owner.project,
        { refresh: true, cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false });
      if (owner.current()) {
        mode = result?.mode === 'change' || result?.mode === 'create' ? result.mode : 'unavailable';
        stateUnknown = result?.reason === 'password_state_unknown';
      }
    } catch { if (owner.current()) error = t('password.unavailable'); }
    finally { if (owner.current()) loading = false; }
  }

  async function requestCreation() {
    if (blocked || mode !== 'create' || sent) return;
    const owner = capture(); if (!owner) return;
    saving = true; error = '';
    try {
      const result = await api.post<{ accepted: boolean }>('/api/v1/profile/password/create/request', {}, owner.token, owner.project,
        { cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false });
      if (owner.current()) {
        if (result?.accepted === true) sent = true;
        else error = t('password.createRequestFailed');
      }
    } catch (e) {
      if (owner.current()) error = t(e instanceof ApiError && e.code === 'password_create_reconciliation_required'
        ? 'password.createOutcomeUnknown' : e instanceof ApiError && e.status === 429
        ? 'password.createRateLimited' : 'password.createRequestFailed');
    } finally { if (owner.current()) saving = false; }
  }

  async function requestRecovery() {
    if (blocked || mode !== 'change' || recoverySent) return;
    const owner = capture(); if (!owner) return;
    clearPasswords(); saving = true; error = '';
    try {
      const result = await api.post<{ accepted: boolean }>('/api/v1/profile/password/recovery/request', {}, owner.token, owner.project,
        { cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false });
      if (owner.current()) {
        if (result?.accepted === true) recoverySent = true;
        else error = t('password.recoveryFailed');
      }
    } catch (e) {
      if (owner.current()) error = t(e instanceof ApiError && e.status === 429 ? 'password.recoveryRateLimited' : 'password.recoveryFailed');
    } finally { if (owner.current()) saving = false; }
  }

  function finishPasswordChange(known: boolean) {
    const message = t(known ? 'password.changed' : 'password.changeOutcomeUnknown');
    logoutInProgress.set(true);
    clearAuth();
    if (known) toast.success(message, 0); else toast.error(message);
    void cloudShell.close('logout', { keepDock: false }).catch(() => {}).finally(() => {
      void goto('/login', { replaceState: true }).finally(() => logoutInProgress.set(false));
    });
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (blocked || mode !== 'change') return;
    error = '';
    if (!currentPassword || !newPassword || !confirmPassword) { error = t('password.required'); return; }
    if (newPassword !== confirmPassword) { error = t('password.mismatch'); return; }
    if (newPassword.length < 8) { error = t('password.minimum'); return; }
    const owner = capture(); if (!owner) return;
    const body = { current_password: currentPassword, new_password: newPassword };
    clearPasswords(); saving = true;
    try {
      await api.post('/api/v1/profile/password', body, owner.token, owner.project,
        { cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false });
      if (owner.current()) finishPasswordChange(true);
    } catch (e) {
      if (owner.current()) {
        if (!(e instanceof ApiError) || e.status === 502 || e.code === 'password_change_outcome_unknown') finishPasswordChange(false);
        else if (e.status === 401 && e.message === 'password_current_invalid') error = t('password.incorrect');
        else error = t('password.changeFailed');
      }
    } finally {
      if (owner.current()) saving = false;
    }
  }

  onMount(() => {
    mounted = true; let previous = '';
    const changed = () => {
      const state = get(auth);
      const next = JSON.stringify([sessionScopeKey(state), !!state.token, state.federated, get(authReady), get(logoutInProgress), get(projectSwitching)]);
      if (next === previous) return;
      previous = next; epoch++; saving = false; loading = false; sent = false; recoverySent = false; stateUnknown = false; mode = 'unavailable'; error = ''; clearPasswords();
      void loadCapability();
    };
    const unsubscribers = [auth.subscribe(changed), authReady.subscribe(changed), logoutInProgress.subscribe(changed), projectSwitching.subscribe(changed)];
    return () => { mounted = false; epoch++; clearPasswords(); unsubscribers.forEach(unsubscribe => unsubscribe()); };
  });
</script>

{#if $authReady}
<Card class="p-5 space-y-4">
  <h3 class="text-sm font-semibold text-ink-0">{t(mode === 'create' ? 'password.createTitle' : 'password.title')}</h3>
  {#if error}<Alert tone="danger">{error}</Alert>{/if}
  {#if loading}<LoadingState variant="section" label={t('password.checking')}  />
  {:else if mode === 'create'}
    <Alert tone="warning">{t('password.createWarning')}</Alert>
    <p class="text-sm text-ink-1">{t('password.createHelp')}</p>
    {#if sent}<Alert tone="success">{t('password.createSent')}</Alert>
    {:else}<div class="flex justify-end"><Button onclick={requestCreation} disabled={blocked} ariaBusy={saving}>{#if saving}<LoadingState variant="control" label={t('password.createRequesting')}  />{:else}{t('password.createTitle')}{/if}</Button></div>{/if}
  {:else if mode === 'change'}
    {#if stateUnknown}<Alert tone="warning">{t('password.stateUnknown')}</Alert>{/if}
    <form onsubmit={submit} novalidate class="space-y-3">
      <Field for={`${sectionId}-current`} label={t('password.current')}>
        <TextInput id={`${sectionId}-current`} type="password" bind:value={currentPassword} autocomplete="current-password" maxlength={1024} disabled={blocked} required />
      </Field>
      <Field for={`${sectionId}-new`} label={t('password.new')}>
        <TextInput id={`${sectionId}-new`} type="password" bind:value={newPassword} autocomplete="new-password" maxlength={1024} disabled={blocked} placeholder={t('password.minimumPlaceholder')} required />
      </Field>
      <Field for={`${sectionId}-confirm`} label={t('password.confirm')}>
        <TextInput id={`${sectionId}-confirm`} type="password" bind:value={confirmPassword} autocomplete="new-password" maxlength={1024} disabled={blocked} placeholder={t('password.confirmPlaceholder')} required />
      </Field>
      <div class="flex justify-end">
        <Button type="submit" disabled={blocked} ariaBusy={saving}>{#if saving}<LoadingState variant="control" label={t('password.changing')}  />{:else}{t('password.title')}{/if}</Button>
      </div>
    </form>
    <div class="space-y-3 border-t border-line pt-4">
      <p class="text-sm text-ink-1">{t('password.recoveryHelp')}</p>
      {#if recoverySent}<Alert tone="info">{t('password.recoveryAccepted')}</Alert>
      {:else}<Button variant="secondary" onclick={requestRecovery} disabled={blocked} ariaBusy={saving}>{t('password.forgot')}</Button>{/if}
    </div>
  {:else}
    {#if !error}<Alert tone="warning">{t('password.unavailable')}</Alert>{/if}
    <Button variant="secondary" onclick={loadCapability} disabled={blocked}>{t('password.reload')}</Button>
    <p class="text-sm text-ink-1">{t('password.recoveryHelp')}</p>
    <Button variant="link" href="/recover">{t('password.openRecovery')}</Button>
  {/if}
</Card>
{/if}
