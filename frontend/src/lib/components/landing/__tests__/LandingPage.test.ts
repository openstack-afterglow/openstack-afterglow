import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import LandingPage from '../LandingPage.svelte';

class TestIntersectionObserver {
	static instances: TestIntersectionObserver[] = [];
	readonly observed: Element[] = [];
	readonly disconnect = vi.fn();
	constructor(readonly callback: IntersectionObserverCallback, readonly options?: IntersectionObserverInit) { TestIntersectionObserver.instances.push(this); }
	observe(target: Element) { this.observed.push(target); }
	unobserve() {}
	takeRecords() { return []; }
	trigger(target: Element, isIntersecting = true) {
		this.callback([{ target, isIntersecting, intersectionRatio: isIntersecting ? 1 : 0 } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
	}
}

function renderLanding() {
	return render(LandingPage, { siteName: 'Test Cloud', logoPath: '/brand.svg', consoleHref: '/select-project' });
}

beforeEach(() => {
	TestIntersectionObserver.instances = [];
	vi.stubGlobal('IntersectionObserver', TestIntersectionObserver);
	vi.stubGlobal('ResizeObserver', undefined);
	vi.stubGlobal('matchMedia', vi.fn((media: string) => ({ matches: false, media, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('LandingPage navigation', () => {
	it('moves keyboard focus into the content from the skip link', async () => {
		const { container } = renderLanding();
		await fireEvent.click(container.querySelector('.skip-link')!);
		expect(document.activeElement).toBe(container.querySelector('#landing-content'));
	});

	it('tracks the visible service while GPU remains part of server navigation', async () => {
		const tops: Record<string, number> = { overview: 72, capabilities: 400, gpu: 800, workflow: 1200, work: 1600, contact: 2000 };
		vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
			const top = this.classList.contains('top-strip') ? 0 : tops[this.id] ?? 9999;
			const height = this.classList.contains('top-strip') ? 64 : 300;
			return { top, bottom: top + height, left: 0, right: 500, width: 500, height, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
		});
		const { container } = renderLanding();
		const observer = TestIntersectionObserver.instances.find((entry) => entry.observed.some((node) => node.id === 'capabilities'))!;
		const navigation = screen.getByRole('navigation');
		for (const [section, href] of [['capabilities', '#capabilities'], ['gpu', '#capabilities'], ['workflow', '#workflow'], ['work', '#work'], ['contact', '#contact']]) {
			const delta = 80 - tops[section];
			for (const id of Object.keys(tops)) tops[id] += delta;
			observer.trigger(container.querySelector(`#${section}`)!);
			await fireEvent.scroll(window);
			expect(Array.from(navigation.querySelectorAll('a[aria-current="location"]')).map((link) => link.getAttribute('href'))).toEqual([href]);
		}
	});
});
