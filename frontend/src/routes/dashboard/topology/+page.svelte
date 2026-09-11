<script lang="ts">
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import GlobalTopology from '$lib/components/GlobalTopology.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import type { TopologyData } from '$lib/types/topology';

	let data = $state<TopologyData | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let error = $state('');

	const ar = createAutoRefresh(fetchTopology, {
		storageKey: 'dashboard-topology',
		invokeOnMount: false,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	$effect(() => {
		if (!$auth.token) return;
		untrack(() => {
			data = null;
			fetchTopology();
		});
	});

	async function fetchTopology() {
		if (!data) loading = true;
		else refreshing = true;
		error = '';
		try {
			data = await api.get<TopologyData>(
				'/api/v1/networks/topology',
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status}): ${e.message}` : '서버 오류';
		} finally {
			loading = false;
			refreshing = false;
		}
	}
</script>

<div class="p-4 md:p-6 max-w-screen-2xl mx-auto">
	<div class="mb-6 flex items-center justify-between">
		<div>
			<a href="/dashboard" class="text-ink-2 hover:text-ink-1 text-sm transition-colors">
				← 대시보드
			</a>
			<h1 class="text-2xl font-bold text-ink-0 mt-2">네트워크 토폴로지</h1>
		</div>
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={loading || refreshing}
			onManualRefresh={fetchTopology}
		/>
	</div>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm">
			{error}
		</div>
	{:else if loading}
		<LoadingSkeleton variant="card" rows={8} />
	{:else if data}
		{@const _visibleNets = data.networks.filter(n => n.is_external || n.is_shared || n.project_id === $auth.projectId)}
		{@const _projectRouters = data.routers.filter(r => r.project_id === $auth.projectId)}
		{@const _projectFips = data.floating_ips.filter(f => !f.project_id || f.project_id === $auth.projectId)}
		<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
			<GlobalTopology {data} projectId={$auth.projectId} />
		</div>

		<!-- 범례 -->
		<div class="flex flex-wrap gap-5 text-xs text-ink-2 px-1">
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-2 h-4 rounded" style="background:#ea580c"></span>
				외부 네트워크
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-2 h-4 rounded" style="background:#0d9488"></span>
				공유 네트워크
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-2 h-4 rounded" style="background:#3b82f6"></span>
				내부 네트워크
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded-full" style="background:#1c1400;border:1px solid #f59e0b"></span>
				라우터 (외부 게이트웨이)
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded-full" style="background:#0f172a;border:1px solid #64748b"></span>
				라우터 (내부)
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded" style="background:#052e16;border:1px solid #22c55e"></span>
				인스턴스 (ACTIVE)
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded" style="background:#450a0a;border:1px solid #ef4444"></span>
				인스턴스 (SHUTOFF/ERROR)
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded" style="background:#1c1917;border:1px solid #78716c"></span>
				인스턴스 (기타)
			</span>
		</div>

		<!-- 요약 (현재 프로젝트 기준) -->
		<div class="mt-4 flex gap-6 text-xs text-ink-3 px-1">
			<span>네트워크 {_visibleNets.length}개</span>
			<span>라우터 {_projectRouters.length}개</span>
			<span>인스턴스 {data.instances.length}개</span>
			<span>Floating IP {_projectFips.length}개</span>
		</div>
	{/if}
</div>
