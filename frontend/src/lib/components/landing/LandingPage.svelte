<script lang="ts">
	import { onMount } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import ThemeSelect from '$lib/components/ThemeSelect.svelte';
	import EntryTopbar from '$lib/components/entry/EntryTopbar.svelte';
	import EntryStage from '$lib/components/entry/EntryStage.svelte';
	import { entryNavLinks } from '$lib/components/entry/entryNav';
	import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import LandingScene from './LandingScene.svelte';
	import LandingMotionGraphic from './LandingMotionGraphic.svelte';

	interface Props {
		siteName: string;
		logoPath: string;
		consoleHref: string;
	}

	let { siteName, logoPath, consoleHref }: Props = $props();
	const email = 'pieroot@konkuk.ac.kr';
	const navLinks = $derived(entryNavLinks(''));
	const sectionIds = ['overview', 'capabilities', 'workflow', 'work', 'contact'];
	let root: HTMLElement;
	let activeSection = $state('overview');

	function focusLandingContent() {
		document.getElementById('landing-content')?.focus();
	}

	function updateActiveSection() {
		const activationLine = (root.querySelector<HTMLElement>('.top-strip')?.getBoundingClientRect().bottom ?? 0) + 16;
		let current = 'overview';
		for (const id of sectionIds) {
			const section = root.querySelector<HTMLElement>(`#${id}`);
			if (section && section.getBoundingClientRect().top <= activationLine) current = id;
		}
		activeSection = current;
	}

	onMount(() => {
		let alive = true;
		let observer: IntersectionObserver | undefined;
		const header = root.querySelector<HTMLElement>('.top-strip');
		const sections = Array.from(root.querySelectorAll<HTMLElement>('section[id]'));
		function observeNavigation() {
			observer?.disconnect();
			updateActiveSection();
			if (typeof window.IntersectionObserver !== 'function') return;
			const top = (header?.getBoundingClientRect().bottom ?? 0) + 16;
			observer = new window.IntersectionObserver(() => { if (alive) updateActiveSection(); }, { rootMargin: `-${top}px 0px 0px 0px` });
			sections.forEach((section) => observer?.observe(section));
		}
		const resize = typeof window.ResizeObserver === 'function' ? new window.ResizeObserver(observeNavigation) : undefined;
		if (header) resize?.observe(header);
		observeNavigation();
		return () => {
			alive = false;
			observer?.disconnect();
			resize?.disconnect();
		};
	});
</script>

