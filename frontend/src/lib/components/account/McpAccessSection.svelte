<script lang="ts">
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import { getLocale, intlLocale } from '$lib/i18n/runtime.svelte';
	import { onMount, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { api, ApiError, getBaseUrl } from '$lib/api/client';
	import { siteConfig } from '$lib/config/site';
	import { page } from '$app/stores';
	import { docsHref } from '$lib/docs/locales';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';

	interface McpAccessRecord {
		id: string;
		grant_id: string;
		name: string;
		source: string;
		access_level: string;
		status: string;
		visible_prefix: string | null;
		issued_at: string | null;
		expires_at: string;
		last_used_at: string | null;
		revoked_at: string | null;
		is_lumen_default: boolean;
	}

	interface IssuedToken extends McpAccessRecord {
		token: string;
	}

	interface McpConnectionResult {
		endpoint: string;
		protocol_version: string;
		server_name: string;
		server_version: string;
		tool_count: number;
	}

	interface AccessScope {
		token: string | undefined;
		projectId: string | undefined;
		userId: string | undefined;
		enabled: boolean;
	}

	let scope = $state.raw<AccessScope | null>(null);
	let collectionScope = $state.raw<AccessScope | null>(null);
	let loadSequence = 0;
	const mcpEnabled = $derived($siteConfig.services.mcp);
	const mcpUrl = $derived($siteConfig.mcp_url || `${getBaseUrl().replace(/\/+$/, '')}/api/v1/mcp`);
	const oauthAuthorizeUrl = $derived(`${mcpUrl.replace(/\/+$/, '')}/oauth/authorize`);

	let tokens = $state<McpAccessRecord[]>([]);
	let oauthGrants = $state<McpAccessRecord[]>([]);
	let loading = $state(false);
	let loadError = $state('');
	let actionError = $state('');
	let creating = $state(false);
	let mutatingId = $state<string | null>(null);
	let tokenName = $state('Lumen');
	let accessLevel = $state<'read' | 'manage'>('read');
	let expiresAt = $state('');
	let issuedToken = $state<string | null>(null);
	let showIssuedToken = $state(false);
	let copied = $state<'token' | 'config' | null>(null);
	let oauthConfigCopied = $state(false);
	let verificationToken = $state('');
	let verifying = $state(false);
	let verificationSource = $state<'issued' | 'saved' | null>(null);
	let verificationResult = $state<McpConnectionResult | null>(null);
	let verificationError = $state('');
	let verificationSequence = 0;
	const setupConfig = $derived(connectionConfig('YOUR_PERSONAL_MCP_TOKEN'));
	const oauthConfig = $derived(connectionConfig());
	const issuedConfig = $derived(issuedToken ? connectionConfig(issuedToken) : '');

	function connectionConfig(secret?: string) {
		return JSON.stringify({
			mcpServers: {
				'my-stream-server': {
					type: 'http',
					url: mcpUrl,
					...(secret ? { headers: { Authorization: `Bearer ${secret}` } } : {}),
				},
			},
		}, null, 2);
	}

	function clearVerification() {
		verificationSequence += 1;
		verificationToken = '';
		verifying = false;
		verificationSource = null;
		verificationResult = null;
		verificationError = '';
	}

	function errorMessage(error: unknown, fallback: string) {
		return error instanceof ApiError ? error.message : fallback;
	}

	const VERIFY_ERROR_KEYS = {
		invalid_request: 'mcp.verifyError.invalidRequest',
		invalid_token: 'mcp.verifyError.invalidToken',
		not_configured: 'mcp.verifyError.notConfigured',
		rejected: 'mcp.verifyError.rejected',
		redirect: 'mcp.verifyError.redirect',
		protocol: 'mcp.verifyError.protocol',
		unavailable: 'mcp.verifyError.unavailable',
	} as const;

	// The verify endpoint returns stable codes; show them in the reader's language.
	function verificationErrorMessage(error: unknown) {
		if (error instanceof ApiError) {
			const code = error.code;
			if (code && Object.hasOwn(VERIFY_ERROR_KEYS, code)) return t(VERIFY_ERROR_KEYS[code as keyof typeof VERIFY_ERROR_KEYS]);
			if (error.status === 429) return t('mcp.verifyError.rateLimited');
		}
		return t('mcp.verifyError.unavailable');
	}

	function isCurrentScope(owner: AccessScope | null): owner is AccessScope & { token: string; projectId: string } {
		return owner !== null && owner === scope && owner.enabled && !!owner.token && !!owner.projectId;
	}

	function ownsToken(owner: AccessScope, record: McpAccessRecord) {
		return isCurrentScope(owner) && collectionScope === owner && tokens.includes(record);
	}

	function ownsGrant(owner: AccessScope, record: McpAccessRecord) {
		return isCurrentScope(owner) && collectionScope === owner && oauthGrants.includes(record);
	}

	function reset() {
		collectionScope = null;
		tokens = [];
		oauthGrants = [];
		loading = false;
		loadError = '';
		actionError = '';
		creating = false;
		mutatingId = null;
		tokenName = 'Lumen';
		accessLevel = 'read';
		expiresAt = '';
		issuedToken = null;
		showIssuedToken = false;
		copied = null;
		oauthConfigCopied = false;
		clearVerification();
	}

	// Subscribe synchronously so even a batched A → B → A gets a new owner.
	// Unrelated store updates keep the owner, including populated refresh rows.
	onMount(() => {
		const unsubscribe = derived([auth, siteConfig, authReady, projectSwitching], ([authState, config, ready, switching]): AccessScope => ({
			token: authState.token ?? undefined,
			projectId: authState.projectId ?? undefined,
			userId: authState.userId ?? undefined,
			enabled: config.services.mcp && ready && !switching,
		})).subscribe((next) => {
			if (scope?.token === next.token && scope?.projectId === next.projectId && scope?.userId === next.userId && scope?.enabled === next.enabled) return;
			scope = next;
			reset();
		});
		return () => {
			unsubscribe();
			scope = null;
			reset();
		};
	});

	// Keep this zero-argument entry point compatible with onclick={loadAccess}.
	async function loadAccess() {
		await loadAccessFor(scope);
	}

	async function loadAccessFor(owner: AccessScope | null) {
		if (!isCurrentScope(owner)) return;
		const request = ++loadSequence;
		loading = true;
		try {
			const [personalTokens, grants] = await Promise.all([
				api.get<McpAccessRecord[]>('/api/v1/auth/mcp-tokens', owner.token, owner.projectId),
				api.get<McpAccessRecord[]>('/api/v1/auth/mcp-oauth/grants', owner.token, owner.projectId),
			]);
			if (!isCurrentScope(owner) || request !== loadSequence) return;
			tokens = personalTokens;
			oauthGrants = grants;
			collectionScope = owner;
			loadError = '';
		} catch (error) {
			if (!isCurrentScope(owner) || request !== loadSequence) return;
			loadError = errorMessage(error, t('mcp.loadFailed'));
		} finally {
			if (isCurrentScope(owner) && request === loadSequence) loading = false;
		}
	}

	function submitToken(owner: AccessScope, event: SubmitEvent) {
		event.preventDefault();
		void createToken(owner);
	}

	async function createToken(owner: AccessScope) {
		if (!isCurrentScope(owner) || creating || !tokenName.trim()) return;
		creating = true;
		actionError = '';
		try {
			const issued = await api.post<IssuedToken>(
				'/api/v1/auth/mcp-tokens',
				{
					name: tokenName.trim(),
					access_level: accessLevel,
					expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
				},
				owner.token,
				owner.projectId,
			);
			if (!isCurrentScope(owner)) return;
			issuedToken = issued.token;
			showIssuedToken = true;
			copied = null;
			clearVerification();
			tokenName = 'Lumen';
			expiresAt = '';
			await loadAccessFor(owner);
		} catch (error) {
			if (isCurrentScope(owner)) actionError = errorMessage(error, t('mcp.createFailed'));
		} finally {
			if (isCurrentScope(owner)) creating = false;
		}
	}

	function dismissIssuedToken(owner: AccessScope, secret: string | null) {
		if (!isCurrentScope(owner) || issuedToken !== secret) return;
		issuedToken = null;
		showIssuedToken = false;
		copied = null;
		clearVerification();
	}

	async function copyIssuedToken(owner: AccessScope, secret: string | null) {
		if (!isCurrentScope(owner) || !secret || issuedToken !== secret) return;
		try {
			await navigator.clipboard.writeText(secret);
			if (isCurrentScope(owner) && issuedToken === secret) copied = 'token';
		} catch {
			if (isCurrentScope(owner) && issuedToken === secret) actionError = t('mcp.copyFailed');
		}
	}

	async function copyIssuedConfig(owner: AccessScope, secret: string | null) {
		if (!isCurrentScope(owner) || !secret || issuedToken !== secret) return;
		try {
			await navigator.clipboard.writeText(connectionConfig(secret));
			if (isCurrentScope(owner) && issuedToken === secret) copied = 'config';
		} catch {
			if (isCurrentScope(owner) && issuedToken === secret) actionError = t('mcp.copyFailed');
		}
	}

	async function copyOAuthConfig(owner: AccessScope) {
		if (!isCurrentScope(owner)) return;
		try {
			await navigator.clipboard.writeText(oauthConfig);
			if (isCurrentScope(owner)) oauthConfigCopied = true;
		} catch {
			if (isCurrentScope(owner)) actionError = t('mcp.copyFailed');
		}
	}
	async function verifyConnection(owner: AccessScope, secret: string | null, source: 'issued' | 'saved') {
		if (!isCurrentScope(owner) || !secret?.trim() || verifying) return;
		if (source === 'issued' && secret !== issuedToken) return;
		const request = ++verificationSequence;
		const current = () => isCurrentScope(owner) && request === verificationSequence
			&& (source === 'issued' ? issuedToken === secret : verificationToken.trim() === secret.trim());
		verifying = true;
		verificationSource = source;
		verificationResult = null;
		verificationError = '';
		try {
			const result = await api.post<McpConnectionResult>(
				'/api/v1/auth/mcp-tokens/verify', { token: secret.trim() }, owner.token, owner.projectId,
			);
			if (current()) verificationResult = result;
		} catch (error) {
			if (current()) verificationError = verificationErrorMessage(error);
		} finally {
			if (current()) {
				verifying = false;
				if (source === 'saved') verificationToken = '';
			}
		}
	}

	function submitVerification(owner: AccessScope, event: SubmitEvent) {
		event.preventDefault();
		void verifyConnection(owner, verificationToken, 'saved');
	}

	async function selectLumenDefault(owner: AccessScope, record: McpAccessRecord) {
		if (!isCurrentScope(owner) || !ownsToken(owner, record) || mutatingId !== null) return;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.put(`/api/v1/auth/mcp-tokens/${encodeURIComponent(record.id)}/lumen-default`, {}, owner.token, owner.projectId);
			if (isCurrentScope(owner) && collectionScope === owner) await loadAccessFor(owner);
		} catch (error) {
			if (isCurrentScope(owner) && collectionScope === owner) actionError = errorMessage(error, t('mcp.selectFailed'));
		} finally {
			if (isCurrentScope(owner)) mutatingId = null;
		}
	}

	async function clearLumenDefault(owner: AccessScope, record: McpAccessRecord) {
		if (!isCurrentScope(owner) || !ownsToken(owner, record) || !record.is_lumen_default || mutatingId !== null) return;
		mutatingId = 'lumen-default';
		actionError = '';
		try {
			await api.delete('/api/v1/auth/mcp-tokens/lumen-default', owner.token, owner.projectId);
			if (isCurrentScope(owner) && collectionScope === owner) await loadAccessFor(owner);
		} catch (error) {
			if (isCurrentScope(owner) && collectionScope === owner) actionError = errorMessage(error, t('mcp.clearFailed'));
		} finally {
			if (isCurrentScope(owner)) mutatingId = null;
		}
	}

	async function revokeToken(owner: AccessScope, record: McpAccessRecord) {
		if (!isCurrentScope(owner) || !ownsToken(owner, record) || mutatingId !== null) return;
		if (!(await confirmDialog(t('mcp.revokeConfirm', { name: record.name })))) return;
		if (!isCurrentScope(owner) || !ownsToken(owner, record) || mutatingId !== null) return;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.delete(`/api/v1/auth/mcp-tokens/${encodeURIComponent(record.id)}`, owner.token, owner.projectId);
			if (isCurrentScope(owner) && collectionScope === owner) await loadAccessFor(owner);
		} catch (error) {
			if (isCurrentScope(owner) && collectionScope === owner) actionError = errorMessage(error, t('mcp.revokeFailed'));
		} finally {
			if (isCurrentScope(owner)) mutatingId = null;
		}
	}

	async function revokeOAuthGrant(owner: AccessScope, record: McpAccessRecord) {
		if (!isCurrentScope(owner) || !ownsGrant(owner, record) || mutatingId !== null) return;
		if (!(await confirmDialog(t('mcp.revokeOAuthConfirm', { name: record.name })))) return;
		if (!isCurrentScope(owner) || !ownsGrant(owner, record) || mutatingId !== null) return;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.delete(`/api/v1/auth/mcp-oauth/grants/${encodeURIComponent(record.grant_id)}`, owner.token, owner.projectId);
			if (isCurrentScope(owner) && collectionScope === owner) await loadAccessFor(owner);
		} catch (error) {
			if (isCurrentScope(owner) && collectionScope === owner) actionError = errorMessage(error, t('mcp.revokeOAuthFailed'));
		} finally {
			if (isCurrentScope(owner)) mutatingId = null;
		}
	}

	function formatDate(value: string | null) {
		if (!value) return '—';
		return new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
	}

	$effect(() => {
		const owner = scope;
		if (isCurrentScope(owner)) untrack(() => void loadAccessFor(owner));
	});
