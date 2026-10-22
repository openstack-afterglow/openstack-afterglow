<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { t } from '$lib/i18n/ns/admin-chat';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import { allowedDeviceUri, eligibility, eligibilityDraft, localTimestamp, type AccountProvider, type ProviderAccount, type ProviderCredential, type AccountUsage, type DeviceAttempt } from './providerAccounts';

	let { provider, token, projectId, onupdated }: { provider: AccountProvider; token?: string; projectId?: string; onupdated?: () => void | Promise<void> } = $props();
	let open = $state(false);
	let accounts = $state<ProviderAccount[]>([]);
	let loading = $state(false);
	let busy = $state(false);
	let error = $state('');
	let policy = $state('priority');
	let selected = $state('');
	let usage = $state<Record<number, AccountUsage>>({});
	let editor = $state<{ kind: 'account' | 'credential'; accountId?: number; credentialId?: number } | null>(null);
	let name = $state('');
	let priority = $state('0');
	let weight = $state('1');
	let modelIds = $state('');
	let operations = $state('');
	let quotaGroup = $state('');
	let secret = $state('');
	let keySource = $state('preserve');
	let environment = $state('');
	let expiry = $state('');
	let cooldown = $state('');
	let authTarget = $state<{ accountId: number; credential: ProviderCredential } | null>(null);
	let attempt = $state<DeviceAttempt | null>(null);
	let tokenSecret = $state('');
	let tokenExpiry = $state('');
	let epoch = 0;
	let readGeneration = 0;
	let destroyed = false;
	let authIdentity = '';
	let propScopeIdentity = '';
	let pollTimer: ReturnType<typeof setTimeout> | undefined;
	const mode = $derived(provider.auth_mode ?? 'api_key');
	const credentials = $derived(accounts.flatMap((account) => account.credentials.map((credential) => ({ account, credential }))));
	const inputClass = 'w-full rounded-lg border border-[var(--color-line-2)] bg-[var(--color-surface-sunken)] px-3 py-2 text-sm text-[var(--color-ink-0)]';

	function stopPolling() { if (pollTimer !== undefined) clearTimeout(pollTimer); pollTimer = undefined; }
	function clearEditor() { editor = null; secret = ''; environment = ''; name = ''; expiry = ''; cooldown = ''; }
	function clearAuth() { stopPolling(); authTarget = null; attempt = null; tokenSecret = ''; tokenExpiry = ''; }
	function reset() { ++epoch; ++readGeneration; open = false; accounts = []; usage = {}; loading = false; busy = false; error = ''; clearEditor(); clearAuth(); }
	const unsubscribe = auth.subscribe((state) => {
		const identity = JSON.stringify([state.token, state.projectId, state.userId, state.sessionId, state.identityDomainId, state.domainId, state.isSystemAdmin, state.roles]);
		if (identity !== authIdentity) { authIdentity = identity; reset(); }
	});
	$effect(() => {
		const identity = JSON.stringify([provider.id, provider.auth_mode, token, projectId]);
		if (identity === propScopeIdentity) return;
		propScopeIdentity = identity;
		untrack(reset);
	});
	onDestroy(() => { destroyed = true; reset(); unsubscribe(); });

	function context() {
		const generation = epoch, providerId = provider.id, requestToken = token, requestProject = projectId, identity = authIdentity;
		return { base: `/api/v1/chat/admin/providers/${providerId}`, token: requestToken, project: requestProject,
			current: () => !destroyed && open && epoch === generation && provider.id === providerId && token === requestToken && projectId === requestProject && identity === authIdentity };
	}
	// Only status codes are surfaced: upstream error bodies may echo a submitted secret.
	function failure(caught: unknown) { return caught instanceof ApiError ? t('accounts.requestFailed', { status: caught.status }) : t('accounts.networkError'); }
	function timestamp(value: string) { if (!value) return null; const date = new Date(value); if (!Number.isFinite(date.getTime())) throw new Error('timestamp'); return date.toISOString(); }
	function displayTime(value: string | null) { return value ? new Date(value).toLocaleString(intlLocale()) : t('accounts.unset'); }
	function credentialPath(accountId: number, credentialId: number) { return `/accounts/${accountId}/credentials/${credentialId}`; }
	async function load() {
		const ctx = context(), request = ++readGeneration;
		loading = true;
		try {
			const result = await api.get<ProviderAccount[]>(`${ctx.base}/accounts`, ctx.token, ctx.project);
			if (ctx.current() && request === readGeneration) accounts = result;
		} catch (caught) { if (ctx.current() && request === readGeneration) error = failure(caught); }
		finally { if (ctx.current() && request === readGeneration) loading = false; }
	}
	export function show() { reset(); open = true; policy = provider.selection_policy ?? 'priority'; selected = provider.selected_credential_id?.toString() ?? ''; void load(); }
	function close() { reset(); }
	async function mutate(action: (ctx: ReturnType<typeof context>) => Promise<unknown>, after?: () => void) {
		if (busy || !open || !token) return;
		const ctx = context(); busy = true; error = '';
		try {
			await action(ctx);
			if (!ctx.current()) return;
			after?.(); usage = {};
			await load();
			if (ctx.current()) await onupdated?.();
		} catch (caught) { if (ctx.current()) error = failure(caught); }
		finally { if (ctx.current()) busy = false; }
	}
	function editAccount(account?: ProviderAccount) {
		if (busy) return; clearAuth(); clearEditor(); error = '';
		editor = { kind: 'account', accountId: account?.id };
		name = account?.name ?? ''; priority = String(account?.priority ?? 0); weight = String(account?.weight ?? 1);
		modelIds = eligibilityDraft(account?.allowed_model_ids ?? null); operations = eligibilityDraft(account?.allowed_capabilities ?? null); quotaGroup = account?.quota_group ?? '';
	}
	function editCredential(accountId: number, credential?: ProviderCredential) {
		if (busy) return; clearAuth(); clearEditor(); error = '';
		editor = { kind: 'credential', accountId, credentialId: credential?.id };
		name = credential?.name ?? ''; priority = String(credential?.priority ?? 0); weight = String(credential?.weight ?? 1);
		modelIds = eligibilityDraft(credential?.allowed_model_ids ?? null); operations = eligibilityDraft(credential?.allowed_capabilities ?? null);
		expiry = localTimestamp(credential?.expires_at ?? null); cooldown = localTimestamp(credential?.cooldown_until ?? null);
		keySource = credential ? 'preserve' : 'stored'; environment = credential?.api_key_env ?? '';
	}
	async function saveEntry(event: SubmitEvent) {
		event.preventDefault(); if (!editor || busy) return;
		const target = editor;
		let body: Record<string, unknown>;
		try {
			if (!name.trim() || name.trim().length > 100 || !/^\d+$/.test(priority) || !/^\d+$/.test(weight) || Number(priority) > 2147483647 || Number(weight) < 1 || Number(weight) > 2147483647) throw new Error('validation');
			body = { name: name.trim(), priority: Number(priority), weight: Number(weight), allowed_model_ids: eligibility(modelIds, true), allowed_capabilities: eligibility(operations) };
			if (target.kind === 'account') { if (quotaGroup.length > 100) throw new Error('quota'); body.quota_group = quotaGroup.trim() || null; }
			else {
				body.expires_at = timestamp(expiry); body.cooldown_until = timestamp(cooldown);
				if (mode === 'api_key' && keySource !== 'preserve') {
					if (keySource === 'stored' && !secret.trim()) throw new Error('secret');
					if (keySource === 'environment' && !/^[A-Z_][A-Z0-9_]{0,127}$/.test(environment.trim())) throw new Error('environment');
					body.api_key = keySource === 'stored' ? secret.trim() : null;
					body.api_key_env = keySource === 'environment' ? environment.trim() : null;
				}
			}
		} catch { error = t('accounts.validation'); return; }
		secret = '';
		const suffix = target.kind === 'account' ? `/accounts${target.accountId ? `/${target.accountId}` : ''}` : `/accounts/${target.accountId}/credentials${target.credentialId ? `/${target.credentialId}` : ''}`;
		await mutate((ctx) => target.kind === 'account' ? target.accountId ? api.patch(`${ctx.base}${suffix}`, body, ctx.token, ctx.project) : api.post(`${ctx.base}${suffix}`, body, ctx.token, ctx.project) : target.credentialId ? api.patch(`${ctx.base}${suffix}`, body, ctx.token, ctx.project) : api.post(`${ctx.base}${suffix}`, body, ctx.token, ctx.project), clearEditor);
	}
	async function remove(account: ProviderAccount, credential?: ProviderCredential) {
		if (busy) return;
		const ctx = context();
		if (!(await confirmDialog(t(credential ? 'accounts.confirmCredentialDelete' : 'accounts.confirmAccountDelete', { name: credential?.name ?? account.name }))) || !ctx.current()) return;
		const suffix = credential ? credentialPath(account.id, credential.id) : `/accounts/${account.id}`;
		await mutate((request) => api.delete(`${request.base}${suffix}`, request.token, request.project), () => { clearEditor(); clearAuth(); });
	}
	async function savePolicy() {
		if (policy === 'explicit' && !credentials.some(({ credential }) => String(credential.id) === selected)) { error = t('accounts.selectCredential'); return; }
		await mutate((ctx) => api.patch(ctx.base, { selection_policy: policy, selected_credential_id: policy === 'explicit' ? Number(selected) : null }, ctx.token, ctx.project));
	}
	async function loadUsage(accountId: number) {
		if (busy) return;
		const ctx = context(); busy = true; error = '';
		try {
			const result = await api.get<AccountUsage>(`${ctx.base}/accounts/${accountId}/usage`, ctx.token, ctx.project);
			if (ctx.current()) usage = { ...usage, [accountId]: result };
		} catch (caught) { if (ctx.current()) error = failure(caught); }
		finally { if (ctx.current()) busy = false; }
	}
	function authenticate(accountId: number, credential: ProviderCredential) { if (busy) return; clearEditor(); clearAuth(); error = ''; authTarget = { accountId, credential }; }
	async function saveToken(event: SubmitEvent) {
		event.preventDefault(); if (!authTarget || !tokenSecret.trim()) return;
		let body: { token: string; expires_at: string | null };
		try { body = { token: tokenSecret.trim(), expires_at: timestamp(tokenExpiry) }; } catch { error = t('accounts.validation'); return; }
		const path = credentialPath(authTarget.accountId, authTarget.credential.id); tokenSecret = '';
		await mutate((ctx) => api.put(`${ctx.base}${path}/auth/token`, body, ctx.token, ctx.project), clearAuth);
	}
	async function disconnect(accountId: number, credential: ProviderCredential) {
		const ctx = context();
		if (busy || !(await confirmDialog(t('accounts.confirmDisconnect', { name: credential.name }))) || !ctx.current()) return;
		await mutate((request) => api.delete(`${request.base}${credentialPath(accountId, credential.id)}/auth`, request.token, request.project), clearAuth);
	}
	function schedulePoll() {
		stopPolling(); if (!attempt || attempt.status !== 'pending') return;
		const remaining = Date.parse(attempt.expires_at) - Date.now();
		if (remaining <= 0) { attempt = { ...attempt, status: 'expired', user_code: undefined, verification_uri: undefined }; return; }
		pollTimer = setTimeout(() => void deviceAction('poll'), Math.min(remaining, Math.max(1, attempt.interval_seconds) * 1000));
	}
	async function deviceAction(action: 'start' | 'poll' | 'cancel') {
		if (!authTarget || busy || (action !== 'start' && attempt?.status !== 'pending')) return;
		const ctx = context(), target = authTarget, previous = attempt;
		const path = `${ctx.base}${credentialPath(target.accountId, target.credential.id)}/auth/device`;
		busy = true; error = ''; stopPolling();
		try {
			if (action === 'cancel') {
				await api.delete(`${path}/${encodeURIComponent(previous!.attempt_id)}`, ctx.token, ctx.project);
				if (ctx.current() && authTarget === target) attempt = { ...previous!, status: 'cancelled', user_code: undefined, verification_uri: undefined };
			} else {
				const result = await api.post<DeviceAttempt>(action === 'start' ? path : `${path}/${encodeURIComponent(previous!.attempt_id)}/poll`, {}, ctx.token, ctx.project);
				if (!ctx.current() || authTarget !== target) return;
				attempt = result.status === 'pending' ? { ...previous, ...result } : { ...result, user_code: undefined, verification_uri: undefined };
				if (result.status === 'connected') { await load(); if (ctx.current()) await onupdated?.(); }
				else schedulePoll();
			}
		} catch (caught) { if (ctx.current() && authTarget === target) error = failure(caught); }
		finally { if (ctx.current() && authTarget === target) busy = false; }
	}
