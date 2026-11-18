<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { api, ApiError } from '$lib/api/client';
	import { currentBillingSession, domainBillingErrorMessage, exceedsDomainCeiling, lumenBrowserPath, modelKeyScopeLabel, readKeyIssuancePolicy, validDomainCredit, type DomainPool, type ServiceKey } from '$lib/api/chatDomainBilling';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import DomainPoolMetrics from './DomainPoolMetrics.svelte';
	import IssuedLumenKey from './IssuedLumenKey.svelte';

	let { scopeKey }: { scopeKey: string } = $props();
	const id = $props.id();
	const keysPath = `${lumenBrowserPath}/service-keys`;
	const poolPath = `${lumenBrowserPath}/domain-pool`;
	// Lumen's issuance policy is the only source of offered model-key scopes.
	let scopes = $state<string[] | null>(null);
	let scopesError = $state('');
	let policyRequest = 0;
	let alive = true;
	onDestroy(() => { alive = false; });
	let denied = $state(false);
	let keys = $state<ServiceKey[] | null>(null);
	let pool = $state<DomainPool | null>(null);
	let keysError = $state('');
	let poolError = $state('');
	let createError = $state('');
	let formOpen = $state(false);
	let issued = $state<string | null>(null);
	let name = $state('');
	let selected = $state<string[]>([]);
	let busy = $state<'create' | 'revoke' | 'limit' | null>(null);
	let managerLimit = $state('');
	let limitError = $state('');
	let limitInput = $state<HTMLInputElement | null>(null);

	const session = () => alive ? currentBillingSession(scopeKey, 'manager') : null;
	function requireCurrent() {
		if (!session()) throw new DOMException('Billing authority changed', 'AbortError');
	}
	const mutation = { replayOnUnauthorized: false, beforeDispatch: requireCurrent };
	const read = { cache: 'no-store' as const, suppressAuthRedirect: true };

	function lostAccess(cause: unknown): boolean {
		if (!(cause instanceof ApiError) || cause.status !== 403) return false;
		denied = true;
		keys = null;
		pool = null;
		issued = null;
		return true;
	}

	async function loadKeys() {
		const owner = session();
		if (!owner) return;
		keysError = '';
		try {
			const rows = await api.get<ServiceKey[]>(keysPath, owner.token, owner.projectId, read);
			if (!session() || denied) return;
			keys = rows.filter((row) => row.owner_domain_id === owner.domainId && row.key_kind === 'service');
		} catch (cause) {
			if (session() && !lostAccess(cause)) keysError = t('apiKeys.toast.loadFailed');
		}
	}

	function showPool(next: DomainPool, domain: string) {
		if (next.domain_id !== domain) throw new Error('Domain pool owner mismatch');
		pool = next;
		managerLimit = next.manager_monthly_limit_credits ?? '';
	}

	async function loadPool() {
		const owner = session();
		if (!owner) return;
		poolError = '';
		try {
			const result = await api.get<DomainPool>(poolPath, owner.token, owner.projectId, read);
			if (session() && !denied) showPool(result, owner.domainId);
		} catch (cause) {
			if (session() && !lostAccess(cause)) poolError = domainBillingErrorMessage(cause) ?? t('domainBilling.loadFailed');
		}
	}

	$effect(() => { void loadKeys(); void loadPool(); });

	async function openCreate() {
		const owner = session();
		if (!owner) return;
		const request = ++policyRequest;
		name = '';
		selected = [];
		scopes = null;
		scopesError = '';
		createError = '';
		formOpen = true;
		try {
			const policy = await readKeyIssuancePolicy(owner.token, owner.projectId);
			if (!session() || denied || request !== policyRequest || !formOpen) return;
			scopes = policy.allowed_scopes;
			selected = ['models:read', 'compat:completions:write'].filter((scope) => scopes!.includes(scope));
		} catch (cause) {
			if (session() && request === policyRequest && !lostAccess(cause)) scopesError = t('apiKeys.policyFailed');
		}
	}

	async function create(event: SubmitEvent) {
		event.preventDefault();
		const owner = session();
		if (!owner || busy || denied || !formOpen || !scopes) return;
		if (!name.trim() || !selected.length) {
			createError = !name.trim() ? t('apiKeys.validation.nameRequired') : t('apiKeys.target.noScopes');
			return;
		}
		busy = 'create';
		createError = '';
		try {
			const result = await api.post<{ key: string }>(keysPath, { name: name.trim(), scopes: selected.filter((scope) => scopes!.includes(scope)) }, owner.token, owner.projectId, mutation);
			if (!session() || denied) return;
			formOpen = false;
			issued = result.key;
			await loadKeys();
		} catch (cause) {
			if (session() && !lostAccess(cause)) createError = domainBillingErrorMessage(cause) ?? t('apiKeys.toast.createFailed');
		} finally {
			if (session()) busy = null;
		}
	}

	async function revoke(row: ServiceKey) {
		if (!session() || busy || denied || !row.is_active) return;
		busy = 'revoke';
		try {
			if (!(await confirmDialog(t('apiKeys.serviceRevokeConfirm', { name: row.name || row.key_prefix })))) return;
			const owner = session();
			if (!owner || denied) return;
			await api.delete(`${keysPath}/${row.id}`, owner.token, owner.projectId, mutation);
			if (!session() || denied) return;
			keys = keys?.map((key) => key.id === row.id ? { ...key, is_active: false } : key) ?? null;
			await loadKeys();
		} catch (cause) {
			if (session() && !lostAccess(cause)) keysError = t('apiKeys.toast.revokeFailed');
		} finally {
			if (session()) busy = null;
		}
	}

	async function saveLimit(event: SubmitEvent) {
		event.preventDefault();
		const owner = session();
		if (!owner || !pool || busy || denied) return;
		const value = managerLimit.trim();
		limitError = value && !validDomainCredit(value) ? t('domainBilling.invalidLimit')
			: value && exceedsDomainCeiling(value, pool.admin_ceiling_credits) ? t('domainBilling.overCeiling') : '';
		if (limitError) { await tick(); limitInput?.focus(); return; }
		busy = 'limit';
		try {
			const next = await api.patch<DomainPool>(poolPath, { manager_monthly_limit_credits: value || null }, owner.token, owner.projectId, mutation);
			if (!session() || denied) return;
			showPool(next, owner.domainId);
			toast.success(t('domainBilling.saved'));
		} catch (cause) {
			if (session() && !lostAccess(cause)) limitError = domainBillingErrorMessage(cause) ?? t('domainBilling.saveFailed');
		} finally {
			if (session()) busy = null;
		}
	}