<div class="landing-page" bind:this={root}>
	<a class="skip-link" href="#landing-content" onclick={focusLandingContent}>{t('landing.skipLink')}</a>
	<EntryTopbar {siteName} {logoPath} links={navLinks} activeHref={`#${activeSection}`}>
		{#snippet actions()}
			<Button variant="primary" size="md" href={consoleHref}>{t('landing.consoleAction')}</Button>
			<LocaleSelect id="landing-locale" variant="compact" />
			<ThemeSelect id="landing-theme" />
		{/snippet}
	</EntryTopbar>

	<div id="landing-content" tabindex="-1">
		<section id="overview" class="hero" aria-labelledby="landing-hero-title">
			<EntryStage wordmark={siteName} wordmarkTag="h1" wordmarkId="landing-hero-title" data-route-scene-part="art">
				{#snippet lead()}<p>{t('landing.story.hero.body')}</p>{/snippet}
				{#snippet actions()}
					<Button variant="primary" size="lg" href={consoleHref}>{t('landing.consoleAction')}</Button>
					<Button variant="link" size="lg" href="#capabilities">{t('landing.story.hero.explore')}<span aria-hidden="true">↗</span></Button>
				{/snippet}
			</EntryStage>
		</section>

		<section id="capabilities" class="feature server-feature">
			<div class="container feature-split">
				<div class="feature-copy">
					<span class="service-name">{t('landing.story.server.label')}</span>
					<h2>{t('landing.story.server.title')}</h2>
					<p>{t('landing.story.server.body')}</p>
					<Button variant="link" href="/docs/nova" ariaLabel={t('landing.story.guideAria', { service: t('landing.story.server.label') })}>{t('landing.story.guide')}<span aria-hidden="true">↗</span></Button>
				</div>
				<LandingScene kind="server" label={t('landing.story.server.label')}>
					{#snippet children(state)}<LandingMotionGraphic kind="server" {state} />{/snippet}
				</LandingScene>
			</div>
		</section>

		<section id="gpu" class="feature gpu-feature">
			<div class="container">
				<div class="feature-copy centered-copy">
					<span class="service-name">{t('landing.story.gpu.label')}</span>
					<h2>{t('landing.story.gpu.title')}</h2>
					<p>{t('landing.story.gpu.body')}</p>
					<Button variant="link" href="/docs/nova" ariaLabel={t('landing.story.guideAria', { service: t('landing.story.gpu.label') })}>{t('landing.story.guide')}<span aria-hidden="true">↗</span></Button>
				</div>
				<div class="wide-scene"><LandingScene kind="gpu" label={t('landing.story.gpu.label')}>
					{#snippet children(state)}<LandingMotionGraphic kind="gpu" {state} />{/snippet}
				</LandingScene></div>
			</div>
		</section>

		<section id="workflow" class="feature gateway-feature">
			<div class="container">
				<div class="feature-copy centered-copy">
					<span class="service-name">Lumen · {t('landing.story.gateway.label')}</span>
					<h2>{t('landing.story.gateway.title')}</h2>
					<p>{t('landing.story.gateway.body')}</p>
					<Button variant="link" href="/docs/lumen" ariaLabel={t('landing.story.guideAria', { service: t('landing.story.gateway.label') })}>{t('landing.story.guide')}<span aria-hidden="true">↗</span></Button>
				</div>
				<div class="wide-scene"><LandingScene kind="gateway" label={t('landing.story.gateway.label')}>
					{#snippet children(state)}<LandingMotionGraphic kind="gateway" {state} />{/snippet}
				</LandingScene></div>
			</div>
		</section>

		<!-- MCP는 Lumen 이야기의 연장이라 별도 nav 항목 없이 #workflow 아래에서 강조된다. -->
		<section id="mcp" class="feature mcp-feature">
			<div class="container">
				<div class="feature-copy centered-copy">
					<span class="service-name">{siteName} · {t('landing.story.mcp.label')}</span>
					<h2>{t('landing.story.mcp.title')}</h2>
					<p>{t('landing.story.mcp.body')}</p>
					<Button variant="link" href="/docs/mcp" ariaLabel={t('landing.story.guideAria', { service: t('landing.story.mcp.label') })}>{t('landing.story.guide')}<span aria-hidden="true">↗</span></Button>
				</div>
				<div class="wide-scene"><LandingScene kind="mcp" label={t('landing.story.mcp.label')}>
					{#snippet children(state)}<LandingMotionGraphic kind="mcp" {state} />{/snippet}
				</LandingScene></div>
			</div>
		</section>

		<section id="work" class="feature kubernetes-feature">
			<div class="container feature-split cluster-layout">
				<div class="feature-copy">
					<span class="service-name">{t('landing.story.kubernetes.label')}</span>
					<h2>{t('landing.story.kubernetes.title')}</h2>
					<p>{t('landing.story.kubernetes.body')}</p>
					<Button variant="link" href="/docs/drover" ariaLabel={t('landing.story.guideAria', { service: t('landing.story.kubernetes.label') })}>{t('landing.story.guide')}<span aria-hidden="true">↗</span></Button>
				</div>
				<LandingScene kind="kubernetes" label={t('landing.story.kubernetes.label')}>
					{#snippet children(state)}<LandingMotionGraphic kind="kubernetes" {state} />{/snippet}
				</LandingScene>
			</div>
		</section>

		<section id="contact" class="feature onprem-feature">
			<div class="container feature-split onprem-layout">
				<div class="feature-copy onprem-copy">
					<span class="service-name">{t('landing.story.onprem.label')}</span>
					<h2>{t('landing.story.onprem.title')}</h2>
					<p>{t('landing.story.onprem.body')}</p>
					<div class="onprem-actions">
						<Button variant="primary" size="lg" href={`mailto:${email}`} ariaLabel={t('landing.contact.emailAriaLabel')}>{t('landing.story.onprem.action')}</Button>
						<Button variant="outline" size="lg" href={consoleHref}>{t('landing.story.onprem.cloudAction')}</Button>
					</div>
					<p class="availability">{t('landing.story.availability')}</p>
					<p class="concept-note">{t('landing.story.motion.example')}</p>
				</div>
				<LandingScene kind="onprem" label={t('landing.story.onprem.label')}>
					{#snippet children(state)}<LandingMotionGraphic kind="onprem" {state} />{/snippet}
				</LandingScene>
			</div>
		</section>
	</div>

	<footer class="footer">
		<div class="container footer-layout">
			<div class="footer-brand"><img src={logoPath} alt="" width="28" height="28" /><strong>{siteName}</strong></div>
			<div class="footer-links">
				<a href="/docs">{t('landing.footer.docs')}</a>
				<a href={`mailto:${email}`}>{email}</a>
				<a href="https://github.com/openstack-afterglow/openstack-afterglow">{t('landing.footer.repository')}</a>
			</div>
		</div>
		<div class="container footer-bottom"><p>{t('landing.footer.copyright', { siteName })}</p></div>
	</footer>
</div>

<style>
	.landing-page { --landing-nav-height: var(--entry-nav-height); --landing-gutter: 1rem; min-height: 100%; padding-top: var(--landing-nav-height); color: var(--color-ink-0); background: var(--color-surface-canvas); font-family: var(--font-sans); line-height: 1.65; letter-spacing: -0.01em; overflow-wrap: anywhere; }
	.landing-page:lang(ja), .landing-page:lang(zh-CN) { --landing-word-break: normal; }
	.container { box-sizing: border-box; width: 100%; max-width: var(--app-content-max-width); margin-inline: auto; padding-inline: var(--landing-gutter); }
	h2, p { margin: 0; }
	h2 { font-family: var(--font-display); font-weight: 500; letter-spacing: -0.035em; word-break: var(--landing-word-break, keep-all); text-wrap: balance; }
	.landing-page :global(a:focus-visible), .landing-page :global(button:focus-visible) { outline: none; box-shadow: var(--focus-ring); }
	#landing-content, section[id] { scroll-margin-top: calc(var(--landing-nav-height) + 1rem); }
	.skip-link { position: fixed; top: 0.75rem; left: 1rem; z-index: var(--z-toast); display: inline-flex; align-items: center; min-height: 2.75rem; padding: 0 0.875rem; border: 1px solid var(--color-warm); border-radius: var(--radius-md); color: var(--color-ink-0); background: var(--color-surface-base); text-decoration: none; transform: translateY(-160%); }
	.skip-link:focus-visible { transform: none; }
	/* First screen: the shared Afterglow stage (EntryStage), the same composition the login identity side shows. */
	.hero { min-height: max(calc(100svh - var(--landing-nav-height)), 32rem); }
	.onprem-actions :global(.btn) { min-height: 2.75rem; }
	.feature { padding-block: 4rem; }
	.feature-split { display: grid; gap: 2rem; align-items: center; }
	.feature-copy { min-width: 0; }
	.service-name { display: inline-block; margin-bottom: 1rem; color: var(--color-warm-text); font-size: 0.9375rem; font-weight: 500; }
	h2 { max-width: 62rem; font-size: clamp(2rem, 4.4vw, 4rem); line-height: 1.2; }
	.feature-copy p { max-width: 34rem; margin-top: 1.25rem; color: var(--color-ink-1); font-size: 1rem; line-height: 1.8; word-break: var(--landing-word-break, keep-all); text-wrap: pretty; }
	.feature-copy :global(.btn-link) { min-height: 2.75rem; margin-top: 0.75rem; padding-inline: 0; color: var(--color-warm-text); }
	.server-feature, .gateway-feature, .kubernetes-feature { background: var(--color-surface-base); }
	.centered-copy { text-align: center; margin-inline: auto; }
	.centered-copy h2, .centered-copy p { margin-inline: auto; }
	.wide-scene { max-width: 60rem; margin: 1rem auto 0; }
	.onprem-actions { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 2rem; }
	.onprem-copy .availability, .onprem-copy .concept-note { max-width: 34rem; margin: 1.25rem 0 0; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.65; }
	.onprem-copy .concept-note { margin-top: 0.5rem; }
	.footer { padding-block: 2rem; border-top: 1px solid var(--color-line); }
	.footer-layout { display: grid; gap: 1rem; }
	.footer-brand { display: flex; align-items: center; gap: 0.5rem; }
	.footer-links { display: flex; flex-wrap: wrap; gap: 0.5rem 1.25rem; }
	.footer-links a { display: inline-flex; align-items: center; min-height: 2.75rem; color: var(--color-ink-1); font-size: 0.8125rem; text-decoration: none; }
	.footer-bottom { margin-top: 1.25rem; color: var(--color-ink-2); font-size: 0.75rem; }
	@media (min-width: 768px) {
		.landing-page { --landing-gutter: 1.5rem; }
		.feature { padding-block: 6rem; }
		.gpu-feature, .gateway-feature, .mcp-feature { padding-block: 3rem; }
		.footer-layout { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
	}
	@media (min-width: 1024px) {
		.feature-split { grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr); gap: 3rem; }
		.cluster-layout { grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr); }
		.cluster-layout > .feature-copy { grid-column: 2; grid-row: 1; }
		.cluster-layout > :global(.landing-scene) { grid-column: 1; grid-row: 1; }
	}
</style>
