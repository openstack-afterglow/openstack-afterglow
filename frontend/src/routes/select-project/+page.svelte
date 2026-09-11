<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth, clearAuth, setAuth, logoutInProgress, exitMockAuth, isMockAuthActive } from '$lib/stores/auth';
	import { api, ApiError, beginSessionRevocation, endSessionRevocation } from '$lib/api/client';
	import type { Project } from '$lib/stores/auth';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import CreateProjectModal from '$lib/components/projects/CreateProjectModal.svelte';

	import { postAuthDestination } from '$lib/utils/mcpConsent';
	let projects = $state<Project[]>([]);
	let loading = $state(true);
	let switching = $state(false);
	let error = $state('');
	let showCreateModal = $state(false);
	let logoutConfirming = $state(false);
	const mockupActive = $derived($page.data.mockup?.active === true);


	async function load() {
		loading = true;
		error = '';
		try {
			const [projs, profile] = await Promise.all([
				api.get<Project[]>('/api/v1/auth/projects/recent', $auth.token ?? undefined),
				// Fix 3: 프로필 401은 .catch(()=>null)로 의도적으로 허용 — 전역 로그아웃 억제
			api.get<{ default_project_id: string }>('/api/v1/profile', $auth.token ?? undefined, undefined, { suppressAuthRedirect: true }).catch(() => null),
			]);
			projects = projs;

			if (profile?.default_project_id) {
				const defaultProj = projs.find(p => p.id === profile.default_project_id);
				if (defaultProj) {
					await selectProject(defaultProj);
					return;
				}
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : '프로젝트 목록을 불러오지 못했습니다';
		} finally {
			loading = false;
		}
	}

	// Fix 1: 토큰 변경에 반응하는 $effect 대신 onMount 1회성 로드로 전환.
	// 기존 $effect는 selectProject() → setAuth(새 토큰) → effect 재실행 → load() 재진입 루프를 일으킴.
	onMount(() => {
		if ($auth.token || mockupActive) {
			load();
		} else {
			goto('/login');
		}
	});

	async function selectProject(proj: Project) {
		const token = $auth.token;
		if (!token || switching) return;
		switching = true;
		try {
			const resp = await api.post<{
				token: string;
				refresh_token: string;
				expires_at: string;
				project_id: string;
				project_name: string;
				user_id: string;
				username: string;
				roles: string[];
				is_system_admin: boolean;
			}>('/api/v1/auth/token/project', { project_id: proj.id }, token);

			if ($logoutInProgress || !$auth.token) return;
			setAuth({
				token: resp.token,
				refreshToken: resp.refresh_token,
				accessExpiresAt: resp.expires_at
					? Math.floor(new Date(resp.expires_at).getTime() / 1000)
					: null,
				projectId: resp.project_id,
				projectName: resp.project_name,
				roles: resp.roles ?? [],
				isSystemAdmin: !!resp.is_system_admin,
			});
			goto(postAuthDestination('/dashboard'));
		} catch (e) {
			error = e instanceof ApiError ? `프로젝트 전환 실패: ${e.message}` : '프로젝트 전환 실패';
		} finally {
			switching = false;
		}
	}

	function openCreateProject() {
		if (mockupActive) {
			toast.info('튜토리얼 모드에서는 프로젝트 생성을 제외합니다.');
			return;
		}
		showCreateModal = true;
	}

	async function logout() {
		if ($logoutInProgress || logoutConfirming) return;
		logoutConfirming = true;
		let confirmed: boolean;
		try {
			confirmed = await confirmDialog('로그아웃하시겠습니까?');
		} finally {
			logoutConfirming = false;
		}
		if (!confirmed) return;

		logoutInProgress.set(true);
		try {
			const pendingRefresh = beginSessionRevocation();
			await pendingRefresh;
			const logoutToken = $auth.token;
			if (logoutToken) {
				try {
					await api.post('/api/v1/auth/logout', {}, logoutToken);
				} catch { /* 실패해도 로컬 정리는 진행 */ }
			}
			const mockLogout = isMockAuthActive();
			if (mockLogout) exitMockAuth();
			clearAuth();
			await goto(mockLogout ? '/login?tutorial=off' : '/login', { replaceState: true });
			toast.success('정상적으로 로그아웃 되었습니다.');
		} finally {
			endSessionRevocation();
			logoutInProgress.set(false);
		}
	}

	function formatRelativeTime(iso: string | null | undefined): string {
		if (!iso) return '-';
		const diff = Date.now() - new Date(iso).getTime();
		const minutes = Math.floor(diff / 60_000);
		if (minutes < 1) return '방금 전';
		if (minutes < 60) return `${minutes}분 전`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}시간 전`;
		const days = Math.floor(hours / 24);
		if (days < 30) return `${days}일 전`;
		const months = Math.floor(days / 30);
		if (months < 12) return `${months}개월 전`;
		return `${Math.floor(months / 12)}년 전`;
	}

	function orgLabel(domain_name: string | null | undefined): string {
		if (!domain_name || domain_name === 'Default') return 'No organization';
		return domain_name;
	}
</script>

<main id="main-content" tabindex="-1" class="min-h-screen bg-surface-canvas text-ink-0">
	<!-- 상단 알림 바 -->
	<div class="border-b border-line bg-[#0B1220]">
		<div class="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
			<div class="flex items-center gap-2 text-sm text-ink-2">
				<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
				</svg>
				<span>작업할 프로젝트를 선택해주세요.</span>
			</div>
			<button
				onclick={logout}
				disabled={$logoutInProgress}
				class="text-sm text-ink-3 hover:text-ink-0 transition-colors"
			>
				로그아웃
			</button>
		</div>
	</div>

	<!-- 본문 -->
	<div class="max-w-6xl mx-auto px-6 py-10">
		<div class="flex items-center justify-between mb-6">
			<h1 class="text-lg font-semibold text-ink-0">최근 프로젝트 선택</h1>
			<button
				onclick={openCreateProject}
				class="flex items-center gap-1.5 px-3 py-1.5 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors"
			>
				<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14M5 12h14"/>
				</svg>
				새 프로젝트
			</button>
		</div>

		{#if loading}
			<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
				{#each [1, 2, 3, 4, 5] as _}
					<div class="h-28 bg-surface-sunken rounded-xl animate-pulse"></div>
				{/each}
			</div>
		{:else if error}
			<div class="text-red-400 text-sm">{error}</div>
		{:else if projects.length === 0}
			<div class="text-ink-3 text-sm text-center py-16">접근 가능한 프로젝트가 없습니다.</div>
		{:else}
			<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
				{#each projects as proj (proj.id)}
					<button
						onclick={() => selectProject(proj)}
						disabled={switching}
						class="text-left border border-line-2 rounded-xl p-5 bg-surface-base hover:border-action-warm hover:bg-surface-sunken transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
					>
						<div class="font-medium text-ink-0 mb-3 truncate">{proj.name}</div>
						<div class="space-y-1 text-[13px] text-ink-2">
							<div class="flex gap-1.5">
								<span class="shrink-0">프로젝트 ID:</span>
								<span class="truncate font-mono text-ink-2">{proj.id}</span>
							</div>
							<div class="flex gap-1.5">
								<span class="shrink-0">조직:</span>
								<span class="truncate">{orgLabel(proj.domain_name)}</span>
							</div>
							<div class="flex gap-1.5">
								<span class="shrink-0">액세스 시기:</span>
								<span>{formatRelativeTime(proj.last_accessed_at)}</span>
							</div>
						</div>
					</button>
				{/each}
			</div>
		{/if}
	</div>
</main>

{#if showCreateModal && !mockupActive}
	<CreateProjectModal
		onClose={() => (showCreateModal = false)}
		onSuccess={(proj) => {
			showCreateModal = false;
			load();
		}}
	/>
{/if}
