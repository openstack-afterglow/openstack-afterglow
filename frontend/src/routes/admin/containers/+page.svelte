<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api } from '$lib/api/client';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import ContainerDetailPanel from '$lib/components/ContainerDetailPanel.svelte';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import StatusChip from '$lib/components/ui/StatusChip.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import TutorialStartButton from '$lib/tutorial/TutorialStartButton.svelte';

	interface AdminContainer {
		uuid: string;
		name: string;
		status: string;
		image: string | null;
		cpu: number | null;
		memory: string | null;
		host: string | null;
		created_at: string | null;
		project_id: string | null;
	}

	let containers = $state<AdminContainer[]>([]);
	let loading = $state(true);
	let refreshing = $state(false);
	let selectedContainerId = $state<string | null>(null);

	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function load() {
		if (containers.length === 0) loading = true;
		else refreshing = true;
		try {
			containers = await api.get<AdminContainer[]>('/api/v1/admin/all-containers', token, projectId);
		} catch {
			containers = [];
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	const ar = createAutoRefresh(load, {
		storageKey: 'admin-containers',
		invokeOnMount: false,
		defaultActive: true,
		defaultInterval: 15,
		intervalOptions: [10, 15, 30, 60]
	});

	onMount(load);
</script>

<div class="p-4 md:p-6 max-w-7xl mx-auto">
	<div data-tour="admin-containers-header">
	<PageHeader breadcrumb="CONTAINERS" title="전체 컨테이너">
		{#snippet actions()}
			<TutorialStartButton tour="admin-containers" compactOnMobile />
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading || refreshing}
				onManualRefresh={load}
			/>
		{/snippet}
	</PageHeader>
	</div>

	<div data-tour="admin-containers-list">
	{#if loading}
		<LoadingSkeleton variant="table" rows={5} />
	{:else if containers.length === 0}
		<div class="text-ink-3 text-sm" data-tour="admin-containers-ready">컨테이너가 없습니다</div>
	{:else}
		<div class="overflow-x-auto" data-tour="admin-containers-ready">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<th class="text-left py-2 pr-4">이름</th>
						<th class="text-left py-2 pr-4">상태</th>
						<th class="text-left py-2 pr-4">이미지</th>
						<th class="text-left py-2 pr-4">CPU</th>
						<th class="text-left py-2 pr-4">메모리</th>
						<th class="text-left py-2 pr-4">호스트</th>
						<th class="text-left py-2">생성일</th>
					</tr>
				</thead>
				<tbody>
					{#each containers as c, index (c.uuid)}
						<tr
							class="border-b border-line/50 text-xs hover:bg-surface-sunken/30 transition-colors cursor-pointer {selectedContainerId === c.uuid ? 'bg-surface-sunken/50' : ''}"
							onclick={() => (selectedContainerId = c.uuid)}
							onkeydown={(e) => e.key === 'Enter' && (selectedContainerId = c.uuid)}
							role="button"
							tabindex="0"
							data-tour={index === 0 ? 'admin-containers-row' : undefined}
						>
							<td class="py-2 pr-4 text-ink-0"><span class="max-md:block max-md:max-w-[66vw] max-md:truncate" title={c.name || c.uuid}>{c.name || c.uuid.slice(0, 8)}</span></td>
							<td class="py-2 pr-4"><StatusChip status={c.status} /></td>
							<td class="py-2 pr-4 text-ink-2 font-mono text-xs">{c.image || '-'}</td>
							<td class="py-2 pr-4 text-ink-2">{c.cpu ?? '-'}</td>
							<td class="py-2 pr-4 text-ink-2">{c.memory || '-'}</td>
							<td class="py-2 pr-4 text-ink-2">{c.host || '-'}</td>
							<td class="py-2 text-ink-3">{c.created_at?.slice(0, 10) ?? '-'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
	</div>
</div>

{#if selectedContainerId}
	<SlidePanel onClose={() => (selectedContainerId = null)} ariaLabel="컨테이너 상세" width="w-full md:w-[480px]" dataTour="admin-containers-detail">
		<ContainerDetailPanel
			containerId={selectedContainerId}
			onClose={() => (selectedContainerId = null)}
			adminMode={true}
			onRefresh={load}
		/>
	</SlidePanel>
{/if}