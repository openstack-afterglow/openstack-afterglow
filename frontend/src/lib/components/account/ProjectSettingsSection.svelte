<script lang="ts">
	import ResponsiveTable from '$lib/components/ui/ResponsiveTable.svelte';
	import CompactResourceCard from '$lib/components/ui/CompactResourceCard.svelte';
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import { t as td } from '$lib/i18n/ns/domain-iam';
	import { onDestroy, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { auth, canManageDomain } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { ProjectAccessMember, AssignableProjectRoles, EligibleProjectUser, Project } from '$lib/types/project';
	import type { IamSession } from '$lib/api/domainIam';
	import { projectAuthority } from '$lib/api/projectAuthority';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import SelectInput from '$lib/components/ui/SelectInput.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ProjectMemberRolesModal from './ProjectMemberRolesModal.svelte';
	import ProjectLifecycleSection from './ProjectLifecycleSection.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { canManageProject, projectPermissions, refreshProjectPermissions } from '$lib/stores/servicePermissions';
	import { authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	let assignable = $state<AssignableProjectRoles | null>(null);
	let editMember = $state<ProjectAccessMember | null>(null);
	const actorOwner = $derived(assignable?.is_owner === true);

	let projectId = $derived($auth.projectId ?? '');
	type Scope = { token: string; projectId: string; userId: string | null; domainId: string; identityDomainId?: string | null; sessionId?: string; session: IamSession };
	let scope = $state.raw<Scope | null>(null);
	let membersRequest = 0;
	const uid = $props.id();
	let eligible = $state<EligibleProjectUser[]>([]);
	let selectedUser = $state('');
	const activeProject = $derived<Project | null>(scope ? { id: scope.projectId, name: $auth.projectName || scope.projectId, description: '', domain_id: scope.domainId, enabled: true, created_at: null } : null);

	// ── 멤버 탭 ───────────────────────────────────────────────────────────────
	let members = $state<ProjectAccessMember[]>([]);
	let membersLoading = $state(false);
	let membersFresh = $state(false);
	let membersError = $state('');
	let managingUserId = $state<string | null>(null);

	async function loadMembers(context: Scope) {
		if (scope !== context) return;
		const request = ++membersRequest;
		membersLoading = true;
		membersFresh = false;
		membersError = '';
		try {
			const [data, catalog, users] = await Promise.all([
				api.get<{ items: ProjectAccessMember[] }>(`/api/v1/projects/${context.projectId}/members`, context.token, context.projectId, { refresh: true }),
				api.get<AssignableProjectRoles>(`/api/v1/projects/${context.projectId}/assignable-roles`, context.token, context.projectId, { refresh: true }),
				projectAuthority(context.session, context.projectId).eligibleUsers(context.projectId)
			]);
			if (scope === context && request === membersRequest) { members = data.items; assignable = catalog; eligible = users.filter(row => row.enabled); membersFresh = true; if (!eligible.some(row => row.id === selectedUser)) selectedUser = ''; }
		} catch (e) {
			if (scope === context && request === membersRequest) {
				membersError = e instanceof ApiError ? e.message : t('projectSettings.membersFailed');
			}
		} finally {
			if (scope === context && request === membersRequest) membersLoading = false;
		}
	}

	function canEdit(member: ProjectAccessMember): boolean {
		return $canManageProject && assignable !== null && !['group', 'inherited'].includes(member.source ?? '') && ((actorOwner) || !member.is_owner);
	}
	function addMember() {
		if (!scope?.session.canSubmit() || managingUserId || !membersFresh || !assignable) return;
		const user = eligible.find(row => row.id === selectedUser); if (!user) return;
		const existing = members.find(row => row.user_id === user.id);
		if (existing?.is_owner && !actorOwner) return;
		editMember = existing ? { ...existing, source: existing.direct_role_ids.length ? existing.source : 'mixed' } : {
			user_id: user.id, username: user.name, email: user.email, source: 'direct', is_owner: false, is_manager: false,
			roles: [], direct_role_ids: [], effective_role_ids: [], external_role_ids: []
		};
		membersError = '';
	}
	async function saveMemberRoles(roleIds: string[]) {
		const context = scope;
		const member = editMember;
		if (!context || !context.session.canSubmit() || !member || !canEdit(member) || managingUserId || !membersFresh) return;
		managingUserId = member.user_id; membersError = '';
		try {
			await api.put(`/api/v1/projects/${context.projectId}/members/${encodeURIComponent(member.user_id)}/roles`, { role_ids: roleIds }, context.token, context.projectId, { replayOnUnauthorized: false });
			if (scope === context) { editMember = null; await Promise.all([loadMembers(context), refreshProjectPermissions()]); }
		} catch (e) {
			if (scope === context) membersError = e instanceof Error ? e.message : t('projectSettings.saveRolesFailed');
		} finally { if (scope === context) managingUserId = null; }
	}
	async function removeMember(member: ProjectAccessMember) {
		const context = scope;
		if (!context || !context.session.canSubmit() || !canEdit(member) || member.is_owner || managingUserId || !membersFresh || (member.is_manager && !actorOwner)) return;
		if (!await confirmDialog(t('projectSettings.removeMemberConfirm', { user: member.username || member.user_id }), { confirmLabel: t('projectSettings.removeMember') })) return;
		if (scope !== context || !context.session.canSubmit() || !canEdit(member) || member.is_owner || !members.includes(member) || managingUserId || !membersFresh || (member.is_manager && !actorOwner)) return;
		managingUserId = member.user_id;
		try {
			await api.delete(`/api/v1/projects/${context.projectId}/members/${encodeURIComponent(member.user_id)}`, context.token, context.projectId, { replayOnUnauthorized: false });
			if (scope === context) await Promise.all([loadMembers(context), refreshProjectPermissions()]);
		} catch (e) {
			if (scope === context) membersError = e instanceof Error ? e.message : t('projectSettings.removeMemberFailed');
		} finally { if (scope === context) managingUserId = null; }
	}


	// Observe every transition synchronously, including A → B → A before effects run.
	// A fresh object fences old work even when the token/project values return to A.
	const unsubscribe = derived([auth, authReady, projectSwitching, logoutInProgress], ([state, ready, switching, loggingOut]) => ({ state, active: ready && !switching && !loggingOut })).subscribe(({ state, active }) => {
		if (active && scope?.token === state.token && scope?.projectId === state.projectId && scope?.userId === state.userId && scope?.domainId === state.domainId && scope?.identityDomainId === state.identityDomainId && scope?.sessionId === state.sessionId) return;
		const context: Scope | null = active && state.token && state.projectId && state.domainId && state.userId
			? { token: state.token, projectId: state.projectId, userId: state.userId, domainId: state.domainId, identityDomainId: state.identityDomainId, sessionId: state.sessionId,
				session: { token: () => state.token!, userId: state.userId, domainId: state.domainId,
					isCurrent: () => scope === context, canSubmit: () => scope === context && $authReady && !$projectSwitching && !$logoutInProgress && $canManageProject } } : null;
		scope = context;
		members = [];
		membersLoading = false;
		membersError = '';
		managingUserId = null;
		assignable = null; editMember = null;
		eligible = []; selectedUser = ''; membersFresh = false;
	});

	onDestroy(() => {
		unsubscribe();
		scope = null;
	});


	$effect(() => {
		const context = scope;
		const allowed = $canManageProject;
		if (context && allowed) untrack(() => { void loadMembers(context); });
	});

</script>

<div class="motion-fade bg-surface-base border border-line rounded-xl p-5">
	<div class="mb-4">
		<h3 class="text-sm font-semibold text-ink-0">{t('projectSettings.title')}</h3>
		{#if projectId}
			<p class="text-xs text-ink-2 mt-0.5">{projectId}</p>
		{/if}
	</div>
	{#if $canManageDomain}<div class="mb-4"><Button href="/dashboard/iam" variant="secondary" size="sm">{td('invitations')}</Button></div>{/if}
	{#if $projectPermissions.loading}<ActivityIndicator label={t('projectSettings.checkingPermissions')} />{/if}
	{#if $projectPermissions.error}<p role="alert" class="text-sm text-state-danger-text">{$projectPermissions.error}</p><Button variant="secondary" size="sm" onclick={() => { void refreshProjectPermissions(); }}>{t('projectSettings.recheckPermissions')}</Button>{/if}

	{#if !projectId}
		<div class="text-ink-2 text-xs text-center py-6">{t('projectSettings.noProject')}</div>
	{:else if $canManageProject}
			{#if scope && activeProject}
				{#key scope}<ProjectLifecycleSection session={scope.session} project={activeProject} callerProject={scope.projectId} blocked={!$canManageProject} onChanged={() => { if (scope) { void loadMembers(scope); void refreshProjectPermissions(); } }} onDeleted={() => { members = []; assignable = null; membersFresh = false; void refreshProjectPermissions(); }} />{/key}
			{/if}
			<div class="my-4 grid items-end gap-3 md:grid-cols-2"><Field label={td('user')} for={`${uid}-member`} help={td('eligibleUsersHelp')}><SelectInput id={`${uid}-member`} bind:value={selectedUser} disabled={membersLoading || managingUserId !== null}><option value="">{td('selectUser')}</option>{#each eligible as row (row.id)}<option value={row.id}>{row.name} · {row.email || row.id}</option>{/each}</SelectInput></Field><div><Button variant="secondary" disabled={!membersFresh || managingUserId !== null || !selectedUser} onclick={addMember}>{td('assignRoles')}</Button></div></div>
			{#if membersError}
				<div class="text-sm text-red-400 mb-4">{membersError}</div>
				{#if !membersFresh && scope}<Button variant="secondary" size="sm" disabled={membersLoading} onclick={() => { if (scope) void loadMembers(scope); }}>{t('projectSettings.retry')}</Button>{/if}
			{/if}

			{#if managingUserId}<ActivityIndicator label={tc('state.processing')} />{/if}
			{#if membersLoading && members.length > 0}<ActivityIndicator label={tc('state.loading')} />{/if}
			{#if membersLoading && members.length === 0}
				<ActivityIndicator label={tc('state.loading')} />
				<div class="space-y-2 mt-2" aria-hidden="true">
					{#each [1, 2, 3] as _}
						<div class="h-12 motion-skeleton rounded-lg"></div>
					{/each}
				</div>
			{:else if members.length === 0}
				<div class="text-ink-2 text-sm text-center py-12">{t('projectSettings.noMembers')}</div>
			{:else}
				<ResponsiveTable>{#snippet cards()}
					{#each members.slice().sort((a, b) => (a.source === 'group' ? 1 : 0) - (b.source === 'group' ? 1 : 0)) as m (m.user_id)}<CompactResourceCard>
						<div class="flex flex-wrap justify-between gap-2"><h3 class="text-sm font-medium">{m.username || m.user_id}</h3><span class="text-xs">{m.is_owner ? 'owner' : m.is_manager ? 'admin' : 'member'}</span></div><p class="text-sm break-all">{m.email || '—'}</p>{#if m.group_name}<p class="text-xs text-ink-2">{m.group_name}</p>{/if}
						{#snippet details()}<p class="text-xs [overflow-wrap:anywhere]">{t('projectSettings.directRoles', { roles: (m.direct_role_ids ?? []).map(id => assignable?.roles.find(role => role.id === id)?.name ?? id).join(', ') || '—' })}</p><p class="text-xs [overflow-wrap:anywhere]">{t('projectSettings.effectiveRoles', { roles: (m.roles ?? []).join(', ') || '—' })}</p>{/snippet}
						{#snippet actions()}{#if canEdit(m)}<Button variant="secondary" size="sm" disabled={managingUserId !== null || !membersFresh} onclick={() => { editMember = m; membersError = ''; }}>{t('projectSettings.editRoles')}</Button>{#if !m.is_owner && (actorOwner || !m.is_manager)}<Button variant="danger" size="sm" disabled={managingUserId !== null || !membersFresh || !(m.direct_role_ids?.length)} onclick={() => removeMember(m)}>{t('projectSettings.removeMember')}</Button>{/if}{:else if ['group', 'inherited'].includes(m.source ?? '')}<span class="text-xs text-ink-2">{t('projectSettings.inheritedReadOnly')}</span>{/if}{/snippet}
					</CompactResourceCard>{/each}
				{/snippet}
				<TableShell>
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-line-2 text-xs text-ink-2 uppercase tracking-wide">
								<th class="text-left px-4 py-3">{t('projectSettings.user')}</th>
								<th class="text-left px-4 py-3">{t('projectSettings.email')}</th>
								<th class="text-left px-4 py-3">{t('projectSettings.role')}</th>
								<th class="text-left px-4 py-3">{t('projectSettings.affiliation')}</th>
								<th class="px-4 py-3"></th>
							</tr>
						</thead>
						<tbody class="divide-y divide-line">
							{#each members.slice().sort((a, b) => (a.source === 'group' ? 1 : 0) - (b.source === 'group' ? 1 : 0)) as m (m.user_id)}
								<tr class="hover:bg-surface-selected/40 transition-colors">
									<td class="px-4 py-3 font-medium text-ink-0">{m.username || m.user_id}</td>
									<td class="px-4 py-3 text-ink-2">{m.email || '—'}</td>
									<td class="px-4 py-3">
										<span class="text-xs text-ink-2">{m.is_owner ? 'owner' : m.is_manager ? 'admin' : 'member'}</span>
										<details class="mt-1 text-xs text-ink-2"><summary>{t('projectSettings.directEffectiveRoles')}</summary><p class="[overflow-wrap:anywhere]">{t('projectSettings.directRoles', { roles: (m.direct_role_ids ?? []).map(id => assignable?.roles.find(role => role.id === id)?.name ?? id).join(', ') || '—' })}</p><p class="[overflow-wrap:anywhere]">{t('projectSettings.effectiveRoles', { roles: (m.roles ?? []).join(', ') || '—' })}</p></details>
									</td>
									<td class="px-4 py-3">
										{#if m.group_name}
											<span class="text-xs px-2 py-0.5 rounded bg-action-warm/10 text-warm-text border border-action-warm/20 font-medium">{m.group_name}</span>
										{/if}
									</td>
									<td class="px-4 py-3 text-right">
										{#if canEdit(m)}
											<Button variant="secondary" size="sm" disabled={managingUserId !== null || !membersFresh} onclick={() => { editMember = m; membersError = ''; }}>{t('projectSettings.editRoles')}</Button>
											{#if !m.is_owner && (actorOwner || !m.is_manager)}<Button variant="danger" size="sm" disabled={managingUserId !== null || !membersFresh || !(m.direct_role_ids?.length)} onclick={() => removeMember(m)}>{t('projectSettings.removeMember')}</Button>{/if}
										{:else if ['group', 'inherited'].includes(m.source ?? '')}<span class="text-xs text-ink-2">{t('projectSettings.inheritedReadOnly')}</span>{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
				</ResponsiveTable>
			{/if}

	{:else if !$projectPermissions.loading && !$projectPermissions.error}
		<p class="text-sm text-ink-2">{t('projectSettings.managerRequired')}</p>
	{/if}
</div>

{#if editMember && assignable && $canManageProject}
	<ProjectMemberRolesModal member={editMember} roles={assignable.roles} busy={managingUserId !== null} submitDisabled={!membersFresh || !scope?.session.canSubmit()} error={membersError} onSave={saveMemberRoles} onClose={() => { if (!managingUserId) editMember = null; }} />
{/if}
