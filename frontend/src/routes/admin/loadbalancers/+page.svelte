<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/stores/auth';
	import { api, ApiError } from '$lib/api/client';
	import type { LoadBalancer } from '$lib/types/loadbalancer';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import AutoRefreshControl from '$lib/components/AutoRefreshControl.svelte';
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import LoadBalancerDetailPanel from '$lib/components/LoadBalancerDetailPanel.svelte';
	import { createAutoRefresh } from '$lib/utils/autoRefresh.svelte';
	import { confirmDialog } from '$lib/stores/confirm.svelte';
	import { toast } from '$lib/stores/toast';
	import BulkSelectionOverlay from '$lib/components/ui/BulkSelectionOverlay.svelte';
	import SelectionCheckbox from '$lib/components/ui/SelectionCheckbox.svelte';
	import SelectionToolbar from '$lib/components/ui/SelectionToolbar.svelte';
	import { createResourceSelection } from '$lib/utils/resourceSelection.svelte';
	import { executeBulkMutations } from '$lib/utils/bulkActions';
	import { isDroverLoadBalancer } from '$lib/utils/droverLoadBalancer';
	let loadbalancers = $state<LoadBalancer[]>([]);
	let loading = $state(true);
	let error = $state('');
	let selectedLbId = $state<string | null>(null);
	let selection = createResourceSelection();
	let busy = $state(false);
	let selectableIds = $derived(new Set(loadbalancers.filter((lb) => !isDroverLoadBalancer(lb)).map((lb) => lb.id)));
	const selectedCount = $derived([...selectableIds].filter((id) => selection.ids.has(id)).length);
	const allSelected = $derived(selectableIds.size > 0 && selectedCount === selectableIds.size);
	const indeterminate = $derived(selectedCount > 0 && !allSelected);
	const token = $derived($auth.token ?? undefined);
	const projectId = $derived($auth.projectId ?? undefined);

	async function fetchLoadbalancers(opts?: { refresh?: boolean }) {
		try {
			loadbalancers = await api.get<LoadBalancer[]>('/api/v1/admin/all-loadbalancers', token, projectId, opts);
			if (selection.count > 0) {
				selection.retain(loadbalancers.filter((lb) => !isDroverLoadBalancer(lb)).map((lb) => lb.id));
			}
			error = '';
		} catch (e) {
			error = e instanceof ApiError ? `조회 실패 (${e.status})` : '서버 오류';
		} finally {
			loading = false;
		}
	}

	async function bulkDelete() {
		const ids = [...selection.ids].filter((id) => selectableIds.has(id));
		if (ids.length === 0) return;
		const warning = '리스너·풀·멤버가 함께 삭제될 수 있습니다.';
		if (!await confirmDialog(`${ids.length}개 로드밸런서를 삭제하시겠습니까?\n${warning}`)) return;
		const tokenSnapshot = token;
		const projectSnapshot = projectId;
		busy = true;
		try {
			const results = await executeBulkMutations(ids, (id) => api.delete(`/api/v1/loadbalancers/${id}`, tokenSnapshot, projectSnapshot));
			const succeeded = results.filter((result) => result.ok).map((result) => result.id);
			if (projectSnapshot === ($auth.projectId ?? undefined)) selection.remove(succeeded);
			if (succeeded.length > 0) toast.success(`${succeeded.length}개 로드밸런서 삭제 요청을 완료했습니다.`);
			const failedCount = results.length - succeeded.length;
			if (failedCount > 0) toast.error(`${failedCount}개 로드밸런서 삭제에 실패했습니다.`);
			if (projectSnapshot === ($auth.projectId ?? undefined)) await fetchLoadbalancers({ refresh: true });
		} finally {
			busy = false;
		}
	}
	const ar = createAutoRefresh(() => fetchLoadbalancers(), {
		storageKey: 'admin-loadbalancers',
		invokeOnMount: false,
		defaultInterval: 30,
		intervalOptions: [15, 30, 60]
	});

	function openLbPanel(id: string) {
		selectedLbId = id;
	}

	function closeLbPanel() {
		selectedLbId = null;
	}

	onMount(() => {
		fetchLoadbalancers();
	});
</script>

