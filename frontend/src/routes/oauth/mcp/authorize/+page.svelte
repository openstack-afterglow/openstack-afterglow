<script lang="ts">
	import { onMount, tick } from 'svelte';
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
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import AuthStudioShell from '$lib/components/auth/AuthStudioShell.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import { t as commonT } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import McpPermissionPreview from '$lib/components/account/McpPermissionPreview.svelte';
	import type { McpConsentProject } from '$lib/utils/mcpConsentPermissions';
	import { beginAuthExperience, observedAuthText, createAuthNoticePresenter, type AuthExperience } from '$lib/components/auth/authExperience';
	import { recordExperience } from '$lib/utils/experience';

	interface ConsentDetails {
		client_id: string;
		client_name: string;
		redirect_uri: string;
		scopes: string[];
		grant_deadline: string;
		ongoing_supported?: boolean;
		domain_id?: string | null;
		domain_name?: string | null;
	}

	interface Owner {
		token: string | null;
		userId: string | null;
		projectId: string | null;
		switching: boolean;
	}
	interface RequestContext { token: string; projectId: string; ticket: string; controller: AbortController; experience: AuthExperience }

	let owner: Owner | null = null;
	let ticket = $state<string | null>(null);
	let activeRequest: RequestContext | null = null;
	let decisionController: AbortController | null = null;
	let mounted = false;
	let ownerEpoch = 0;
	let reviewExperience = $state.raw<AuthExperience>();
	const presentNotice = createAuthNoticePresenter();
	let loading = $state(true);
	let deciding = $state(false);
	let error = $state('');
	let decisionUnconfirmed = $state(false);
	let consent = $state<ConsentDetails | null>(null);
	let projects = $state<McpConsentProject[]>([]);
	let accessLevel = $state<'read' | 'manage'>('read');
	let projectScope = $state<'selected' | 'all'>('selected');
	let selectedProjectIds = $state<string[]>([]);
	let ongoing = $state(true);
	let reviewStep = $state<'client' | 'permissions'>('client');
	let heading = $state<HTMLHeadingElement>();
	const ongoingSupported = $derived(consent?.ongoing_supported === true);
	const previewProjects = $derived(projectScope === 'all' ? projects
		: projects.filter((project) => selectedProjectIds.includes(project.id)));
	const unknownWrite = $derived(accessLevel === 'manage'
		&& previewProjects.some((project) => typeof project.can_write !== 'boolean'));
	const selectedReadOnly = $derived(accessLevel === 'manage' && projectScope === 'selected'
		&& previewProjects.some((project) => project.can_write === false));
	const canApprove = $derived(!loading && !deciding && consent !== null && reviewStep === 'permissions'
		&& previewProjects.length > 0 && !unknownWrite && !selectedReadOnly && !decisionUnconfirmed);
	function message(error: unknown, fallback: string, observation: AuthExperience) {
		if (error instanceof ApiError) { observation.unknownMessage(); return error.message; }
		return fallback;
	}

	function observeChoice() {
		const epoch = ownerEpoch;
		const observation = beginAuthExperience('mcp.consent', 'select', () => mounted && epoch === ownerEpoch && consent !== null, 'mcp');
		reviewExperience = observation;
		recordChoice(observation);
		void observation.applied();
	}
	function recordChoice(observation: AuthExperience) {
		const selection = previewProjects.length === 0 ? 'none'
			: projectScope === 'all' || previewProjects.length === projects.length ? 'all' : 'some';
		recordExperience(observation.context, 'view.state_changed', {
			state: 'ready', step: reviewStep === 'client' ? 0 : 1,
			access: selection === 'none' ? 'none' : accessLevel, selection,
		});
	}
	$effect(() => {
		const visible = consent !== null && !loading && !decisionUnconfirmed && reviewExperience !== undefined;
		const key = !visible ? null : reviewStep === 'client' ? ongoingSupported ? 'mcpConsent.duration.defaultHelp' : 'mcpConsent.duration.unsupported'
			: accessLevel === 'manage' ? 'mcpConsent.manage.body' : 'mcpConsent.read.body';
		if (key) t(key);
		presentNotice('body', reviewExperience, 'public-entry', key, reviewStep === 'permissions' && accessLevel === 'manage' ? 'warning' : 'info');
		const duration = !visible || reviewStep !== 'permissions' ? null : ongoing ? 'mcpConsent.duration.untilRevoked' : 'mcpConsent.duration.finite';
		if (duration) t(duration, { deadline: '' });
		presentNotice('duration', reviewExperience, 'public-entry', duration, ongoing ? 'warning' : 'info');
		const empty = visible && reviewStep === 'permissions' && !previewProjects.length ? 'mcpConsent.projects.empty' : null;
		if (empty) t(empty);
		presentNotice('empty', reviewExperience, 'public-entry', empty, 'warning');
		const warning = !visible || reviewStep !== 'permissions' ? null : unknownWrite ? 'mcpConsent.preview.unknownWrite' : selectedReadOnly ? 'mcpConsent.preview.selectedReadOnly' : null;
		if (warning) t(warning);
		presentNotice('authority', reviewExperience, 'public-entry', warning, 'warning');
	});

	function formatDeadline(value: string) {
		return new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value));
	}

	async function showStep(step: 'client' | 'permissions') {
		if (deciding) return;
		const epoch = ownerEpoch;
		const observation = beginAuthExperience('mcp.consent', 'select', () => mounted && epoch === ownerEpoch && reviewStep === step, 'mcp');
		reviewStep = step;
		reviewExperience = observation;
		recordChoice(observation);
		void observation.applied();
		await tick();
		heading?.focus();
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
		ongoing = true;
		reviewStep = 'client';
		deciding = false;
		decisionUnconfirmed = false;
	}

	function isCurrent(request: RequestContext) {
		return mounted && activeRequest === request;
	}

	// Store subscriptions invalidate synchronously, including a batched A → B → A.
	function reload(action: 'load' | 'retry' = 'load') {
		const epoch = ++ownerEpoch;
		clearSelection();
		loading = Boolean(ticket);
		if (!ticket) return;
		error = '';
		if (!owner || owner.switching) return;
		if (!owner.token) { void goto('/login'); return; }
		if (!owner.projectId) { void goto('/select-project'); return; }
		if (!owner.userId) return;
		const experience = beginAuthExperience('mcp.consent', action, () => mounted && epoch === ownerEpoch, 'mcp');
		experience.state('loading', 0);
		const request = { token: owner.token, projectId: owner.projectId, ticket, controller: new AbortController(), experience };
		activeRequest = request;
		void loadConsent(request);
	}

	async function loadConsent(request: RequestContext) {
		let rendered = false;
		try {
			const [details, availableProjects] = await Promise.all([
				api.get<ConsentDetails>(
					`/api/v1/auth/mcp-oauth/consents/${encodeURIComponent(request.ticket)}`,
					request.token, request.projectId, { refresh: true, suppressAuthRedirect: true, signal: request.controller.signal, ...request.experience.options },
				),
				api.get<McpConsentProject[]>('/api/v1/auth/mcp-projects?preview=true', request.token, request.projectId,
					{ refresh: true, suppressAuthRedirect: true, cache: 'no-store', replayOnUnauthorized: true, timeoutMs: 40_000, signal: request.controller.signal, ...request.experience.options }),
			]);
			if (!isCurrent(request)) { request.experience.discard(request.controller.signal.aborted ? 'aborted' : 'stale'); return; }
			consent = details;
			ongoing = details.ongoing_supported === true;
			projects = availableProjects;
			selectedProjectIds = availableProjects.some((project) => project.id === request.projectId)
				? [request.projectId] : [];
			request.experience.state(availableProjects.length ? 'ready' : 'empty', 0);
			reviewExperience = request.experience;
			recordChoice(request.experience);
			rendered = true;
		} catch (errorValue) {
			if (!isCurrent(request)) { request.experience.discard(request.controller.signal.aborted ? 'aborted' : 'stale'); return; }
			clearSelection();
			const text = observedAuthText(request.experience, 'public-entry', t);
			error = message(errorValue, errorValue instanceof ApiError ? '' : text('mcpConsent.error.loadFailed'), request.experience);
			loading = false;
			request.experience.state('error'); rendered = true;
		} finally {
			if (isCurrent(request)) loading = false;
			if (rendered) void request.experience.applied();
		}
	}

	async function decide(decision: 'approve' | 'deny') {
		const request = activeRequest;
		if (!request || !isCurrent(request) || !consent || loading || deciding || decisionUnconfirmed) return;
		const epoch = ownerEpoch;
		const observation = beginAuthExperience('mcp.consent', decision, () => mounted && epoch === ownerEpoch, 'mcp');
		const text = observedAuthText(observation, 'public-entry', t);
		if (decision === 'approve' && (!canApprove || (ongoing && !ongoingSupported)
			|| (accessLevel === 'manage' && !consent.scopes.includes('mcp:write')))) { observation.validation('authority'); return; }
		observation.state('loading', reviewStep === 'client' ? 0 : 1);
		const requestedOngoing = decision === 'approve' && ongoing;
		const body = decision === 'deny' ? {} : {
			access_level: accessLevel,
			project_scope: projectScope,
			project_ids: projectScope === 'all' ? [] : [...selectedProjectIds],
			...(ongoing ? { ongoing: true } : {}),
		};
		const controller = new AbortController();
		decisionController = controller;
		deciding = true;
		error = '';
		let rendered = false;
		try {
			const result = await api.post<{ redirect_uri: string; effective_ongoing?: boolean }>(
				`/api/v1/auth/mcp-oauth/consents/${encodeURIComponent(request.ticket)}/${decision}`,
				body, request.token, request.projectId,
				{
					signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
					suppressAuthRedirect: true, cache: 'no-store', ...observation.options,
				},
			);
			if (!isCurrent(request) || controller.signal.aborted) { observation.discard(controller.signal.aborted ? 'aborted' : 'stale'); return; }
			if (decision === 'approve' && (requestedOngoing ? result.effective_ongoing !== true
				: result.effective_ongoing !== undefined && result.effective_ongoing !== false)) {
				clearMcpConsentTicket();
				ticket = null;
				decisionUnconfirmed = true;
				error = text('mcpConsent.error.durationUnconfirmed');
				observation.state('error'); rendered = true;
				return;
			}
			clearMcpConsentTicket();
			ticket = null;
			clearSelection();
			// Browser approval/denial received is not remote client readiness or redirect commit.
			rendered = true;
			window.location.assign(result.redirect_uri);
		} catch (errorValue) {
			if (!isCurrent(request)) { observation.discard(controller.signal.aborted ? 'aborted' : 'stale'); return; }
			error = message(errorValue, errorValue instanceof ApiError ? '' : text(decision === 'approve' ? 'mcpConsent.error.approveFailed' : 'mcpConsent.error.denyFailed'), observation);
			observation.state('error'); rendered = true;
		} finally {
			if (isCurrent(request) && decisionController === controller) {
				decisionController = null;
				deciding = false;
			}
			if (rendered) void observation.applied();
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
				ownerEpoch++;
				const observation = beginAuthExperience('mcp.consent', 'load', () => mounted, 'mcp');
				clearMcpConsentTicket();
				ticket = null;
				clearSelection();
				loading = false;
				const text = observedAuthText(observation, 'public-entry', t);
				error = text('mcpConsent.error.invalidRequest');
				observation.validation('format'); observation.state('error'); void observation.applied();
				return;
			}
			if (ticket === queryTicket) return;
			ticket = queryTicket;
			reload();
		});
		if (!ticket && !error) {
			const observation = beginAuthExperience('mcp.consent', 'load', () => mounted, 'mcp');
			error = observedAuthText(observation, 'public-entry', t)('mcpConsent.error.missingOrExpired');
			observation.state('error'); void observation.applied();
		}
		return () => {
			mounted = false;
			ownerEpoch++;
			clearSelection();
			unsubscribeOwner();
			unsubscribePage();
		};
	});
