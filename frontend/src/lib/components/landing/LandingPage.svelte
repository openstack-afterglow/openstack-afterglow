<script lang="ts">
	import { onMount } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';
	import { prefersReducedMotion } from '$lib/utils/motion';
	import LandingConsolePreview, { type ConsolePreviewView } from './LandingConsolePreview.svelte';
	import LandingFigure from './LandingFigure.svelte';
	import LandingOpsBoard from './LandingOpsBoard.svelte';
	import LandingJourney from './LandingJourney.svelte';
	import PlateGraphic from './PlateGraphic.svelte';
	import type { PlateName } from './plateGraphics';
	import LocaleSelect from '$lib/i18n/LocaleSelect.svelte';
	import RichText from '$lib/i18n/RichText.svelte';
	import { t } from '$lib/i18n/ns/public-entry';

	interface Props {
		siteName: string;
		logoPath: string;
		consoleHref: string;
	}

	let { siteName, logoPath, consoleHref }: Props = $props();

	const navLinks = $derived([
		{ label: t('landing.nav.overview'), href: '#overview' },
		{ label: t('landing.nav.capabilities'), href: '#capabilities' },
		{ label: t('landing.nav.workflow'), href: '#workflow' },
		{ label: t('landing.nav.work'), href: '#work' },
		{ label: t('landing.nav.contact'), href: '#contact' },
		{ label: t('landing.nav.docs'), href: '/docs' },
	]);


	const capabilities: Array<{
		tag: string;
		name: PlateName;
		alt: string;
		title: string;
		body: string;
		proof: string;
		workflow: WorkflowKind;
	}> = $derived([
		{
			tag: t('landing.compute.tag'),
			name: 'compute-allocation',
			alt: t('landing.compute.alt'),
			title: t('landing.compute.title'),
			body: t('landing.compute.body'),
			proof: t('landing.compute.proof'),
			workflow: 'compute',
		},
		{
			tag: t('landing.cluster.tag'),
			name: 'kubernetes',
			alt: t('landing.cluster.alt'),
			title: t('landing.cluster.title'),
			body: t('landing.cluster.body'),
			proof: t('landing.cluster.proof'),
			workflow: 'compute',
		},
		{
			tag: t('landing.library.tag'),
			name: 'layer',
			alt: t('landing.library.alt'),
			title: t('landing.library.title'),
			body: t('landing.library.body'),
			proof: t('landing.library.proof'),
			workflow: 'data',
		},
		{
			tag: t('landing.governance.tag'),
			name: 'security',
			alt: t('landing.governance.alt'),
			title: t('landing.governance.title'),
			body: t('landing.governance.body'),
			proof: t('landing.governance.proof'),
			workflow: 'ops',
		},
	]);

	type WorkflowKind = 'compute' | 'data' | 'ops';
	type WorkflowFilter = 'all' | WorkflowKind;

	const filters = $derived([
		{ label: t('landing.filter.all'), value: 'all' },
		{ label: t('landing.filter.compute'), value: 'compute' },
		{ label: t('landing.filter.data'), value: 'data' },
		{ label: t('landing.filter.ops'), value: 'ops' },
	]);

	const workflowCards: Array<{
		kind: WorkflowKind;
		name: PlateName;
		alt: string;
		title: string;
		body: string;
		meta: string;
	}> = $derived([
		{
			kind: 'compute',
			name: 'api',
			alt: t('landing.workflow.computeAlt'),
			title: t('landing.workflow.computeTitle'),
			body: t('landing.workflow.computeBody'),
			meta: t('landing.workflow.computeMeta'),
		},
		{
			kind: 'data',
			name: 'shared-data',
			alt: t('landing.workflow.dataAlt'),
			title: t('landing.workflow.dataTitle'),
			body: t('landing.workflow.dataBody'),
			meta: t('landing.workflow.dataMeta'),
		},
		{
			kind: 'compute',
			name: 'kubernetes',
			alt: t('landing.cluster.alt'),
			title: t('landing.workflow.clusterTitle'),
			body: t('landing.workflow.clusterBody'),
			meta: t('landing.workflow.clusterMeta'),
		},
		{
			kind: 'ops',
			name: 'monitoring',
			alt: t('landing.workflow.observeAlt'),
			title: t('landing.workflow.observeTitle'),
			body: t('landing.workflow.observeBody'),
			meta: t('landing.workflow.observeMeta'),
		},
		{
			kind: 'ops',
			name: 'release',
			alt: t('landing.workflow.securityAlt'),
			title: t('landing.workflow.securityTitle'),
			body: t('landing.workflow.securityBody'),
			meta: t('landing.workflow.securityMeta'),
		},
	]);

	const productViews: Array<{ value: ConsolePreviewView; label: string; title: string; body: string; route: string }> = $derived([
		{ value: 'project', label: t('landing.product.projectLabel'), title: t('landing.product.projectTitle'), body: t('landing.product.projectBody'), route: 'project / overview' },
		{ value: 'cluster', label: t('landing.product.clusterLabel'), title: t('landing.product.clusterTitle'), body: t('landing.product.clusterBody'), route: 'containers / clusters' },
		{ value: 'network', label: t('landing.product.networkLabel'), title: t('landing.product.networkTitle'), body: t('landing.product.networkBody'), route: 'network / topology' },
	]);
	const productOptions = $derived(productViews.map(({ value, label }) => ({ value, label })));
	let selectedProduct: ConsolePreviewView = $state('project');
	let activeProduct = $derived(productViews.find((view) => view.value === selectedProduct) ?? productViews[0]!);

	const email = 'pieroot@konkuk.ac.kr';
	const sectionIds = ['overview', 'capabilities', 'workflow', 'work', 'contact'];

	let landingRoot: HTMLElement;
	let navLinksElement: HTMLDivElement;
	let selectedFilter: WorkflowFilter = $state('all');
	let activeSection = $state('overview');
	let visibleCount = $derived(
		workflowCards.filter((card) => selectedFilter === 'all' || card.kind === selectedFilter).length,
	);
	let revealObserver: IntersectionObserver | undefined;
	let revealReadyFrame: number | undefined;

	$effect(() => {
		if (!navLinksElement) return;
		const activeLink = navLinksElement.querySelector<HTMLAnchorElement>(`a[href="#${activeSection}"]`);
		if (!activeLink) return;
		const linkRect = activeLink.getBoundingClientRect();
		const navRect = navLinksElement.getBoundingClientRect();
		navLinksElement.scrollLeft = Math.max(
			0,
			navLinksElement.scrollLeft + linkRect.left - navRect.left - (navLinksElement.clientWidth - linkRect.width) / 2,
		);
	});

	function isWorkflowFilter(value: string): value is WorkflowFilter {
		return value === 'all' || value === 'compute' || value === 'data' || value === 'ops';
	}

	function selectFilter(value: string) {
		if (isWorkflowFilter(value)) selectedFilter = value;
	}

	function selectProduct(value: string) {
		const match = productViews.find((view) => view.value === value);
		if (match) selectedProduct = match.value;
	}

	function focusLandingContent() {
		document.getElementById('landing-content')?.focus();
	}

	function updateActiveSection() {
		const navigationBottom = landingRoot.querySelector<HTMLElement>('.top-strip')?.getBoundingClientRect().bottom ?? 0;
		const activationLine = navigationBottom + 16;
		let current = 'overview';
		for (const id of sectionIds) {
			const section = document.getElementById(id);
			if (section && section.getBoundingClientRect().top <= activationLine) current = id;
		}
		activeSection = current;
	}

	onMount(() => {
		const html = document.documentElement;
		const previousScrollBehavior = html.style.scrollBehavior;
		const motionQuery = typeof window.matchMedia === 'function' ? window.matchMedia(REDUCED_MOTION_QUERY) : undefined;
		const revealItems = Array.from(landingRoot.querySelectorAll<HTMLElement>('[data-reveal]'));

		const configureMotion = () => {
			revealObserver?.disconnect();
			revealObserver = undefined;
			if (revealReadyFrame !== undefined) window.cancelAnimationFrame(revealReadyFrame);
			revealReadyFrame = undefined;
			landingRoot.classList.remove('reveal-enabled', 'reveal-ready');
			const reducedMotion = prefersReducedMotion();
			html.style.scrollBehavior = reducedMotion ? 'auto' : 'smooth';
			if (reducedMotion) {
				revealItems.forEach((item) => item.classList.add('is-visible'));
				return;
			}
			if (typeof window.IntersectionObserver !== 'function') return;
			landingRoot.classList.add('reveal-enabled');
			revealObserver = new window.IntersectionObserver(
				(entries) => {
					for (const entry of entries) {
						if (entry.isIntersecting) {
							entry.target.classList.add('is-visible');
							revealObserver?.unobserve(entry.target);
						}
					}
				},
				{ threshold: 0, rootMargin: '0px 0px -8% 0px' },
			);
			revealItems.filter((item) => !item.classList.contains('is-visible')).forEach((item) => revealObserver?.observe(item));
			revealReadyFrame = window.requestAnimationFrame(() => landingRoot.classList.add('reveal-ready'));
		};
		configureMotion();
		motionQuery?.addEventListener('change', configureMotion);
		const handleScroll = () => updateActiveSection();
		updateActiveSection();
		window.addEventListener('scroll', handleScroll, { passive: true });
		window.addEventListener('resize', handleScroll);

		return () => {
			window.removeEventListener('scroll', handleScroll);
			window.removeEventListener('resize', handleScroll);
			motionQuery?.removeEventListener('change', configureMotion);
			revealObserver?.disconnect();
			revealObserver = undefined;
			if (revealReadyFrame !== undefined) window.cancelAnimationFrame(revealReadyFrame);
			revealReadyFrame = undefined;
			landingRoot.classList.remove('reveal-enabled', 'reveal-ready');
			html.style.scrollBehavior = previousScrollBehavior;
		};
	});
