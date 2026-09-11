<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';

	interface Project {
		id: string;
		name: string;
		description: string;
		enabled: boolean;
		domain_id: string | null;
		created_at: string | null;
	}
	interface Member {
		user_id: string;
		user_name: string;
		role_id: string;
		role_name: string;
		type?: 'user' | 'group';
		group_id?: string;
	}
	interface User { id: string; name: string; }
	interface Group { id: string; name: string; description: string; }
	interface Role { id: string; name: string; }

	let {
		project,
		onClose,
	}: {
		project: Project | null;
		onClose: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	let members = $state<Member[]>([]);
	let membersLoading = $state(false);
	let allUsers = $state<User[]>([]);
	let allGroups = $state<Group[]>([]);
	let allRoles = $state<Role[]>([]);
	let addError = $state('');
	let addSaving = $state(false);
	let userSearchFilter = $state('');
	let pendingAddUser = $state<User | null>(null);
	let pendingRoleId = $state('');
	let accessTab = $state<'users' | 'groups'>('users');
	let pendingAddGroup = $state<Group | null>(null);
	let pendingGroupRoleId = $state('');

	let memberUserIds = $derived(new Set(members.filter(m => m.type !== 'group').map(m => m.user_id)));
	let memberGroupIds = $derived(new Set(members.filter(m => m.type === 'group').map(m => m.group_id)));
	let filteredUsers = $derived(
		allUsers.filter(u => !userSearchFilter || u.name.toLowerCase().includes(userSearchFilter.toLowerCase()))
	);
	let filteredGroups = $derived(
		allGroups.filter(g => !userSearchFilter || g.name.toLowerCase().includes(userSearchFilter.toLowerCase()))
	);

	$effect(() => {
		if (project) {
			membersLoading = true;
			addError = '';
			userSearchFilter = '';
			pendingAddUser = null;
			pendingAddGroup = null;
			pendingRoleId = '';
			pendingGroupRoleId = '';
			accessTab = 'users';
			const p = project;
			Promise.all([
				api.get<Member[]>(`/api/v1/admin/projects/${p.id}/members`, token, projectId),
				api.get<{ items: User[] }>('/api/v1/admin/users?limit=100', token, projectId),
				api.get<Role[]>('/api/v1/admin/roles', token, projectId),
				api.get<Group[]>('/api/v1/admin/groups', token, projectId),
			]).then(([m, u, r, g]) => {
				members = m;
				allUsers = u.items;
				allRoles = r;
				allGroups = g;
				if (allRoles.length > 0) {
					pendingRoleId = allRoles[0].id;
					pendingGroupRoleId = allRoles[0].id;
				}
			}).catch(() => {
				members = [];
			}).finally(() => {
				membersLoading = false;
			});
		}
	});

	async function reloadMembers() {
		if (!project) return;
		try {
			members = await api.get<Member[]>(`/api/v1/admin/projects/${project.id}/members`, token, projectId);
		} catch { members = []; }
	}

	async function assignRole(userId: string, roleId: string) {
		if (!project || !userId || !roleId) return;
		addSaving = true;
		addError = '';
		try {
			await api.post('/api/v1/admin/roles/assign', {
				user_id: userId,
				project_id: project.id,
				role_id: roleId,
			}, token, projectId);
			pendingAddUser = null;
			await reloadMembers();
		} catch (e) {
			addError = e instanceof ApiError ? e.message : '할당 실패';
		} finally {
			addSaving = false;
		}
	}

	async function assignGroupRole(groupId: string, roleId: string) {
		if (!project || !groupId || !roleId) return;
		addSaving = true;
		addError = '';
		try {
			await api.post('/api/v1/admin/roles/assign-group', {
				group_id: groupId,
				project_id: project.id,
				role_id: roleId,
			}, token, projectId);
			pendingAddGroup = null;
			await reloadMembers();
		} catch (e) {
			addError = e instanceof ApiError ? e.message : '그룹 할당 실패';
		} finally {
			addSaving = false;
		}
	}

	async function revokeRole(m: Member) {
		if (!project) return;
		try {
			if (m.type === 'group' && m.group_id) {
				await api.delete(
					`/api/v1/admin/roles/assign-group?group_id=${m.group_id}&project_id=${project.id}&role_id=${m.role_id}`,
					token, projectId,
				);
			} else {
				await api.delete(
					`/api/v1/admin/roles/assign?user_id=${m.user_id}&project_id=${project.id}&role_id=${m.role_id}`,
					token, projectId,
				);
			}
			await reloadMembers();
		} catch {}
	}
</script>

{#if project}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={onClose}
		role="dialog" aria-modal="true" tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && onClose()}
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl w-full max-w-3xl mx-4 shadow-[var(--shadow-restraint)] max-h-[85vh] flex flex-col"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<div class="flex items-center justify-between p-5 border-b border-line">
				<div>
					<h2 class="text-lg font-semibold text-ink-0">접근 권한 관리</h2>
					<p class="text-xs text-ink-3 mt-0.5">프로젝트: {project.name}</p>
				</div>
				<button onclick={onClose} class="text-ink-2 hover:text-ink-0 text-xl">&times;</button>
			</div>

			{#if addError}
				<div class="mx-5 mt-3 bg-red-900/40 border border-red-700 text-red-300 rounded px-3 py-2 text-xs">{addError}</div>
			{/if}

			{#if membersLoading}
				<div class="text-xs text-ink-3 py-8 text-center">로딩 중...</div>
			{:else}
				<div class="flex flex-1 min-h-0">
					<!-- 왼쪽: 전체 사용자/그룹 -->
					<div class="w-1/2 border-r border-line flex flex-col">
						<div class="p-4 border-b border-line">
							<div class="flex gap-1 mb-2">
								<button
									onclick={() => { accessTab = 'users'; userSearchFilter = ''; }}
									class="px-3 py-1 text-xs rounded {accessTab === 'users' ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken text-ink-2 hover:text-ink-0'}"
								>사용자</button>
								<button
									onclick={() => { accessTab = 'groups'; userSearchFilter = ''; }}
									class="px-3 py-1 text-xs rounded {accessTab === 'groups' ? 'bg-action-warm text-ink-0' : 'bg-surface-sunken text-ink-2 hover:text-ink-0'}"
								>그룹</button>
							</div>
							<input
								type="text"
								placeholder="{accessTab === 'users' ? '사용자' : '그룹'} 이름 검색"
								bind:value={userSearchFilter}
								class="w-full bg-surface-sunken border border-line-2 text-ink-0 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
							/>
						</div>
						<div class="overflow-y-auto flex-1">
							{#if accessTab === 'users'}
								{#each filteredUsers as u}
									<div class="flex items-center justify-between px-4 py-2 hover:bg-surface-sunken/50 border-b border-line/30">
										<span class="text-sm text-ink-1">{u.name}</span>
										<button
											onclick={() => { pendingAddUser = u; pendingRoleId = allRoles[0]?.id ?? ''; }}
											class="text-action-warm hover:text-action-warm-hover text-lg font-bold leading-none">+</button>
									</div>
								{/each}
							{:else}
								{#each filteredGroups as g}
									<div class="flex items-center justify-between px-4 py-2 hover:bg-surface-sunken/50 border-b border-line/30">
										<div>
											<span class="text-sm text-ink-1">{g.name}</span>
											{#if memberGroupIds.has(g.id)}<span class="text-xs text-ink-3 ml-1">할당됨</span>{/if}
										</div>
										{#if !memberGroupIds.has(g.id)}
											<button
												onclick={() => { pendingAddGroup = g; pendingGroupRoleId = allRoles[0]?.id ?? ''; }}
												class="text-action-warm hover:text-action-warm-hover text-lg font-bold leading-none">+</button>
										{/if}
									</div>
								{/each}
							{/if}
						</div>
					</div>

					<!-- 오른쪽: 프로젝트 멤버 -->
					<div class="w-1/2 flex flex-col">
						<div class="p-4 border-b border-line">
							<div class="text-xs text-ink-2 uppercase tracking-wide">프로젝트 멤버</div>
						</div>
						<div class="overflow-y-auto flex-1">
							{#if members.length === 0}
								<div class="text-xs text-ink-3 px-4 py-4">멤버가 없습니다</div>
							{:else}
								{#each members as m}
									<div class="flex items-center justify-between px-4 py-2 hover:bg-surface-sunken/50 border-b border-line/30">
										<div>
											<div class="text-sm text-ink-1">{m.user_name}</div>
											<div class="text-xs text-ink-3">{m.role_name}</div>
										</div>
										<button onclick={() => revokeRole(m)} class="text-red-400 hover:text-red-300 text-lg font-bold leading-none">-</button>
									</div>
								{/each}
							{/if}
						</div>
					</div>
				</div>
			{/if}

			<div class="flex justify-end p-4 border-t border-line">
				<button onclick={onClose} class="px-4 py-2 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm font-medium rounded-lg">닫기</button>
			</div>
		</div>
	</div>
{/if}

<!-- 사용자 역할 선택 서브 모달 -->
{#if pendingAddUser}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/70 flex items-center justify-center z-[60]"
		onclick={() => { pendingAddUser = null; }}
		role="dialog" tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-5 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h3 class="text-base font-semibold text-ink-0 mb-3">{pendingAddUser.name} — 역할 선택</h3>
			<select bind:value={pendingRoleId} class="w-full bg-surface-sunken border border-line-2 text-ink-0 text-sm rounded px-3 py-2 focus:outline-none focus:border-action-warm mb-4">
				{#each allRoles as r}
					<option value={r.id}>{r.name}</option>
				{/each}
			</select>
			<div class="flex justify-end gap-3">
				<button onclick={() => { pendingAddUser = null; }} class="px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm rounded-lg">취소</button>
				<button
					onclick={() => pendingAddUser && assignRole(pendingAddUser.id, pendingRoleId)}
					disabled={addSaving || !pendingRoleId}
					class="px-3 py-1.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm rounded-lg disabled:opacity-30"
				>{addSaving ? '추가 중...' : '추가'}</button>
			</div>
		</div>
	</div>
{/if}

<!-- 그룹 역할 선택 서브 모달 -->
{#if pendingAddGroup}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 bg-surface-scrim/70 flex items-center justify-center z-[60]"
		onclick={() => { pendingAddGroup = null; }}
		role="dialog" tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl p-5 w-full max-w-sm mx-4 shadow-[var(--shadow-restraint)]"
			onclick={(e) => e.stopPropagation()}
			role="none"
			onkeydown={(e) => e.stopPropagation()}
		>
			<h3 class="text-base font-semibold text-ink-0 mb-3">[그룹] {pendingAddGroup.name} — 역할 선택</h3>
			<select bind:value={pendingGroupRoleId} class="w-full bg-surface-sunken border border-line-2 text-ink-0 text-sm rounded px-3 py-2 focus:outline-none focus:border-action-warm mb-4">
				{#each allRoles as r}
					<option value={r.id}>{r.name}</option>
				{/each}
			</select>
			<div class="flex justify-end gap-3">
				<button onclick={() => { pendingAddGroup = null; }} class="px-3 py-1.5 bg-surface-selected hover:bg-surface-selected text-ink-0 text-sm rounded-lg">취소</button>
				<button
					onclick={() => pendingAddGroup && assignGroupRole(pendingAddGroup.id, pendingGroupRoleId)}
					disabled={addSaving || !pendingGroupRoleId}
					class="px-3 py-1.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm rounded-lg disabled:opacity-30"
				>{addSaving ? '추가 중...' : '추가'}</button>
			</div>
		</div>
	</div>
{/if}
