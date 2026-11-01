<script lang="ts">
	import { t } from '$lib/i18n/ns/drover-pages';
	let { reason }: { reason: string } = $props();
	const firstLine = $derived(reason.trim().split('\n')[0]);
	const summary = $derived(firstLine.length > 120 ? `${firstLine.slice(0, 120)}…` : firstLine);
</script>

<div class="min-w-0 space-y-1 text-[0.8125rem]" role="none" onclick={(event) => event.stopPropagation()} onkeydown={(event) => event.stopPropagation()}>
	<p class="break-words text-state-danger-text">{summary}</p>
	<details>
		<summary class="min-h-11 cursor-pointer py-2 text-ink-1 underline decoration-line-2 underline-offset-4 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)] md:min-h-9">{t('clusterError.details')}</summary>
		<p class="max-w-prose whitespace-pre-wrap break-words text-ink-1">{reason}</p>
		<p class="mt-2 max-w-prose text-ink-2">{t('clusterError.recovery')}</p>
	</details>
</div>
