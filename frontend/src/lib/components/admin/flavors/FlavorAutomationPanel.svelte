<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { ApiError } from '$lib/api/client';
	import { flavorAutomation, type FlavorAutomationStatus } from '$lib/api/flavorAutomation';
	import { t } from '$lib/i18n/ns/compute-pools';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { Alert, Button, Card } from '$lib/components/ui';
	import FlavorAutomationPolicyPanel from './FlavorAutomationPolicyPanel.svelte';
	let { onChanged }: { onChanged?: () => void } = $props();
	let data = $state<FlavorAutomationStatus | null>(null);
	const ready = $derived(data?.readiness?.verified === true);
	let loading = $state(false), busy = $state(false), reloadRequired = $state(false), enabled = $state(false);
	let error = $state(''), outcome = $state(''), epoch = $state(0), refresh = $state(0);
	let generation = 0, live = true, ownerKey = '';
	function allowed() { const state = get(auth); return live && !!state.token && state.isSystemAdmin === true && get(authReady) && !get(projectSwitching) && !get(logoutInProgress); }
	const sync = () => {
		const state = get(auth), next = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, !!state.token, get(authReady), get(projectSwitching), get(logoutInProgress)]);
		if (next === ownerKey) return;
		ownerKey = next; ++epoch; ++generation; data = null; error = ''; outcome = ''; loading = false; busy = false; reloadRequired = false;
	};
	const subscriptions = [auth.subscribe(sync), authReady.subscribe(sync), projectSwitching.subscribe(sync), logoutInProgress.subscribe(sync)];
	onDestroy(() => { live = false; ++generation; subscriptions.forEach(stop => stop()); });
	function capture() {
		const pending = generation, revision = epoch;
		const current = () => allowed() && pending === generation && revision === epoch;
		return { current, client: flavorAutomation({ token: () => get(auth).token ?? '', projectId: () => get(auth).projectId ?? undefined, isCurrent: current, canSubmit: current }) };
	}
	function accept(snapshot: FlavorAutomationStatus) { data = snapshot; enabled = snapshot.enabled; }
	function fail(cause: unknown) { error = cause instanceof ApiError && cause.status === 409 && /revision|conflict/.test(cause.message) ? t('conflict') : cause instanceof ApiError ? cause.message : t('loadFailed'); }
	async function load() {
		if (!allowed() || busy) return;
		++generation; const owner = capture(); loading = true; error = ''; outcome = ''; reloadRequired = false; data = null;
		try { const snapshot = await owner.client.load(); if (owner.current()) accept(snapshot); }
		catch (cause) { if (owner.current()) fail(cause); }
		finally { if (owner.current()) loading = false; }
	}
	async function mutate(reconcile = false) {
		if (!allowed() || loading || busy || reloadRequired || !data || (reconcile && (!data.enabled || data.status === 'running'))) return;
		if (!ready && (reconcile || enabled)) return;
		if (!reconcile && enabled === data.enabled) return;
		const owner = capture(), revision = data.revision; busy = true; error = ''; outcome = '';
		try {
			const snapshot = reconcile ? await owner.client.reconcile() : await owner.client.save(revision, enabled);
			if (owner.current()) {
				accept(snapshot);
				outcome = reconcile ? (snapshot.status === 'complete' ? t('reconciled') : '') : t('saved');
				onChanged?.();
			}
		}
		catch (cause) { if (owner.current()) { fail(cause); outcome = cause instanceof ApiError && cause.status < 500 ? '' : t('unknownOutcome'); reloadRequired = true; } }
		finally { if (owner.current()) busy = false; }
	}
	function date(value: string | null) { if (!value) return t('never'); const time = Date.parse(value); return Number.isFinite(time) ? new Intl.DateTimeFormat(intlLocale(), { dateStyle: 'medium', timeStyle: 'medium' }).format(time) : t('unknown'); }
	$effect(() => { void epoch; void refresh; untrack(() => { if (allowed()) void load(); }); });
