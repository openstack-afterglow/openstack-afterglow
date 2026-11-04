<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { authDisplayContext } from '$lib/stores/authDisplayContext';
	import { t } from '$lib/i18n/ns/usage-schedule';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { Alert, Button, Field, Pill } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import type { UsageExtensionPage, UsageExtensionPolicy, UsageExtensionRequest } from '$lib/types/instanceUsage';

	let scope = $state<'project' | 'domain'>(!get(auth).projectId && get(auth).isDomainManager ? 'domain' : 'project');
	let policy = $state<UsageExtensionPolicy | null>(null);
	let requests = $state<UsageExtensionRequest[] | null>(null);
	let nextCursor = $state<string | null>(null);
	let reviewRequired = $state(false);
	let loading = $state(false);
	let busy = $state(false);
	let confirmed = $state(false);
	let policyError = $state('');
	let requestsError = $state('');
	let mutationError = $state('');
	let notice = $state('');
	let generation = 0;
	let disposed = false;
	let abort: AbortController | null = null;
	const root = '/api/v1/instances';
	const context = $derived($authDisplayContext.key);

	function owner() {
		const state = get(auth);
		return { context: get(authDisplayContext).key, project: state.projectId ?? undefined, domain: state.domainId,
			token: state.token ?? undefined, manager: state.isDomainManager === true, scope, generation,
			ready: get(authReady) && !get(projectSwitching) };
	}
	function current(value: ReturnType<typeof owner>) {
		return !disposed && value.context === get(authDisplayContext).key && value.scope === scope && value.generation === generation;
	}
	function query(value: ReturnType<typeof owner>) {
		return value.scope === 'domain' ? `?domain_id=${encodeURIComponent(value.domain ?? '')}` : '';
	}
	function eligible(value: ReturnType<typeof owner>) {
		return value.ready && (value.scope === 'domain' ? value.manager && !!value.domain : !!value.project);
	}
	async function requestPage(value: ReturnType<typeof owner>, signal: AbortSignal, cursor: string | null = null) {
		const scopeQuery = query(value);
		const cursorQuery = cursor === null ? '' : `${scopeQuery ? '&' : '?'}cursor=${encodeURIComponent(cursor)}`;
		const result = await api.get<UsageExtensionPage>(`${root}/usage-extension-requests${scopeQuery}${cursorQuery}`,
			value.token, value.project, { signal, cache: 'no-store' });
		if (!current(value)) return null;
		if (!Array.isArray(result.items) || (result.next_cursor !== null && (typeof result.next_cursor !== 'string' || !result.next_cursor))
			|| (cursor !== null && result.next_cursor === cursor)
			|| result.items.some(row => !row.id || !row.revision || !row.instance_id
				|| (value.scope === 'domain' ? row.domain_id !== value.domain : row.project_id !== value.project))) throw new Error('Request scope mismatch');
		return result;
	}
	async function loadMore() {
		if (busy || loading || !confirmed || !requests || !nextCursor) return;
		generation += 1;
		const value = owner();
		if (!value.token || !eligible(value)) return;
		const cursor = nextCursor;
		abort?.abort(); abort = new AbortController(); loading = true; requestsError = '';
		try {
			const result = await requestPage(value, abort.signal, cursor);
			if (!result || !current(value)) return;
			// Live status transitions can move a row into a later page.
			const merged = new Map(requests.map(row => [row.id, row]));
			for (const row of result.items) merged.set(row.id, row);
			requests = [...merged.values()]; nextCursor = result.next_cursor;
		} catch (cause) {
			if (current(value)) requestsError = cause instanceof ApiError ? cause.message : t('requestsFailed');
		} finally { if (current(value)) loading = false; }
	}
	async function refresh() {
		if (busy) return;
		abort?.abort();
		generation += 1;
		const value = owner();
		confirmed = false; notice = ''; mutationError = ''; policyError = ''; requestsError = '';
		requests = null; nextCursor = null;
		if (!value.token || !eligible(value)) return;
		abort = new AbortController();
		const options = { signal: abort.signal, cache: 'no-store' as const };
		loading = true;
		await Promise.all([
			api.get<UsageExtensionPolicy>(`${root}/usage-extension-policy${query(value)}`, value.token, value.project, options)
				.then(result => {
					if (!current(value)) return;
					if (!result.domain_id || typeof result.review_required !== 'boolean' || typeof result.can_manage !== 'boolean' || !result.revision
						|| (value.scope === 'domain' && result.domain_id !== value.domain)) throw new Error('Policy scope mismatch');
					policy = result; reviewRequired = result.review_required;
				}).catch(cause => { if (current(value)) { policy = null; policyError = cause instanceof ApiError ? cause.message : t('policyFailed'); } }),
			requestPage(value, abort.signal)
				.then(result => {
					if (!result || !current(value)) return;
					requests = result.items; nextCursor = result.next_cursor;
				}).catch(cause => { if (current(value)) { requests = null; nextCursor = null; requestsError = cause instanceof ApiError ? cause.message : t('requestsFailed'); } }),
		]);
		if (current(value)) { loading = false; confirmed = true; }
	}
	async function savePolicy() {
		const value = owner();
		const previous = policy;
		if (!confirmed || busy || loading || !previous?.can_manage || !value.token || !eligible(value)) return;
		busy = true; mutationError = ''; notice = '';
		abort = new AbortController();
		try {
			const result = await api.put<UsageExtensionPolicy>(`${root}/usage-extension-policy${query(value)}`,
				{ review_required: reviewRequired, revision: previous.revision }, value.token, value.project,
				{ signal: abort.signal, replayOnUnauthorized: false });
			if (!current(value)) return;
			if (result.domain_id !== previous.domain_id || !result.revision || typeof result.can_manage !== 'boolean'
				|| typeof result.review_required !== 'boolean') throw new Error('Policy scope mismatch');
			policy = result; reviewRequired = result.review_required; notice = t('saved');
		} catch (cause) {
			if (current(value)) { confirmed = false; mutationError = cause instanceof ApiError ? cause.message : t('operationFailed'); }
		} finally { if (current(value)) busy = false; }
	}
	async function review(request: UsageExtensionRequest, decision: 'approve' | 'reject') {
		const value = owner();
		if (!confirmed || busy || loading || !value.token || !eligible(value) || !request.can_review || request.status !== 'pending'
			|| !requests?.some(row => row.id === request.id && row.revision === request.revision)) return;
		busy = true; mutationError = ''; notice = '';
		abort = new AbortController();
		try {
			const result = await api.post<UsageExtensionRequest>(`${root}/usage-extension-requests/${encodeURIComponent(request.id)}/review`,
				{ decision, revision: request.revision }, value.token, value.project,
				{ signal: abort.signal, replayOnUnauthorized: false });
			if (!current(value)) return;
			if (result.id !== request.id || result.project_id !== request.project_id || result.domain_id !== request.domain_id
				|| result.instance_id !== request.instance_id || !result.revision
				|| !['applying', 'approved', 'rejected', 'stale', 'uncertain'].includes(result.status)) throw new Error('Request scope mismatch');
			requests = requests!.map(row => row.id === result.id ? result : row);
			notice = ['approved', 'rejected'].includes(result.status) ? t('reviewSaved') : '';
		} catch (cause) {
			if (current(value)) { confirmed = false; mutationError = cause instanceof ApiError ? cause.message : t('operationFailed'); }
		} finally { if (current(value)) busy = false; }
	}
	function date(value: string) {
		return new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
	}
	$effect.pre(() => {
		void context; void scope;
		untrack(() => {
			generation += 1; abort?.abort(); policy = null; requests = null; loading = false; busy = false;
			confirmed = false; policyError = ''; requestsError = ''; mutationError = ''; notice = '';
			nextCursor = null;
			const state = get(auth);
			if (!state.isDomainManager && scope === 'domain') { scope = 'project'; return; }
			if (!state.projectId && state.isDomainManager && state.domainId && scope !== 'domain') { scope = 'domain'; return; }
			void refresh();
		});
	});
	onDestroy(() => { disposed = true; generation += 1; abort?.abort(); });
