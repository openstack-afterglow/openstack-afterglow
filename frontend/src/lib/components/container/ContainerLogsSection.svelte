<script lang="ts">
	import { t } from '$lib/i18n/ns/containers-shell';
	import { useContainerDetailController } from '$lib/stores/containerDetailController.svelte';

	const s = useContainerDetailController();
</script>

<div class="bg-surface-base border border-line rounded-xl overflow-hidden">
	<button
		onclick={s.toggleLogs}
		class="w-full flex items-center justify-between px-4 py-3 text-xs text-ink-2 hover:text-ink-0 transition-colors"
		data-tour="admin-containers-logs"
	>
		<span class="uppercase tracking-wide font-medium">{t('container.logs')}</span>
		<span class="text-ink-2">{s.logsOpen ? '▲' : '▼'}</span>
	</button>
	{#if s.logsOpen}
		<div class="px-4 pb-4">
			<div class="flex justify-end mb-2">
				<button onclick={s.fetchLogs} disabled={s.logsLoading} class="text-xs text-warm-text hover:text-warm-text-hover disabled:opacity-40">
					{s.logsLoading ? t('container.fetching') : t('container.refresh')}
				</button>
			</div>
			{#if s.logs}
				<pre class="bg-surface-canvas rounded p-3 text-xs text-ink-2 overflow-auto max-h-64 font-mono whitespace-pre-wrap">{s.logs}</pre>
			{:else}
				<div class="text-ink-2 text-xs">{t('container.clickRefresh')}</div>
			{/if}
		</div>
	{/if}
</div>
