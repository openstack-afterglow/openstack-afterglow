<script lang="ts">
	import { onMount } from 'svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import ToggleGroup from '$lib/components/ui/ToggleGroup.svelte';
	import { prefersReducedMotion } from '$lib/utils/motion';
	import LandingFigure from './LandingFigure.svelte';
	import LandingOpsBoard from './LandingOpsBoard.svelte';
	import PlateGraphic from './PlateGraphic.svelte';
	import type { PlateName } from './plateGraphics';

	interface Props {
		siteName: string;
		logoPath: string;
		consoleHref: string;
	}

	let { siteName, logoPath, consoleHref }: Props = $props();

	const navLinks = [
		{ label: '개요', href: '#overview' },
		{ label: '제공 기능', href: '#capabilities' },
		{ label: '워크플로우', href: '#workflow' },
		{ label: '화면', href: '#work' },
		{ label: '문의', href: '#contact' },
	];

	const overviewRows = [
		{ num: '01', title: '신청', body: '연구원이 필요한 실험 환경을 프로젝트 범위 안에서 요청합니다.' },
		{ num: '02', title: '배정', body: '관리자는 VM, 스토리지, 네트워크, 클러스터 자원을 정책에 맞게 제공합니다.' },
		{ num: '03', title: '관측', body: '사용량과 상태를 지표, 로그, 토폴로지로 확인합니다.' },
		{ num: '04', title: '재사용', body: '라이브러리 레이어와 스냅샷으로 다음 연구자의 환경 준비 시간을 줄입니다.' },
	];

	const capabilities: Array<{
		tag: string;
		name: PlateName;
		alt: string;
		title: string;
		body: string;
		proof: string;
	}> = [
		{
			tag: 'Compute',
			name: 'compute-allocation',
			alt: 'VM 서버, GPU 칩, vCPU, 스토리지 자원 배정 콜라주',
			title: 'VM·GPU·vCPU·스토리지 자원 배정',
			body: 'GPU 가속 VM에 필요한 GPU, vCPU, 메모리, 스토리지를 프로젝트 쿼터 안에서 배정해 개별 실험 환경을 바로 준비합니다.',
			proof: '프로젝트 쿼터 안에서',
		},
		{
			tag: 'Cluster',
			name: 'kubernetes',
			alt: 'K8s 클러스터 프로비저닝 콜라주',
			title: 'Kubernetes 실습과 실험 환경',
			body: 'K8s 클러스터 노드를 구성한 뒤 수업·연구 프로젝트의 Pod와 워크로드를 배포하고 상태를 콘솔에서 추적합니다.',
			proof: '노드부터 워크로드까지',
		},
		{
			tag: 'Library',
			name: 'layer',
			alt: 'AI ML 라이브러리 레이어 콜라주',
			title: 'AI/ML 라이브러리 레이어',
			body: '반복 설치가 필요한 프레임워크와 데이터 처리 도구를 불변 레이어로 관리해 팀별 환경을 재사용하고 포크합니다.',
			proof: '설치 대신 재사용',
		},
		{
			tag: 'Governance',
			name: 'security',
			alt: '보안과 거버넌스 콜라주',
			title: '교수자와 관리자용 운영 제어',
			body: '프로젝트, 사용자, 역할, 쿼터, 모니터링, 감사 로그를 묶어 연구실 단위 운영 기준을 유지합니다.',
			proof: '역할과 경계를 한곳에서',
		},
	];

	type WorkflowKind = 'compute' | 'data' | 'ops';
	type WorkflowFilter = 'all' | WorkflowKind;

	const filters = [
		{ label: '전체', value: 'all' },
		{ label: '컴퓨팅', value: 'compute' },
		{ label: '데이터', value: 'data' },
		{ label: '운영', value: 'ops' },
	];

	const workflowCards: Array<{
		kind: WorkflowKind;
		name: PlateName;
		alt: string;
		title: string;
		body: string;
		meta: string;
	}> = [
		{
			kind: 'compute',
			name: 'api',
			alt: 'API 자동화 콜라주',
			title: '컴퓨팅 자원 신청',
			body: '연구원이 필요한 이미지, flavor, 네트워크, 키를 선택해 실험 인스턴스를 준비합니다.',
			meta: 'VM · GPU · Network',
		},
		{
			kind: 'data',
			name: 'shared-data',
			alt: '공유 데이터 공간과 스냅샷 흐름 콜라주',
			title: '공유 데이터 공간',
			body: '파일 스토리지와 스냅샷으로 팀 데이터와 실험 산출물을 안전하게 이어갑니다.',
			meta: 'Share · Snapshot',
		},
		{
			kind: 'compute',
			name: 'kubernetes',
			alt: 'K8s 클러스터 프로비저닝 콜라주',
			title: '클러스터 실습',
			body: '수업이나 프로젝트별 Kubernetes 클러스터를 만들고 노드 구성을 추적합니다.',
			meta: 'Cluster · Node',
		},
		{
			kind: 'ops',
			name: 'monitoring',
			alt: '모니터링과 관측성 콜라주',
			title: '관측 가능한 운영',
			body: '지표 기반 화면을 통해 사용량과 병목을 빠르게 확인합니다.',
			meta: 'Metric · Log',
		},
		{
			kind: 'ops',
			name: 'release',
			alt: '클라우드 배포 흐름 콜라주',
			title: '보안과 감사',
			body: '권한 경계, 키 분리 암호화, 작업 로그로 멀티테넌트 위험을 줄입니다.',
			meta: 'Role · Audit',
		},
	];

	const methodSteps = [
		{ step: '01', label: 'Project', title: '연구 목적에 맞는 프로젝트를 만든다', detail: '사용자와 역할, 자원 경계를 먼저 정합니다.' },
		{ step: '02', label: 'Allocate', title: '컴퓨팅과 데이터 자원을 배정한다', detail: '정해진 쿼터 안에서 필요한 환경을 제공합니다.' },
		{ step: '03', label: 'Observe', title: '실험 환경을 실행하고 관측한다', detail: '상태와 사용량, 연결 관계를 한 흐름에서 봅니다.' },
		{ step: '04', label: 'Reuse', title: '레이어와 스냅샷으로 다시 쓴다', detail: '검증한 환경과 데이터를 다음 연구에 이어줍니다.' },
	];

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
		const reducedMotion = prefersReducedMotion();
		html.style.scrollBehavior = reducedMotion ? 'auto' : 'smooth';

		const handleScroll = () => updateActiveSection();
		updateActiveSection();
		window.addEventListener('scroll', handleScroll, { passive: true });

		const revealItems = Array.from(landingRoot.querySelectorAll<HTMLElement>('[data-reveal]'));
		if (!reducedMotion && typeof window.IntersectionObserver === 'function') {
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
				{ threshold: 0.18, rootMargin: '0px 0px -8% 0px' },
			);
			revealItems.forEach((item) => revealObserver?.observe(item));
			revealReadyFrame = window.requestAnimationFrame(() => landingRoot.classList.add('reveal-ready'));
		}

		return () => {
			window.removeEventListener('scroll', handleScroll);
			revealObserver?.disconnect();
			revealObserver = undefined;
			if (revealReadyFrame !== undefined) window.cancelAnimationFrame(revealReadyFrame);
			revealReadyFrame = undefined;
			landingRoot.classList.remove('reveal-enabled', 'reveal-ready');
			html.style.scrollBehavior = previousScrollBehavior;
		};
	});
