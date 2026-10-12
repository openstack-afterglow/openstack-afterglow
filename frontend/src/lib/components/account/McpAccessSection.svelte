<script module lang="ts">
	export interface McpClientObservation {
		client_name: string | null;
		client_version: string | null;
		product: string | null;
		kind: 'browser' | 'agent' | 'bot' | 'sdk' | 'unknown';
		identity_source: 'client_info' | 'user_agent' | 'unknown';
		browser: string | null;
		os: string | null;
		first_seen_at: string | null;
		last_seen_at: string | null;
	}
	interface McpProject {
		id: string;
		name: string;
	}
	interface McpAccessRecord {
		id: string;
		grant_id: string;
		name: string;
		source: string;
		access_level: string;
		project_scope: 'current' | 'selected' | 'all';
		project_ids: string[];
		projects: McpProject[];
		status: string;
		visible_prefix: string | null;
		issued_at: string | null;
		expires_at: string | null;
		last_used_at: string | null;
		revoked_at: string | null;
		is_lumen_default: boolean;
		client_observations: McpClientObservation[] | null;
	}
</script>

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
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';




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
	let tokensScope = $state.raw<AccessScope | null>(null);
	let grantsScope = $state.raw<AccessScope | null>(null);
	let loadSequence = 0;
	let loadController: AbortController | null = null;
	let issuanceSequence = 0;
	let issuanceController: AbortController | null = null;
	let projectsScope = $state.raw<AccessScope | null>(null);
	let projects = $state<McpProject[]>([]);
	let projectsError = $state('');
	let projectScope = $state<'selected' | 'all'>('selected');
	let selectedProjectIds = $state<string[]>([]);
	let defaultProjectSelection = true;
	let loading = $state(false);
	let tokensLoading = $state(false);
	let grantsLoading = $state(false);
	let tokensError = $state('');
	let grantsError = $state('');
	const projectsReady = $derived(projectsScope === scope && isCurrentScope(scope) && !loading);
	const validProjectSelection = $derived(projectsReady && tokensScope === scope && !tokensError && projects.length > 0 && (projectScope === 'all'
		|| (selectedProjectIds.length > 0 && selectedProjectIds.every((id) => projects.some((project) => project.id === id)))));
	const mcpEnabled = $derived($siteConfig.services.mcp);
	const mcpUrl = $derived($siteConfig.mcp_url || `${getBaseUrl().replace(/\/+$/, '')}/api/v1/mcp`);
	const oauthAuthorizeUrl = $derived(`${mcpUrl.replace(/\/+$/, '')}/oauth/authorize`);

	type AccessMethod = 'oauth' | 'api';
	type Lifetime = '1d' | '1w' | '1m' | '3m' | '6m' | '1y' | 'never' | 'custom';
	type CopyTarget = 'oauth' | 'setup' | 'token' | 'config';
	let method = $state<AccessMethod>('oauth');
	let methodSequence = 0;
	let lifetime = $state<Lifetime>('1m');
	let copyStates = $state<Partial<Record<CopyTarget, 'copied' | 'failed'>>>({});
	const copySequences: Record<CopyTarget, number> = { oauth: 0, setup: 0, token: 0, config: 0 };
	let tokens = $state<McpAccessRecord[]>([]);
	let oauthGrants = $state<McpAccessRecord[]>([]);
	let actionError = $state('');
	let creating = $state(false);
	let mutatingId = $state<string | null>(null);
	let tokenName = $state('Lumen');
	let accessLevel = $state<'read' | 'manage'>('read');
	let expiresAt = $state('');
	let issuedToken = $state<string | null>(null);
	let showIssuedToken = $state(false);
	function clearCopies() {
		for (const target of ['oauth', 'setup', 'token', 'config'] as const) copySequences[target] += 1;
		copyStates = {};
	}
	let verificationToken = $state('');
	let verifying = $state(false);
	let verificationSource = $state<'issued' | 'saved' | null>(null);
	let verificationResult = $state<McpConnectionResult | null>(null);
	let verificationError = $state('');
	let verificationSequence = 0;
	let verificationController: AbortController | null = null;
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

	function invalidateIssuance() {
		issuanceSequence += 1;
		issuanceController?.abort();
		issuanceController = null;
		creating = false;
	}

	function clearVerification() {
		verificationSequence += 1;
		verificationController?.abort();
		verificationController = null;
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
		return method === 'api' && isCurrentScope(owner) && tokensScope === owner && !tokensLoading && !tokensError && tokens.includes(record);
	}

	function ownsGrant(owner: AccessScope, record: McpAccessRecord) {
		return method === 'oauth' && isCurrentScope(owner) && grantsScope === owner && !grantsLoading && !grantsError && oauthGrants.includes(record);
	}

	function reset() {
		loadController?.abort();
		loadController = null;
		tokensScope = null;
		grantsScope = null;
		invalidateIssuance();
		projectsScope = null;
		projects = [];
		projectsError = '';
		projectScope = 'selected';
		selectedProjectIds = [];
		defaultProjectSelection = true;
		tokens = [];
		oauthGrants = [];
		loading = false;
		tokensLoading = false;
		grantsLoading = false;
		tokensError = '';
		grantsError = '';
		actionError = '';
		mutatingId = null;
		tokenName = 'Lumen';
		accessLevel = 'read';
		lifetime = '1m';
		expiresAt = '';
		issuedToken = null;
		showIssuedToken = false;
		clearCopies();
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

	function toggleProject(owner: AccessScope, id: string) {
		if (!isCurrentScope(owner) || !projectsReady || creating || projectScope !== 'selected' || !projects.some((project) => project.id === id)) return;
		selectedProjectIds = selectedProjectIds.includes(id)
			? selectedProjectIds.filter((selected) => selected !== id)
			: [...selectedProjectIds, id];
	}

	async function loadProjectsFor(owner: AccessScope & { token: string; projectId: string }, request: number, signal: AbortSignal) {
		const previousSelection = selectedProjectIds;
		const useDefault = defaultProjectSelection;
		defaultProjectSelection = false;
		projectsScope = null;
		projects = [];
		selectedProjectIds = [];
		projectsError = '';
		try {
			const available = await api.get<McpProject[]>('/api/v1/auth/mcp-projects', owner.token, owner.projectId, { refresh: true, signal, suppressAuthRedirect: true });
			if (!isCurrentScope(owner) || request !== loadSequence) return;
			projects = available;
			projectsScope = owner;
			selectedProjectIds = (useDefault ? [owner.projectId] : previousSelection)
				.filter((id) => available.some((project) => project.id === id));
		} catch {
			if (isCurrentScope(owner) && request === loadSequence) projectsError = t('mcp.projectsLoadFailed');
		}
	}

	async function loadAccessFor(owner: AccessScope | null) {
		if (!isCurrentScope(owner)) return;
		const request = ++loadSequence;
		loadController?.abort();
		const controller = new AbortController();
		loadController = controller;
		const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]);
		tokensScope = null;
		grantsScope = null;
		tokens = [];
		oauthGrants = [];
		tokensError = '';
		grantsError = '';
		tokensLoading = true;
		grantsLoading = true;
		loading = true;
		// A reload invalidates both the editable project snapshot and pending issuance.
		invalidateIssuance();
		const token = owner.token;
		const projectId = owner.projectId;
		const current = () => isCurrentScope(owner) && request === loadSequence;
		async function loadRecords(kind: AccessMethod) {
			try {
				const records = await api.get<McpAccessRecord[]>(kind === 'api' ? '/api/v1/auth/mcp-tokens' : '/api/v1/auth/mcp-oauth/grants', token, projectId, { refresh: true, signal, suppressAuthRedirect: true });
				if (!current()) return;
				if (kind === 'api') { tokens = records; tokensScope = owner; }
				else { oauthGrants = records; grantsScope = owner; }
			} catch (error) {
				if (!current()) return;
				if (kind === 'api') tokensError = errorMessage(error, t('mcp.loadFailed'));
				else grantsError = errorMessage(error, t('mcp.loadFailed'));
			} finally {
				if (current()) {
					if (kind === 'api') tokensLoading = false;
					else grantsLoading = false;
				}
			}
		}
		await Promise.all([loadProjectsFor(owner, request, signal), loadRecords('api'), loadRecords('oauth')]);
		controller.abort();
		if (loadController === controller) loadController = null;
		if (current()) {
			if (tokensError) { projectScope = 'selected'; selectedProjectIds = []; }
			loading = false;
		}
	}

	function selectMethod(next: AccessMethod) {
		if (method === next) return;
		methodSequence += 1;
		method = next;
		invalidateIssuance();
		issuedToken = null;
		showIssuedToken = false;
		clearVerification();
		clearCopies();
		actionError = '';
	}

	function expirationPayload(now: Date): { non_expiring: true } | { expires_at: string } | null {
		if (lifetime === 'never') return { non_expiring: true };
		const expiry = lifetime === 'custom' ? new Date(expiresAt) : new Date(now.getTime());
		if (lifetime === '1d' || lifetime === '1w') {
			expiry.setUTCDate(expiry.getUTCDate() + (lifetime === '1d' ? 1 : 7));
		} else if (lifetime !== 'custom') {
			const months = { '1m': 1, '3m': 3, '6m': 6, '1y': 12 }[lifetime];
			// UTC calendar arithmetic preserves time and clamps the day to the target month-end.
			const day = expiry.getUTCDate();
			expiry.setUTCDate(1);
			expiry.setUTCMonth(expiry.getUTCMonth() + months);
			const monthEnd = new Date(expiry.getTime());
			monthEnd.setUTCMonth(monthEnd.getUTCMonth() + 1, 0);
			expiry.setUTCDate(Math.min(day, monthEnd.getUTCDate()));
		}
		if (!Number.isFinite(expiry.getTime()) || expiry.getTime() <= now.getTime()) return null;
		return { expires_at: expiry.toISOString() };
	}

	function submitToken(owner: AccessScope, event: SubmitEvent) {
		event.preventDefault();
		void createToken(owner);
	}

	async function createToken(owner: AccessScope) {
		if (!isCurrentScope(owner) || method !== 'api' || creating || !tokenName.trim() || !validProjectSelection) return;
		const expiration = expirationPayload(new Date());
		if (!expiration) {
			actionError = t('mcp.invalidExpiry');
			return;
		}
		const request = ++issuanceSequence;
		const projectRequest = loadSequence;
		const current = () => isCurrentScope(owner) && request === issuanceSequence && projectRequest === loadSequence;
		const controller = new AbortController();
		const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]);
		issuanceController = controller;
		creating = true;
		actionError = '';
		try {
			const issued = await api.post<IssuedToken>(
				'/api/v1/auth/mcp-tokens',
				{
					name: tokenName.trim(),
					access_level: accessLevel,
					project_scope: projectScope,
					project_ids: projectScope === 'all' ? [] : [...selectedProjectIds],
					...expiration,
				},
				owner.token,
				owner.projectId,
				{ signal, suppressAuthRedirect: true, cache: 'no-store' },
			);
			if (!current()) return;
			issuanceController = null;
			issuedToken = issued.token;
			showIssuedToken = true;
			clearCopies();
			clearVerification();
			tokenName = 'Lumen';
			lifetime = '1m';
			expiresAt = '';
			await loadAccessFor(owner);
		} catch (error) {
			if (current()) actionError = errorMessage(error, t('mcp.createFailed'));
		} finally {
			if (issuanceController === controller) issuanceController = null;
			if (current()) creating = false;
		}
	}

	function dismissIssuedToken(owner: AccessScope, secret: string | null) {
		if (!isCurrentScope(owner) || issuedToken !== secret) return;
		issuedToken = null;
		showIssuedToken = false;
		clearCopies();
		clearVerification();
	}

	async function copyContent(target: CopyTarget, owner: AccessScope, secret: string | null = null) {
		const secretTarget = target === 'token' || target === 'config';
		if (!isCurrentScope(owner) || (secretTarget && (!secret || issuedToken !== secret))) return;
		if (method !== (target === 'oauth' ? 'oauth' : 'api')) return;
		const content = () => target === 'oauth' ? oauthConfig : target === 'setup' ? setupConfig
			: target === 'config' ? connectionConfig(secret!) : secret!;
		const text = content();
		const selected = methodSequence;
		const request = ++copySequences[target];
		const current = () => isCurrentScope(owner) && selected === methodSequence && request === copySequences[target]
			&& (!secretTarget || issuedToken === secret) && content() === text;
		copyStates[target] = undefined;
		try {
			await navigator.clipboard.writeText(text);
			if (current()) copyStates[target] = 'copied';
		} catch {
			if (current()) copyStates[target] = 'failed';
		}
	}
	async function verifyConnection(owner: AccessScope, secret: string | null, source: 'issued' | 'saved') {
		if (!isCurrentScope(owner) || method !== 'api' || !secret?.trim() || verifying) return;
		if (source === 'issued' && secret !== issuedToken) return;
		const request = ++verificationSequence;
		const controller = new AbortController();
		const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]);
		verificationController = controller;
		const current = () => isCurrentScope(owner) && request === verificationSequence
			&& (source === 'issued' ? issuedToken === secret : verificationToken.trim() === secret.trim());
		verifying = true;
		verificationSource = source;
		verificationResult = null;
		verificationError = '';
		try {
			const result = await api.post<McpConnectionResult>(
				'/api/v1/auth/mcp-tokens/verify', { token: secret.trim() }, owner.token, owner.projectId,
				{ signal, suppressAuthRedirect: true, cache: 'no-store' },
			);
			if (current()) verificationResult = result;
		} catch (error) {
			if (current()) verificationError = verificationErrorMessage(error);
		} finally {
			if (verificationController === controller) verificationController = null;
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
		const selected = methodSequence;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.put(`/api/v1/auth/mcp-tokens/${encodeURIComponent(record.id)}/lumen-default`, {}, owner.token, owner.projectId);
			if (isCurrentScope(owner) && tokensScope === owner) await loadAccessFor(owner);
		} catch (error) {
			if (ownsToken(owner, record) && selected === methodSequence) actionError = errorMessage(error, t('mcp.selectFailed'));
		} finally {
			if (isCurrentScope(owner)) mutatingId = null;
		}
	}

	async function clearLumenDefault(owner: AccessScope, record: McpAccessRecord) {
		if (!isCurrentScope(owner) || !ownsToken(owner, record) || !record.is_lumen_default || mutatingId !== null) return;
		const selected = methodSequence;
		mutatingId = 'lumen-default';
		actionError = '';
		try {
			await api.delete('/api/v1/auth/mcp-tokens/lumen-default', owner.token, owner.projectId);
			if (isCurrentScope(owner) && tokensScope === owner) await loadAccessFor(owner);
		} catch (error) {
			if (ownsToken(owner, record) && selected === methodSequence) actionError = errorMessage(error, t('mcp.clearFailed'));
		} finally {
			if (isCurrentScope(owner)) mutatingId = null;
		}
	}

	async function revokeToken(owner: AccessScope, record: McpAccessRecord) {
		if (!isCurrentScope(owner) || !ownsToken(owner, record) || mutatingId !== null) return;
		const selected = methodSequence;
		const loaded = loadSequence;
		if (!(await confirmDialog(t('mcp.revokeConfirm', { name: record.name })))) return;
		if (!isCurrentScope(owner) || selected !== methodSequence || loaded !== loadSequence || !ownsToken(owner, record) || mutatingId !== null) return;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.delete(`/api/v1/auth/mcp-tokens/${encodeURIComponent(record.id)}`, owner.token, owner.projectId);
			if (isCurrentScope(owner) && tokensScope === owner) await loadAccessFor(owner);
		} catch (error) {
			if (ownsToken(owner, record) && selected === methodSequence) actionError = errorMessage(error, t('mcp.revokeFailed'));
		} finally {
			if (isCurrentScope(owner)) mutatingId = null;
		}
	}

	async function revokeOAuthGrant(owner: AccessScope, record: McpAccessRecord) {
		if (!isCurrentScope(owner) || !ownsGrant(owner, record) || mutatingId !== null) return;
		const selected = methodSequence;
		const loaded = loadSequence;
		if (!(await confirmDialog(t('mcp.revokeOAuthConfirm', { name: record.name })))) return;
		if (!isCurrentScope(owner) || selected !== methodSequence || loaded !== loadSequence || !ownsGrant(owner, record) || mutatingId !== null) return;
		mutatingId = record.id;
		actionError = '';
		try {
			await api.delete(`/api/v1/auth/mcp-oauth/grants/${encodeURIComponent(record.grant_id)}`, owner.token, owner.projectId);
			if (isCurrentScope(owner) && grantsScope === owner) await loadAccessFor(owner);
		} catch (error) {
			if (ownsGrant(owner, record) && selected === methodSequence) actionError = errorMessage(error, t('mcp.revokeOAuthFailed'));
		} finally {
			if (isCurrentScope(owner)) mutatingId = null;
		}
	}

	function formatDate(value: string | null) {
		if (!value) return '—';
		return new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
	}
	function formatObservationDate(value: string | null) {
		return value && Number.isFinite(Date.parse(value)) ? formatDate(value) : t('mcp.unknown');
	}


	$effect(() => {
		const owner = scope;
		if (isCurrentScope(owner)) untrack(() => void loadAccessFor(owner));
	});

	$effect(() => {
		// Changing the resource invalidates feedback and pending copies for the old JSON.
		mcpUrl;
		untrack(clearCopies);
	});
