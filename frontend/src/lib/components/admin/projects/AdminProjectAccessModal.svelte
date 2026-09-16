<script lang="ts">
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';

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
	interface Principal {
		key: string;
		id: string;
		name: string;
		type: 'user' | 'group';
		roles: { role_id: string; role_name: string }[];
	}

	let {
		project,
		onClose,
	}: {
		project: Project | null;
		onClose: () => void;
	} = $props();

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);
	const ROLE_ORDER = ['reader', 'member', 'admin'];

	let members = $state<Member[]>([]);
	let membersLoading = $state(false);
	let allUsers = $state<User[]>([]);
	let allGroups = $state<Group[]>([]);
	let allRoles = $state<Role[]>([]);
	let addError = $state('');
	let addSaving = $state(false);
	let userSearchFilter = $state('');
	let accessTab = $state<'users' | 'groups'>('users');
	let detailPrincipal = $state<Principal | null>(null);
	let detailError = $state('');
	let roleBusy = $state<string | null>(null);
	let removingKey = $state<string | null>(null);

	let readerRole = $derived(allRoles.find((role) => role.name.toLowerCase() === 'reader') ?? null);
	let orderedRoles = $derived(
		[...allRoles].sort((a, b) => {
			const ai = ROLE_ORDER.indexOf(a.name.toLowerCase());
			const bi = ROLE_ORDER.indexOf(b.name.toLowerCase());
			if (ai !== bi) return (ai === -1 ? ROLE_ORDER.length : ai) - (bi === -1 ? ROLE_ORDER.length : bi);
			return a.name.localeCompare(b.name);
		}),
	);
	let principals = $derived.by(() => {
		const map = new Map<string, Principal>();
		for (const member of members) {
			const type = member.type === 'group' ? 'group' : 'user';
			const principal = map.get(member.user_id) ?? {
				key: member.user_id,
				id: type === 'group' ? (member.group_id ?? member.user_id) : member.user_id,
				name: member.user_name,
				type,
				roles: [],
			};
			principal.roles.push({ role_id: member.role_id, role_name: member.role_name });
			map.set(member.user_id, principal);
		}
		return [...map.values()];
	});
	let detailRoleIds = $derived(new Set(principals.find((principal) => principal.key === detailPrincipal?.key)?.roles.map((role) => role.role_id) ?? []));
	let memberUserIds = $derived(new Set(members.filter((member) => member.type !== 'group').map((member) => member.user_id)));
	let memberGroupIds = $derived(new Set(members.filter((member) => member.type === 'group').map((member) => member.group_id)));
	let filteredUsers = $derived(
		allUsers.filter((user) => !userSearchFilter || user.name.toLowerCase().includes(userSearchFilter.toLowerCase())),
	);
	let filteredGroups = $derived(
		allGroups.filter((group) => !userSearchFilter || group.name.toLowerCase().includes(userSearchFilter.toLowerCase())),
	);

	$effect(() => {
		if (!project) return;
		membersLoading = true;
		addError = '';
		userSearchFilter = '';
		accessTab = 'users';
		detailPrincipal = null;
		detailError = '';
		roleBusy = null;
		removingKey = null;
		const currentProject = project;
		Promise.all([
			api.get<Member[]>(`/api/v1/admin/projects/${currentProject.id}/members`, token, projectId),
			api.get<{ items: User[] }>('/api/v1/admin/users?limit=100', token, projectId),
			api.get<Role[]>('/api/v1/admin/roles', token, projectId),
			api.get<Group[]>('/api/v1/admin/groups', token, projectId),
		])
			.then(([loadedMembers, users, roles, groups]) => {
				members = loadedMembers;
				allUsers = users.items;
				allRoles = roles;
				allGroups = groups;
			})
			.catch(() => {
				members = [];
			})
			.finally(() => {
				membersLoading = false;
			});
	});

	async function reloadMembers() {
		if (!project) return;
		try {
			members = await api.get<Member[]>(`/api/v1/admin/projects/${project.id}/members`, token, projectId);
		} catch {
			members = [];
		}
	}

	function assignRequest(principal: { id: string; type: 'user' | 'group' }, roleId: string) {
		if (!project) return Promise.resolve();
		return principal.type === 'group'
			? api.post('/api/v1/admin/roles/assign-group', { group_id: principal.id, project_id: project.id, role_id: roleId }, token, projectId)
			: api.post('/api/v1/admin/roles/assign', { user_id: principal.id, project_id: project.id, role_id: roleId }, token, projectId);
	}

	function revokeRequest(principal: { id: string; type: 'user' | 'group' }, roleId: string) {
		if (!project) return Promise.resolve();
		return principal.type === 'group'
			? api.delete(`/api/v1/admin/roles/assign-group?group_id=${principal.id}&project_id=${project.id}&role_id=${roleId}`, token, projectId)
			: api.delete(`/api/v1/admin/roles/assign?user_id=${principal.id}&project_id=${project.id}&role_id=${roleId}`, token, projectId);
	}

	async function addAsReader(target: { id: string; type: 'user' | 'group' }) {
		if (!project || !readerRole || addSaving) return;
		addSaving = true;
		addError = '';
		try {
			await assignRequest(target, readerRole.id);
			await reloadMembers();
		} catch (error) {
			addError = error instanceof ApiError ? error.message : (target.type === 'group' ? '그룹 멤버 추가 실패' : '멤버 추가 실패');
		} finally {
			addSaving = false;
		}
	}

	async function toggleRole(role: Role, checked: boolean) {
		if (!detailPrincipal || roleBusy) return;
		if (!checked && role.id === readerRole?.id) return;
		roleBusy = role.id;
		detailError = '';
		try {
			if (checked) await assignRequest(detailPrincipal, role.id);
			else await revokeRequest(detailPrincipal, role.id);
			await reloadMembers();
		} catch (error) {
			detailError = error instanceof ApiError ? error.message : (checked ? '역할 할당 실패' : '역할 회수 실패');
		} finally {
			roleBusy = null;
		}
	}

	async function removePrincipal(principal: Principal) {
		if (!project || removingKey) return;
		removingKey = principal.key;
		addError = '';
		try {
			for (const role of principal.roles) {
				await revokeRequest(principal, role.role_id);
			}
		} catch (error) {
			addError = error instanceof ApiError ? error.message : '멤버 제거 실패';
		} finally {
			await reloadMembers();
			removingKey = null;
		}
	}
