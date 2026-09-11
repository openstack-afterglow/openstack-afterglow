<script lang="ts">
	import { untrack } from 'svelte';
	import { useK3sClusterDetailController } from '$lib/stores/k3sClusterDetailController.svelte';
	import { SectionHeader } from '$lib/components/ui';
	import K3sPodLogOverlay from './K3sPodLogOverlay.svelte';
	import type { PodInfo } from '$lib/types/k3s';

	const s = useK3sClusterDetailController();

	let loading = $state(false);
	let loadError = $state('');
	let viewingLogPod = $state<PodInfo | null>(null);

	const phaseColor: Record<string, string> = {
		Running:   'text-green-400 bg-green-900/30',
		Pending:   'text-yellow-400 bg-yellow-900/30',
		Succeeded: 'text-action-warm bg-surface-selected/30',
		Failed:    'text-red-400 bg-red-900/30',
	};

	$effect(() => {
		const ns = s.selectedNamespace;
		if (!ns) return;
		if (s.podsLoaded) return;
		loading = true;
		loadError = '';
		untrack(() => s.loadPods())
			.catch(() => { loadError = 'Pod 로드 실패'; })
			.finally(() => { loading = false; });
	});
</script>

{#if viewingLogPod}
	<K3sPodLogOverlay pod={viewingLogPod} onClose={() => { viewingLogPod = null; }} />
{/if}

<div class="bg-surface-base border border-line rounded-lg p-5 mb-4">
	<SectionHeader title="Pod" meta="{s.pods.length}개" />

	{#if loading}
		<div class="mt-4 text-sm text-ink-2 text-center py-6">로딩 중...</div>
	{:else if loadError}
		<div class="mt-4 text-sm text-red-400">{loadError}</div>
	{:else if s.pods.length === 0}
		<div class="mt-4 text-sm text-ink-3 text-center py-6">Pod 없음</div>
	{:else}
		<div class="mt-4 overflow-x-auto">
			<table class="w-full text-xs">
				<thead>
					<tr class="border-b border-line">
						<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-ink-3 font-medium">이름</th>
						<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-ink-3 font-medium">상태</th>
						<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-ink-3 font-medium">Ready</th>
						<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-ink-3 font-medium">재시작</th>
						<th class="text-left pb-2 text-[10px] uppercase tracking-wide text-ink-3 font-medium">노드</th>
						<th class="pb-2"></th>
					</tr>
				</thead>
				<tbody>
					{#each s.pods as pod}
						{@const actioning = s.workloadActioning === `${s.selectedNamespace}:pod:${pod.name}`}
						{@const pColor = phaseColor[pod.phase] ?? 'text-ink-2 bg-surface-sunken/50'}
						<tr class="border-b border-line/50 hover:bg-surface-sunken/30 transition-colors">
							<td class="py-2.5 text-ink-0 font-mono max-w-[200px] truncate">{pod.name}</td>
							<td class="py-2.5">
								<span class="px-1.5 py-0.5 rounded text-[10px] font-medium {pColor}">{pod.phase || '—'}</span>
							</td>
							<td class="py-2.5 tabular-nums text-ink-2">{pod.ready}</td>
							<td class="py-2.5 tabular-nums {pod.restarts > 5 ? 'text-yellow-400' : 'text-ink-2'}">{pod.restarts}</td>
							<td class="py-2.5 text-ink-2 font-mono text-[10px]">{pod.node ?? '—'}</td>
							<td class="py-2.5">
								<div class="flex items-center justify-end gap-1.5">
									<button
										onclick={() => { viewingLogPod = pod; }}
										class="px-2 py-1 rounded text-[10px] bg-surface-sunken text-ink-2 hover:bg-surface-selected transition-colors"
									>로그</button>
									<button
										onclick={() => s.removePod(pod.name)}
										disabled={!!s.workloadActioning}
										class="px-2 py-1 rounded text-[10px] bg-red-900/40 text-red-300 hover:bg-red-900/70 disabled:opacity-40 transition-colors"
									>{actioning ? '삭제 중...' : '삭제'}</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
