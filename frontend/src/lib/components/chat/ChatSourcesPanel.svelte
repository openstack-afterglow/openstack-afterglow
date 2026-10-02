<script lang="ts">
	import SlidePanel from '$lib/components/SlidePanel.svelte';
	import { citationDomain, citationLabel, type Citation } from '$lib/api/chatCitations';
	import { t } from '$lib/i18n/ns/chat-panel';

	interface Props {
		open: boolean;
		citations: Citation[];
		onClose: () => void;
	}
	let { open, citations, onClose }: Props = $props();
</script>

{#if open}
	<SlidePanel {onClose} width="w-full md:w-[24rem] max-w-full" resizable={false} ariaLabel={t('sources.ariaLabel')}>
		<section id="chat-sources-panel" class="px-4 pb-6" aria-labelledby="chat-sources-heading">
			<h2 id="chat-sources-heading" class="text-base font-semibold text-ink-0">{t('sources.title', { count: citations.length })}</h2>
			<p class="mt-2 text-xs leading-relaxed text-ink-2">{t('sources.description')}</p>
			{#if citations.length === 0}
				<p class="py-8 text-sm leading-relaxed text-ink-2">{t('sources.empty')}</p>
			{:else}
				<ol class="mt-4 divide-y divide-line">
					{#each citations as c, i (`${c.source_kind}:${c.url ?? c.document_index}:${i}`)}
						<li class="py-4">
							<div class="mb-2 flex items-center gap-2 text-xs text-ink-2">
								<span class="font-mono tabular-nums">{i + 1}</span>
								<span>{citationDomain(c.url)}</span>
							</div>
							{#if c.url}
								<a class="source-link" href={c.url} target="_blank" rel="noopener noreferrer nofollow">
									<span class="text-sm font-medium leading-relaxed">{citationLabel(c)}</span>
									<span class="mt-1 block break-all text-xs font-normal text-ink-2">{c.url}</span>
								</a>
							{:else}
								<p class="text-sm font-medium leading-relaxed text-ink-0">{citationLabel(c)}</p>
							{/if}
							{#if c.snippet}
								<p class="mt-2 whitespace-pre-line break-words text-sm leading-relaxed text-ink-2">{c.snippet}</p>
							{/if}
						</li>
					{/each}
				</ol>
			{/if}
		</section>
	</SlidePanel>
{/if}

<style>
	.source-link {
		display: block;
		min-block-size: 2.75rem;
		border-radius: 0.375rem;
		color: var(--color-accent);
		overflow-wrap: anywhere;
		text-decoration: none;
	}
	.source-link:visited { color: var(--color-accent-2); }
	.source-link:hover { text-decoration: underline; }
	.source-link:focus-visible { outline: none; box-shadow: var(--focus-ring); }
</style>
