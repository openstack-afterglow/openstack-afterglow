<script lang="ts">
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { createTableView } from '$lib/utils/tableView.svelte';
	import TableColumnHeader from '$lib/components/ui/TableColumnHeader.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession, type IamAssignableRoles } from '$lib/api/domainIam';
	import { projectAuthority } from '$lib/api/projectAuthority';
	import type { Project, ProjectAccessMember, EligibleProjectUser } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { iamErrorMessage } from './iamError';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import ProjectMemberRolesModal from '$lib/components/account/ProjectMemberRolesModal.svelte';

	let { session, project, blocked = false, onDenied }: { session: IamSession; project: Project; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => domainIam(session));
	const authority = untrack(() => projectAuthority(session));
	const uid = $props.id();
	let live = true;
	let revision = 0;
	let users = $state<EligibleProjectUser[]>([]);
	let user = $state('');
	let members = $state<ProjectAccessMember[]>([]);
	let catalog = $state<IamAssignableRoles | null>(null);
	let editing = $state<ProjectAccessMember | null>(null);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	const ownerCount = $derived(new Set(members.filter(member => member.is_owner).map(member => member.user_id)).size);

	function fail(cause: unknown) {
		if (!live || !session.isCurrent()) return;
		error = iamErrorMessage(cause, t('loadFailed'));
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	async function load() {
		const pending = ++revision;
		loading = true; error = ''; catalog = null; editing = null; members = []; users = []; user = '';
		try {
			const [rows, roles, eligible] = await Promise.all([client.members(project.id), client.roles(project.id), authority.eligibleUsers(project.id)]);
			if (live && session.isCurrent() && pending === revision) { members = rows.items; catalog = roles; users = eligible.filter(row => row.enabled); }
		} catch (cause) { if (pending === revision) fail(cause); }
		finally { if (live && pending === revision) loading = false; }
	}
	// Group/inherited grants stay read-only in the editor; adding direct roles matches assign().
	function editable(member: ProjectAccessMember) { return !loading && !!catalog && (catalog.can_manage_owners || !member.is_owner); }
	function removable(member: ProjectAccessMember) { return editable(member) && member.direct_role_ids.length > 0 && !member.is_owner && (!member.is_manager || catalog?.can_manage_owners); }
	function startEdit(member: ProjectAccessMember) {
		editing = { ...member, source: member.direct_role_ids.length ? member.source : 'mixed' };
		error = '';
	}
	function assign() {
		if (!live || !session.isCurrent() || blocked || !session.canSubmit() || busy || loading || !catalog || !user) return;
		const selected = users.find(row => row.id === user); if (!selected) return;
		const current = members.find(row => row.user_id === user);
		if (current?.is_owner && !catalog.can_manage_owners) return;
		editing = current ? { ...current, source: current.direct_role_ids.length ? current.source : 'mixed' } : { user_id: selected.id, username: selected.name, email: selected.email, is_owner: false, is_manager: false, source: 'direct', roles: [], direct_role_ids: [], direct_roles: [], effective_role_ids: [], external_role_ids: [] };
		error = '';
	}
	async function save(roleIds: string[]) {
		const member = editing; const pending = revision;
		if (!live || !session.canSubmit() || blocked || !member || busy || loading || !catalog || (member.is_owner && !catalog.can_manage_owners)) return;
		busy = true; error = '';
		try { await client.assignRoles(project.id, member.user_id, roleIds); if (live && session.isCurrent() && pending === revision) { editing = null; await load(); } }
		catch (cause) { if (pending === revision) fail(cause); }
		finally { if (live) busy = false; }
	}
	async function remove(member: ProjectAccessMember) {
		const pending = revision;
		if (!live || !session.canSubmit() || blocked || busy || !removable(member)) return;
		const approved = await confirmDialog(t('removeConfirm', { user: member.username || member.user_id }), { confirmLabel: t('removeMember') });
		if (!approved || !live || !session.canSubmit() || blocked || revision !== pending || busy || !removable(member) || !members.includes(member)) return;
		busy = true; error = '';
		try { await client.removeMember(project.id, member.user_id); if (live && revision === pending) await load(); }
		catch (cause) { if (pending === revision) fail(cause); }
		finally { if (live) busy = false; }
	}
	onMount(() => { void load(); });
	onDestroy(() => { live = false; revision++; members = []; catalog = null; editing = null; });
	const tableSearchId = `${uid}-search`;
	let tableSearch = $state('');
	const tableView = createTableView<(typeof members)[number]>({ rows: () => members, locale: () => intlLocale(), search: () => tableSearch, searchable: row => [row.username || row.user_id, row.user_id, ...row.roles], columns: () => [{ key: 'user', label: t('user'), value: row => row.username || row.user_id }, { key: 'roles', label: t('roles'), value: row => row.roles.join(', '), filterValues: row => row.roles }, { key: 'source', label: t('source'), value: row => row.source ? t(row.source) : null }] });
</script>

<div class="space-y-4">
	{#if loading}<LoadingState variant={members.length ? 'inline' : 'surface'} label={t('loading')} />{/if}
	{#if error && !editing}<Alert tone="danger">{error}</Alert>{/if}
	{#if catalog}
		<Alert tone="info">{t('rolesHelp')}</Alert>
		<div class="grid items-end gap-4 md:grid-cols-[1fr_auto]">
			<Field label={t('user')} for={`${uid}-user`} help={t('eligibleUsersHelp')}>
				<SelectInput id={`${uid}-user`} bind:value={user} disabled={busy || loading}><option value="">{t('selectUser')}</option>{#each users as row (row.id)}<option value={row.id}>{row.name} · {row.email || row.id}</option>{/each}</SelectInput>
			</Field>
			<div><Button variant="primary" disabled={blocked || !session.canSubmit() || busy || loading || !user} onclick={assign}>{t('assignRoles')}</Button></div>
		</div>
	{/if}
	<RegexSearch id={tableSearchId} bind:value={tableSearch} /><TableViewControls view={tableView} />
	<ResponsiveTable>
		{#snippet cards()}
			{#each tableView.rows as member (`${member.user_id}-${member.source ?? ''}`)}<CompactResourceCard>
				<h3 class="text-sm font-medium">{member.username || member.user_id}</h3><p class="text-xs">{member.source ? t(member.source) : '—'} · {t('roleCount', { count: member.roles.length })}</p>{#if member.is_owner && ownerCount <= 1}<p class="text-xs text-ink-2">{t('lastOwner')}</p>{/if}
				{#snippet details()}<p class="text-xs [overflow-wrap:anywhere]">{member.roles.join(', ') || '—'}</p>{/snippet}
				{#snippet actions()}<Button variant="secondary" size="sm" disabled={busy || !editable(member)} onclick={() => startEdit(member)}>{t('editRoles')}</Button><Button variant="danger-outline" size="sm" disabled={blocked || !session.canSubmit() || busy || !removable(member)} onclick={() => remove(member)}>{t('removeMember')}</Button>{/snippet}
			</CompactResourceCard>{/each}
			{#if !loading && !error && !members.length}<p class="text-sm text-ink-2">{t('emptyMembers')}</p>{/if}
		{/snippet}
		<TableShell><table>
			<thead><tr><TableColumnHeader view={tableView} columnKey="user" /><TableColumnHeader view={tableView} columnKey="roles" /><TableColumnHeader view={tableView} columnKey="source" /><th>{t('actions')}</th></tr></thead>
			<tbody>
				{#each tableView.rows as member (`${member.user_id}-${member.source ?? ''}`)}<tr>
					<td>{member.username || member.user_id}</td>
					<td><details><summary class="min-h-11 cursor-pointer">{t('roleCount', { count: member.roles.length })}</summary><p class="max-w-80 whitespace-normal text-xs [overflow-wrap:anywhere]">{member.roles.join(', ') || '—'}</p></details>{#if member.is_owner && ownerCount <= 1}<span class="text-xs text-ink-2">{t('lastOwner')}</span>{/if}</td>
					<td>{member.source ? t(member.source) : '—'}</td>
					<td><div class="flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={busy || !editable(member)} onclick={() => startEdit(member)}>{t('editRoles')}</Button><Button variant="danger-outline" size="sm" disabled={blocked || !session.canSubmit() || busy || !removable(member)} onclick={() => remove(member)}>{t('removeMember')}</Button></div></td>
				</tr>{/each}
				{#if !loading && !error && !members.length}<tr><td colspan="4">{t('emptyMembers')}</td></tr>{/if}
			</tbody>
		</table></TableShell>
	</ResponsiveTable>
</div>
{#if editing && catalog}<ProjectMemberRolesModal member={editing} roles={catalog.roles} {busy} submitDisabled={blocked || !session.canSubmit()} {error} onSave={save} onClose={() => { editing = null; error = ''; }} />{/if}
