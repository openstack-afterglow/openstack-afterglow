<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import ProjectQuotaPanel from '$lib/components/ProjectQuotaPanel.svelte';
	import type { Overview, VersionInfo, ProjectUsage } from '$lib/types/adminOverview';
	import KpiCardRow from '$lib/components/admin/overview/KpiCardRow.svelte';
	import ResourceDonutsCard from '$lib/components/admin/overview/ResourceDonutsCard.svelte';
	import ProjectUsageTable from '$lib/components/admin/overview/ProjectUsageTable.svelte';
	import ServiceCountCards from '$lib/components/admin/overview/ServiceCountCards.svelte';
	import VersionInfoPanel from '$lib/components/admin/overview/VersionInfoPanel.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { Alert, PageHeader, PageShell, StatTile } from '$lib/components/ui';
	import { toast } from '$lib/stores/toast';

	interface Notification {
		severity: string;
		message: string;
		target: string;
		href: string;
	}

	interface IdentitySummary {
		user_count: number;
		project_count: number;
		role_count: number;
		group_count: number;
		partial?: boolean;
		partial_reasons?: string[];
		recent_users?: { id: string; name: string }[];
		recent_projects?: { id: string; name: string }[];
	}

	let overview = $state<Overview | null>(null);
	let overviewLoading = $state(true);
	let error = $state('');
	let projectUsage = $state<ProjectUsage[]>([]);
	let projectUsageLoading = $state(true);
	let versionInfo = $state<VersionInfo | null>(null);
	let versionOpen = $state(false);
	let selectedProject = $state<ProjectUsage | null>(null);
	let notifications = $state<Notification[]>([]);
	let identitySummary = $state<IdentitySummary | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	const mockupAdminActive = $derived($page.data.mockup?.active === true && $page.data.mockup.profile === 'admin');

	function selectProjectUsage(project: ProjectUsage) {
		if (mockupAdminActive) {
			toast.info('mockup mode에서는 관리자 개요만 지원합니다.');
			return;
		}
		selectedProject = project;
	}
	function loadProjectUsage() {
		projectUsageLoading = true;
		api.get<ProjectUsage[]>('/api/v1/admin/overview/projects', token, projectId)
			.then(r => { projectUsage = r; })
			.catch(() => {})
			.finally(() => { projectUsageLoading = false; });
	}

	const ar = createAutoRefresh(
		() => { loadProjectUsage(); },
		{ storageKey: 'admin-overview', defaultActive: true, defaultInterval: 60, invokeOnMount: false }
	);

	onMount(() => {
		api.get<Overview>('/api/v1/admin/overview', token, projectId)
			.then(r => { overview = r; })
			.catch((e) => {
				if (e instanceof ApiError && e.status === 403) { goto('/dashboard'); return; }
				error = e instanceof ApiError ? `조회 실패: ${e.message}` : '서버 오류';
			})
			.finally(() => { overviewLoading = false; });

		loadProjectUsage();

		api.get<VersionInfo>('/api/v1/admin/version', token, projectId)
			.then(r => { versionInfo = r; })
			.catch(() => {});

		api.get<Notification[]>('/api/v1/admin/notifications', token, projectId)
			.then(r => { notifications = r; })
			.catch(() => {});

		api.get<IdentitySummary>('/api/v1/admin/identity/summary', token, projectId)
			.then(r => { identitySummary = r; })
			.catch(() => {});
	});
</script>

