<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import type { SignupOptions } from '$lib/types/enrollmentPolicy';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { t } from '$lib/i18n/ns/domain-auth';
	import { beginAuthExperience, observedAuthText, createAuthNoticePresenter, type AuthExperience } from './authExperience';

	let { signup = false }: { signup?: boolean } = $props();
	let email = $state('');
	let kind = $state<'username' | 'password'>('username');
	let ready = $state(false);
	let loading = $state(true);
	let sending = $state(false);
	let sent = $state(false);
	let error = $state('');
	let live = true;
	let form = $state<HTMLFormElement>();
	let resultExperience = $state.raw<AuthExperience>();
	let loadExperience = $state.raw<AuthExperience>();
	const presentNotice = createAuthNoticePresenter();
	$effect(() => {
		const key = sent && resultExperience ? signup ? 'login.signup.sent' : 'recovery.sent' : null;
		if (key) t(key);
		presentNotice('sent', resultExperience, 'domain-auth', key, 'info');
	});
	$effect(() => {
		const key = !loading && !ready ? 'recovery.notAvailable' : null;
		if (key) t(key);
		presentNotice('availability', loadExperience, 'domain-auth', key, 'warning');
	});
	onMount(() => {
		const observation = beginAuthExperience(signup ? 'auth.signup' : 'auth.recover', 'load', () => live);
		loadExperience = observation;
		const text = observedAuthText(observation, 'domain-auth', t);
		observation.state('loading');
		void api.get<SignupOptions>('/api/v1/auth/signup/options', undefined, undefined, { refresh: true, cache: 'no-store', suppressAuthRedirect: true, ...observation.options })
			.then(options => {
				if (!live) { observation.discard('unmounted'); return; }
				ready = options.smtp_configured && (signup ? options.signup_enabled : options.recovery_enabled);
				observation.state(ready ? 'ready' : 'disabled');
			})
			.catch(() => {
				if (!live) { observation.discard('unmounted'); return; }
				error = text('onboarding.unavailable'); observation.state('error');
			})
			.finally(() => { if (live) { loading = false; void observation.applied(); } });
		return () => { live = false; email = ''; };
	});
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (!ready || sending) return;
		const observation = beginAuthExperience(signup ? 'auth.signup' : 'auth.recover', signup ? 'submit' : 'recover', () => live);
		if (!form?.reportValidity()) { observation.validation('format'); return; }
		const text = observedAuthText(observation, 'domain-auth', t);
		resultExperience = observation;
		sending = true; error = ''; sent = false;
		observation.state('loading');
		try {
			const result = await api.post<{ accepted: boolean }>(signup ? '/api/v1/auth/registrations' : `/api/v1/auth/recovery/${kind}`, { email: email.trim() }, undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false, ...observation.options });
			if (!live) { observation.discard('unmounted'); return; }
			if (result?.accepted === true) { sent = true; email = ''; observation.state('ready'); }
			else { error = text('login.signup.failed'); observation.state('error'); }
		} catch (e) {
			if (!live) { observation.discard('unmounted'); return; }
			error = text(e instanceof ApiError && e.status === 429 ? 'login.signup.rateLimited' : 'login.signup.failed');
			observation.state('error');
		} finally { if (live) { sending = false; void observation.applied(); } }
	}
</script>

<div class="auth-flow">
{#if loading}
	<LoadingState variant="section" label={t('onboarding.processing')}  />
{:else}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if sent}<Alert tone="info">{signup ? t('login.signup.sent') : t('recovery.sent')}</Alert>{/if}
	{#if !ready}<Alert tone="warning">{t('recovery.notAvailable')}</Alert>{:else}
		<form bind:this={form} onsubmit={submit} class="auth-flow">
			{#if !signup}
				<fieldset disabled={sending} class="flex flex-wrap gap-4 text-sm text-ink-1">
					<legend class="sr-only">{t('recovery.title')}</legend>
					<label class="min-h-11 flex items-center gap-2"><input type="radio" bind:group={kind} value="username" />{t('recovery.username')}</label>
					<label class="min-h-11 flex items-center gap-2"><input type="radio" bind:group={kind} value="password" />{t('recovery.password')}</label>
				</fieldset>
				{#if kind === 'password'}<p class="text-sm text-ink-1">{t('recovery.passwordHelp')}</p>{/if}
			{/if}
			<Field for="account-request-email" label={t('login.signup.email')} help={signup ? t('signup.description') : t('recovery.description')} required>
				<TextInput id="account-request-email" type="email" autocomplete="email" inputmode="email" bind:value={email} disabled={sending} required />
			</Field>
			<div class="auth-flow-actions">
				<Button type="submit" disabled={sending} ariaBusy={sending} class="w-full">{#if sending}<LoadingState variant="control" label={t('login.signup.sending')} />{:else}{t('login.signup.submit')}{/if}</Button>
			</div>
		</form>
	{/if}
{/if}
</div>
