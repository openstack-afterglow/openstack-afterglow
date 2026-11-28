<script lang="ts">
	import type { Snippet } from 'svelte';
	import { resolvedTheme } from '$lib/stores/theme';
	import { t } from '$lib/i18n/ns/public-entry';
	import type { EntryNavLink } from './entryNav';

	/**
	 * The one public-entry bar: landing, every AuthStudioShell surface and the console entry overlay render
	 * this same bar, so a route scene only fades what differs (the console action) instead of rebuilding it.
	 */
	interface Props {
		siteName: string;
		logoPath: string;
		/** Section links; the landing passes in-page anchors, other surfaces the same links on `/`. */
		links?: EntryNavLink[];
		/** `href` of the link to mark as the current location. */
		activeHref?: string;
		/** Right side: console action, locale, theme. */
		actions?: Snippet;
		/** Overlay copy of the same bar: no actions, not interactive. */
		decorative?: boolean;
		/** Scene marker attribute value (`data-route-scene-part` or `data-console-entry-part`). */
		scenePart?: 'route' | 'console';
		ariaLabel?: string;
	}

	let { siteName, logoPath, links = [], activeHref, actions, decorative = false, scenePart = 'route', ariaLabel }: Props = $props();
	let linksElement = $state<HTMLDivElement | null>(null);
	const routePart = (part: string) => (scenePart === 'route' ? part : undefined);
	const consolePart = (part: string) => (scenePart === 'console' ? part : undefined);

	// Keep the current section link visible when the links row scrolls (phones).
	$effect(() => {
		if (!linksElement || !activeHref) return;
		const link = linksElement.querySelector<HTMLAnchorElement>(`a[href="${activeHref}"]`);
		if (!link) return;
		const linkRect = link.getBoundingClientRect();
		const navRect = linksElement.getBoundingClientRect();
		linksElement.scrollLeft = Math.max(0, linksElement.scrollLeft + linkRect.left - navRect.left - (linksElement.clientWidth - linkRect.width) / 2);
	});
</script>

<header
	class="top-strip entry-topbar"
	data-route-scene-part={routePart('topbar')}
	data-console-entry-part={consolePart('topbar')}
	aria-hidden={decorative ? 'true' : undefined}
	inert={decorative}
>
	<nav class="entry-nav" aria-label={decorative ? undefined : (ariaLabel ?? t('landing.nav.ariaLabel'))}>
		<svelte:element
			this={decorative ? 'span' : 'a'}
			class="entry-brand"
			href={decorative ? undefined : '/'}
			aria-label={decorative ? undefined : t('loginBrand.home')}
			data-route-scene-part={routePart('brand')}
			data-console-entry-part={consolePart('brand')}
		>
			<img src={logoPath} alt="" width="28" height="28" style:color-scheme={$resolvedTheme} />
			<span>{siteName}</span>
		</svelte:element>
		{#if links.length}
			<div class="entry-links" bind:this={linksElement}>
				{#each links as link (link.href)}
					<a href={link.href} class:is-active={activeHref === link.href} aria-current={activeHref === link.href ? 'location' : undefined}>{link.label}</a>
				{/each}
			</div>
		{/if}
		{#if actions && !decorative}
			<div class="entry-actions">{@render actions()}</div>
		{/if}
	</nav>
</header>

<style>
	/* Height comes from `--entry-nav-height` (layout.css) so every page pads by the same amount. */
	.entry-topbar {
		position: fixed;
		inset: 0 0 auto;
		z-index: var(--z-sidebar);
		border-bottom: 1px solid var(--color-line);
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
		font-family: var(--font-sans);
	}
	.entry-nav {
		box-sizing: border-box;
		display: grid;
		grid-template-areas: 'brand actions' 'links links';
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.25rem 0.5rem;
		width: 100%;
		max-width: var(--app-content-max-width);
		height: var(--entry-nav-height);
		margin-inline: auto;
		padding-inline: 1rem;
	}
	.entry-brand {
		grid-area: brand;
		display: flex; gap: 0.5rem; align-items: center;
		justify-self: start;
		min-width: 0; min-height: 2.75rem;
		color: var(--color-ink-0); text-decoration: none;
		font-size: 0.875rem; font-weight: 600;
	}
	.entry-brand img { flex-shrink: 0; width: auto; max-width: 8rem; height: 28px; object-fit: contain; }
	.entry-brand span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.entry-links { grid-area: links; display: flex; gap: 0.75rem; align-items: center; min-width: 0; overflow-x: auto; }
	.entry-links a {
		flex-shrink: 0; display: inline-flex; align-items: center; min-height: 2.75rem; padding: 0.25rem;
		border-bottom: 1px solid transparent; color: var(--color-ink-2); font-size: 0.75rem; text-decoration: none;
		transition: color var(--motion-duration-fast) var(--motion-ease-standard);
	}
	.entry-links a:hover, .entry-links a.is-active { color: var(--color-ink-0); border-color: var(--color-warm); }
	.entry-actions { grid-area: actions; display: flex; align-items: center; justify-content: flex-end; gap: 0.5rem; min-width: 0; }
	.entry-actions :global(.btn) { min-height: 2.75rem; }
	.entry-topbar :global(a:focus-visible), .entry-topbar :global(button:focus-visible) { outline: none; box-shadow: var(--focus-ring); }
	@media (min-width: 768px) {
		.entry-nav { padding-inline: 1.5rem; }
	}
	/* Short phones in landscape: one row, the section links stay on the landing page itself. */
	@media (max-width: 1023px) and (max-height: 620px) {
		.entry-nav { grid-template-areas: 'brand actions'; }
		.entry-links { display: none; }
	}
	@media (min-width: 1024px) {
		/* Links stay centered whatever the actions hold, so a scene only fades the actions that differ. */
		.entry-nav { grid-template-areas: 'brand links actions'; grid-template-columns: minmax(8rem, 1fr) auto minmax(8rem, 1fr); gap: 1rem; }
		.entry-links { gap: 1.25rem; }
	}
	@media (max-width: 380px) {
		.entry-brand span { display: none; }
	}
</style>
