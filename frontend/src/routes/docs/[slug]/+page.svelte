<script lang="ts">
	import { page } from '$app/stores';
	import Button from '$lib/components/ui/Button.svelte';
	import Alert from '$lib/components/ui/Alert.svelte';
	import DocCodeBlock from '$lib/components/docs/DocCodeBlock.svelte';
	import { siteConfig } from '$lib/config/site';
	import { docsContentHref, docsHref, docsMessages } from '$lib/docs/locales';
	import type { DocLink } from '$lib/docs/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
	const guide = $derived(data.guide);
	const locale = $derived(data.docsLocale);
	const messages = $derived(docsMessages[locale]);
	const outline = $derived([
		{ id: 'prerequisites', title: messages.prerequisites },
		...guide.sections.map(({ id, title }) => ({ id, title })),
		{ id: 'console', title: messages.consoleUsage },
		{ id: 'related', title: messages.related },
	]);
</script>

<svelte:head>
	<title>{guide.name} · {messages.guideTitle} | {$siteConfig.site_name}</title>
	<meta name="description" content={guide.summary} />
</svelte:head>

{#snippet links(items: DocLink[])}
	<ul class="content-links">
		{#each items as link (link.href)}
			<li><a href={docsContentHref(link.href, locale, $page.url)} target={link.href.startsWith('https://') ? '_blank' : undefined} rel={link.href.startsWith('https://') ? 'noreferrer' : undefined}>{link.label}<span aria-hidden="true"> →</span></a>{#if link.description}<p>{link.description}</p>{/if}</li>
		{/each}
	</ul>
{/snippet}
{#snippet tableOfContents()}
	<nav aria-label={messages.toc}><ul>{#each outline as item (item.id)}<li><a href={`#${item.id}`}>{item.title}</a></li>{/each}</ul></nav>
{/snippet}

<div class="guide-frame">
	<article class="guide-article" aria-labelledby="guide-title">
		<header class="article-heading">
			<nav aria-label={messages.breadcrumbs} class="breadcrumbs"><a href={docsHref(undefined, locale, $page.url)}>Docs</a><span aria-hidden="true">/</span><span>{guide.name}</span></nav>
			<p class="guide-name">{guide.name}</p>
			<h1 id="guide-title">{guide.title}</h1>
			<p class="guide-summary">{guide.summary}</p>
		</header>
		<details class="inline-outline"><summary>{messages.toc}</summary>{@render tableOfContents()}</details>
		<section id="prerequisites" aria-labelledby="prerequisites-title">
			<h2 id="prerequisites-title">{messages.prerequisites}</h2>
			<ul>{#each guide.prerequisites as prerequisite}<li>{prerequisite}</li>{/each}</ul>
		</section>
		{#each guide.sections as section (section.id)}
			<section id={section.id} aria-labelledby={`${section.id}-title`}>
				<h2 id={`${section.id}-title`}>{section.title}</h2>
				{#each section.paragraphs ?? [] as paragraph}<p>{paragraph}</p>{/each}
				{#if section.bullets}<ul>{#each section.bullets as bullet}<li>{bullet}</li>{/each}</ul>{/if}
				{#if section.steps}
					<ol class="guide-steps">
						{#each section.steps as step}
							<li><h3>{step.title}</h3>{#each step.text as paragraph}<p>{paragraph}</p>{/each}{#if step.command}<DocCodeBlock command={step.command} {locale} />{/if}{#if step.links}{@render links(step.links)}{/if}</li>
						{/each}
					</ol>
				{/if}
				{#each section.commands ?? [] as command}<DocCodeBlock {command} {locale} />{/each}
				{#if section.callout}<div class="section-callout"><Alert tone={section.callout.tone} title={section.callout.title}>{section.callout.text}</Alert></div>{/if}
				{#if section.links}{@render links(section.links)}{/if}
			</section>
		{/each}
		<section id="console" aria-labelledby="console-title">
			<h2 id="console-title">{messages.consoleUsage}</h2>
			<p>{messages.consoleNote}</p>
			<div class="console-actions">
				{#each guide.consoleLinks as link (link.href)}
					{@const enabled = !link.service || Boolean(($siteConfig.services as Record<string, boolean>)[link.service])}
					<div>
						<Button variant="secondary" href={link.href} disabled={!enabled} class="min-h-11">{link.label} →</Button>
						{#if link.description}<p class="service-note">{link.description}</p>{/if}
						{#if !enabled}<p class="service-note">{messages.serviceUnavailable}</p>{/if}
					</div>
				{/each}
			</div>
		</section>
		<section id="related" aria-labelledby="related-title">
			<h2 id="related-title">{messages.related}</h2>
			<ul class="related-guides">{#each data.relatedGuides as related (related.slug)}<li><a href={docsHref(related.slug, locale, $page.url)}><strong>{related.name}</strong><span>{related.title}</span><span aria-hidden="true">→</span></a></li>{/each}</ul>
			{#if guide.externalLinks}<h3 class="official-heading">{messages.official}</h3>{@render links(guide.externalLinks)}{/if}
		</section>
	</article>
	<aside class="desktop-outline" aria-label={messages.toc}><p>{messages.inThisArticle}</p>{@render tableOfContents()}</aside>
</div>

<style>
	.guide-frame { display: grid; min-width: 0; gap: 2rem; }
	.guide-article { min-width: 0; max-width: 46rem; width: 100%; margin-inline: auto; font-size: 0.875rem; line-height: 1.85; overflow-wrap: anywhere; }
	.article-heading { padding: 0.5rem 0 2rem; border-bottom: 1px solid var(--color-line); }
	.breadcrumbs { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; color: var(--color-ink-2); font-size: 0.75rem; }
	.breadcrumbs a { color: var(--color-ink-2); }
	.guide-name { margin: 1.5rem 0 0.5rem; color: var(--color-warm-text); font-size: 0.75rem; font-weight: 600; }
	h1 { margin: 0; color: var(--color-ink-0); font-family: var(--font-display); font-size: clamp(1.5rem, 3vw, 2.25rem); font-weight: 500; line-height: 1.4; letter-spacing: -0.025em; word-break: keep-all; }
	.guide-summary { margin: 1rem 0 0; color: var(--color-ink-2); }
	section { padding-block: 1.75rem; border-bottom: 1px solid var(--color-line); scroll-margin-top: 5.5rem; }
	section:last-child { border-bottom: 0; }
	h2 { margin: 0 0 1rem; color: var(--color-ink-0); font-size: 1.25rem; font-weight: 600; line-height: 1.5; }
	h3 { margin: 0 0 0.375rem; color: var(--color-ink-0); font-size: 0.875rem; font-weight: 600; }
	p { margin: 0.75rem 0; }
	ul, ol { margin: 0.75rem 0; padding-left: 1.25rem; }
	ul { list-style: disc; }
	ol { list-style: decimal; }
	li { padding-left: 0.25rem; margin-block: 0.5rem; }
	.guide-steps > li { margin-block: 1.25rem; }
	.guide-steps > li::marker { color: var(--color-ink-2); font-weight: 600; }
	.section-callout { margin-top: 1rem; }
	.content-links { display: grid; gap: 0.5rem; padding: 0; list-style: none; }
	.content-links li { margin: 0; padding: 0; }
	.content-links a { display: inline-flex; min-height: 2.75rem; align-items: center; color: var(--color-accent); font-size: 0.8125rem; text-decoration: underline; text-underline-offset: 0.25rem; }
	.content-links p { margin: 0; color: var(--color-ink-2); font-size: 0.8125rem; }
	.console-actions { display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1rem; }
	.service-note { max-width: 15rem; margin: 0.5rem 0 0; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.6; }
	.related-guides { margin: 1rem 0; padding: 0; list-style: none; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-base); overflow: hidden; }
	.related-guides li { margin: 0; padding: 0; border-bottom: 1px solid var(--color-line); }
	.related-guides li:last-child { border-bottom: 0; }
	.related-guides a { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.25rem 1rem; padding: 0.875rem 1rem; color: var(--color-ink-1); text-decoration: none; }
	.related-guides a:hover { background: var(--color-surface-selected); }
	.related-guides strong { color: var(--color-ink-0); font-size: 0.8125rem; font-weight: 600; }
	.related-guides span:first-of-type { grid-column: 1; color: var(--color-ink-2); font-size: 0.8125rem; }
	.related-guides span:last-of-type { grid-column: 2; grid-row: 1 / 3; align-self: center; }
	.official-heading { margin-top: 1.5rem; }
	.inline-outline { margin-top: 1.5rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-base); }
	.inline-outline summary { min-height: 2.75rem; padding: 0.75rem 1rem; cursor: pointer; font-size: 0.8125rem; font-weight: 500; }
	.inline-outline nav { padding: 0 0.75rem 0.75rem; }
	.inline-outline ul, .desktop-outline ul { margin: 0; padding: 0; list-style: none; }
	.inline-outline li, .desktop-outline li { margin: 0; padding: 0; }
	.inline-outline a, .desktop-outline a { display: flex; min-height: 2.75rem; align-items: center; padding: 0.375rem 0.5rem; border-radius: var(--radius-md); color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.6; text-decoration: none; }
	.inline-outline a:hover, .desktop-outline a:hover { color: var(--color-ink-0); background: var(--color-surface-selected); }
	.desktop-outline { display: none; }
	a:focus-visible, summary:focus-visible { outline: none; border-radius: var(--radius-md); box-shadow: var(--focus-ring); }
	@media (min-width: 64rem) {
		.guide-frame { grid-template-columns: minmax(0, 1fr) 10rem; gap: 1.5rem; }
		.inline-outline { display: none; }
		.desktop-outline { position: sticky; top: 5.5rem; display: block; align-self: start; max-height: calc(100dvh - 6.5rem); overflow-y: auto; border-left: 1px solid var(--color-line); padding-left: 0.75rem; }
		.desktop-outline > p { margin: 0 0 0.75rem; padding-left: 0.5rem; color: var(--color-ink-1); font-size: 0.75rem; font-weight: 600; }
	}
</style>
