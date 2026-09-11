<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import { projectNames } from '$lib/stores/projectNames';
	import K3sClusterDetailPanel from '$lib/components/K3sClusterDetailPanel.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import TableShell from '$lib/components/ui/TableShell.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';

	interface AdminK3sCluster {
		id: string;
		name: string;
		status: string;
		status_reason: string | null;
		server_ip: string | null;
		api_address: string | null;
		agent_count: number;
		agent_vm_ids: string[];
		k3s_version: string | null;
		created_at: string | null;
		project_id: string | null;
	}

	let clusters = $state<AdminK3sCluster[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let statusFilter = $state<'all' | 'active' | 'pending' | 'error' | 'deleted'>('all');
	// 슬라이드 패널
	let selectedClusterId = $state<string | null>(null);

	function openClusterPanel(id: string) {
		selectedClusterId = id;
	}

	function closeClusterPanel() {
		selectedClusterId = null;
	}

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		if (clusters.length === 0) loading = true;
		else refreshing = true;
		try {
			let url = '/api/v1/admin/k3s-clusters';
			const params = new URLSearchParams();
			if (statusFilter === 'active') params.set('status', 'ACTIVE');
			else if (statusFilter === 'pending') params.set('status', 'CREATING,PROVISIONING,SCALING,DELETING');
			else if (statusFilter === 'error') params.set('status', 'ERROR,FAILED');
			else if (statusFilter === 'deleted') {
				params.set('include_deleted', 'true');
				params.set('status', 'DELETED');
			}
			if (params.toString()) url += `?${params.toString()}`;
			clusters = await api.get<AdminK3sCluster[]>(url, token, projectId);
		} catch {
			clusters = [];
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	function setStatusFilter(filter: typeof statusFilter) {
		statusFilter = filter;
		void load();
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-drover',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60]
	});

	onMount(() => {
		load();
		projectNames.load(token, projectId);
	});
</script>

<!-- 슬라이드 패널 -->
{#if selectedClusterId}
	<SlidePanel onClose={closeClusterPanel} ariaLabel="Drover 클러스터 상세">
		<K3sClusterDetailPanel clusterId={selectedClusterId} onClose={closeClusterPanel} adminMode={true} />
	</SlidePanel>
{/if}

<div class="p-4 md:p-8 max-w-7xl mx-auto">
	<PageHeader breadcrumb="DROVER" title="Drover 클러스터">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>
	<div class="mb-4 flex min-w-0 items-center gap-2">
		<span class="shrink-0 text-xs text-ink-2">상태 필터:</span>
		<div class="min-w-0 overflow-x-auto pb-1">
			<ToggleGroup
				value={statusFilter}
				options={[
					{ value: 'all', label: '전체' },
					{ value: 'active', label: '정상 (ACTIVE)' },
					{ value: 'pending', label: '진행 중 (PENDING)' },
					{ value: 'error', label: '오류 (ERROR/FAILED)' },
					{ value: 'deleted', label: '삭제됨 (DELETED)' }
				]}
				onchange={(value) => setStatusFilter(value as typeof statusFilter)}
				size="xs"
				ariaLabel="클러스터 상태 필터"
			/>
		</div>
	</div>

	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if clusters.length === 0}
		<EmptyState headline="Drover 클러스터가 없습니다" />
	{:else}
		<TableShell density="compact">
			<table class="min-w-[58rem] text-sm">
				<thead>
					<tr class="text-xs uppercase tracking-wide">
						<th>이름</th>
						<th>상태</th>
						<th>프로젝트</th>
						<th>서버 IP</th>
						<th>노드</th>
						<th>버전</th>
						<th>생성일</th>
					</tr>
				</thead>
				<tbody>
					{#each clusters as c (c.id)}
						<tr
							class="cursor-pointer text-xs transition-colors focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
							onclick={() => openClusterPanel(c.id)}
							onkeydown={(e) => e.key === 'Enter' && openClusterPanel(c.id)}
							role="button"
							tabindex="0">
							<td>
								<span class="max-md:block max-md:max-w-[66vw] max-md:truncate text-ink-0 transition-colors hover:text-accent" title={c.name}>
									{c.name}
								</span>
								{#if c.status_reason}
									<div class="mt-0.5 max-w-40 truncate text-xs text-ink-3">{c.status_reason}</div>
								{/if}
							</td>
							<td>
								<StatusChip status={c.status} />
							</td>
							<td class="text-ink-2">
								{c.project_id ? ($projectNames.get(c.project_id) ?? c.project_id.slice(0, 8)) : '-'}
							</td>
							<td class="font-mono text-ink-2">{c.server_ip || '-'}</td>
							<td class="text-ink-2">1 서버 + {c.agent_vm_ids?.length ?? 0} / {c.agent_count} 에이전트</td>
							<td class="text-ink-3">{c.k3s_version || '-'}</td>
							<td class="text-ink-3">{c.created_at ? c.created_at.slice(0, 10) : '-'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</TableShell>
	{/if}
</div>
