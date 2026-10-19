<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { t } from '$lib/i18n/ns/domain-auth';

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
	onMount(() => {
		void api.get<{ signup_enabled: boolean; smtp_configured: boolean; recovery_enabled: boolean }>('/api/v1/auth/signup/options', undefined, undefined, { refresh: true, cache: 'no-store', suppressAuthRedirect: true })
			.then(options => { if (live) ready = options.smtp_configured && (signup ? options.signup_enabled : options.recovery_enabled); })
			.catch(() => { if (live) error = t('onboarding.unavailable'); })
			.finally(() => { if (live) loading = false; });
		return () => { live = false; email = ''; };
	});
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (!ready || sending || !form?.reportValidity()) return;
		sending = true; error = ''; sent = false;
		try {
			await api.post(signup ? '/api/v1/auth/registrations' : `/api/v1/auth/recovery/${kind}`, { email: email.trim() }, undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false });
			if (live) { sent = true; email = ''; }
		} catch (e) {
			if (live) error = e instanceof ApiError && e.status === 429 ? t('login.signup.rateLimited') : t('login.signup.failed');
		} finally { if (live) sending = false; }
	}
</script>

{#if loading}
	<ActivityIndicator label={t('onboarding.processing')} />
{:else}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if sent}<Alert tone="info">{signup ? t('login.signup.sent') : t('recovery.sent')}</Alert>{/if}
	{#if !ready}<Alert tone="warning">{t('recovery.notAvailable')}</Alert>{:else}
		<form bind:this={form} onsubmit={submit} class="space-y-4">
			{#if !signup}
				<fieldset disabled={sending} class="flex flex-wrap gap-4 text-sm text-ink-1">
					<legend class="sr-only">{t('recovery.title')}</legend>
					<label class="min-h-11 flex items-center gap-2"><input type="radio" bind:group={kind} value="username" />{t('recovery.username')}</label>
					<label class="min-h-11 flex items-center gap-2"><input type="radio" bind:group={kind} value="password" />{t('recovery.password')}</label>
				</fieldset>
			{/if}
			<Field for="account-request-email" label={t('login.signup.email')} help={signup ? t('signup.description') : t('recovery.description')} required>
				<TextInput id="account-request-email" type="email" autocomplete="email" inputmode="email" bind:value={email} disabled={sending} required />
			</Field>
			<Button type="submit" disabled={sending} ariaBusy={sending} class="w-full">{sending ? t('login.signup.sending') : t('login.signup.submit')}</Button>
		</form>
	{/if}
{/if}