</script>

{#if project}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: onClose }}
		class="fixed inset-0 bg-surface-scrim/60 flex items-center justify-center z-50"
		onclick={onClose}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<div
			class="bg-surface-base border border-line-2 rounded-xl w-full max-w-3xl mx-4 shadow-[var(--shadow-restraint)] max-h-[85vh] flex flex-col"
			onclick={(event) => event.stopPropagation()}
			role="none"
		>
			<div class="flex items-center justify-between p-5 border-b border-line">
				<div>
					<h2 class="text-lg font-semibold text-ink-0">접근 권한 관리</h2>
					<p class="text-xs text-ink-2 mt-0.5">프로젝트: {project.name}</p>
				</div>
				<Button variant="ghost" size="icon" ariaLabel="접근 권한 관리 닫기" onclick={onClose}>&times;</Button>
			</div>

			{#if addError}
				<Alert tone="danger" class="mx-5 mt-3">{addError}</Alert>
			{/if}
			{#if !membersLoading && allRoles.length > 0 && !readerRole}
				<Alert tone="warning" class="mx-5 mt-3">reader 역할을 찾을 수 없어 멤버를 추가할 수 없습니다. Keystone 역할 목록을 확인하세요.</Alert>
			{/if}

			{#if membersLoading}
				<div class="text-xs text-ink-2 py-8 text-center">로딩 중...</div>
			{:else}
				<div class="flex flex-col md:flex-row flex-1 min-h-0">
					<div class="md:w-1/2 flex flex-col min-h-0 flex-1 md:flex-none border-b md:border-b-0 md:border-r border-line">
						<div class="p-4 border-b border-line">
							<div class="flex gap-1 mb-2">
								<Button variant={accessTab === 'users' ? 'primary' : 'subtle'} size="xs" onclick={() => { accessTab = 'users'; userSearchFilter = ''; }}>사용자</Button>
								<Button variant={accessTab === 'groups' ? 'primary' : 'subtle'} size="xs" onclick={() => { accessTab = 'groups'; userSearchFilter = ''; }}>그룹</Button>
							</div>
							<input
								type="text"
								placeholder={accessTab === 'users' ? '사용자 이름 검색' : '그룹 이름 검색'}
								bind:value={userSearchFilter}
								class="w-full bg-surface-sunken border border-line-2 text-ink-0 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-action-warm"
							/>
						</div>
						<div class="overflow-y-auto flex-1">
							{#if accessTab === 'users'}
								{#each filteredUsers as user}
									<div class="flex items-center justify-between px-4 py-2 hover:bg-surface-sunken/50 border-b border-line/30">
										<div class="min-w-0">
											<span class="text-sm text-ink-1">{user.name}</span>
											{#if memberUserIds.has(user.id)}<span class="text-xs text-ink-2 ml-1">할당됨</span>{/if}
										</div>
										{#if !memberUserIds.has(user.id)}
											<Button variant="ghost" size="icon" ariaLabel={`${user.name} reader로 추가`} title="reader 역할로 추가" disabled={!readerRole || addSaving} onclick={() => addAsReader({ id: user.id, type: 'user' })}>+</Button>
										{/if}
									</div>
								{/each}
							{:else}
								{#each filteredGroups as group}
									<div class="flex items-center justify-between px-4 py-2 hover:bg-surface-sunken/50 border-b border-line/30">
										<div class="min-w-0">
											<span class="text-sm text-ink-1">{group.name}</span>
											{#if memberGroupIds.has(group.id)}<span class="text-xs text-ink-2 ml-1">할당됨</span>{/if}
										</div>
										{#if !memberGroupIds.has(group.id)}
											<Button variant="ghost" size="icon" ariaLabel={`${group.name} reader로 추가`} title="reader 역할로 추가" disabled={!readerRole || addSaving} onclick={() => addAsReader({ id: group.id, type: 'group' })}>+</Button>
										{/if}
									</div>
								{/each}
							{/if}
						</div>
					</div>

					<div class="md:w-1/2 flex flex-col min-h-0 flex-1 md:flex-none">
						<div class="p-4 border-b border-line">
							<div class="text-xs text-ink-2 uppercase tracking-wide">프로젝트 멤버</div>
						</div>
						<div class="overflow-y-auto flex-1">
							{#if principals.length === 0}
								<div class="text-xs text-ink-2 px-4 py-4">멤버가 없습니다</div>
							{:else}
								{#each principals as principal (principal.key)}
									<div class="flex items-start justify-between gap-3 px-4 py-2 border-b border-line/30">
										<div class="min-w-0">
											<div class="text-sm text-ink-1 truncate">{principal.name}</div>
											<div class="mt-1 flex flex-wrap gap-1">
												{#each principal.roles as role (role.role_id)}
													<Pill tone={role.role_name.toLowerCase() === 'admin' ? 'admin-tone' : 'neutral'} size="xs">{role.role_name}</Pill>
												{/each}
											</div>
										</div>
										<div class="flex shrink-0 items-center gap-1">
											<Button variant="subtle" size="xs" ariaLabel={`${principal.name} 권한`} onclick={() => { detailPrincipal = principal; detailError = ''; }}>권한</Button>
											<Button variant="danger-outline" size="xs" ariaLabel={`${principal.name} 제거`} disabled={removingKey !== null} onclick={() => removePrincipal(principal)}>{removingKey === principal.key ? '제거 중...' : '제거'}</Button>
										</div>
									</div>
								{/each}
							{/if}
						</div>
					</div>
				</div>
			{/if}

			<div class="flex justify-end p-4 border-t border-line">
				<Button variant="secondary" size="sm" onclick={onClose}>닫기</Button>
			</div>
		</div>
	</div>
{/if}

{#if detailPrincipal}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:dialogFocus={{ enabled: true, onEscape: () => { detailPrincipal = null; } }}
		class="fixed inset-0 bg-surface-scrim/70 flex items-center justify-center z-[60]"
		onclick={() => { detailPrincipal = null; }}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
		aria-labelledby="project-access-detail-title"
	>
		<div class="bg-surface-base border border-line-2 rounded-xl p-5 w-full max-w-sm mx-4 max-h-[85vh] flex flex-col shadow-[var(--shadow-restraint)]" onclick={(event) => event.stopPropagation()} role="none">
			<h3 id="project-access-detail-title" class="text-base font-semibold text-ink-0 mb-1">{detailPrincipal.name} — 세부 권한</h3>
			<p class="text-xs text-ink-2 mb-3">체크하면 즉시 할당되고, 해제하면 즉시 회수됩니다. reader는 기본 역할이며 멤버 제거로만 해제됩니다.</p>
			{#if detailError}<Alert tone="danger" class="mb-3">{detailError}</Alert>{/if}
			<ul class="overflow-y-auto flex-1 min-h-0 divide-y divide-line/30" aria-label="역할 목록">
				{#each orderedRoles as role (role.id)}
					{@const assigned = detailRoleIds.has(role.id)}
					{@const locked = assigned && role.id === readerRole?.id}
					<li class="flex items-center justify-between py-2">
						<label class="flex items-center gap-2 text-sm text-ink-1 cursor-pointer">
							<input type="checkbox" class="rounded border-line-2 bg-surface-sunken" checked={assigned} disabled={locked || roleBusy !== null} onchange={(event) => toggleRole(role, event.currentTarget.checked)} />
							<span>{role.name}</span>
						</label>
						{#if locked}<span class="text-xs text-ink-2">기본 역할</span>{:else if roleBusy === role.id}<span class="text-xs text-ink-2">저장 중...</span>{/if}
					</li>
				{/each}
			</ul>
			<div class="flex justify-end mt-4">
				<Button variant="secondary" size="sm" onclick={() => { detailPrincipal = null; }}>닫기</Button>
			</div>
		</div>
	</div>
{/if}
