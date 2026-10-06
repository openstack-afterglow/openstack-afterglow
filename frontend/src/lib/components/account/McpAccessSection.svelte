<script lang="ts">
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { onMount, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { api, ApiError, getBaseUrl } from '$lib/api/client';
	import { siteConfig } from '$lib/config/site';
	import { auth } from '$lib/stores/auth';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import AnimatedNumber from '$lib/components/ui/AnimatedNumber.svelte';

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

	interface AccessScope {
		token: string | undefined;
		projectId: string | undefined;
		enabled: boolean;
	}

	let scope = $state.raw<AccessScope | null>(null);
	let collectionScope = $state.raw<AccessScope | null>(null);
	let loadSequence = 0;
	const mcpEnabled = $derived($siteConfig.services.mcp);
	const mcpUrl = $derived($siteConfig.mcp_url || `${getBaseUrl().replace(/\/+$/, '')}/api/v1/mcp`);

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
	let copied = $state(false);

	function errorMessage(error: unknown, fallback: string) {
		return error instanceof ApiError ? error.message : fallback;
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
		copied = false;
	}

	// Subscribe synchronously so even a batched A → B → A gets a new owner.
	// Unrelated store updates keep the owner, including populated refresh rows.
	onMount(() => {
		const unsubscribe = derived([auth, siteConfig], ([authState, config]): AccessScope => ({
			token: authState.token ?? undefined,
			projectId: authState.projectId ?? undefined,
			enabled: config.services.mcp,
		})).subscribe((next) => {
			if (scope?.token === next.token && scope?.projectId === next.projectId && scope?.enabled === next.enabled) return;
			scope = next;
			reset();
		});
		return () => {
			unsubscribe();
			scope = null;
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
			copied = false;
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
		copied = false;
	}

	async function copyIssuedToken(owner: AccessScope, secret: string | null) {
		if (!isCurrentScope(owner) || !secret || issuedToken !== secret) return;
		try {
			await navigator.clipboard.writeText(secret);
			if (isCurrentScope(owner) && issuedToken === secret) copied = true;
		} catch {
			if (isCurrentScope(owner) && issuedToken === secret) actionError = t('mcp.copyFailed');
		}
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

{#if mcpEnabled && scope}
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
			{#if issuedToken}<pre>{issuedToken}</pre>{/if}
			<div class="dialog-actions"><Button variant="outline" onclick={copyIssuedToken.bind(null, owner, issuedToken)}>{copied ? t('mcp.copied') : t('mcp.copy')}</Button><Button onclick={dismissIssuedToken.bind(null, owner, issuedToken)}>{t('mcp.done')}</Button></div>
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
	:global(.issued-token-dialog) { width: min(32rem, calc(100vw - 2rem)); display: grid; gap: 0.875rem; }
	:global(.issued-token-dialog pre) { margin: 0; max-height: 12rem; overflow: auto; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: 0.5rem; background: var(--color-surface-sunken); color: var(--color-ink-0); font-size: 0.75rem; white-space: pre-wrap; word-break: break-all; }
	.dialog-actions { justify-content: flex-end; gap: 0.5rem; }
	@media (max-width: 56rem) { .token-form { grid-template-columns: 1fr 1fr; } .token-submit { grid-column: 1 / -1; } }
	@media (max-width: 38rem) { .token-form { grid-template-columns: 1fr; } .record { align-items: flex-start; flex-direction: column; } .record-actions { justify-content: flex-start; } }
</style>
