<script lang="ts">
	import { onMount } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/public-entry';
	import LandingScene from './LandingScene.svelte';
	import LandingMotionGraphic from './LandingMotionGraphic.svelte';
	import LandingChatDemo from './LandingChatDemo.svelte';

	interface Props {
		siteName: string;
		logoPath: string;
		consoleHref: string;
	}

	let { siteName, logoPath, consoleHref }: Props = $props();
	const email = 'pieroot@konkuk.ac.kr';
	const navLinks = $derived([
		{ label: t('landing.story.nav.compute'), href: '#capabilities' },
		{ label: t('landing.story.nav.chat'), href: '#workflow' },
		{ label: t('landing.story.nav.kubernetes'), href: '#work' },
		{ label: t('landing.story.nav.onprem'), href: '#contact' },
		{ label: t('landing.nav.docs'), href: '/docs' },
	]);
	const services = $derived([
		{ label: t('landing.story.server.label'), href: '#capabilities' },
		{ label: t('landing.story.gpu.label'), href: '#gpu' },
		{ label: t('landing.story.chat.label'), href: '#workflow' },
		{ label: t('landing.story.kubernetes.label'), href: '#work' },
	]);
	const sectionIds = ['overview', 'capabilities', 'workflow', 'work', 'contact'];
	let root: HTMLElement;
	let navLinksElement: HTMLDivElement;
	let activeSection = $state('overview');

	$effect(() => {
		if (!navLinksElement) return;
		const link = navLinksElement.querySelector<HTMLAnchorElement>(`a[href="#${activeSection}"]`);
		if (!link) return;
		const linkRect = link.getBoundingClientRect();
		const navRect = navLinksElement.getBoundingClientRect();
		navLinksElement.scrollLeft = Math.max(0, navLinksElement.scrollLeft + linkRect.left - navRect.left - (navLinksElement.clientWidth - linkRect.width) / 2);
	});

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
	<header class="top-strip">
		<nav class="container nav" aria-label={t('landing.nav.ariaLabel')}>
			<a class="brand" href="/">
				<img src={logoPath} alt="" width="28" height="28" />
				<span>{siteName}</span>
			</a>
			<div class="nav-links" bind:this={navLinksElement}>
				{#each navLinks as link}
					<a href={link.href} class:is-active={activeSection === link.href.slice(1)} aria-current={activeSection === link.href.slice(1) ? 'location' : undefined}>{link.label}</a>
				{/each}
			</div>
			<Button variant="primary" size="md" class="nav-cta" href={consoleHref}>{t('landing.consoleAction')}</Button>
			<div class="nav-locale"><LocaleSelect id="landing-locale" variant="compact" /></div>
		</nav>
	</header>

	<div id="landing-content" tabindex="-1">
		<section id="overview" class="hero">
			<div class="container hero-layout">
				<div class="hero-copy">
					<h1><RichText segments={t.rich('landing.story.hero.title')} /></h1>
					<p class="hero-lead">{t('landing.story.hero.body')}</p>
					<div class="hero-actions">
						<Button variant="primary" size="lg" href={consoleHref}>{t('landing.consoleAction')}</Button>
						<Button variant="link" size="lg" href="#capabilities">{t('landing.story.hero.explore')}<span aria-hidden="true">↗</span></Button>
					</div>
				</div>
				<LandingScene kind="hero" label={siteName} class="hero-stage">
					{#snippet children(state)}
						<figure class="hero-product">
							<LandingMotionGraphic kind="hero" {state} />
							<figcaption>{t('landing.story.hero.imageNote')}</figcaption>
						</figure>
					{/snippet}
				</LandingScene>
				<ul class="service-shortcuts" aria-label={t('landing.story.services.aria')}>
					{#each services as service}<li><a href={service.href}>{service.label}<span aria-hidden="true">↗</span></a></li>{/each}
				</ul>
			</div>
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

		<section id="workflow" class="feature chat-feature">
			<div class="container chat-layout">
				<div class="feature-copy chat-heading">
					<span class="service-name">Lumen · {t('landing.story.chat.label')}</span>
					<h2>{t('landing.story.chat.title')}</h2>
					<p>{t('landing.story.chat.body')}</p>
					<Button variant="link" href="/docs/lumen" ariaLabel={t('landing.story.guideAria', { service: t('landing.story.chat.label') })}>{t('landing.story.guide')}<span aria-hidden="true">↗</span></Button>
				</div>
				<LandingScene kind="chat" label={t('landing.story.chat.label')}>
					{#snippet children(state)}
						<LandingChatDemo {state} />
					{/snippet}
				</LandingScene>
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
	.landing-page { --landing-nav-height: 6.5rem; --landing-gutter: 1rem; min-height: 100%; padding-top: var(--landing-nav-height); color: var(--color-ink-0); background: var(--color-surface-canvas); font-family: var(--font-sans); line-height: 1.65; letter-spacing: -0.01em; overflow-wrap: anywhere; }
	.landing-page:lang(ja), .landing-page:lang(zh-CN) { --landing-word-break: normal; }
	.container { box-sizing: border-box; width: 100%; max-width: var(--app-content-max-width); margin-inline: auto; padding-inline: var(--landing-gutter); }
	h1, h2, p, figure { margin: 0; }
	h1, h2 { font-family: var(--font-display); font-weight: 500; letter-spacing: -0.045em; word-break: var(--landing-word-break, keep-all); text-wrap: balance; }
	.landing-page :global(a:focus-visible), .landing-page :global(button:focus-visible) { outline: none; box-shadow: var(--focus-ring); }
	#landing-content, section[id] { scroll-margin-top: calc(var(--landing-nav-height) + 1rem); }
	.skip-link { position: fixed; top: 0.75rem; left: 1rem; z-index: var(--z-toast); display: inline-flex; align-items: center; min-height: 2.75rem; padding: 0 0.875rem; border: 1px solid var(--color-warm); border-radius: var(--radius-md); color: var(--color-ink-0); background: var(--color-surface-base); text-decoration: none; transform: translateY(-160%); }
	.skip-link:focus-visible { transform: none; }
	.top-strip { position: fixed; inset: 0 0 auto; z-index: var(--z-sidebar); border-bottom: 1px solid var(--color-line); background: var(--color-surface-canvas); }
	.nav { display: grid; grid-template-areas: 'brand cta locale' 'links links links'; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 0.25rem 0.5rem; min-height: var(--landing-nav-height); }
	.brand { grid-area: brand; display: flex; gap: 0.5rem; align-items: center; min-width: 0; min-height: 2.75rem; color: var(--color-ink-0); text-decoration: none; font-size: 0.875rem; font-weight: 600; }
	.brand img { flex-shrink: 0; object-fit: contain; }
	.brand span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.nav-links { grid-area: links; display: flex; gap: 0.75rem; align-items: center; min-width: 0; overflow-x: auto; }
	.nav-links a { flex-shrink: 0; display: inline-flex; align-items: center; min-height: 2.75rem; padding: 0.25rem; border-bottom: 1px solid transparent; color: var(--color-ink-2); font-size: 0.75rem; text-decoration: none; transition: color var(--motion-duration-fast) var(--motion-ease-standard); }
	.nav-links a:hover, .nav-links a.is-active { color: var(--color-ink-0); border-color: var(--color-warm); }
	.landing-page :global(.nav-cta) { grid-area: cta; min-height: 2.75rem; }
	.nav-locale { grid-area: locale; }
	.hero { padding-block: 2rem 3rem; }
	.hero-layout { display: grid; justify-items: center; gap: 1.25rem; }
	.hero-copy { max-width: 64rem; text-align: center; }
	h1 { font-size: clamp(2.25rem, 5.3vw, 4.5rem); line-height: 1.2; }
	h1 :global(em) { color: var(--color-warm-text); font-style: normal; }
	.hero-lead { max-width: 44rem; margin: 1rem auto 0; color: var(--color-ink-1); font-size: 1rem; word-break: var(--landing-word-break, keep-all); text-wrap: pretty; }
	.hero-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.5rem; margin-top: 1rem; }
	.hero-actions :global(.btn), .onprem-actions :global(.btn) { min-height: 2.75rem; }
	.landing-page :global(.hero-stage) { max-width: 42rem; }
	figcaption { margin-top: 0.5rem; color: var(--color-ink-2); font-size: 0.75rem; text-align: center; }
	.service-shortcuts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.25rem 1rem; width: 100%; max-width: 54rem; margin: 0; padding: 0; list-style: none; }
	.service-shortcuts li { min-width: 0; }
	.service-shortcuts a { display: flex; justify-content: center; align-items: center; gap: 0.5rem; min-height: 2.75rem; padding: 0.375rem; border-bottom: 1px solid var(--color-line-2); color: var(--color-ink-0); font-size: 0.875rem; font-weight: 500; text-decoration: none; }
	.service-shortcuts a span { color: var(--color-warm-text); }
	.feature { padding-block: 4rem; }
	.feature-split { display: grid; gap: 2rem; align-items: center; }
	.feature-copy { min-width: 0; }
	.service-name { display: inline-block; margin-bottom: 1rem; color: var(--color-warm-text); font-size: 0.9375rem; font-weight: 500; }
	h2 { max-width: 62rem; font-size: clamp(2rem, 4.4vw, 4rem); line-height: 1.2; }
	.feature-copy p { max-width: 34rem; margin-top: 1.25rem; color: var(--color-ink-1); font-size: 1rem; line-height: 1.8; word-break: var(--landing-word-break, keep-all); text-wrap: pretty; }
	.feature-copy :global(.btn-link) { min-height: 2.75rem; margin-top: 0.75rem; padding-inline: 0; color: var(--color-warm-text); }
	.server-feature, .chat-feature, .onprem-feature { background: var(--color-surface-base); }
	.centered-copy { text-align: center; margin-inline: auto; }
	.centered-copy h2, .centered-copy p { margin-inline: auto; }
	.centered-copy p { max-width: 48rem; }
	.wide-scene { max-width: 42rem; margin: 1rem auto 0; }
	.chat-layout { max-width: 64rem; }
	.chat-heading { margin-bottom: 1.25rem; }
	.chat-heading h2 { font-size: clamp(2rem, 3.4vw, 3rem); }
	.chat-heading p { max-width: 48rem; }
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
		.hero { padding-top: 2.5rem; }
		.service-shortcuts { grid-template-columns: repeat(4, minmax(0, 1fr)); }
		.feature { padding-block: 6rem; }
		.gpu-feature { padding-block: 3rem; }
		.chat-feature { padding-block: 2.5rem; }
		.footer-layout { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
	}
	@media (min-width: 1024px) {
		.landing-page { --landing-nav-height: 4rem; }
		.nav { grid-template-areas: 'brand links cta locale'; grid-template-columns: minmax(8rem, 1fr) auto auto auto; gap: 1rem; }
		.nav-links { gap: 1.25rem; }
		.hero { padding-bottom: 4rem; }
		.hero-layout { gap: 1rem; }
		.feature-split { grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr); gap: 3rem; }
		.cluster-layout { grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr); }
		.cluster-layout > .feature-copy { grid-column: 2; grid-row: 1; }
		.cluster-layout > :global(.landing-scene) { grid-column: 1; grid-row: 1; }
	}
</style>