</script>

<Button variant="outline" size="sm" onclick={show}>{t('accounts.manage')}</Button>
<Modal bind:open onClose={close} ariaLabel={t('accounts.manage')}>
	<div class="max-h-[calc(100dvh-2rem)] w-[min(58rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-surface-raised)] p-4 sm:p-6">
		<div class="flex items-start justify-between gap-3"><div><h3 class="text-base font-semibold text-[var(--color-ink-0)]">{t('accounts.manage')}</h3><p class="mt-1 break-all text-sm text-[var(--color-ink-2)]">{provider.name}</p></div><Button variant="ghost" onclick={close}>{t('configuration.close')}</Button></div>
		<p class="mt-3 text-sm text-[var(--color-ink-2)]">{t('accounts.scopeNotice')}</p>
		{#if mode !== 'api_key'}<Alert tone="warning" class="mt-3">{t('accounts.subscriptionPolicy')}</Alert>{/if}
		{#if error}<Alert tone="danger" class="mt-3">{error}</Alert>{/if}
		<div class="mt-4 grid gap-3 sm:grid-cols-2">
			<Field label={t('accounts.selectionPolicy')} for="pool-policy"><SelectInput id="pool-policy" bind:value={policy} disabled={busy}><option value="priority">{t('accounts.priorityPolicy')}</option><option value="weighted">{t('accounts.weightedPolicy')}</option><option value="explicit">{t('accounts.explicitPolicy')}</option></SelectInput></Field>
			{#if policy === 'explicit'}<Field label={t('accounts.selectedCredential')} for="pool-credential"><SelectInput id="pool-credential" bind:value={selected} disabled={busy}><option value="">{t('accounts.selectCredential')}</option>{#each credentials as item (item.credential.id)}<option value={String(item.credential.id)}>{item.account.name} / {item.credential.name} (#{item.credential.id})</option>{/each}</SelectInput></Field>{/if}
		</div>
		<p class="mt-2 text-xs text-[var(--color-ink-2)]">{t('accounts.policyHelp')}</p>
		<div class="mt-3 flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={busy || loading} onclick={savePolicy}>{t('accounts.savePolicy')}</Button><Button size="sm" disabled={busy} onclick={() => editAccount()}>{t('accounts.addAccount')}</Button><Button variant="ghost" size="sm" disabled={busy || loading} onclick={() => { error = ''; void load(); }}>{t('configuration.refreshAll')}</Button></div>
		{#if editor}
			<form class="mt-4 space-y-3 rounded-lg border border-[var(--color-line)] p-4" onsubmit={saveEntry} aria-label={t(editor.kind === 'account' ? 'accounts.accountEditor' : 'accounts.credentialEditor')}>
				<h4 class="font-medium text-[var(--color-ink-0)]">{t(editor.kind === 'account' ? 'accounts.accountEditor' : 'accounts.credentialEditor')}</h4>
				<div class="grid gap-3 sm:grid-cols-2">
					<Field label={t('accounts.name')} for="pool-name"><TextInput id="pool-name" bind:value={name} required disabled={busy} /></Field>
					{#if editor.kind === 'account'}<Field label={t('accounts.quotaGroup')} for="pool-quota"><TextInput id="pool-quota" bind:value={quotaGroup} disabled={busy} /></Field>{/if}
					<Field label={t('accounts.priority')} for="pool-priority"><TextInput id="pool-priority" bind:value={priority} disabled={busy} /></Field>
					<Field label={t('accounts.weight')} for="pool-weight"><TextInput id="pool-weight" bind:value={weight} disabled={busy} /></Field>
					<Field label={t('accounts.modelIds')} for="pool-models"><TextInput id="pool-models" bind:value={modelIds} disabled={busy} /></Field>
					<Field label={t('accounts.operations')} for="pool-operations"><TextInput id="pool-operations" bind:value={operations} disabled={busy} /></Field>
					{#if editor.kind === 'credential'}
						<Field label={t('configuration.expirationTime')} for="pool-expiry"><input class={inputClass} id="pool-expiry" type="datetime-local" bind:value={expiry} disabled={busy} /></Field>
						<Field label={t('accounts.cooldown')} for="pool-cooldown"><input class={inputClass} id="pool-cooldown" type="datetime-local" bind:value={cooldown} disabled={busy} /></Field>
						{#if mode === 'api_key'}
							<Field label={t('accounts.keySource')} for="pool-source"><SelectInput id="pool-source" bind:value={keySource} disabled={busy} onchange={() => { secret = ''; }}>{#if editor.credentialId}<option value="preserve">{t('accounts.preserveKey')}</option>{/if}<option value="stored">{t('accounts.storedKey')}</option><option value="environment">{t('accounts.environmentKey')}</option><option value="none">{t('accounts.noKey')}</option></SelectInput></Field>
							{#if keySource === 'stored'}<Field label={t('configuration.apiKey')} for="pool-secret"><TextInput id="pool-secret" type="password" bind:value={secret} disabled={busy} required autocomplete="new-password" /></Field>{:else if keySource === 'environment'}<Field label={t('accounts.environmentName')} for="pool-env"><TextInput id="pool-env" bind:value={environment} disabled={busy} required /></Field>{/if}
						{/if}
					{/if}
				</div>
				<p class="text-xs text-[var(--color-ink-2)]">{t('accounts.eligibilityHelp')}</p>
				<div class="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={busy} onclick={clearEditor}>{t('configuration.cancel')}</Button><Button type="submit" disabled={busy} ariaBusy={busy}>{t('accounts.save')}</Button></div>
			</form>
		{/if}
		{#if authTarget}
			<section class="mt-4 space-y-3 rounded-lg border border-[var(--color-line)] p-4" aria-label={t('configuration.subscriptionAuthentication')}>
				<div class="flex justify-between gap-2"><h4 class="break-all font-medium text-[var(--color-ink-0)]">{authTarget.credential.name}</h4><Button variant="ghost" size="sm" disabled={busy} onclick={clearAuth}>{t('configuration.close')}</Button></div>
				{#if mode === 'anthropic_subscription'}
					<form class="space-y-3" onsubmit={saveToken}>
						<p class="text-xs text-[var(--color-ink-2)]">{t('accounts.claudeTokenHelp')}</p>
						<Field label={t('configuration.claudeSetupToken')} for="pool-token"><TextInput id="pool-token" type="password" bind:value={tokenSecret} required disabled={busy} autocomplete="new-password" /></Field>
						<Field label={t('configuration.expirationTime')} for="pool-token-expiry"><input class={inputClass} id="pool-token-expiry" type="datetime-local" bind:value={tokenExpiry} disabled={busy} /></Field>
						<Button type="submit" disabled={busy || !tokenSecret.trim()} ariaBusy={busy}>{t('configuration.registerToken')}</Button>
					</form>
				{:else}
					<p class="text-xs text-[var(--color-ink-2)]">{t('accounts.deviceCloseNotice')}</p>
					{#if attempt}
						<p role="status">{t(`accounts.deviceStatus.${attempt.status}`)}</p>
						<p class="text-xs text-[var(--color-ink-2)]">{t('configuration.credentialExpiry', { v0: displayTime(attempt.expires_at) })}</p>
						{#if attempt.status === 'pending'}
							{#if attempt.user_code}<code class="block break-all rounded-lg bg-[var(--color-surface-sunken)] p-3 text-lg text-[var(--color-ink-0)]">{attempt.user_code}</code>{/if}
							{@const uri = allowedDeviceUri(attempt.verification_uri)}
							{#if uri}<Button variant="secondary" href={uri} target="_blank">{t('configuration.openOpenaiAuthenticationPage')}</Button>{:else if attempt.verification_uri}<Alert tone="danger">{t('configuration.theAuthenticationUrlWasNotOpenedBecauseItIs')}</Alert>{/if}
							<div class="flex flex-wrap gap-2"><Button variant="secondary" disabled={busy} onclick={() => deviceAction('poll')}>{t('configuration.checkNow')}</Button><Button variant="danger-outline" disabled={busy} onclick={() => deviceAction('cancel')}>{t('configuration.cancelAuthentication')}</Button></div>
						{/if}
					{/if}
					{#if !attempt || (attempt.status !== 'pending' && attempt.status !== 'connected')}<Button disabled={busy} ariaBusy={busy} onclick={() => deviceAction('start')}>{t('configuration.connectChatgpt')}</Button>{/if}
				{/if}
			</section>
		{/if}
		{#if loading}<p class="mt-4 text-sm text-[var(--color-ink-2)]" role="status">{t('accounts.loading')}</p>{/if}
		{#if !loading && accounts.length === 0}<p class="mt-4 text-sm text-[var(--color-ink-2)]">{t('accounts.empty')}</p>{/if}
		<div class="mt-4 space-y-4">
			{#each accounts as account (account.id)}
				<section class="rounded-lg border border-[var(--color-line)] p-3 sm:p-4" aria-label={account.name}>
					<div class="flex flex-wrap items-center justify-between gap-2"><div class="flex min-w-0 flex-wrap items-center gap-2"><h4 class="break-all font-medium text-[var(--color-ink-0)]">{account.name} <span class="text-xs text-[var(--color-ink-2)]">#{account.id}</span></h4><Pill tone={account.is_active ? 'success' : 'neutral'}>{account.is_active ? t('configuration.active') : t('configuration.inactive')}</Pill></div><div class="flex flex-wrap gap-2"><Button variant="ghost" size="sm" disabled={busy} onclick={() => editAccount(account)}>{t('accounts.edit')}</Button><Button variant="ghost" size="sm" disabled={busy} onclick={() => mutate((ctx) => api.patch(`${ctx.base}/accounts/${account.id}`, { is_active: !account.is_active }, ctx.token, ctx.project))}>{account.is_active ? t('configuration.deactivate') : t('configuration.activate')}</Button><Button variant="danger-outline" size="sm" disabled={busy} onclick={() => remove(account)}>{t('configuration.delete')}</Button></div></div>
					<p class="mt-2 break-all text-xs text-[var(--color-ink-2)]">{t('accounts.poolSummary', { priority: account.priority, weight: account.weight })} · {t('accounts.quotaGroup')}: {account.quota_group ?? t('accounts.unset')}</p>
					<p class="mt-1 break-all text-xs text-[var(--color-ink-2)]">{t('accounts.modelIds')}: {eligibilityDraft(account.allowed_model_ids) || t('accounts.unrestricted')} · {t('accounts.operations')}: {eligibilityDraft(account.allowed_capabilities) || t('accounts.unrestricted')}</p>
					<div class="mt-3 flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={busy} onclick={() => editCredential(account.id)}>{t('accounts.addCredential')}</Button><Button variant="ghost" size="sm" disabled={busy} onclick={() => loadUsage(account.id)}>{t('accounts.usage')}</Button></div>
					{#if usage[account.id]}
						<div class="mt-3 space-y-2 text-xs text-[var(--color-ink-2)]" aria-label={t('accounts.usage')}><p>{t('accounts.usageNotice')}</p>{#each usage[account.id].credentials as row}<p class="break-all">{t('accounts.usageRow', { id: row.credential_id ?? '-', requests: row.requests, input: row.prompt_tokens, output: row.completion_tokens, cost: row.raw_cost })}</p>{:else}<p>{t('accounts.noUsage')}</p>{/each}</div>
					{/if}
					{#each account.credentials as credential (credential.id)}
						<div class="mt-3 border-t border-[var(--color-line)] pt-3" data-credential-id={credential.id}>
							<div class="flex flex-wrap items-center gap-2"><span class="break-all text-sm font-medium text-[var(--color-ink-0)]">{credential.name} (#{credential.id})</span><Pill size="xs" tone={credential.is_active ? 'success' : 'neutral'}>{credential.is_active ? t('configuration.active') : t('configuration.inactive')}</Pill><Pill size="xs" tone={credential.auth_mode === 'api_key' ? credential.api_key_configured ? 'success' : 'warning' : credential.subscription_status === 'configured' ? 'success' : 'warning'}>{credential.auth_mode === 'api_key' ? credential.api_key_configured ? t('configuration.keyConfigured') : t('configuration.noKey') : credential.subscription_status === 'configured' ? t('configuration.connected') : credential.subscription_status === 'reauth_required' ? t('configuration.reconnectRequired') : t('configuration.authenticationNotConnected')}</Pill></div>
							<p class="mt-1 break-all text-xs text-[var(--color-ink-2)]">{t('accounts.poolSummary', { priority: credential.priority, weight: credential.weight })} · {t('accounts.generation', { generation: credential.generation })}{credential.api_key_env ? ` · ${credential.api_key_env}` : ''}</p>
							<p class="mt-1 break-all text-xs text-[var(--color-ink-2)]">{t('accounts.modelIds')}: {eligibilityDraft(credential.allowed_model_ids) || t('accounts.unrestricted')} · {t('accounts.operations')}: {eligibilityDraft(credential.allowed_capabilities) || t('accounts.unrestricted')}</p>
							<p class="mt-1 break-all text-xs text-[var(--color-ink-2)]">{t('configuration.expirationTime')}: {displayTime(credential.expires_at)} · {t('accounts.cooldown')}: {displayTime(credential.cooldown_until)}{credential.subscription_expires_at ? ` · ${t('configuration.credentialExpiry', { v0: displayTime(credential.subscription_expires_at) })}` : ''}</p>
							<div class="mt-2 flex flex-wrap gap-2"><Button variant="ghost" size="sm" disabled={busy} onclick={() => editCredential(account.id, credential)}>{t('accounts.editCredential')}</Button><Button variant="ghost" size="sm" disabled={busy} onclick={() => mutate((ctx) => api.patch(`${ctx.base}${credentialPath(account.id, credential.id)}`, { is_active: !credential.is_active }, ctx.token, ctx.project))}>{credential.is_active ? t('configuration.deactivate') : t('configuration.activate')}</Button>{#if credential.auth_mode !== 'api_key'}<Button variant="secondary" size="sm" disabled={busy} onclick={() => authenticate(account.id, credential)}>{t('configuration.connect')}</Button><Button variant="ghost" size="sm" disabled={busy} onclick={() => disconnect(account.id, credential)}>{t('configuration.disconnect')}</Button>{/if}<Button variant="danger-outline" size="sm" disabled={busy} onclick={() => remove(account, credential)}>{t('configuration.delete')}</Button></div>
						</div>
					{/each}
				</section>
			{/each}
		</div>
	</div>
</Modal>
