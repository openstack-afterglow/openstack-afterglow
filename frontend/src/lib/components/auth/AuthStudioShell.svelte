<script lang="ts">
	import type { Snippet } from 'svelte';
	import ExperienceSupportCode from '$lib/components/ui/ExperienceSupportCode.svelte';
	import ThemeSelect from '$lib/components/ThemeSelect.svelte';
	import EntryTopbar from '$lib/components/entry/EntryTopbar.svelte';
	import EntryStage from '$lib/components/entry/EntryStage.svelte';
	import { entryNavLinks } from '$lib/components/entry/entryNav';
	import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';
	import { siteConfig } from '$lib/config/site';
	import { resolveLandingLogoPath } from '$lib/config/brandAssets';
	import { resolvedTheme } from '$lib/stores/theme';
	import { t } from '$lib/i18n/ns/public-entry';

	interface Props {
		/** Standalone entry surfaces share the landing bar, the Afterglow stage and safe panel scrolling. */
		variant: 'login' | 'logout' | 'account' | 'consent';
		wide?: boolean;
		localeId: string;
		themeId: string;
		footerNote: string;
		children: Snippet;
	}

	let { variant, wide = false, localeId, themeId, footerNote, children }: Props = $props();
	const site = $derived($siteConfig.site_name);
	const copyVariant = $derived(variant === 'logout' ? 'logout' : 'login');
	const logo = $derived(resolveLandingLogoPath($siteConfig, $resolvedTheme));
	const links = $derived(entryNavLinks('/'));
</script>

<div class="auth-studio" data-variant={variant} class:auth-wide={wide}>
	<EntryTopbar siteName={site} logoPath={logo} {links}>
		{#snippet actions()}
			<LocaleSelect id={localeId} variant="compact" />
			<ThemeSelect id={themeId} />
		{/snippet}
	</EntryTopbar>

	<main id="main-content" tabindex="-1" class="auth-layout">
		<section class="auth-identity" aria-label={t('authStudio.artLabel')}>
			<EntryStage wordmark={site} data-route-scene-part="art">
				{#snippet lead()}<p>{t(`authStudio.${copyVariant}.headline1`)} {t(`authStudio.${copyVariant}.headline2`)}</p>{/snippet}
			</EntryStage>
		</section>
		<section class="auth-panel" data-route-scene-part="panel">
			<div class="auth-panel-content">
				{@render children()}
				<footer class="auth-support">
					<ExperienceSupportCode />
					<p class="auth-panel-note">{t('authStudio.footer.workspace', { site })}{#if site !== 'Afterglow'}{' · Powered by Afterglow'}{/if} · {footerNote}</p>
				</footer>
			</div>
		</section>
	</main>
</div>

<style>
	/* The landing bar and the landing stage, with the task beside the stage: wide screens split the
	   stage and the panel, narrower screens keep the whole stage as background behind a centered card.
	   The panel scrolls rather than hiding security or error content. */
	.auth-studio {
		box-sizing: border-box;
		height: 100dvh;
		min-width: 0;
		display: grid;
		grid-template-rows: minmax(0, 1fr);
		padding-top: var(--entry-nav-height);
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
	}
	.auth-layout { display: grid; grid-template-columns: 1fr 1fr; min-height: 0; min-width: 0; height: 100%; }
	.auth-identity { position: relative; min-width: 0; min-height: 0; }

	.auth-panel {
		display: grid; place-items: safe center; min-width: 0; min-height: 0; overflow-y: auto;
		padding: clamp(0.75rem, 2.5vh, 2rem) 2rem;
		border-left: 1px solid var(--color-line);
		background: var(--color-surface-base);
	}
	.auth-panel-content { width: 100%; max-width: 380px; }
	.auth-wide .auth-panel-content { max-width: 560px; }
	.auth-panel-content :global(.auth-flow) { display: grid; gap: 1.25rem; min-width: 0; overflow-wrap: anywhere; }
	.auth-panel-content :global(.auth-flow-heading h1) {
		margin: 0; font-size: clamp(1.4rem, 2vw, 1.8rem); font-weight: 500;
		line-height: 1.3; letter-spacing: -0.03em; word-break: keep-all; overflow-wrap: anywhere;
	}
	.auth-panel-content :global(.auth-flow-heading) { display: grid; gap: 0.65rem; min-width: 0; }
	.auth-panel-content :global(.auth-flow-heading > p) { margin: 0; font-size: var(--type-support); line-height: 1.65; color: var(--color-ink-2); }
	.auth-panel-content :global(.auth-flow-fields) { display: grid; gap: 1rem; min-width: 0; }
	.auth-panel-content :global(.auth-flow-actions) { display: flex; flex-wrap: wrap; gap: 0.75rem; }
	.auth-panel-content :global(.auth-flow-actions > *) { flex: 1 1 9rem; min-width: 0; }
	.auth-panel-content :global(.auth-flow-links) {
		display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.5rem 1rem;
		border-top: 1px solid var(--color-line); padding-top: 0.75rem;
	}
	.auth-panel-note { margin: 0.75rem 0 0; color: var(--color-ink-2); font-size: var(--type-identifier); line-height: 1.6; }

	@media (min-width: 1600px) {
		.auth-layout { grid-template-columns: 1.2fr 1fr; }
		.auth-panel-content { max-width: 416px; }
	}
	/* Below 1024px: the stage is the whole background (exactly the landing hero) and the task is a centered
	   card, so the picture stays visible above and below it. Short viewports shrink the margins first. */
	@media (max-width: 1023px) {
		.auth-layout { position: relative; grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr); }
		.auth-identity { position: absolute; inset: 0; }
		.auth-identity :global(.entry-stage-caption) { display: none; }
		.auth-panel {
			position: relative; z-index: 1; border: 0; background: transparent;
			padding: clamp(2.5rem, 9vh, 5rem) 1rem;
			/* Outside the card the stage (and its motion control) stays reachable. */
			pointer-events: none;
		}
		.auth-panel-content {
			max-width: 440px; padding: 1.25rem; pointer-events: auto;
			border: 1px solid var(--color-line); border-radius: var(--radius-lg);
			background: var(--color-surface-base);
		}
		.auth-panel-content :global(.auth-flow) { gap: 0.85rem; }
	}
	@media (max-height: 800px) {
		.auth-panel { padding: 0.5rem 1.25rem; }
		.auth-panel-content :global(.auth-flow) { gap: 0.75rem; }
		.auth-panel-content :global(.auth-flow-heading h1) { font-size: 1.35rem; }
	}
	@media (max-width: 1023px) and (max-height: 800px) {
		.auth-panel { padding: clamp(1.5rem, 6vh, 3rem) 0.75rem; }
		.auth-panel-content { padding: 1rem; }
	}
	@media (max-height: 620px) {
		.auth-identity { display: none; }
		.auth-layout { display: block; }
		.auth-panel { height: 100%; padding: 0.5rem 1rem; border: 0; background: var(--color-surface-base); pointer-events: auto; }
		.auth-panel-content { max-width: 440px; padding: 0; border: 0; }
	}
	@media (max-height: 440px) and (min-width: 480px) {
		.auth-panel-content { max-width: 760px; }
		.auth-panel { padding: 4px 1rem; }
		.auth-panel-content :global(.auth-flow-fields) { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.5rem 1rem; }
		.auth-panel-content :global(.auth-flow-heading) { gap: 0.35rem; }
		.auth-panel-content :global(.auth-flow-heading h1) { font-size: 1.2rem; }
	}
</style>