</script>

<svelte:head>
	<meta name="referrer" content="no-referrer" />
</svelte:head>

<AuthStudioShell
	variant="consent"
	wide
	localeId="mcp-consent-locale"
	themeId="mcp-consent-theme"
	footerNote={t('mcpConsent.eyebrow')}
>
	<div class="auth-flow">
		<header class="auth-flow-heading">
			<h1 bind:this={heading} tabindex="-1">{reviewStep === 'client' ? t('mcpConsent.title') : t('mcpConsent.projects.choose')}</h1>
			<p>{t('mcpConsent.description')}</p>
		</header>
		{#if error}
			<Alert tone="danger" title={t('mcpConsent.error.title')}>
				{#snippet children()}{error}{/snippet}
			</Alert>
		{/if}
		{#if loading}
			<LoadingState variant="section" label={t('mcpConsent.loading')} />
		{:else if consent && !decisionUnconfirmed}
			{@const requestsManage = consent.scopes.includes('mcp:write')}
			{#if reviewStep === 'client'}
				<dl aria-label={t('mcpConsent.details.client')} class="consent-details">
					<div><dt>{t('mcpConsent.details.client')}</dt><dd><strong>{consent.client_name}</strong></dd></div>
					<div><dt>{t('mcpConsent.details.domain')}</dt><dd><strong>{consent.domain_name ?? ''}</strong> <code>{consent.domain_id ?? ''}</code></dd></div>
					<div><dt>{t('mcpConsent.details.clientId')}</dt><dd><code>{consent.client_id}</code></dd></div>
					<div><dt>{t('mcpConsent.details.redirectUri')}</dt><dd><code>{consent.redirect_uri}</code></dd></div>
					<div><dt>{t('mcpConsent.details.permissions')}</dt><dd class="scopes">{#each consent.scopes as scope}<StatusChip status={scope === 'mcp:write' ? 'manage' : 'read'} label={scope} />{/each}</dd></div>
					<div><dt>{t('mcpConsent.details.deadline')}</dt><dd><strong>{formatDeadline(consent.grant_deadline)}</strong></dd></div>
				</dl>
				<p class="duration-help">{t(ongoingSupported ? 'mcpConsent.duration.defaultHelp' : 'mcpConsent.duration.unsupported')}</p>
				<div class="auth-flow-actions">
					{#if deciding}
						<LoadingState variant="inline" label={t('mcpConsent.actions.processing')} class="decision-activity" />
					{/if}
					<Button variant="danger-outline" onclick={() => decide('deny')} disabled={deciding}>{t('mcpConsent.actions.deny')}</Button>
					<Button onclick={() => showStep('permissions')} disabled={deciding}>{commonT('pagination.next')}</Button>
				</div>
			{:else}
			<div class="consent-client-summary">
				<strong>{consent.client_name}</strong>
				<code>{consent.client_id}</code>
				<p class="consent-domain"><span>{t('mcpConsent.details.domain')}</span> <strong>{consent.domain_name ?? ''}</strong> <code>{consent.domain_id ?? ''}</code></p>
				<p class="consent-domain-help">{t('mcpConsent.domain.help')}</p>
				{#if ($auth.availableDomains?.length ?? 0) > 1}
					<Button variant="secondary" onclick={() => void goto('/select-domain')} disabled={deciding}>{t('mcpConsent.domain.change')}</Button>
				{/if}
			</div>
			<div class="choices auth-flow-fields">
				<Field label={t('mcpConsent.access.label')} for="mcp-consent-access" help={requestsManage ? t('mcpConsent.access.help') : t('mcpConsent.access.manageUnavailable')}>
					<SelectInput id="mcp-consent-access" value={accessLevel} disabled={deciding}
						onchange={(event) => { accessLevel = (event.target as HTMLSelectElement).value === 'manage' && requestsManage ? 'manage' : 'read'; observeChoice(); }}>
						<option value="read">{t('mcpConsent.access.read')}</option>
						<option value="manage" disabled={!requestsManage}>{t('mcpConsent.access.manage')}</option>
					</SelectInput>
				</Field>
				<Field label={t('mcpConsent.projects.label')} for="mcp-consent-project-scope" help={t('mcpConsent.projects.help')}>
					<SelectInput id="mcp-consent-project-scope" value={projectScope} disabled={deciding || projects.length === 0}
						onchange={(event) => { projectScope = (event.target as HTMLSelectElement).value === 'all' ? 'all' : 'selected'; observeChoice(); }}>
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
									observeChoice();
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
			{#if previewProjects.length > 0}
				<McpPermissionPreview projects={previewProjects} {accessLevel} />
			{/if}
			{#if unknownWrite || selectedReadOnly}
				<Alert tone="warning">
					{#snippet children()}{t(unknownWrite ? 'mcpConsent.preview.unknownWrite' : 'mcpConsent.preview.selectedReadOnly')}{/snippet}
				</Alert>
			{/if}
			<Alert tone={accessLevel === 'manage' ? 'warning' : 'info'} title={accessLevel === 'manage' ? t('mcpConsent.manage.title') : t('mcpConsent.read.title')}>
				{#snippet children()}{accessLevel === 'manage' ? t('mcpConsent.manage.body') : t('mcpConsent.read.body')}{/snippet}
			</Alert>
			<fieldset class="duration-options" disabled={deciding} aria-describedby="mcp-consent-duration-help mcp-consent-revocation-help">
				<legend>{t('mcpConsent.duration.title')}</legend>
				<div class="duration-option">
					<SelectionCheckbox ariaLabel={t('mcpConsent.duration.ongoingLabel')} checked={ongoing} disabled={deciding || !ongoingSupported}
						onclick={() => { if (!deciding && ongoingSupported) { ongoing = !ongoing; observeChoice(); } }} />
					<span>{t('mcpConsent.duration.ongoingLabel')}</span>
				</div>
				<p id="mcp-consent-duration-help" class="duration-help">{t(ongoingSupported ? 'mcpConsent.duration.help' : 'mcpConsent.duration.unsupported')}</p>
				<Alert tone={ongoing ? 'warning' : 'info'}>
					{#snippet children()}{ongoing ? t('mcpConsent.duration.untilRevoked') : t('mcpConsent.duration.finite', { deadline: formatDeadline(consent!.grant_deadline) })}{/snippet}
				</Alert>
				<p id="mcp-consent-revocation-help" class="duration-help">{t('mcpConsent.duration.revocation')}</p>
			</fieldset>
			<div class="auth-flow-actions">
				{#if deciding}
					<LoadingState variant="inline" label={t('mcpConsent.actions.processing')} class="decision-activity" />
				{/if}
				<Button variant="secondary" onclick={() => showStep('client')} disabled={deciding}>{commonT('pagination.previous')}</Button>
				<Button variant="danger-outline" onclick={() => decide('deny')} disabled={deciding}>{t('mcpConsent.actions.deny')}</Button>
				<Button onclick={() => decide('approve')} disabled={!canApprove}>{accessLevel === 'manage' ? t('mcpConsent.actions.allowManage') : t('mcpConsent.actions.allowRead')}</Button>
			</div>
			{/if}
		{/if}
		{#if error && !consent && ticket}
			<Button variant="secondary" onclick={() => reload('retry')}>{t('mcpConsent.actions.retry')}</Button>
		{/if}
	</div>
</AuthStudioShell>

<style>
	.consent-details { display: grid; gap: 0.75rem; min-width: 0; margin: 0; }
	.consent-details > div { display: grid; gap: 0.25rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--color-line); min-width: 0; }
	.consent-details dt { color: var(--color-ink-2); font-size: var(--type-identifier); }
	.consent-details dd { min-width: 0; margin: 0; color: var(--color-ink-0); font-size: var(--type-body); overflow-wrap: anywhere; }
	.consent-details strong { font-weight: 500; }
	.consent-details code, .consent-client-summary code { font-size: var(--type-identifier); overflow-wrap: anywhere; }
	.scopes { display: flex; gap: 0.5rem; flex-wrap: wrap; }
	.scopes :global(.chip .label) { white-space: normal; overflow-wrap: anywhere; }
	.consent-client-summary { display: grid; gap: 0.25rem; min-width: 0; padding-bottom: 0.75rem; border-bottom: 1px solid var(--color-line); }
	.consent-client-summary strong { font-size: var(--type-body); font-weight: 500; }
	.consent-client-summary code { color: var(--color-ink-2); }
	.choices { grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); }
	.choices :global(.field), .choices :global(select) { min-width: 0; }
	.project-options { display: grid; gap: 0.5rem; min-width: 0; margin: 0; padding: 0; border: 0; }
	.project-options legend { margin-bottom: 0.5rem; color: var(--color-ink-1); font-size: var(--type-body); }
	.project-option { display: flex; align-items: flex-start; gap: 0.5rem; min-width: 0; padding-block: 0.5rem; color: var(--color-ink-0); font-size: var(--type-body); overflow-wrap: anywhere; }
	.project-option :global(.selection-checkbox) { flex-shrink: 0; }
	.project-options span { min-width: 0; }
	.project-options code { display: block; color: var(--color-ink-2); font-size: var(--type-identifier); }
	.duration-options { display: grid; gap: 0.75rem; min-width: 0; margin: 0; padding: 0; border: 0; }
	.duration-options legend { margin-bottom: 0.5rem; color: var(--color-ink-1); font-size: var(--type-body); }
	.duration-option { display: flex; align-items: center; gap: 0.5rem; min-width: 0; color: var(--color-ink-0); font-size: var(--type-body); overflow-wrap: anywhere; }
	.duration-option :global(.selection-checkbox) { flex-shrink: 0; width: var(--control-touch-height); height: var(--control-touch-height); }
	.duration-help { margin: 0; color: var(--color-ink-2); font-size: var(--type-support); overflow-wrap: anywhere; }
	.auth-flow-actions :global(button) { max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
	.auth-flow-actions :global(.decision-activity) { flex-basis: 100%; }
	@media (min-width: 640px) {
		.consent-details { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem 1.25rem; }
		.consent-details > div:nth-child(3) { grid-column: 1 / -1; }
	}
</style>
