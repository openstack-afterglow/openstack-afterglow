<script lang="ts">
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { onDestroy, untrack } from 'svelte';
	import { derived } from 'svelte/store';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { ProjectAccessMember, ProjectInvitation, AssignableProjectRoles } from '$lib/types/project';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ProjectMemberRolesModal from './ProjectMemberRolesModal.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { canManageProject, projectPermissions, refreshProjectPermissions } from '$lib/stores/servicePermissions';
	import { authReady, projectSwitching } from '$lib/stores/auth';
	let assignable = $state<AssignableProjectRoles | null>(null);
	let editMember = $state<ProjectAccessMember | null>(null);
	let migrationOwnerId = $state('');
	let migrating = $state(false);
	let migrationNotice = $state('');
	const verifiedSystemAdmin = $derived($authReady && !$projectSwitching && $auth.isSystemAdmin === true);
	const actorOwner = $derived($projectPermissions.permissions?.is_owner === true || verifiedSystemAdmin);

	type Tab = 'members' | 'invitations';

	let activeTab = $state<Tab>('members');
	let projectId = $derived($auth.projectId ?? '');
	type Scope = { token: string; projectId: string; userId: string | null };
	let scope = $state.raw<Scope | null>(null);
	let membersRequest = 0;
	let invitationsRequest = 0;

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
			const [data, catalog] = await Promise.all([
				api.get<{ items: ProjectAccessMember[] }>(`/api/v1/projects/${context.projectId}/members`, context.token, context.projectId, { refresh: true }),
				api.get<AssignableProjectRoles>(`/api/v1/projects/${context.projectId}/assignable-roles`, context.token, context.projectId, { refresh: true })
			]);
			if (scope === context && request === membersRequest) { members = data.items; assignable = catalog; membersFresh = true; }
		} catch (e) {
			if (scope === context && request === membersRequest) {
				membersError = e instanceof ApiError ? e.message : t('projectSettings.membersFailed');
			}
		} finally {
			if (scope === context && request === membersRequest) membersLoading = false;
		}
	}

	function canEdit(member: ProjectAccessMember): boolean {
		return $canManageProject && assignable !== null && !['group', 'inherited'].includes(member.source ?? '') && ((assignable.is_owner && actorOwner) || !member.is_owner);
	}
	async function saveMemberRoles(roleIds: string[]) {
		const context = scope;
		const member = editMember;
		if (!context || !member || !canEdit(member) || managingUserId || !membersFresh) return;
		managingUserId = member.user_id; membersError = '';
		try {
			await api.put(`/api/v1/projects/${context.projectId}/members/${member.user_id}/roles`, { role_ids: roleIds }, context.token, context.projectId);
			if (scope === context) { editMember = null; await Promise.all([loadMembers(context), refreshProjectPermissions()]); }
		} catch (e) {
			if (scope === context) membersError = e instanceof Error ? e.message : t('projectSettings.saveRolesFailed');
		} finally { if (scope === context) managingUserId = null; }
	}
	async function removeMember(member: ProjectAccessMember) {
		const context = scope;
		if (!context || !canEdit(member) || managingUserId || !membersFresh || (member.is_manager && !actorOwner)) return;
		if (!await confirmDialog(t('projectSettings.removeMemberConfirm', { user: member.username || member.user_id }), { confirmLabel: t('projectSettings.removeMember') })) return;
		if (scope !== context || !canEdit(member) || !members.includes(member) || managingUserId || !membersFresh || (member.is_manager && !actorOwner)) return;
		managingUserId = member.user_id;
		try {
			await api.delete(`/api/v1/projects/${context.projectId}/members/${member.user_id}`, context.token, context.projectId);
			if (scope === context) await Promise.all([loadMembers(context), refreshProjectPermissions()]);
		} catch (e) {
			if (scope === context) membersError = e instanceof Error ? e.message : t('projectSettings.removeMemberFailed');
		} finally { if (scope === context) managingUserId = null; }
	}
	async function migrateManagers() {
		const context = scope;
		const owner = migrationOwnerId.trim();
		if (!context || !owner || !verifiedSystemAdmin || migrating) return;
		if (!await confirmDialog(t('projectSettings.migrationConfirm', { owner }), { confirmLabel: t('projectSettings.migrateConfirm'), confirmVariant: 'primary' })) return;
		if (scope !== context || !verifiedSystemAdmin || migrating) return;
		migrating = true; membersError = '';
		try {
			const result = await api.post<{ migrated_user_ids: string[]; deleted_legacy_rows: number }>(`/api/v1/projects/${context.projectId}/members/migrate-legacy-managers`, { owner_user_id: owner }, context.token, context.projectId);
			if (scope === context) { migrationNotice = t('projectSettings.migrationNotice', { users: result.migrated_user_ids.length, records: result.deleted_legacy_rows }); await Promise.all([loadMembers(context), refreshProjectPermissions()]); }
		} catch (e) {
			if (scope === context) membersError = e instanceof Error ? e.message : t('projectSettings.migrationFailed');
		} finally { if (scope === context) migrating = false; }
	}

	// ── 초대 탭 ───────────────────────────────────────────────────────────────
	let invitations = $state<ProjectInvitation[]>([]);
	let invitationsLoading = $state(false);
	let invitationsError = $state('');
	let inviteEmail = $state('');
	let inviteRole = $state('project_member');
	let inviting = $state(false);
	let inviteSuccess = $state('');
	let revokingInvitationId = $state<number | null>(null);

	// Observe every transition synchronously, including A → B → A before effects run.
	// A fresh object fences old work even when the token/project values return to A.
	const unsubscribe = derived([auth, authReady, projectSwitching], ([state, ready, switching]) => ({ state, active: ready && !switching })).subscribe(({ state, active }) => {
		if (active && scope?.token === state.token && scope?.projectId === state.projectId && scope?.userId === state.userId) return;
		scope = active && state.token && state.projectId
			? { token: state.token, projectId: state.projectId, userId: state.userId }
			: null;
		members = [];
		membersLoading = false;
		membersError = '';
		managingUserId = null;
		assignable = null; editMember = null; migrationOwnerId = ''; migrating = false; migrationNotice = '';
		invitations = [];
		invitationsLoading = false;
		invitationsError = '';
		inviteEmail = '';
		inviteRole = 'project_member';
		inviting = false;
		inviteSuccess = '';
		revokingInvitationId = null;
	});

	onDestroy(() => {
		unsubscribe();
		scope = null;
	});

	async function loadInvitations(context: Scope) {
		if (scope !== context) return;
		const request = ++invitationsRequest;
		invitationsLoading = true;
		invitationsError = '';
		try {
			const data = await api.get<{ items: ProjectInvitation[] }>(
				`/api/v1/projects/${context.projectId}/invitations`,
				context.token,
				context.projectId,
				{ refresh: true }
			);
			if (scope === context && request === invitationsRequest) invitations = data.items;
		} catch (e) {
			if (scope === context && request === invitationsRequest) {
				invitationsError = e instanceof ApiError ? e.message : t('projectSettings.invitationsFailed');
			}
		} finally {
			if (scope === context && request === invitationsRequest) invitationsLoading = false;
		}
	}

	async function sendInvitation() {
		const context = scope;
		const email = inviteEmail.trim();
		const role = inviteRole;
		if (!context || !email || inviting || !$canManageProject) return;
		inviting = true;
		invitationsError = '';
		inviteSuccess = '';
		try {
			await api.post(
				`/api/v1/projects/${context.projectId}/invitations`,
				{ email, keystone_role: role },
				context.token,
				context.projectId
			);
			if (scope !== context) return;
			inviteEmail = '';
			inviteSuccess = t('projectSettings.sent');
			await loadInvitations(context);
		} catch (e) {
			if (scope === context) {
				invitationsError = e instanceof ApiError ? e.message : t('projectSettings.sendFailed');
			}
		} finally {
			if (scope === context) inviting = false;
		}
	}

	async function revokeInvitation(invitation: ProjectInvitation) {
		const context = scope;
		if (!context || !$canManageProject || revokingInvitationId !== null || !invitations.includes(invitation) || invitation.status !== 'pending') return;
		revokingInvitationId = invitation.id;
		try {
			await api.delete(
				`/api/v1/projects/${context.projectId}/invitations/${invitation.id}`,
				context.token,
				context.projectId
			);
			if (scope === context) await loadInvitations(context);
		} catch (e) {
			if (scope === context) {
				invitationsError = e instanceof ApiError ? e.message : t('projectSettings.revokeFailed');
			}
		} finally {
			if (scope === context) revokingInvitationId = null;
		}
	}

	// ── 탭 전환 ───────────────────────────────────────────────────────────────
	$effect(() => {
		const context = scope;
		const tab = activeTab;
		if (!context) return;
		const allowed = $canManageProject;
		untrack(() => {
			if (!allowed) return;
			if (tab === 'members') void loadMembers(context);
			else void loadInvitations(context);
		});
	});

	function statusLabel(status: string): string {
		const map: Record<string, string> = {
			pending: t('projectSettings.pending'),
			accepted: t('projectSettings.accepted'),
			declined: t('projectSettings.declined'),
			expired: t('projectSettings.expired'),
			revoked: t('projectSettings.revoked'),
			no_user: t('projectSettings.noUser'),
		};
		return map[status] ?? status;
	}

	function statusColor(status: string): string {
		if (status === 'accepted') return 'text-green-400 bg-green-500/10';
		if (status === 'pending') return 'text-yellow-400 bg-yellow-500/10';
		if (status === 'no_user') return 'text-ink-2 bg-surface-selected/10';
		return 'text-red-400 bg-red-500/10';
	}

	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleDateString(intlLocale(), { year: 'numeric', month: 'short', day: 'numeric' });
	}
