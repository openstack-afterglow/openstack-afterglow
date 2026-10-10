<script lang="ts">
	import { onMount } from 'svelte';
	import { derived } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { api, ApiError } from '$lib/api/client';
	import { auth, projectSwitching } from '$lib/stores/auth';
	import {
		clearMcpConsentTicket,
		pendingMcpConsentTicket,
		storeMcpConsentTicket,
	} from '$lib/utils/mcpConsent';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	interface ConsentDetails {
		client_id: string;
		client_name: string;
		redirect_uri: string;
		scopes: string[];
		grant_deadline: string;
	}

	interface ConsentProject { id: string; name: string }
	interface Owner {
		token: string | null;
		userId: string | null;
		projectId: string | null;
		switching: boolean;
	}
	interface RequestContext { token: string; projectId: string; ticket: string; controller: AbortController }

	let owner: Owner | null = null;
	let ticket = $state<string | null>(null);
	let activeRequest: RequestContext | null = null;
	let decisionController: AbortController | null = null;
	let mounted = false;
	let loading = $state(true);
	let deciding = $state(false);
	let error = $state('');
	let consent = $state<ConsentDetails | null>(null);
	let projects = $state<ConsentProject[]>([]);
	let accessLevel = $state<'read' | 'manage'>('read');
	let projectScope = $state<'selected' | 'all'>('selected');
	let selectedProjectIds = $state<string[]>([]);
	const canApprove = $derived(!loading && !deciding && consent !== null && projects.length > 0
		&& (projectScope === 'all' || selectedProjectIds.length > 0));
	function message(error: unknown, fallback: string) {
		return error instanceof ApiError ? error.message : fallback;
	}

	function formatDeadline(value: string) {
		return new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value));
	}

	function clearSelection() {
		activeRequest?.controller.abort();
		decisionController?.abort();
		decisionController = null;
		activeRequest = null;
		consent = null;
		projects = [];
		selectedProjectIds = [];
		accessLevel = 'read';
		projectScope = 'selected';
		deciding = false;
	}

	function isCurrent(request: RequestContext) {
		return mounted && activeRequest === request;
	}

	// Store subscriptions invalidate synchronously, including a batched A → B → A.
	function reload() {
		clearSelection();
		loading = Boolean(ticket);
		if (!ticket) return;
		error = '';
		if (!owner || owner.switching) return;
		if (!owner.token) { void goto('/login'); return; }
		if (!owner.projectId) { void goto('/select-project'); return; }
		if (!owner.userId) return;
		const request = { token: owner.token, projectId: owner.projectId, ticket, controller: new AbortController() };
		activeRequest = request;
		void loadConsent(request);
	}

	async function loadConsent(request: RequestContext) {
		try {
			const [details, availableProjects] = await Promise.all([
				api.get<ConsentDetails>(
					`/api/v1/auth/mcp-oauth/consents/${encodeURIComponent(request.ticket)}`,
					request.token, request.projectId, { refresh: true, suppressAuthRedirect: true, signal: request.controller.signal },
				),
				api.get<ConsentProject[]>('/api/v1/auth/mcp-projects', request.token, request.projectId,
					{ refresh: true, suppressAuthRedirect: true, signal: request.controller.signal }),
			]);
			if (!isCurrent(request)) return;
			consent = details;
			projects = availableProjects;
			selectedProjectIds = availableProjects.some((project) => project.id === request.projectId)
				? [request.projectId] : [];
		} catch (errorValue) {
			if (!isCurrent(request)) return;
			clearSelection();
			error = message(errorValue, t('mcpConsent.error.loadFailed'));
			loading = false;
		} finally {
			if (isCurrent(request)) loading = false;
		}
	}

	async function decide(decision: 'approve' | 'deny') {
		const request = activeRequest;
		if (!request || !isCurrent(request) || !consent || loading || deciding) return;
		if (decision === 'approve' && (!canApprove || (accessLevel === 'manage' && !consent.scopes.includes('mcp:write')))) return;
		const body = decision === 'deny' ? {} : {
			access_level: accessLevel,
			project_scope: projectScope,
			project_ids: projectScope === 'all' ? [] : [...selectedProjectIds],
		};
		const controller = new AbortController();
		decisionController = controller;
		deciding = true;
		error = '';
		try {
			const result = await api.post<{ redirect_uri: string }>(
				`/api/v1/auth/mcp-oauth/consents/${encodeURIComponent(request.ticket)}/${decision}`,
				body, request.token, request.projectId,
				{
					signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
					suppressAuthRedirect: true, cache: 'no-store',
				},
			);
			if (!isCurrent(request) || controller.signal.aborted) return;
			clearMcpConsentTicket();
			ticket = null;
			clearSelection();
			window.location.assign(result.redirect_uri);
		} catch (errorValue) {
			if (!isCurrent(request)) return;
			error = message(errorValue, decision === 'approve' ? t('mcpConsent.error.approveFailed') : t('mcpConsent.error.denyFailed'));
		} finally {
			if (isCurrent(request) && decisionController === controller) {
				decisionController = null;
				deciding = false;
			}
		}
	}

	onMount(() => {
		mounted = true;
		ticket = pendingMcpConsentTicket();
		const unsubscribeOwner = derived([auth, projectSwitching], ([actor, switching]): Owner => ({
			token: actor.token, userId: actor.userId, projectId: actor.projectId, switching,
		})).subscribe((next) => {
			if (owner && owner.token === next.token && owner.userId === next.userId
				&& owner.projectId === next.projectId && owner.switching === next.switching) return;
			owner = next;
			reload();
		});
		const unsubscribePage = page.subscribe(({ url }) => {
			const queryTicket = url.searchParams.get('ticket');
			if (!queryTicket) return;
			const valid = storeMcpConsentTicket(queryTicket);
			try {
				history.replaceState(null, '', '/oauth/mcp/authorize');
			} catch {
				// URL cleanup is defense in depth; the backend still validates the ticket.
			}
			if (!valid) {
				clearMcpConsentTicket();
				ticket = null;
				clearSelection();
				loading = false;
				error = t('mcpConsent.error.invalidRequest');
				return;
			}
			if (ticket === queryTicket) return;
			ticket = queryTicket;
			reload();
		});
		if (!ticket && !error) error = t('mcpConsent.error.missingOrExpired');
		return () => {
			mounted = false;
			clearSelection();
			unsubscribeOwner();
			unsubscribePage();
		};
	});
