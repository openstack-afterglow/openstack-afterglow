<script module lang="ts">
	export interface ApprovedMcpServer {
		id: number;
		name: string;
		url: string | null;
		auth_mode?: 'none' | 'oauth' | 'admin';
		oauth_scopes?: string[];
		is_active: boolean;
		server_is_active?: boolean;
		activation_is_active?: boolean;
		config_version?: number;
	}
</script>

<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { serviceCapabilities, projectPermissions } from '$lib/stores/servicePermissions';
	import { api, ApiError } from '$lib/api/client';
	import type { CloudToolsCatalogue } from '$lib/api/chatContracts';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import FormModal from '$lib/components/ui/FormModal.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import { t } from '$lib/i18n/ns/chat-settings';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	let { servers, loading, oauthStatus, onChanged }: {
		servers: ApprovedMcpServer[];
		loading: boolean;
		oauthStatus: Record<number, { connected: boolean }>;
		onChanged: () => Promise<void>;
	} = $props();

	interface Scope { token: string; projectId: string; userId: string; projectName: string }
	let scope = $state.raw<Scope | null>(null);
	let cloud = $state<CloudToolsCatalogue | null>(null);
	let cloudLoading = $state(false);
	let loadError = $state('');
	let actionError = $state('');
	let consent = $state<{ kind: 'cloud' } | { kind: 'remote'; server: ApprovedMcpServer } | null>(null);
	let consentOpen = $state(false);
	let access = $state<'read' | 'manage'>('read');
	let busy = $state(false);
	let loadGeneration = 0;
	let actionGeneration = 0;
	let controller: AbortController | null = null;
	let actionController: AbortController | null = null;
	const canCloud = $derived($serviceCapabilities('lumen-tools_user'));
	const canMcp = $derived($serviceCapabilities('lumen-mcp_editor'));
	const canWrite = $derived($projectPermissions.permissions?.can_write === true && !$projectPermissions.loading && !$projectPermissions.error);
	const cloudActive = $derived(canCloud && cloud?.enabled === true);
	const accessOptions = $derived([
		{ value: 'read', label: t('extensions.catalogue.read'), disabled: busy || !canCloud },
		{ value: 'manage', label: t('extensions.catalogue.manage'), disabled: busy || !canCloud || !canWrite }
	]);
	const consentValid = $derived.by(() => {
		const choice = consent;
		if (!scope || !choice) return false;
		if (choice.kind === 'cloud') return canCloud && cloud?.available === true && (access === 'read' || canWrite);
		return canMcp && servers.some((server) => server.id === choice.server.id && server.config_version === choice.server.config_version && server.server_is_active === true);
	});

	onMount(() => {
		const unsubscribe = derived([auth, authReady, projectSwitching], ([actor, ready, switching]) =>
			ready && !switching && actor.token && actor.projectId && actor.userId
				? { token: actor.token, projectId: actor.projectId, userId: actor.userId, projectName: actor.projectName || actor.projectId } : null
		).subscribe((owner) => {
			if (owner && scope && owner.token === scope.token && owner.projectId === scope.projectId && owner.userId === scope.userId) return;
			controller?.abort();
			actionController?.abort();
			++loadGeneration;
			++actionGeneration;
			scope = owner;
			cloud = null;
			cloudLoading = false;
			loadError = '';
			actionError = '';
			consentOpen = false;
			consent = null;
			busy = false;
		});
		return () => {
			controller?.abort();
			actionController?.abort();
			scope = null;
			++loadGeneration;
			++actionGeneration;
			unsubscribe();
		};
	});

	async function loadCloud(owner: Scope) {
		const generation = ++loadGeneration;
		controller?.abort();
		controller = new AbortController();
		cloudLoading = true;
		loadError = '';
		try {
			const result = await api.get<CloudToolsCatalogue>('/api/v1/chat/cloud-tools', owner.token, owner.projectId, { refresh: true, signal: controller.signal });
			if (scope !== owner || generation !== loadGeneration || !canCloud) return;
			cloud = result;
		} catch (error) {
			if (scope !== owner || generation !== loadGeneration) return;
			cloud = null;
			loadError = error instanceof ApiError ? error.message : t('extensions.catalogue.loadFailed');
		} finally {
			if (scope === owner && generation === loadGeneration) cloudLoading = false;
		}
	}

	$effect(() => {
		const owner = scope;
		if (owner && canCloud) untrack(() => void loadCloud(owner));
	});

	function openConsent(server?: ApprovedMcpServer) {
		if (!scope || busy || (server ? !canMcp : !canCloud)) return;
		consent = server ? { kind: 'remote', server: { ...server } } : { kind: 'cloud' };
		access = 'read';
		actionError = '';
		consentOpen = true;
	}

	async function approve() {
		if (!scope || !consent || busy || !consentValid) return;
		const owner = scope;
		const choice = consent;
		const generation = ++actionGeneration;
		const request = new AbortController();
		actionController = request;
		const options = { signal: AbortSignal.any([request.signal, AbortSignal.timeout(30_000)]) };
		busy = true;
		actionError = '';
		try {
			if (choice.kind === 'cloud') {
				await api.post('/api/v1/chat/cloud-tools', { access_level: access }, owner.token, owner.projectId, options);
			} else {
				await api.patch(`/api/v1/chat/mcp-servers/${choice.server.id}/activation`, { is_active: true, config_version: choice.server.config_version }, owner.token, owner.projectId, options);
				if (scope !== owner || generation !== actionGeneration || !canMcp) return;
				if (choice.server.auth_mode === 'oauth' && !oauthStatus[choice.server.id]?.connected) {
					const result = await api.post<{ authorization_url: string }>(`/api/v1/chat/mcp-servers/${choice.server.id}/oauth/start`, {}, owner.token, owner.projectId, options);
					if (scope !== owner || generation !== actionGeneration || !canMcp) return;
					if (!result.authorization_url) throw new Error('Missing authorization URL');
					window.location.assign(result.authorization_url);
				}
			}
			if (scope !== owner || generation !== actionGeneration || !(choice.kind === 'cloud' ? canCloud : canMcp)) return;
			consentOpen = false;
			consent = null;
			await Promise.all([canCloud ? loadCloud(owner) : Promise.resolve(), onChanged()]);
		} catch (error) {
			if (scope === owner && generation === actionGeneration) actionError = error instanceof ApiError ? error.message : t('extensions.catalogue.approveFailed');
		} finally {
			if (scope === owner && generation === actionGeneration) busy = false;
			if (actionController === request) actionController = null;
		}
	}

	async function deactivate(server?: ApprovedMcpServer) {
		if (!scope || busy || (server ? !canMcp : !canCloud)) return;
		const owner = scope;
		const generation = ++actionGeneration;
		const request = new AbortController();
		actionController = request;
		const options = { signal: AbortSignal.any([request.signal, AbortSignal.timeout(30_000)]) };
		busy = true;
		actionError = '';
		try {
			if (server) await api.patch(`/api/v1/chat/mcp-servers/${server.id}/activation`, { is_active: false, config_version: server.config_version }, owner.token, owner.projectId, options);
			else await api.delete('/api/v1/chat/cloud-tools', owner.token, owner.projectId, options);
			if (scope !== owner || generation !== actionGeneration) return;
			await Promise.all([canCloud ? loadCloud(owner) : Promise.resolve(), onChanged()]);
		} catch (error) {
			if (scope === owner && generation === actionGeneration) actionError = error instanceof ApiError ? error.message : t('extensions.catalogue.deactivateFailed');
		} finally {
			if (scope === owner && generation === actionGeneration) busy = false;
			if (actionController === request) actionController = null;
		}
	}