</script>

<div class="motion-fade bg-surface-base border border-line rounded-xl p-5">
	<div class="mb-4">
		<h3 class="text-sm font-semibold text-ink-0">{t('projectSettings.title')}</h3>
		{#if projectId}
			<p class="text-xs text-ink-2 mt-0.5">{projectId}</p>
		{/if}
	</div>
	{#if $projectPermissions.loading}<ActivityIndicator label={t('projectSettings.checkingPermissions')} />{/if}
	{#if $projectPermissions.error}<p role="alert" class="text-sm text-state-danger-text">{$projectPermissions.error}</p><Button variant="secondary" size="sm" onclick={() => { void refreshProjectPermissions(); }}>{t('projectSettings.recheckPermissions')}</Button>{/if}

	{#if !projectId}
		<div class="text-ink-2 text-xs text-center py-6">{t('projectSettings.noProject')}</div>
	{:else if $canManageProject}
		<!-- 탭 -->
		<div class="flex gap-1 mb-5 border-b border-line">
			<button
				onclick={() => (activeTab = 'members')}
				class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px {activeTab === 'members' ? 'border-action-warm text-warm-text' : 'border-transparent text-ink-2 hover:text-ink-0'}"
			>
				{t('projectSettings.members')}
			</button>
			<button
				onclick={() => (activeTab = 'invitations')}
				class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px {activeTab === 'invitations' ? 'border-action-warm text-warm-text' : 'border-transparent text-ink-2 hover:text-ink-0'}"
			>
				{t('projectSettings.invitations')}
			</button>
		</div>

		<!-- ── 멤버 탭 ─────────────────────────────────────────────────────────── -->
		{#if activeTab === 'members'}
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
											{#if actorOwner || !m.is_manager}<Button variant="danger" size="sm" disabled={managingUserId !== null || !membersFresh || !(m.direct_role_ids?.length)} onclick={() => removeMember(m)}>{t('projectSettings.removeMember')}</Button>{/if}
										{:else if ['group', 'inherited'].includes(m.source ?? '')}<span class="text-xs text-ink-2">{t('projectSettings.inheritedReadOnly')}</span>{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</TableShell>
			{/if}
			{#if verifiedSystemAdmin}
				<div class="mt-4 border border-line rounded-lg p-3 space-y-3">
					<Field label={t('projectSettings.migrationOwner')} for="migration-owner" help={t('projectSettings.migrationHelp')}><TextInput id="migration-owner" bind:value={migrationOwnerId} disabled={migrating} /></Field>
					<Button variant="secondary" disabled={!migrationOwnerId.trim() || migrating} ariaBusy={migrating} onclick={migrateManagers}>{t('projectSettings.migrateManagers')}</Button>
					{#if migrationNotice}<p role="status" class="text-sm text-ink-2">{migrationNotice}</p>{/if}
				</div>
			{/if}
		{/if}

		<!-- ── 초대 탭 ─────────────────────────────────────────────────────────── -->
		{#if activeTab === 'invitations'}
			<!-- 초대 발송 폼 -->
			<div class="bg-surface-sunken/50 border border-line-2 rounded-xl p-4 mb-5">
				<h4 class="text-sm font-medium text-ink-0 mb-3">{t('projectSettings.newInvitation')}</h4>
				<div class="flex flex-wrap gap-2">
					<input
						bind:value={inviteEmail}
						type="email"
						placeholder="user@example.com"
						class="flex-1 min-w-0 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm transition-colors"
						onkeydown={(e) => e.key === 'Enter' && sendInvitation()}
					/>
					<select
						bind:value={inviteRole}
						class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm transition-colors"
					>
						<option value="project_member">{t('projectSettings.memberRole')}</option>
						<option value="project_reader">{t('projectSettings.readerRole')}</option>
					</select>
					<button
						onclick={sendInvitation}
						disabled={!$canManageProject || !inviteEmail.trim() || inviting}
						class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-action-warm/40 disabled:cursor-not-allowed text-action-on-warm text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
					>
						{#if inviting}<ActivityIndicator size="xs" label={t('projectSettings.sending')} />{:else}{t('projectSettings.send')}{/if}
					</button>
				</div>
				{#if inviteSuccess}
					<div class="mt-2 text-xs text-green-400">{inviteSuccess}</div>
				{/if}
				{#if invitationsError}
					<div class="mt-2 text-xs text-red-400">{invitationsError}</div>
				{/if}
			</div>

			<!-- 초대 목록 -->
			{#if revokingInvitationId !== null}<ActivityIndicator label={tc('state.processing')} />{/if}
			{#if invitationsLoading && invitations.length > 0}<ActivityIndicator label={tc('state.loading')} />{/if}
			{#if invitationsLoading && invitations.length === 0}
				<ActivityIndicator label={tc('state.loading')} />
				<div class="space-y-2 mt-2" aria-hidden="true">
					{#each [1, 2] as _}
						<div class="h-12 motion-skeleton rounded-lg"></div>
					{/each}
				</div>
			{:else if invitations.length === 0}
				<div class="text-ink-2 text-sm text-center py-8">{t('projectSettings.noInvitations')}</div>
			{:else}
				<div class="bg-surface-sunken/50 border border-line-2 rounded-xl overflow-hidden">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-line-2 text-xs text-ink-2 uppercase tracking-wide">
								<th class="text-left px-4 py-3">{t('projectSettings.email')}</th>
								<th class="text-left px-4 py-3">{t('projectSettings.role')}</th>
								<th class="text-left px-4 py-3">{t('projectSettings.status')}</th>
								<th class="text-left px-4 py-3">{t('projectSettings.expires')}</th>
								<th class="px-4 py-3"></th>
							</tr>
						</thead>
						<tbody class="divide-y divide-line">
							{#each invitations as inv (inv.id)}
								<tr class="hover:bg-surface-selected/40 transition-colors">
									<td class="px-4 py-3 font-medium text-ink-0">{inv.invited_email}</td>
									<td class="px-4 py-3 text-ink-2">{inv.keystone_role}</td>
									<td class="px-4 py-3">
										<span class="text-xs px-2 py-0.5 rounded font-medium {statusColor(inv.status)}">
											{statusLabel(inv.status)}
										</span>
									</td>
									<td class="px-4 py-3 text-ink-2 text-xs">{fmtDate(inv.expires_at)}</td>
									<td class="px-4 py-3 text-right">
										{#if inv.status === 'pending'}
											<button
												onclick={() => revokeInvitation(inv)}
												disabled={revokingInvitationId !== null}
												class="text-xs text-ink-2 hover:text-red-400 transition-colors"
											>
												{t('projectSettings.cancel')}
											</button>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		{/if}
	{:else if !$projectPermissions.loading && !$projectPermissions.error}
		<p class="text-sm text-ink-2">{t('projectSettings.managerRequired')}</p>
	{/if}
</div>

{#if editMember && assignable && $canManageProject}
	<ProjectMemberRolesModal member={editMember} roles={assignable.roles} isOwner={assignable.is_owner && actorOwner} busy={managingUserId !== null} error={membersError} onSave={saveMemberRoles} onClose={() => { if (!managingUserId) editMember = null; }} />
{/if}
