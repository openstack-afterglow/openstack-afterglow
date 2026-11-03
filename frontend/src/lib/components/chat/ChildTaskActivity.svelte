<script lang="ts">
	import type { RunActivityItem } from '$lib/api/chatRunReducer';
	import Pill from '$lib/components/ui/Pill.svelte';
	import { t } from '$lib/i18n/ns/chat-panel';
	import { intlLocale } from '$lib/i18n/runtime.svelte';

	let { item }: { item: Extract<RunActivityItem, { kind: 'child' }> } = $props();
	const title = $derived(t('childTask.title', { index: item.ordinal === null ? item.childRunId : new Intl.NumberFormat(intlLocale()).format(item.ordinal + 1) }));
	const label = $derived(item.status === 'completed' ? t('toolCall.completed') : item.status === 'failed' ? t('toolCall.failed') : item.status === 'canceled' ? t('childTask.canceled') : t('childTask.requested'));
	const tone = $derived(item.status === 'completed' ? 'success' : item.status === 'failed' ? 'danger' : item.status === 'canceled' ? 'warning' : 'neutral');
</script>

<section class="min-w-0 space-y-2 break-words text-sm" aria-label={title}>
	<div class="flex flex-wrap items-center gap-2"><span class="font-medium text-ink-1">{title}</span><Pill {tone} size="xs">{label}</Pill></div>
	{#if item.summary}
		<div class="max-h-48 overflow-y-auto whitespace-pre-wrap text-ink-1" tabindex="0" role="textbox" aria-readonly="true" aria-multiline="true" aria-label={t('toolCall.result')}>{item.summary}</div>
	{/if}
	{#if item.errorCode}<p class="break-all text-xs text-state-danger-text">{t('toolCall.errorCode')}: <code>{item.errorCode}</code></p>{/if}
	{#if item.artifacts.length}
		<ul class="space-y-1" aria-label={t('toolCall.generatedFiles')}>
			{#each item.artifacts as artifact, index (`${artifact.asset_id}:${index}`)}
				<li><a class="inline-flex min-h-11 flex-col justify-center break-all text-accent underline underline-offset-2 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]" href={`/lumen/sources/assets/${encodeURIComponent(artifact.asset_id)}`}>
					<span>{artifact.name}</span><span class="text-xs text-ink-2">{artifact.mime_type} · {new Intl.NumberFormat(intlLocale()).format(artifact.size_bytes)} B</span>
				</a></li>
			{/each}
		</ul>
	{/if}
	<details>
		<summary class="flex min-h-11 cursor-pointer items-center text-xs text-ink-2 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]">{t('childTask.details')}</summary>
		<dl class="grid min-w-0 gap-1 break-all text-xs md:grid-cols-[max-content_minmax(0,1fr)]">
			<dt class="text-ink-2">child_run_id</dt><dd class="font-mono text-ink-1">{item.childRunId}</dd>
			<dt class="text-ink-2">call_id</dt><dd class="font-mono text-ink-1">{item.callId}</dd>
			<dt class="text-ink-2">wait_group_id</dt><dd class="font-mono text-ink-1">{item.waitGroupId}</dd>
			{#if item.agentId !== null}<dt class="text-ink-2">{t('input.agent')}</dt><dd class="font-mono text-ink-1">{item.agentId}</dd>{/if}
			{#if item.access}<dt class="text-ink-2">{t('childTask.access')}</dt><dd class="text-ink-1">{item.access === 'write' ? t('childTask.write') : t('childTask.read')}</dd>{/if}
			{#if item.initialStatus}<dt class="text-ink-2">{t('childTask.initialStatus')}</dt><dd class="text-ink-1">{item.initialStatus === 'waiting_resource' ? t('childTask.waitingResource') : t('childTask.queued')}</dd>{/if}
		</dl>
	</details>
</section>
