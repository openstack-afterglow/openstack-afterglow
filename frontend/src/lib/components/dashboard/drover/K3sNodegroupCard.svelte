<script lang="ts">
	import type { K3sNodegroup } from '$lib/types/k3s';

	let {
		nodegroup,
		onEdit,
		onDelete,
	}: {
		nodegroup: K3sNodegroup;
		onEdit?: (ng: K3sNodegroup) => void;
		onDelete?: (ng: K3sNodegroup) => void;
	} = $props();

	const roleLabel = $derived(nodegroup.role === 'server' ? '서버' : '에이전트');
	const roleBadgeClass = $derived(
		nodegroup.role === 'server'
			? 'bg-purple-900/40 text-purple-400 border-purple-800'
			: 'bg-surface-selected/40 text-action-warm border-action-warm'
	);


	function nestedNumber(source: Record<string, unknown>, path: string[]): number {
		let value: unknown = source;
		for (const key of path) {
			if (!value || typeof value !== 'object') return 0;
			value = (value as Record<string, unknown>)[key];
		}
		const n = Number(value ?? 0);
		return Number.isFinite(n) ? n : 0;
	}
	const runningVms = $derived(nodegroup.vms.filter(v => v.status === 'RUNNING' || v.status === 'ACTIVE').length);
	const inFlight = $derived((nodegroup.stampede_state as Record<string, number>)?.in_flight_count ?? 0);
	const gpuCount = $derived(
		nestedNumber(nodegroup.stampede_state, ['flavor_summary', 'gpu']) ||
			nestedNumber(nodegroup.stampede_state, ['capacity', 'allocatable', 'gpu'])
	);
</script>

<div class="bg-surface-sunken/50 border border-line-2 rounded-lg p-3 space-y-2">
	<div class="flex items-center justify-between">
		<div class="flex items-center gap-2 flex-wrap">
			<span class="text-xs border rounded px-1.5 py-0.5 {roleBadgeClass}">{roleLabel}</span>
			<span class="text-sm font-medium text-ink-0">{nodegroup.name}</span>
			{#if nodegroup.is_default}
				<span class="text-xs text-ink-3">(기본)</span>
			{/if}
			{#if nodegroup.stampede_enabled}
				<span class="text-xs bg-surface-selected/50 text-action-warm border border-action-warm/60 rounded px-1.5 py-0.5 leading-none">Stampede</span>
				<span class="text-xs text-ink-3">{nodegroup.min_size}–{nodegroup.max_size}</span>
				{#if gpuCount > 0}
					<span class="text-xs bg-emerald-900/50 text-emerald-300 border border-emerald-700/60 rounded px-1.5 py-0.5 leading-none">GPU {gpuCount}</span>
				{/if}
				{#if inFlight > 0}
					<span class="text-xs text-yellow-400 animate-pulse">▲ +{inFlight} 프로비저닝 중</span>
				{/if}
			{/if}
		</div>
		<div class="flex items-center gap-1">
			{#if onEdit && !nodegroup.is_default}
				<button
					onclick={() => onEdit?.(nodegroup)}
					class="text-xs text-ink-2 hover:text-action-warm-hover px-2 py-1 rounded transition-colors"
				>수정</button>
			{/if}
			{#if onDelete && !nodegroup.is_default}
				<button
					onclick={() => onDelete?.(nodegroup)}
					class="text-xs text-ink-2 hover:text-red-400 px-2 py-1 rounded transition-colors"
				>삭제</button>
			{/if}
		</div>
	</div>

	<div class="flex items-center gap-4 text-xs text-ink-2">
		<span>노드 수: <span class="text-ink-0">{nodegroup.node_count}</span></span>
		{#if nodegroup.vms.length > 0}
			<span>VM: <span class="text-ink-0">{runningVms}/{nodegroup.vms.length}</span></span>
		{/if}
		{#if nodegroup.flavor_id}
			<span class="font-mono truncate max-w-32">{nodegroup.flavor_id.slice(0, 12)}...</span>
		{/if}
	</div>

	{#if Object.keys(nodegroup.labels ?? {}).length > 0}
		<div class="flex flex-wrap gap-1">
			{#each Object.entries(nodegroup.labels) as [k, v]}
				<span class="text-xs bg-surface-selected text-ink-2 rounded px-1.5 py-0.5 font-mono">{k}={v}</span>
			{/each}
		</div>
	{/if}
</div>
