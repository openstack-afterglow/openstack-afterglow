<script lang="ts">
	import type { K3sProgressController } from '$lib/stores/k3sProgress.svelte';

	let {
		controller,
		activeSteps,
		onClose,
		onViewCluster,
	}: {
		controller: K3sProgressController;
		activeSteps: { id: string; label: string }[];
		onClose: () => void;
		onViewCluster: (clusterId: string) => void;
	} = $props();
</script>

<div class="fixed inset-0 bg-surface-scrim/70 flex items-center justify-center z-50">
	<div data-tour="drover-progress" class="bg-surface-base border border-line-2 rounded-xl p-6 w-full max-w-md mx-4 shadow-[var(--shadow-restraint)]">
		<h2 class="text-lg font-semibold text-ink-0 mb-4">
			{controller.mode === 'delete' ? 'Drover 클러스터 삭제' : 'Drover 클러스터 생성'}
		</h2>
		<!-- 스텝 표시 -->
		<div class="space-y-2 mb-4">
			{#each activeSteps as step}
				{@const isCurrent = controller.step === step.id}
				{@const isDone = activeSteps.findIndex(s => s.id === controller.step) > activeSteps.findIndex(s => s.id === step.id)}
				{@const stepTime = controller.stepTimings[step.id]}
				<div class="flex items-center gap-2 text-sm {isDone ? 'text-green-400' : isCurrent ? 'text-action-warm' : 'text-ink-3'}">
					<span class="w-4 h-4 flex items-center justify-center flex-shrink-0">
						{#if isDone}✓{:else if isCurrent}<span class="animate-pulse">●</span>{:else}○{/if}
					</span>
					<span class="flex-1">{step.label}</span>
					{#if isDone && stepTime != null}
						<span class="text-xs opacity-60">{stepTime}s~</span>
					{:else if isCurrent && controller.elapsedSeconds > 0}
						<span class="text-xs opacity-60">{controller.elapsedSeconds}s</span>
					{/if}
				</div>
			{/each}
		</div>
		<!-- 진행 바 -->
		<div class="bg-surface-sunken rounded-full h-2 mb-3">
			<div class="bg-action-warm h-2 rounded-full transition-all duration-500" style="width: {controller.pct}%"></div>
		</div>
		<div class="flex items-center justify-between mb-4">
			<p class="text-sm text-ink-2">{controller.msg}</p>
			{#if controller.elapsedSeconds > 0}
				<span class="text-xs text-ink-3 flex-shrink-0 ml-2">경과 {controller.elapsedSeconds}초</span>
			{/if}
		</div>
		{#if controller.error}
			<div class="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2 mb-4">{controller.error}</div>
		{/if}
		{#if controller.isTerminal}
			<div class="flex justify-end gap-3">
				<button onclick={onClose}
					class="px-4 py-2 text-sm text-ink-2 hover:text-ink-0 transition-colors">닫기</button>
				{#if controller.createdClusterId && controller.step === 'completed' && controller.mode === 'create'}
					<button
						onclick={() => onViewCluster(controller.createdClusterId!)}
						class="px-5 py-2 bg-action-warm hover:bg-action-warm-hover text-action-on-warm text-sm font-medium rounded-lg transition-colors">
						클러스터 보기
					</button>
				{/if}
			</div>
		{:else}
			<div class="flex items-center justify-between">
				<p class="text-xs text-ink-3">백그라운드에서 계속 진행됩니다.</p>
				<button onclick={onClose}
					class="px-3 py-1.5 text-xs text-ink-3 hover:text-ink-0 transition-colors border border-line-2 rounded-lg hover:bg-surface-sunken">
					닫기
				</button>
			</div>
		{/if}
	</div>
</div>
