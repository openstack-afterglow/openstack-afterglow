<script lang="ts">
	import { useContainerDetailController } from '$lib/stores/containerDetailController.svelte';

	const s = useContainerDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl overflow-hidden">
	<button
		onclick={s.toggleLogs}
		class="w-full flex items-center justify-between px-4 py-3 text-xs text-ink-2 hover:text-ink-0 transition-colors"
		data-tour="admin-containers-logs"
	>
		<span class="uppercase tracking-wide font-medium">로그</span>
		<span class="text-ink-3">{s.logsOpen ? '▲' : '▼'}</span>
	</button>
	{#if s.logsOpen}
		<div class="px-4 pb-4">
			<div class="flex justify-end mb-2">
				<button onclick={s.fetchLogs} disabled={s.logsLoading} class="text-xs text-action-warm hover:text-action-warm-hover disabled:opacity-40">
					{s.logsLoading ? '조회 중...' : '새로고침'}
				</button>
			</div>
			{#if s.logs}
				<pre class="bg-surface-canvas rounded p-3 text-xs text-ink-2 overflow-auto max-h-64 font-mono whitespace-pre-wrap">{s.logs}</pre>
			{:else}
				<div class="text-ink-3 text-xs">새로고침을 클릭하세요</div>
			{/if}
		</div>
	{/if}
</div>
