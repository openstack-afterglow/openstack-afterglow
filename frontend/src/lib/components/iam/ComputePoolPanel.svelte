<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import type { IamSession } from '$lib/api/domainIam';
	import { ApiError } from '$lib/api/client';
	import { computePools, computePoolLimit, parseComputeLimits, type ComputePool, type ComputeLimits } from '$lib/api/computePools';
	import { t } from '$lib/i18n/ns/compute-pools';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { Alert, Button, Card, Field, TextInput, SearchSelect } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	let { domainId, adminMode = false, session, blocked = false }: { domainId: string; adminMode?: boolean; session?: IamSession; blocked?: boolean } = $props();
	const uid = $props.id();
	let data = $state<ComputePool | null>(null);
	let loading = $state(false), busy = $state(false), reloadRequired = $state(false);
	let error = $state(''), outcome = $state(''), project = $state('');
	let enabled = $state(false);
	let poolDraft = $state<Record<string, string>>({}), capDraft = $state<Record<string, string>>({});
	let gpuNames = $state<Record<string, { name: string; display: string }>>({});
	let epoch = $state(0), refresh = $state(0);
	let live = true, generation = 0, ownerKey = '';
	const reset = () => { ++generation; data = null; error = ''; outcome = ''; project = ''; poolDraft = {}; capDraft = {}; gpuNames = {}; busy = false; reloadRequired = false; };
	const sync = () => {
		const state = get(auth);
		const next = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, !!state.token, get(authReady), get(projectSwitching), get(logoutInProgress)]);
		if (next !== ownerKey) { ownerKey = next; ++epoch; reset(); }
	};
	const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync), logoutInProgress.subscribe(sync)];
	onDestroy(() => { live = false; ++generation; subscriptions.forEach(stop => stop()); });
	function allowed(write = false) {
		const state = get(auth);
		return live && !blocked && !!state.token && get(authReady) && !get(projectSwitching) && !get(logoutInProgress) && (adminMode ? state.isSystemAdmin === true : !!session?.isCurrent() && (!write || session.canSubmit()));
	}
	function capture() {
		const pending = generation, revision = epoch, target = domainId, mode = adminMode, iam = session;
		const current = () => allowed() && pending === generation && revision === epoch && target === domainId && mode === adminMode && iam === session;
		return { current, client: computePools(target, mode, { token: () => mode ? get(auth).token ?? '' : iam?.token() ?? '', projectId: () => mode ? get(auth).projectId ?? undefined : undefined, isCurrent: current, canSubmit: () => current() && allowed(true) }) };
	}
	function accept(snapshot: ComputePool) {
		if (snapshot.domain_id !== domainId || !['unmanaged', 'active', 'paused'].includes(snapshot.state)) throw new Error(t('scopeMismatch'));
		data = snapshot; enabled = snapshot.enabled;
		gpuNames = Object.fromEntries((snapshot.gpu_profiles ?? []).map(row => [row.resource_class, { name: row.name, display: row.display_name && row.display_name !== row.name ? row.display_name : '' }]));
		poolDraft = Object.fromEntries(resources(snapshot).map(key => [key, snapshot.limits[key] == null ? '' : String(snapshot.limits[key])]));
		if (!snapshot.projects.some(row => row.id === project)) project = '';
		selectProject(project);
	}
	function label(key: string) { const gpu = gpuNames[key]; return key === 'CPU' ? t('cpu') : key === 'MEMORY_MB' ? t('ram') : gpu ? [gpu.name, gpu.display, key].filter(Boolean).join(' · ') : key; }
	function resources(snapshot: ComputePool) { return [...new Set(['CPU', 'MEMORY_MB', ...Object.keys(snapshot.limits), ...Object.keys(snapshot.usage), ...Object.keys(gpuNames), ...Object.values(snapshot.project_limits).flatMap(Object.keys)])].sort((a, b) => a === b ? 0 : a === 'CPU' ? -1 : b === 'CPU' ? 1 : a === 'MEMORY_MB' ? -1 : b === 'MEMORY_MB' ? 1 : a.localeCompare(b)); }
	function number(value: number | null | undefined) { return value == null ? t('unknown') : value === -1 ? t('unlimited') : new Intl.NumberFormat(intlLocale()).format(value); }
	function selectProject(id: string) { project = id; capDraft = data ? Object.fromEntries(resources(data).map(key => [key, data?.project_limits[id]?.[key] == null ? '' : String(data.project_limits[id][key])])) : {}; }
	async function load() {
		if (!allowed() || busy) return;
		++generation; const owner = capture(); loading = true; error = ''; outcome = ''; data = null; reloadRequired = false;
		try {
			const result = await owner.client.load();
			if (!owner.current()) return;
			accept(result);
		} catch (cause) { if (owner.current()) fail(cause); }
		finally { if (owner.current()) loading = false; }
	}
	function fail(cause: unknown) { error = cause instanceof ApiError && cause.status === 409 && /revision|conflict/.test(cause.message) ? t('conflict') : cause instanceof ApiError ? cause.message : t('loadFailed'); }
	async function save(kind: 'pool' | 'cap' | 'remove') {
		if (!allowed(true) || loading || busy || reloadRequired || !data?.policy_ready || data.control_scope !== 'afterglow' || (kind === 'pool' && !adminMode) || (kind !== 'pool' && (data.state === 'unmanaged' || !data.projects.some(row => row.id === project && (kind === 'remove' || row.enabled))))) return;
		const limits = kind === 'pool' ? parseComputeLimits(poolDraft) : parseComputeLimits(capDraft, data.limits);
		if (kind !== 'remove' && !limits) return;
		const owner = capture(), revision = data.revision, target = project;
		busy = true; error = ''; outcome = '';
		try {
			const snapshot = kind === 'pool' ? await owner.client.save(revision, enabled, limits as ComputeLimits) : kind === 'cap' ? await owner.client.saveProject(target, revision, limits as ComputeLimits) : await owner.client.removeProject(target, revision);
			if (!owner.current()) return;
			accept(snapshot); outcome = t('saved');
		} catch (cause) { if (owner.current()) { fail(cause); reloadRequired = true; outcome = cause instanceof ApiError && cause.status < 500 ? '' : t('unknownOutcome'); } }
		finally { if (owner.current()) busy = false; }
	}
	async function removeStaleCap(projectId: string) {
		if (!allowed(true) || loading || busy || reloadRequired || !data?.stale_project_caps?.includes(projectId) || data.control_scope !== 'afterglow') return;
		const owner = capture(), revision = data.revision;
		busy = true; error = ''; outcome = '';
		try {
			const snapshot = await owner.client.removeProject(projectId, revision);
			if (owner.current()) { accept(snapshot); outcome = t('saved'); }
		} catch (cause) {
			if (owner.current()) { fail(cause); reloadRequired = true; outcome = cause instanceof ApiError && cause.status < 500 ? '' : t('unknownOutcome'); }
		} finally { if (owner.current()) busy = false; }
	}
	$effect(() => { void epoch; void refresh; void domainId; void adminMode; void session; void blocked; untrack(() => { reset(); loading = false; if (allowed()) void load(); }); });
	const poolValues = $derived(parseComputeLimits(poolDraft));
	const capValues = $derived(data ? parseComputeLimits(capDraft, data.limits) : null);
	const locked = $derived(blocked || loading || busy || reloadRequired || !allowed(true) || !data?.policy_ready || data.control_scope !== 'afterglow');