</script>

<Card surface="base" class="mb-6 min-w-0">
	<section class="space-y-4" aria-label={t('automationTitle')}>
		<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold">{t('automationTitle')}</h2><Button variant="secondary" disabled={!allowed() || loading || busy} onclick={() => refresh++}>{t('refresh')}</Button></div>
		<p class="text-sm text-ink-2">{t('automationHelp')}</p>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if outcome}<Alert tone={reloadRequired ? 'warning' : 'info'}>{outcome}</Alert>{/if}
		{#if reloadRequired}<Alert tone="warning">{t('reloadRequired')}</Alert>{/if}
		{#if loading}<LoadingState variant="section" label={t('loading')} />{/if}
		{#if data && allowed()}
			<dl class="grid grid-cols-1 gap-3 text-sm md:grid-cols-3"><div><dt class="text-ink-2">{t('status')}</dt><dd>{t(`automationStatus.${data.status}`)}</dd></div><div><dt class="text-ink-2">{t('lastRun')}</dt><dd class="break-words">{date(data.last_run)}</dd></div><div><dt class="text-ink-2">{t('revision', { revision: data.revision })}</dt><dd>{data.enabled ? t('enabled') : t('disabled')}</dd></div></dl>
			{#if data.error}<Alert tone="warning">{data.error}</Alert>{/if}
			{#if !ready}<Alert tone="warning" title={t('automationReadinessBlocked')}><p>{t('automationReadinessHelp')}</p><p class="mt-2 break-words text-xs">{data.readiness?.reason || t('unknown')}</p></Alert>{/if}
			<label class="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" bind:checked={enabled} disabled={busy || reloadRequired || (!ready && !data.enabled)} />{t('enableAutomation')}</label>
			<div class="flex flex-wrap gap-2"><Button variant="accent" disabled={busy || reloadRequired || enabled === data.enabled || (!ready && enabled)} onclick={() => mutate()}>{#if busy}<LoadingState variant="control" label="" aria-hidden="true" />{/if}{busy ? t('saving') : t('saveAutomation')}</Button><Button variant="secondary" disabled={busy || reloadRequired || !ready || !data.enabled || data.status === 'running'} onclick={() => mutate(true)}>{t('reconcile')}</Button></div>
			{#if data.diagnostics.length}<details><summary class="min-h-11 cursor-pointer py-3 text-sm text-ink-1">{t('diagnostics')}</summary><ul class="space-y-2 text-xs text-ink-2">{#each data.diagnostics as row}<li class="break-words"><code>{row.code}</code> · {row.message}</li>{/each}</ul></details>{/if}
			{#if data.items.length}<details><summary class="min-h-11 cursor-pointer py-3 text-sm text-ink-1">{t('report', { count: data.items.length })}</summary><ul class="divide-y divide-line">{#each data.items as row (row.id)}<li class="space-y-1 py-3 text-sm"><div class="flex flex-wrap justify-between gap-2"><strong class="break-all font-medium">{row.display_name ?? row.name}</strong><span>{t(`itemStatus.${row.status}`)}</span></div>{#if row.display_name}<p class="break-all text-xs text-ink-2">{row.name}</p>{/if}<code class="block break-all text-xs text-ink-2">{row.id}</code><p class="break-words text-xs text-ink-2">{row.vcpus} vCPU · {row.ram} MiB · GPU {row.gpu_count ?? t('unknown')} · {t('publishedProjects', { count: row.projects })}</p>{#if row.gpu_resource_class}<code class="block break-all text-xs text-ink-2">{row.gpu_resource_class}</code>{/if}{#if row.reason}<p class="break-words text-xs text-ink-2">{row.reason}</p>{/if}</li>{/each}</ul></details>{/if}
		{/if}
	</section>
</Card>

<FlavorAutomationPolicyPanel onChanged={() => { refresh++; onChanged?.(); }} />