{#key $auth.projectId}
<PageShell class="flex flex-col gap-5">
	<PageHeader
		breadcrumb="ADMIN / OVERVIEW"
		title="관리자 개요"
		subtitle="클러스터 전반 · 자원 현황 · 실시간 알림"
	/>

	{#if notifications.length > 0}
		{@const critCount = notifications.filter(n => n.severity === 'critical').length}
		{@const warnCount = notifications.filter(n => n.severity === 'warning').length}
		<Alert tone={critCount > 0 ? 'danger' : 'warning'} class="notification-alert">
			<span class="text-sm" style="color: var(--color-ink-1);">
				{#if critCount > 0}
					<span class="font-semibold" style="color: var(--color-state-danger);">{critCount} critical</span> ·
				{/if}
				{#if warnCount > 0}
					<span class="font-semibold" style="color: var(--color-state-warning);">{warnCount} warning</span> ·
				{/if}
				{notifications.length - critCount - warnCount} info —
				<a href="/admin/monitoring" class="underline" style="color: var(--admin-tone);">모니터링 상세 →</a>
			</span>
		</Alert>
	{/if}

	{#if error}
		<Alert tone="danger">{error}</Alert>
	{/if}


	{#if overviewLoading}
		<div class="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3">
			{#each Array(3) as _}
				<div class="h-[82px] bg-surface-base animate-pulse"></div>
			{/each}
		</div>
		<div class="bg-surface-base border border-line rounded-lg p-5 animate-pulse h-[260px]"></div>
	{:else if overview}
		<KpiCardRow {overview} />

		<!-- Identity 통계: 사용자/프로젝트/역할/그룹 -->
		{#if identitySummary}
			<div class="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
				<a href="/admin/users" class="block">
					<StatTile label="사용자" value={identitySummary.user_count} unit="명" accent="amber" flat class="h-full">
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/>
							</svg>
						{/snippet}
						{#if identitySummary.recent_users && identitySummary.recent_users.length > 0}
							{#snippet footer()}
								<span class="flex items-center gap-1 text-[10px] text-emerald-400">
									<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 animate-pulse"></span>
									최근 추가 {identitySummary?.recent_users?.length ?? 0}명
								</span>
							{/snippet}
						{/if}
					</StatTile>
				</a>
				<a href="/admin/projects" class="block">
					<StatTile label="프로젝트" value={identitySummary.project_count} unit="활성" accent="blue" flat class="h-full">
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
							</svg>
						{/snippet}
						{#if identitySummary.recent_projects && identitySummary.recent_projects.length > 0}
							{#snippet footer()}
								<span class="flex items-center gap-1 text-[10px] text-emerald-400">
									<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 animate-pulse"></span>
									최근 추가 {identitySummary?.recent_projects?.length ?? 0}개
								</span>
							{/snippet}
						{/if}
					</StatTile>
				</a>
				<a href="/admin/roles" class="block">
					<StatTile label="역할" value={identitySummary.role_count} unit="정의됨" accent="violet" flat class="h-full">
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
							</svg>
						{/snippet}
					</StatTile>
				</a>
				<a href="/admin/groups" class="block">
					<StatTile label="그룹" value={identitySummary.group_count} unit="그룹" accent="cyan" flat class="h-full">
						{#snippet icon()}
							<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
								<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
								<circle cx="9" cy="7" r="4"/>
								<path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
							</svg>
						{/snippet}
					</StatTile>
				</a>
			</div>

			{#if identitySummary.partial && identitySummary.partial_reasons && identitySummary.partial_reasons.length > 0}
				<div class="flex items-center gap-2.5 px-4 py-2.5 rounded-xl border text-xs"
				     style="background: color-mix(in oklab, var(--color-state-warning) 10%, transparent); border-color: color-mix(in oklab, var(--color-state-warning) 30%, transparent); color: var(--color-state-warning);">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="flex-shrink-0">
						<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
						<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
					</svg>
					<span>일부 정보 미완 — {identitySummary.partial_reasons.map(r => r.includes('insufficient_privileges') ? r.split(':')[0] + ' 권한 부족 (system-scope 필요)' : r).join(', ')}</span>
				</div>
			{/if}
		{/if}

		<ResourceDonutsCard {overview} />

		<div class="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-3.5">
			<ProjectUsageTable
				projects={projectUsage}
				loading={projectUsageLoading}
				onSelectProject={selectProjectUsage}
			/>
			<ServiceCountCards {overview} />
		</div>

		<!-- 퀵 링크 -->
		<div class="flex gap-3 flex-wrap text-sm">
			<a href="/admin/hypervisors" class="text-ink-2 hover:text-ink-0 transition-colors">하이퍼바이저 →</a>
			<a href="/admin/instances" class="text-ink-2 hover:text-ink-0 transition-colors">전체 인스턴스 →</a>
			<a href="/admin/containers" class="text-ink-2 hover:text-ink-0 transition-colors">전체 컨테이너 →</a>
			<a href="/admin/file-storage" class="text-ink-2 hover:text-ink-0 transition-colors">파일 스토리지 →</a>
			<a href="/admin/database-instances" class="text-ink-2 hover:text-ink-0 transition-colors">Database →</a>
			<a href="/admin/object-storage" class="text-ink-2 hover:text-ink-0 transition-colors">Object Storage →</a>
			<a href="/admin/topology" class="text-ink-2 hover:text-ink-0 transition-colors">전체 토폴로지 →</a>
			<a href="/admin/networks" class="text-ink-2 hover:text-ink-0 transition-colors">네트워크 →</a>
		</div>

		<VersionInfoPanel {versionInfo} bind:open={versionOpen} />
	{:else}
		<div class="text-ink-3 text-sm">개요를 불러올 수 없습니다</div>
	{/if}
</PageShell>

{#if selectedProject}
	<ProjectQuotaPanel
		projectId={selectedProject.project_id}
		projectName={selectedProject.project_name}
		{token}
		authProjectId={projectId}
		onClose={() => { selectedProject = null; }}
		onUpdated={() => { loadProjectUsage(); }}
	/>
{/if}
{/key}