</script>

<section id="usage-extension-review" aria-labelledby="usage-extension-review-title" aria-busy={loading || busy}
	class="min-w-0 scroll-mt-4 space-y-4 rounded-lg border border-line bg-surface-base p-4 md:p-6 [overflow-wrap:anywhere]">
	<div class="flex min-w-0 flex-wrap items-start justify-between gap-3">
		<h2 id="usage-extension-review-title" class="text-[15px] font-semibold text-ink-0">{t('reviewTitle')}</h2>
		<Button variant="secondary" class="min-h-11 max-w-full whitespace-normal" disabled={busy || loading} onclick={() => void refresh()}>{t('refresh')}</Button>
	</div>
	{#if $auth.isDomainManager}
		<Field label={t('reviewScope')} for="usage-extension-scope">
			<select id="usage-extension-scope" bind:value={scope} disabled={busy} class="min-h-11 w-full rounded-md border border-line-2 bg-surface-sunken px-3 py-2 text-sm text-ink-0">
				<option value="project" disabled={!$auth.projectId}>{t('projectScope')}</option><option value="domain">{t('domainScope')}</option>
			</select>
		</Field>
	{/if}
	{#if loading}<LoadingState variant="inline" label={t('loading')} />{/if}
	{#if policyError}<Alert tone="danger">{policyError}</Alert>{/if}
	{#if requestsError}<Alert tone="danger">{requestsError}</Alert>{/if}
	{#if mutationError}<Alert tone="danger">{mutationError}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	{#if policy}
		<div class="space-y-3 border-b border-line pb-4">
			<h3 class="text-sm font-semibold text-ink-0">{t('policyTitle')}</h3>
			<p class="text-sm text-ink-2">{t(policy.review_required ? 'reviewRequired' : 'automatic')}</p>
			{#if policy.can_manage}
				<form class="space-y-3" aria-label={t('policyTitle')} onsubmit={(event) => { event.preventDefault(); void savePolicy(); }}>
					<Field label={t('policyTitle')} for="usage-extension-policy" help={t('policyHelp')}>
						<select id="usage-extension-policy" value={String(reviewRequired)} disabled={busy || loading || !confirmed}
							onchange={(event) => { reviewRequired = event.currentTarget.value === 'true'; }}
							class="min-h-11 w-full rounded-md border border-line-2 bg-surface-sunken px-3 py-2 text-sm text-ink-0">
							<option value="false">{t('automaticOption')}</option><option value="true">{t('reviewRequiredOption')}</option>
						</select>
					</Field>
					<Button type="submit" class="min-h-11 max-w-full whitespace-normal" disabled={busy || loading || !confirmed || reviewRequired === policy.review_required}>{t('policySave')}</Button>
				</form>
			{/if}
		</div>
	{/if}
	<p class="text-sm leading-relaxed text-ink-2">{t('pendingWarning')}</p>
	{#if requests?.length === 0}<p class="text-sm text-ink-2">{t('requestsEmpty')}</p>{/if}
	{#each requests ?? [] as request (request.id)}
		<article class="min-w-0 space-y-3 border-t border-line pt-4" aria-label={request.instance_name || request.instance_id}>
			<div class="flex flex-wrap items-start justify-between gap-2">
				<div class="min-w-0"><h3 class="break-words text-sm font-semibold text-ink-0">{request.instance_name || request.instance_id}</h3><p class="break-all text-xs text-ink-2">{request.instance_id}</p></div>
				<Pill tone={request.status === 'approved' ? 'success' : ['uncertain', 'stale'].includes(request.status) ? 'danger' : 'neutral'} class="max-w-full whitespace-normal">{t(`request.${request.status}`)}</Pill>
			</div>
			<dl class="grid min-w-0 gap-3 text-sm md:grid-cols-2">
				<div><dt class="text-ink-2">{t('requestProject')}</dt><dd class="break-all text-ink-0">{request.project_id}</dd></div>
				<div><dt class="text-ink-2">{t('requestedBy')}</dt><dd class="break-all text-ink-0">{request.requested_by}</dd></div>
				<div><dt class="text-ink-2">{t('requestedExpiry')}</dt><dd class="tabular-nums text-ink-0"><time datetime={request.expires_at}>{date(request.expires_at)}</time></dd></div>
				<div><dt class="text-ink-2">{t('requestReason')}</dt><dd class="whitespace-pre-wrap text-ink-0">{request.reason}</dd></div>
			</dl>
			{#if request.can_review && request.status === 'pending'}
				<div class="flex flex-wrap gap-2">
					<Button class="min-h-11 max-w-full whitespace-normal" disabled={busy || loading || !confirmed} onclick={() => void review(request, 'approve')}>{t('approve')}</Button>
					<Button variant="secondary" class="min-h-11 max-w-full whitespace-normal" disabled={busy || loading || !confirmed} onclick={() => void review(request, 'reject')}>{t('reject')}</Button>
				</div>
			{/if}
		</article>
	{/each}
	{#if nextCursor}
		<Button variant="secondary" class="min-h-11 max-w-full whitespace-normal" disabled={busy || loading || !confirmed}
			onclick={() => void loadMore()}>{t('loadMore')}</Button>
	{/if}
</section>
