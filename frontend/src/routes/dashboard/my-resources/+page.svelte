<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import { Alert, EmptyState, PageHeader, PageShell } from '$lib/components/ui';
	import MyResourcesSummary from '$lib/components/dashboard/my-resources/MyResourcesSummary.svelte';
	import ProjectUsageTable from '$lib/components/dashboard/my-resources/ProjectUsageTable.svelte';
	import InstancesPreviewCard from '$lib/components/dashboard/my-resources/InstancesPreviewCard.svelte';
	import VolumesPreviewCard from '$lib/components/dashboard/my-resources/VolumesPreviewCard.svelte';
	import type { UserDashboardSummary } from '$lib/types/userDashboard';

	let data = $state<UserDashboardSummary | null>(null);
	let initialLoading = $state(true);
	let refreshing = $state(false);
	let error = $state('');

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	const allInstances = $derived(
		data ? data.projects.flatMap(p => p.instances.map(inst => ({ ...inst, project: p.project_name }))) : []
	);
	const allVolumes = $derived(
		data ? data.projects.flatMap(p => p.volumes.map(vol => ({ ...vol, project: p.project_name }))) : []
	);

	async function load(opts?: { refresh?: boolean }) {
		error = '';
		try {
			data = await api.get<UserDashboardSummary>('/api/v1/user-dashboard/summary', token, projectId, opts);
		} catch (e) {
			error = e instanceof ApiError ? e.message : '데이터를 불러올 수 없습니다';
		} finally {
			initialLoading = false;
		}
	}

	async function forceRefresh() {
		refreshing = true;
		try {
			await load({ refresh: true });
		} finally {
			refreshing = false;
		}
	}

	const ar = createAutoRefresh(() => load(), {
		storageKey: 'dashboard-my-resources',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 30,
		intervalOptions: [10, 15, 30, 60],
	});
	$effect(() => {
		const pid = $auth.projectId;
		if (!pid) return;
		untrack(() => load());
	});
</script>

<PageShell>
	<div class="flex items-center gap-3 mb-4">
		<a
			href="/dashboard"
			class="inline-flex items-center gap-1.5 text-xs text-ink-2 hover:text-ink-0 transition-colors px-2.5 py-1.5 rounded-md hover:bg-surface-sunken"
		>
			<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path></svg>
			대시보드로 돌아가기
		</a>
		<span class="text-ink-3">·</span>
		<a
			href="/dashboard/account"
			class="inline-flex items-center gap-1.5 text-xs text-action-warm hover:text-action-warm-hover transition-colors px-2.5 py-1.5 rounded-md hover:bg-action-warm-hover/10"
		>
			계정 설정
			<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
		</a>
	</div>

	<PageHeader breadcrumb="" title="내 리소스">
		{#snippet actions()}
			<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={refreshing}
			onManualRefresh={forceRefresh}
		/>
		{/snippet}
	</PageHeader>

	{#if error}
		<Alert tone="danger" class="mb-4">{error}</Alert>
	{/if}

	{#if initialLoading}
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-3.5 mb-4">
			{#each [1, 2, 3, 4] as _}
				<div class="animate-pulse bg-surface-base border border-line rounded-lg h-[82px]"></div>
			{/each}
		</div>
		<div class="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
			{#each [1, 2, 3, 4] as _}
				<div class="animate-pulse bg-surface-base border border-line rounded-lg h-48"></div>
			{/each}
		</div>
	{:else if data}
		<MyResourcesSummary totals={data.totals} />
		<ProjectUsageTable projects={data.projects} />

		<div class="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
			<InstancesPreviewCard instances={allInstances} />
			<VolumesPreviewCard volumes={allVolumes} />

			<!-- Floating IP 카드 -->
			<div class="bg-surface-base border border-line rounded-lg p-5">
				<div class="flex items-center gap-2.5 mb-3.5">
					<div class="w-10 h-10 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 flex items-center justify-center shrink-0">
						<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
						</svg>
					</div>
					<div class="text-ink-0 font-semibold text-sm">Floating IP</div>
					<span class="ml-auto text-xs text-ink-3">{data.totals.floating_ips}개</span>
				</div>
				<div class="flex flex-col items-center justify-center py-6">
					<div class="text-[11px] text-ink-3 text-center leading-relaxed">
						Floating IP 목록은<br />
						<a href="/dashboard/network/floating-ips" class="text-emerald-400 hover:text-emerald-300 transition-colors">네트워크 → Floating IP</a>에서 확인하세요
					</div>
				</div>
			</div>
		</div>

		{#if data.projects.length === 0}
			<EmptyState headline="소속 프로젝트가 없습니다" description="프로젝트에 초대되면 리소스가 여기에 표시됩니다." />
		{/if}
	{/if}
</PageShell>