</script>

{#snippet clientObservations(record: McpAccessRecord)}
	{@const observations = (record.client_observations ?? []).slice(0, 10)}
	<div class="client-observations" role="group" aria-label={t('mcp.observations')}>
		{#if observations.length === 0}
			<p>{t('mcp.noObservations')}</p>
		{:else}
			<p>{t('mcp.observationHelp')}</p>
			<details>
				<summary class="min-h-11 py-3 md:min-h-0 md:py-0 cursor-pointer text-xs text-ink-1 focus-visible:outline-2 focus-visible:outline-accent">{t('mcp.observationCount', { count: observations.length })}</summary>
				<ul class="client-list">
					{#each observations as observation}
						<li>
							<p><strong>{observation.client_name || t('mcp.unknownClient')}</strong> · {t('mcp.clientVersion', { version: observation.client_version || t('mcp.unknown') })}</p>
							<p>{t('mcp.clientInference', { product: observation.product || t('mcp.unknown'), kind: t(`mcp.clientKind.${observation.kind}`) })}</p>
							<p>{t('mcp.clientEvidence', { source: t(`mcp.clientSource.${observation.identity_source}`) })}</p>
							<p>{t('mcp.clientPlatform', { browser: observation.browser || t('mcp.unknown'), os: observation.os || t('mcp.unknown') })}</p>
							<p>{t('mcp.clientDates', { first: formatObservationDate(observation.first_seen_at), last: formatObservationDate(observation.last_seen_at) })}</p>
						</li>
					{/each}
				</ul>
			</details>
		{/if}
	</div>
{/snippet}

{#snippet listFailure(error: string)}
	<Alert tone="danger" title={t('mcp.loadErrorTitle')}>
		{#snippet children()}
			<p>{error}</p>
			<Button variant="outline" size="sm" onclick={loadAccess}>{t('mcp.retryList')}</Button>
		{/snippet}
	</Alert>
{/snippet}

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

{#snippet savedRestrictions(record: McpAccessRecord)}
	<div class="saved-restrictions" role="group" aria-label={t('mcp.savedRestrictions')}>
		<p class="restriction-heading">{t('mcp.savedRestrictions')}</p>
		<p>{t('mcp.savedAccess', { access: record.access_level === 'manage' ? t('mcp.manage') : t('mcp.read') })}</p>
		{#if record.project_scope === 'all'}
			<p>{t('mcp.savedAllProjects')}</p>
		{:else if record.project_scope === 'selected'}
			<p>{t('mcp.savedSelectedProjects')}</p>
		{:else if record.project_scope === 'current'}
			<p>{t('mcp.savedCurrentProject')}</p>
		{/if}
		{#if record.projects?.length}
			<p>{t('mcp.savedProjects', { projects: record.projects.map((project) => `${project.name} (${project.id})`).join(', ') })}</p>
		{:else}
			<p>{t('mcp.savedProjectsUnavailable')}</p>
		{/if}
	</div>
{/snippet}

{#snippet jsonBlock(owner: AccessScope, target: CopyTarget, json: string, label: string, copyLabel: string, secret: string | null = null)}
	<div class="config-block" data-mcp-config={target}>
		<div class="config-header">
			<strong>mcp.json</strong>
			<Button variant="outline" size="sm" onclick={copyContent.bind(null, target, owner, secret)}>{copyStates[target] === 'copied' ? t('mcp.copied') : copyLabel}</Button>
		</div>
		<pre class="mcp-code" role="region" aria-label={label}>{json}</pre>
		{#if copyStates[target] === 'failed'}<p class="copy-error" role="alert">{t('mcp.copyFailed')}</p>{/if}
	</div>
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

		<div class="method-selection" role="group" aria-label={t('mcp.method')}>
			<Button class="method-card" variant={method === 'oauth' ? 'secondary' : 'outline'} ariaPressed={method === 'oauth'} onclick={() => selectMethod('oauth')}>{t('mcp.methodOAuth')}</Button>
			<Button class="method-card" variant={method === 'api' ? 'secondary' : 'outline'} ariaPressed={method === 'api'} onclick={() => selectMethod('api')}>{t('mcp.methodApiKey')}</Button>
		</div>

		{#if method === 'oauth'}
		<section aria-labelledby="mcp-oauth-setup-heading" class="connection-section">
			<h3 id="mcp-oauth-setup-heading">{t('mcp.oauthSetupTitle')}</h3>
			<p>{t('mcp.oauthSetupHelp')}</p>
			<p class="endpoint"><span>{t('mcp.oauthAuthorizeEndpoint')}</span><code>{oauthAuthorizeUrl}</code></p>
			{@render jsonBlock(owner, 'oauth', oauthConfig, t('mcp.oauthConfig'), t('mcp.copyOAuthConfig'))}
			<p>{t('mcp.oauthClientSecretHelp')}</p>
		</section>
		{/if}

		{#if method === 'api'}

		<Alert tone="warning" title={t('mcp.onceTitle')}>
			{#snippet children()}{t('mcp.onceHelp')}{/snippet}
		</Alert>
		{/if}

		{#if actionError}
			<Alert tone="danger" title={t('mcp.actionErrorTitle')}>
				{#snippet children()}{actionError}{/snippet}
			</Alert>
		{/if}

		{#if mutatingId}<ActivityIndicator label={tc('state.processing')} />{/if}
		{#if method === 'api'}
		<form class="token-form" onsubmit={submitToken.bind(null, owner)}>
			<Field label={t('mcp.name')} for="mcp-token-name" required>
				{#snippet children()}
					<input id="mcp-token-name" class="control" bind:value={tokenName} maxlength="100" autocomplete="off" disabled={creating} />
				{/snippet}
			</Field>
			<Field label={t('mcp.permission')} for="mcp-token-access">
				{#snippet children()}
					<select id="mcp-token-access" class="control" bind:value={accessLevel} disabled={creating} aria-describedby="mcp-permission-help">
						<option value="read">{t('mcp.read')}</option>
						<option value="manage">{t('mcp.manage')}</option>
					</select>
				{/snippet}
			</Field>
			<p class="permission-help" id="mcp-permission-help">{t('mcp.permissionHelp')}</p>
			<Field label={t('mcp.expiry')} for="mcp-token-expiry" help={t('mcp.expiryHelp')}>
				{#snippet children()}
					<select id="mcp-token-expiry" class="control" bind:value={lifetime} disabled={creating} onchange={() => { expiresAt = ''; actionError = ''; }}>
						<option value="1d">{t('mcp.expiry1d')}</option>
						<option value="1w">{t('mcp.expiry1w')}</option>
						<option value="1m">{t('mcp.expiry1m')}</option>
						<option value="3m">{t('mcp.expiry3m')}</option>
						<option value="6m">{t('mcp.expiry6m')}</option>
						<option value="1y">{t('mcp.expiry1y')}</option>
						<option value="never">{t('mcp.expiryNever')}</option>
						<option value="custom">{t('mcp.expiryCustom')}</option>
					</select>
				{/snippet}
			</Field>
			{#if lifetime === 'custom'}
				<Field label={t('mcp.customExpiry')} for="mcp-token-custom-expiry">
					{#snippet children()}
						<input id="mcp-token-custom-expiry" class="control" type="datetime-local" bind:value={expiresAt} disabled={creating} oninput={() => { actionError = ''; }} />
					{/snippet}
				</Field>
			{/if}
			<div class="project-selection">
				<Field label={t('mcp.projects')} for="mcp-token-project-scope" help={t('mcp.projectsHelp')}>
					{#snippet children()}
						<select id="mcp-token-project-scope" class="control" bind:value={projectScope} disabled={!projectsReady || creating} aria-describedby="mcp-token-project-scope-message">
							<option value="selected">{t('mcp.selectedProjects')}</option>
							<option value="all">{t('mcp.allProjects')}</option>
						</select>
					{/snippet}
				</Field>
				{#if projectsError}
					<Alert tone="danger" title={t('mcp.projectsLoadFailed')}>
						{#snippet children()}{t('mcp.projectsRetryHelp')}{/snippet}
					</Alert>
				{:else if !projectsReady}
					<ActivityIndicator label={t('mcp.projectsLoading')} />
				{:else if projects.length === 0}
					<p class="project-help">{t('mcp.noProjects')}</p>
				{:else if projectScope === 'selected'}
					<div class="project-options" role="group" aria-label={t('mcp.selectedProjects')}>
						{#each projects as project (project.id)}
							<div class="project-option">
								<SelectionCheckbox ariaLabel={t('mcp.selectProject', { name: project.name, id: project.id })} checked={selectedProjectIds.includes(project.id)} disabled={creating} onclick={toggleProject.bind(null, owner, project.id)} />
								<span>{project.name}<code>{project.id}</code></span>
							</div>
						{/each}
					</div>
					{#if selectedProjectIds.length === 0}<p class="project-help" role="alert">{t('mcp.projectsRequired')}</p>{/if}
				{/if}
			</div>
			<div class="token-submit"><Button type="submit" disabled={creating || !tokenName.trim() || !validProjectSelection}>{#if creating}<ActivityIndicator size="xs" label={t('mcp.creating')} />{:else}{t('mcp.create')}{/if}</Button></div>
		</form>
		<section aria-labelledby="mcp-setup-heading" class="connection-section">
			<h3 id="mcp-setup-heading">{t('mcp.setupTitle')}</h3>
			<p>{t('mcp.setupHelp')}</p>
			{@render jsonBlock(owner, 'setup', setupConfig, t('mcp.config'), t('mcp.copySetupConfig'))}
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
				{#if tokensScope === owner && !tokensError}<span><AnimatedNumber value={tokens.length} format={(n) => t('mcp.count', { count: Math.round(n) })} /></span>{/if}
			</div>
			{#if tokensError}
				{@render listFailure(tokensError)}
			{:else if tokensLoading}
				<div class="empty"><ActivityIndicator label={t('mcp.loadingAccess')} /></div>
			{:else if tokensScope === owner && tokens.length === 0}
				<p class="empty">{t('mcp.emptyTokens')}</p>
			{:else}
				<div class="records">
					{#each tokens as record (record.id)}
						<div class="record">
							<div class="record-main">
								<div class="record-title"><strong>{record.name}</strong><StatusChip status={record.status} /></div>
								<p>{t('mcp.recordDetails', { prefix: record.visible_prefix ?? t('mcp.noPrefix'), access: record.access_level === 'manage' ? t('mcp.manage') : t('mcp.read'), lastUsed: formatDate(record.last_used_at), expires: record.expires_at ? formatDate(record.expires_at) : t('mcp.expiryNever') })}</p>
								{@render savedRestrictions(record)}
								{@render clientObservations(record)}
								{#if record.is_lumen_default}<p class="default-note">{t('mcp.lumenDefault')}</p>{/if}
							</div>
							<div class="record-actions">
								{#if record.is_lumen_default}
									<Button variant="subtle" size="xs" onclick={clearLumenDefault.bind(null, owner, record)} disabled={mutatingId !== null}>{t('mcp.clearLumen')}</Button>
								{:else}
									<Button variant="outline" size="xs" onclick={selectLumenDefault.bind(null, owner, record)} disabled={mutatingId !== null || record.status !== 'active'}>{t('mcp.setLumen')}</Button>
								{/if}
								<Button class="min-h-11 md:min-h-0" variant="danger-outline" size="xs" onclick={revokeToken.bind(null, owner, record)} disabled={mutatingId !== null}>{t('mcp.revoke')}</Button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>
		{/if}

		{#if method === 'oauth'}

		<section aria-labelledby="mcp-oauth-grants-heading">
			<div class="subheading"><h3 id="mcp-oauth-grants-heading">{t('mcp.oauth')}</h3>{#if grantsScope === owner && !grantsError}<span><AnimatedNumber value={oauthGrants.length} format={(n) => t('mcp.count', { count: Math.round(n) })} /></span>{/if}</div>
			{#if grantsError}
				{@render listFailure(grantsError)}
			{:else if grantsLoading}
				<div class="empty"><ActivityIndicator label={t('mcp.loadingAccess')} /></div>
			{:else if grantsScope === owner && oauthGrants.length === 0}
				<p class="empty">{t('mcp.emptyOAuth')}</p>
			{:else if grantsScope === owner && oauthGrants.length > 0}
				<div class="records">
					{#each oauthGrants as record (record.id)}
						<div class="record">
							<div class="record-main">
								<div class="record-title"><strong>{record.name}</strong><StatusChip status={record.status} /></div>
								<p>{t('mcp.oauthDetails', { access: record.access_level === 'manage' ? t('mcp.manage') : t('mcp.read'), expires: formatDate(record.expires_at) })}</p>
								{@render savedRestrictions(record)}
								{@render clientObservations(record)}
							</div>
							<Button class="min-h-11 md:min-h-0" variant="danger-outline" size="xs" onclick={revokeOAuthGrant.bind(null, owner, record)} disabled={mutatingId !== null}>{t('mcp.revokeAccess')}</Button>
						</div>
					{/each}
				</div>
			{/if}
		</section>
		{/if}
	</Card>

	<Modal open={showIssuedToken} onClose={dismissIssuedToken.bind(null, owner, issuedToken)} ariaLabel={t('mcp.newToken')}>
		<Card surface="modal" padding="lg" class="issued-token-dialog">
			<h2>{t('mcp.newToken')}</h2>
			<p>{t('mcp.newTokenHelp')}</p>
			{#if issuedToken}
				<pre class="mcp-code">{issuedToken}</pre>
				<h3>{t('mcp.config')}</h3>
				<p>{t('mcp.configSecretWarning')}</p>
				{@render jsonBlock(owner, 'config', issuedConfig, t('mcp.config'), t('mcp.copyConfig'), issuedToken)}
			{/if}
			{#if copyStates.token === 'failed'}<p class="copy-error" role="alert">{t('mcp.copyFailed')}</p>{/if}
			{#if verificationSource === 'issued'}{@render connectionFeedback()}{/if}
			<div class="dialog-actions">
				<Button variant="outline" onclick={copyContent.bind(null, 'token', owner, issuedToken)}>{copyStates.token === 'copied' ? t('mcp.copied') : t('mcp.copy')}</Button>
				<Button variant="outline" onclick={verifyConnection.bind(null, owner, issuedToken, 'issued')} disabled={verifying}>
					{#if verifying}<ActivityIndicator size="xs" label={t('mcp.verifying')} />{:else}{t('mcp.verify')}{/if}
				</Button>
				<Button onclick={dismissIssuedToken.bind(null, owner, issuedToken)}>{t('mcp.done')}</Button>
			</div>
		</Card>
	</Modal>
{/if}

<style>
	:global(.mcp-access) { display: grid; gap: 1rem; min-width: 0; }
	.section-heading, .subheading, .record, .record-title, .record-actions, .dialog-actions { display: flex; align-items: center; }
	.section-heading, .subheading, .record { justify-content: space-between; gap: 1rem; }
	.section-heading h2, .subheading h3, :global(.issued-token-dialog h2) { margin: 0; color: var(--color-ink-0); }
	.section-heading h2 { font-size: 1rem; }
	.section-heading p, .record p, .empty, :global(.issued-token-dialog p) { margin: 0.25rem 0 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	.endpoint { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; margin: 0; color: var(--color-ink-2); font-size: 0.75rem; }
	.endpoint span { font-weight: 600; }
	.endpoint code { color: var(--color-ink-1); overflow-wrap: anywhere; }
	.method-selection { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; min-width: 0; }
	.method-selection :global(.method-card) { width: 100%; min-width: 0; min-height: 3.5rem; white-space: normal; overflow-wrap: anywhere; }
	.method-selection :global([aria-pressed='true']) { border-color: var(--color-accent); box-shadow: inset 0 0 0 1px var(--color-accent); }
	.config-block { min-width: 0; display: grid; gap: 0.5rem; }
	.config-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; color: var(--color-ink-1); font-size: 0.8125rem; }
	.config-header :global(button) { max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
	.copy-error { color: var(--color-state-danger-text); font-size: 0.8125rem; margin: 0; }
	.permission-help { grid-column: 1 / -1; margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	.token-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; align-items: start; min-width: 0; padding: 1rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-sunken); }
	.control { box-sizing: border-box; width: 100%; min-width: 0; min-height: 2.5rem; padding: 0.5rem 0.625rem; border: 1px solid var(--color-line-2); border-radius: 0.5rem; background: var(--color-surface-base); color: var(--color-ink-0); font: inherit; }
	.control:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
	.token-submit { padding-bottom: 0.0625rem; }
	.project-selection, .token-submit { grid-column: 1 / -1; min-width: 0; }
	.project-selection { display: grid; gap: 0.75rem; }
	.project-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); gap: 0.5rem; }
	.project-option { display: flex; align-items: center; gap: 0.75rem; min-width: 0; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-base); }
	.project-option span { min-width: 0; color: var(--color-ink-1); font-size: 0.8125rem; overflow-wrap: anywhere; }
	.project-option code { display: block; color: var(--color-ink-2); font-size: 0.75rem; }
	.project-help { margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	.record p { overflow-wrap: anywhere; }
	.saved-restrictions { margin-top: 0.75rem; padding-top: 0.5rem; border-top: 1px solid var(--color-line); }
	.record .restriction-heading { color: var(--color-ink-1); font-weight: 500; }
	.client-observations { margin-top: 0.75rem; padding-top: 0.5rem; border-top: 1px solid var(--color-line); font-size: 0.75rem; }
	.client-list { display: grid; gap: 0.5rem; list-style: none; margin: 0.5rem 0 0; padding: 0; }
	.client-list li { padding-left: 0.75rem; border-left: 1px solid var(--color-line); }
	.client-list strong { color: var(--color-ink-1); }
	.subheading { margin-bottom: 0.5rem; }
	.subheading h3 { font-size: 0.875rem; }
	.subheading span { color: var(--color-ink-2); font-size: 0.75rem; }
	.records { display: grid; gap: 0.5rem; }
	.record { align-items: flex-start; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: 0.625rem; background: var(--color-surface-base); }
	.record-main { min-width: 0; }
	.record-title { gap: 0.5rem; flex-wrap: wrap; }
	.record-title strong { color: var(--color-ink-0); font-size: 0.875rem; }
	.record-actions { flex-wrap: wrap; justify-content: flex-end; }
	:global(.issued-token-dialog) { box-sizing: border-box; width: min(44rem, calc(100vw - 2rem)); max-width: 100%; min-width: 0; display: grid; gap: 0.875rem; }
	:global(.issued-token-dialog h3), .connection-section h3 { margin: 0; color: var(--color-ink-0); font-size: 0.875rem; }
	.connection-section { min-width: 0; display: grid; gap: 0.75rem; }
	.connection-section p { margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.5; }
	:global(.mcp-code) { min-width: 0; margin: 0; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-sunken); color: var(--color-ink-0); font-size: 0.75rem; white-space: pre-wrap; overflow-wrap: anywhere; }
	.verification-form { display: grid; gap: 0.75rem; align-items: start; }
	.verification-form :global(button) { justify-self: start; }
	.verification-result p { margin: 0; overflow-wrap: anywhere; }
	.verification-result p + p { margin-top: 0.5rem; }
	.dialog-actions { justify-content: flex-end; flex-wrap: wrap; gap: 0.5rem; }
	.dialog-actions :global(button) { max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
	@media (max-width: 47.999rem) { .token-form { grid-template-columns: minmax(0, 1fr); } .section-heading { align-items: flex-start; } .record { align-items: flex-start; flex-direction: column; } .record-actions { justify-content: flex-start; } }
</style>
