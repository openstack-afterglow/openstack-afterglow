<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { derived, get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { api, ApiError } from '$lib/api/client';
	import { auth, projectSwitching, setAuth } from '$lib/stores/auth';
	import type { SessionTokenResponse } from '$lib/types/auth';
	import { domainAuthState } from '$lib/utils/authSession';
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
	import {
		canChooseWrite, isWriteOperation, MCP_OPERATIONS, nativeCloudAccess,
		type McpConsentProject, type McpOperation,
	} from '$lib/utils/mcpConsentPermissions';
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
	// Project ID -> chosen operations; a project is approved only when it has at least one.
	let operations = $state<Record<string, McpOperation[]>>({});
	let ongoing = $state(true);
	let reviewStep = $state<'client' | 'permissions'>('client');
	let heading = $state<HTMLHeadingElement>();
	let domainSwitching = $state(false);
	let domainError = $state('');
	// Table area only: a domain change refreshes the projects without leaving the permission step.
	let projectsRefreshing = $state(false);
	// Remounts the select so a failed switch snaps it back to the connected domain.
	let domainSelectKey = $state(0);
	let inlineDomainSwitch = false;
	const ongoingSupported = $derived(consent?.ongoing_supported === true);
	const requestsManage = $derived(consent?.scopes.includes('mcp:write') === true);
	const previewProjects = $derived(projects.filter((project) => (operations[project.id]?.length ?? 0) > 0));
	const accessLevel = $derived<'read' | 'manage'>(
		previewProjects.some((project) => operations[project.id].some(isWriteOperation)) ? 'manage' : 'read');
	const domainOptions = $derived.by(() => {
		const listed = $auth.availableDomains ?? [];
		const currentId = consent?.domain_id;
		return currentId && !listed.some((domain) => domain.id === currentId)
			? [{ id: currentId, name: consent?.domain_name ?? currentId }, ...listed]
			: listed;
	});
	const loopbackRedirect = $derived(consent !== null && isLoopback(consent.redirect_uri));
	const canApprove = $derived(!loading && !deciding && !domainSwitching && !projectsRefreshing && consent !== null && reviewStep === 'permissions'
		&& previewProjects.length > 0 && !decisionUnconfirmed);
	function message(error: unknown, fallback: string, observation: AuthExperience) {
		if (error instanceof ApiError) { observation.unknownMessage(); return error.message; }
		return fallback;
	}

	function isLoopback(uri: string) {
		try {
			const { protocol, hostname } = new URL(uri);
			return protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(hostname);
		} catch {
			return false;
		}
	}

	function allowed(project: McpConsentProject, operation: McpOperation) {
		return !isWriteOperation(operation) || (requestsManage && canChooseWrite(project));
	}
	function chosen(project: McpConsentProject, operation: McpOperation) {
		return operations[project.id]?.includes(operation) === true;
	}
	function withOperation(current: McpOperation[], operation: McpOperation, enabled: boolean): McpOperation[] {
		const next = MCP_OPERATIONS.filter((candidate) => candidate === operation ? enabled : current.includes(candidate));
		// Create and update always carry read.
		return next.some(isWriteOperation) && !next.includes('read') ? MCP_OPERATIONS.filter((candidate) => candidate === 'read' || next.includes(candidate)) : next;
	}
	function readLocked(project: McpConsentProject) {
		return (operations[project.id] ?? []).some(isWriteOperation);
	}
	function toggle(project: McpConsentProject, operation: McpOperation) {
		if (deciding || !allowed(project, operation) || (operation === 'read' && readLocked(project))) return;
		operations = { ...operations, [project.id]: withOperation(operations[project.id] ?? [], operation, !chosen(project, operation)) };
		observeChoice();
	}
	function columnProjects(operation: McpOperation) {
		return projects.filter((project) => allowed(project, operation));
	}
	function columnState(operation: McpOperation) {
		const eligible = columnProjects(operation);
		const count = eligible.filter((project) => chosen(project, operation)).length;
		return { all: eligible.length > 0 && count === eligible.length, some: count > 0 && count < eligible.length, eligible: eligible.length };
	}
	function toggleColumn(operation: McpOperation) {
		if (deciding) return;
		const enable = !columnState(operation).all;
		const next = { ...operations };
		for (const project of columnProjects(operation)) {
			if (operation === 'read' && !enable && readLocked(project)) continue;
			next[project.id] = withOperation(next[project.id] ?? [], operation, enable);
		}
		operations = next;
		observeChoice();
	}

	function observeChoice() {
		const epoch = ownerEpoch;
		const observation = beginAuthExperience('mcp.consent', 'select', () => mounted && epoch === ownerEpoch && consent !== null, 'mcp');
		reviewExperience = observation;
		recordChoice(observation);
		void observation.applied();
	}
	function recordChoice(observation: AuthExperience) {
		const selection = previewProjects.length === 0 ? 'none' : previewProjects.length === projects.length ? 'all' : 'some';
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
		operations = {};
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

	// `inline` refreshes only the project area after a domain change: the step, duration and client details stay.
	async function loadConsent(request: RequestContext, inline = false) {
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
			ongoing = inline ? ongoing && details.ongoing_supported === true : details.ongoing_supported === true;
			projects = availableProjects;
			operations = availableProjects.some((project) => project.id === request.projectId)
				? { [request.projectId]: ['read'] } : {};
			request.experience.state(availableProjects.length ? 'ready' : 'empty', inline ? 1 : 0);
			reviewExperience = request.experience;
			recordChoice(request.experience);
			rendered = true;
		} catch (errorValue) {
			if (!isCurrent(request)) { request.experience.discard(request.controller.signal.aborted ? 'aborted' : 'stale'); return; }
			const text = observedAuthText(request.experience, 'public-entry', t);
			const failure = message(errorValue, errorValue instanceof ApiError ? '' : text('mcpConsent.error.loadFailed'), request.experience);
			// A failed inline refresh leaves the session in the new domain, so the page falls back to the
			// ordinary load failure state (error and retry) instead of showing the old domain's details.
			clearSelection();
			error = failure;
			loading = false;
			projectsRefreshing = false;
			request.experience.state('error'); rendered = true;
		} finally {
			if (isCurrent(request)) { loading = false; projectsRefreshing = false; }
			if (rendered) void request.experience.applied();
		}
	}

	function refreshProjects() {
		const current = get(auth);
		if (!ticket || !current.token || !current.projectId || !current.userId) { reload(); return; }
		activeRequest?.controller.abort();
		const epoch = ownerEpoch;
		const experience = beginAuthExperience('mcp.consent', 'load', () => mounted && epoch === ownerEpoch, 'mcp');
		experience.state('loading', 1);
		const request = { token: current.token, projectId: current.projectId, ticket, controller: new AbortController(), experience };
		activeRequest = request;
		projectsRefreshing = true;
		projects = [];
		operations = {};
		void loadConsent(request, true);
	}

	// Re-scope only the working domain, then refresh the project area for the same ticket in place.
	async function switchDomain(target: string) {
		const current = get(auth);
		if (!target || target === consent?.domain_id || deciding || domainSwitching || projectsRefreshing || get(projectSwitching)
			|| !current.token || !domainOptions.some((domain) => domain.id === target)) {
			domainSelectKey++;
			return;
		}
		domainSwitching = true;
		domainError = '';
		inlineDomainSwitch = true;
		projectSwitching.set(true);
		let switched = false;
		try {
			const response = await api.post<SessionTokenResponse>('/api/v1/auth/token/domain', { domain_id: target }, current.token, undefined,
				{ replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' });
			setAuth(domainAuthState(response, current, target));
			switched = true;
		} catch {
			domainError = t('mcpConsent.domain.switchFailed');
			domainSelectKey++;
		} finally {
			projectSwitching.set(false);
			inlineDomainSwitch = false;
			domainSwitching = false;
		}
		if (switched) refreshProjects();
	}

	async function decide(decision: 'approve' | 'deny') {
		const request = activeRequest;
		if (!request || !isCurrent(request) || !consent || loading || deciding || decisionUnconfirmed) return;
		const epoch = ownerEpoch;
		const observation = beginAuthExperience('mcp.consent', decision, () => mounted && epoch === ownerEpoch, 'mcp');
		const text = observedAuthText(observation, 'public-entry', t);
		const unauthorizedWrite = previewProjects.some((project) => operations[project.id].some((operation) => !allowed(project, operation)));
		if (decision === 'approve' && (!canApprove || (ongoing && !ongoingSupported) || unauthorizedWrite)) { observation.validation('authority'); return; }
		observation.state('loading', reviewStep === 'client' ? 0 : 1);
		const requestedOngoing = decision === 'approve' && ongoing;
		// Uniform all-read or all-operation selections keep the pre-operation wire body, so an
		// older backend in a rolling upgrade still accepts them; mixed selections need the map.
		const uniform = previewProjects.every((project) => operations[project.id].length === (accessLevel === 'manage' ? MCP_OPERATIONS.length : 1));
		const body = decision === 'deny' ? {} : {
			access_level: accessLevel,
			project_scope: 'selected',
			project_ids: previewProjects.map((project) => project.id),
			...(uniform ? {} : { project_operations: Object.fromEntries(previewProjects.map((project) => [project.id, [...operations[project.id]]])) }),
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
			if (inlineDomainSwitch) return;
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
		{#if domainError}
			<Alert tone="danger">
				{#snippet children()}{domainError}{/snippet}
			</Alert>
		{/if}
		{#if loading}
			<LoadingState variant="section" label={t(domainSwitching ? 'mcpConsent.domain.switching' : 'mcpConsent.loading')} />
		{:else if consent && !decisionUnconfirmed}
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
			</div>
			<section class="operation-section" aria-labelledby="mcp-consent-operations">
				<h2 id="mcp-consent-operations" class="operation-heading">{t('mcpConsent.operations.label')}</h2>
				<div class="domain-field">
					{#if domainOptions.length > 1}
						<Field label={t('mcpConsent.details.domain')} for="mcp-consent-domain">
							{#key domainSelectKey}
								<SelectInput id="mcp-consent-domain" value={consent.domain_id ?? ''} disabled={deciding || domainSwitching || projectsRefreshing}
									onchange={(event) => void switchDomain((event.target as HTMLSelectElement).value)}>
									{#each domainOptions as domain (domain.id)}
										<option value={domain.id}>{domain.name}</option>
									{/each}
								</SelectInput>
							{/key}
						</Field>
					{:else}
						<p class="consent-domain"><span>{t('mcpConsent.details.domain')}</span> <strong>{consent.domain_name ?? ''}</strong></p>
					{/if}
					<code>{consent.domain_id ?? ''}</code>
					<p class="duration-help">{t('mcpConsent.domain.help')}</p>
				</div>
				<p class="duration-help">{t(requestsManage ? 'mcpConsent.operations.help' : 'mcpConsent.operations.readOnlyClient')}</p>
				{#if domainSwitching || projectsRefreshing}
					<LoadingState variant="section" label={t('mcpConsent.domain.switching')} />
				{:else if projects.length > 0}
					<div class="operation-table-scroll">
						<table class="operation-table" aria-labelledby="mcp-consent-operations">
							<thead>
								<tr>
									<th scope="col">{t('mcpConsent.operations.project')}</th>
									{#each MCP_OPERATIONS as operation (operation)}
										{@const column = columnState(operation)}
										<th scope="col">
											<span class="operation-column">
												<SelectionCheckbox ariaLabel={t('mcpConsent.operations.selectAll', { operation: t(`mcpConsent.operations.${operation}`) })}
													checked={column.all} indeterminate={column.some} disabled={deciding || column.eligible === 0}
													onclick={() => toggleColumn(operation)} />
												<span>{t(`mcpConsent.operations.${operation}`)}</span>
											</span>
											<small>{t(`mcpConsent.operations.${operation}Help`)}</small>
										</th>
									{/each}
								</tr>
							</thead>
							<tbody>
								{#each projects as project (project.id)}
									{@const ceiling = nativeCloudAccess(project)}
									<tr>
										<th scope="row">
											<span class="project-label">{project.name}<code>{project.id}</code></span>
											{#if ceiling !== 'manage'}
												<small class="project-ceiling">{t(`mcpConsent.operations.ceiling.${ceiling}`)}</small>
											{/if}
										</th>
										{#each MCP_OPERATIONS as operation (operation)}
											<td>
												<SelectionCheckbox ariaLabel={`${project.name} ${project.id} ${t(`mcpConsent.operations.${operation}`)}`}
													checked={chosen(project, operation)} disabled={deciding || !allowed(project, operation) || (operation === 'read' && readLocked(project))}
													onclick={() => toggle(project, operation)} />
											</td>
										{/each}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>
			{#if domainSwitching || projectsRefreshing}
				<!-- The project area above shows the refresh; no permission preview for a stale selection. -->
			{:else if previewProjects.length === 0}
				<Alert tone="warning">
					{#snippet children()}{t('mcpConsent.projects.empty')}{/snippet}
				</Alert>
			{:else}
				<McpPermissionPreview projects={previewProjects} {operations} />
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
			{#if loopbackRedirect}
				<p class="duration-help">{t('mcpConsent.remote.help')}</p>
			{/if}
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
	.domain-field { display: grid; gap: 0.25rem; min-width: 0; }
	.domain-field :global(select) { min-width: 0; }
	.domain-field code { color: var(--color-ink-2); font-size: var(--type-identifier); overflow-wrap: anywhere; }
	.consent-domain { margin: 0; color: var(--color-ink-1); font-size: var(--type-body); }
	.operation-section { display: grid; gap: 0.5rem; min-width: 0; }
	.operation-heading { margin: 0; color: var(--color-ink-0); font-size: 1rem; font-weight: 600; }
	.operation-table-scroll { min-width: 0; overflow-x: auto; }
	.operation-table { width: 100%; border-collapse: collapse; font-size: var(--type-support); }
	.operation-table th, .operation-table td { padding: 0.5rem 0.375rem; border-bottom: 1px solid var(--color-line); vertical-align: top; text-align: left; }
	.operation-table thead th { color: var(--color-ink-1); font-weight: 500; }
	.operation-table thead th:not(:first-child), .operation-table td { width: 5.5rem; text-align: center; }
	.operation-table small { display: block; margin-top: 0.125rem; color: var(--color-ink-2); font-size: var(--type-identifier); font-weight: 400; }
	.operation-column { display: inline-flex; align-items: center; gap: 0.25rem; }
	.operation-table tbody th { min-width: 0; color: var(--color-ink-0); font-weight: 400; overflow-wrap: anywhere; }
	.project-label code { display: block; color: var(--color-ink-2); font-size: var(--type-identifier); }
	.operation-table .project-ceiling { color: var(--color-state-warning-text); }
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
	@media (max-width: 479px) {
		.operation-table thead th:not(:first-child), .operation-table td { width: 3.75rem; }
		.operation-table thead small { display: none; }
	}
</style>
