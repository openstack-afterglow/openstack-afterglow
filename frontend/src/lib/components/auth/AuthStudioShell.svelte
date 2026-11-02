<script lang="ts">
	import type { Snippet } from 'svelte';
	import AfterglowOrbit from '$lib/components/ui/AfterglowOrbit.svelte';
	import ThemeSelect from '$lib/components/ThemeSelect.svelte';
	import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';
	import { siteConfig } from '$lib/config/site';
	import { resolvedTheme } from '$lib/stores/theme';
	import { t } from '$lib/i18n/ns/public-entry';

	interface Props {
		/** `login` or `logout`; selects authored copy and layout variants. */
		variant: 'login' | 'logout';
		localeId: string;
		themeId: string;
		footerNote: string;
		children: Snippet;
	}

	let { variant, localeId, themeId, footerNote, children }: Props = $props();
	let motion = $state(true);
	const site = $derived($siteConfig.site_name);
	const operatorLogo = $derived(site === 'Afterglow' ? '/afterglow-symbol.svg'
		: ($resolvedTheme === 'dark' ? ($siteConfig.logo_light_path || $siteConfig.logo_path) : ($siteConfig.logo_dark_path || $siteConfig.logo_path)));
</script>

<div class="auth-studio" data-variant={variant}>
	<header class="auth-topbar">
		<a class="auth-brand" href="/" aria-label={t('loginBrand.home')}>
			{#if operatorLogo}<img src={operatorLogo} alt="" height="28" />{/if}
			<span>{site}</span>
		</a>
		<div class="auth-top-actions">
			<LocaleSelect id={localeId} variant="compact" />
			<ThemeSelect id={themeId} />
		</div>
	</header>

	<main id="main-content" tabindex="-1" class="auth-layout">
		<section class="auth-identity" aria-label={t('authStudio.artLabel')}>
			<AfterglowOrbit active={motion} />
			<button type="button" class="auth-motion" onclick={() => { motion = !motion; }}>
				{motion ? t('landing.story.hero.pauseMotion') : t('landing.story.hero.playMotion')}
			</button>
			<div class="auth-identity-copy">
				<p class="auth-eyebrow" aria-hidden="true">{t(`authStudio.${variant}.eyebrow`)}</p>
				<h2>{t(`authStudio.${variant}.headline1`)}<br />{t(`authStudio.${variant}.headline2`)}</h2>
				<p class="auth-identity-description">{t(`authStudio.${variant}.description1`)}<br />{t(`authStudio.${variant}.description2`, { site })}</p>
				{#if variant === 'login'}
					<div class="auth-service-terms" aria-hidden="true">NOVA <span>/</span> NEUTRON <span>/</span> CINDER <span>/</span> LUMEN</div>
				{/if}
			</div>
			{#if variant === 'login'}<span class="auth-identity-index" aria-hidden="true">: : CLOUD WORKSPACE : :</span>{/if}
		</section>
		<section class="auth-panel">
			<div class="auth-panel-content">
				{@render children()}
			</div>
		</section>
	</main>

	<footer class="auth-footer">
		<span>{t('authStudio.footer.workspace', { site })}{#if site !== 'Afterglow'}{' · Powered by Afterglow'}{/if}</span>
		<a href="/">{t('loginBrand.home')} <span aria-hidden="true">↗</span></a>
		<span class="auth-footer-note">{footerNote}</span>
	</footer>
</div>

<style>
	/* Viewport-fit auth composition adapted from output/afterglow-login. The
	   artwork yields space first; the form panel scrolls rather than hiding
	   security or error content. */
	.auth-studio {
		height: 100dvh;
		min-width: 0;
		display: grid;
		grid-template-rows: 64px minmax(0, 1fr) 48px;
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
	}
	.auth-topbar {
		display: flex; align-items: center; justify-content: space-between; gap: 1rem;
		padding: 0 clamp(1.25rem, 4vw, 4.5rem);
		border-bottom: 1px solid var(--color-line);
		min-width: 0;
	}
	.auth-brand {
		display: inline-flex; align-items: center; gap: 0.65rem; min-height: 44px; min-width: 0;
		color: var(--color-ink-0); text-decoration: none;
		font-size: 1.1rem; font-weight: 600; letter-spacing: -0.035em;
	}
	.auth-brand img { display: block; height: 28px; width: auto; max-width: 8rem; object-fit: contain; }
	.auth-brand span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.auth-brand:focus-visible { outline: 2px solid var(--color-warm-2); outline-offset: 4px; border-radius: 0.25rem; }
	.auth-top-actions { display: flex; align-items: center; gap: 0.75rem; flex-shrink: 0; }

	.auth-layout { display: grid; grid-template-columns: 1fr 1fr; min-height: 0; min-width: 0; height: 100%; }
	.auth-identity {
		position: relative; isolation: isolate; overflow: hidden; min-width: 0; min-height: 0;
		border-right: 1px solid var(--color-line);
		background: var(--afterglow-artwork-base);
	}
	.auth-motion {
		position: absolute; z-index: 2; bottom: 1rem; left: clamp(1.25rem, 4vw, 4.5rem);
		min-height: 44px; padding: 0.5rem 0; border: 0; background: transparent;
		color: var(--color-ink-2); font: inherit; font-size: 0.6875rem; cursor: pointer;
	}
	.auth-motion:hover { color: var(--color-ink-0); }
	.auth-motion:focus-visible { outline: 2px solid var(--color-warm-2); outline-offset: 4px; }
	.auth-identity-copy {
		position: absolute; z-index: 1; left: 0; right: 0; bottom: 5rem;
		padding: 0 clamp(1.5rem, 4vw, 4.5rem); pointer-events: none;
	}
	.auth-eyebrow, .auth-panel-content :global(.auth-eyebrow) {
		margin: 0 0 1rem; font: 0.625rem var(--font-mono); letter-spacing: 0.18em; color: var(--color-warm-2);
	}
	.auth-identity h2 {
		margin: 0 0 1.1rem; font-size: clamp(1.7rem, 2.6vw, 3rem); font-weight: 400;
		letter-spacing: -0.055em; line-height: 1.32; word-break: keep-all;
	}
	.auth-identity-description { margin: 0; font-size: 0.8125rem; line-height: 1.9; color: var(--color-ink-2); }
	.auth-service-terms {
		display: flex; flex-wrap: wrap; gap: 0.6rem; margin-top: 1.8rem;
		font: 0.5625rem var(--font-mono); letter-spacing: 0.13em; color: var(--color-ink-2);
	}
	.auth-service-terms span { color: var(--color-warm); }
	.auth-identity-index {
		position: absolute; right: 1.25rem; bottom: 1.85rem;
		font: 0.5625rem var(--font-mono); letter-spacing: 0.1em; color: var(--color-ink-2);
	}

	.auth-panel {
		display: grid; place-items: center; min-width: 0; min-height: 0; overflow-y: auto;
		padding: clamp(0.75rem, 2.5vh, 2rem) 2rem;
		background: var(--color-surface-base);
	}
	.auth-panel-content { width: 100%; max-width: 380px; }

	.auth-footer {
		display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: nowrap;
		padding: 0 clamp(1.25rem, 4vw, 4.5rem); min-width: 0;
		border-top: 1px solid var(--color-line); color: var(--color-ink-2); font-size: 0.625rem;
	}
	.auth-footer > span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.auth-footer a { display: flex; align-items: center; gap: 0.5rem; min-height: 44px; color: inherit; text-decoration: none; white-space: nowrap; }
	.auth-footer a:hover { color: var(--color-ink-0); }
	.auth-footer a:focus-visible { outline: 2px solid var(--color-warm-2); outline-offset: 2px; }
	.auth-footer-note { font-family: var(--font-mono); letter-spacing: 0.08em; white-space: nowrap; }

	@media (min-width: 1600px) {
		.auth-layout { grid-template-columns: 1.2fr 1fr; }
		.auth-panel-content { max-width: 416px; }
		.auth-identity-copy { padding-left: 7vw; bottom: 6rem; }
	}
	@media (min-width: 768px) and (max-width: 1023px) {
		.auth-layout { grid-template-columns: 1fr; grid-template-rows: minmax(120px, 22%) minmax(0, 1fr); }
		.auth-identity { border-right: 0; border-bottom: 1px solid var(--color-line); }
		.auth-identity-copy { bottom: auto; top: 2rem; padding: 0 2.5rem; }
		.auth-identity h2 { font-size: 1.65rem; }
		.auth-identity-description, .auth-service-terms, .auth-identity-index { display: none; }
		.auth-motion { left: auto; right: 1.5rem; bottom: 0.5rem; }
		.auth-panel-content { max-width: 440px; }
		.auth-footer-note { display: none; }
	}
	@media (max-width: 767px) {
		.auth-studio { grid-template-rows: 52px minmax(0, 1fr) 45px; }
		.auth-topbar, .auth-footer { padding-inline: 1.25rem; }
		.auth-brand { font-size: 1rem; }
		.auth-brand img { height: 24px; }
		.auth-layout { grid-template-columns: 1fr; grid-template-rows: minmax(60px, 15%) minmax(0, 1fr); }
		.auth-identity { border-right: 0; border-bottom: 1px solid var(--color-line); }
		.auth-identity-copy, .auth-identity-index { display: none; }
		.auth-motion { left: auto; right: 1rem; bottom: 0.25rem; font-size: 0.625rem; }
		.auth-panel { padding: 0.75rem 1.25rem; }
		.auth-panel-content { max-width: 440px; }
		.auth-footer-note { display: none; }
		.auth-footer { font-size: 0.5625rem; }
	}
	@media (max-height: 800px) {
		.auth-studio { grid-template-rows: 48px minmax(0, 1fr) 33px; }
		.auth-footer a { min-height: 32px; }
		.auth-identity-copy { bottom: 4rem; }
		.auth-identity-description, .auth-service-terms, .auth-identity-index { display: none; }
		.auth-panel { padding: 0.5rem 1.25rem; }
	}
	@media (max-width: 767px) and (max-height: 800px) {
		.auth-layout { grid-template-rows: minmax(32px, 9%) minmax(0, 1fr); }
		.auth-motion { bottom: 0; font-size: 0.5625rem; }
	}
	@media (max-height: 620px) {
		.auth-studio { grid-template-rows: 44px minmax(0, 1fr); }
		.auth-footer, .auth-identity { display: none; }
		.auth-layout { display: block; }
		.auth-panel { height: 100%; padding: 0.5rem 1rem; }
		.auth-panel-content { max-width: 440px; }
		.auth-brand { font-size: 0.9rem; }
		.auth-brand img { height: 22px; }
	}
	@media (max-height: 440px) and (min-width: 480px) {
		.auth-panel-content { max-width: 760px; }
		.auth-panel { padding: 4px 1rem; }
	}
	@media (max-width: 380px) {
		.auth-brand span { display: none; }
		.auth-top-actions { gap: 0.5rem; }
	}
</style>
