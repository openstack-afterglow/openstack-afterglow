<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

	const s = useInstanceDetailController();

	let showLog = $state(false);
	let logPreEl = $state<HTMLPreElement | null>(null);

	$effect(() => {
		if (s.consoleLog && logPreEl) {
			logPreEl.scrollTop = logPreEl.scrollHeight;
		}
	});

	async function toggleLog() {
		showLog = !showLog;
		s.consolePollAr.active = showLog;
		if (showLog) await s.loadConsoleLog(s.logFull);
	}
</script>

<div class="bg-surface-base border border-line rounded-lg p-6 mb-4">
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">콘솔 로그</h2>
		<div class="flex gap-2 items-center">
			{#if showLog}
				<span class="text-xs text-ink-3">{s.consolePollAr.intervalSeconds}초마다 자동 갱신</span>
				<button
					onclick={s.toggleFullLog}
					class="text-xs {s.logFull ? 'text-yellow-400 border-yellow-900' : 'text-ink-2 border-line-2'} hover:text-ink-1 px-2 py-1 border hover:border-line-2 rounded transition-colors"
				>
					{s.logFull ? '최근 200줄' : '전체 로그'}
				</button>
				<a
					href="/dashboard/compute/instances/{s.instance!.id}/console-log"
					target="_blank"
					rel="noopener noreferrer"
					class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors"
					title="새 창에서 전체 로그 보기"
				>
					새 창에서 보기 ↗
				</a>
				<button
					onclick={() => s.loadConsoleLog(s.logFull)}
					disabled={s.logLoading}
					class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors disabled:text-ink-3"
				>
					{s.logLoading ? '로딩...' : '새로고침'}
				</button>
			{/if}
			<button
				onclick={toggleLog}
				class="text-xs text-action-warm hover:text-action-warm-hover transition-colors"
			>
				{showLog ? '닫기' : '로그 보기'}
			</button>
		</div>
	</div>
	{#if showLog}
		<pre
			bind:this={logPreEl}
			class="bg-surface-canvas border border-line rounded p-3 text-xs text-ink-2 font-mono overflow-x-auto max-h-96 overflow-y-auto whitespace-pre-wrap"
		>{s.logLoading && !s.consoleLog ? '로딩 중...' : s.consoleLog}</pre>
	{/if}
</div>
