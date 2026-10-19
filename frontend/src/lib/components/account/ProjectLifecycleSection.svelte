<script lang="ts">
	import { onMount, onDestroy, untrack } from 'svelte';
	import type { IamSession } from '$lib/api/domainIam';
	import { projectAuthority } from '$lib/api/projectAuthority';
	import type { Project, ProjectOwnership, EligibleProjectUser } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { ApiError } from '$lib/api/client';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import AdminProjectDeleteModal from '$lib/components/admin/projects/AdminProjectDeleteModal.svelte';
	import { get } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { continueAfterProjectDeletion } from '$lib/utils/projectDeletionContinuation';
	let { session, project, callerProject, blocked = false, onChanged, onDeleted, onDenied = () => {} }: {
		session: IamSession; project: Project; callerProject?: string; blocked?: boolean;
		onChanged: () => void; onDeleted: () => void; onDenied?: () => void;
	} = $props();
	const client = untrack(() => projectAuthority(session, callerProject));
	const uid = $props.id();
	let live = true;
	let revision = 0;
	let ownership = $state<ProjectOwnership | null>(null);
	let users = $state<EligibleProjectUser[]>([]);
	let target = $state('');
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let needsRefresh = $state(false);
	let deleting = $state(false);
	const pendingTransfer = $derived(ownership?.transfer_operation && ownership.transfer_operation.status !== 'completed' ? ownership.transfer_operation : null);
	const transferUsers = $derived(users.filter(row => row.id !== ownership?.owner_user_id && (!pendingTransfer || row.id === pendingTransfer.to_user_id)));
	const current = () => live && session.isCurrent();
	function fail(cause: unknown) {
		if (!current()) return;
		error = cause instanceof Error ? cause.message : t('loadFailed');
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	async function load() {
		if (!current() || busy) return;
		const pending = ++revision;
		loading = true; error = ''; ownership = null; users = [];
		try {
			const [status, eligible] = await Promise.all([client.ownership(project.id), client.eligibleUsers(project.id)]);
			if (!current() || pending !== revision) return;
			if (status.project_id !== project.id || (status.transfer_operation && (status.transfer_operation.project_id !== project.id || status.transfer_operation.domain_id !== session.domainId))) throw new Error(t('loadFailed'));
			ownership = status; users = eligible.filter(row => row.enabled); needsRefresh = false;
			if (!users.some(row => row.id === target && row.id !== status.owner_user_id)) target = '';
			if (status.transfer_operation?.status === 'settled') target = users.some(row => row.id === status.transfer_operation?.to_user_id) ? status.transfer_operation.to_user_id : '';
		} catch (cause) { if (pending === revision) fail(cause); }
		finally { if (current() && pending === revision) loading = false; }
	}
	function canTransfer() {
		return current() && session.canSubmit() && !blocked && !loading && !busy && !needsRefresh
			&& ownership?.can_transfer === true && !!target && target !== ownership.owner_user_id
			&& (!pendingTransfer || pendingTransfer.status === 'settled') && transferUsers.some(row => row.id === target && row.enabled);
	}
	async function transfer() {
		if (!canTransfer()) return;
		const pending = revision; const selected = target;
		const user = users.find(row => row.id === selected)!;
		const approved = await confirmDialog(t('transferConfirm', { project: project.name, user: user.name || user.id }), { confirmLabel: t('transferOwnership'), confirmVariant: 'primary' });
		if (!approved || revision !== pending || selected !== target || !canTransfer()) return;
		busy = true; error = '';
		try {
			const result = await client.transfer(project.id, selected);
			if (!current() || pending !== revision) return;
			ownership = result; target = ''; onChanged();
		} catch (cause) {
			if (pending === revision && current()) { needsRefresh = true; fail(cause); }
		} finally { if (current() && pending === revision) busy = false; }
	}
	function deleted() {
		deleting = false;
		if (!current()) return;
		const state = get(auth);
		if (state.projectId === project.id && state.domainId === session.domainId) void continueAfterProjectDeletion(project.id, session.domainId);
		else onDeleted();
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; revision++; ownership = null; users = []; deleting = false; });
</script>

<section class="space-y-3 rounded-lg border border-line p-4" aria-label={t('ownership')}>
	<div class="flex flex-wrap items-center justify-between gap-3"><h4 class="text-sm font-semibold text-ink-0">{t('ownership')}</h4><Button variant="secondary" size="sm" disabled={loading || busy} onclick={load}>{t('refresh')}</Button></div>
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if needsRefresh}<Alert tone="warning">{t('mutationUncertain')}</Alert>{/if}
	{#if ownership}
		<Alert tone={ownership.status === 'unique' ? 'info' : 'warning'}>{t(ownership.status === 'unique' ? 'ownershipUnique' : ownership.status === 'conflict' ? 'ownershipConflict' : 'ownershipMissing')}</Alert>
		{#if pendingTransfer}
			<Alert tone="warning">{t(pendingTransfer.status === 'settled' ? 'transferSettled' : 'transferUnresolved')}</Alert>
			<p class="text-xs text-ink-2 [overflow-wrap:anywhere]">{t('transferOperationDetails', { id: pendingTransfer.id, from: pendingTransfer.from_user_id, to: pendingTransfer.to_user_id, stage: pendingTransfer.stage })}</p>
		{/if}
		{#if ownership.owners.length}<ul class="space-y-1 text-sm text-ink-1">{#each ownership.owners as owner (`${owner.user_id}-${owner.source}`)}<li class="[overflow-wrap:anywhere]">{owner.name || owner.user_id} · <code>{owner.user_id}</code> · {t(owner.source === 'direct' ? 'direct' : 'groupOrInherited')}</li>{/each}</ul>{/if}
		{#if ownership.can_transfer}
			<div class="grid items-end gap-3 md:grid-cols-2"><Field label={t('newOwner')} for={`${uid}-owner`} help={t('eligibleUsersHelp')}><SelectInput id={`${uid}-owner`} bind:value={target} disabled={busy || loading}><option value="">{t('selectUser')}</option>{#each transferUsers as row (row.id)}<option value={row.id}>{row.name} · {row.email || row.id}</option>{/each}</SelectInput></Field><div><Button variant="secondary" disabled={!canTransfer()} ariaBusy={busy} onclick={transfer}>{t('transferOwnership')}</Button></div></div>
		{/if}
		<p class="text-xs text-ink-2">{t('safeDeleteHelp')}</p>
		{#if $auth.projectId === project.id && $auth.domainId === session.domainId}<p class="text-xs text-ink-2">{t('activeDeletionHelp')}</p>{/if}
		<Button variant="danger-outline" disabled={blocked || !session.canSubmit() || busy || loading || needsRefresh || !!pendingTransfer || !ownership.can_delete} onclick={() => { if (current() && session.canSubmit() && !blocked && !pendingTransfer && ownership?.can_delete) deleting = true; }}>{t('deleteProject')}</Button>
	{/if}
</section>
{#if deleting && current()}
	<AdminProjectDeleteModal {project} domainId={session.domainId} {session} onClose={() => { deleting = false; }} onSuccess={deleted} />
{/if}
