import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import LandingPage from '../LandingPage.svelte';

const email = 'pieroot@konkuk.ac.kr';

function renderLanding(consoleHref = '/login') {
	return render(LandingPage, {
		siteName: 'Test Cloud',
		logoPath: '/brand.svg',
		consoleHref,
	});
}

function landingRoot(container: HTMLElement) {
	const root = container.querySelector<HTMLElement>('.landing-page');
	if (!root) throw new Error('Landing root was not rendered');
	return root;
}

function workflowCards(container: HTMLElement) {
	return Array.from(container.querySelectorAll<HTMLElement>('.lab-card'));
}

function mutedWorkflowCount(container: HTMLElement) {
	return workflowCards(container).filter((card) => card.classList.contains('is-muted')).length;
}

function setScrollY(value: number) {
	Object.defineProperty(window, 'scrollY', {
		configurable: true,
		writable: true,
		value,
	});
}

function setMatchMedia(reducedMotion: boolean) {
	Object.defineProperty(window, 'matchMedia', {
		configurable: true,
		writable: true,
		value: vi.fn((query: string) => ({
			matches: reducedMotion && query === '(prefers-reduced-motion: reduce)',
			media: query,
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
			onchange: null,
		})),
	});
}

function mockSectionTops(tops: Record<string, number>) {
	return vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
		const isTopStrip = this.classList.contains('top-strip');
		const top = isTopStrip ? 0 : (tops[this.id] ?? 999);
		const height = isTopStrip ? 72 : 100;
		return {
			top,
			bottom: top + height,
			left: 0,
			right: 0,
			width: 0,
			height,
			x: 0,
			y: top,
			toJSON: () => ({}),
		} as DOMRect;
	});
}


class TestIntersectionObserver {
	static instances: TestIntersectionObserver[] = [];
	readonly callback: IntersectionObserverCallback;
	readonly options: IntersectionObserverInit | undefined;
	readonly observed: Element[] = [];
	readonly unobserve = vi.fn((target: Element) => {
		const index = this.observed.indexOf(target);
		if (index >= 0) this.observed.splice(index, 1);
	});
	readonly disconnect = vi.fn();

	constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
		this.callback = callback;
		this.options = options;
		TestIntersectionObserver.instances.push(this);
	}

	observe(target: Element) {
		this.observed.push(target);
	}

	takeRecords() {
		return [] as IntersectionObserverEntry[];
	}

	trigger(target: Element = this.observed[0]) {
		this.callback(
			[
				{
					target,
					isIntersecting: true,
					intersectionRatio: 1,
				} as IntersectionObserverEntry,
			],
			this as unknown as IntersectionObserver,
		);
	}
}

const originalMatchMediaDescriptor = Object.getOwnPropertyDescriptor(window, 'matchMedia');
const originalIntersectionObserverDescriptor = Object.getOwnPropertyDescriptor(window, 'IntersectionObserver');
const originalScrollYDescriptor = Object.getOwnPropertyDescriptor(window, 'scrollY');

beforeEach(() => {
	vi.useFakeTimers();
	vi.clearAllMocks();
	setMatchMedia(false);
	Reflect.deleteProperty(window, 'IntersectionObserver');
	Reflect.deleteProperty(globalThis, 'IntersectionObserver');
	setScrollY(0);
	document.documentElement.style.scrollBehavior = '';
	TestIntersectionObserver.instances = [];
});

afterEach(() => {
	cleanup();
	vi.clearAllTimers();
	vi.useRealTimers();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();

	if (originalMatchMediaDescriptor) {
		Object.defineProperty(window, 'matchMedia', originalMatchMediaDescriptor);
	} else {
		Reflect.deleteProperty(window, 'matchMedia');
	}
	if (originalIntersectionObserverDescriptor) {
		Object.defineProperty(window, 'IntersectionObserver', originalIntersectionObserverDescriptor);
	} else {
		Reflect.deleteProperty(window, 'IntersectionObserver');
	}
	if (originalScrollYDescriptor) {
		Object.defineProperty(window, 'scrollY', originalScrollYDescriptor);
	} else {
		Reflect.deleteProperty(window, 'scrollY');
	}
	document.documentElement.style.scrollBehavior = '';
});

