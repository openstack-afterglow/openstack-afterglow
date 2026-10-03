import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import LandingPage from '../LandingPage.svelte';


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
	it('moves focus to the landing content from the skip link', async () => {
		const { container } = renderLanding();
		const skipLink = container.querySelector<HTMLAnchorElement>('.skip-link');
		const content = container.querySelector<HTMLElement>('#landing-content');
		expect(skipLink?.getAttribute('href')).toBe('#landing-content');
		expect(content).toBeTruthy();

		await fireEvent.click(skipLink!);
		expect(document.activeElement).toBe(content);
	});

	it.each(['/login', '/dashboard'])('links every console action to %s', (consoleHref) => {
		const { container } = renderLanding(consoleHref);
		for (const selector of ['a.nav-cta', '.hero-actions a.btn-primary', 'a.product-console', 'a.contact-console']) {
			const actions = container.querySelectorAll<HTMLAnchorElement>(selector);
			expect(actions, selector).toHaveLength(1);
			expect(actions[0]?.getAttribute('href'), selector).toBe(consoleHref);
		}
	});

	it('points the hero secondary action at capabilities and the scroll cue at the overview', () => {
		const { container } = renderLanding();
		expect(container.querySelector('.hero-actions a.btn-outline')?.getAttribute('href')).toBe('#capabilities');
		expect(container.querySelector('.hero-bottom a')?.getAttribute('href')).toBe('#overview');
		expect(container.querySelector('#capabilities')).toBeTruthy();
		expect(container.querySelector('#overview')).toBeTruthy();
	});

	it('renders the runtime brand in the navigation and footer', () => {
		const { container } = renderLanding();
		const brand = container.querySelector<HTMLAnchorElement>('a.brand');
		expect(brand?.getAttribute('href')).toBe('/');
		const brandLogo = brand?.querySelector('img');
		expect(brandLogo?.getAttribute('src')).toBe('/brand.svg');
		expect(brandLogo?.getAttribute('alt')).toBe('');
		expect(brand?.textContent).toContain('Test Cloud');
		expect(container.querySelector('.footer-brand')?.textContent).toContain('Test Cloud');
	});

	it('offers the inquiry e-mail and repository links and renders no raster artwork', () => {
		const { container } = renderLanding();
		const footer = container.querySelector<HTMLElement>('footer');
		expect(footer?.querySelector('a[href^="mailto:"]')).toBeTruthy();
		expect(footer?.querySelector('a[href="https://github.com/openstack-afterglow/openstack-afterglow"]')).toBeTruthy();

		const images = Array.from(container.querySelectorAll('img'));
		expect(images.length).toBeGreaterThan(0);
		for (const image of images) {
			expect(image.getAttribute('src') ?? '').not.toMatch(/\.(png|jpe?g|webp|gif)([?#]|$)/i);
		}
	});

	it('selects the matching workflow filter from each capability card', async () => {
		const { container } = renderLanding();
		const filterButtons = Array.from(container.querySelectorAll<HTMLButtonElement>('.landing-workflow-filter button'));
		const capabilityLinks = Array.from(container.querySelectorAll<HTMLAnchorElement>('.cap-card .cap-explore'));
		const filterIndex = { compute: 1, data: 2, ops: 3 } as const;
		const expectedKinds = ['compute', 'compute', 'data', 'ops'] as const;
		expect(filterButtons).toHaveLength(4);
		expect(capabilityLinks).toHaveLength(expectedKinds.length);

		for (const [index, link] of capabilityLinks.entries()) {
			const kind = expectedKinds[index]!;
			await fireEvent.click(filterButtons[0]!);
			expect(mutedWorkflowCount(container)).toBe(0);

			expect(link.getAttribute('href')).toBe('#workflow');
			await fireEvent.click(link);
			const pressed = filterButtons.filter((button) => button.getAttribute('aria-pressed') === 'true');
			expect(pressed).toEqual([filterButtons[filterIndex[kind]]]);
			const nonMatching = workflowCards(container).filter((card) => card.dataset.kind !== kind).length;
			expect(nonMatching).toBeGreaterThan(0);
			expect(mutedWorkflowCount(container)).toBe(nonMatching);
		}
	});

	it('switches the product preview screen, route, and description together', async () => {
		const { container } = renderLanding();
		const preview = () => container.querySelector<HTMLElement>('.product-stage [data-view]');
		const route = () => container.querySelector('.product-stage .stage-bar b')?.textContent?.trim();
		const heading = () => container.querySelector('.product-description h3')?.textContent?.trim();
		const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>('.product-switcher button'));
		expect(buttons).toHaveLength(3);
		expect(preview()?.dataset.view).toBe('project');

		const seen = { routes: new Set([route()]), headings: new Set([heading()]) };
		for (const [index, view] of ['cluster', 'network', 'project'].entries()) {
			const button = buttons[(index + 1) % 3]!;
			const previousRoute = route();
			const previousHeading = heading();
			await fireEvent.click(button);
			expect(button.getAttribute('aria-pressed')).toBe('true');
			expect(preview()?.dataset.view).toBe(view);
			expect(container.querySelectorAll('.product-stage [data-view]')).toHaveLength(1);
			expect(route()).not.toBe(previousRoute);
			expect(heading()).not.toBe(previousHeading);
			seen.routes.add(route());
			seen.headings.add(heading());
		}
		expect(seen.routes.size).toBe(3);
		expect(seen.headings.size).toBe(3);
	});

	it('keeps all workflow rows mounted in one list while filtering and updates pressed state', async () => {
		const { container } = renderLanding();
		const cards = workflowCards(container);
		expect(cards).toHaveLength(5);
		expect(mutedWorkflowCount(container)).toBe(0);

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

		expect(activeLinks().map((link) => link.textContent?.trim())).toEqual(['개요']);

		for (const state of [
			{
				label: '제공 기능',
				tops: { overview: -300, capabilities: 80, workflow: 320, work: 560, contact: 800 },
			},
			{
				label: '워크플로우',
				tops: { overview: -560, capabilities: -320, workflow: 80, work: 320, contact: 560 },
			},
			{
				label: '화면',
				tops: { overview: -800, capabilities: -560, workflow: -320, work: 80, contact: 320 },
			},
			{
				label: '문의',
				tops: { overview: -1040, capabilities: -800, workflow: -560, work: -320, contact: 80 },
			},
		]) {
			Object.assign(sectionTops, state.tops);
			await fireEvent.scroll(window);
			const current = activeLinks();
			expect(current).toHaveLength(1);
			expect(current[0]?.textContent?.trim()).toBe(state.label);
			expect(current[0]?.getAttribute('aria-current')).toBe('location');
		}

		expect(container.querySelectorAll('.nav-links a[aria-current="location"]')).toHaveLength(1);
	});



	it('leaves reveal content visible without an observer and restores scroll behavior on cleanup', () => {
		document.documentElement.style.scrollBehavior = 'instant';
		const { container, unmount } = renderLanding();
		const root = landingRoot(container);
		expect(root.classList.contains('reveal-enabled')).toBe(false);
		const revealItems = container.querySelectorAll<HTMLElement>('[data-reveal]');
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
		withoutObserver.unmount();
		expect(document.documentElement.style.scrollBehavior).toBe('instant');
	});


});
