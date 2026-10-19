<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession, type LoginPolicy, type IamProvider, type ProviderWrite } from '$lib/api/domainIam';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { iamErrorMessage } from './iamError';
	import { t as tc } from '$lib/i18n/ns/common';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => domainIam(session));
	const uid = $props.id();
	let live = true;
	let revision = 0;
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let notice = $state('');
	let policy = $state<LoginPolicy | null>(null);
	let passwordEnabled = $state(true);
	let signupEnabled = $state(false);
	let loginDomains = $state('');
	let signupDomains = $state('');
	let providers = $state<IamProvider[]>([]);
	let open = $state(false);
	let editing = $state<IamProvider | null>(null);
	let name = $state('');
	let kind = $state<'oidc' | 'github'>('oidc');
	let enabled = $state(true);
	let issuer = $state('');
	let clientId = $state('');
	let secret = $state('');
	let scopes = $state('');
	let idp = $state('');
	let protocol = $state('');
	let authorizationUrl = $state('');
	let tokenUrl = $state('');
	let apiUrl = $state('');
	let federationToken = $state<'id_token' | 'access_token'>('id_token');
	let tokenAuth = $state<'auto' | 'client_secret_basic' | 'client_secret_post'>('auto');
	const destinationChanged = $derived(!!editing && (issuer.trim() !== (editing.issuer_url ?? '') || tokenUrl.trim() !== (editing.token_url ?? '')));
	let providerForm = $state<HTMLFormElement>();
	const split = (value: string) => [...new Set(value.split(/[\s,]+/).map(item => item.trim()).filter(Boolean))];
	function fail(cause: unknown) {
		if (!live) return;
		error = iamErrorMessage(cause, t('saveFailed'));
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	function applyPolicy(result: LoginPolicy) {
		policy = result; passwordEnabled = result.password_enabled; signupEnabled = result.signup_enabled;
		loginDomains = result.allowed_email_domains.join(', '); signupDomains = result.signup_email_domains.join(', ');
	}
	async function load() {
		const pending = ++revision; loading = true; error = '';
		try {
			const [p, rows] = await Promise.all([client.policy(), client.providers()]);
			if (live && revision === pending) { applyPolicy(p); providers = rows.items; }
		} catch (cause) { if (revision === pending) fail(cause); }
		finally { if (live && revision === pending) loading = false; }
	}
	async function savePolicy(event: SubmitEvent) {
		event.preventDefault(); if (!live || blocked || !policy || busy || loading) return;
		busy = true; error = ''; notice = '';
		try {
			const result = await client.savePolicy({ password_enabled: passwordEnabled, signup_enabled: signupEnabled, allowed_email_domains: split(loginDomains), signup_email_domains: split(signupDomains), revision: policy.revision });
			if (live) { applyPolicy(result); notice = t('saved'); }
		} catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	function close() {
		open = false; editing = null; secret = ''; name = ''; issuer = ''; clientId = ''; scopes = ''; idp = ''; protocol = ''; authorizationUrl = ''; tokenUrl = ''; apiUrl = '';
	}
	function edit(provider: IamProvider | null) {
		if (busy || loading) return;
		editing = provider; name = provider?.name ?? ''; kind = provider?.kind ?? 'oidc'; enabled = provider?.enabled ?? true;
		issuer = provider?.issuer_url ?? ''; clientId = provider?.client_id ?? ''; secret = '';
		scopes = provider?.scopes.join(' ') ?? 'openid profile email'; idp = provider?.keystone_idp_id ?? ''; protocol = provider?.keystone_protocol_id ?? '';
		authorizationUrl = provider?.authorization_url ?? ''; tokenUrl = provider?.token_url ?? ''; apiUrl = provider?.api_url ?? '';
		federationToken = provider?.federation_token_type ?? 'id_token'; tokenAuth = provider?.token_endpoint_auth_method ?? 'auto';
		error = ''; open = true;
	}
	function changeKind() {
		issuer = ''; authorizationUrl = ''; tokenUrl = ''; apiUrl = ''; secret = '';
		scopes = kind === 'oidc' ? 'openid profile email' : 'read:user user:email';
		federationToken = kind === 'oidc' ? 'id_token' : 'access_token'; tokenAuth = kind === 'oidc' ? 'auto' : 'client_secret_post';
	}
	async function saveProvider() {
		if (!live || blocked || busy || loading || !providerForm?.reportValidity()) return;
		const body: ProviderWrite = {
			name: name.trim(), kind, enabled, issuer_url: kind === 'oidc' ? issuer.trim() : null, client_id: clientId.trim(), scopes: split(scopes), keystone_idp_id: idp.trim(), keystone_protocol_id: protocol.trim(),
			// OIDC endpoints are discovery-pinned server metadata, never client input.
			...(kind === 'github' ? { authorization_url: authorizationUrl.trim() || null, token_url: tokenUrl.trim() || null, api_url: apiUrl.trim() || null } : {}),
			federation_token_type: kind === 'github' ? 'access_token' : federationToken,
			token_endpoint_auth_method: kind === 'github' ? 'client_secret_post' : tokenAuth === 'auto' ? null : tokenAuth,
			...(secret ? { client_secret: secret } : {}), ...(editing ? { revision: editing.revision } : {})
		};
		secret = ''; busy = true; error = ''; notice = '';
		try {
			if (editing) {
				const changes: Partial<Omit<ProviderWrite, 'kind'>> = { revision: editing.revision };
				for (const [key, value] of Object.entries(body)) {
					// A replacement secret re-pins the OIDC issuer's discovered token destination.
					const repin = key === 'issuer_url' && kind === 'oidc' && 'client_secret' in body;
					if (key !== 'kind' && key !== 'revision' && (key === 'client_secret' || repin || JSON.stringify(value) !== JSON.stringify(editing[key as keyof IamProvider]))) Object.assign(changes, { [key]: value });
				}
				await client.updateProvider(editing.id, changes);
			} else await client.createProvider(body);
			if (live) { close(); notice = t('saved'); await load(); }
		}
		catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	async function toggle(provider: IamProvider) {
		const pending = revision;
		if (!live || blocked || busy || loading) return;
		if (provider.enabled && !await confirmDialog(t('disableProviderConfirm', { name: provider.name }), { confirmLabel: t('disable') })) return;
		if (!live || blocked || busy || loading || revision !== pending || !providers.includes(provider)) return;
		busy = true; error = ''; notice = '';
		try { await client.updateProvider(provider.id, { enabled: !provider.enabled, revision: provider.revision }); if (live) await load(); }
		catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	async function remove(provider: IamProvider) {
		const pending = revision;
		if (!live || blocked || busy || loading) return;
		if (!await confirmDialog(t('deleteProviderConfirm', { name: provider.name }), { confirmLabel: t('delete') })) return;
		if (!live || blocked || busy || loading || pending !== revision || !providers.includes(provider)) return;
		busy = true; error = ''; notice = '';
		try { await client.deleteProvider(provider.id); if (live) await load(); }
		catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; revision++; secret = ''; providers = []; policy = null; });
</script>

<div class="space-y-4">
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if error && !open}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	<Button variant="secondary" disabled={loading || busy} onclick={load}>{t('refresh')}</Button>
	{#if policy}
		<Card><form class="space-y-4" onsubmit={savePolicy}>
			<h2 class="text-base font-semibold text-ink-0">{t('policy')}</h2>
			<Alert tone="info">{t('policyHelp')}</Alert>
			{#if !policy.smtp_configured}<Alert tone="warning">{t('smtpMissing')}</Alert>{/if}
			<fieldset disabled={loading || busy} class="space-y-4">
				<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1"><input type="checkbox" bind:checked={passwordEnabled} />{t('passwordLogin')}</label>
				<Field label={t('loginDomains')} help={t('loginDomainsHelp')} for={`${uid}-login-domains`}><TextInput id={`${uid}-login-domains`} bind:value={loginDomains} /></Field>
				<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1"><input type="checkbox" bind:checked={signupEnabled} />{t('signup')}</label>
				<Field label={t('signupDomains')} help={t('signupDomainsHelp')} for={`${uid}-signup-domains`}><TextInput id={`${uid}-signup-domains`} bind:value={signupDomains} /></Field>
				<Button type="submit" variant="primary" disabled={blocked}>{t('savePolicy')}</Button>
			</fieldset>
		</form></Card>
	{/if}
	<Card>
		<div class="mb-4 flex flex-wrap items-center justify-between gap-3"><h2 class="text-base font-semibold text-ink-0">{t('providers')}</h2><Button variant="primary" disabled={loading || busy || !policy} onclick={() => edit(null)}>{t('addProvider')}</Button></div>
		<Alert tone="info">{t('federationHelp')}</Alert>
		{#if policy}<p class="my-3 text-sm text-ink-2">{t('usableProviders', { count: policy.usable_provider_count })}</p>{/if}
		<p class="mb-3 text-sm text-ink-2">{t('verificationHelp')}</p>
		<TableShell><table><thead><tr><th>{t('name')}</th><th>{t('kind')}</th><th>{t('status')}</th><th>{t('secretStatus')}</th><th>{t('actions')}</th></tr></thead><tbody>
			{#each providers as provider (provider.id)}<tr><td>{provider.name}</td><td>{provider.kind === 'oidc' ? t('oidc') : t('github')}</td><td>{provider.enabled ? t('enabled') : t('disabled')}<span class="block text-xs text-ink-2">{provider.verified && provider.verified_revision === provider.revision ? t('verifiedProvider') : t('unverifiedProvider')}</span></td><td>{provider.client_secret_configured ? t('configured') : t('notConfigured')}</td><td><div class="flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={busy || loading} onclick={() => edit(provider)}>{t('edit')}</Button><Button variant="secondary" size="sm" disabled={blocked || busy || loading} onclick={() => toggle(provider)}>{provider.enabled ? t('disable') : t('enable')}</Button><Button variant="danger-outline" size="sm" disabled={blocked || busy || loading} onclick={() => remove(provider)}>{t('delete')}</Button></div></td></tr>{/each}
			{#if !loading && !error && !providers.length}<tr><td colspan="5">{t('emptyProviders')}</td></tr>{/if}
		</tbody></table></TableShell>
	</Card>
</div>
{#if open}
	<FormModal bind:open title={editing ? t('editProvider') : t('addProvider')} submitting={busy} onClose={close} onSubmit={saveProvider} submitLabel={t('save')}>
		<form bind:this={providerForm} class="space-y-4" onsubmit={(event) => { event.preventDefault(); void saveProvider(); }}>
			{#if error}<Alert tone="danger">{error}</Alert>{/if}
			<Alert tone="info">{t('callbackHelp')}</Alert>
			<Field label={t('name')} for={`${uid}-name`} required><TextInput id={`${uid}-name`} bind:value={name} required disabled={busy} /></Field>
			<Field label={t('kind')} for={`${uid}-kind`}><SelectInput id={`${uid}-kind`} bind:value={kind} disabled={busy || !!editing} onchange={changeKind}><option value="oidc">{t('oidc')}</option><option value="github">{t('github')}</option></SelectInput></Field>
			{#if kind === 'oidc'}<Field label={t('issuer')} for={`${uid}-issuer`} required><TextInput id={`${uid}-issuer`} type="url" bind:value={issuer} required disabled={busy} /></Field>{/if}
			{#if kind === 'oidc'}
				<Field label={t('federationToken')} for={`${uid}-federation-token`} help={t('federationTokenHelp')}><SelectInput id={`${uid}-federation-token`} bind:value={federationToken} disabled={busy}><option value="id_token">{t('idToken')}</option><option value="access_token">{t('accessToken')}</option></SelectInput></Field>
				<Field label={t('tokenAuth')} for={`${uid}-token-auth`}><SelectInput id={`${uid}-token-auth`} bind:value={tokenAuth} disabled={busy}><option value="auto">{t('auto')}</option><option value="client_secret_basic">client_secret_basic</option><option value="client_secret_post">client_secret_post</option></SelectInput></Field>
			{/if}
			<Field label={t('clientId')} for={`${uid}-client-id`} required><TextInput id={`${uid}-client-id`} bind:value={clientId} required disabled={busy} autocomplete="off" /></Field>
			<Field label={t('clientSecret')} help={editing ? t('secretKeepHelp') : t('secretHelp')} for={`${uid}-secret`} required={!editing || destinationChanged}><TextInput id={`${uid}-secret`} type="password" bind:value={secret} required={!editing || destinationChanged} disabled={busy} autocomplete="new-password" /></Field>
			<Field label={t('scopes')} help={t('scopesHelp')} for={`${uid}-scopes`}><TextInput id={`${uid}-scopes`} bind:value={scopes} disabled={busy} /></Field>
			<Field label={t('idp')} help={t('federationHelp')} for={`${uid}-idp`} required><TextInput id={`${uid}-idp`} bind:value={idp} required disabled={busy} /></Field>
			<Field label={t('protocol')} for={`${uid}-protocol`} required><TextInput id={`${uid}-protocol`} bind:value={protocol} required disabled={busy} /></Field>
			{#if kind === 'github'}
				<Alert tone="info">{t('githubEndpointsHelp')}</Alert>
				<Field label={t('authorizationUrl')} for={`${uid}-authorize`}><TextInput id={`${uid}-authorize`} type="url" bind:value={authorizationUrl} disabled={busy} /></Field>
				<Field label={t('tokenUrl')} for={`${uid}-token`}><TextInput id={`${uid}-token`} type="url" bind:value={tokenUrl} disabled={busy} /></Field>
				<Field label={t('apiUrl')} for={`${uid}-api`}><TextInput id={`${uid}-api`} type="url" bind:value={apiUrl} disabled={busy} /></Field>
			{/if}
			<label class="flex min-h-11 items-center gap-3 text-sm text-ink-1"><input type="checkbox" bind:checked={enabled} disabled={busy} />{t('enabled')}</label>
		</form>
		{#snippet actions()}
			<Button variant="secondary" disabled={busy} onclick={close}>{tc('actions.cancel')}</Button>
			<Button variant="primary" disabled={busy || blocked} onclick={saveProvider}>{t('save')}</Button>
		{/snippet}
	</FormModal>
{/if}
