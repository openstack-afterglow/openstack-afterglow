<script lang="ts">
	import Button from '$lib/components/ui/Button.svelte';
	import type { DocCommand } from '$lib/docs/types';
	import type { DocsLocale } from '$lib/docs/locales';
	import { docsMessages } from '$lib/docs/locales';

	let { command, locale }: { command: DocCommand; locale: DocsLocale } = $props();
	const messages = $derived(docsMessages[locale]);
	let status = $state('');
	let feedbackRevision = 0;
	$effect(() => { command; locale; feedbackRevision += 1; status = ''; });
	async function copy() {
		const code = command.code;
		const copiedRevision = feedbackRevision;
		try {
			await navigator.clipboard.writeText(code);
			if (feedbackRevision === copiedRevision) status = messages.copySuccess;
		} catch {
			if (feedbackRevision === copiedRevision) status = messages.copyFailure;
		}
	}
</script>

<div class="code-block">
	<div class="code-heading"><span>{command.label}</span><Button variant="ghost" size="sm" class="min-h-11" ariaLabel={messages.copyLabel(command.label)} onclick={copy}>{messages.copy}</Button></div>
	<pre role="region" aria-label={command.label} tabindex="0"><code>{command.code}</code></pre>
	{#if status}<p role="status" class="copy-status">{status}</p>{/if}
</div>

<style>
	.code-block { min-width: 0; margin-block: 1rem; overflow: hidden; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-sunken); }
	.code-heading { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.25rem 0.75rem; border-bottom: 1px solid var(--color-line); color: var(--color-ink-2); font-size: 0.75rem; }
	.code-heading span { min-width: 0; overflow-wrap: anywhere; }
	pre { max-width: 100%; margin: 0; overflow-x: auto; padding: 1rem; color: var(--color-ink-0); font-family: var(--font-mono); font-size: 0.8125rem; line-height: 1.7; }
	pre:focus-visible { outline: none; box-shadow: inset 0 0 0 2px var(--color-accent); }
	.copy-status { margin: 0; padding: 0 1rem 0.75rem; color: var(--color-ink-1); font-size: 0.75rem; line-height: 1.5; }
</style>
