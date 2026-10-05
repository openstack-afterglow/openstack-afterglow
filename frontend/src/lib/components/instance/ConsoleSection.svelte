<script lang="ts">
	import { useInstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
	import { t } from '$lib/i18n/ns/instance';

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
		<h2 class="text-sm font-semibold text-ink-2 uppercase tracking-wide">{t('console.title')}</h2>
		<div class="flex gap-2 items-center">
			{#if showLog}
				<span class="text-xs text-ink-2">{t('console.autoRefresh', { seconds: s.consolePollAr.intervalSeconds })}</span>
				<button
					onclick={s.toggleFullLog}
					class="text-xs {s.logFull ? 'text-yellow-400 border-yellow-900' : 'text-ink-2 border-line-2'} hover:text-ink-1 px-2 py-1 border hover:border-line-2 rounded transition-colors"
				>
					{s.logFull ? t('console.recentLines') : t('console.fullLog')}
				</button>
				<a
					href="/dashboard/compute/instances/{s.instance!.id}/console-log"
					target="_blank"
					rel="noopener noreferrer"
					class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors"
					title={t('console.newWindowTitle')}
				>
					{t('console.newWindow')}
				</a>
				<button
					onclick={() => s.loadConsoleLog(s.logFull)}
					disabled={s.logLoading}
					class="text-xs text-ink-2 hover:text-ink-1 px-2 py-1 border border-line-2 hover:border-line-2 rounded transition-colors disabled:text-ink-3"
				>
					{s.logLoading ? t('console.loading') : t('console.refresh')}
				</button>
			{/if}
			<button
				onclick={toggleLog}
				class="text-xs text-warm-text hover:text-warm-text-hover transition-colors"
			>
				{showLog ? t('console.close') : t('console.viewLog')}
			</button>
		</div>
	</div>
	{#if showLog}
		<pre
			bind:this={logPreEl}
			class="bg-surface-canvas border border-line rounded p-3 text-xs text-ink-2 font-mono overflow-x-auto max-h-96 overflow-y-auto whitespace-pre-wrap"
		>{s.logLoading && !s.consoleLog ? t('console.loadingContent') : s.consoleLog}</pre>
	{/if}
</div>
