<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { ApiError } from '$lib/api/client';
	import type { IamSession } from '$lib/api/domainIam';
	import { computePools, computePoolLimit, type ComputePool } from '$lib/api/computePools';
	import { gpuQuotaRequests, type GpuQuotaRequest, type GpuQuotaRequestFilter } from '$lib/api/gpuQuotaRequests';
	import { t } from '$lib/i18n/ns/gpu-quota-requests';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { Alert, Button, Card, Field, TextInput, TextareaInput, SelectInput, Pill } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';

	let { adminMode = false, session, blocked = false, onDenied, onSelectDomain }: { adminMode?: boolean; session?: IamSession; blocked?: boolean; onDenied?: () => void; onSelectDomain?: (domainId: string) => void } = $props();
	const uid = $props.id();
	let rows = $state<GpuQuotaRequest[]>([]), next = $state<string | null>(null);
	let pool = $state<ComputePool | null>(null);
	let status = $state<GpuQuotaRequestFilter>(untrack(() => adminMode ? 'pending' : 'all'));
	let project = $state(''), resource = $state(''), additional = $state('1'), reason = $state('');
	let notes = $state<Record<string, string>>({});
	let loading = $state(false), poolLoading = $state(false), loaded = $state(false), busy = $state(false), reloadRequired = $state(false), denied = $state(false);
	let error = $state(''), poolError = $state(''), outcome = $state(''), epoch = $state(0);
	let live = true, generation = 0, ownerKey = '';
	function reset() {
		++generation; rows = []; next = null; pool = null; notes = {}; project = ''; resource = ''; additional = '1'; reason = '';
		loading = false; poolLoading = false; loaded = false; busy = false; reloadRequired = false; denied = false; error = ''; poolError = ''; outcome = '';
	}
	const sync = () => {
		const state = get(auth);
		const key = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, !!state.token, get(authReady), get(projectSwitching), get(logoutInProgress)]);
		if (key !== ownerKey) { ownerKey = key; ++epoch; reset(); }
	};
	const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync), logoutInProgress.subscribe(sync)];
	onDestroy(() => { live = false; ++generation; subscriptions.forEach(stop => stop()); });
	function allowed(write = false) {
		void epoch;
		const state = get(auth);
		return live && !blocked && !denied && !!state.token && get(authReady) && !get(projectSwitching) && !get(logoutInProgress)
			&& (adminMode ? state.isSystemAdmin === true : !!session?.isCurrent() && (!write || session.canSubmit()));
	}
	function capture() {
		const pending = generation, revision = epoch, mode = adminMode, iam = session;
		const current = () => allowed() && pending === generation && revision === epoch && mode === adminMode && iam === session;
		const authority = { token: () => mode ? get(auth).token ?? '' : iam?.token() ?? '', projectId: () => mode ? get(auth).projectId ?? undefined : undefined, isCurrent: current, canSubmit: () => current() && allowed(true) };
		return { current, client: gpuQuotaRequests(mode, authority), pools: computePools(iam?.domainId ?? '', mode, authority) };
	}
	function fail(cause: unknown, mutation = false) {
		if (cause instanceof ApiError && cause.status === 403) { denied = true; rows = []; pool = null; onDenied?.(); }
		return cause instanceof ApiError && cause.status === 409 ? t('conflict') : mutation ? t('mutationFailed') : t('loadFailed');
	}
	function validRow(row: GpuQuotaRequest) {
		return typeof row.id === 'string' && !!row.id && typeof row.domain_id === 'string' && typeof row.project_id === 'string'
			&& ['pending', 'fulfilled', 'rejected'].includes(row.status) && (adminMode || row.domain_id === session?.domainId);
	}
	async function loadPool(owner: ReturnType<typeof capture>) {
		poolLoading = true; poolError = ''; pool = null;
		try {
			const snapshot = await owner.pools.load();
			if (!owner.current()) return;
			if (snapshot.domain_id !== session?.domainId || snapshot.control_scope !== 'afterglow') throw new Error('scope');
			pool = snapshot;
			if (!snapshot.projects.some(row => row.enabled && row.id === project)) project = '';
			if (!snapshot.gpu_profiles?.some(row => row.resource_class === resource)) resource = '';
		} catch (cause) { if (owner.current()) poolError = fail(cause); }
		finally { if (owner.current()) poolLoading = false; }
	}
	async function load(cursor?: string, preserveOutcome = false) {
		if (!allowed() || busy) return;
		++generation; const owner = capture();
		loading = true; loaded = false; error = ''; rows = []; next = null; notes = {};
		if (!preserveOutcome) outcome = '';
		if (!adminMode) void loadPool(owner);
		try {
			const page = await owner.client.list(status, cursor);
			if (!owner.current()) return;
			if (!Array.isArray(page.items) || page.items.length > 50 || !page.items.every(validRow) || (page.next_cursor !== null && typeof page.next_cursor !== 'string')) throw new Error('scope');
			notes = Object.fromEntries(page.items.map(row => [row.id, '']));
			rows = page.items; next = page.next_cursor; loaded = true; reloadRequired = false;
		} catch (cause) { if (owner.current()) error = fail(cause); }
		finally { if (owner.current()) loading = false; }
	}
	const readyPool = $derived(pool?.policy_ready === true && pool.control_scope === 'afterglow');
	const baseline = $derived(pool && project && resource ? pool.project_limits[project]?.[resource] ?? computePoolLimit(pool.limits, resource) : null);
	const amount = $derived(/^[1-9]\d*$/.test(additional) ? Number(additional) : NaN);
	const target = $derived(baseline === null || baseline === -1 ? null : baseline + amount);
	const valid = $derived(readyPool && pool?.projects.some(row => row.id === project && row.enabled) && pool?.gpu_profiles?.some(row => row.resource_class === resource) && baseline !== -1 && Number.isSafeInteger(amount) && amount <= 2_147_483_647 && target !== null && target <= 2_147_483_647 && reason.length <= 2000);
	const locked = $derived(blocked || busy || loading || reloadRequired || !loaded || !allowed(true));
	async function submit() {
		if (adminMode || !allowed(true) || locked || poolLoading || !valid) return;
		const body = { project_id: project, resource_class: resource, additional: amount, reason };
		const owner = capture(); busy = true; error = ''; outcome = '';
		try {
			const result = await owner.client.create(body);
			if (!owner.current()) return;
			if (!validRow(result) || result.project_id !== body.project_id || result.resource_class !== body.resource_class || result.additional !== body.additional) throw new Error('scope');
			reason = ''; outcome = t('submitted'); busy = false; status = 'all'; await load(undefined, true);
		} catch (cause) { if (owner.current()) { error = fail(cause, true); reloadRequired = true; outcome = cause instanceof ApiError && cause.status < 500 ? '' : t('unknownOutcome'); } }
		finally { if (owner.current()) busy = false; }
	}
	async function resolve(row: GpuQuotaRequest, decision: 'fulfilled' | 'rejected') {
		if (!adminMode || !allowed(true) || locked || row.status !== 'pending' || !rows.includes(row) || (notes[row.id] ?? '').length > 2000) return;
		const owner = capture(), note = notes[row.id] ?? '';
		busy = true; error = ''; outcome = '';
		try {
			const result = await owner.client.resolve(row.id, decision, note);
			if (!owner.current()) return;
			if (!validRow(result) || result.id !== row.id || result.domain_id !== row.domain_id || result.project_id !== row.project_id || result.resource_class !== row.resource_class || result.target_limit !== row.target_limit || result.status !== decision) throw new Error('scope');
			outcome = t('decided'); busy = false; await load(undefined, true);
		} catch (cause) { if (owner.current()) { error = fail(cause, true); reloadRequired = true; outcome = cause instanceof ApiError && cause.status < 500 ? '' : t('unknownOutcome'); } }
		finally { if (owner.current()) busy = false; }
	}
	function number(value: number) { return value === -1 ? t('unlimited') : new Intl.NumberFormat(intlLocale()).format(value); }
	function date(value: string) { const time = new Date(value); return Number.isNaN(time.getTime()) ? value : new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(time); }
	$effect(() => { void epoch; void adminMode; void session; void blocked; untrack(() => { reset(); if (allowed()) void load(); }); });
