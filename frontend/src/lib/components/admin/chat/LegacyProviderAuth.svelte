<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { t } from '$lib/i18n/ns/admin-chat';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import { allowedDeviceUri, type AccountProvider, type DeviceAttempt } from './providerAccounts';

	type LegacyProvider = AccountProvider & { has_api_key?: boolean; has_credentials?: boolean; auth_status?: string; auth_expires_at?: string | null };
	let { provider, token, projectId, onupdated }: { provider: LegacyProvider; token?: string; projectId?: string; onupdated?: () => void | Promise<void> } = $props();
	let open = $state(false);
	let busy = $state(false);
	let error = $state('');
	let secret = $state('');
	let expiry = $state('');
	let attempt = $state<DeviceAttempt | null>(null);
	let epoch = 0;
	let destroyed = false;
	let authIdentity = '';
	let propIdentity = '';
	let pollTimer: ReturnType<typeof setTimeout> | undefined;
	const mode = $derived(provider.auth_mode ?? 'api_key');
	const inputClass = 'w-full rounded-lg border border-[var(--color-line-2)] bg-[var(--color-surface-sunken)] px-3 py-2 text-sm text-[var(--color-ink-0)]';
	const label = $derived(mode === 'api_key' ? t('configuration.changeKey') : mode === 'chatgpt_device' ? provider.has_credentials ? t('configuration.reconnectAlternate') : t('configuration.connect') : provider.has_credentials ? t('configuration.replaceToken') : t('configuration.registerToken'));

	function stopPolling() { if (pollTimer !== undefined) clearTimeout(pollTimer); pollTimer = undefined; }
	function reset() { ++epoch; stopPolling(); open = false; busy = false; error = ''; secret = ''; expiry = ''; attempt = null; }
	const unsubscribe = auth.subscribe((state) => {
		const identity = JSON.stringify([state.token, state.projectId, state.userId, state.sessionId, state.identityDomainId, state.domainId, state.isSystemAdmin, state.roles]);
		if (identity !== authIdentity) { authIdentity = identity; reset(); }
	});
	$effect(() => {
		const identity = JSON.stringify([provider.id, provider.auth_mode, token, projectId]);
		if (identity !== propIdentity) { propIdentity = identity; untrack(reset); }
	});
	onDestroy(() => { destroyed = true; reset(); unsubscribe(); });
	function context() {
		const generation = epoch, providerId = provider.id, requestMode = mode, requestToken = token, requestProject = projectId, identity = authIdentity;
		return { base: `/api/v1/chat/admin/providers/${providerId}`, token: requestToken, project: requestProject,
			current: () => !destroyed && epoch === generation && provider.id === providerId && mode === requestMode && token === requestToken && projectId === requestProject && authIdentity === identity };
	}
	// Never display upstream bodies that could echo a submitted API key or setup token.
	function failure(caught: unknown) {
		if (caught instanceof ApiError) {
			if (caught.status === 409) return t('configuration.completeOrCancelTheCurrentChatExecutionOrAnother');
			if (caught.status === 429) return t('configuration.authenticationRequestsAreRateLimitedCheckAgainManuallyIn');
			if (caught.status === 503) return t('configuration.couldNotConnectToTheSubscriptionAuthenticationProviderOr');
			return t('accounts.requestFailed', { status: caught.status });
		}
		return t('configuration.subscriptionAuthenticationRequestFailedTryAgain');
	}
	export function show() { if (!token || destroyed) return; reset(); open = true; }
	function close() {
		const ctx = context(), pending = attempt?.status === 'pending' ? attempt.attempt_id : null;
		reset();
		// Explicit dismissal cancels only the captured provider attempt using its original scope.
		if (pending && ctx.token) {
			const closed = context();
			void api.delete(`${ctx.base}/auth/device/${encodeURIComponent(pending)}`, ctx.token, ctx.project).catch(() => {
				if (closed.current()) toast.error(t('configuration.couldNotConfirmAuthenticationCancellationCheckTheServersExpiration'));
			});
		}
	}
	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (busy || !open || !token || mode === 'chatgpt_device' || (mode !== 'api_key' && !secret.trim())) return;
		let expiresAt: string | null = null;
		try { if (expiry) expiresAt = new Date(expiry).toISOString(); }
		catch { error = t('accounts.validation'); return; }
		const ctx = context(), submitted = secret.trim();
		secret = ''; busy = true; error = '';
		try {
			if (mode === 'api_key') await api.patch(ctx.base, { api_key: submitted || null }, ctx.token, ctx.project);
			else await api.put(`${ctx.base}/auth/token`, { token: submitted, expires_at: expiresAt }, ctx.token, ctx.project);
			if (!ctx.current() || !open) return;
			await onupdated?.();
			if (ctx.current() && open) reset();
		} catch (caught) { if (ctx.current() && open) error = failure(caught); }
		finally { if (ctx.current()) busy = false; }
	}
	async function disconnect() {
		if (busy || !token) return;
		const ctx = context();
		if (!(await confirmDialog(t('configuration.disconnectTheSubscriptionForRegisteredModelsWillBeKept', { v0: provider.name }))) || !ctx.current()) return;
		busy = true; error = '';
		try {
			await api.delete(`${ctx.base}/auth`, ctx.token, ctx.project);
			if (!ctx.current()) return;
			await onupdated?.();
			if (ctx.current()) reset();
		} catch (caught) { if (ctx.current()) error = failure(caught); }
		finally { if (ctx.current()) busy = false; }
	}
	function schedulePoll() {
		stopPolling();
		if (!attempt || attempt.status !== 'pending') return;
		const remaining = Date.parse(attempt.expires_at) - Date.now();
		if (remaining <= 0) { attempt = { ...attempt, status: 'expired', user_code: undefined, verification_uri: undefined }; return; }
		pollTimer = setTimeout(() => void deviceAction('poll'), Math.min(remaining, Math.max(1, attempt.interval_seconds) * 1000));
	}
	async function deviceAction(action: 'start' | 'poll' | 'cancel') {
		if (busy || !open || !token || mode !== 'chatgpt_device' || (action !== 'start' && attempt?.status !== 'pending')) return;
		const ctx = context(), previous = attempt;
		busy = true; error = ''; stopPolling();
		try {
			const path = `${ctx.base}/auth/device`;
			if (action === 'cancel') {
				await api.delete(`${path}/${encodeURIComponent(previous!.attempt_id)}`, ctx.token, ctx.project);
				if (ctx.current() && open) attempt = { ...previous!, status: 'cancelled', user_code: undefined, verification_uri: undefined };
			} else {
				const result = await api.post<DeviceAttempt>(action === 'start' ? path : `${path}/${encodeURIComponent(previous!.attempt_id)}/poll`, {}, ctx.token, ctx.project);
				if (!ctx.current() || !open) return;
				attempt = result.status === 'pending' ? { ...previous, ...result } : { ...result, user_code: undefined, verification_uri: undefined };
				if (result.status === 'connected') await onupdated?.();
				else schedulePoll();
			}
		} catch (caught) { if (ctx.current() && open) error = action === 'cancel' ? t('configuration.theAuthenticationRequestOnTheServerMayRemainActive', { v0: failure(caught) }) : failure(caught); }
		finally { if (ctx.current()) busy = false; }
	}
	async function copyCode() {
		if (!attempt?.user_code) return;
		const ctx = context();
		try { await navigator.clipboard.writeText(attempt.user_code); if (ctx.current() && open) toast.success(t('configuration.authenticationCodeCopied')); }
		catch { if (ctx.current() && open) error = t('configuration.couldNotCopyAuthenticationCode'); }
	}
