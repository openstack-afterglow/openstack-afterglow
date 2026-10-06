<script lang="ts">
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';
	import type { LayoutData } from './$types';
	import { afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import Button from '$lib/components/ui/Button.svelte';
	import { siteConfig } from '$lib/config/site';
	import { resolveLandingLogoPath } from '$lib/config/brandAssets';
	import { auth, isLoggedIn } from '$lib/stores/auth';
	import { theme, resolvedTheme } from '$lib/stores/theme';
	import { docsHref, docsLanguageHref, docsLocaleFromUrl, docsLocales, docsMessages } from '$lib/docs/locales';
	import { getLocale } from '$lib/i18n/runtime.svelte';

	let { children, data }: { children: Snippet; data: LayoutData } = $props();
	const locale = $derived(docsLocaleFromUrl($page.url));
	const messages = $derived(docsMessages[locale]);
	const docCategories = $derived(messages.categories);
	const docGuides = $derived(data.docsNavigationGuides);
	const localeName = $derived(docsLocales.find(({ id }) => id === locale)!.name);
	const consoleLabel = $derived($isLoggedIn ? messages.consoleReturn : messages.consoleAccess);
	let themeReady = $state(false);
	let mobileMenu: HTMLDetailsElement | undefined;
	let languageMenu: HTMLDetailsElement | undefined;
	$effect(() => {
		document.documentElement.lang = locale;
		return () => { document.documentElement.lang = getLocale(); };
	});
	onMount(() => { themeReady = true; });
	afterNavigate(() => {
		if (mobileMenu) mobileMenu.open = false;
		if (languageMenu) languageMenu.open = false;
	});
	function languageKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && languageMenu?.open) {
			event.preventDefault();
			languageMenu.open = false;
			languageMenu.querySelector('summary')?.focus();
		}
	}
	const consoleHref = $derived($page.data.mockup?.active ? $page.data.mockup.homePath : ($isLoggedIn ? ($auth.projectId ? '/dashboard' : '/select-project') : '/login'));
	const logoPath = $derived(resolveLandingLogoPath($siteConfig, themeReady ? $resolvedTheme : 'dark'));
	const currentSlug = $derived($page.params.slug);
	const themeLabel = $derived($theme === 'system' ? messages.themeSystem : $theme === 'dark' ? messages.themeDark : messages.themeLight);
	const themeIcons = {
		system: 'M3 4h18v13H3zM8 21h8M12 17v4',
		dark: 'M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z',
		light: 'M12 3v1m0 16v1M3 12h1m16 0h1M5.6 5.6l.7.7m11.4 11.4.7.7M5.6 18.4l.7-.7m11.4-11.4.7-.7M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
	};
</script>

<svelte:document onclick={(event) => {
	if (languageMenu?.open && event.target instanceof Node && !languageMenu.contains(event.target)) languageMenu.open = false;
}} />

