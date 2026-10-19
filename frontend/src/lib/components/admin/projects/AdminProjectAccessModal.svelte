<script lang="ts">
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { dialogFocus } from '$lib/utils/dialogFocus';
	import Button from '$lib/components/ui/Button.svelte';
	import Pill from '$lib/components/ui/Pill.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { t as td } from '$lib/i18n/ns/domain-admin';
	import { t as tc } from '$lib/i18n/ns/common';

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
	interface User { id: string; name: string; domain_id: string; }
	interface Group { id: string; name: string; description: string; domain_id: string; }
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
		domainId,
		onClose,
	}: {
		project: Project | null;
		domainId: string;
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

	interface Scope { target: string; domainId: string; token: string | undefined; projectId: string | undefined; }
	let scope: Scope | null = null;
	let membersGeneration = 0;
	function current(request: Scope) {
		return scope === request && project?.id === request.target && project.domain_id === request.domainId
			&& domainId === request.domainId && token === request.token && projectId === request.projectId;
	}
	function path(request: Scope, endpoint: string) {
		return `${endpoint}${endpoint.includes('?') ? '&' : '?'}domain_id=${encodeURIComponent(request.domainId)}`;
	}
	$effect(() => {
		const request: Scope = { target: project?.id ?? '', domainId, token, projectId };
		const targetDomain = project?.domain_id;
		scope = request.target && domainId && targetDomain === domainId ? request : null;
		members = []; allUsers = []; allGroups = []; allRoles = [];
		membersLoading = !!scope;
		addError = scope || !request.target ? '' : td('projects.accessLoadFailed');
		addSaving = false; userSearchFilter = ''; accessTab = 'users';
		detailPrincipal = null; detailError = ''; roleBusy = null; removingKey = null;
		if (scope) {
			void Promise.all([
				api.get<Member[]>(path(request, `/api/v1/admin/projects/${encodeURIComponent(request.target)}/members`), request.token, request.projectId),
				api.get<{ domain_id: string; items: User[] }>(`/api/v1/admin/domains/${encodeURIComponent(request.domainId)}/members`, request.token, request.projectId, { refresh: true }),
				api.get<Role[]>(path(request, '/api/v1/admin/roles'), request.token, request.projectId),
				api.get<Group[]>(path(request, '/api/v1/admin/groups'), request.token, request.projectId),
			]).then(([loadedMembers, users, roles, groups]) => {
				if (!current(request)) return;
				if (users.domain_id !== request.domainId || groups.some((group) => group.domain_id !== request.domainId)) throw new Error('foreign domain');
				members = loadedMembers; allUsers = users.items; allRoles = roles; allGroups = groups;
			}).catch((error) => {
				if (current(request)) addError = error instanceof ApiError ? error.message : td('projects.accessLoadFailed');
			}).finally(() => { if (current(request)) membersLoading = false; });
		}
		return () => { scope = null; membersGeneration += 1; };
	});

	async function reloadMembers(request: Scope) {
		if (!current(request)) return;
		const generation = ++membersGeneration;
		const loaded = await api.get<Member[]>(path(request, `/api/v1/admin/projects/${encodeURIComponent(request.target)}/members`), request.token, request.projectId);
		if (current(request) && generation === membersGeneration) members = loaded;
	}
	function assignRequest(request: Scope, principal: { id: string; type: 'user' | 'group' }, roleId: string) {
		const endpoint = principal.type === 'group' ? '/api/v1/admin/roles/assign-group' : '/api/v1/admin/roles/assign';
		const identity = principal.type === 'group' ? { group_id: principal.id } : { user_id: principal.id };
		return api.post(path(request, endpoint), { ...identity, project_id: request.target, role_id: roleId, domain_id: request.domainId }, request.token, request.projectId);
	}
	function revokeRequest(request: Scope, principal: { id: string; type: 'user' | 'group' }, roleId: string) {
		const endpoint = principal.type === 'group' ? '/api/v1/admin/roles/assign-group' : '/api/v1/admin/roles/assign';
		const params = new URLSearchParams({ project_id: request.target, role_id: roleId });
		params.set(principal.type === 'group' ? 'group_id' : 'user_id', principal.id);
		return api.delete(path(request, `${endpoint}?${params}`), request.token, request.projectId);
	}
	async function addAsReader(target: { id: string; type: 'user' | 'group' }) {
		const request = scope;
		if (!request || !current(request) || !readerRole || addSaving) return;
		const catalog = target.type === 'group' ? allGroups : allUsers;
		if (!catalog.some((item) => item.id === target.id)) return;
		addSaving = true; addError = '';
		try {
			await assignRequest(request, target, readerRole.id);
			if (current(request)) await reloadMembers(request);
		} catch (error) {
			if (current(request)) addError = error instanceof ApiError ? error.message : (target.type === 'group' ? t('projectAccess.addGroupFailed') : t('projectAccess.addMemberFailed'));
		} finally { if (current(request)) addSaving = false; }
	}
	async function toggleRole(role: Role, checked: boolean) {
		const request = scope;
		if (!request || !current(request) || !detailPrincipal || roleBusy) return;
		if (!checked && role.id === readerRole?.id) return;
		const principal = detailPrincipal;
		roleBusy = role.id; detailError = '';
		try {
			if (checked) await assignRequest(request, principal, role.id);
			else await revokeRequest(request, principal, role.id);
			if (current(request)) await reloadMembers(request);
		} catch (error) {
			if (current(request)) detailError = error instanceof ApiError ? error.message : (checked ? t('projectAccess.assignRoleFailed') : t('projectAccess.revokeRoleFailed'));
		} finally { if (current(request)) roleBusy = null; }
	}
	async function removePrincipal(principal: Principal) {
		const request = scope;
		if (!request || !current(request) || removingKey) return;
		removingKey = principal.key; addError = '';
		try {
			for (const role of principal.roles) {
				if (!current(request)) return;
				await revokeRequest(request, principal, role.role_id);
			}
			if (current(request)) await reloadMembers(request);
		} catch (error) {
			if (current(request)) addError = error instanceof ApiError ? error.message : t('projectAccess.removeMemberFailed');
		} finally { if (current(request)) removingKey = null; }
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
					<h2 class="text-lg font-semibold text-ink-0">{t('projectAccess.title')}</h2>
					<p class="text-xs text-ink-2 mt-0.5">{t('projectAccess.projectLabel', { name: project.name })}</p>
				</div>
				<Button variant="ghost" size="icon" ariaLabel={t('projectAccess.closeLabel')} onclick={onClose}>&times;</Button>
			</div>

			{#if addError}
				<Alert tone="danger" class="mx-5 mt-3">{addError}</Alert>
			{/if}
			{#if !membersLoading && allRoles.length > 0 && !readerRole}
				<Alert tone="warning" class="mx-5 mt-3">{t('projectAccess.readerMissing')}</Alert>
			{/if}

			{#if addSaving}<div class="px-5 py-2"><ActivityIndicator size="xs" label={t('projectAccess.addingMember')} /></div>{/if}
			{#if membersLoading}
				<div class="text-xs text-ink-2 py-8 text-center"><ActivityIndicator size="xs" label={t('state.loading')} /></div>
			{:else}
				<div class="flex flex-col md:flex-row flex-1 min-h-0">
					<div class="md:w-1/2 flex flex-col min-h-0 flex-1 md:flex-none border-b md:border-b-0 md:border-r border-line">
						<div class="p-4 border-b border-line">
							<div class="flex gap-1 mb-2">
								<Button variant={accessTab === 'users' ? 'primary' : 'subtle'} size="xs" onclick={() => { accessTab = 'users'; userSearchFilter = ''; }}>{t('projectAccess.tabUsers')}</Button>
								<Button variant={accessTab === 'groups' ? 'primary' : 'subtle'} size="xs" onclick={() => { accessTab = 'groups'; userSearchFilter = ''; }}>{t('projectAccess.tabGroups')}</Button>
							</div>
							<input
								type="text"
								placeholder={accessTab === 'users' ? t('projectAccess.searchUsers') : t('projectAccess.searchGroups')}
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
											{#if memberUserIds.has(user.id)}<span class="text-xs text-ink-2 ml-1">{t('projectAccess.assigned')}</span>{/if}
										</div>
										{#if !memberUserIds.has(user.id)}
											<Button ariaBusy={addSaving} variant="ghost" size="icon" ariaLabel={t('projectAccess.addAsReaderLabel', { name: user.name })} title={t('projectAccess.addAsReaderTitle')} disabled={!readerRole || addSaving} onclick={() => addAsReader({ id: user.id, type: 'user' })}>+</Button>
										{/if}
									</div>
								{/each}
							{:else}
								{#each filteredGroups as group}
									<div class="flex items-center justify-between px-4 py-2 hover:bg-surface-sunken/50 border-b border-line/30">
										<div class="min-w-0">
											<span class="text-sm text-ink-1">{group.name}</span>
											{#if memberGroupIds.has(group.id)}<span class="text-xs text-ink-2 ml-1">{t('projectAccess.assigned')}</span>{/if}
										</div>
										{#if !memberGroupIds.has(group.id)}
											<Button ariaBusy={addSaving} variant="ghost" size="icon" ariaLabel={t('projectAccess.addAsReaderLabel', { name: group.name })} title={t('projectAccess.addAsReaderTitle')} disabled={!readerRole || addSaving} onclick={() => addAsReader({ id: group.id, type: 'group' })}>+</Button>
										{/if}
									</div>
								{/each}
							{/if}
						</div>
					</div>

					<div class="md:w-1/2 flex flex-col min-h-0 flex-1 md:flex-none">
						<div class="p-4 border-b border-line">
							<div class="text-xs text-ink-2 uppercase tracking-wide">{t('projectAccess.membersHeading')}</div>
						</div>
						<div class="overflow-y-auto flex-1">
							{#if principals.length === 0}
								<div class="text-xs text-ink-2 px-4 py-4">{t('projectAccess.noMembers')}</div>
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
											<Button variant="subtle" size="xs" ariaLabel={t('projectAccess.permissionsLabel', { name: principal.name })} onclick={() => { detailPrincipal = principal; detailError = ''; }}>{t('projectAccess.permissions')}</Button>
											<Button ariaBusy={removingKey === principal.key} variant="danger-outline" size="xs" ariaLabel={t('projectAccess.removeLabel', { name: principal.name })} disabled={removingKey !== null} onclick={() => removePrincipal(principal)}>{#if removingKey === principal.key}<span class="inline-flex items-center gap-2" role="status"><ActivityIndicator size="xs" />{t('state.removing')}</span>{:else}{t('actions.remove')}{/if}</Button>
										</div>
									</div>
								{/each}
							{/if}
						</div>
					</div>
				</div>
			{/if}

			<div class="flex justify-end p-4 border-t border-line">
				<Button variant="secondary" size="sm" onclick={onClose}>{tc('actions.close')}</Button>
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
			<h3 id="project-access-detail-title" class="text-base font-semibold text-ink-0 mb-1">{t('projectAccess.detailTitle', { name: detailPrincipal.name })}</h3>
			<p class="text-xs text-ink-2 mb-3">{t('projectAccess.detailHelp')}</p>
			{#if detailError}<Alert tone="danger" class="mb-3">{detailError}</Alert>{/if}
			<ul class="overflow-y-auto flex-1 min-h-0 divide-y divide-line/30" aria-label={t('projectAccess.roleListLabel')}>
				{#each orderedRoles as role (role.id)}
					{@const assigned = detailRoleIds.has(role.id)}
					{@const locked = assigned && role.id === readerRole?.id}
					<li class="flex items-center justify-between py-2">
						<label class="flex items-center gap-2 text-sm text-ink-1 cursor-pointer">
							<input type="checkbox" class="rounded border-line-2 bg-surface-sunken" checked={assigned} disabled={locked || roleBusy !== null} onchange={(event) => toggleRole(role, event.currentTarget.checked)} />
							<span>{role.name}</span>
						</label>
						{#if roleBusy === role.id}<ActivityIndicator size="xs" label={t('state.saving')} />{:else if locked}<span class="text-xs text-ink-2">{t('projectAccess.defaultRole')}</span>{/if}
					</li>
				{/each}
			</ul>
			<div class="flex justify-end mt-4">
				<Button variant="secondary" size="sm" onclick={() => { detailPrincipal = null; }}>{tc('actions.close')}</Button>
			</div>
		</div>
	</div>
{/if}