</script>

<Card class="mb-6 min-w-0">
	<section class="space-y-4" aria-label={t(adminMode ? 'queueTitle' : 'title')}>
		<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold text-ink-0">{t(adminMode ? 'queueTitle' : 'title')}</h2><Button variant="secondary" disabled={busy || loading || !allowed()} onclick={() => load()}>{t('reload')}</Button></div>
		<p class="text-sm text-ink-2">{t(adminMode ? 'manualHelp' : 'requestHelp')}</p>
		<p class="text-sm text-ink-2">{t('scopeHelp')}</p>
		<p class="text-sm text-ink-2">{t('privacyHelp')}</p>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if outcome}<Alert tone={reloadRequired ? 'warning' : 'info'}>{outcome}</Alert>{/if}
		{#if reloadRequired}<Alert tone="warning">{t('reloadRequired')}</Alert>{/if}
		{#if !adminMode && allowed()}
			{#if poolLoading}<LoadingState variant="section" label={t('poolLoading')}  />{:else if poolError}<Alert tone="warning">{poolError}</Alert>{:else if pool}
				{#if pool.state !== 'active' || !pool.enabled}<Alert tone="warning">{t('inactiveHelp')}</Alert>{/if}
				{#if !readyPool}<Alert tone="warning">{t('policyUnavailable')}</Alert>{/if}
				<form class="space-y-3" onsubmit={(event) => { event.preventDefault(); void submit(); }}>
					<div class="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2">
						<Field for={`${uid}-project`} label={t('project')}><SelectInput id={`${uid}-project`} bind:value={project} disabled={locked || !readyPool}><option value="">{t('chooseProject')}</option>{#each pool.projects.filter(row => row.enabled) as row (row.id)}<option value={row.id}>{row.name || row.id} · {row.id}</option>{/each}</SelectInput></Field>
						<Field for={`${uid}-gpu`} label={t('profile')}><SelectInput id={`${uid}-gpu`} bind:value={resource} disabled={locked || !readyPool}><option value="">{t('chooseProfile')}</option>{#each pool.gpu_profiles ?? [] as row (row.name)}<option value={row.resource_class}>{row.name} · {row.resource_class}</option>{/each}</SelectInput></Field>
					</div>
					{#if !pool.gpu_profiles?.length}<p class="text-sm text-ink-2">{t('noProfiles')}</p>{/if}
					{#if baseline !== null}<p class="break-words text-sm text-ink-2">{t('baseline', { limit: number(baseline) })} {t(pool.project_limits[project]?.[resource] === undefined ? 'inherited' : 'explicitCap')}</p>{/if}
					{#if baseline === -1}<Alert tone="info">{t('alreadyUnlimited')}</Alert>{/if}
					<Field for={`${uid}-additional`} label={t('additional')} help={t('additionalHelp')}><TextInput id={`${uid}-additional`} inputmode="numeric" bind:value={additional} disabled={locked || !readyPool} /></Field>
					{#if valid && target !== null}<p class="text-sm tabular-nums text-ink-1">{t('target', { limit: number(target) })}</p>{/if}
					<Field for={`${uid}-reason`} label={t('reason')} help={t('textLimit')} error={reason.length > 2000 ? t('tooLong') : ''}><TextareaInput id={`${uid}-reason`} rows={2} bind:value={reason} disabled={locked || !readyPool} ariaInvalid={reason.length > 2000} /></Field>
					<Button type="submit" variant="primary" disabled={locked || poolLoading || !valid}>{#if busy}<LoadingState variant="control" label={t('saving')} />{:else}{t('submit')}{/if}</Button>
				</form>
			{/if}
		{/if}
		<div class="border-t border-line pt-4"><Field for={`${uid}-status`} label={t('history')}><SelectInput id={`${uid}-status`} bind:value={status} disabled={busy || loading || !allowed()} onchange={() => load()}>{#each ['pending', 'fulfilled', 'rejected', 'all'] as filter}<option value={filter}>{t(filter as GpuQuotaRequestFilter)}</option>{/each}</SelectInput></Field></div>
		{#if loading}<LoadingState variant="section" label={t('loading')}  />{:else if loaded && allowed()}
			{#if !rows.length}<p class="text-sm text-ink-2">{t('empty')}</p>{:else}
				<ul class="divide-y divide-line">
					{#each rows as row (row.id)}
						<li class="min-w-0 space-y-3 py-4">
							<div class="flex flex-wrap items-center gap-2"><h3 class="min-w-0 break-all text-sm font-semibold text-ink-0">{row.gpu_profile_name}</h3><Pill tone={row.status === 'pending' ? 'warning' : row.status === 'fulfilled' ? 'success' : 'neutral'}>{t(row.status)}</Pill></div>
							<dl class="grid min-w-0 grid-cols-1 gap-2 text-sm md:grid-cols-2"><div><dt class="text-ink-2">{t('project')}</dt><dd class="break-all"><code>{row.project_id}</code></dd></div><div><dt class="text-ink-2">{t('domain')}</dt><dd class="break-all"><code>{row.domain_id}</code></dd></div><div><dt class="text-ink-2">{t('additional')}</dt><dd class="tabular-nums">{number(row.additional)}</dd></div><div><dt class="text-ink-2">{t('targetLabel')}</dt><dd class="tabular-nums">{number(row.baseline_limit)} → {number(row.target_limit)}</dd></div></dl>
							<details class="text-sm"><summary class="min-h-11 cursor-pointer py-2 text-ink-1">{t('details')}</summary><dl class="space-y-2 break-all text-ink-2"><div><dt>{t('requestId')}</dt><dd><code>{row.id}</code></dd></div><div><dt>{t('resourceClass')}</dt><dd><code>{row.resource_class}</code></dd></div><div><dt>{t('requester')}</dt><dd><code>{row.requester_id}</code></dd></div><div><dt>{t('created')}</dt><dd>{date(row.created_at)}</dd></div><div><dt>{t('revision')}</dt><dd>{number(row.pool_revision)}</dd></div>{#if row.reason}<div><dt>{t('reason')}</dt><dd class="whitespace-pre-wrap break-words">{row.reason}</dd></div>{/if}{#if row.reviewed_at}<div><dt>{t('reviewed')}</dt><dd>{date(row.reviewed_at)} · <code>{row.reviewer_id}</code></dd></div>{/if}{#if row.note}<div><dt>{t('note')}</dt><dd class="whitespace-pre-wrap break-words">{row.note}</dd></div>{/if}</dl></details>
							{#if adminMode}
								<Button variant="secondary" disabled={busy || !allowed()} onclick={() => { if (allowed()) onSelectDomain?.(row.domain_id); }}>{t('openDomain')}</Button>
								{#if row.status === 'pending'}<Field for={`${uid}-note-${row.id}`} label={t('note')} help={t('textLimit')} error={(notes[row.id] ?? '').length > 2000 ? t('tooLong') : ''}><TextareaInput id={`${uid}-note-${row.id}`} rows={2} bind:value={notes[row.id]} disabled={locked} /></Field><div class="flex flex-wrap gap-2"><Button variant="accent" disabled={locked || (notes[row.id] ?? '').length > 2000} onclick={() => resolve(row, 'fulfilled')}>{t('fulfill')}</Button><Button variant="secondary" disabled={locked || (notes[row.id] ?? '').length > 2000} onclick={() => resolve(row, 'rejected')}>{t('reject')}</Button></div>{/if}
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
			<div class="flex flex-wrap items-center gap-2"><p class="mr-auto text-xs text-ink-2">{t('pageBound')}</p>{#if next}<Button variant="secondary" disabled={busy || !allowed()} onclick={() => { if (next) void load(next); }}>{t('next')}</Button>{/if}</div>
		{/if}
	</section>
</Card>