</script>

{#if mode === 'api_key'}
	<Pill size="xs" tone={provider.has_api_key ? 'success' : 'warning'}>{provider.has_api_key ? t('configuration.keyConfigured') : t('configuration.noKey')}</Pill>
{:else}
	<Pill size="xs" tone={provider.auth_status === 'configured' ? 'success' : 'warning'}>{provider.auth_status === 'configured' ? t('configuration.connected') : provider.auth_status === 'reauth_required' ? t('configuration.reconnectRequired') : t('configuration.authenticationNotConnected')}</Pill>
	{#if provider.auth_expires_at}<span class="text-xs text-[var(--color-ink-2)]">{t('configuration.credentialExpiry', { v0: new Date(provider.auth_expires_at).toLocaleString(intlLocale()) })}</span>{/if}
{/if}
<Button variant="outline" size="sm" onclick={show} disabled={busy || !token}>{label}</Button>
{#if mode !== 'api_key' && provider.auth_status !== 'disconnected'}<Button variant="ghost" size="sm" onclick={disconnect} disabled={busy || !token}>{t('configuration.disconnect')}</Button>{/if}
{#if error && !open}<Alert tone="danger">{error}</Alert>{/if}
<Modal bind:open onClose={close} ariaLabel={mode === 'api_key' ? t('configuration.changeKey') : t('configuration.subscriptionAuthentication')}>
	<div class="max-h-[calc(100dvh-2rem)] w-[min(36rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 sm:p-5">
		<div class="flex items-start justify-between gap-3"><div><h3 class="text-base font-semibold text-[var(--color-ink-0)]">{mode === 'api_key' ? t('configuration.changeKey') : mode === 'chatgpt_device' ? t('configuration.connectChatgptSubscription') : t('configuration.registerClaudeSubscriptionToken')}</h3><p class="mt-1 break-all text-sm text-[var(--color-ink-2)]">{provider.name}</p></div><Button variant="ghost" onclick={close}>{t('configuration.close')}</Button></div>
		{#if mode !== 'api_key'}<Alert tone="warning" title={`${t('configuration.experimental')} · ${t('configuration.sharedByAllUsers')}`} class="mt-4">{t('configuration.thisConnectionIsSharedByAllAfterglowUsersUse')}</Alert>{/if}
		{#if error}<Alert tone="danger" class="mt-3">{error}</Alert>{/if}
		{#if mode !== 'chatgpt_device'}
			<form class="mt-4 space-y-4" onsubmit={save} aria-label={mode === 'api_key' ? t('configuration.changeKey') : t('configuration.registerClaudeSubscriptionToken')}>
				{#if mode === 'api_key'}<p class="text-sm text-[var(--color-ink-2)]">{t('configuration.enterANewApiKeyForLeaveBlankTo', { v0: provider.name })}</p>{:else}<p class="text-sm text-[var(--color-ink-2)]">{#snippet command(text: string)}<code class="font-mono">{text}</code>{/snippet}<RichText segments={t.rich('configuration.claudeSetupTokenGuidance')} tags={{ markup1: command }} /></p>{/if}
				<Field label={mode === 'api_key' ? t('configuration.apiKey') : t('configuration.claudeSetupToken')} for="legacy-secret-{provider.id}"><TextInput id="legacy-secret-{provider.id}" type="password" bind:value={secret} required={mode !== 'api_key'} disabled={busy} autocomplete="new-password" /></Field>
				{#if mode === 'anthropic_subscription'}<Field label={t('configuration.expirationTime')} for="legacy-expiry-{provider.id}" help={t('configuration.enterOnlyIfTheProviderSpecifiedAnExpirationTime')}><input id="legacy-expiry-{provider.id}" class={inputClass} type="datetime-local" bind:value={expiry} disabled={busy} /></Field>{/if}
				<div class="flex flex-wrap justify-end gap-2">{#if mode === 'anthropic_subscription'}<Button variant="secondary" href="https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan" target="_blank">{t('configuration.officialGuidance')}</Button>{/if}<Button type="submit" disabled={busy || (mode !== 'api_key' && !secret.trim())} ariaBusy={busy}>{mode === 'api_key' ? t('configuration.save') : t('configuration.registerToken')}</Button></div>
			</form>
		{:else}
			<div class="mt-4 space-y-3">
				<p class="text-sm text-[var(--color-ink-2)]">{t('configuration.startingTheConnectionDisplaysAnOpenaiAuthenticationPageAnd')}</p>
				{#if attempt}
					<p role="status">{attempt.status === 'pending' ? t('configuration.awaitingAuthentication') : attempt.status === 'connected' ? t('configuration.connected') : attempt.status === 'expired' ? t('configuration.authenticationExpired') : attempt.status === 'cancelled' ? t('configuration.authenticationCanceled') : t('configuration.authenticationError')}</p>
					<p class="text-xs text-[var(--color-ink-2)]">{t('configuration.deviceCredentialExpiry', { v0: new Date(attempt.expires_at).toLocaleString(intlLocale()) })}</p>
					{#if attempt.status === 'pending'}
						{#if attempt.user_code}<p class="text-xs text-[var(--color-ink-2)]">{t('configuration.oneTimeAuthenticationCode')}</p><code class="block break-all rounded-lg bg-[var(--color-surface-sunken)] p-3 text-lg text-[var(--color-ink-0)]">{attempt.user_code}</code><Button variant="secondary" onclick={copyCode}>{t('configuration.copyCode')}</Button>{/if}
						{@const uri = allowedDeviceUri(attempt.verification_uri)}
						{#if uri}<Button variant="secondary" href={uri} target="_blank">{t('configuration.openOpenaiAuthenticationPage')}</Button>{:else if attempt.verification_uri}<Alert tone="danger">{t('configuration.theAuthenticationUrlWasNotOpenedBecauseItIs')}</Alert>{/if}
						<div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={busy} onclick={() => deviceAction('poll')}>{t('configuration.checkNow')}</Button><Button variant="danger-outline" disabled={busy} onclick={() => deviceAction('cancel')}>{t('configuration.cancelAuthentication')}</Button></div>
					{/if}
				{/if}
				{#if !attempt || (attempt.status !== 'pending' && attempt.status !== 'connected')}<Button disabled={busy} ariaBusy={busy} onclick={() => deviceAction('start')}>{t('configuration.connectChatgpt')}</Button>{/if}
			</div>
		{/if}
	</div>
</Modal>
