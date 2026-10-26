<script lang="ts">
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { onMount, onDestroy, untrack } from 'svelte';
	import { ApiError } from '$lib/api/client';
	import { domainIam, type IamSession, type IamAssignableRoles } from '$lib/api/domainIam';
	import { projectAuthority } from '$lib/api/projectAuthority';
	import type { Project, ProjectAccessMember, EligibleProjectUser } from '$lib/types/project';
	import { t } from '$lib/i18n/ns/domain-iam';
	import { t as workspaceT } from '$lib/i18n/ns/workspace-selector';
	import { iamErrorMessage } from './iamError';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import ProjectMemberRolesModal from '$lib/components/account/ProjectMemberRolesModal.svelte';
	import ProjectLifecycleSection from '$lib/components/account/ProjectLifecycleSection.svelte';
	import IamProjectCreators from './IamProjectCreators.svelte';
	import CreateProjectModal from '$lib/components/projects/CreateProjectModal.svelte';
	let { session, blocked = false, onDenied }: { session: IamSession; blocked?: boolean; onDenied: () => void } = $props();
	const client = untrack(() => domainIam(session));
	const authority = untrack(() => projectAuthority(session));
	const uid = $props.id();
	let live = true;
	let revision = 0;
	let projects = $state<Project[]>([]);
	let users = $state<EligibleProjectUser[]>([]);
	let project = $state('');
	let user = $state('');
	let members = $state<ProjectAccessMember[]>([]);
	let catalog = $state<IamAssignableRoles | null>(null);
	let editing = $state<ProjectAccessMember | null>(null);
	let loading = $state(true);
	let busy = $state(false);
	let showCreate = $state(false);
	let creating = $state(false);
	let error = $state('');
	const ownerCount = $derived(new Set(members.filter(member => member.is_owner).map(member => member.user_id)).size);
	function fail(cause: unknown) {
		if (!live || !session.isCurrent()) return;
		error = iamErrorMessage(cause, t('loadFailed'));
		if (cause instanceof ApiError && cause.status === 403) onDenied();
	}
	async function load() {
		const pending = ++revision; const target = project;
		loading = true; error = ''; catalog = null; editing = null; members = []; users = []; user = '';
		if (!target) { loading = false; return; }
		try {
			const [rows, roles, eligible] = await Promise.all([client.members(target), client.roles(target), authority.eligibleUsers(target)]);
			if (live && session.isCurrent() && pending === revision) { members = rows.items; catalog = roles; users = eligible.filter(row => row.enabled); }
		} catch (cause) { if (pending === revision) fail(cause); }
		finally { if (live && pending === revision) loading = false; }
	}
	async function initialize(preferred = project) {
		const pending = ++revision;
		loading = true; error = '';
		try {
			const p = await client.projects();
			if (live && session.isCurrent() && pending === revision) {
				projects = p.items;
				project = projects.some(row => row.id === preferred) ? preferred : projects[0]?.id ?? '';
				await load();
			}
		} catch (cause) { if (pending === revision) { fail(cause); if (live) loading = false; } }
	}
	function created(result: { id: string; name: string }) {
		if (!live || !session.isCurrent()) return;
		showCreate = false;
		void initialize(result.id);
	}
	function editable(member: ProjectAccessMember) { return !loading && !!catalog && !['group', 'inherited'].includes(member.source ?? '') && (catalog.can_manage_owners || !member.is_owner); }
	function removable(member: ProjectAccessMember) { return editable(member) && !member.is_owner && (!member.is_manager || catalog?.can_manage_owners); }
	function assign() {
		if (!live || !session.isCurrent() || blocked || !session.canSubmit() || busy || loading || !catalog || !user) return;
		const selected = users.find(row => row.id === user); if (!selected) return;
		const current = members.find(row => row.user_id === user);
		if (current?.is_owner && !catalog.can_manage_owners) return;
		editing = current ? { ...current, source: current.direct_role_ids.length ? current.source : 'mixed' } : { user_id: selected.id, username: selected.name, email: selected.email, is_owner: false, is_manager: false, source: 'direct', roles: [], direct_role_ids: [], effective_role_ids: [], external_role_ids: [] };
		error = '';
	}
	async function save(roleIds: string[]) {
		const member = editing; const target = project; const pending = revision;
		if (!live || !session.canSubmit() || blocked || !member || busy || loading || !catalog || (member.is_owner && !catalog.can_manage_owners)) return;
		busy = true; error = '';
		try { await client.assignRoles(target, member.user_id, roleIds); if (live && session.isCurrent() && pending === revision) { editing = null; await load(); } }
		catch (cause) { if (pending === revision) fail(cause); }
		finally { if (live) busy = false; }
	}
	async function remove(member: ProjectAccessMember) {
		const target = project; const pending = revision;
		if (!live || !session.canSubmit() || blocked || busy || !removable(member)) return;
		const approved = await confirmDialog(t('removeConfirm', { user: member.username || member.user_id }), { confirmLabel: t('removeMember') });
		if (!approved || !live || !session.canSubmit() || blocked || revision !== pending || busy || !removable(member) || !members.includes(member)) return;
		busy = true; error = '';
		try { await client.removeMember(target, member.user_id); if (live && revision === pending) await load(); }
		catch (cause) { if (pending === revision) fail(cause); }
		finally { if (live) busy = false; }
	}
	onMount(() => { void initialize(); });
	onDestroy(() => { live = false; revision++; members = []; catalog = null; editing = null; });