{#snippet navigation()}
	<nav aria-label={messages.serviceDocs} class="docs-navigation">
		<a href={docsHref(undefined, locale, $page.url)} aria-current={!currentSlug && $page.url.pathname === '/docs' ? 'page' : undefined} class:current={!currentSlug && $page.url.pathname === '/docs'}>{messages.docsHome}</a>
		{#each docCategories as category (category.id)}
			<div class="nav-group">
				<p>{category.label}</p>
				{#each docGuides.filter((guide) => guide.category === category.id) as guide (guide.slug)}
					<a href={docsHref(guide.slug, locale, $page.url)} class:current={currentSlug === guide.slug} aria-current={currentSlug === guide.slug ? 'page' : undefined}>{guide.name}</a>
				{/each}
			</div>
		{/each}
	</nav>
{/snippet}

<div class="docs-shell" lang={locale}>
	<a href="#main-content" class="docs-skip" onclick={() => document.getElementById('main-content')?.focus()}>{messages.skip}</a>
	<header class="docs-header">
		<div class="header-inner">
			<a class="docs-brand" href="/" title={messages.homeTitle}>
				<img src={logoPath} alt="" width="28" height="28" />
				<span>{$siteConfig.site_name}</span>
			</a>
			<a class="docs-label" href={docsHref(undefined, locale, $page.url)}>Docs</a>
			<div class="header-actions">
				<a class="home-link" href="/">{messages.home}</a>
				<details class="language-menu" bind:this={languageMenu}>
					<summary aria-label={`${messages.language}: ${localeName}`} onkeydown={languageKeydown}>{localeName}<span aria-hidden="true">⌄</span></summary>
					<nav aria-label={messages.language}>
						{#each docsLocales as language (language.id)}
							<a href={docsLanguageHref($page.url, language.id)} lang={language.id} hreflang={language.id} class:current={language.id === locale} aria-current={language.id === locale ? 'page' : undefined} onkeydown={languageKeydown} onclick={() => { if (languageMenu) languageMenu.open = false; }}>{language.name}</a>
						{/each}
					</nav>
				</details>
				<Button variant="ghost" size="icon" class="min-h-11 min-w-11" ariaLabel={`${themeLabel}, ${messages.themeChange}`} title={`${themeLabel}, ${messages.themeChange}`} onclick={() => theme.toggle()}>
					<svg class="size-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d={themeIcons[$theme]} /></svg>
				</Button>
				<Button variant="primary" href={consoleHref} ariaLabel={consoleLabel} title={consoleLabel} class="min-h-11 min-w-11">
					<svg class="console-icon size-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 3H4v18h4M12 8l4 4-4 4M8 12h12" /></svg>
					<span class="console-label">{consoleLabel}</span>
				</Button>
			</div>
		</div>
	</header>
	<div class="docs-frame">
		<aside class="docs-sidebar" aria-label={messages.navigation}>
			{@render navigation()}
			<p class="sidebar-note">{messages.publicNote[0]}<br />{messages.publicNote[1]}</p>
		</aside>
		<div class="docs-workspace">
			<details class="mobile-menu" bind:this={mobileMenu}>
				<summary>{messages.menu} <span aria-hidden="true">⌄</span></summary>
				{@render navigation()}
			</details>
			<main id="main-content" tabindex="-1">{@render children()}</main>
			<footer class="docs-footer"><span>{$siteConfig.site_name} · {messages.userDocs}</span><a href="/">{messages.backHome} →</a></footer>
		</div>
	</div>
</div>

<style>
	.docs-shell { min-height: 100dvh; background: var(--color-surface-canvas); color: var(--color-ink-1); }
	.docs-skip { position: fixed; top: 0.75rem; left: 1rem; z-index: var(--z-command); padding: 0.75rem 1rem; border-radius: var(--radius-md); background: var(--color-surface-raised); color: var(--color-ink-0); transform: translateY(-200%); }
	.docs-skip:focus-visible { transform: translateY(0); box-shadow: var(--focus-ring); }
	.docs-header { position: sticky; top: 0; z-index: var(--z-header); border-bottom: 1px solid var(--color-line); background: var(--color-surface-base); }
	.header-inner { display: flex; min-height: 4rem; max-width: 90rem; align-items: center; gap: 0.75rem; margin-inline: auto; padding: 0.5rem 1rem; }
	.docs-brand { display: flex; min-width: 0; align-items: center; gap: 0.625rem; color: var(--color-ink-0); font-size: 0.875rem; font-weight: 600; text-decoration: none; }
	.docs-brand img { flex-shrink: 0; object-fit: contain; }
	.docs-brand span { display: none; overflow: hidden; max-width: 10rem; text-overflow: ellipsis; white-space: nowrap; }
	.docs-label { display: none; border-left: 1px solid var(--color-line); padding-left: 0.75rem; color: var(--color-ink-0); font-size: 0.875rem; font-weight: 600; text-decoration: none; }
	.header-actions { display: flex; margin-left: auto; flex-shrink: 0; align-items: center; gap: 0.5rem; }
	.home-link { display: none; min-height: 2.75rem; align-items: center; color: var(--color-ink-2); font-size: 0.8125rem; text-decoration: none; }
	.console-label { display: none; }
	.language-menu { position: relative; }
	.language-menu summary { display: flex; min-height: 2.75rem; align-items: center; gap: 0.5rem; padding: 0.5rem; cursor: pointer; color: var(--color-ink-1); font-size: 0.8125rem; white-space: nowrap; list-style: none; }
	.language-menu summary::-webkit-details-marker { display: none; }
	.language-menu nav { position: absolute; right: 0; top: calc(100% + 0.5rem); display: grid; min-width: 10rem; padding: 0.375rem; border: 1px solid var(--color-line); border-radius: var(--radius-md); background: var(--color-surface-raised); }
	.language-menu a { display: flex; min-height: 2.75rem; align-items: center; border-radius: var(--radius-md); padding: 0.5rem 0.75rem; color: var(--color-ink-1); font-size: 0.8125rem; text-decoration: none; }
	.language-menu a:hover, .language-menu a.current { background: var(--color-surface-selected); }
	.docs-shell:is(:lang(ja), :lang(zh-CN)) :global(:is(h1, h2, h3, p, a, li)) { word-break: normal; overflow-wrap: anywhere; }
	.docs-frame { display: grid; max-width: 90rem; gap: 1.5rem; margin-inline: auto; padding: 1rem; }
	.docs-sidebar { display: none; }
	.docs-workspace { min-width: 0; }
	.docs-navigation { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.8125rem; }
	.docs-navigation a { display: flex; min-height: 2.75rem; align-items: center; border-radius: var(--radius-md); padding: 0.5rem 0.75rem; color: var(--color-ink-2); text-decoration: none; transition: background var(--motion-duration-fast) var(--motion-ease-standard), color var(--motion-duration-fast) var(--motion-ease-standard); }
	.docs-navigation a:hover { background: var(--color-surface-sunken); color: var(--color-ink-0); }
	.docs-navigation a.current { background: var(--color-surface-selected); color: var(--color-ink-0); font-weight: 600; }
	.nav-group { margin-top: 1.25rem; }
	.nav-group p { margin: 0 0 0.375rem; padding-inline: 0.75rem; color: var(--color-ink-1); font-size: 0.75rem; font-weight: 600; }
	.sidebar-note { margin: 1.5rem 0 0; border-top: 1px solid var(--color-line); padding: 1rem 0.75rem; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.6; }
	.mobile-menu { margin-bottom: 1.5rem; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-base); }
	.mobile-menu summary { display: flex; min-height: 2.75rem; align-items: center; justify-content: space-between; padding: 0.75rem 1rem; cursor: pointer; font-size: 0.8125rem; font-weight: 500; }
	.mobile-menu[open] summary { border-bottom: 1px solid var(--color-line); }
	.mobile-menu .docs-navigation { max-height: 60dvh; overflow-y: auto; padding: 0.75rem; }
	main { min-width: 0; scroll-margin-top: 5rem; }
	main:focus-visible { outline: none; box-shadow: var(--focus-ring); }
	.docs-footer { display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; justify-content: space-between; align-items: center; margin-top: 4rem; border-top: 1px solid var(--color-line); padding-block: 1rem; color: var(--color-ink-2); font-size: 0.75rem; }
	.docs-footer a { display: inline-flex; min-height: 2.75rem; align-items: center; color: var(--color-ink-1); text-decoration: none; }
	a:focus-visible, summary:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: var(--radius-md); }
	@media (min-width: 40rem) { .docs-brand span, .docs-label, .console-label { display: block; } .console-icon { display: none; } }
	@media (min-width: 48rem) {
		.header-inner { padding-inline: 1.5rem; }
		.home-link { display: flex; }
		.docs-frame { grid-template-columns: 14rem minmax(0, 1fr); padding: 1.5rem; gap: 2rem; }
		.docs-sidebar { position: sticky; top: 5.5rem; display: block; align-self: start; max-height: calc(100dvh - 6.5rem); overflow-y: auto; }
		.mobile-menu { display: none; }
	}
</style>