</script>

{#if !denied}
	<section class="mt-5 space-y-3" aria-labelledby={`${id}-keys`}>
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div class="max-w-prose">
				<h3 id={`${id}-keys`} class="mb-1 text-sm font-semibold text-ink-1">{t('apiKeys.serviceTitle')}</h3>
				<p class="text-xs text-ink-2">{t('apiKeys.serviceDescription')}</p>
			</div>
			<Button variant="secondary" onclick={openCreate} disabled={busy !== null}>{t('apiKeys.newServiceKey')}</Button>
		</div>
		{#if keysError}
			<Alert flat tone="danger">{keysError}</Alert>
			<Button variant="secondary" size="sm" onclick={loadKeys}>{t('apiKeys.guide.reload')}</Button>
		{/if}
		{#if keys === null && !keysError}<LoadingState variant="inline" label={t('apiKeys.loading')} />
		{:else if keys?.length === 0}<p class="text-sm text-ink-2">{t('apiKeys.serviceEmpty')}</p>
		{:else if keys}
			<ul class="divide-y divide-line border-y border-line">
				{#each keys as row (row.id)}
					<li class="flex flex-wrap items-center justify-between gap-2 py-3">
						<div class="min-w-0">
							<p class="break-words text-sm font-medium text-ink-1">{row.name || t('apiKeys.unnamed')}</p>
							<code class="text-xs text-ink-2">{row.key_prefix}…</code>
						</div>
						{#if row.is_active}<Button variant="danger-outline" size="sm" onclick={() => revoke(row)} disabled={busy !== null}>{t('apiKeys.revoke')}</Button>
						{:else}<Pill>{t('apiKeys.revoked')}</Pill>{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="mt-5" aria-labelledby={`${id}-pool`}>
		<Card>
			<h3 id={`${id}-pool`} class="mb-1 text-sm font-semibold text-ink-1">{t('domainBilling.title')}</h3>
			<p class="mb-3 text-xs text-ink-2">{t('domainBilling.managerDescription')}</p>
			{#if poolError}
				<Alert flat tone="danger">{poolError}</Alert>
				<Button variant="secondary" size="sm" onclick={loadPool}>{t('apiKeys.guide.reload')}</Button>
			{:else if !pool}<LoadingState variant="inline" label={t('domainBilling.loading')} />
			{:else}
				{#if !pool.is_active}<Alert class="mb-3" flat tone="warning">{t('domainBilling.inactive')}</Alert>{/if}
				<DomainPoolMetrics {pool} />
				<form class="mt-4 grid items-start gap-2 border-t border-line pt-3" method="post" onsubmit={saveLimit} aria-labelledby={`${id}-pool`}>
					<Field for={`${id}-limit`} label={t('domainBilling.managerLimit')} help={t('domainBilling.limitHelp')} error={limitError || undefined}>
						<TextInput id={`${id}-limit`} bind:element={limitInput} bind:value={managerLimit} inputmode="decimal" ariaInvalid={!!limitError} disabled={busy !== null} oninput={() => { limitError = ''; }} />
					</Field>
					<Button class="justify-self-end" variant="secondary" type="submit" disabled={busy !== null} ariaBusy={busy === 'limit'}>{t('apiKeys.save')}</Button>
				</form>
			{/if}
		</Card>
	</section>

	<FormModal bind:open={formOpen} title={t('apiKeys.newServiceKey')} submitting={busy === 'create'}>
		<form id={`${id}-create`} class="space-y-3" method="post" onsubmit={create} aria-label={t('apiKeys.newServiceKey')}>
			<Field for={`${id}-name`} label={t('apiKeys.nameLabel')}>
				<TextInput id={`${id}-name`} maxlength={100} required bind:value={name} disabled={busy === 'create'} />
			</Field>
			{#if scopesError}<Alert flat tone="danger">{scopesError}</Alert>
			{:else if !scopes}<LoadingState variant="inline" label={t('apiKeys.policyLoading')} />
			{:else}
				<fieldset class="space-y-1" disabled={busy === 'create'}>
					<legend class="mb-1 text-sm font-medium text-ink-1">{t('apiKeys.scopes')}</legend>
					{#each scopes as scope (scope)}
						<label class="flex min-h-11 items-center gap-2 text-xs text-ink-2">
							<input type="checkbox" value={scope} bind:group={selected} />
							<span>{modelKeyScopeLabel(scope)}<code class="block break-all">{scope}</code></span>
						</label>
					{/each}
				</fieldset>
				{#if scopes.length === 0}<Alert flat tone="warning">{t('apiKeys.target.noScopes')}</Alert>{/if}
			{/if}
			<p class="text-xs text-ink-2">{t('apiKeys.toolsNotice')}</p>
			{#if createError}<Alert flat tone="danger">{createError}</Alert>{/if}
		</form>
		{#snippet actions()}
			<Button variant="secondary" onclick={() => { formOpen = false; }} disabled={busy === 'create'}>{t('apiKeys.cancel')}</Button>
			<Button type="submit" form={`${id}-create`} disabled={busy === 'create' || !scopes} ariaBusy={busy === 'create'}>{t('apiKeys.create')}</Button>
		{/snippet}
	</FormModal>

	{#if issued}<IssuedLumenKey secret={issued} canCopy={() => !!session() && !denied} close={() => { issued = null; }} />{/if}
{/if}