</script>

<Card surface="base" class="min-w-0">
	<section class="space-y-4" aria-label={t('title')}>
		<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold text-ink-0">{t('title')}</h2><Button variant="secondary" disabled={blocked || loading || busy || !allowed()} onclick={() => refresh++}>{t('refresh')}</Button></div>
		<p class="text-sm text-ink-2">{t('help')}</p>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if outcome}<Alert tone={reloadRequired ? 'warning' : 'info'}>{outcome}</Alert>{/if}
		{#if reloadRequired}<Alert tone="warning">{t('reloadRequired')}</Alert>{/if}
		{#if loading}<LoadingState variant={data ? 'inline' : 'section'} label={t('loading')}  />{/if}
		{#if data && allowed()}
			<div class="flex flex-wrap gap-2 text-sm text-ink-2"><span>{t(`poolState.${data.state}`)}</span><span>{t('revision', { revision: data.revision })}</span><code class="break-all">{data.domain_id}</code></div>
			<Alert tone={data.policy_ready && data.control_scope === 'afterglow' ? 'info' : 'warning'}>{data.policy_ready && data.control_scope === 'afterglow' ? t('policyReady') : t('policyUnavailable')}<p class="mt-1 break-words">{t('scopeHelp')}</p></Alert>
			{#if data.state === 'paused'}<Alert tone="warning">{t('pauseHelp')}</Alert>{/if}
			{#if data.stale_project_caps?.length}
				<Alert tone="warning">{t('staleCapHelp')}</Alert>
				<ul class="divide-y divide-line">{#each data.stale_project_caps as id (id)}<li class="flex flex-wrap items-center justify-between gap-2 py-3"><code class="min-w-0 break-all text-xs text-ink-1">{id}</code><Button variant="secondary" disabled={blocked || loading || busy || reloadRequired || !allowed(true) || data.control_scope !== 'afterglow'} onclick={() => removeStaleCap(id)}>{t('verifyRemoveCap')}</Button></li>{/each}</ul>
			{/if}
			<div class="divide-y divide-line">
				{#each resources(data) as key (key)}
					<div class="grid min-w-0 grid-cols-1 gap-3 py-3 md:grid-cols-2">
						<div class="min-w-0"><h3 class="break-all text-sm font-medium text-ink-0">{gpuNames[key]?.name ?? label(key)}</h3>{#if gpuNames[key]}<p class="mt-1 break-all text-xs text-ink-2">{gpuNames[key].display ? `${gpuNames[key].display} · ` : ''}<code>{key}</code></p>{/if}<dl class="mt-2 grid grid-cols-3 gap-2 text-xs text-ink-2"><div class="min-w-0"><dt>{t('usage')}</dt><dd class="break-words tabular-nums text-ink-0">{number(data.usage[key])}</dd></div><div class="min-w-0"><dt>{t('limit')}</dt><dd class="break-words tabular-nums text-ink-0">{data.state === 'unmanaged' ? '—' : number(computePoolLimit(data.limits, key))}</dd></div><div class="min-w-0"><dt>{t('remaining')}</dt><dd class="break-words tabular-nums text-ink-0">{data.state === 'unmanaged' ? '—' : number(data.available[key])}</dd></div></dl></div>
						{#if adminMode}<Field for={`${uid}-pool-${key}`} label={t('poolLimit', { resource: label(key) })} help={t('limitHelp')} error={poolValues === null ? t('invalidLimit') : ''}><TextInput id={`${uid}-pool-${key}`} inputmode="numeric" bind:value={poolDraft[key]} disabled={locked} ariaInvalid={poolValues === null} /></Field>{/if}
					</div>
				{/each}
			</div>
			{#if adminMode}<label class="flex min-h-11 items-center gap-2 text-sm text-ink-1"><input type="checkbox" bind:checked={enabled} disabled={locked} />{t('enablePool')}</label><Alert tone="warning">{t('transitionHelp')}</Alert><p class="text-sm text-ink-2">{t('pauseHelp')}</p><Button variant="primary" disabled={locked || poolValues === null} onclick={() => save('pool')}>{#if busy}<LoadingState variant="control" label={t('saving')} />{:else}{t('savePool')}{/if}</Button>{/if}
			<div class="space-y-3 border-t border-line pt-4">
				<h3 class="text-sm font-semibold text-ink-0">{t('projectCaps')}</h3><p class="text-sm text-ink-2">{t('capHelp')}</p>
				<Field for={`${uid}-project`} label={t('project')}><SearchSelect id={`${uid}-project`} value={project} options={data.projects.map(row => ({ value: row.id, label: row.name || row.id, description: row.enabled ? row.id : `${row.id} · ${t('disabled')}` }))} disabled={blocked || loading || busy || reloadRequired || !allowed() || data.state === 'unmanaged'} placeholder={t('chooseProject')} ariaLabel={t('project')} onchange={selectProject} /></Field>
				{#if project}<code class="block break-all text-xs text-ink-2">{project}</code><div class="grid grid-cols-1 gap-3 md:grid-cols-2">{#each resources(data) as key (key)}<Field for={`${uid}-cap-${key}`} label={label(key)} help={t('capLimitHelp', { limit: number(computePoolLimit(data.limits, key)) })} error={capValues === null ? t('invalidCap') : ''}><TextInput id={`${uid}-cap-${key}`} bind:value={capDraft[key]} disabled={locked || data.state === 'unmanaged' || !data.projects.some(row => row.id === project && row.enabled)} inputmode="numeric" ariaInvalid={capValues === null} /></Field>{/each}</div><div class="flex flex-wrap gap-2"><Button variant="accent" disabled={locked || data.state === 'unmanaged' || capValues === null || !data.projects.some(row => row.id === project && row.enabled)} onclick={() => save('cap')}>{t('saveCap')}</Button><Button variant="secondary" disabled={locked || data.state === 'unmanaged' || !data.project_limits[project]} onclick={() => save('remove')}>{t('removeCap')}</Button></div>{/if}
			</div>
		{/if}
	</section>
</Card>
