<script lang="ts">
	import type { DocScreenshot } from '$lib/docs/types';
	import { docsMessages, type DocsLocale } from '$lib/docs/locales';

	let { screenshot, locale }: { screenshot: DocScreenshot; locale: DocsLocale } = $props();
	const messages = $derived(docsMessages[locale]);
</script>

<figure class="doc-screenshot">
	<a href={screenshot.src} target="_blank" rel="noopener noreferrer" aria-label={messages.screenshotOpenLabel(screenshot.alt)}>
		<img src={screenshot.src} alt={screenshot.alt} width={screenshot.width} height={screenshot.height} loading="lazy" decoding="async" />
		<span class="original-hint">{messages.screenshotOpen}<span aria-hidden="true"> ↗</span></span>
	</a>
	<figcaption>
		<p class="caption">{screenshot.caption}</p>
		<p class="language-note">{messages.screenshotKoreanNote}</p>
	</figcaption>
</figure>

<style>
	.doc-screenshot { min-width: 0; max-width: 100%; margin: 1.25rem 0; overflow-wrap: anywhere; }
	a { display: block; width: fit-content; max-width: 100%; color: var(--color-accent); text-decoration: none; border-radius: var(--radius-lg); }
	a:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	img { display: block; box-sizing: border-box; max-width: 100%; height: auto; border: 1px solid var(--color-line); border-radius: var(--radius-lg); }
	.original-hint { display: flex; align-items: center; min-height: 2.75rem; font-size: 0.75rem; line-height: 1.6; text-decoration: underline; text-underline-offset: 0.25rem; }
	figcaption { font-size: 0.75rem; line-height: 1.6; }
	.caption { margin: 0 0 0.25rem; color: var(--color-ink-1); }
	.language-note { margin: 0; color: var(--color-ink-2); }
</style>