</script>

{#snippet desktopBreak(_text: string)}<br class="desktop-break" />{/snippet}

<div class="landing-page" bind:this={landingRoot}>
	<a class="skip-link" href="#landing-content" onclick={focusLandingContent}>{t('landing.skipLink')}</a>

	<header class="top-strip">
		<nav class="container nav" aria-label={t('landing.nav.ariaLabel')}>
			<a class="brand" href="/">
				<img src={logoPath} alt="" />
				<span>{siteName}</span>
				<small>{t('landing.brand.tagline')}</small>
			</a>
			<div class="nav-links" bind:this={navLinksElement}>
				{#each navLinks as link}
					<a
						href={link.href}
						class:is-active={activeSection === link.href.slice(1)}
						aria-current={activeSection === link.href.slice(1) ? 'location' : undefined}
					>{link.label}</a>
				{/each}
			</div>
			<Button variant="primary" size="md" class="nav-cta" href={consoleHref}>{t('landing.consoleAction')}</Button>
			<div class="nav-locale"><LocaleSelect id="landing-locale" variant="labelled" /></div>
		</nav>
	</header>

	<div id="landing-content" tabindex="-1">
		<section class="hero">
			<div class="container hero-layout">
				<div class="hero-copy" data-reveal>
					<div class="eyebrow"><span aria-hidden="true"></span>{t('landing.hero.eyebrow')}</div>
					<h1><RichText segments={t.rich('landing.hero.title')} /></h1>
					<p class="lead"><RichText segments={t.rich('landing.hero.lead')} tags={{ desktopBreak }} /></p>
					<div class="hero-actions">
						<Button variant="primary" size="lg" class="landing-btn" href={consoleHref}>{t('landing.consoleAction')}</Button>
						<Button variant="outline" size="lg" class="landing-btn" href="#capabilities">{t('landing.hero.capabilitiesAction')}</Button>
						<Button variant="link" size="lg" class="landing-btn" href="/docs">{t('landing.hero.guideAction')}</Button>
					</div>
					<div class="hero-context"><span>{t('landing.hero.context')}</span><p>{t('landing.request.title')} <i aria-hidden="true">→</i> {t('landing.allocate.title')} <i aria-hidden="true">→</i> {t('landing.observe.title')} <i aria-hidden="true">→</i> {t('landing.reuse.title')}</p></div>
				</div>
				<div id="environment-preview" class="hero-board" data-reveal><LandingOpsBoard /></div>
			</div>
			<div class="container hero-bottom"><span>{t('landing.hero.teamEnvironment')}</span><a href="#overview"><span class="cue-fine">{t('landing.hero.scrollCue')}</span><span class="cue-touch">{t('landing.hero.touchCue')}</span><span aria-hidden="true">↓</span></a></div>
		</section>

		<section id="overview" class="section overview-section">
			<div class="container">
				<div class="section-head" data-reveal>
					<div class="section-label"><span>{t('landing.overview.label')}</span><b>{t('landing.overview.kicker')}</b></div>
					<div>
						<h2><RichText segments={t.rich('landing.overview.title')} /></h2>
						<p>{t('landing.overview.body')}</p>
					</div>
				</div>
				<LandingJourney />
			</div>
		</section>

		<section id="capabilities" class="section">
			<div class="container">
				<div class="section-head" data-reveal>
					<div class="section-label"><span>{t('landing.nav.capabilities')}</span><b>{t('landing.capabilities.kicker')}</b></div>
					<div>
						<h2><RichText segments={t.rich('landing.capabilities.title')} /></h2>
						<p>{t('landing.capabilities.body')}</p>
					</div>
				</div>
				<div data-reveal>
					<Card surface="subtle" padding="none" class="capability-grid">
						{#each capabilities as capability}
							<article class="cap-card">
								<div class="cap-media"><PlateGraphic name={capability.name} alt={capability.alt} fit="contain" /></div>
								<div class="cap-content">
									<div class="cap-meta"><span>{capability.tag}</span><b>{capability.proof}</b></div>
									<h3>{capability.title}</h3>
									<p>{capability.body}</p>
									<Button variant="link" class="cap-explore" href="#workflow" onclick={() => selectFilter(capability.workflow)} ariaLabel={t('landing.capabilities.exploreAriaLabel', { title: capability.title })}>{t('landing.capabilities.exploreAction')} <span aria-hidden="true">↗</span></Button>
								</div>
							</article>
						{/each}
					</Card>
				</div>
			</div>
		</section>

		<section id="workflow" class="section workflow-section">
			<div class="container">
				<div class="section-head" data-reveal>
					<div class="section-label"><span>{t('landing.nav.workflow')}</span><b>{t('landing.workflow.kicker')}</b></div>
					<div>
						<h2><RichText segments={t.rich('landing.workflow.title')} /></h2>
						<p>{t('landing.workflow.body')}</p>
					</div>
				</div>
				<div class="workflow-layout" data-reveal>
					<aside class="filter-panel">
						<Card surface="subtle" padding="lg" class="filter-panel-surface">
							<span class="filter-kicker">{t('landing.workflow.filterKicker')}</span>
							<h3><RichText segments={t.rich('landing.workflow.filterTitle')} /></h3>
							<ToggleGroup value={selectedFilter} options={filters} onchange={selectFilter} size="sm" fullWidth class="landing-workflow-filter" ariaLabel={t('landing.workflow.filterAriaLabel')} />
							<p><RichText segments={t.rich('landing.workflow.visibleCount', { count: visibleCount })} /></p>
						</Card>
					</aside>
					<Card surface="subtle" padding="none" class="workflow-list">
						{#each workflowCards as card, index}
							{@const matches = selectedFilter === 'all' || card.kind === selectedFilter}
							<article class="lab-card" class:is-muted={!matches} data-kind={card.kind}>
								<div class="workflow-index">{String(index + 1).padStart(2, '0')}</div>
								<PlateGraphic name={card.name} alt={card.alt} fit="cover" class="lab-card-media" />
								<div class="workflow-copy"><span>{card.meta}</span><h3>{card.title}</h3><p>{card.body}</p></div>
							</article>
						{/each}
					</Card>
				</div>
			</div>
		</section>


		<section id="work" class="section work-section">
			<div class="container">
				<div class="section-head" data-reveal>
					<div class="section-label"><span>{t('landing.work.label')}</span><b>{t('landing.work.kicker')}</b></div>
					<div>
						<h2><RichText segments={t.rich('landing.work.title')} /></h2>
						<p>{t('landing.work.body')}</p>
					</div>
				</div>
				<div class="product-tour" data-reveal>
					<div class="product-stage">
						<div class="stage-bar" aria-hidden="true"><b>afterglow / {activeProduct.route}</b><em>{t('landing.product.exampleScreen')}</em></div>
						{#key selectedProduct}
							<LandingConsolePreview class="screen-main" view={activeProduct.value} />
						{/key}
					</div>
					<div class="product-controls">
						<span class="filter-kicker">{t('landing.product.kicker')}</span>
						<ToggleGroup value={selectedProduct} options={productOptions} onchange={selectProduct} fullWidth class="product-switcher" ariaLabel={t('landing.product.ariaLabel')} />
						<div class="product-description" aria-live="polite"><h3>{activeProduct.title}</h3><p>{activeProduct.body}</p></div>
						<Button variant="outline" size="lg" class="product-console" href={consoleHref}>{t('landing.product.consoleAction')} <span aria-hidden="true">↗</span></Button>
					</div>
				</div>
			</div>
		</section>

		<section class="section audience-section">
			<div class="container audience-layout">
				<div data-reveal>
					<div class="section-label"><span>{t('landing.audience.label')}</span><b>{t('landing.audience.kicker')}</b></div>
					<blockquote>{t('landing.audience.quote')}</blockquote>
					<ul class="audience-list" aria-label={t('landing.audience.ariaLabel')}>
						<li class="glyph">{t('landing.audience.lab')}</li><li class="glyph">{t('landing.audience.instructor')}</li><li class="glyph">{t('landing.audience.researcher')}</li><li class="glyph">{t('landing.audience.practiceTeam')}</li><li class="glyph">{t('landing.audience.organization')}</li>
					</ul>
				</div>
				<div class="quote-visual" data-reveal>
					<LandingFigure class="audience-figure" name="professor" alt={t('landing.audience.figureAlt')} />
					<div class="audience-note"><span>{t('landing.audience.noteKicker')}</span><strong><RichText segments={t.rich('landing.audience.noteTitle')} /></strong><p>{t('landing.audience.noteBody')}</p></div>
				</div>
			</div>
		</section>

		<section id="contact" class="section contact-section">
			<div class="container">
				<div class="contact-panel" data-reveal>
					<div>
						<div class="eyebrow"><span aria-hidden="true"></span>{t('landing.contact.kicker')}</div>
						<h2><RichText segments={t.rich('landing.contact.title')} /></h2>
						<p>{t('landing.contact.body')}</p>
					</div>
					<div class="contact-actions">
						<Button variant="primary" size="lg" class="contact-console" href={consoleHref}>{t('landing.consoleAction')}</Button>
						<Button variant="outline" size="lg" class="email-pill" href={`mailto:${email}`} ariaLabel={t('landing.contact.emailAriaLabel')}>{email}</Button>
					</div>
				</div>
			</div>
		</section>
	</div>

	<footer class="footer">
		<div class="container footer-layout">
			<div class="footer-brand"><img src={logoPath} alt="" /><strong>{siteName}</strong><span>{t('landing.footer.tagline')}</span></div>
			<div class="footer-grid">
				<div><h3>{t('landing.footer.product')}</h3><a href="#overview">{t('landing.nav.overview')}</a><a href="#capabilities">{t('landing.nav.capabilities')}</a><a href="#workflow">{t('landing.nav.workflow')}</a><a href="/docs">{t('landing.footer.docs')}</a></div>
				<div><h3>{t('landing.footer.contact')}</h3><a href={`mailto:${email}`}>{email}</a><a href="https://github.com/openstack-afterglow/openstack-afterglow">{t('landing.footer.repository')}</a></div>
			</div>
		</div>
		<div class="container footer-bottom"><p>{t('landing.footer.copyright', { siteName })}</p><span>{t('landing.footer.location')}</span></div>
	</footer>
</div>

<style>
	.landing-page {
		--landing-ease: cubic-bezier(0.2, 0.8, 0.2, 1);
		--landing-container: 80rem;
		--landing-gutter: 1rem;
		--landing-nav-height: 10rem;
		min-height: 100%;
		overflow-x: clip;
		padding-top: var(--landing-nav-height);
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
		font-family: var(--font-sans);
		font-weight: 400;
		letter-spacing: -0.01em;
		font-size: 0.9375rem;
		line-height: 1.65;
		overflow-wrap: anywhere;
		-webkit-font-smoothing: antialiased;
		text-rendering: optimizeLegibility;
	}
	.landing-page:lang(ja), .landing-page:lang(zh-CN) { --landing-word-break: normal; }
	.landing-page :global(img) { display: block; max-width: 100%; }
	.landing-page :global(a) { color: inherit; }
	.landing-page h1, .landing-page h2, .landing-page h3, .landing-page p, .landing-page blockquote { margin: 0; }
	.landing-page .container { width: min(var(--landing-container), calc(100% - var(--landing-gutter) * 2)); margin-inline: auto; }
	.landing-page :global(a:focus-visible), .landing-page :global(button:focus-visible) { outline: none; box-shadow: var(--focus-ring); }

	.skip-link { position: fixed; top: 0.75rem; left: 1rem; z-index: var(--z-toast); display: inline-flex; min-height: 2.75rem; align-items: center; padding: 0 0.875rem; border: 1px solid var(--color-warm); border-radius: 0.5rem; background: var(--color-ink-0); color: var(--color-surface-canvas); font-weight: 700; text-decoration: none; transform: translateY(-160%); transition: transform var(--motion-duration-fast) var(--landing-ease); }
	.skip-link:focus-visible { transform: translateY(0); }

	.top-strip { position: fixed; inset: 0 0 auto; z-index: var(--z-sidebar); border-bottom: 1px solid color-mix(in oklab, var(--color-line) 84%, transparent); background: color-mix(in oklab, var(--color-surface-canvas) 88%, transparent); backdrop-filter: blur(1.125rem); }
	.nav { display: grid; grid-template-areas: 'brand cta' 'locale locale' 'links links'; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 0.25rem 0.75rem; min-height: var(--landing-nav-height); padding-block: 0.5rem; }
	.brand { grid-area: brand; display: grid; grid-template-columns: 2rem minmax(0, 1fr); min-width: 0; max-width: 100%; min-height: 2.75rem; align-items: center; column-gap: 0.625rem; width: fit-content; overflow-wrap: anywhere; text-decoration: none; }
	.brand img { grid-row: 1 / 3; width: 2rem; height: 2rem; object-fit: contain; }
	.brand span { align-self: end; font-size: 0.8125rem; font-weight: 700; line-height: 1; }
	.brand small { align-self: start; color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.6875rem; line-height: 1; text-transform: uppercase; }
	.nav-links { grid-area: links; display: flex; min-width: 0; align-items: center; gap: 0.125rem; overflow-x: auto; scrollbar-width: none; }
	.nav-links::-webkit-scrollbar { display: none; }
	.nav-links a { position: relative; display: inline-flex; min-width: 2.75rem; min-height: 2.75rem; flex: 0 0 auto; align-items: center; justify-content: center; padding: 0.5rem 0.625rem; color: var(--color-ink-2); font-size: 0.75rem; text-decoration: none; }
	.nav-links a::after { content: ''; position: absolute; inset: auto 0.625rem 0.25rem; height: 1px; background: var(--color-warm); transform: scaleX(0); transform-origin: left; transition: transform var(--motion-duration-fast) var(--landing-ease); }
	.nav-links a:hover, .nav-links a.is-active { color: var(--color-ink-0); }
	.nav-links a.is-active::after { transform: scaleX(1); }
	.landing-page :global(.nav-cta) { grid-area: cta; }
	.nav-locale { grid-area: locale; min-width: 0; justify-self: end; }
	.landing-page :global(.nav-cta), .landing-page :global(.landing-btn), .landing-page :global(.contact-console), .landing-page :global(.email-pill) { min-height: 2.75rem; border-radius: 0.625rem; font-weight: 700; }

	.hero { position: relative; overflow: clip; padding: 3.5rem 0 2rem; }
	.hero::before { content: ''; position: absolute; top: -18rem; left: -10rem; width: 36rem; height: 36rem; border-radius: 999px; background: color-mix(in oklab, var(--color-warm) 12%, transparent); filter: blur(6rem); pointer-events: none; }
	.hero-layout { position: relative; display: grid; gap: 2.5rem; align-items: center; }
	.eyebrow, .section-label, .filter-kicker { font-family: var(--font-mono); font-variant-numeric: tabular-nums; text-transform: uppercase; }
	.eyebrow { display: inline-flex; align-items: center; gap: 0.625rem; color: var(--color-ink-2); font-size: 0.6875rem; letter-spacing: 0.08em; }
	.eyebrow > span { width: 0.5rem; height: 0.5rem; border-radius: 999px; background: var(--color-warm); box-shadow: 0 0 0 0.25rem var(--warm-soft); }
	.hero h1, .section h2, .cap-content h3, blockquote, .audience-note strong { font-family: var(--font-display); }
	.hero h1 { max-width: 48rem; margin-top: 1.5rem; font-size: clamp(1.875rem, 8vw, 4.25rem); font-weight: 500; letter-spacing: -0.045em; line-height: 1.2; word-break: var(--landing-word-break, keep-all); }
	.hero h1 :global(em) { display: block; width: fit-content; max-width: 100%; white-space: normal; color: var(--color-warm-text); font-style: normal; }
	.lead { max-width: 42rem; margin-top: 1.5rem !important; color: var(--color-ink-1); font-size: clamp(1rem, 2.2vw, 1.125rem); line-height: 1.72; word-break: var(--landing-word-break, keep-all); }
	.hero-actions { display: flex; flex-wrap: wrap; gap: 0.625rem; margin-top: 1.75rem; }
	.hero-context { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--color-line); }
	.hero-context > span { color: var(--color-ink-2); font-size: 0.8125rem; }
	.hero-context p { margin-top: 0.5rem; font-size: 0.875rem; }
	.hero-context i { margin-inline: 0.5rem; color: var(--color-warm-text); font-style: normal; }
	.hero-bottom { position: relative; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 0.25rem 1rem; margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--color-line); color: var(--color-ink-2); font-size: 0.75rem; }
	.hero-bottom a { display: inline-flex; align-items: center; gap: 0.75rem; min-height: 2.75rem; text-decoration: none; }
	.cue-touch { display: none; }
	@media (pointer: coarse) {
		.cue-fine { display: none; }
		.cue-touch { display: inline; }
	}
	.hero-bottom a:hover { color: var(--color-ink-0); }
	.lead :global(.desktop-break) { display: none; }
	.hero-board { min-width: 0; }

	.section { padding: 5rem 0; border-top: 1px solid var(--color-line); }
	#landing-content, .section[id], #environment-preview { scroll-margin-top: calc(var(--landing-nav-height) + 1rem); }
	.section-head { display: grid; gap: 1.75rem; margin-bottom: 2.5rem; }
	.section-label { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.75rem; color: var(--color-warm-text); font-size: 0.6875rem; letter-spacing: 0.08em; }
	.section-label span { font-weight: 700; }
	.section-label b { color: var(--color-ink-2); font-weight: 500; }
	.section h2 { max-width: 58rem; font-size: clamp(2rem, 7vw, 3.75rem); font-weight: 500; letter-spacing: -0.03em; line-height: 1.12; text-wrap: pretty; word-break: var(--landing-word-break, keep-all); }
	.section-head > div:last-child > p { max-width: 46rem; margin-top: 1rem; color: var(--color-ink-1); font-size: 1rem; word-break: var(--landing-word-break, keep-all); }

	.overview-section { background: color-mix(in oklab, var(--color-surface-base) 64%, var(--color-surface-canvas)); }

	.landing-page :global(.capability-grid) { display: grid; grid-auto-flow: dense; border-color: var(--color-line); background: var(--color-surface-base); }
	.cap-card { display: grid; grid-template-rows: 12rem minmax(0, 1fr); min-width: 0; border-bottom: 1px solid var(--color-line); }
	.cap-card:last-child { border-bottom: 0; }
	.cap-media { overflow: hidden; border-bottom: 1px solid var(--color-line); background: var(--color-surface-editorial-media); }
	.cap-media :global(.plate-graphic) { width: 100%; height: 100%; padding: 0.5rem; transition: transform var(--motion-duration-data) var(--motion-ease-out); }
	.cap-content { display: flex; min-width: 0; flex-direction: column; padding: 1.25rem; }
	.cap-meta { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 0.25rem 1rem; font-family: var(--font-mono); font-size: 0.6875rem; }
	.cap-meta span { color: var(--color-accent); text-transform: uppercase; }
	.cap-meta b { color: var(--color-ink-2); font-weight: 500; }
	.cap-content h3 { margin-top: 1.25rem; font-size: clamp(1.25rem, 4vw, 2rem); font-weight: 500; letter-spacing: -0.022em; line-height: 1.17; text-wrap: balance; word-break: var(--landing-word-break, keep-all); }
	.cap-content p { margin-top: 0.875rem; color: var(--color-ink-1); font-size: 0.8125rem; word-break: var(--landing-word-break, keep-all); }
	.landing-page :global(.cap-explore) { justify-content: flex-start; min-height: 2.75rem; width: fit-content; max-width: 100%; white-space: normal; margin-top: auto; padding: 1.25rem 0 0; color: var(--color-warm-text); font-size: 0.8125rem; }
	@media (hover: hover) and (pointer: fine) {
		.cap-card:has(:global(a:hover)) .cap-media :global(.plate-graphic), .cap-card:focus-within .cap-media :global(.plate-graphic) { transform: scale(1.03); }
	}

	.workflow-section { background: color-mix(in oklab, var(--color-surface-base) 64%, var(--color-surface-canvas)); }
	.workflow-layout { display: grid; gap: 1rem; align-items: start; }
	.landing-page :global(.filter-panel-surface) { border-color: var(--color-line); background: color-mix(in oklab, var(--color-surface-raised) 62%, transparent); }
	.filter-kicker { color: var(--color-accent); font-size: 0.6875rem; letter-spacing: 0.08em; }
	.filter-panel h3 { margin-top: 0.75rem; font-size: 1.5rem; line-height: 1.15; }
	.landing-page :global(.landing-workflow-filter) { margin-top: 1.5rem; }
	.landing-page :global(.landing-workflow-filter .toggle-option) { min-height: 2.75rem; }
	.filter-panel p { margin-top: 0.75rem; color: var(--color-ink-2); font-size: 0.75rem; }
	.filter-panel p :global(strong) { color: var(--color-warm-text); }
	.landing-page :global(.workflow-list) { border-color: var(--color-line); background: color-mix(in oklab, var(--color-surface-raised) 62%, transparent); }
	.lab-card { transition: opacity var(--motion-duration-base) var(--landing-ease), transform var(--motion-duration-base) var(--landing-ease); }
	.lab-card { display: grid; grid-template-columns: auto minmax(3.5rem, 5rem) minmax(0, 1fr); align-items: center; gap: 0.75rem; padding: 1rem; border-bottom: 1px solid var(--color-line); }
	.lab-card:last-of-type { border-bottom: 0; }
	.lab-card.is-muted { opacity: 0.62; transform: scale(0.99); }
	.workflow-index { align-self: start; color: var(--color-warm-text); font-family: var(--font-mono); font-size: 0.6875rem; }
	.landing-page :global(.lab-card-media) { width: 100%; aspect-ratio: 1 / 1; border-radius: 0.625rem; background: var(--color-surface-editorial-media); }
	.workflow-copy span { color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.6875rem; text-transform: uppercase; }
	.workflow-copy h3 { margin-top: 0.25rem; font-size: 1rem; }
	.workflow-copy p { margin-top: 0.35rem; color: var(--color-ink-2); font-size: 0.75rem; word-break: var(--landing-word-break, keep-all); }

	.work-section { overflow: hidden; background: color-mix(in oklab, var(--color-surface-base) 64%, var(--color-surface-canvas)); }
	.product-tour { display: grid; gap: 1.5rem; align-items: center; }
	.product-stage { min-width: 0; overflow: hidden; container-type: inline-size; border: 1px solid var(--color-line-2); border-radius: var(--radius-lg); background: var(--color-surface-canvas); }
	.stage-bar { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--color-line); color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.4; }
	.stage-bar b { min-width: 0; overflow: hidden; font-family: var(--font-mono); font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
	.stage-bar em { flex: 0 0 auto; font-family: var(--font-sans); font-style: normal; }
	.landing-page :global(.screen-main) { animation: screen-enter var(--motion-duration-data) var(--motion-ease-out) both; }
	.product-controls { min-width: 0; }
	.landing-page :global(.product-switcher) { margin-top: 1rem; }
	.landing-page :global(.product-switcher .toggle-option) { min-width: 0; min-height: 2.75rem; padding-inline: 0.25rem; white-space: normal; overflow-wrap: anywhere; }
	.product-description { margin-block: 1.5rem; min-height: 6.5rem; }
	.product-description h3 { font-family: var(--font-display); font-size: 1.5rem; font-weight: 500; line-height: 1.3; }
	.product-description p { margin-top: 0.75rem; color: var(--color-ink-1); font-size: 0.9375rem; word-break: var(--landing-word-break, keep-all); }
	.landing-page :global(.product-console) { min-height: 2.75rem; }
	@keyframes screen-enter { from { opacity: 0; transform: translateY(0.5rem); } to { opacity: 1; transform: translateY(0); } }

	.audience-layout { display: grid; gap: 2.5rem; align-items: center; }
	blockquote { max-width: 47rem; margin-top: 1.75rem !important; font-size: clamp(2rem, 7vw, 3.75rem); font-weight: 500; letter-spacing: -0.03em; line-height: 1.14; text-wrap: balance; word-break: var(--landing-word-break, keep-all); }
	.audience-list { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 2rem 0 0; padding: 0; list-style: none; }
	.glyph { padding: 0.5rem 0.75rem; border: 1px solid var(--color-line-2); border-radius: 999px; color: var(--color-ink-1); font-size: 0.75rem; }
	.quote-visual { display: grid; gap: 0.75rem; overflow: hidden; border: 1px solid var(--color-line); border-radius: 1rem; background: var(--color-surface-base); }
	.landing-page :global(.audience-figure) { min-height: 18rem; margin: 0; background: var(--color-surface-editorial-media); }
	.landing-page :global(.audience-figure .plate-graphic) { width: 100%; height: 100%; min-height: 18rem; }
	.audience-note { padding: 1.25rem; border-top: 1px solid var(--color-line); }
	.audience-note span { color: var(--color-accent); font-family: var(--font-mono); font-size: 0.6875rem; text-transform: uppercase; }
	.audience-note strong { display: block; margin-top: 0.75rem; font-size: 1.5rem; font-weight: 500; letter-spacing: -0.02em; line-height: 1.2; }
	.audience-note p { margin-top: 0.75rem; color: var(--color-ink-2); font-size: 0.8125rem; }

	.contact-section { position: relative; overflow: hidden; }
	.contact-panel { position: relative; overflow: hidden; display: grid; gap: 2rem; padding: clamp(1.5rem, 5vw, 3rem); border: 1px solid color-mix(in oklab, var(--color-warm) 34%, var(--color-line)); border-radius: 1.25rem; background: var(--gradient-editorial-cta), var(--color-surface-raised); }
	.contact-panel::after { content: ''; position: absolute; right: -8rem; bottom: -12rem; width: 24rem; height: 24rem; border: 1px solid color-mix(in oklab, var(--color-warm) 18%, transparent); border-radius: 999px; box-shadow: 0 0 0 3rem color-mix(in oklab, var(--color-warm) 4%, transparent), 0 0 0 6rem color-mix(in oklab, var(--color-warm) 3%, transparent); pointer-events: none; }
	.contact-panel > * { position: relative; z-index: 1; }
	.contact-panel h2 { margin-top: 1.25rem; }
	.contact-panel p { margin-top: 1rem; color: var(--color-ink-1); }
	.contact-actions { display: flex; flex-wrap: wrap; gap: 0.625rem; align-self: end; }
	.landing-page :global(.email-pill) { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }

	.footer { padding: 3rem 0 1.5rem; border-top: 1px solid var(--color-line); background: var(--color-surface-base); }
	.footer-layout { display: grid; gap: 2.5rem; }
	.footer-brand { display: grid; grid-template-columns: 2.25rem auto; align-items: center; width: fit-content; column-gap: 0.75rem; }
	.footer-brand img { grid-row: 1 / 3; width: 2.25rem; height: 2.25rem; object-fit: contain; }
	.footer-brand strong { align-self: end; }
	.footer-brand span { align-self: start; color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.625rem; text-transform: uppercase; }
	.footer-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.5rem; }
	.footer h3 { margin-bottom: 0.75rem; font-size: 0.75rem; }
	.footer a { display: flex; min-width: 2.75rem; min-height: 2.75rem; width: fit-content; align-items: center; color: var(--color-ink-2); font-size: 0.75rem; line-height: 1.35; text-decoration: none; }
	.footer a:hover { color: var(--color-ink-0); }
	.footer-bottom { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.5rem 1rem; margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--color-line); color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.75rem; }

	[data-reveal] { opacity: 1; transform: none; }
	:global(.landing-page.reveal-enabled) [data-reveal]:not(.is-visible) { opacity: 0; transform: translateY(1.5rem); }
	:global(.landing-page.reveal-enabled.reveal-ready) [data-reveal] { transition: opacity 600ms var(--landing-ease), transform 600ms var(--landing-ease); }

	@media (min-width: 768px) {
		.landing-page { --landing-gutter: 2rem; --landing-nav-height: 7rem; }
		.nav { grid-template-areas: 'brand cta locale' 'links links links'; grid-template-columns: minmax(0, 1fr) auto auto; }
		.nav-links { justify-content: center; }
		.hero { padding: 5rem 0 2rem; }
		.hero-bottom { margin-top: 4rem; }
		.section { padding: 7rem 0; }
		.landing-page :global(.capability-grid) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		.cap-card:nth-child(odd) { border-right: 1px solid var(--color-line); }
		.cap-card:nth-last-child(-n + 2) { border-bottom: 0; }
		.workflow-layout { grid-template-columns: minmax(15rem, 0.38fr) minmax(0, 0.62fr); }
		.filter-panel { position: sticky; top: 5.5rem; }
		.footer-layout { grid-template-columns: minmax(0, 1fr) minmax(22rem, 0.7fr); }
	}

	@media (min-width: 1024px) {
		.landing-page { --landing-nav-height: 4.5rem; }
		.nav { grid-template-areas: 'brand links cta locale'; grid-template-columns: auto minmax(0, 1fr) auto auto; }
		.hero h1 { font-size: clamp(2.25rem, 3.4vw, 3.75rem); }
		.lead :global(.desktop-break) { display: initial; }
		.hero-layout { grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr); gap: clamp(2rem, 4vw, 4rem); }
		.hero { padding-top: 6rem; }
		.section { padding: 8rem 0; }
		.product-tour { grid-template-columns: minmax(0, 1.8fr) minmax(0, 1fr); gap: 3rem; }
		.audience-layout { grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr); }
		.contact-panel { grid-template-columns: minmax(0, 1fr) auto; align-items: end; }
		.section-head { grid-template-columns: minmax(10rem, 0.3fr) minmax(0, 1fr); gap: 2rem; }
		.cap-card { grid-template: minmax(22rem, 1fr) / minmax(0, 0.82fr) minmax(0, 1.18fr); }
		.cap-media { border-right: 1px solid var(--color-line); border-bottom: 0; }
	}

	@media (prefers-reduced-motion: reduce) {
		.landing-page :global(*), .landing-page :global(*::before), .landing-page :global(*::after) { scroll-behavior: auto !important; transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
		[data-reveal], :global(.landing-page.reveal-enabled) [data-reveal]:not(.is-visible) { opacity: 1; transform: none; transition: none; }
	}
</style>