</script>

<section class="catalogue" aria-labelledby="approved-mcp-heading">
	<div>
		<h3 id="approved-mcp-heading" class="text-sm font-semibold text-ink-1">{t('extensions.catalogue.title')}</h3>
		<p class="mt-1 text-xs text-ink-2">{t('extensions.catalogue.description')}</p>
	</div>
	<Card surface="raised" padding="md">
		<div class="server-row">
			<div class="server-copy">
				<div class="server-title"><strong>Afterglow MCP</strong><Pill tone="neutral" size="xs">{t('extensions.catalogue.builtin')}</Pill><Pill tone={cloudActive ? 'success' : 'neutral'} size="xs">{cloudActive ? t('extensions.state.active') : t('extensions.state.inactive')}</Pill></div>
				<p>{t('extensions.catalogue.cloudDescription')}</p>
				{#if cloudActive && cloud}
					<p>{t('extensions.catalogue.savedAccess', { access: cloud.access_level === 'manage' ? t('extensions.catalogue.manage') : t('extensions.catalogue.read'), project: cloud.allowed_projects.map((project) => project.name || project.id).join(', ') })}</p>
					{#if cloud.expires_at}<p class="tabular-nums">{t('extensions.catalogue.expires', { date: new Date(cloud.expires_at).toLocaleDateString(intlLocale()) })}</p>{/if}
				{:else if cloudLoading}<p role="status">{t('extensions.catalogue.loading')}</p>
				{:else if canCloud && cloud?.available === false}<p>{t('extensions.catalogue.unavailable')}</p>{/if}
			</div>
			<div class="server-actions">
				{#if cloudActive}
					<Button variant="secondary" size="sm" onclick={() => deactivate()} disabled={busy || cloudLoading}>{t('extensions.actions.deactivate')}</Button>
				{:else}
					<Button variant="outline" size="sm" onclick={() => openConsent()} disabled={busy || cloudLoading || !canCloud || cloud?.available !== true}>{t('extensions.catalogue.activateCloud')}</Button>
				{/if}
			</div>
		</div>
	</Card>
	{#if loadError}<Alert tone="danger">{loadError}{#snippet actions()}<Button variant="secondary" size="sm" onclick={() => scope && loadCloud(scope)}>{t('extensions.catalogue.retry')}</Button>{/snippet}</Alert>{/if}
	{#if loading}
		<div class="motion-skeleton h-16 rounded-lg border border-line" role="status" aria-label={t('extensions.mcp.loading')}></div>
	{:else}
		{#each servers as server (server.id)}
			{@const connected = server.auth_mode !== 'oauth' || oauthStatus[server.id]?.connected === true}
			{@const active = server.is_active && connected}
			<Card surface="raised" padding="md">
				<div class="server-row">
					<div class="server-copy">
						<div class="server-title"><strong>{server.name}</strong><Pill tone="neutral" size="xs">{t('extensions.catalogue.approved')}</Pill><Pill tone={active ? 'success' : 'neutral'} size="xs">{active ? t('extensions.state.active') : t('extensions.state.inactive')}</Pill></div>
						{#if server.url}<p class="break-all">{server.url}</p>{/if}
						{#if server.auth_mode === 'oauth'}<p>{t('extensions.mcp.oauthRequired')}</p>{/if}
					</div>
					<div class="server-actions">
						{#if server.activation_is_active === true || server.is_active}
							<Button variant="secondary" size="sm" onclick={() => deactivate(server)} disabled={busy || !canMcp}>{t('extensions.actions.deactivate')}</Button>
						{/if}
						{#if !active}
							<Button variant="outline" size="sm" onclick={() => openConsent(server)} disabled={busy || !canMcp || server.server_is_active !== true || !server.config_version}>{t('extensions.catalogue.activateServer', { name: server.name })}</Button>
						{/if}
					</div>
				</div>
			</Card>
		{/each}
	{/if}
	{#if actionError && !consentOpen}<Alert tone="danger">{actionError}</Alert>{/if}
</section>

<FormModal bind:open={consentOpen} title={t('extensions.catalogue.consentTitle', { name: consent?.kind === 'remote' ? consent.server.name : 'Afterglow MCP' })} submitting={busy}>
	<div class="consent-fields">
		<Field label={t('extensions.catalogue.project')}><p class="text-sm text-ink-0">{scope?.projectName}</p><p class="break-all font-mono text-xs text-ink-2">{scope?.projectId}</p></Field>
		{#if consent?.kind === 'cloud'}
			<Field label={t('extensions.catalogue.permissions')} help={t('extensions.catalogue.scopeHelp')}>
				<ToggleGroup value={access} options={accessOptions} onchange={(value) => { access = value as 'read' | 'manage'; }} fullWidth ariaLabel={t('extensions.catalogue.permissions')} />
			</Field>
			<Alert tone={access === 'manage' ? 'warning' : 'info'}>{access === 'manage' ? t('extensions.catalogue.manageHelp') : t('extensions.catalogue.readHelp')}</Alert>
		{:else if consent?.kind === 'remote'}
			<Field label={t('extensions.catalogue.destination')}><p class="break-all text-sm text-ink-0">{consent.server.url}</p></Field>
			<Field label={t('extensions.catalogue.permissions')}><p class="text-sm text-ink-1">{consent.server.oauth_scopes?.length ? consent.server.oauth_scopes.join(', ') : t('extensions.catalogue.providerPermissions')}</p></Field>
			<Alert tone="info">{consent.server.auth_mode === 'oauth' ? t('extensions.catalogue.oauthHelp') : t('extensions.catalogue.remoteHelp')}</Alert>
		{/if}
		{#if actionError}<Alert tone="danger">{actionError}</Alert>{/if}
	</div>
	{#snippet actions()}
		<Button variant="secondary" onclick={() => { consentOpen = false; consent = null; }} disabled={busy}>{t('apiKeys.cancel')}</Button>
		<Button variant="primary" onclick={approve} disabled={busy || !consentValid}>{busy ? t('extensions.catalogue.approving') : t('extensions.catalogue.approve')}</Button>
	{/snippet}
</FormModal>

<style>
	.catalogue { display: grid; gap: 0.75rem; margin-bottom: 1.5rem; }
	.server-row { display: flex; flex-direction: column; gap: 1rem; }
	.server-copy { min-width: 0; }
	.server-title { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--color-ink-0); }
	.server-copy p { margin: 0.5rem 0 0; font-size: 0.75rem; color: var(--color-ink-2); }
	.server-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; flex-shrink: 0; }
	.consent-fields { display: grid; gap: 1rem; }
	@media (min-width: 768px) { .server-row { flex-direction: row; justify-content: space-between; align-items: center; } }
</style>
