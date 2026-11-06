<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import { quotaFields, type QuotaField } from '$lib/api/workspaceIam';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { t } from '$lib/i18n/ns/admin-system';
	import { t as tq } from '$lib/i18n/ns/workspace-iam';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button, Card, Field, SelectInput, TextInput } from '$lib/components/ui';
	import type { EnrollmentPolicy, EnrollmentPolicyWrite, SignupRequest, SignupRequestFilter, SignupRequestPage } from '$lib/types/enrollmentPolicy';
	import PersonalQuotaConvergence from './PersonalQuotaConvergence.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import { sessionScopeKey } from '$lib/utils/authSession';
	import { createTableView, type TableViewState } from '$lib/utils/tableView.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';

	let { section = 'all' }: { section?: 'all' | 'policy' | 'quotas' | 'requests' } = $props();
	const uid = $props.id();
	const policyPath = '/api/v1/admin/enrollment-policy';
	const queuePath = '/api/v1/admin/signup-requests';
	const readOptions = { refresh: true, cache: 'no-store', replayOnUnauthorized: false } as const;
	const writeOptions = { cache: 'no-store', replayOnUnauthorized: false } as const;
	const filters: SignupRequestFilter[] = ['pending', 'approved', 'rejected', 'all'];
	const knownFields = new Set<string>(Object.values(quotaFields).flat());

	let mounted = $state(false);
	let epoch = $state(0);
	let policy = $state<EnrollmentPolicy | null>(null);
	let publicSignup = $state(false);
	let signupButtonVisible = $state(false);
	let approvalMode = $state('auto');
	let quotas = $state<Record<string, string>>({});
	let policyLoading = $state(false);
	let saving = $state(false);
	let reloadRequired = $state(false);
	let policyError = $state('');
	let policyNotice = $state('');
	let filter = $state<SignupRequestFilter>('pending');
	let page = $state<SignupRequestPage | null>(null);
	let cursor = $state<string | null>(null);
	let history = $state<Array<string | null>>([]);
	let queueLoading = $state(false);
	let decisionId = $state<string | null>(null);
	let queueError = $state('');
	let queueNotice = $state('');
	let policyRead = 0;
	let queueRead = 0;
	let queueSearch = $state('');
	const queuePresentation = $state<TableViewState>({ sort: null, filters: {} });
	const queueView = createTableView<SignupRequest>({
		rows: () => authorized ? page?.items ?? [] : [],
		search: () => queueSearch,
		state: queuePresentation,
		columns: () => [
			{ key: 'email', label: tc('table.email'), value: (row) => row.email },
			{ key: 'id', label: t('enrollment.requestId'), value: (row) => row.id },
			{
				key: 'status', label: t('enrollment.status'), value: (row) => row.status,
				format: (_value, row) => t(`enrollment.status.${row.status}`),
				filterMode: 'single',
				filterOptions: () => filters.filter((status) => status !== 'all').map((status) => ({ value: status, label: t(`enrollment.status.${status}`), count: null })),
				filterSelection: () => filter === 'all' ? null : [filter],
				onFilterChange: (values) => {
					if (!allowed() || decisionId) return;
					const next = values?.[0] ?? 'all';
					if (!filters.includes(next as SignupRequestFilter)) return;
					filter = next as SignupRequestFilter;
					void loadQueue(null, []);
				},
			},
			{ key: 'source', label: t('enrollment.source'), value: (row) => row.source, format: (_value, row) => t(`enrollment.source.${row.source}`) },
			{ key: 'domain', label: t('enrollment.domain'), value: (row) => row.domain_id },
			{ key: 'provider', label: t('enrollment.provider'), value: (row) => row.provider_id },
			{ key: 'created', label: t('enrollment.created'), value: (row) => row.created_at },
			{ key: 'reviewed', label: t('enrollment.reviewed'), value: (row) => row.reviewed_at },
			{ key: 'reviewer', label: t('enrollment.reviewer'), value: (row) => row.reviewed_by_user_id },
		],
	});

	function allowed() {
		const state = get(auth);
		return mounted && get(authReady) && !get(projectSwitching) && !get(logoutInProgress)
			&& !!state.token && !!state.userId && state.isSystemAdmin;
	}

	const authorized = $derived.by(() => { epoch; return allowed(); });
	function capture() {
		if (!allowed()) return null;
		const ticket = epoch;
		const state = get(auth);
		return { token: state.token!, projectId: state.projectId ?? undefined,
			current: () => allowed() && epoch === ticket };
	}

	function clearPrivateState(preservePresentation = false) {
		policy = null; page = null; quotas = {}; publicSignup = false; signupButtonVisible = false; approvalMode = 'auto';
		policyError = ''; policyNotice = ''; queueError = ''; queueNotice = '';
		saving = false; decisionId = null; policyLoading = false; queueLoading = false;
		reloadRequired = false; cursor = null; history = [];
		if (!preservePresentation) {
			filter = 'pending'; queueSearch = '';
			queuePresentation.sort = null; queuePresentation.filters = {};
		}
	}

	onMount(() => {
		mounted = true;
		const fingerprint = () => {
			const state = get(auth);
			return JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId,
				state.token, state.projectId, state.isSystemAdmin, get(authReady), get(projectSwitching), get(logoutInProgress)]);
		};
		let key = fingerprint();
		const displayFingerprint = () => {
			const state = get(auth);
			return JSON.stringify([sessionScopeKey(state), state.isSystemAdmin, get(authReady), get(projectSwitching), get(logoutInProgress)]);
		};
		let displayKey = displayFingerprint();
		const changed = () => {
			const next = fingerprint();
			if (next === key) return;
			const nextDisplayKey = displayFingerprint();
			const preservePresentation = nextDisplayKey === displayKey && allowed();
			key = next;
			displayKey = nextDisplayKey;
			// Invalidate credentials and pending work even when retaining display-only conditions.
			++epoch;
			clearPrivateState(preservePresentation);
		};
		const unsubscribers = [auth.subscribe(changed), authReady.subscribe(changed), projectSwitching.subscribe(changed), logoutInProgress.subscribe(changed)];
		return () => { mounted = false; ++epoch; for (const unsubscribe of unsubscribers) unsubscribe(); };
	});

	$effect(() => {
		if (!mounted) return;
		epoch;
		untrack(() => { if (allowed()) { void loadPolicy(); void loadQueue(null, []); } });
	});

	function applyPolicy(next: EnrollmentPolicy) {
		policy = next;
		publicSignup = next.public_signup_enabled;
		signupButtonVisible = next.public_signup_button_visible;
		approvalMode = next.approval_mode;
		quotas = Object.fromEntries(Object.values(next.quota_fields).flat().map(key => [key, next.personal_quotas[key]?.toString() ?? '']));
	}

	async function loadPolicy() {
		const owner = capture();
		if (!owner || saving || policyLoading) return;
		const read = ++policyRead;
		policyLoading = true; policyError = ''; policyNotice = ''; policy = null;
		try {
			const result = await api.get<EnrollmentPolicy>(policyPath, owner.token, owner.projectId, readOptions);
			if (!owner.current() || read !== policyRead) return;
			applyPolicy(result); reloadRequired = false;
		} catch {
			if (owner.current() && read === policyRead) policyError = t('enrollment.loadFailed');
		} finally {
			if (owner.current() && read === policyRead) policyLoading = false;
		}
	}

	async function savePolicy(event: SubmitEvent) {
		event.preventDefault();
		const owner = capture();
		if (!owner || !policy || saving || policyLoading || reloadRequired) return;
		// Disabled-service entries are not editable, and an unrelated save must not erase them.
		const personalQuotas: Record<string, number> = { ...policy.personal_quotas };
		for (const key of Object.values(policy.quota_fields).flat()) {
			const value = (quotas[key] ?? '').trim();
			if (!value) { delete personalQuotas[key]; continue; }
			if (!/^(?:-1|\d+)$/.test(value) || !Number.isSafeInteger(Number(value))) {
				policyError = t(section === 'policy' ? 'enrollment.invalidQuotaOtherTab' : 'enrollment.invalidQuota'); return;
			}
			personalQuotas[key] = Number(value);
		}
		const body: EnrollmentPolicyWrite = { revision: policy.revision, public_signup_enabled: publicSignup,
			public_signup_button_visible: signupButtonVisible,
			approval_mode: approvalMode as EnrollmentPolicy['approval_mode'], personal_quotas: personalQuotas };
		saving = true; policyError = ''; policyNotice = '';
		try {
			const result = await api.put<EnrollmentPolicy>(policyPath, body, owner.token, owner.projectId, writeOptions);
			if (!owner.current()) return;
			applyPolicy(result); policyNotice = t('enrollment.saved');
		} catch (cause) {
			if (!owner.current()) return;
			reloadRequired = true;
			policyError = t(cause instanceof ApiError && cause.status === 409 ? 'enrollment.conflict' : 'enrollment.saveFailed');
		} finally {
			if (owner.current()) saving = false;
		}
	}

	async function loadQueue(nextCursor: string | null = null, nextHistory: Array<string | null> = []) {
		const owner = capture();
		if (!owner || decisionId) return;
		const read = ++queueRead;
		const selected = filter;
		queueLoading = true; queueError = ''; queueNotice = ''; page = null;
		const params = new URLSearchParams({ status: selected });
		if (nextCursor !== null) params.set('cursor', nextCursor);
		try {
			const result = await api.get<SignupRequestPage>(`${queuePath}?${params}`, owner.token, owner.projectId, readOptions);
			if (!owner.current() || read !== queueRead) return;
			page = result; cursor = nextCursor; history = nextHistory;
		} catch {
			if (owner.current() && read === queueRead) queueError = t('enrollment.queueFailed');
		} finally {
			if (owner.current() && read === queueRead) queueLoading = false;
		}
	}

	async function decide(request: SignupRequest, action: 'approve' | 'reject') {
		const owner = capture();
		if (!owner || !page || queueLoading || decisionId || request.status !== 'pending') return;
		decisionId = request.id; queueError = ''; queueNotice = '';
		try {
			const result = await api.post<SignupRequest>(`${queuePath}/${encodeURIComponent(request.id)}/${action}`, {}, owner.token, owner.projectId, writeOptions);
			if (!owner.current()) return;
			page = { ...page, items: page.items.map(item => item.id === request.id ? result : item)
				.filter(item => filter === 'all' || item.status === filter) };
			queueNotice = t('enrollment.decisionRecorded', { email: result.email, status: t(`enrollment.status.${result.status}`) });
		} catch (cause) {
			if (!owner.current()) return;
			page = null;
			queueError = t(cause instanceof ApiError && cause.status === 503
				&& cause.message === 'signup_approval_notification_failed; approval remains approved'
				? 'enrollment.notificationFailed' : 'enrollment.decisionFailed');
		} finally {
			if (owner.current()) decisionId = null;
		}
	}

	function serviceLabel(section: string) {
		return Object.prototype.hasOwnProperty.call(quotaFields, section) ? tq(`service.${section as keyof typeof quotaFields}`) : t('enrollment.serviceKey', { key: section });
	}
	function fieldLabel(field: string) {
		return knownFields.has(field) ? tq(`field.${field as QuotaField}`) : t('enrollment.quotaKey', { key: field });
	}