</script>

<svelte:head>
	<meta name="referrer" content="no-referrer" />
</svelte:head>

<main class="consent-page">
	<Card surface="raised" padding="lg" class="consent-card motion-stagger">
		<header>
			<p class="eyebrow">{t('mcpConsent.eyebrow')}</p>
			<h1>{t('mcpConsent.title')}</h1>
			<p>{t('mcpConsent.description')}</p>
		</header>

		{#if error}
			<Alert tone="danger" title={t('mcpConsent.error.title')}>
				{#snippet children()}{error}{/snippet}
			</Alert>
		{/if}
		{#if loading}
			<ActivityIndicator label={t('mcpConsent.loading')} />
		{:else if consent}
			{@const requestsManage = consent.scopes.includes('mcp:write')}
			<section aria-labelledby="consent-client-heading" class="details">
				<div><span>{t('mcpConsent.details.client')}</span><strong id="consent-client-heading">{consent.client_name}</strong></div>
				<div><span>{t('mcpConsent.details.clientId')}</span><code>{consent.client_id}</code></div>
				<div><span>{t('mcpConsent.details.redirectUri')}</span><code>{consent.redirect_uri}</code></div>
				<div><span>{t('mcpConsent.details.permissions')}</span><div class="scopes">{#each consent.scopes as scope}<StatusChip status={scope === 'mcp:write' ? 'manage' : 'read'} />{/each}</div></div>
				<div><span>{t('mcpConsent.details.deadline')}</span><strong>{formatDeadline(consent.grant_deadline)}</strong></div>
			</section>
			<div class="choices">
				<Field label={t('mcpConsent.access.label')} for="mcp-consent-access" help={requestsManage ? t('mcpConsent.access.help') : t('mcpConsent.access.manageUnavailable')}>
					<SelectInput id="mcp-consent-access" value={accessLevel} disabled={deciding}
						onchange={(event) => { accessLevel = (event.target as HTMLSelectElement).value === 'manage' && requestsManage ? 'manage' : 'read'; }}>
						<option value="read">{t('mcpConsent.access.read')}</option>
						<option value="manage" disabled={!requestsManage}>{t('mcpConsent.access.manage')}</option>
					</SelectInput>
				</Field>
				<Field label={t('mcpConsent.projects.label')} for="mcp-consent-project-scope" help={t('mcpConsent.projects.help')}>
					<SelectInput id="mcp-consent-project-scope" value={projectScope} disabled={deciding || projects.length === 0}
						onchange={(event) => { projectScope = (event.target as HTMLSelectElement).value === 'all' ? 'all' : 'selected'; }}>
						<option value="selected">{t('mcpConsent.projects.selected')}</option>
						<option value="all">{t('mcpConsent.projects.all')}</option>
					</SelectInput>
				</Field>
			</div>
			{#if projectScope === 'selected'}
				<fieldset class="project-options" disabled={deciding}>
					<legend>{t('mcpConsent.projects.choose')}</legend>
					{#each projects as project (project.id)}
						<div class="project-option">
							<SelectionCheckbox ariaLabel={`${project.name} ${project.id}`} checked={selectedProjectIds.includes(project.id)} disabled={deciding}
								onclick={() => {
									if (deciding) return;
									selectedProjectIds = selectedProjectIds.includes(project.id)
										? selectedProjectIds.filter((id) => id !== project.id) : [...selectedProjectIds, project.id];
								}} />
							<span>{project.name}<code>{project.id}</code></span>
						</div>
					{/each}
				</fieldset>
			{/if}
			{#if projects.length === 0 || (projectScope === 'selected' && selectedProjectIds.length === 0)}
				<Alert tone="warning">
					{#snippet children()}{t('mcpConsent.projects.empty')}{/snippet}
				</Alert>
			{/if}
			<Alert tone={accessLevel === 'manage' ? 'warning' : 'info'} title={accessLevel === 'manage' ? t('mcpConsent.manage.title') : t('mcpConsent.read.title')}>
				{#snippet children()}{accessLevel === 'manage' ? t('mcpConsent.manage.body') : t('mcpConsent.read.body')}{/snippet}
			</Alert>
			<div class="actions">
				{#if deciding}
					<ActivityIndicator label={t('mcpConsent.actions.processing')} class="decision-activity motion-fade" />
				{/if}
				<Button variant="danger-outline" onclick={() => decide('deny')} disabled={deciding}>{t('mcpConsent.actions.deny')}</Button>
				<Button onclick={() => decide('approve')} disabled={!canApprove}>{accessLevel === 'manage' ? t('mcpConsent.actions.allowManage') : t('mcpConsent.actions.allowRead')}</Button>
			</div>
		{/if}
		{#if error && !consent && ticket}
			<Button variant="secondary" onclick={reload}>{t('mcpConsent.actions.retry')}</Button>
		{/if}
	</Card>
</main>

<style>
	.consent-page { display: grid; min-height: 100vh; place-items: center; padding: 1rem; background: var(--color-surface-canvas); }
	:global(.consent-card) { width: min(42rem, 100%); min-width: 0; display: grid; gap: 1rem; }
	header h1 { margin: 0; color: var(--color-ink-0); font-size: 1.5rem; }
	header p { margin: 0.5rem 0 0; color: var(--color-ink-2); line-height: 1.5; }
	.eyebrow { color: var(--color-accent) !important; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
	.details { display: grid; gap: 0.75rem; padding: 1rem; border: 1px solid var(--color-line); border-radius: 0.75rem; background: var(--color-surface-sunken); }
	.details > div { display: grid; gap: 0.25rem; }
	.details span { color: var(--color-ink-2); font-size: 0.75rem; }
	.details strong, .details code { color: var(--color-ink-0); font-size: 0.875rem; overflow-wrap: anywhere; }
	.scopes { display: flex; gap: 0.5rem; flex-wrap: wrap; }
	.choices { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); gap: 1rem; min-width: 0; }
	.choices :global(.field), .choices :global(select) { min-width: 0; }
	.project-options { display: grid; gap: 0.5rem; min-width: 0; margin: 0; padding: 0.75rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); }
	.project-options legend { color: var(--color-ink-1); font-size: 0.875rem; }
	.project-option { display: flex; align-items: flex-start; gap: 0.5rem; min-width: 0; color: var(--color-ink-0); font-size: 0.875rem; overflow-wrap: anywhere; }
	.project-option :global(.selection-checkbox) { flex-shrink: 0; }
	.project-options span { min-width: 0; }
	.project-options code { display: block; color: var(--color-ink-2); font-size: 0.75rem; }
	.actions :global(button) { max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
	.actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 0.5rem; }
	.actions :global(.decision-activity) { margin-right: auto; }
</style>