</script>

{#snippet connectionFeedback()}
	{#if verificationError}
		<Alert tone="danger" title={t('mcp.verifyFailed')}>
			{#snippet children()}{verificationError}{/snippet}
		</Alert>
	{:else if verificationResult}
		{@const result = verificationResult}
		<div role="status" class="verification-result">
			<Alert tone="info" title={t('mcp.verified')}>
				{#snippet children()}
					<p>{t('mcp.verificationDetails', { name: result.server_name, version: result.server_version, protocol: result.protocol_version, count: result.tool_count })}</p>
					<p>{t('mcp.verificationLimit')}</p>
				{/snippet}
			</Alert>
		</div>
	{/if}
{/snippet}

{#if mcpEnabled && isCurrentScope(scope)}
	{@const owner = scope}
	<Card class="mcp-access motion-fade" surface="raised" padding="lg">
		<div class="section-heading">
			<div>
				<h2>{t('mcp.title')}</h2>
				<p>{t('mcp.scopeHelp')}</p>
			</div>
			<Button variant="ghost" size="sm" onclick={loadAccess} disabled={loading}>
				{#if loading}<ActivityIndicator size="xs" label={t('mcp.loading')} />{:else}{t('mcp.refresh')}{/if}
			</Button>
		</div>

		<p class="endpoint"><span>{t('mcp.endpoint')}</span><code>{mcpUrl}</code></p>
		<Button href={docsHref('mcp', getLocale(), $page.url)} variant="link" size="sm">{t('mcp.docs')}</Button>

		<section aria-labelledby="mcp-oauth-setup-heading" class="connection-section">
			<h3 id="mcp-oauth-setup-heading">{t('mcp.oauthSetupTitle')}</h3>
			<p>{t('mcp.oauthSetupHelp')}</p>
			<p class="endpoint"><span>{t('mcp.oauthAuthorizeEndpoint')}</span><code>{oauthAuthorizeUrl}</code></p>
			<pre class="mcp-code" role="region" aria-label={t('mcp.oauthConfig')}>{oauthConfig}</pre>
			<p>{t('mcp.oauthClientSecretHelp')}</p>
			<div><Button variant="outline" size="sm" onclick={copyOAuthConfig.bind(null, owner)}>{oauthConfigCopied ? t('mcp.copied') : t('mcp.copyOAuthConfig')}</Button></div>
		</section>

		<Alert tone="warning" title={t('mcp.onceTitle')}>
			{#snippet children()}{t('mcp.onceHelp')}{/snippet}
		</Alert>

		{#if loadError}
			<Alert tone="danger" title={t('mcp.loadErrorTitle')}>
				{#snippet children()}{loadError}{/snippet}
			</Alert>
		{/if}
		{#if actionError}
			<Alert tone="danger" title={t('mcp.actionErrorTitle')}>
				{#snippet children()}{actionError}{/snippet}
			</Alert>
		{/if}

		{#if mutatingId}<ActivityIndicator label={tc('state.processing')} />{/if}
		<form class="token-form" onsubmit={submitToken.bind(null, owner)}>
			<Field label={t('mcp.name')} for="mcp-token-name" required>
				{#snippet children()}
					<input id="mcp-token-name" class="control" bind:value={tokenName} maxlength="100" autocomplete="off" />
				{/snippet}
			</Field>
			<Field label={t('mcp.permission')} for="mcp-token-access" help={t('mcp.permissionHelp')}>
				{#snippet children()}
					<select id="mcp-token-access" class="control" bind:value={accessLevel}>
						<option value="read">{t('mcp.read')}</option>
						<option value="manage">{t('mcp.manage')}</option>
					</select>
				{/snippet}
			</Field>
			<Field label={t('mcp.expiry')} for="mcp-token-expiry" help={t('mcp.expiryHelp')}>
				{#snippet children()}
					<input id="mcp-token-expiry" class="control" type="datetime-local" bind:value={expiresAt} />
				{/snippet}
			</Field>
			<div class="token-submit"><Button type="submit" disabled={creating || !tokenName.trim()}>{#if creating}<ActivityIndicator size="xs" label={t('mcp.creating')} />{:else}{t('mcp.create')}{/if}</Button></div>
		</form>
		<section aria-labelledby="mcp-setup-heading" class="connection-section">
			<h3 id="mcp-setup-heading">{t('mcp.setupTitle')}</h3>
			<p>{t('mcp.setupHelp')}</p>
			<pre class="mcp-code" role="region" aria-label={t('mcp.config')}>{setupConfig}</pre>
		</section>

		<section aria-labelledby="mcp-verify-heading" class="connection-section">
			<h3 id="mcp-verify-heading">{t('mcp.verifyTitle')}</h3>
			<form class="verification-form" onsubmit={submitVerification.bind(null, owner)}>
				<Field label={t('mcp.tokenLabel')} for="mcp-verification-token" help={t('mcp.verifyHelp')}>
					{#snippet children()}
						<TextInput id="mcp-verification-token" type="password" bind:value={verificationToken} maxlength={256} disabled={verifying} oninput={() => { verificationResult = null; verificationError = ''; }} />
					{/snippet}
				</Field>
				<Button type="submit" variant="outline" disabled={verifying || !verificationToken.trim()}>
					{#if verifying && verificationSource === 'saved'}<ActivityIndicator size="xs" label={t('mcp.verifying')} />{:else}{t('mcp.verify')}{/if}
				</Button>
			</form>
			{#if verificationSource === 'saved'}{@render connectionFeedback()}{/if}
		</section>


		<section aria-labelledby="mcp-personal-tokens-heading">
			<div class="subheading">
				<h3 id="mcp-personal-tokens-heading">{t('mcp.personal')}</h3>
				<span><AnimatedNumber value={tokens.length} format={(n) => t('mcp.count', { count: Math.round(n) })} /></span>
			</div>
			{#if loading && tokens.length === 0}
				<div class="empty"><ActivityIndicator label={t('mcp.loadingAccess')} /></div>
			{:else if tokens.length === 0}
				<p class="empty">{t('mcp.emptyTokens')}</p>
			{:else}
				<div class="records">
					{#each tokens as record (record.id)}
						<div class="record">
							<div class="record-main">
								<div class="record-title"><strong>{record.name}</strong><StatusChip status={record.status} /></div>
								<p>{t('mcp.recordDetails', { prefix: record.visible_prefix ?? t('mcp.noPrefix'), access: record.access_level === 'manage' ? t('mcp.manage') : t('mcp.read'), lastUsed: formatDate(record.last_used_at), expires: formatDate(record.expires_at) })}</p>
								{#if record.is_lumen_default}<p class="default-note">{t('mcp.lumenDefault')}</p>{/if}
							</div>
							<div class="record-actions">
								{#if record.is_lumen_default}
									<Button variant="subtle" size="xs" onclick={clearLumenDefault.bind(null, owner, record)} disabled={mutatingId !== null}>{t('mcp.clearLumen')}</Button>
								{:else}
									<Button variant="outline" size="xs" onclick={selectLumenDefault.bind(null, owner, record)} disabled={mutatingId !== null || record.status !== 'active'}>{t('mcp.setLumen')}</Button>
								{/if}
								<Button variant="danger-outline" size="xs" onclick={revokeToken.bind(null, owner, record)} disabled={mutatingId !== null}>{t('mcp.revoke')}</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<section aria-labelledby="mcp-oauth-grants-heading">
			<div class="subheading"><h3 id="mcp-oauth-grants-heading">{t('mcp.oauth')}</h3><span><AnimatedNumber value={oauthGrants.length} format={(n) => t('mcp.count', { count: Math.round(n) })} /></span></div>
			{#if !loading && oauthGrants.length === 0}
				<p class="empty">{t('mcp.emptyOAuth')}</p>
			{:else if oauthGrants.length > 0}
				<div class="records">
					{#each oauthGrants as record (record.id)}
						<div class="record">
							<div class="record-main"><div class="record-title"><strong>{record.name}</strong><StatusChip status={record.status} /></div><p>{t('mcp.oauthDetails', { access: record.access_level === 'manage' ? t('mcp.manage') : t('mcp.read'), expires: formatDate(record.expires_at) })}</p></div>
							<Button variant="danger-outline" size="xs" onclick={revokeOAuthGrant.bind(null, owner, record)} disabled={mutatingId !== null}>{t('mcp.revokeAccess')}</Button>
						</div>
					{/each}
				</div>
			{/if}
		</section>
	</Card>

	<Modal open={showIssuedToken} onClose={dismissIssuedToken.bind(null, owner, issuedToken)} ariaLabel={t('mcp.newToken')}>
		<Card surface="modal" padding="lg" class="issued-token-dialog">
			<h2>{t('mcp.newToken')}</h2>
			<p>{t('mcp.newTokenHelp')}</p>
			{#if issuedToken}
				<pre class="mcp-code">{issuedToken}</pre>
				<h3>{t('mcp.config')}</h3>
				<p>{t('mcp.configSecretWarning')}</p>
				<pre class="mcp-code" role="region" aria-label={t('mcp.config')}>{issuedConfig}</pre>
			{/if}
			{#if verificationSource === 'issued'}{@render connectionFeedback()}{/if}
			<div class="dialog-actions">
				<Button variant="outline" onclick={copyIssuedToken.bind(null, owner, issuedToken)}>{copied === 'token' ? t('mcp.copied') : t('mcp.copy')}</Button>
				<Button variant="outline" onclick={copyIssuedConfig.bind(null, owner, issuedToken)}>{copied === 'config' ? t('mcp.copied') : t('mcp.copyConfig')}</Button>
				<Button variant="outline" onclick={verifyConnection.bind(null, owner, issuedToken, 'issued')} disabled={verifying}>
					{#if verifying}<ActivityIndicator size="xs" label={t('mcp.verifying')} />{:else}{t('mcp.verify')}{/if}
				</Button>
				<Button onclick={dismissIssuedToken.bind(null, owner, issuedToken)}>{t('mcp.done')}</Button>
			</div>
		</Card>
	</Modal>
{/if}

<style>
	:global(.mcp-access) { display: grid; gap: 1rem; }
	.section-heading, .subheading, .record, .record-title, .record-actions, .dialog-actions { display: flex; align-items: center; }
	.section-heading, .subheading, .record { justify-content: space-between; gap: 1rem; }
	.section-heading h2, .subheading h3, :global(.issued-token-dialog h2) { margin: 0; color: var(--color-ink-0); }
	.section-heading h2 { font-size: 1rem; }
	.section-heading p, .record p, .empty, :global(.issued-token-dialog p) { margin: 0.25rem 0 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	.endpoint { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; margin: 0; color: var(--color-ink-2); font-size: 0.75rem; }
	.endpoint span { font-weight: 600; }
	.endpoint code { color: var(--color-ink-1); overflow-wrap: anywhere; }
	.token-form { display: grid; grid-template-columns: minmax(0, 1fr) minmax(9rem, 0.7fr) minmax(10rem, 0.8fr) auto; gap: 0.75rem; align-items: end; padding: 1rem; border: 1px solid var(--color-line); border-radius: 0.75rem; background: var(--color-surface-sunken); }
	.control { box-sizing: border-box; width: 100%; min-height: 2.5rem; padding: 0.5rem 0.625rem; border: 1px solid var(--color-line-2); border-radius: 0.5rem; background: var(--color-surface-base); color: var(--color-ink-0); font: inherit; }
	.control:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
	.token-submit { padding-bottom: 0.0625rem; }
	.subheading { margin-bottom: 0.5rem; }
	.subheading h3 { font-size: 0.875rem; }
	.subheading span { color: var(--color-ink-2); font-size: 0.75rem; }
	.records { display: grid; gap: 0.5rem; }
	.record { padding: 0.75rem; border: 1px solid var(--color-line); border-radius: 0.625rem; background: var(--color-surface-base); }
	.record-main { min-width: 0; }
	.record-title { gap: 0.5rem; flex-wrap: wrap; }
	.record-title strong { color: var(--color-ink-0); font-size: 0.875rem; }
	.record-actions { flex-wrap: wrap; justify-content: flex-end; }
	:global(.issued-token-dialog) { width: min(44rem, calc(100vw - 2rem)); display: grid; gap: 0.875rem; }
	:global(.issued-token-dialog h3), .connection-section h3 { margin: 0; color: var(--color-ink-0); font-size: 0.875rem; }
	.connection-section { min-width: 0; display: grid; gap: 0.75rem; }
	.connection-section p { margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	:global(.mcp-code) { min-width: 0; margin: 0; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-sunken); color: var(--color-ink-0); font-size: 0.75rem; white-space: pre-wrap; overflow-wrap: anywhere; }
	.verification-form { display: grid; gap: 0.75rem; align-items: start; }
	.verification-form :global(button) { justify-self: start; }
	.verification-result p { margin: 0; overflow-wrap: anywhere; }
	.verification-result p + p { margin-top: 0.5rem; }
	.dialog-actions { justify-content: flex-end; flex-wrap: wrap; gap: 0.5rem; }
	@media (max-width: 56rem) { .token-form { grid-template-columns: 1fr 1fr; } .token-submit { grid-column: 1 / -1; } }
	@media (max-width: 38rem) { .token-form { grid-template-columns: 1fr; } .record { align-items: flex-start; flex-direction: column; } .record-actions { justify-content: flex-start; } }
</style>
