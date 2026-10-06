<script lang="ts">
	import { t } from '$lib/i18n/ns/account';
	import { t as tc } from '$lib/i18n/ns/common';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import { onDestroy, untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { ProjectManagerMember, ProjectInvitation } from '$lib/types/project';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';

	type Tab = 'members' | 'invitations';

	let activeTab = $state<Tab>('members');
	let projectId = $derived($auth.projectId ?? '');
	type Scope = { token: string; projectId: string; userId: string | null };
	let scope = $state.raw<Scope | null>(null);
	let membersRequest = 0;
	let invitationsRequest = 0;

	// ── 멤버 탭 ───────────────────────────────────────────────────────────────
	let members = $state<ProjectManagerMember[]>([]);
	let membersLoading = $state(false);
	let membersError = $state('');
	let managingUserId = $state<string | null>(null);

	async function loadMembers(context: Scope) {
		if (scope !== context) return;
		const request = ++membersRequest;
		membersLoading = true;
		membersError = '';
		try {
			const data = await api.get<{ items: ProjectManagerMember[] }>(
				`/api/v1/projects/${context.projectId}/members`,
				context.token,
				context.projectId,
				// Do not join a pending request from an earlier visit to this scope.
				{ refresh: true }
			);
			if (scope === context && request === membersRequest) members = data.items;
		} catch (e) {
			if (scope === context && request === membersRequest) {
				membersError = e instanceof ApiError ? e.message : t('projectSettings.membersFailed');
			}
		} finally {
			if (scope === context && request === membersRequest) membersLoading = false;
		}
	}

	async function promoteManager(member: ProjectManagerMember) {
		const context = scope;
		if (!context || managingUserId || !members.includes(member) || member.is_manager ||
			member.source === 'group' || member.user_id === context.userId) return;
		managingUserId = member.user_id;
		try {
			await api.post(
				`/api/v1/projects/${context.projectId}/managers/${member.user_id}`,
				{}, context.token, context.projectId
			);
			if (scope === context) await loadMembers(context);
		} catch (e) {
			if (scope === context) {
				membersError = e instanceof ApiError ? e.message : t('projectSettings.promoteFailed');
			}
		} finally {
			if (scope === context) managingUserId = null;
		}
	}

	async function demoteManager(member: ProjectManagerMember) {
		const context = scope;
		if (!context || managingUserId || !members.includes(member) || !member.is_manager ||
			member.source === 'group' || member.user_id === context.userId) return;
		managingUserId = member.user_id;
		try {
			await api.delete(
				`/api/v1/projects/${context.projectId}/managers/${member.user_id}`,
				context.token, context.projectId
			);
			if (scope === context) await loadMembers(context);
		} catch (e) {
			if (scope === context) {
				membersError = e instanceof ApiError ? e.message : t('projectSettings.demoteFailed');
			}
		} finally {
			if (scope === context) managingUserId = null;
		}
	}

	// ── 초대 탭 ───────────────────────────────────────────────────────────────
	let invitations = $state<ProjectInvitation[]>([]);
	let invitationsLoading = $state(false);
	let invitationsError = $state('');
	let inviteEmail = $state('');
	let inviteRole = $state('member');
	let inviting = $state(false);
	let inviteSuccess = $state('');
	let revokingInvitationId = $state<number | null>(null);

	// Observe every transition synchronously, including A → B → A before effects run.
	// A fresh object fences old work even when the token/project values return to A.
	const unsubscribe = auth.subscribe((state) => {
		if (scope?.token === state.token && scope?.projectId === state.projectId &&
			scope?.userId === state.userId) return;
		scope = state.token && state.projectId
			? { token: state.token, projectId: state.projectId, userId: state.userId }
			: null;
		members = [];
		membersLoading = false;
		membersError = '';
		managingUserId = null;
		invitations = [];
		invitationsLoading = false;
		invitationsError = '';
		inviteEmail = '';
		inviteRole = 'member';
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
		if (!context || !email || inviting) return;
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
		if (!context || revokingInvitationId !== null || !invitations.includes(invitation) ||
			invitation.status !== 'pending') return;
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
		untrack(() => {
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

	{#if !projectId}
		<div class="text-ink-2 text-xs text-center py-6">{t('projectSettings.noProject')}</div>
	{:else}
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
				<div class="bg-surface-sunken/50 border border-line-2 rounded-xl overflow-hidden">
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
										{#if m.is_manager}
											<span class="text-xs px-2 py-0.5 rounded bg-action-warm/15 text-warm-text border border-action-warm/30 font-medium">{t('projectSettings.administrator')}</span>
										{:else}
											<span class="text-ink-2 text-xs">{t('projectSettings.member')}</span>
										{/if}
									</td>
									<td class="px-4 py-3">
										{#if m.source === 'group' && m.group_name}
											<span class="text-xs px-2 py-0.5 rounded bg-action-warm/10 text-warm-text border border-action-warm/20 font-medium">{m.group_name}</span>
										{/if}
									</td>
									<td class="px-4 py-3 text-right">
										{#if m.source !== 'group' && m.user_id !== $auth.userId}
											{#if m.is_manager}
												<button
													onclick={() => demoteManager(m)}
													disabled={managingUserId !== null}
													class="text-xs text-ink-2 hover:text-red-400 transition-colors"
												>
													{t('projectSettings.removeAdministrator')}
												</button>
											{:else}
												<button
													onclick={() => promoteManager(m)}
													disabled={managingUserId !== null}
													class="text-xs text-ink-2 hover:text-warm-text-hover transition-colors"
												>
													{t('projectSettings.assignAdministrator')}
												</button>
											{/if}
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		{/if}

		<!-- ── 초대 탭 ─────────────────────────────────────────────────────────── -->
		{#if activeTab === 'invitations'}
			<!-- 초대 발송 폼 -->
			<div class="bg-surface-sunken/50 border border-line-2 rounded-xl p-4 mb-5">
				<h4 class="text-sm font-medium text-ink-0 mb-3">{t('projectSettings.newInvitation')}</h4>
				<div class="flex gap-2">
					<input
						bind:value={inviteEmail}
						type="email"
						placeholder="user@example.com"
						class="flex-1 bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm transition-colors"
						onkeydown={(e) => e.key === 'Enter' && sendInvitation()}
					/>
					<select
						bind:value={inviteRole}
						class="bg-surface-sunken border border-line-2 rounded-lg px-3 py-2 text-sm text-ink-0 focus:outline-none focus:border-action-warm transition-colors"
					>
						<option value="member">{t('projectSettings.memberRole')}</option>
						<option value="reader">{t('projectSettings.readerRole')}</option>
					</select>
					<button
						onclick={sendInvitation}
						disabled={!inviteEmail.trim() || inviting}
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
	{/if}
</div>
