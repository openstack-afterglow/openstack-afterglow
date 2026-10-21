<script lang="ts">
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession, type IamInvitation, type IamAssignableRoles } from '$lib/api/domainIam';
	import type { Project, ProjectAccessMember } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { iamErrorMessage } from './iamError';
	import { enrollmentStatusLabel } from './enrollmentStatus';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import ProjectMemberRolesModal from '$lib/components/account/ProjectMemberRolesModal.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => domainIam(session));
	const uid = $props.id();
	let live = true;
	let roleRequest = 0;
	let projects = $state<Project[]>([]);
	let rows = $state<IamInvitation[]>([]);
	let project = $state('');
	let email = $state('');
	let roleIds = $state<string[]>([]);
	let catalog = $state<IamAssignableRoles | null>(null);
	let chooseRoles = $state(false);
	let loading = $state(true);
	let rolesLoading = $state(false);
	let busy = $state(false);
	let error = $state('');
	let notice = $state('');
	const member = $derived<ProjectAccessMember>({ user_id: '', username: email || t('invite'), email, is_owner: false, is_manager: false, source: 'direct', roles: [], direct_role_ids: roleIds, effective_role_ids: roleIds, external_role_ids: [] });
	function fail(cause: unknown) { if (!live) return; error = iamErrorMessage(cause, t('saveFailed')); if (cause instanceof ApiError && cause.status === 403) onDenied(); }
	async function roles() {
		const request = ++roleRequest; const target = project;
		catalog = null; roleIds = []; chooseRoles = false; rolesLoading = true;
		if (!target) { rolesLoading = false; return; }
		try { const result = await client.roles(target); if (live && request === roleRequest) catalog = result; }
		catch (cause) { if (request === roleRequest) fail(cause); }
		finally { if (live && request === roleRequest) rolesLoading = false; }
	}
	async function load() {
		loading = true; error = '';
		try {
			const [p, invitations] = await Promise.all([client.projects(), client.invitations()]);
			if (live) { projects = p.items; rows = invitations.items; if (!projects.some(row => row.id === project)) { project = ''; await roles(); } }
		} catch (cause) { fail(cause); }
		finally { if (live) loading = false; }
	}
	async function send(event: SubmitEvent) {
		event.preventDefault();
		if (!live || !session.canSubmit() || blocked || busy || loading || rolesLoading || (project && (!catalog || !roleIds.length)) || !email.trim()) return;
		busy = true; error = ''; notice = '';
		try { await client.invite(email.trim(), project || undefined, project ? [...roleIds] : []); if (live) { email = ''; roleIds = []; notice = t('inviteSent'); await load(); } }
		catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	async function revoke(row: IamInvitation) {
		if (!live || blocked || busy || loading || !(row.status === 'pending' || row.recovery_required)) return;
		if (!await confirmDialog(t('revokeConfirm', { email: row.email }), { confirmLabel: t('revoke') })) return;
		if (!live || blocked || busy || loading || !rows.includes(row) || !(row.status === 'pending' || row.recovery_required)) return;
		busy = true; error = '';
		try { await client.revoke(row.id); if (live) await load(); }
		catch (cause) { fail(cause); }
		finally { if (live) busy = false; }
	}
	function date(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString(intlLocale()); }
	onMount(() => { void load(); });
	onDestroy(() => { live = false; roleRequest++; email = ''; rows = []; });
</script>

<div class="space-y-4">
	<Alert tone="info">{t('inviteHelp')}</Alert>
	{#if error}<Alert tone="danger">{error}</Alert>{/if}
	{#if notice}<Alert tone="success">{notice}</Alert>{/if}
	{#if loading || rolesLoading}<ActivityIndicator label={t('loading')} />{/if}
	<Card><form class="space-y-4" onsubmit={send}>
		<div class="grid gap-4 md:grid-cols-2">
			<Field label={t('email')} required for={`${uid}-email`}><TextInput id={`${uid}-email`} type="email" bind:value={email} required disabled={busy || loading} autocomplete="off" /></Field>
			<Field label={t('optionalProject')} help={t('defaultMembership')} for={`${uid}-project`}><SelectInput id={`${uid}-project`} bind:value={project} disabled={blocked || busy || loading} onchange={() => { error = ''; void roles(); }}><option value="">{t('defaultMembership')}</option>{#each projects as row (row.id)}<option value={row.id}>{row.name}</option>{/each}</SelectInput></Field>
		</div>
		<div class="flex flex-wrap items-center gap-3">{#if project}<Button type="button" variant="secondary" disabled={blocked || busy || loading || rolesLoading || !catalog} onclick={() => chooseRoles = true}>{t('selectRoles')}</Button><span class="text-sm text-ink-2">{t('roleCount', { count: roleIds.length })}</span>{/if}<Button type="submit" variant="primary" disabled={blocked || busy || loading || rolesLoading || (!!project && (!catalog || !roleIds.length))}>{t('sendInvite')}</Button></div>
	</form></Card>
	<div><Button variant="secondary" disabled={busy || loading} onclick={load}>{t('refresh')}</Button></div>
	<ResponsiveTable>
		{#snippet cards()}
			{#each rows as row (row.id)}<CompactResourceCard>
				<h3 class="text-sm font-medium break-all">{row.email}</h3><p class="text-xs">{enrollmentStatusLabel(row.status)}</p><p class="text-sm">{row.project_name || row.project_id || t('defaultMembership')}</p>
				{#snippet details()}<p class="text-xs">{t('expires')}: {date(row.expires_at)}</p>{/snippet}
				{#snippet actions()}<Button variant="danger-outline" size="sm" disabled={blocked || busy || loading || !(row.status === 'pending' || row.recovery_required)} onclick={() => revoke(row)}>{t('revoke')}</Button>{/snippet}
			</CompactResourceCard>{/each}
			{#if !loading && !error && !rows.length}<p class="text-sm text-ink-2">{t('emptyInvites')}</p>{/if}
		{/snippet}
	<TableShell><table><thead><tr><th>{t('email')}</th><th>{t('project')}</th><th>{t('status')}</th><th>{t('expires')}</th><th>{t('actions')}</th></tr></thead>
		<tbody>{#each rows as row (row.id)}<tr><td>{row.email}</td><td>{row.project_name || row.project_id || t('defaultMembership')}</td><td>{enrollmentStatusLabel(row.status)}</td><td>{date(row.expires_at)}</td><td><Button variant="danger-outline" size="sm" disabled={blocked || busy || loading || !(row.status === 'pending' || row.recovery_required)} onclick={() => revoke(row)}>{t('revoke')}</Button></td></tr>{/each}{#if !loading && !error && !rows.length}<tr><td colspan="5">{t('emptyInvites')}</td></tr>{/if}</tbody>
	</table></TableShell>
	</ResponsiveTable>
</div>
{#if chooseRoles && catalog}<ProjectMemberRolesModal {member} roles={catalog.roles} busy={false} error="" onSave={(ids) => { roleIds = ids; chooseRoles = false; }} onClose={() => chooseRoles = false} />{/if}