</script>

<div class="landing-page" bind:this={landingRoot}>
	<a class="skip-link" href="#landing-content" onclick={focusLandingContent}>본문으로 건너뛰기</a>

	<header class="top-strip">
		<nav class="container nav" aria-label="주요 내비게이션">
			<a class="brand" href="/">
				<img src={logoPath} alt="" />
				<span>{siteName}</span>
				<small>Research cloud</small>
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
			<Button variant="primary" size="md" class="nav-cta" href={consoleHref}>콘솔 접속</Button>
		</nav>
	</header>

	<div id="landing-content" tabindex="-1">
		<section class="hero">
			<div class="container hero-layout">
				<div class="hero-copy" data-reveal>
					<div class="eyebrow"><span aria-hidden="true"></span>Research infrastructure, delivered</div>
					<h1>연구실 클라우드를<br />더 쉽게 제공하는 <em>운영 콘솔</em></h1>
					<p class="lead">Afterglow는 교수, 연구원, 실습팀이 필요한 컴퓨팅 자원과 공유 스토리지, Kubernetes 환경, AI/ML 라이브러리 레이어를 한 곳에서 신청하고 운영하도록 설계된 클라우드 포털입니다.</p>
					<div class="hero-actions">
						<Button variant="primary" size="lg" class="landing-btn" href={consoleHref}>콘솔 접속</Button>
						<Button variant="outline" size="lg" class="landing-btn" href="#capabilities">기능 보기</Button>
					</div>
					<ul class="hero-facts" aria-label="Afterglow 핵심 운영 범위">
						<li><b>Project</b><span>연구팀별 자원 경계</span></li>
						<li><b>Policy</b><span>역할과 쿼터 제어</span></li>
						<li><b>Reuse</b><span>환경과 데이터 재사용</span></li>
					</ul>
				</div>
				<div class="hero-board" data-reveal><LandingOpsBoard /></div>
			</div>
		</section>

		<section id="overview" class="section overview-section">
			<div class="container">
				<div class="section-head" data-reveal>
					<div class="section-label"><span>운영의 범위</span><b>From request to reuse</b></div>
					<div>
						<h2>클라우드를 제공하는 일은<br />자원 생성보다 넓습니다</h2>
						<p>연구실에서는 사용자 초대, 프로젝트 쿼터, 이미지와 네트워크, 데이터 공유, GPU 사용량, 실습 클러스터, 감사 로그가 한꺼번에 얽힙니다. Afterglow는 이 흐름을 연구 조직이 이해할 수 있는 콘솔로 묶습니다.</p>
					</div>
				</div>
				<div class="overview-layout" data-reveal>
					<Card surface="subtle" padding="none" class="overview-ledger">
						{#each overviewRows as row}
							<article class="overview-row">
								<b>{row.num}</b>
								<div><h3>{row.title}</h3><p>{row.body}</p></div>
								<span aria-hidden="true">↗</span>
							</article>
						{/each}
					</Card>
					<div class="overview-proof">
						<LandingFigure class="overview-screen" name="console" fit="cover" alt="Afterglow 프로젝트 대시보드 화면">프로젝트 대시보드 / 자원과 사용량</LandingFigure>
						<div class="proof-note"><span>하나의 프로젝트 안에서</span><strong>사람 · 정책 · 인프라</strong><p>운영자는 전체 흐름을 읽고, 연구자는 필요한 환경에 바로 접근합니다.</p></div>
					</div>
				</div>
			</div>
		</section>

		<section id="capabilities" class="section">
			<div class="container">
				<div class="section-head" data-reveal>
					<div class="section-label"><span>제공 기능</span><b>Operational surfaces</b></div>
					<div>
						<h2>연구 클라우드 제공에 필요한<br />표면을 한데 모읍니다</h2>
						<p>사용자는 실험을 시작하고, 운영자는 경계를 유지하고, 교수자는 팀 단위 자원 흐름을 확인할 수 있어야 합니다.</p>
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
					<div class="section-label"><span>워크플로우</span><b>Choose a context</b></div>
					<div>
						<h2>연구실마다 다른 사용 흐름을<br />필터처럼 꺼내 봅니다</h2>
						<p>컴퓨팅, 데이터, 운영 맥락을 전환하며 필요한 자원과 상태를 한 흐름에서 확인합니다.</p>
					</div>
				</div>
				<div class="workflow-layout" data-reveal>
					<aside class="filter-panel">
						<Card surface="subtle" padding="lg" class="filter-panel-surface">
							<span class="filter-kicker">View by domain</span>
							<h3>필요한 운영 맥락을<br />선택하세요</h3>
							<ToggleGroup value={selectedFilter} options={filters} onchange={selectFilter} size="sm" fullWidth class="landing-workflow-filter" ariaLabel="워크플로우 필터" />
							<p><b>{visibleCount}</b>개의 관련 흐름이 표시됩니다.</p>
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
						{#if visibleCount === 0}
							<p class="empty-state" role="status" aria-live="polite">선택한 조건에 맞는 워크플로우가 없습니다. 전체를 선택해 다시 확인하세요.</p>
						{/if}
					</Card>
				</div>
			</div>
		</section>

		<section class="section method-section">
			<div class="container">
				<div class="section-head compact-head" data-reveal>
					<div class="section-label"><span>제공 방식</span><b>Four steps</b></div>
					<div><h2>제공 방식은 네 단계로 정리됩니다</h2></div>
				</div>
				<div data-reveal>
					<Card surface="subtle" padding="none" class="method-grid">
						{#each methodSteps as step}
							<article class="method-step">
								<div class="method-meta"><b>{step.step}</b><span>{step.label}</span></div>
								<div class="method-mark" aria-hidden="true"><span></span></div>
								<div><h3>{step.title}</h3><p>{step.detail}</p></div>
							</article>
						{/each}
					</Card>
				</div>
			</div>
		</section>

		<section id="work" class="section work-section">
			<div class="container">
				<div class="section-head" data-reveal>
					<div class="section-label"><span>제품 화면</span><b>Operational proof</b></div>
					<div>
						<h2>실제 콘솔은 운영자가<br />빠르게 읽을 수 있어야 합니다</h2>
						<p>대시보드, 관리자, 클러스터, 네트워크 화면은 자원 상태와 연결 관계를 같은 운영 문법으로 보여줍니다.</p>
					</div>
				</div>
				<div class="product-stage" data-reveal>
					<div class="stage-bar"><span><i></i><i></i><i></i></span><b>afterglow / project / research-lab</b><em>live console</em></div>
					<div class="work-grid">
						<LandingFigure class="screen-main" name="kubernetes" fit="cover" alt="Afterglow Kubernetes 클러스터 화면">Kubernetes 클러스터 / 노드와 워크로드</LandingFigure>
						<div class="screen-stack">
							<LandingFigure name="security" fit="cover" alt="Afterglow 관리자 개요 화면">관리자 개요 / 사용량과 서비스 상태</LandingFigure>
							<LandingFigure name="network-topology" fit="cover" alt="Afterglow 네트워크 토폴로지 화면">네트워크 토폴로지 / 연결 관계</LandingFigure>
						</div>
					</div>
				</div>
			</div>
		</section>

		<section class="section audience-section">
			<div class="container audience-layout">
				<div data-reveal>
					<div class="section-label"><span>사용자</span><b>Built for the lab</b></div>
					<blockquote>“실험 환경을 만드는 시간이 줄어들면, 연구자는 다시 질문에 집중할 수 있습니다”</blockquote>
					<ul class="audience-list" aria-label="대상 사용자와 조직">
						<li class="glyph">연구실</li><li class="glyph">교수자</li><li class="glyph">연구원</li><li class="glyph">실습팀</li><li class="glyph">연구 조직</li>
					</ul>
				</div>
				<div class="quote-visual" data-reveal>
					<LandingFigure class="audience-figure" name="professor" alt="교수자와 연구원이 프로젝트 환경을 함께 운영하는 화면" />
					<div class="audience-note"><span>Shared context</span><strong>같은 프로젝트를<br />서로 다른 역할로</strong><p>사용자는 환경을 쓰고, 교수자는 흐름을 보고, 운영자는 경계를 지킵니다.</p></div>
				</div>
			</div>
		</section>

		<section id="contact" class="section contact-section">
			<div class="container">
				<div class="contact-panel" data-reveal>
					<div>
						<div class="eyebrow"><span aria-hidden="true"></span>Console ready</div>
						<h2>연구실 클라우드 제공 방식을<br />정리할 준비가 되셨나요?</h2>
						<p>데모, PoC, 학내 연구실 배포 논의를 위해 연락 주세요.</p>
					</div>
					<div class="contact-actions">
						<Button variant="primary" size="lg" class="contact-console" href={consoleHref}>콘솔 접속</Button>
						<Button variant="outline" size="lg" class="email-pill" href={`mailto:${email}`} ariaLabel="이메일 문의 보내기">{email}</Button>
					</div>
				</div>
			</div>
		</section>
	</div>

	<footer class="footer">
		<div class="container footer-layout">
			<div class="footer-brand"><img src={logoPath} alt="" /><strong>{siteName}</strong><span>Research cloud operations</span></div>
			<div class="footer-grid">
				<div><h3>제품</h3><a href="#overview">개요</a><a href="#capabilities">제공 기능</a><a href="#workflow">워크플로우</a></div>
				<div><h3>연락</h3><a href={`mailto:${email}`}>{email}</a><a href="https://github.com/openstack-afterglow/openstack-afterglow">GitHub 저장소</a></div>
			</div>
		</div>
		<div class="container footer-bottom"><p>© 2026 {siteName}. 연구 클라우드 운영 콘솔.</p><span>Seoul · Republic of Korea</span></div>
	</footer>
</div>

<style>
	.landing-page {
		--landing-ease: cubic-bezier(0.2, 0.8, 0.2, 1);
		--landing-container: 80rem;
		--landing-gutter: 1rem;
		--landing-nav-height: 6.25rem;
		min-height: 100%;
		padding-top: var(--landing-nav-height);
		background: var(--color-surface-canvas);
		color: var(--color-ink-0);
		font-family: var(--font-sans);
		font-weight: 400;
		letter-spacing: -0.01em;
		font-size: 0.9375rem;
		line-height: 1.65;
		-webkit-font-smoothing: antialiased;
		text-rendering: optimizeLegibility;
	}
	.landing-page :global(img) { display: block; max-width: 100%; }
	.landing-page :global(a) { color: inherit; }
	.landing-page h1, .landing-page h2, .landing-page h3, .landing-page p, .landing-page blockquote { margin: 0; }
	.landing-page .container { width: min(var(--landing-container), calc(100% - var(--landing-gutter) * 2)); margin-inline: auto; }
	.landing-page :global(a:focus-visible), .landing-page :global(button:focus-visible) { outline: none; box-shadow: var(--focus-ring); }

	.skip-link { position: fixed; top: 0.75rem; left: 1rem; z-index: var(--z-toast); display: inline-flex; min-height: 2.75rem; align-items: center; padding: 0 0.875rem; border: 1px solid var(--color-warm); border-radius: 0.5rem; background: var(--color-ink-0); color: var(--color-surface-canvas); font-weight: 700; text-decoration: none; transform: translateY(-160%); transition: transform var(--motion-duration-fast) var(--landing-ease); }
	.skip-link:focus-visible { transform: translateY(0); }

	.top-strip { position: fixed; inset: 0 0 auto; z-index: var(--z-sidebar); border-bottom: 1px solid color-mix(in oklab, var(--color-line) 84%, transparent); background: color-mix(in oklab, var(--color-surface-canvas) 88%, transparent); backdrop-filter: blur(1.125rem); }
	.nav { display: grid; grid-template-areas: 'brand cta' 'links links'; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 0.25rem 0.75rem; min-height: var(--landing-nav-height); padding-block: 0.5rem; }
	.brand { grid-area: brand; display: grid; grid-template-columns: 2rem auto; min-height: 2.75rem; align-items: center; column-gap: 0.625rem; width: fit-content; text-decoration: none; }
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
	.landing-page :global(.nav-cta), .landing-page :global(.landing-btn), .landing-page :global(.contact-console), .landing-page :global(.email-pill) { min-height: 2.75rem; border-radius: 0.625rem; font-weight: 700; }

	.hero { position: relative; overflow: hidden; padding: 4.5rem 0 5rem; }
	.hero::before { content: ''; position: absolute; top: -18rem; left: -10rem; width: 36rem; height: 36rem; border-radius: 999px; background: color-mix(in oklab, var(--color-warm) 12%, transparent); filter: blur(6rem); pointer-events: none; }
	.hero-layout { position: relative; display: grid; gap: 3rem; align-items: center; }
	.eyebrow, .section-label, .filter-kicker { font-family: var(--font-mono); font-variant-numeric: tabular-nums; text-transform: uppercase; }
	.eyebrow { display: inline-flex; align-items: center; gap: 0.625rem; color: var(--color-ink-2); font-size: 0.6875rem; letter-spacing: 0.08em; }
	.eyebrow > span { width: 0.5rem; height: 0.5rem; border-radius: 999px; background: var(--color-warm); box-shadow: 0 0 0 0.25rem var(--warm-soft); }
	.hero h1, .section h2, .cap-content h3, blockquote, .audience-note strong { font-family: var(--font-display); }
	.hero h1 { max-width: 48rem; margin-top: 1.5rem; font-size: clamp(2.75rem, 10vw, 4.25rem); font-weight: 500; letter-spacing: -0.04em; line-height: 1.06; text-wrap: balance; word-break: keep-all; }
	.hero h1 em { display: block; width: fit-content; color: var(--color-warm); font-style: normal; white-space: nowrap; }
	.lead { max-width: 42rem; margin-top: 1.5rem !important; color: var(--color-ink-1); font-size: clamp(1rem, 2.2vw, 1.125rem); line-height: 1.72; word-break: keep-all; }
	.hero-actions { display: flex; flex-wrap: wrap; gap: 0.625rem; margin-top: 1.75rem; }
	.hero-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem; margin: 2.5rem 0 0; padding: 1rem 0 0; border-top: 1px solid var(--color-line); list-style: none; }
	.hero-facts li { min-width: 0; }
	.hero-facts b { display: block; color: var(--color-accent); font-family: var(--font-mono); font-size: 0.6875rem; font-weight: 500; text-transform: uppercase; }
	.hero-facts span { display: block; margin-top: 0.25rem; color: var(--color-ink-2); font-size: 0.6875rem; word-break: keep-all; }
	.hero-board { min-width: 0; }

	.section { padding: 4.5rem 0; border-top: 1px solid var(--color-line); }
	#landing-content, .section[id] { scroll-margin-top: calc(var(--landing-nav-height) + 1rem); }
	.section-head { display: grid; gap: 1.75rem; margin-bottom: 2.5rem; }
	.section-label { display: flex; align-items: center; gap: 0.75rem; color: var(--color-warm-text); font-size: 0.6875rem; letter-spacing: 0.08em; }
	.section-label span { font-weight: 700; }
	.section-label b { color: var(--color-ink-2); font-weight: 500; }
	.section h2 { max-width: 58rem; font-size: clamp(2rem, 7vw, 3.75rem); font-weight: 500; letter-spacing: -0.03em; line-height: 1.12; text-wrap: balance; word-break: keep-all; }
	.section-head > div:last-child > p { max-width: 46rem; margin-top: 1rem; color: var(--color-ink-1); font-size: 1rem; word-break: keep-all; }

	.overview-section { background: color-mix(in oklab, var(--color-surface-base) 64%, var(--color-surface-canvas)); }
	.overview-layout { display: grid; gap: 1rem; }
	.landing-page :global(.overview-ledger) { border-color: var(--color-line); background: color-mix(in oklab, var(--color-surface-raised) 62%, transparent); }
	.overview-row { display: grid; grid-template-columns: 2rem minmax(0, 1fr) auto; gap: 0.75rem; align-items: start; padding: 1.25rem; border-bottom: 1px solid var(--color-line); }
	.overview-row:last-child { border-bottom: 0; }
	.overview-row > b { color: var(--color-warm-text); font-family: var(--font-mono); font-size: 0.6875rem; }
	.overview-row h3 { font-size: 1rem; }
	.overview-row p { margin-top: 0.25rem; color: var(--color-ink-2); font-size: 0.8125rem; word-break: keep-all; }
	.overview-row > span { color: var(--color-ink-2); }
	.overview-proof { position: relative; min-height: 24rem; overflow: hidden; border: 1px solid var(--color-line); border-radius: 1rem; background: var(--color-surface-editorial-media); }
	.landing-page :global(.overview-screen) { position: absolute; inset: 0; margin: 0; }
	.landing-page :global(.overview-screen .plate-graphic) { width: 100%; height: 100%; opacity: 0.74; }
	.landing-page :global(.overview-screen figcaption) { display: none; }
	.proof-note { position: absolute; inset: auto 1rem 1rem; max-width: 22rem; padding: 1rem; border: 1px solid var(--color-line-2); border-radius: 0.75rem; background: color-mix(in oklab, var(--color-surface-canvas) 86%, transparent); backdrop-filter: blur(0.75rem); }
	.proof-note span { color: var(--color-warm-text); font-family: var(--font-mono); font-size: 0.6875rem; text-transform: uppercase; }
	.proof-note strong { display: block; margin-top: 0.35rem; font-size: 1.25rem; }
	.proof-note p { margin-top: 0.5rem; color: var(--color-ink-2); font-size: 0.75rem; }

	.landing-page :global(.capability-grid) { display: grid; border-color: var(--color-line); background: color-mix(in oklab, var(--color-surface-raised) 62%, transparent); }
	.cap-card { display: grid; grid-template-rows: 12rem minmax(0, 1fr); min-width: 0; border-bottom: 1px solid var(--color-line); }
	.cap-card:last-child { border-bottom: 0; }
	.cap-media { overflow: hidden; border-bottom: 1px solid var(--color-line); background: var(--color-surface-editorial-media); }
	.cap-media :global(.plate-graphic) { width: 100%; height: 100%; padding: 0.5rem; }
	.cap-content { display: flex; min-width: 0; flex-direction: column; padding: 1.25rem; }
	.cap-meta { display: flex; align-items: center; justify-content: space-between; gap: 1rem; font-family: var(--font-mono); font-size: 0.6875rem; }
	.cap-meta span { color: var(--color-accent); text-transform: uppercase; }
	.cap-meta b { color: var(--color-ink-2); font-weight: 500; }
	.cap-content h3 { margin-top: 1.25rem; font-size: clamp(1.25rem, 4vw, 2rem); font-weight: 500; letter-spacing: -0.022em; line-height: 1.17; text-wrap: balance; word-break: keep-all; }
	.cap-content p { margin-top: 0.875rem; color: var(--color-ink-1); font-size: 0.8125rem; word-break: keep-all; }

	.workflow-section { background: color-mix(in oklab, var(--color-surface-base) 64%, var(--color-surface-canvas)); }
	.workflow-layout { display: grid; gap: 1rem; align-items: start; }
	.landing-page :global(.filter-panel-surface) { border-color: var(--color-line); background: color-mix(in oklab, var(--color-surface-raised) 62%, transparent); }
	.filter-kicker { color: var(--color-accent); font-size: 0.6875rem; letter-spacing: 0.08em; }
	.filter-panel h3 { margin-top: 0.75rem; font-size: 1.5rem; line-height: 1.15; }
	.landing-page :global(.landing-workflow-filter) { margin-top: 1.5rem; }
	.landing-page :global(.landing-workflow-filter .toggle-option) { min-height: 2.75rem; }
	.filter-panel p { margin-top: 0.75rem; color: var(--color-ink-2); font-size: 0.75rem; }
	.filter-panel p b { color: var(--color-warm-text); }
	.landing-page :global(.workflow-list) { border-color: var(--color-line); background: color-mix(in oklab, var(--color-surface-raised) 62%, transparent); }
	.lab-card { transition: opacity var(--motion-duration-base) var(--landing-ease), transform var(--motion-duration-base) var(--landing-ease); }
	.lab-card { display: grid; grid-template-columns: auto minmax(5.5rem, 7rem) minmax(0, 1fr); align-items: center; gap: 0.75rem; padding: 0.75rem; border-bottom: 1px solid var(--color-line); }
	.lab-card:last-of-type { border-bottom: 0; }
	.lab-card.is-muted { opacity: 0.62; transform: scale(0.99); }
	.workflow-index { align-self: start; color: var(--color-warm-text); font-family: var(--font-mono); font-size: 0.6875rem; }
	.landing-page :global(.lab-card-media) { width: 100%; aspect-ratio: 1 / 1; border-radius: 0.625rem; background: var(--color-surface-editorial-media); }
	.workflow-copy span { color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.625rem; text-transform: uppercase; }
	.workflow-copy h3 { margin-top: 0.25rem; font-size: 1rem; }
	.workflow-copy p { margin-top: 0.35rem; color: var(--color-ink-2); font-size: 0.75rem; word-break: keep-all; }
	.empty-state { padding: 1rem; border: 1px dashed var(--color-line-2); border-radius: 0.75rem; color: var(--color-ink-2); }

	.landing-page :global(.method-grid) { display: grid; border-color: var(--color-line); background: color-mix(in oklab, var(--color-surface-raised) 62%, transparent); }
	.method-step { display: grid; grid-template-columns: auto 1fr; gap: 1rem; padding: 1.5rem; border-bottom: 1px solid var(--color-line); }
	.method-step:last-child { border-bottom: 0; }
	.method-meta { display: flex; flex-direction: column; align-items: flex-start; gap: 0.25rem; font-family: var(--font-mono); font-size: 0.6875rem; text-transform: uppercase; }
	.method-meta b { color: var(--color-warm-text); }
	.method-meta span { color: var(--color-ink-2); }
	.method-mark { display: none; }
	.method-step h3 { font-size: 1.125rem; line-height: 1.2; word-break: keep-all; }
	.method-step p { margin-top: 0.625rem; color: var(--color-ink-2); font-size: 0.75rem; word-break: keep-all; }

	.work-section { overflow: hidden; background: color-mix(in oklab, var(--color-surface-base) 64%, var(--color-surface-canvas)); }
	.product-stage { overflow: hidden; border: 1px solid var(--color-line-2); border-radius: 1rem; background: var(--color-surface-base); box-shadow: 0 2rem 6rem color-mix(in oklab, var(--color-surface-canvas) 78%, transparent); }
	.stage-bar { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 0.75rem; padding: 0.75rem 1rem; border-bottom: 1px solid var(--color-line); color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.625rem; }
	.stage-bar > span { display: flex; gap: 0.25rem; }
	.stage-bar i { width: 0.4375rem; height: 0.4375rem; border-radius: 999px; background: var(--color-line-2); }
	.stage-bar b { overflow: hidden; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
	.stage-bar em { color: var(--color-state-success-text); font-style: normal; text-transform: uppercase; }
	.work-grid { display: grid; gap: 0.75rem; padding: 0.75rem; }
	.landing-page :global(.screen-main), .landing-page :global(.screen-stack figure) { margin: 0; overflow: hidden; border: 1px solid var(--color-line); border-radius: 0.75rem; background: var(--color-surface-editorial-media); }
	.landing-page :global(.screen-main .plate-graphic) { width: 100%; aspect-ratio: 16 / 10; }
	.screen-stack { display: grid; gap: 0.75rem; }
	.landing-page :global(.screen-stack .plate-graphic) { width: 100%; aspect-ratio: 16 / 10; }
	.landing-page :global(figcaption) { padding: 0.625rem 0.75rem; border-top: 1px solid var(--color-line); color: var(--color-ink-2); font-family: var(--font-mono); font-size: 0.625rem; }

	.audience-layout { display: grid; gap: 2.5rem; align-items: center; }
	blockquote { max-width: 47rem; margin-top: 1.75rem !important; font-size: clamp(2rem, 7vw, 3.75rem); font-weight: 500; letter-spacing: -0.03em; line-height: 1.14; text-wrap: balance; word-break: keep-all; }
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
		.landing-page { --landing-gutter: 2rem; --landing-nav-height: 4.5rem; }
		.nav { display: flex; min-height: 4.5rem; padding-block: 0; }
		.nav-links { flex: 1 1 auto; justify-content: center; }
		.hero { padding: 5.5rem 0 6rem; }
		.hero-facts span { font-size: 0.75rem; }
		.section { padding: 5.5rem 0; }
		.overview-layout { grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr); }
		.landing-page :global(.capability-grid) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		.cap-card:nth-child(odd) { border-right: 1px solid var(--color-line); }
		.cap-card:nth-last-child(-n + 2) { border-bottom: 0; }
		.workflow-layout { grid-template-columns: minmax(14rem, 0.36fr) minmax(0, 0.64fr); }
		.filter-panel { position: sticky; top: 5.5rem; }
		.landing-page :global(.method-grid) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		.method-step:nth-child(odd) { border-right: 1px solid var(--color-line); }
		.method-step:nth-last-child(-n + 2) { border-bottom: 0; }
		.work-grid { grid-template-columns: minmax(0, 1.25fr) minmax(15rem, 0.75fr); }
		.audience-layout { grid-template-columns: minmax(0, 1.05fr) minmax(20rem, 0.95fr); }
		.contact-panel { grid-template-columns: minmax(0, 1fr) auto; align-items: end; }
		.footer-layout { grid-template-columns: minmax(0, 1fr) minmax(22rem, 0.7fr); }
	}

	@media (min-width: 1024px) {
		.hero h1 { font-size: clamp(3.25rem, 5vw, 4.25rem); }
		.hero-layout { grid-template-columns: minmax(0, 0.86fr) minmax(32rem, 1.14fr); gap: clamp(2rem, 4vw, 4rem); }
		.section-head { grid-template-columns: minmax(10rem, 0.3fr) minmax(0, 1fr); gap: 2rem; }
		.cap-card { grid-template: minmax(20rem, 1fr) / minmax(14rem, 0.82fr) minmax(0, 1.18fr); }
		.cap-media { border-right: 1px solid var(--color-line); border-bottom: 0; }
		.landing-page :global(.method-grid) { grid-template-columns: repeat(4, minmax(0, 1fr)); }
		.method-step { grid-template-columns: 1fr; min-height: 23rem; border-right: 1px solid var(--color-line); border-bottom: 0 !important; }
		.method-step:last-child { border-right: 0; }
		.method-mark { display: grid; grid-template-columns: 1fr auto 1fr; place-items: center; align-self: center; width: 100%; }
		.method-mark::before, .method-mark::after { content: ''; width: 100%; border-top: 1px dashed var(--color-line-2); }
		.method-mark span { width: 0.75rem; height: 0.75rem; border: 2px solid var(--color-warm); border-radius: 999px; box-shadow: 0 0 0 0.35rem var(--warm-soft); }
	}

	@media (prefers-reduced-motion: reduce) {
		.landing-page :global(*), .landing-page :global(*::before), .landing-page :global(*::after) { scroll-behavior: auto !important; transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
		[data-reveal], :global(.landing-page.reveal-enabled) [data-reveal]:not(.is-visible) { opacity: 1; transform: none; transition: none; }
	}
</style>
