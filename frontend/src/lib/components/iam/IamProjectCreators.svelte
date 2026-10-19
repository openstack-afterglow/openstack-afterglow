<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import { domainIam, type IamSession, type IamUser } from '$lib/api/domainIam';
	import { projectAuthority } from '$lib/api/projectAuthority';
	import type { ProjectCreators } from '$lib/types/project';
	import { ApiError } from '$lib/api/client';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => projectAuthority(session));
	const directory = untrack(() => domainIam(session));
	const uid = $props.id();
	let live = true; let revision = 0;
	let creators = $state<ProjectCreators | null>(null);
	let users = $state<IamUser[]>([]);
	let selected = $state('');
	let loading = $state(true); let busy = $state(false); let needsRefresh = $state(false); let error = $state('');
	const current = () => live && session.isCurrent();
	function fail(cause: unknown) {
		if (!current()) return;
		error = cause instanceof Error ? cause.message : t('loadFailed');
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	async function load() {
		if (!current() || busy) return;
		const pending = ++revision; loading = true; error = ''; creators = null;
		try {
			const [status, rows] = await Promise.all([client.creators(), directory.users()]);
			if (!current() || pending !== revision) return;
			if (status.domain_id !== session.domainId) throw new Error(t('domainMismatch'));
			creators = status; users = rows.items.filter(row => row.enabled); needsRefresh = false;
			if (!users.some(row => row.id === selected)) selected = '';
		} catch (cause) { if (pending === revision) fail(cause); }
		finally { if (current() && pending === revision) loading = false; }
	}
	function canChange(userId: string, enabled: boolean) {
		return current() && session.canSubmit() && !blocked && !loading && !busy && !needsRefresh && !!creators?.role
			&& (enabled ? users.some(row => row.id === userId) && !creators.users.some(row => row.id === userId && row.direct)
				: creators.users.some(row => row.id === userId && row.direct));
	}
	async function change(userId: string, enabled: boolean) {
		if (!canChange(userId, enabled)) return;
		const pending = revision;
		const name = users.find(row => row.id === userId)?.name || creators?.users.find(row => row.id === userId)?.name || userId;
		const approved = await confirmDialog(t(enabled ? 'grantCreatorConfirm' : 'revokeCreatorConfirm', { user: name }), { confirmLabel: t(enabled ? 'grantCreator' : 'revokeCreator') });
		if (!approved || pending !== revision || (enabled && selected !== userId) || !canChange(userId, enabled)) return;
		busy = true; error = '';
		try {
			const result = await client.setCreator(userId, enabled);
			if (current() && pending === revision) { creators = result; selected = ''; }
		} catch (cause) { if (current() && pending === revision) { needsRefresh = true; fail(cause); } }
		finally { if (current() && pending === revision) busy = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; revision++; creators = null; users = []; });
</script>

<section class="space-y-3 rounded-lg border border-line p-4" aria-label={t('projectCreators')}>
	<div class="flex flex-wrap items-center justify-between gap-3"><h3 class="text-sm font-semibold text-ink-0">{t('projectCreators')}</h3><Button variant="secondary" size="sm" disabled={loading || busy} onclick={load}>{t('refresh')}</Button></div>
	<p class="text-sm text-ink-2">{t('projectCreatorsHelp')}</p>
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if needsRefresh}<Alert tone="warning">{t('mutationUncertain')}</Alert>{/if}
	{#if creators}
		{#if !creators.role}<Alert tone="warning">{t('creatorPresetMissing')}</Alert>{:else}
			<div class="grid items-end gap-3 md:grid-cols-2"><Field label={t('user')} for={`${uid}-creator`} help={t('eligibleUsersHelp')}><SelectInput id={`${uid}-creator`} bind:value={selected} disabled={busy || loading}><option value="">{t('selectUser')}</option>{#each users.filter(row => !creators?.users.some(creator => creator.id === row.id && creator.direct)) as row (row.id)}<option value={row.id}>{row.name} · {row.email || row.id}</option>{/each}</SelectInput></Field><div><Button variant="secondary" disabled={!canChange(selected, true)} onclick={() => change(selected, true)}>{t('grantCreator')}</Button></div></div>
		{/if}
		<ul class="space-y-2">{#each creators.users as row (row.id)}<li class="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"><span class="text-sm text-ink-1 [overflow-wrap:anywhere]">{row.name || row.id} · {t(row.source)}{#if row.direct && row.source !== 'direct'} · {t('direct')}{/if}</span><Button variant="danger-outline" size="sm" disabled={!canChange(row.id, false)} onclick={() => change(row.id, false)}>{t('revokeCreator')}</Button></li>{/each}</ul>
		{#if creators.role && !creators.users.length}<p class="text-sm text-ink-2">{t('emptyCreators')}</p>{/if}
	{/if}
</section>
