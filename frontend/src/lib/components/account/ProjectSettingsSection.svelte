<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { ProjectManagerMember, ProjectInvitation } from '$lib/types/project';

	type Tab = 'members' | 'invitations';

	let activeTab = $state<Tab>('members');
	let projectId = $derived($auth.projectId ?? '');

	// ── 멤버 탭 ───────────────────────────────────────────────────────────────
	let members = $state<ProjectManagerMember[]>([]);
	let membersLoading = $state(false);
	let membersError = $state('');

	async function loadMembers() {
		if (!projectId) return;
		membersLoading = true;
		membersError = '';
		try {
			const data = await api.get<{ items: ProjectManagerMember[] }>(
				`/api/v1/projects/${projectId}/members`,
				$auth.token ?? undefined
			);
			members = data.items;
		} catch (e) {
			membersError = e instanceof ApiError ? e.message : '멤버 목록 조회 실패';
		} finally {
			membersLoading = false;
		}
	}

	async function promoteManager(userId: string) {
		try {
			await api.post(`/api/v1/projects/${projectId}/managers/${userId}`, {}, $auth.token ?? undefined);
			await loadMembers();
		} catch (e) {
			membersError = e instanceof ApiError ? e.message : '승격 실패';
		}
	}

	async function demoteManager(userId: string) {
		try {
			await api.delete(`/api/v1/projects/${projectId}/managers/${userId}`, $auth.token ?? undefined);
			await loadMembers();
		} catch (e) {
			membersError = e instanceof ApiError ? e.message : '해제 실패';
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

	async function loadInvitations() {
		if (!projectId) return;
		invitationsLoading = true;
		invitationsError = '';
		try {
			const data = await api.get<{ items: ProjectInvitation[] }>(
				`/api/v1/projects/${projectId}/invitations`,
				$auth.token ?? undefined
			);
			invitations = data.items;
		} catch (e) {
			invitationsError = e instanceof ApiError ? e.message : '초대 목록 조회 실패';
		} finally {
			invitationsLoading = false;
		}
	}

	async function sendInvitation() {
		if (!inviteEmail.trim() || inviting) return;
		inviting = true;
		invitationsError = '';
		inviteSuccess = '';
		try {
			await api.post(
				`/api/v1/projects/${projectId}/invitations`,
				{ email: inviteEmail.trim(), keystone_role: inviteRole },
				$auth.token ?? undefined
			);
			inviteEmail = '';
			inviteSuccess = '초대가 발송되었습니다.';
			await loadInvitations();
		} catch (e) {
			invitationsError = e instanceof ApiError ? e.message : '초대 발송 실패';
		} finally {
			inviting = false;
		}
	}

	async function revokeInvitation(invId: number) {
		try {
			await api.delete(
				`/api/v1/projects/${projectId}/invitations/${invId}`,
				$auth.token ?? undefined
			);
			await loadInvitations();
		} catch (e) {
			invitationsError = e instanceof ApiError ? e.message : '초대 취소 실패';
		}
	}

	// ── 탭 전환 ───────────────────────────────────────────────────────────────
	$effect(() => {
		if (activeTab === 'members') loadMembers();
		else loadInvitations();
	});

	function statusLabel(status: string): string {
		const map: Record<string, string> = {
			pending: '대기 중',
			accepted: '수락됨',
			declined: '거절됨',
			expired: '만료됨',
			revoked: '취소됨',
			no_user: '미가입',
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
		return new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' });
	}
</script>

<div class="bg-surface-base border border-line rounded-xl p-5">
	<div class="mb-4">
		<h3 class="text-sm font-semibold text-ink-0">프로젝트 멤버 & 초대</h3>
		{#if projectId}
			<p class="text-xs text-ink-3 mt-0.5">{projectId}</p>
		{/if}
	</div>

	{#if !projectId}
		<div class="text-ink-3 text-xs text-center py-6">활성 프로젝트가 없습니다.</div>
	{:else}
		<!-- 탭 -->
		<div class="flex gap-1 mb-5 border-b border-line">
			<button
				onclick={() => (activeTab = 'members')}
				class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px {activeTab === 'members' ? 'border-action-warm text-action-warm' : 'border-transparent text-ink-3 hover:text-ink-0'}"
			>
				멤버
			</button>
			<button
				onclick={() => (activeTab = 'invitations')}
				class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px {activeTab === 'invitations' ? 'border-action-warm text-action-warm' : 'border-transparent text-ink-3 hover:text-ink-0'}"
			>
				초대
			</button>
		</div>

		<!-- ── 멤버 탭 ─────────────────────────────────────────────────────────── -->
		{#if activeTab === 'members'}
			{#if membersError}
				<div class="text-sm text-red-400 mb-4">{membersError}</div>
			{/if}

			{#if membersLoading}
				<div class="space-y-2">
					{#each [1, 2, 3] as _}
						<div class="h-12 bg-surface-sunken rounded-lg animate-pulse"></div>
					{/each}
				</div>
			{:else if members.length === 0}
				<div class="text-ink-3 text-sm text-center py-12">멤버가 없습니다.</div>
			{:else}
				<div class="bg-surface-sunken/50 border border-line-2 rounded-xl overflow-hidden">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-line-2 text-xs text-ink-3 uppercase tracking-wide">
								<th class="text-left px-4 py-3">사용자</th>
								<th class="text-left px-4 py-3">이메일</th>
								<th class="text-left px-4 py-3">역할</th>
								<th class="text-left px-4 py-3">소속</th>
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
											<span class="text-[11px] px-2 py-0.5 rounded bg-action-warm/15 text-action-warm border border-action-warm/30 font-medium">관리자</span>
										{:else}
											<span class="text-ink-3 text-xs">멤버</span>
										{/if}
									</td>
									<td class="px-4 py-3">
										{#if m.source === 'group' && m.group_name}
											<span class="text-[11px] px-2 py-0.5 rounded bg-action-warm/10 text-action-warm border border-action-warm/20 font-medium">{m.group_name}</span>
										{/if}
									</td>
									<td class="px-4 py-3 text-right">
										{#if m.source !== 'group' && m.user_id !== $auth.userId}
											{#if m.is_manager}
												<button
													onclick={() => demoteManager(m.user_id)}
													class="text-xs text-ink-3 hover:text-red-400 transition-colors"
												>
													관리자 해제
												</button>
											{:else}
												<button
													onclick={() => promoteManager(m.user_id)}
													class="text-xs text-ink-3 hover:text-action-warm-hover transition-colors"
												>
													관리자 지정
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
				<h4 class="text-sm font-medium text-ink-0 mb-3">새 초대 발송</h4>
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
						<option value="member">member</option>
						<option value="reader">reader</option>
					</select>
					<button
						onclick={sendInvitation}
						disabled={!inviteEmail.trim() || inviting}
						class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover disabled:bg-action-warm/40 disabled:cursor-not-allowed text-action-on-warm text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
					>
						{inviting ? '발송 중...' : '초대 발송'}
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
			{#if invitationsLoading}
				<div class="space-y-2">
					{#each [1, 2] as _}
						<div class="h-12 bg-surface-sunken rounded-lg animate-pulse"></div>
					{/each}
				</div>
			{:else if invitations.length === 0}
				<div class="text-ink-3 text-sm text-center py-8">초대 내역이 없습니다.</div>
			{:else}
				<div class="bg-surface-sunken/50 border border-line-2 rounded-xl overflow-hidden">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-line-2 text-xs text-ink-3 uppercase tracking-wide">
								<th class="text-left px-4 py-3">이메일</th>
								<th class="text-left px-4 py-3">역할</th>
								<th class="text-left px-4 py-3">상태</th>
								<th class="text-left px-4 py-3">만료일</th>
								<th class="px-4 py-3"></th>
							</tr>
						</thead>
						<tbody class="divide-y divide-line">
							{#each invitations as inv (inv.id)}
								<tr class="hover:bg-surface-selected/40 transition-colors">
									<td class="px-4 py-3 font-medium text-ink-0">{inv.invited_email}</td>
									<td class="px-4 py-3 text-ink-2">{inv.keystone_role}</td>
									<td class="px-4 py-3">
										<span class="text-[11px] px-2 py-0.5 rounded font-medium {statusColor(inv.status)}">
											{statusLabel(inv.status)}
										</span>
									</td>
									<td class="px-4 py-3 text-ink-3 text-xs">{fmtDate(inv.expires_at)}</td>
									<td class="px-4 py-3 text-right">
										{#if inv.status === 'pending'}
											<button
												onclick={() => revokeInvitation(inv.id)}
												class="text-xs text-ink-3 hover:text-red-400 transition-colors"
											>
												취소
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