</script>

<section aria-label={t('enrollment.title')} data-testid="admin-enrollment-policy">
	<div hidden={section === 'requests'}>
	<Card padding="lg">
		<div class="panel-header">
			<div><h2>{t(section === 'quotas' ? 'enrollment.quotas' : 'enrollment.title')}</h2><p>{t('enrollment.summary')}</p></div>
			<Button variant="subtle" onclick={loadPolicy} disabled={!authorized || policyLoading || saving}>{t('enrollment.reloadPolicy')}</Button>
		</div>
		{#if policyError}<Alert tone="danger">{policyError}</Alert>{/if}
		{#if policyNotice}<Alert tone="success">{policyNotice}</Alert>{/if}
		{#if policyLoading}<LoadingState variant="section" label={t('enrollment.loading')} />{/if}
		{#if policy && authorized}
			<form onsubmit={savePolicy} aria-label={t('enrollment.policyForm')}>
				<p>{t('enrollment.futureOnly')}</p>
				<Alert tone={policy.smtp_configured ? 'info' : 'warning'}>{t(policy.smtp_configured ? 'enrollment.smtpReady' : 'enrollment.smtpMissing')}</Alert>
				<fieldset disabled={saving || reloadRequired || policyLoading}>
					<div class="controls" hidden={section === 'quotas'}>
						<label class="toggle"><input id={`${uid}-public-email`} type="checkbox" bind:checked={publicSignup} />{t('enrollment.publicEmail')}</label>
						<p>{t('enrollment.emailHelp')}</p>
						<label class="toggle"><input id={`${uid}-signup-visible`} type="checkbox" bind:checked={signupButtonVisible} aria-describedby={`${uid}-signup-visible-help`} />{t('enrollment.signupButtonVisible')}</label>
						<p id={`${uid}-signup-visible-help`}>{t('enrollment.signupButtonHelp')}</p>
						<Field label={t('enrollment.approvalMode')} for={`${uid}-approval-mode`} help={t('enrollment.approvalHelp')}>
							<SelectInput id={`${uid}-approval-mode`} bind:value={approvalMode}>
								<option value="auto">{t('enrollment.mode.auto')}</option><option value="admin">{t('enrollment.mode.admin')}</option>
							</SelectInput>
						</Field>
					</div>
					<div class="quota-task" hidden={section === 'policy'}>
					<h3>{t('enrollment.quotas')}</h3><p id={`${uid}-quota-help`}>{t('enrollment.quotaHelp')}</p>
					<Button variant="secondary" disabled={!policy.source_default_personal_quotas} onclick={() => {
						if (!policy?.source_default_personal_quotas) return;
						quotas = { ...quotas, ...Object.fromEntries(Object.entries(policy.source_default_personal_quotas).map(([key, value]) => [key, String(value)])) };
					}}>{t('enrollment.useSourceDefaults')}</Button>
					<div class="quota-sections">
						{#each Object.entries(policy.quota_fields) as [section, fields] (section)}
							<fieldset aria-label={serviceLabel(section)}><legend>{serviceLabel(section)}</legend>
								<div class="quota-grid">{#each fields as field (field)}
									<Field label={fieldLabel(field)} for={`${uid}-quota-${field}`}>
										<TextInput id={`${uid}-quota-${field}`} bind:value={quotas[field]} inputmode="numeric" placeholder={t('enrollment.nativeDefault')} ariaDescribedBy={`${uid}-quota-help`} />
									</Field>
								{/each}</div>
							</fieldset>
						{/each}
					</div>
					</div>
					<Button type="submit" variant="primary" disabled={saving || reloadRequired} ariaBusy={saving}>{#if saving}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{t(saving ? 'enrollment.saving' : 'enrollment.save')}</Button>
				</fieldset>
			</form>
		{:else if !policyLoading && !policyError}<p>{t('enrollment.authorityRequired')}</p>{/if}
		<div hidden={section === 'policy'}>
		{#if policy && authorized}
			{@const owner = capture()}
			{#key `${epoch}:${policy.revision}`}
				{#if owner}<PersonalQuotaConvergence token={owner.token} projectId={owner.projectId} current={owner.current} />{/if}
			{/key}
		{/if}
		</div>
	</Card>
	</div>

	<div hidden={section === 'policy' || section === 'quotas'}>
	<Card padding="lg">
		<section aria-label={t('enrollment.queue')}>
			<div class="panel-header"><div><h2>{t('enrollment.queue')}</h2><p>{t('enrollment.reviewHelp')}</p></div>
				<Button variant="subtle" onclick={() => loadQueue(null, [])} disabled={!authorized || queueLoading || decisionId !== null}>{t('enrollment.reloadQueue')}</Button>
			</div>
			<p>{t('enrollment.mailUnconfirmed')}</p>
			<fieldset disabled={!authorized || decisionId !== null} aria-label={t('enrollment.filter')}>
				<RegexSearch id={`${uid}-request-search`} bind:value={queueSearch} />
				<p>{tc('table.loadedScope')}</p>
				<TableViewControls view={queueView} class="" />
			</fieldset>
			{#if queueError}<Alert tone="danger">{queueError}</Alert>{/if}
			{#if queueNotice}<Alert tone="success">{queueNotice}</Alert>{/if}
			{#if queueLoading}<LoadingState variant="section" label={t('enrollment.queueLoading')} />{/if}
			{#if page && authorized}
				<p>{t('enrollment.loadedCount', { count: page.items.length })}</p>
				{#if page.items.length === 0}<p>{t('enrollment.empty')}</p>{/if}
				{#if page.items.length > 0 && queueView.rows.length === 0}<p>{tc('table.noMatches')}</p>{/if}
				<ul class="requests">
					{#each queueView.rows as request (request.id)}
						<li data-request-id={request.id}>
							<article aria-label={t('enrollment.requestLabel', { email: request.email, id: request.id })}>
								<h3>{request.email}</h3>
								<dl>
									<div><dt>{t('enrollment.requestId')}</dt><dd class="identifier">{request.id}</dd></div>
									<div><dt>{t('enrollment.status')}</dt><dd>{t(`enrollment.status.${request.status}`)}</dd></div>
									<div><dt>{t('enrollment.source')}</dt><dd>{t(`enrollment.source.${request.source}`)}</dd></div>
									<div><dt>{t('enrollment.domain')}</dt><dd class="identifier">{request.domain_id ?? t('enrollment.notProvided')}</dd></div>
									<div><dt>{t('enrollment.provider')}</dt><dd class="identifier">{request.provider_id ?? t('enrollment.notProvided')}</dd></div>
									<div><dt>{t('enrollment.created')}</dt><dd><time datetime={request.created_at}>{request.created_at}</time></dd></div>
									<div><dt>{t('enrollment.reviewed')}</dt><dd>{#if request.reviewed_at}<time datetime={request.reviewed_at}>{request.reviewed_at}</time>{:else}{t('enrollment.notReviewed')}{/if}</dd></div>
									<div><dt>{t('enrollment.reviewer')}</dt><dd class="identifier">{request.reviewed_by_user_id ?? t('enrollment.notProvided')}</dd></div>
								</dl>
								{#if request.status === 'pending'}
									<div class="actions">
										<Button variant="secondary" onclick={() => decide(request, 'approve')} disabled={decisionId !== null} ariaBusy={decisionId === request.id}>{t('enrollment.approve')}</Button>
										<Button variant="danger-outline" onclick={() => decide(request, 'reject')} disabled={decisionId !== null}>{t('enrollment.reject')}</Button>
									</div>
								{/if}
							</article>
						</li>
					{/each}
				</ul>
				<nav class="actions" aria-label={t('enrollment.pagination')}>
					<Button variant="subtle" disabled={!history.length || decisionId !== null} onclick={() => loadQueue(history.at(-1) ?? null, history.slice(0, -1))}>{t('enrollment.previous')}</Button>
					<Button variant="subtle" disabled={page.next_cursor === null || decisionId !== null} onclick={() => { if (page?.next_cursor != null) void loadQueue(page.next_cursor, [...history, cursor]); }}>{t('enrollment.next')}</Button>
				</nav>
			{/if}
		</section>
	</Card>
	</div>
</section>

<style>
	section, form, .quota-sections, .controls { display: grid; gap: 1rem; min-width: 0; }
	[hidden] { display: none !important; }
	.quota-task { display: grid; gap: 1rem; min-width: 0; }
	.panel-header, .actions { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 0.75rem; }
	.panel-header > div { flex: 1 1 20rem; min-width: 0; }
	h2 { margin: 0; color: var(--color-ink-0); font-size: 1rem; font-weight: 600; }
	h3, legend { margin: 0; color: var(--color-ink-1); font-size: 0.875rem; font-weight: 600; }
	p { margin: 0; color: var(--color-ink-2); font-size: 0.875rem; line-height: 1.6; }
	fieldset { border: 0; padding: 0; margin: 0; min-width: 0; display: grid; gap: 1rem; }
	legend { margin-bottom: 0.75rem; }
	.quota-grid, dl { display: grid; gap: 0.75rem; grid-template-columns: minmax(0, 1fr); }
	.toggle { display: flex; align-items: center; gap: 0.75rem; min-height: 44px; color: var(--color-ink-1); font-size: 0.875rem; }
	.requests { list-style: none; padding: 0; margin: 0; display: grid; gap: 1rem; }
	li { border: 1px solid var(--color-line); border-radius: var(--radius-lg); padding: 1rem; min-width: 0; }
	article { display: grid; gap: 1rem; }
	dl { margin: 0; }
	dt { color: var(--color-ink-2); font-size: 0.75rem; }
	dd { margin: 0.25rem 0 0; color: var(--color-ink-1); font-size: 0.8125rem; font-variant-numeric: tabular-nums; }
	.identifier { font-family: var(--font-mono); }
	h3, dd { overflow-wrap: anywhere; }
	.actions { justify-content: flex-start; }
	.actions :global(button) { min-height: 44px; }
	@media (min-width: 768px) { .quota-grid, dl { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
	@media (min-width: 1024px) { .quota-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
</style>
