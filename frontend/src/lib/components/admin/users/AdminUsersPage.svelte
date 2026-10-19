<script lang="ts">
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import ActivityIndicator from '$lib/components/ui/ActivityIndicator.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { auth, authReady, projectSwitching } from '$lib/stores/auth';
	import { derived } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import type { User } from '$lib/types/common';
	import type { DomainAccountResult } from '$lib/types/auth';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminUsersTable from '$lib/components/admin/users/AdminUsersTable.svelte';
	import AdminUserCreateModal from '$lib/components/admin/users/AdminUserCreateModal.svelte';
	import AdminUserEditModal from '$lib/components/admin/users/AdminUserEditModal.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import { t } from '$lib/i18n/ns/admin-identity';
	import { intlLocale } from '$lib/i18n/runtime.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import { domainPath } from '$lib/api/domains';
	import { t as td } from '$lib/i18n/ns/domain-admin';
	let { domainId, domainName }: { domainId: string; domainName: string } = $props();
	let alive = true;
	let loadGeneration = 0;
	let activityGeneration = 0;
	let creationRevision = $state(0);
	let creationOwner = '';
	let creationToken: string | undefined;
	let creationProject: string | undefined;
	let creationAllowed = $state(false);
	const unsubscribeCreation = derived([auth, authReady, projectSwitching], ([state, ready, switching]) => ({ state, ready, switching })).subscribe(({ state, ready, switching }) => {
		const owner = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, ready, switching]);
		if (owner !== creationOwner) { creationOwner = owner; creationRevision++; }
		creationToken = state.token ?? undefined;
		creationProject = state.projectId ?? undefined;
		creationAllowed = !!state.token && !!state.userId && state.isSystemAdmin === true && ready && !switching;
	});
	let loadError = $state('');
	let activityError = $state('');
	onDestroy(() => { alive = false; loadGeneration += 1; activityGeneration += 1; creationRevision++; unsubscribeCreation(); });

	let allUsers = $state<User[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let showCreate = $state(false);
	let editUser = $state<User | null>(null);

	// 검색·정렬·필터 (auto-refresh 갱신 시에도 유지됨)
	let search = $state('');
	let sortBy = $state<'name' | 'first_seen'>('name');
	let sortDir = $state<'asc' | 'desc'>('asc');
	let filterStatus = $state<'all' | 'enabled' | 'disabled'>('all');

	// 클라이언트 페이지네이션
	let currentPage = $state(1);
	const PAGE_SIZE = 20;

	// 활동 로그 카드
	interface ActivityEvent {
		id: number;
		created_at: string;
		username: string;
		action: string;
		resource_name: string | null;
		status: string;
	}
	let activityLog = $state<ActivityEvent[]>([]);
	let loadingActivity = $state(false);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	// 집계 통계 (client-side, 전체 로드 데이터 재사용)
	const stats = $derived({
		total: allUsers.length,
		enabled: allUsers.filter((u) => u.enabled).length,
		disabled: allUsers.filter((u) => !u.enabled).length
	});

	// 검색 + 필터 + 정렬
	const filteredUsers = $derived.by(() => {
		let list = allUsers;
		if (search.trim()) {
			const q = search.trim().toLowerCase();
			list = list.filter(
				(u) => u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)
			);
		}
		if (filterStatus !== 'all') {
			list = list.filter((u) => (filterStatus === 'enabled' ? u.enabled : !u.enabled));
		}
		list = [...list].sort((a, b) => {
			let av: string, bv: string;
			if (sortBy === 'name') {
				av = a.name.toLowerCase();
				bv = b.name.toLowerCase();
			} else {
				av = a.first_seen ?? '';
				bv = b.first_seen ?? '';
			}
			return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
		});
		return list;
	});

	const totalPages = $derived(Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE)));
	const pagedUsers = $derived(
		filteredUsers.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
	);

	// 필터·정렬 변경 시 첫 페이지로 리셋
	$effect(() => {
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		search;
		filterStatus;
		sortBy;
		sortDir;
		currentPage = 1;
	});

	async function loadAll() {
		if (!alive) return;
		const generation = ++loadGeneration;
		const requestToken = token;
		const requestProject = projectId;
		const owns = () => alive && generation === loadGeneration && requestToken === token && requestProject === projectId;
		loadError = '';
		if (allUsers.length === 0) loading = true;
		else refreshing = true;
		try {
			let marker: string | null = null;
			const collected: User[] = [];
			do {
				let url = domainPath('/api/v1/admin/users?limit=100', domainId);
				if (marker) url += `&marker=${encodeURIComponent(marker)}`;
				const res = await api.get<{ items: User[]; next_marker: string | null }>(
					url,
					requestToken,
					requestProject
				);
				if (!owns()) return;
				if (res.items.some(user => user.domain_id !== domainId)) throw new Error(td('scope.invalid'));
				collected.push(...(res.items ?? []));
				marker = res.next_marker ?? null;
			} while (marker);
			if (owns()) allUsers = collected;
		} catch (e) {
			if (owns()) { allUsers = []; loadError = e instanceof ApiError ? e.message : td('users.loadFailed'); }
		} finally {
			if (owns()) { loading = false; refreshing = false; }
		}
	}

	async function loadActivity() {
		if (!alive) return;
		const generation = ++activityGeneration;
		const requestToken = token;
		const requestProject = projectId;
		const owns = () => alive && generation === activityGeneration && requestToken === token && requestProject === projectId;
		activityError = '';
		loadingActivity = true;
		try {
			const data = await api.get<ActivityEvent[]>(
				domainPath('/api/v1/admin/users/activity?limit=10', domainId),
				requestToken,
				requestProject
			);
			if (owns()) activityLog = Array.isArray(data) ? data : [];
		} catch (e) {
			if (owns()) { activityLog = []; activityError = e instanceof ApiError ? e.message : td('users.activityFailed'); }
		} finally {
			if (owns()) loadingActivity = false;
		}
	}

	async function create(form: {
		name: string;
		email: string;
		password: string;
		personal_domain_name: string;
		enabled: boolean;
	}): Promise<string | Pick<DomainAccountResult, 'identity_domain_id' | 'identity_domain_name'>> {
		if (!alive || !creationAllowed || !form.personal_domain_name.trim()) return td('scope.invalid');
		const boundary = creationRevision;
		const target = domainId;
		const owns = () => alive && creationAllowed && boundary === creationRevision && target === domainId;
		try {
			const result = await api.post<Pick<DomainAccountResult, 'identity_domain_id' | 'identity_domain_name'>>(
				'/api/v1/admin/users',
				{ domain_id: target, name: form.name, email: form.email, password: form.password, personal_domain_name: form.personal_domain_name, enabled: form.enabled },
				creationToken,
				creationProject,
				{ replayOnUnauthorized: false }
			);
			if (!owns()) return td('scope.invalid');
			await loadAll();
			return owns() ? result : td('scope.invalid');
		} catch (e) {
			if (!owns()) return td('scope.invalid');
			return e instanceof ApiError ? e.message : t('userPage.createFailed');
		}
	}

	async function update(
		id: string,
		form: { name: string; email: string; password: string; enabled: boolean }
	): Promise<string | true> {
		if (!alive || !allUsers.some(user => user.id === id && user.domain_id === domainId)) return td('scope.invalid');
		try {
			await api.patch(
				domainPath(`/api/v1/admin/users/${encodeURIComponent(id)}`, domainId),
				{
					name: form.name,
					email: form.email || null,
					enabled: form.enabled,
					...(form.password ? { password: form.password } : {})
				},
				token,
				projectId
			);
			await loadAll();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : t('userPage.updateFailed');
		}
	}

	function formatActivityTime(iso: string): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleString(intlLocale(), {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	const ar = createAutoRefresh(
		() => {
			loadAll();
			loadActivity();
		},
		{
			storageKey: 'admin-users',
			invokeOnMount: false,
			defaultActive: true,
			defaultInterval: 60,
			intervalOptions: [30, 60]
		}
	);

	onMount(() => {
		loadAll();
		loadActivity();
	});
</script>

{#if creationAllowed}{#key `${creationRevision}:${domainId}`}<AdminUserCreateModal bind:open={showCreate} {domainId} {domainName} onCreate={create} />{/key}{/if}
<AdminUserEditModal bind:user={editUser} {domainId} onUpdate={update} />

<PageShell>
	<div data-tour="admin-identity-header">
		<PageHeader breadcrumb={t('userPage.breadcrumb')} title={t('userPage.title')}>
		{#snippet actions()}
			<TutorialStartButton tour="admin-identity" compactOnMobile />
			<button
				onclick={() => {
					showCreate = true;
				}}
				disabled={!creationAllowed}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
				>{t('userPage.create')}</button
			>
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={() => {
					loadAll();
					loadActivity();
				}}
			/>
		{/snippet}
	</PageHeader>
	</div>
	{#if loadError}<Alert class="mb-4">{loadError}</Alert>{/if}
	{#if activityError}<Alert class="mb-4">{activityError}</Alert>{/if}

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if !loadError}
		<!-- 통계 카드 + 최근 변경 로그 카드 -->
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5" data-tour="admin-identity-overview">
			<span class="sr-only" data-tour="admin-identity-overview-ready">{t('userPage.overviewReady')}</span>
			<!-- 집계 통계 -->
			<div class="md:col-span-2 bg-surface-base border border-line rounded-lg p-4">
				<p class="text-xs font-semibold text-ink-2 mb-3">{t('userPage.overviewTitle')}</p>
				<div class="flex gap-8">
					<div class="text-center">
						<div class="text-2xl font-bold text-ink-0">{stats.total}</div>
						<div class="text-xs text-ink-2 mt-0.5">{t('userPage.total')}</div>
					</div>
					<div class="text-center">
						<div class="text-2xl font-bold text-[var(--color-state-success-text)]">{stats.enabled}</div>
						<div class="text-xs text-ink-2 mt-0.5">{t('userPage.enabled')}</div>
					</div>
					<div class="text-center">
						<div class="text-2xl font-bold text-[var(--color-state-danger-text)]">{stats.disabled}</div>
						<div class="text-xs text-ink-2 mt-0.5">{t('userPage.disabled')}</div>
					</div>
				</div>
			</div>

			<!-- 최근 변경 로그 -->
			<div class="bg-surface-base border border-line rounded-lg p-4">
				<p class="text-xs font-semibold text-ink-2 mb-2">{t('userPage.recentChanges')}</p>
				{#if loadingActivity}
					<p class="text-xs text-ink-2"><ActivityIndicator size="xs" label={t('userPage.loading')} /></p>
				{:else if activityLog.length === 0}
					<p class="text-xs text-ink-2">{t('userPage.noChanges')}</p>
				{:else}
					<ul class="space-y-1.5">
						{#each activityLog.slice(0, 5) as ev (ev.id)}
							<li class="text-xs text-ink-2 flex justify-between gap-2">
								<span class="truncate"
									><span class="text-ink-2">{ev.username}</span>
									{ev.action}</span
								>
								<span class="text-ink-2 shrink-0">{formatActivityTime(ev.created_at)}</span>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</div>

		<!-- 검색 · 정렬 · 필터 바 -->
		<div class="flex flex-wrap gap-2 mb-3" data-tour="admin-identity-filters">
			<input
				bind:value={search}
				type="text"
				placeholder={t('userPage.searchPlaceholder')}
				class="flex-1 min-w-[180px] bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
			/>
			<select
				bind:value={filterStatus}
				class="bg-surface-sunken border border-line-2 rounded-lg px-2 py-1.5 text-sm text-ink-2 focus:outline-none focus-visible:shadow-[var(--focus-ring)]"
				data-tour="admin-identity-status-filter"
			>
				<option value="all">{t('userPage.allStatuses')}</option>
				<option value="enabled">{t('userPage.enabledOnly')}</option>
				<option value="disabled">{t('userPage.disabledOnly')}</option>
			</select>
			<select
				bind:value={sortBy}
				class="bg-surface-sunken border border-line-2 rounded-lg px-2 py-1.5 text-sm text-ink-2 focus:outline-none focus-visible:shadow-[var(--focus-ring)]"
			>
				<option value="name">{t('userPage.sortName')}</option>
				<option value="first_seen">{t('userPage.sortFirstActivity')}</option>
			</select>
			<button
				onclick={() => {
					sortDir = sortDir === 'asc' ? 'desc' : 'asc';
				}}
				class="px-3 py-1.5 bg-surface-sunken border border-line-2 rounded-lg text-sm text-ink-2 hover:bg-surface-selected transition-colors"
			>{sortDir === 'asc' ? t('userPage.ascending') : t('userPage.descending')}</button>
		</div>

		<div class="bg-surface-base border border-line rounded-lg p-5" data-tour="admin-identity-list">
			{#if pagedUsers.length === 0}
				<p class="text-xs text-ink-2 text-center py-6" data-tour="admin-identity-list-ready">{t('userPage.noResults')}</p>
			{:else}
				<div data-tour="admin-identity-list-ready">
				<AdminUsersTable
					users={pagedUsers}
					{refreshing}
					page={currentPage}
					hasPrev={currentPage > 1}
					hasNext={currentPage < totalPages}
					onEdit={(u) => {
						editUser = u;
					}}
					onPrev={() => {
						currentPage = Math.max(1, currentPage - 1);
					}}
					onNext={() => {
						currentPage = Math.min(totalPages, currentPage + 1);
					}}
				/>
				</div>
			{/if}
		</div>
	{/if}
</PageShell>
