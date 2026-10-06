<script lang="ts">
	import { t } from '$lib/i18n/ns/topology';
	import { untrack } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
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
		if (!data) error = '';
		try {
			data = await api.get<TopologyData>(
				'/api/v1/networks/topology',
				$auth.token ?? undefined,
				$auth.projectId ?? undefined
			);
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? t('topology.loadFailed', { status: e.status, message: e.message }) : t('topology.serverError');
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
				{t('legacy.back')}
			</a>
			<h1 class="text-2xl font-bold text-ink-0 mt-2">{t('legacy.title')}</h1>
		</div>
		<AutoRefreshControl
			bind:active={ar.active}
			bind:intervalSeconds={ar.intervalSeconds}
			intervalOptions={ar.intervalOptions}
			refreshing={loading || refreshing}
			onManualRefresh={fetchTopology}
		/>
	</div>

	<!-- 갱신 실패는 그려진 토폴로지를 내리지 않는다(다시 마운트되면 자동 갱신이 진입 모션을 재생한다) -->
	{#if error}
		{#if data}
			<div role="status" class="mb-4 rounded-lg border border-state-danger/30 bg-state-danger/10 px-4 py-3 text-sm text-state-danger">{error}</div>
		{:else}
			<Alert tone="danger" class="mb-4">{error}</Alert>
		{/if}
	{/if}
	{#if loading}
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
				{t('network.external')}
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-2 h-4 rounded" style="background:#0d9488"></span>
				{t('network.shared')}
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-2 h-4 rounded" style="background:#3b82f6"></span>
				{t('network.internal')}
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded-full" style="background:#1c1400;border:1px solid #f59e0b"></span>
				{t('legacy.externalRouter')}
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded-full" style="background:#0f172a;border:1px solid #64748b"></span>
				{t('legacy.internalRouter')}
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded" style="background:#052e16;border:1px solid #22c55e"></span>
				{t('legacy.activeInstance')}
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded" style="background:#450a0a;border:1px solid #ef4444"></span>
				{t('legacy.stoppedInstance')}
			</span>
			<span class="flex items-center gap-1.5">
				<span class="inline-block w-3 h-3 rounded" style="background:#1c1917;border:1px solid #78716c"></span>
				{t('legacy.otherInstance')}
			</span>
		</div>

		<!-- 요약 (현재 프로젝트 기준) -->
		<div class="mt-4 flex gap-6 text-xs text-ink-2 px-1">
			<span>{t('summary.networks', { count: _visibleNets.length })}</span>
			<span>{t('summary.routers', { count: _projectRouters.length })}</span>
			<span>{t('summary.instances', { count: data.instances.length })}</span>
			<span>{t('summary.floatingIps', { count: _projectFips.length })}</span>
		</div>
	{/if}
</div>