<div class="bulk-selection-page p-4 md:p-8 max-w-7xl mx-auto">
	<PageHeader breadcrumb="NETWORK / LOADBALANCERS" title="로드밸런서">
		{#snippet actions()}
			<AutoRefreshControl
				bind:active={ar.active}
				bind:intervalSeconds={ar.intervalSeconds}
				intervalOptions={ar.intervalOptions}
				refreshing={loading}
				onManualRefresh={() => fetchLoadbalancers({ refresh: true })}
			/>
		{/snippet}
	</PageHeader>

	{#if error}
		<div class="bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm mb-4">
			{error}
		</div>
	{/if}

	{#if loading && loadbalancers.length === 0}
		<div class="space-y-4 animate-pulse">
			{#each [1, 2, 3] as _}
				<div class="h-12 bg-surface-sunken/50 rounded-lg"></div>
			{/each}
		</div>
	{:else if loadbalancers.length === 0}
		<div class="text-center py-20 text-ink-3 bg-surface-base/20 border border-line/50 rounded-lg">
			<div class="text-5xl mb-4">⚖️</div>
			<p class="text-lg">로드밸런서가 없습니다</p>
		</div>
	{:else}
		<div class="flex justify-end mb-3">
			<SelectionToolbar
				label="로드밸런서"
				ariaLabel="로드밸런서 전체 선택"
				checked={allSelected}
				indeterminate={indeterminate}
				selectedCount={selectedCount}
				disabled={busy || selectableIds.size === 0}
				onToggle={() => selection.toggleAll(selectableIds)}
			/>
		</div>
		<div class="overflow-x-auto bg-surface-base/20 border border-line/50 rounded-lg p-5">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b border-line text-ink-2 text-xs uppercase tracking-wide">
						<th class="py-2 pr-3 w-8 text-left" aria-label="선택"></th>
						<th class="text-left py-2 pr-4">이름 / ID</th>
						<th class="text-left py-2 pr-4">프로젝트 ID</th>
						<th class="text-left py-2 pr-4">VIP 주소</th>
						<th class="text-left py-2 pr-4">프로비저닝 상태</th>
						<th class="text-left py-2 pr-4">운영 상태</th>
						<th class="text-left py-2">액션</th>
					</tr>
				</thead>
				<tbody>
					{#each loadbalancers as lb (lb.id)}
						{@const isProtected = isDroverLoadBalancer(lb)}
						<tr class="resource-selection-surface border-b border-line/30 text-xs transition-colors hover:bg-surface-sunken/10" data-selected={selection.has(lb.id)}>
							<td class="py-3 pr-3 text-left" onclick={(e) => e.stopPropagation()}>
								<SelectionCheckbox
									checked={selection.has(lb.id)}
									disabled={busy || isProtected}
									unavailable={isProtected}
									title={isProtected ? 'Drover가 관리하는 로드밸런서입니다. (일괄 삭제 불가)' : undefined}
									ariaLabel={`${lb.name || lb.id.slice(0, 12)} 선택`}
									onclick={() => selection.toggle(lb.id)}
								/>
							</td>
							<td class="p-0">
								<button
									type="button"
									onclick={() => openLbPanel(lb.id)}
									class="block w-full py-3 pr-4 font-semibold text-ink-0 hover:text-action-warm-hover transition-colors text-left"
									title={lb.name || lb.id}
								>
									<span class="max-md:block max-md:max-w-[40vw] max-md:truncate">
										{lb.name || lb.id.slice(0, 12)}
									</span>
								</button>
							</td>
							<td class="py-3 pr-4 text-ink-3 font-mono text-[10px] select-all" title={lb.project_id}>
								{lb.project_id ? lb.project_id.slice(0, 8) + '...' : '—'}
							</td>
							<td class="py-3 pr-4 text-ink-2 font-mono">
								{lb.vip_address ?? '—'}
							</td>
							<td class="py-3 pr-4 font-medium">
								<span class={lb.status === 'ACTIVE' ? 'text-green-400' : 'text-orange-400'}>
									{lb.status ?? '—'}
								</span>
							</td>
							<td class="py-3 pr-4">
								<span class={lb.operating_status === 'ONLINE' ? 'text-green-400' : lb.operating_status === 'OFFLINE' ? 'text-red-400' : 'text-ink-3'}>
									{lb.operating_status ?? '—'}
								</span>
							</td>
							<td class="py-3" onclick={(e) => e.stopPropagation()}>
								<button
									onclick={() => openLbPanel(lb.id)}
									class="px-2.5 py-1 text-xs bg-surface-sunken hover:bg-surface-selected text-ink-2 border border-line-2 rounded transition-colors"
								>
									상세
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<div class="mt-4 text-xs text-ink-3">총 {loadbalancers.length}개 로드밸런서</div>
		</div>
	{/if}
</div>

<BulkSelectionOverlay
	count={selectedCount}
	ariaLabel="선택한 로드밸런서 일괄 작업"
	actions={[{ key: 'delete', label: '삭제', tone: 'danger', onAction: bulkDelete }]}
	{busy}
	onClear={() => selection.clear()}
/>

{#if selectedLbId}
	<SlidePanel onClose={closeLbPanel} ariaLabel="관리자 로드밸런서 상세">
		<LoadBalancerDetailPanel
			lbId={selectedLbId}
			onClose={closeLbPanel}
			onDeleted={() => { fetchLoadbalancers({ refresh: true }); closeLbPanel(); }}
		/>
	</SlidePanel>
{/if}