</script>

<div class="space-y-4">
	<div class="flex flex-wrap justify-end gap-2"><Button variant="accent" disabled={blocked || !session.canSubmit() || busy || creating} onclick={() => { showCreate = true; }}>{workspaceT('newProject')}</Button></div>
	<IamProjectCreators {session} {blocked} {onDenied} />
	<div class="grid gap-4 md:grid-cols-2">
		<Field label={t('project')} for={`${uid}-project`}><SelectInput id={`${uid}-project`} bind:value={project} disabled={busy || !projects.length} onchange={() => { user = ''; void load(); }}><option value="">{t('selectProject')}</option>{#each projects as row (row.id)}<option value={row.id}>{row.name}</option>{/each}</SelectInput></Field>
		<div class="flex items-end"><Button variant="secondary" disabled={busy || loading} onclick={() => { void (projects.length ? load() : initialize()); }}>{t('refresh')}</Button></div>
	</div>
	{#if loading}<ActivityIndicator label={t('loading')} />{/if}
	{#if error && !editing}<Alert tone="danger">{error}</Alert>{/if}
	{#if !loading && !error && !projects.length}<Alert tone="info">{t('emptyProjects')}</Alert>{/if}
	{#if project && projects.some(row => row.id === project)}
		{#key project}<ProjectLifecycleSection {session} project={projects.find(row => row.id === project)!} {blocked} {onDenied} onChanged={() => { void load(); }} onDeleted={() => { void initialize(); }} />{/key}
	{/if}
	{#if catalog}
		<Alert tone="info">{t('rolesHelp')}</Alert>
		<div class="grid items-end gap-4 md:grid-cols-2"><Field label={t('user')} for={`${uid}-user`} help={t('eligibleUsersHelp')}><SelectInput id={`${uid}-user`} bind:value={user} disabled={busy || loading}><option value="">{t('selectUser')}</option>{#each users as row (row.id)}<option value={row.id}>{row.name} · {row.email || row.id}</option>{/each}</SelectInput></Field><div><Button variant="primary" disabled={blocked || !session.canSubmit() || busy || loading || !user} onclick={assign}>{t('assignRoles')}</Button></div></div>
	{/if}
	<ResponsiveTable>{#snippet cards()}
		{#each members as member (`${member.user_id}-${member.source ?? ''}`)}<CompactResourceCard>
			<h3 class="text-sm font-medium">{member.username || member.user_id}</h3><p class="text-xs">{member.source ? t(member.source) : '—'} · {t('roleCount', { count: member.roles.length })}</p>{#if member.is_owner && ownerCount <= 1}<p class="text-xs text-ink-2">{t('lastOwner')}</p>{/if}
			{#snippet details()}<p class="text-xs [overflow-wrap:anywhere]">{member.roles.join(', ') || '—'}</p>{/snippet}
			{#snippet actions()}<Button variant="secondary" size="sm" disabled={busy || !editable(member)} onclick={() => { editing = member; error = ''; }}>{t('editRoles')}</Button><Button variant="danger-outline" size="sm" disabled={blocked || !session.canSubmit() || busy || !removable(member)} onclick={() => remove(member)}>{t('removeMember')}</Button>{/snippet}
		</CompactResourceCard>{/each}
		{#if !loading && !error && project && !members.length}<p class="text-sm text-ink-2">{t('emptyMembers')}</p>{/if}
	{/snippet}
	<TableShell><table>
		<thead><tr><th>{t('user')}</th><th>{t('roles')}</th><th>{t('source')}</th><th>{t('actions')}</th></tr></thead>
		<tbody>{#each members as member (`${member.user_id}-${member.source ?? ''}`)}<tr><td>{member.username || member.user_id}</td><td><details><summary class="min-h-11 cursor-pointer">{t('roleCount', { count: member.roles.length })}</summary><p class="max-w-80 whitespace-normal text-xs [overflow-wrap:anywhere]">{member.roles.join(', ') || '—'}</p></details>{#if member.is_owner && ownerCount <= 1}<span class="text-xs text-ink-2">{t('lastOwner')}</span>{/if}</td><td>{member.source ? t(member.source) : '—'}</td><td><div class="flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={busy || !editable(member)} onclick={() => { editing = member; error = ''; }}>{t('editRoles')}</Button><Button variant="danger-outline" size="sm" disabled={blocked || !session.canSubmit() || busy || !removable(member)} onclick={() => remove(member)}>{t('removeMember')}</Button></div></td></tr>{/each}
		{#if !loading && !error && project && !members.length}<tr><td colspan="4">{t('emptyMembers')}</td></tr>{/if}</tbody>
	</table></TableShell>
	</ResponsiveTable>
</div>
{#if editing && catalog}<ProjectMemberRolesModal member={editing} roles={catalog.roles} {busy} submitDisabled={blocked || !session.canSubmit()} {error} onSave={save} onClose={() => { editing = null; error = ''; }} />{/if}
{#if showCreate}<CreateProjectModal domainId={session.domainId} domainName="" bind:submitting={creating} submitDisabled={blocked || !session.canSubmit()} onCreate={authority.create} onClose={() => { showCreate = false; }} onSuccess={created} />{/if}
