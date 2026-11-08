<script lang="ts">
	import { createTableView } from '$lib/utils/tableView.svelte';
	import RegexSearch from '$lib/components/ui/RegexSearch.svelte';
	import TableViewControls from '$lib/components/ui/TableViewControls.svelte';
	import { t as tc } from '$lib/i18n/ns/common';
	import PageShell from '$lib/components/ui/PageShell.svelte';
	import LoadingState from '$lib/components/ui/LoadingState.svelte';
	import { onDestroy, onMount, untrack } from 'svelte';
	import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
	import { derived } from 'svelte/store';
	import { api, ApiError } from '$lib/api/client';
	import type { User } from '$lib/types/common';
	import type { DomainAccountResult } from '$lib/types/auth';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminUsersTable from '$lib/components/admin/users/AdminUsersTable.svelte';
	import AdminUserCreateModal from '$lib/components/admin/users/AdminUserCreateModal.svelte';
	import AdminUserEditModal from '$lib/components/admin/users/AdminUserEditModal.svelte';
	import AdminUserDeleteModal from '$lib/components/admin/users/AdminUserDeleteModal.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';
	import { isTourActive } from '$lib/tutorial/engine';
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
	const unsubscribeCreation = derived([auth, authReady, projectSwitching, logoutInProgress], ([state, ready, switching, loggingOut]) => ({ state, ready, switching, loggingOut })).subscribe(({ state, ready, switching, loggingOut }) => {
		const owner = JSON.stringify([state.sessionId, state.userId, state.identityDomainId, state.domainId, state.projectId, state.isSystemAdmin, ready, switching, loggingOut]);
		if (owner !== creationOwner) { creationOwner = owner; creationRevision++; }
		creationToken = state.token ?? undefined;
		creationProject = state.projectId ?? undefined;
		creationAllowed = !!state.token && !!state.userId && state.isSystemAdmin === true && ready && !switching && !loggingOut;
	});
	let loadError = $state('');
	let activityError = $state('');
	onDestroy(() => { alive = false; loadGeneration += 1; activityGeneration += 1; creationRevision++; unsubscribeCreation(); });

	let allUsers = $state<User[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let showCreate = $state(false);
	let editUser = $state<User | null>(null);
	let deleteSelection = $state<{ user: User; revision: number; domain: string } | null>(null);
	let preparingDelete = $state(false);
	let deleting = $state(false);
	let deletePreparation = 0;
	// Only the user this page just created during a running tour carries the tutorial delete anchor.
	let tourCreatedId = $state<string | null>(null);
	$effect.pre(() => {
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		domainId;
		untrack(() => { creationRevision++; deleteSelection = null; deletePreparation++; preparingDelete = false; tourCreatedId = null; });
	});

	// 검색·정렬·필터 (auto-refresh 갱신 시에도 유지됨)
	let search = $state('');

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
	const tableView = createTableView<User>({ rows: () => allUsers, locale: () => intlLocale(), search: () => search, searchable: row => [row.name, row.email, row.id, row.domain_id].map(value => String(value ?? '')), columns: () => [
		{ key: 'name', label: t('userTable.name'), value: row => row.name },
		{ key: 'email', label: t('userTable.email'), value: row => row.email },
		{ key: 'status', label: t('userTable.status'), value: row => row.enabled, format: (_, row) => t(row.enabled ? 'userTable.enabled' : 'userTable.disabled') },
		{ key: 'id', label: t('userTable.id'), value: row => row.id },
		{ key: 'firstActivity', label: t('userTable.firstActivity'), value: row => row.first_seen ?? row.created_at }
	] });
	// While a tour runs, keep the user it just created on page 1 so the delete step can anchor on it.
	const filteredUsers = $derived.by(() => {
		const rows = tableView.rows;
		const created = tourCreatedId ? rows.find((row) => row.id === tourCreatedId) : undefined;
		return created && isTourActive() ? [created, ...rows.filter((row) => row !== created)] : rows;
	});
	let activitySearch = $state('');
	const activityView = createTableView<ActivityEvent>({ rows: () => activityLog, locale: () => intlLocale(), search: () => activitySearch, columns: () => [
		{ key: 'created', label: tc('table.issued'), value: row => row.created_at },
		{ key: 'user', label: t('userTable.name'), value: row => row.username },
		{ key: 'action', label: t('projectTable.actions'), value: row => row.action },
		{ key: 'resource', label: t('form.name'), value: row => row.resource_name },
		{ key: 'status', label: t('userTable.status'), value: row => row.status }
	] });

	const totalPages = $derived(Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE)));
	const pagedUsers = $derived(
		filteredUsers.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
	);

	// 필터·정렬 변경 시 첫 페이지로 리셋
	$effect(() => {
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		search;
		JSON.stringify(tableView.filters);
		tableView.sort;
		currentPage = 1;
	});
	$effect(() => { if (currentPage > totalPages) currentPage = totalPages; });

	async function loadAll(fresh = false): Promise<boolean> {
		if (!alive) return false;
		const generation = ++loadGeneration;
		const requestToken = token;
		const requestProject = projectId;
		const requestDomain = domainId;
		const boundary = creationRevision;
		const owns = () => alive && generation === loadGeneration && requestToken === token && requestProject === projectId && requestDomain === domainId && boundary === creationRevision;
		loadError = '';
		if (allUsers.length === 0) loading = true;
		else refreshing = true;
		try {
			let marker: string | null = null;
			const collected: User[] = [];
			do {
				let url = domainPath('/api/v1/admin/users?limit=100', requestDomain);
				if (marker) url += `&marker=${encodeURIComponent(marker)}`;
				const res = await api.get<{ items: User[]; next_marker: string | null }>(
					url,
					requestToken,
					requestProject,
					{ refresh: fresh }
				);
				if (!owns()) return false;
				if (res.items.some(user => user.domain_id !== requestDomain)) throw new Error(td('scope.invalid'));
				collected.push(...(res.items ?? []));
				marker = res.next_marker ?? null;
			} while (marker);
			if (!owns()) return false;
			allUsers = collected;
			return true;
		} catch (e) {
			if (owns()) { allUsers = []; loadError = e instanceof ApiError ? e.message : td('users.loadFailed'); }
			return false;
		} finally {
			if (owns()) { loading = false; refreshing = false; }
		}
	}

	async function loadActivity(fresh = false) {
		if (!alive) return;
		const generation = ++activityGeneration;
		const requestToken = token;
		const requestProject = projectId;
		const requestDomain = domainId;
		const boundary = creationRevision;
		const owns = () => alive && generation === activityGeneration && requestToken === token && requestProject === projectId && requestDomain === domainId && boundary === creationRevision;
		activityError = '';
		loadingActivity = true;
		try {
			const data = await api.get<ActivityEvent[]>(
				domainPath('/api/v1/admin/users/activity?limit=10', requestDomain),
				requestToken,
				requestProject,
				{ refresh: fresh }
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
		enabled: boolean;
	}): Promise<string | DomainAccountResult> {
		if (!alive || !creationAllowed) return td('scope.invalid');
		const boundary = creationRevision;
		const target = domainId;
		const owns = () => alive && creationAllowed && boundary === creationRevision && target === domainId;
		try {
			const result = await api.post<DomainAccountResult>(
				'/api/v1/admin/users',
				{ domain_id: target, name: form.name, email: form.email, password: form.password, enabled: form.enabled },
				creationToken,
				creationProject,
				{ replayOnUnauthorized: false }
			);
			if (!owns()) return td('scope.invalid');
			if (isTourActive()) tourCreatedId = result.user_id;
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
	async function openDelete(user: User) {
		if (!alive || !creationAllowed || deleting || preparingDelete || user.id === $auth.userId || user.domain_id !== domainId) return;
		const boundary = creationRevision;
		const targetDomain = domainId;
		const request = ++deletePreparation;
		preparingDelete = true;
		// Every new confirmation rereads native inventory, including after an uncertain write.
		const loaded = await loadAll(true);
		if (!alive || request !== deletePreparation) return;
		preparingDelete = false;
		if (!loaded || !creationAllowed || boundary !== creationRevision || targetDomain !== domainId) return;
		const target = allUsers.find(item => item.id === user.id && item.domain_id === targetDomain);
		if (target) deleteSelection = { user: { ...target }, revision: boundary, domain: targetDomain };
	}

	async function deleteUser(id: string, confirmation: string): Promise<true | { error: string; rereadRequired: boolean }> {
		const selected = deleteSelection;
		const owns = () => alive && creationAllowed && selected !== null && deleteSelection === selected && selected.revision === creationRevision && selected.domain === domainId;
		if (!owns() || !selected || deleting || confirmation !== id || selected.user.id !== id || selected.user.domain_id !== domainId || id === $auth.userId || !allUsers.some(user => user.id === id && user.domain_id === selected.domain)) {
			return { error: td('scope.invalid'), rereadRequired: true };
		}
		deleting = true;
		try {
			await api.delete<void>(domainPath(`/api/v1/admin/users/${encodeURIComponent(id)}`, selected.domain), creationToken, creationProject, { replayOnUnauthorized: false });
			if (!owns()) return { error: td('scope.invalid'), rereadRequired: true };
			if (tourCreatedId === id) tourCreatedId = null;
			if (editUser?.id === id && editUser.domain_id === selected.domain) editUser = null;
			await Promise.all([loadAll(true), loadActivity(true)]);
			return owns() ? true : { error: td('scope.invalid'), rereadRequired: true };
		} catch (e) {
			if (!owns()) return { error: td('scope.invalid'), rereadRequired: true };
			return { error: e instanceof ApiError ? e.message : t('userDelete.failed'), rereadRequired: !(e instanceof ApiError) || e.status <= 0 || e.status >= 500 || e.status === 408 || e.status === 401 };
		} finally {
			deleting = false;
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
		async () => { await Promise.allSettled([loadAll(), loadActivity()]); },
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

{#if creationAllowed}{#key `${creationRevision}:${domainId}`}<AdminUserCreateModal bind:open={showCreate} {domainId} onCreate={create} />{/key}{/if}
<AdminUserEditModal bind:user={editUser} {domainId} onUpdate={update} />
{#each creationAllowed && deleteSelection && deleteSelection.revision === creationRevision && deleteSelection.domain === domainId ? [deleteSelection] : [] as selected (selected)}
	<AdminUserDeleteModal user={selected.user} domainId={selected.domain} {domainName} onDelete={deleteUser} onClose={() => { if (deleteSelection === selected) deleteSelection = null; }} />
{/each}

<PageShell>
	<div data-tour="admin-identity-header">
		<PageHeader breadcrumb={t('userPage.breadcrumb')} title={t('userPage.title')}>
		{#snippet actions()}
			<!-- The route's create/delete tour button owns the invite bubble; this view tour starts on demand only. -->
			<TutorialStartButton tour="admin-identity" compactOnMobile invite={false} />
			<button
				data-tour="admin-users-create-open"
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
		<LoadingState variant="surface" label={t('userPage.loading')} />
	{:else if !loadError}
		<!-- 통계 카드 + 최근 변경 로그 카드 -->
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5" data-tour="admin-identity-overview">
			<span class="sr-only" data-tour="admin-identity-overview-ready">{t('userPage.overviewReady')}</span>
			<!-- 집계 통계 -->
			<div class="md:col-span-2 bg-surface-base border border-line rounded-lg p-4" data-tour="admin-users-summary">
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
				<RegexSearch id="admin-users-activity-search" bind:value={activitySearch} />
				<TableViewControls view={activityView} class="" />
				<p class="text-xs text-ink-2">{tc('table.loadedScope')}</p>
				{#if loadingActivity}
					<p class="text-xs text-ink-2"><LoadingState variant="inline" label={t('userPage.loading')} /></p>
				{:else if activityLog.length === 0}
					<p class="text-xs text-ink-2">{t('userPage.noChanges')}</p>
				{:else}
					<ul class="space-y-1.5">
						{#each activityView.rows.slice(0, 5) as ev (ev.id)}
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
	{/if}

		<!-- 검색 · 정렬 · 필터 바 -->
		<div class="flex flex-wrap gap-2 mb-3" data-tour="admin-identity-filters">
			<RegexSearch id="admin-users-search" bind:value={search} placeholder={t('userPage.searchPlaceholder')} />
		</div>

		<div class="bg-surface-base border border-line rounded-lg p-5" data-tour="admin-identity-list">
				<div data-tour={!loading && !loadError ? 'admin-identity-list-ready' : undefined}>
				{#if !loading && !loadError && !pagedUsers.length}<p class="py-6 text-center text-sm text-ink-2">{tc('table.noMatches')}</p>{/if}
				<AdminUsersTable
					users={pagedUsers}
					view={tableView}
					{refreshing}
					page={currentPage}
					hasPrev={currentPage > 1}
					hasNext={currentPage < totalPages}
					actorId={$auth.userId}
					deleteDisabled={!creationAllowed || deleting || preparingDelete}
					tourDeleteId={tourCreatedId}
					onDelete={openDelete}
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
		</div>
</PageShell>
