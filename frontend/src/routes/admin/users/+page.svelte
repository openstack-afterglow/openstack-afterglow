<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { User } from '$lib/types/common';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import AdminUsersTable from '$lib/components/admin/users/AdminUsersTable.svelte';
	import AdminUserCreateModal from '$lib/components/admin/users/AdminUserCreateModal.svelte';
	import AdminUserEditModal from '$lib/components/admin/users/AdminUserEditModal.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';

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
		if (allUsers.length === 0) loading = true;
		else refreshing = true;
		try {
			let marker: string | null = null;
			const collected: User[] = [];
			do {
				let url = '/api/v1/admin/users?limit=100';
				if (marker) url += `&marker=${marker}`;
				const res = await api.get<{ items: User[]; next_marker: string | null }>(
					url,
					token,
					projectId
				);
				collected.push(...(res.items ?? []));
				marker = res.next_marker ?? null;
			} while (marker);
			allUsers = collected;
		} catch {
			allUsers = [];
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function loadActivity() {
		loadingActivity = true;
		try {
			const data = await api.get<ActivityEvent[]>(
				'/api/v1/admin/users/activity?limit=10',
				token,
				projectId
			);
			activityLog = Array.isArray(data) ? data : [];
		} catch {
			activityLog = [];
		} finally {
			loadingActivity = false;
		}
	}

	async function create(form: {
		name: string;
		email: string;
		password: string;
		enabled: boolean;
	}): Promise<string | true> {
		try {
			await api.post(
				'/api/v1/admin/users',
				{ name: form.name, email: form.email || null, password: form.password || null, enabled: form.enabled },
				token,
				projectId
			);
			await loadAll();
			return true;
		} catch (e) {
			return e instanceof ApiError ? e.message : '생성 실패';
		}
	}

	async function update(
		id: string,
		form: { name: string; email: string; password: string; enabled: boolean }
	): Promise<string | true> {
		try {
			await api.patch(
				`/api/v1/admin/users/${id}`,
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
			return e instanceof ApiError ? e.message : '수정 실패';
		}
	}

	function formatActivityTime(iso: string): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleString('ko-KR', {
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

<AdminUserCreateModal bind:open={showCreate} onCreate={create} />
<AdminUserEditModal bind:user={editUser} onUpdate={update} />

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<div data-tour="admin-identity-header">
	<PageHeader breadcrumb="IDENTITY / USERS" title="사용자">
		{#snippet actions()}
			<TutorialStartButton tour="admin-identity" compactOnMobile />
			<button
				onclick={() => {
					showCreate = true;
				}}
				class="px-4 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg"
				>+ 생성</button
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

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else}
		<!-- 통계 카드 + 최근 변경 로그 카드 -->
		<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5" data-tour="admin-identity-overview">
			<span class="sr-only" data-tour="admin-identity-overview-ready">사용자 현황 준비됨</span>
			<!-- 집계 통계 -->
			<div class="md:col-span-2 bg-surface-base border border-line rounded-lg p-4">
				<p class="text-xs font-semibold text-ink-2 mb-3">사용자 현황</p>
				<div class="flex gap-8">
					<div class="text-center">
						<div class="text-2xl font-bold text-ink-0">{stats.total}</div>
						<div class="text-xs text-ink-3 mt-0.5">전체</div>
					</div>
					<div class="text-center">
						<div class="text-2xl font-bold text-green-400">{stats.enabled}</div>
						<div class="text-xs text-ink-3 mt-0.5">활성</div>
					</div>
					<div class="text-center">
						<div class="text-2xl font-bold text-red-400">{stats.disabled}</div>
						<div class="text-xs text-ink-3 mt-0.5">비활성</div>
					</div>
				</div>
			</div>

			<!-- 최근 변경 로그 -->
			<div class="bg-surface-base border border-line rounded-lg p-4">
				<p class="text-xs font-semibold text-ink-2 mb-2">최근 사용자 변경</p>
				{#if loadingActivity}
					<p class="text-xs text-ink-3">로딩...</p>
				{:else if activityLog.length === 0}
					<p class="text-xs text-ink-3">변경 내역 없음</p>
				{:else}
					<ul class="space-y-1.5">
						{#each activityLog.slice(0, 5) as ev (ev.id)}
							<li class="text-xs text-ink-2 flex justify-between gap-2">
								<span class="truncate"
									><span class="text-ink-2">{ev.username}</span>
									{ev.action}</span
								>
								<span class="text-ink-3 shrink-0">{formatActivityTime(ev.created_at)}</span>
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
				placeholder="이름 또는 이메일 검색..."
				class="flex-1 min-w-[180px] bg-surface-sunken border border-line-2 rounded-lg px-3 py-1.5 text-sm text-ink-0 placeholder-ink-3 focus:outline-none focus:border-action-warm"
			/>
			<select
				bind:value={filterStatus}
				class="bg-surface-sunken border border-line-2 rounded-lg px-2 py-1.5 text-sm text-ink-2 focus:outline-none"
				data-tour="admin-identity-status-filter"
			>
				<option value="all">전체 상태</option>
				<option value="enabled">활성만</option>
				<option value="disabled">비활성만</option>
			</select>
			<select
				bind:value={sortBy}
				class="bg-surface-sunken border border-line-2 rounded-lg px-2 py-1.5 text-sm text-ink-2 focus:outline-none"
			>
				<option value="name">이름순</option>
				<option value="first_seen">최초 활동일순</option>
			</select>
			<button
				onclick={() => {
					sortDir = sortDir === 'asc' ? 'desc' : 'asc';
				}}
				class="px-3 py-1.5 bg-surface-sunken border border-line-2 rounded-lg text-sm text-ink-2 hover:bg-surface-selected transition-colors"
			>{sortDir === 'asc' ? '오름차순' : '내림차순'}</button>
		</div>

		<div class="bg-surface-base border border-line rounded-lg p-5" data-tour="admin-identity-list">
			{#if pagedUsers.length === 0}
				<p class="text-xs text-ink-3 text-center py-6" data-tour="admin-identity-list-ready">검색 결과가 없습니다.</p>
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
</div>
