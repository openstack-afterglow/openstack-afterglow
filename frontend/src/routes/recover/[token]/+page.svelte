<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { page } from '$app/stores';
	import { api, ApiError } from '$lib/api/client';
	import { isOnboardingToken } from '$lib/utils/domainLogin';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { t } from '$lib/i18n/ns/domain-auth';

	interface RecoveryInfo { kind: 'username' | 'password' | 'email_change'; email: string; username?: string; identity_domain_id?: string; identity_domain_name?: string }
	const token = $derived(($page.params as Record<string, string>)['token'] ?? '');
	let info = $state<RecoveryInfo | null>(null);
	let loading = $state(true);
	let busy = $state(false);
	let changed = $state(false);
	let submitted = $state(false);
	let error = $state('');
	let password = $state('');
	let confirm = $state('');
	let live = true;
	let generation = 0;
	$effect(() => { const current = token; untrack(() => void inspect(current)); });
	async function inspect(current: string) {
		const boundary = ++generation;
		info = null; error = ''; loading = true; changed = false; busy = false; password = ''; confirm = '';
		submitted = false;
		if (!isOnboardingToken(current)) { loading = false; error = t('onboarding.linkInvalid'); return; }
		try {
			// Username tickets are consumed by this read: never cache or retry it automatically.
			const result = await api.get<RecoveryInfo>(`/api/v1/auth/recovery/${encodeURIComponent(current)}`, undefined, undefined, { refresh: true, cache: 'no-store', suppressAuthRedirect: true, replayOnUnauthorized: false });
			if (live && boundary === generation) info = result;
		} catch (e) { if (live && boundary === generation) error = t(e instanceof ApiError && [404, 410].includes(e.status) ? 'onboarding.linkInvalid' : 'recovery.failed'); }
		finally { if (live && boundary === generation) loading = false; }
	}
	async function complete(event: SubmitEvent) {
		event.preventDefault();
		if (!info || info.kind === 'username' || busy || changed || submitted) return;
		if (info.kind === 'password' && (password.length < 12 || password.length > 1024 || password !== confirm)) {
			error = password !== confirm ? t('onboarding.passwordMismatch') : t('onboarding.passwordTooShort'); return;
		}
		const boundary = generation;
		const body = info.kind === 'password' ? { token, new_password: password } : { token };
		const path = info.kind === 'password' ? '/api/v1/auth/recovery/password/complete' : '/api/v1/auth/email/changes/accept';
		password = ''; confirm = ''; busy = true; error = '';
		submitted = true;
		try {
			await api.post(path, body, undefined, undefined, { suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: false });
			if (live && boundary === generation) changed = true;
		} catch (e) { if (live && boundary === generation) error = t(e instanceof ApiError && [404, 410].includes(e.status) ? 'onboarding.linkInvalid' : 'recovery.failed'); }
		finally { if (live && boundary === generation) busy = false; }
	}
	onDestroy(() => { live = false; generation++; info = null; password = ''; confirm = ''; });
</script>
<svelte:head><meta name="referrer" content="no-referrer" /><meta name="robots" content="noindex, nofollow" /></svelte:head>
<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas py-8 flex items-center justify-center">
	<PageShell class="flex justify-center"><div class="w-full max-w-md bg-surface-raised border border-line-2 rounded-xl p-5 sm:p-6 space-y-4">
		<h1 class="text-xl font-semibold text-ink-0">{t('recovery.title')}</h1>
		{#if loading}<ActivityIndicator label={t('onboarding.processing')} />{:else}
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			{#if changed}<Alert tone="success">{t('recovery.changed')}</Alert>
			{:else if info?.kind === 'username'}
				<Alert tone="info">{t('recovery.usernameResult')}</Alert>
				<dl class="space-y-2 text-sm text-ink-1"><dt>{t('onboarding.name')}</dt><dd class="font-mono break-all">{info.username}</dd><dt>{t('select.identityDomain')}</dt><dd class="break-all">{info.identity_domain_name}</dd><dd class="font-mono break-all">{info.identity_domain_id}</dd></dl>
			{:else if info}
				<p class="text-sm text-ink-1 break-all">{info.email}</p>
				<form onsubmit={complete} class="space-y-4">
					{#if info.kind === 'password'}
						<Field for="recover-password" label={t('onboarding.password')} help={t('onboarding.passwordHelp')} required><TextInput id="recover-password" type="password" autocomplete="new-password" bind:value={password} maxlength={1024} disabled={busy} required /></Field>
						<Field for="recover-confirm" label={t('onboarding.passwordConfirm')} required><TextInput id="recover-confirm" type="password" autocomplete="new-password" bind:value={confirm} maxlength={1024} disabled={busy} required /></Field>
					{:else}<Alert tone="info">{t('emailChange.confirm')}</Alert>{/if}
					<Button type="submit" disabled={busy || submitted} ariaBusy={busy}>{info.kind === 'password' ? t('recovery.reset') : t('emailChange.accept')}</Button>
				</form>
			{/if}
			<Button variant="link" href="/login" disabled={busy}>{t('common.backToLogin')}</Button>
			{#if !info || (error && submitted)}<Button variant="link" href="/recover">{t('recovery.requestAnother')}</Button>{/if}
		{/if}
	</div></PageShell>
</main>