describe('LandingPage', () => {
	it('renders the semantic landing structure, navigation, copy, and runtime branding', async () => {
		const { container } = renderLanding();

		const skipLink = screen.getByRole('link', { name: '본문으로 건너뛰기' });
		expect(skipLink.getAttribute('href')).toBe('#landing-content');
		const content = container.querySelector<HTMLElement>('#landing-content');
		expect(content?.getAttribute('tabindex')).toBe('-1');
		expect(content?.tagName).toBe('DIV');
		expect(container.querySelector('main')).toBeNull();
		expect(container.querySelector('header')).toBeTruthy();
		const pageFooter = container.querySelector<HTMLElement>('.landing-page > footer');
		expect(pageFooter).toBeTruthy();
		expect(content?.contains(pageFooter)).toBe(false);
		await fireEvent.click(skipLink);
		expect(document.activeElement).toBe(content);

		const brand = container.querySelector<HTMLAnchorElement>('a.brand');
		expect(brand?.getAttribute('href')).toBe('/');
		expect(brand?.querySelector('img')?.getAttribute('alt')).toBe('');
		expect(brand?.querySelector('img')?.getAttribute('src')).toBe('/brand.svg');
		expect(brand?.textContent).toContain('Test Cloud');
		expect(container.querySelector('.footer-brand')?.textContent).toContain('Test Cloud');

		const nav = screen.getByRole('navigation', { name: '주요 내비게이션' });
		const navLinks = Array.from(nav.querySelectorAll<HTMLAnchorElement>('.nav-links a'));
		expect(navLinks.map((link) => link.getAttribute('href'))).toEqual([
			'#overview', '#capabilities', '#workflow', '#work', '#contact',
		]);
		expect(screen.getAllByRole('link', { name: '콘솔 접속' })).toHaveLength(3);
		expect(screen.getAllByRole('link', { name: '콘솔 접속' }).every((link) => link.getAttribute('href') === '/login')).toBe(true);
		expect(screen.getByRole('link', { name: '기능 보기' }).getAttribute('href')).toBe('#capabilities');

		const sectionOrder = Array.from(container.querySelectorAll('#landing-content > section')).map(
			(section) => section.id || (section.classList.contains('hero') ? 'hero' : 'section'),
		);
		expect(sectionOrder).toEqual(['hero', 'overview', 'capabilities', 'workflow', 'section', 'work', 'section', 'contact']);
		expect(container.querySelectorAll('.roman, .collage')).toHaveLength(0);
	});

	it('uses the supplied dashboard destination for every console action', () => {
		renderLanding('/dashboard');
		expect(screen.getAllByRole('link', { name: '콘솔 접속' }).every((link) => link.getAttribute('href') === '/dashboard')).toBe(true);
	});

	it('keeps all workflow rows mounted in one list while filtering and updates pressed state', async () => {
		const { container } = renderLanding();
		const cards = workflowCards(container);
		expect(cards).toHaveLength(5);
		expect(mutedWorkflowCount(container)).toBe(0);
		expect(container.querySelectorAll('.workflow-list')).toHaveLength(1);
		expect(container.querySelector('#workflow-progress')).toBeNull();
		expect(Array.from(container.querySelectorAll('.lab-card h3')).map((heading) => heading.textContent?.trim())).toEqual([
			'컴퓨팅 자원 신청',
			'공유 데이터 공간',
			'클러스터 실습',
			'관측 가능한 운영',
			'보안과 감사',
		]);

		const filterGroup = screen.getByRole('group', { name: '워크플로우 필터' });
		const chooseFilter = async (label: string, muted: number) => {
			await fireEvent.click(screen.getByRole('button', { name: label }));
			expect(workflowCards(container)).toHaveLength(5);
			expect(mutedWorkflowCount(container)).toBe(muted);
			expect(filterGroup.querySelector(`[aria-pressed="true"]`)?.textContent?.trim()).toBe(label);
		};

		await chooseFilter('컴퓨팅', 3);
		await chooseFilter('데이터', 4);
		await chooseFilter('운영', 3);
		await chooseFilter('전체', 0);
	});

	it('updates the scrollspy from overview through contact with one active location', async () => {
		const sectionTops = {
			overview: 80,
			capabilities: 320,
			workflow: 560,
			work: 800,
			contact: 1040,
		};
		mockSectionTops(sectionTops);
		const { container } = renderLanding();
		const nav = screen.getByRole('navigation', { name: '주요 내비게이션' });
		const activeLinks = () =>
			Array.from(nav.querySelectorAll<HTMLAnchorElement>('.nav-links a')).filter(
				(link) => link.getAttribute('aria-current') === 'location',
			);

		expect(activeLinks().map((link) => link.getAttribute('href'))).toEqual(['#overview']);

		for (const state of [
			{
				href: '#capabilities',
				tops: { overview: -300, capabilities: 80, workflow: 320, work: 560, contact: 800 },
			},
			{
				href: '#workflow',
				tops: { overview: -560, capabilities: -320, workflow: 80, work: 320, contact: 560 },
			},
			{
				href: '#work',
				tops: { overview: -800, capabilities: -560, workflow: -320, work: 80, contact: 320 },
			},
			{
				href: '#contact',
				tops: { overview: -1040, capabilities: -800, workflow: -560, work: -320, contact: 80 },
			},
		]) {
			Object.assign(sectionTops, state.tops);
			await fireEvent.scroll(window);
			const current = activeLinks();
			expect(current).toHaveLength(1);
			expect(current[0]?.getAttribute('href')).toBe(state.href);
			expect(current[0]?.getAttribute('aria-current')).toBe('location');
		}

		expect(container.querySelectorAll('.nav-links a[aria-current="location"]')).toHaveLength(1);
	});

	it('does not render retired issue, GitHub status, clipboard, or fallback surfaces', () => {
		const fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);
		const { container } = renderLanding();

		expect(fetchMock).not.toHaveBeenCalled();
		expect(container.querySelector('.issue-row')).toBeNull();
		expect(container.querySelector('.mailto-fallback')).toBeNull();
		expect(container.querySelector('#copy-feedback')).toBeNull();
		expect(screen.queryByRole('button', { name: '이메일 주소 복사' })).toBeNull();
		expect(screen.queryByRole('status')).toBeNull();
		expect(container.innerHTML).not.toContain('api.github.com');

		const inquiry = screen.getByRole('link', { name: '이메일 문의 보내기' });
		expect(inquiry.getAttribute('href')).toBe(`mailto:${email}`);
			expect(inquiry.textContent?.trim()).toBe(email);
	});

	it('keeps refined compute, Kubernetes, method-visual, and footer contracts', () => {
		const { container } = renderLanding();
		const computeCard = container.querySelector<HTMLElement>('.cap-card');
		const computeImage = computeCard?.querySelector<SVGElement>('svg.plate-graphic');
		expect(computeImage?.getAttribute('data-plate')).toBe('compute-allocation');

		const clusterCard = Array.from(container.querySelectorAll<HTMLElement>('.lab-card')).find(
			(card) => card.querySelector('h3')?.textContent?.trim() === '클러스터 실습',
		);
		expect(clusterCard).toBeTruthy();

		const dataCard = Array.from(container.querySelectorAll<HTMLElement>('.lab-card')).find(
			(card) => card.querySelector('h3')?.textContent?.trim() === '공유 데이터 공간',
		);
		const dataImage = dataCard?.querySelector<SVGElement>('svg.plate-graphic');
		expect(dataImage?.getAttribute('data-plate')).toBe('shared-data');
		expect(dataImage?.getAttribute('role')).toBe('img');

			const quoteImages = Array.from(container.querySelectorAll<SVGElement>('.quote-visual svg.plate-graphic'));
			expect(quoteImages.map((image) => image.getAttribute('data-plate'))).toEqual(['professor']);
			quoteImages.forEach((image) => {
				expect(image.getAttribute('role')).toBe('img');
			});

			const methodSteps = Array.from(container.querySelectorAll<HTMLElement>('.method-step'));
			expect(methodSteps).toHaveLength(4);
			expect(methodSteps.map((step) => step.querySelector('.method-meta b')?.textContent?.trim())).toEqual(['01', '02', '03', '04']);


			const footer = container.querySelector<HTMLElement>('.landing-page > footer');
		const footerColumns = Array.from(footer?.querySelectorAll<HTMLElement>('.footer-grid > div') ?? []);
		expect(footerColumns).toHaveLength(2);
		expect(footer?.querySelector(`a[href="mailto:${email}"]`)).toBeTruthy();
		expect(footer?.querySelector('a[href="https://github.com/openstack-afterglow/openstack-afterglow"]')).toBeTruthy();
	});

	it('uses only theme-aware inline artwork for the product-proof image slots', () => {
		const { container } = renderLanding();
			const proofImages = Array.from(container.querySelectorAll<SVGElement>('.overview-screen svg.plate-graphic, #work svg.plate-graphic'));
		expect(proofImages.map((image) => image.getAttribute('data-plate'))).toEqual([
			'console',
			'kubernetes',
			'security',
			'network-topology',
		]);
		expect(new Set(proofImages.map((image) => image.getAttribute('data-plate'))).size).toBe(4);
		expect(proofImages.every((image) => image.tagName.toLowerCase() === 'svg')).toBe(true);
		// No raster artwork anywhere: the only <img> is the brand logo (an SVG asset).
		expect(
			Array.from(container.querySelectorAll<HTMLImageElement>('img')).some((image) =>
				/\.(png|jpe?g|webp|gif)$/.test(image.getAttribute('src') ?? ''),
			),
		).toBe(false);
	});
	it('leaves reveal content visible without an observer and restores scroll behavior on cleanup', () => {
		document.documentElement.style.scrollBehavior = 'instant';
		const { container, unmount } = renderLanding();
		const root = landingRoot(container);
		expect(root.classList.contains('reveal-enabled')).toBe(false);
		const revealItems = container.querySelectorAll<HTMLElement>('[data-reveal]');
		expect(revealItems.length).toBeGreaterThan(0);
		revealItems.forEach((item) => {
			expect(item.classList.contains('is-visible')).toBe(false);
		});
		expect(document.documentElement.style.scrollBehavior).toBe('smooth');
		unmount();
		expect(document.documentElement.style.scrollBehavior).toBe('instant');
	});

	it('uses IntersectionObserver for motion reveals and disconnects it on unmount', () => {
		setMatchMedia(false);
		vi.stubGlobal('IntersectionObserver', TestIntersectionObserver);
		Object.defineProperty(window, 'IntersectionObserver', {
			configurable: true,
			writable: true,
			value: TestIntersectionObserver,
		});
		document.documentElement.style.scrollBehavior = 'auto';
		const { container, unmount } = renderLanding();
		const root = landingRoot(container);
		expect(root.classList.contains('reveal-enabled')).toBe(true);
		expect(document.documentElement.style.scrollBehavior).toBe('smooth');
		const observer = TestIntersectionObserver.instances[0];
		expect(observer).toBeTruthy();
		expect(observer.options).toMatchObject({ threshold: 0.18, rootMargin: '0px 0px -8% 0px' });
		expect(observer.observed.length).toBeGreaterThan(0);
		const target = observer.observed[0];
		observer.trigger(target);
		expect(target.classList.contains('is-visible')).toBe(true);
		expect(observer.unobserve).toHaveBeenCalledWith(target);

		unmount();
		expect(observer.disconnect).toHaveBeenCalledTimes(1);
		expect(root.classList.contains('reveal-enabled')).toBe(false);
		expect(document.documentElement.style.scrollBehavior).toBe('auto');
	});

	it('uses automatic scrolling for reduced motion and tolerates unavailable matchMedia or observer APIs', () => {
		setMatchMedia(true);
		vi.stubGlobal('IntersectionObserver', TestIntersectionObserver);
		Object.defineProperty(window, 'IntersectionObserver', {
			configurable: true,
			writable: true,
			value: TestIntersectionObserver,
		});
		const reduced = renderLanding();
		expect(document.documentElement.style.scrollBehavior).toBe('auto');
		expect(TestIntersectionObserver.instances).toHaveLength(0);
		reduced.unmount();
		Reflect.deleteProperty(window, 'IntersectionObserver');
		Reflect.deleteProperty(globalThis, 'IntersectionObserver');

		Reflect.deleteProperty(window, 'matchMedia');
		document.documentElement.style.scrollBehavior = 'instant';
		const withoutMatchMedia = renderLanding();
		expect(document.documentElement.style.scrollBehavior).toBe('smooth');
		expect(landingRoot(withoutMatchMedia.container).classList.contains('reveal-enabled')).toBe(false);
		withoutMatchMedia.unmount();

		Object.defineProperty(window, 'IntersectionObserver', {
			configurable: true,
			writable: true,
			value: undefined,
		});
		const withoutObserver = renderLanding();
		const root = landingRoot(withoutObserver.container);
		expect(root.classList.contains('reveal-enabled')).toBe(false);
		expect(root.querySelectorAll('[data-reveal]').length).toBeGreaterThan(0);
		withoutObserver.unmount();
		expect(document.documentElement.style.scrollBehavior).toBe('instant');
	});


	it('renders all artwork slots as theme-aware inline plate graphics', () => {
		const { container } = renderLanding();
			expect(container.querySelector('.hero-board .ops-board')).toBeTruthy();
			expect(container.querySelector('.hero-board svg.plate-graphic')).toBeNull();

			const overviewGraphic = container.querySelector<SVGElement>('#overview figure svg.plate-graphic');
			expect(overviewGraphic?.getAttribute('role')).toBe('img');
			expect(overviewGraphic?.getAttribute('data-plate')).toBe('console');
		const workflowGraphic = container.querySelector<SVGElement>('.lab-card svg.plate-graphic');
		expect(workflowGraphic?.getAttribute('data-plate')).toBeTruthy();
	});
});
