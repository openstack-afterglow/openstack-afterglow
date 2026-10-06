<script lang="ts">
	import { page } from '$app/stores';
	import type { PageData } from './$types';
	import Button from '$lib/components/ui/Button.svelte';
	import Field from '$lib/components/ui/Field.svelte';
	import TextInput from '$lib/components/ui/TextInput.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import { siteConfig } from '$lib/config/site';
	import { createDocSearchIndex, searchDocGuides } from '$lib/docs/catalog';
	import { docsHref, docsLocales, docsMessages } from '$lib/docs/locales';

	let { data }: { data: PageData } = $props();
	let query = $state('');
	const locale = $derived(data.docsLocale);
	const messages = $derived(docsMessages[locale]);
	const localeName = $derived(docsLocales.find(({ id }) => id === locale)!.name);
	const searchIndex = $derived(createDocSearchIndex(data.guides));
	const results = $derived(searchDocGuides(query, searchIndex));
</script>

<svelte:head>
	<title>Docs · {messages.guideTitle} | {$siteConfig.site_name}</title>
	<meta name="description" content={messages.indexDescription} />
</svelte:head>

<div class="docs-index">
	<header class="intro">
		<p class="eyebrow">{messages.userDocs}</p>
		<h1>{messages.heroTitle[0]}<br />{messages.heroTitle[1]}</h1>
		<p class="intro-copy">{messages.heroCopy[0]}<br />{messages.heroCopy[1]}</p>
		<Button variant="primary" href={docsHref('getting-started', locale, $page.url)} class="min-h-11 mt-6">{messages.getStarted} →</Button>
	</header>
	<div class="search-area">
		<Field for="docs-search" label={messages.searchLabel} help={messages.searchHelp}>
			<TextInput id="docs-search" type="search" bind:value={query} placeholder={messages.searchPlaceholder} class="min-h-11" />
		</Field>
		<p role="status" class="search-count">{query.trim() ? messages.resultsCount(results.length) : messages.guideCount(data.guides.length)} · {localeName}</p>
	</div>
	{#if results.length === 0}
		<EmptyState headline={messages.noResultsTitle} description={messages.noResultsDescription}>
			{#snippet cta()}<Button variant="secondary" onclick={() => { query = ''; }} class="min-h-11">{messages.resetSearch}</Button>{/snippet}
		</EmptyState>
	{:else}
		{#each messages.categories as category (category.id)}
			{@const guides = results.filter((guide) => guide.category === category.id)}
			{#if guides.length > 0}
				<section class="guide-group" aria-labelledby={`category-${category.id}`}>
					<div class="group-heading"><h2 id={`category-${category.id}`}>{category.label}</h2><p>{category.description}</p></div>
					<div class="guide-list">
						{#each guides as guide (guide.slug)}
							<a href={docsHref(guide.slug, locale, $page.url)} class="guide-link">
								<div class="guide-name"><h3>{guide.name}</h3><span aria-hidden="true">↗</span></div>
								<p class="guide-title">{guide.title}</p>
								<p class="guide-summary">{guide.summary}</p>
							</a>
						{/each}
					</div>
				</section>
			{/if}
		{/each}
	{/if}
	<p class="availability-note">{messages.availability}</p>
</div>

<style>
	.docs-index { max-width: 64rem; margin-inline: auto; }
	.intro { padding: 1rem 0 2.5rem; border-bottom: 1px solid var(--color-line); }
	.eyebrow { margin: 0 0 1rem; color: var(--color-warm-text); font-size: 0.75rem; font-weight: 600; }
	h1 { margin: 0; color: var(--color-ink-0); font-family: var(--font-display); font-size: clamp(1.875rem, 4vw, 3rem); font-weight: 500; line-height: 1.3; letter-spacing: -0.03em; word-break: keep-all; }
	.intro-copy { margin: 1.25rem 0 0; color: var(--color-ink-2); font-size: 0.875rem; line-height: 1.8; word-break: keep-all; }
	.search-area { display: grid; gap: 0.75rem; margin-block: 2rem; }
	.search-count { margin: 0; color: var(--color-ink-2); font-size: 0.75rem; }
	.guide-group { margin-top: 2.5rem; }
	.group-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.5rem 1rem; margin-bottom: 1rem; }
	h2 { margin: 0; color: var(--color-ink-0); font-size: 1.25rem; font-weight: 600; }
	.group-heading p { margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.6; }
	.guide-list { display: grid; border: 1px solid var(--color-line); border-radius: var(--radius-lg); overflow: hidden; background: var(--color-surface-base); }
	.guide-link { min-width: 0; padding: 1.25rem; border-bottom: 1px solid var(--color-line); text-decoration: none; transition: background var(--motion-duration-fast) var(--motion-ease-standard); }
	.guide-link:last-child { border-bottom: 0; }
	.guide-link:hover { background: var(--color-surface-selected); }
	.guide-link:focus-visible { outline: none; box-shadow: inset 0 0 0 2px var(--color-accent); }
	.guide-name { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
	h3 { margin: 0; color: var(--color-ink-0); font-size: 0.875rem; font-weight: 600; }
	.guide-name span { color: var(--color-ink-2); }
	.guide-title { margin: 0.5rem 0 0; color: var(--color-ink-1); font-size: 0.8125rem; font-weight: 500; line-height: 1.6; }
	.guide-summary { margin: 0.375rem 0 0; color: var(--color-ink-2); font-size: 0.8125rem; line-height: 1.7; word-break: keep-all; }
	.availability-note { margin-top: 2.5rem; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.7; }
	@media (min-width: 64rem) {
		.guide-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		.guide-link { border-bottom: 1px solid var(--color-line); }
		.guide-link:nth-child(odd):not(:last-child) { border-right: 1px solid var(--color-line); }
		.guide-link:nth-last-child(2):nth-child(odd) { border-bottom: 0; }
		.guide-link:last-child:nth-child(odd) { grid-column: 1 / -1; }
	}
</style>
