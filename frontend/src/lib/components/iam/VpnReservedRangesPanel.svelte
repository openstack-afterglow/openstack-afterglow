<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import type { IamSession } from '$lib/api/domainIam';
	import { ApiError } from '$lib/api/client';
	import { vpnReservedRanges, parseReservedRanges, type VpnReservedRanges } from '$lib/api/vpnReservedRanges';
	import { t } from '$lib/i18n/ns/vpn-reserved-ranges';
	import { Alert, Button, Card, Field, TextareaInput } from '$lib/components/ui';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	let { domainId, adminMode = false, session, blocked = false }: { domainId: string; adminMode?: boolean; session?: IamSession; blocked?: boolean } = $props();
	const uid = $props.id();
	let data = $state<VpnReservedRanges | null>(null);
	let draft = $state('');
	let loading = $state(false), busy = $state(false), reloadRequired = $state(false);
	let error = $state(''), outcome = $state('');
	let epoch = $state(0);
	let live = true, generation = 0, ownerKey = '';
	const reset = () => { ++generation; data = null; draft = ''; error = ''; outcome = ''; busy = false; reloadRequired = false; };
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
		return { current, client: vpnReservedRanges(target, mode, { token: () => mode ? get(auth).token ?? '' : iam?.token() ?? '', projectId: () => mode ? get(auth).projectId ?? undefined : undefined, isCurrent: current, canSubmit: () => current() && allowed(true) }) };
	}
	function accept(snapshot: VpnReservedRanges) {
		if (snapshot.domain_id !== domainId || !Array.isArray(snapshot.vpn_reserved_cidrs)) throw new Error(t('scopeMismatch'));
		data = snapshot; draft = snapshot.vpn_reserved_cidrs.join('\n');
	}
	function fail(cause: unknown) {
		error = cause instanceof ApiError && cause.code === 'revision_conflict' ? t('conflict')
			: cause instanceof ApiError && cause.code === 'vpn_reserved_ranges_invalid' ? t('invalid')
			: cause instanceof Error && cause.message ? cause.message : t('loadFailed');
	}
	async function load() {
		if (!allowed() || busy) return;
		++generation; const owner = capture(); loading = true; error = ''; outcome = ''; reloadRequired = false;
		try {
			const result = await owner.client.load();
			if (owner.current()) accept(result);
		} catch (cause) {
			if (owner.current()) { fail(cause); data = null; draft = ''; }
		} finally { if (owner.current()) loading = false; }
	}
	async function save() {
		if (!allowed(true) || loading || busy || reloadRequired || !data || tooMany) return;
		const owner = capture(), revision = data.revision, values = parsed;
		busy = true; error = ''; outcome = '';
		try {
			const snapshot = await owner.client.save(revision, values);
			if (owner.current()) { accept(snapshot); outcome = t('saved'); }
		} catch (cause) {
			if (!owner.current()) return;
			fail(cause);
			// A rejected request changed nothing; any other failure may have been applied.
			if (!(cause instanceof ApiError && cause.status < 500 && cause.code !== 'revision_conflict')) { reloadRequired = true; outcome = cause instanceof ApiError && cause.status < 500 ? '' : t('unknownOutcome'); }
		} finally { if (owner.current()) busy = false; }
	}
	const lifecycleKey = $derived(JSON.stringify([epoch, domainId, adminMode, blocked]));
	const activeSession = $derived(session);
	$effect(() => { void lifecycleKey; void activeSession; untrack(() => { reset(); loading = false; if (allowed()) void load(); }); });
	const parsed = $derived(parseReservedRanges(draft));
	const tooMany = $derived(!!data && parsed.length > data.max_ranges);
	const locked = $derived(blocked || loading || busy || reloadRequired || !allowed(true));
</script>

<Card surface="base" class="min-w-0">
	<section class="space-y-4" aria-label={t('title')}>
		<div class="flex flex-wrap items-center gap-2"><h2 class="mr-auto text-lg font-semibold text-ink-0">{t('title')}</h2><Button variant="secondary" disabled={blocked || loading || busy || !allowed()} onclick={load}>{t('refresh')}</Button></div>
		<p class="text-sm text-ink-2">{t('help')}</p>
		{#if error}<Alert tone="danger">{error}</Alert>{/if}
		{#if outcome}<Alert tone={reloadRequired ? 'warning' : 'success'}>{outcome}</Alert>{/if}
		{#if reloadRequired}<Alert tone="warning">{t('reloadRequired')}</Alert>{/if}
		{#if loading}<LoadingState variant={data ? 'inline' : 'section'} label={t('loading')} />{/if}
		{#if data && allowed()}
			<div class="flex flex-wrap gap-2 text-sm text-ink-2"><span>{data.configured ? t('configured') : t('defaultInUse', { ranges: data.default_vpn_reserved_cidrs.join(', ') })}</span><span>{t('revision', { revision: data.revision })}</span>{#if adminMode}<code class="break-all">{data.domain_id}</code>{/if}</div>
			<Alert tone="info">{t('existingHelp')}</Alert>
			<Field for={`${uid}-ranges`} label={t('ranges')} help={t('rangesHelp', { max: data.max_ranges })} error={tooMany ? t('tooMany', { max: data.max_ranges }) : ''}>
				<TextareaInput id={`${uid}-ranges`} rows={5} bind:value={draft} disabled={locked} ariaInvalid={tooMany} placeholder="10.8.0.0/24" />
			</Field>
			{#if parsed.length === 0}<Alert tone="warning">{t('emptyWarning')}</Alert>{/if}
			<Button variant="primary" disabled={locked || tooMany} onclick={save}>{#if busy}<LoadingState variant="control" label={t('saving')} />{:else}{t('save')}{/if}</Button>
		{/if}
	</section>
</Card>
