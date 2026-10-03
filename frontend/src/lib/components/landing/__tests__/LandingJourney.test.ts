import { act, cleanup, fireEvent, render, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';
import LandingJourney from '../LandingJourney.svelte';

type Query = EventTarget & { matches: boolean };

let roomy: Query;
let reduced: Query;
let frames: FrameRequestCallback[];
let tops: number[];

async function flushFrames() {
	await act(async () => {
		const pending = frames;
		frames = [];
		for (const callback of pending) callback(0);
		await tick();
	});
}

async function scrollPage() {
	window.dispatchEvent(new Event('scroll'));
	await flushFrames();
}

async function setMedia(target: Query, matches: boolean) {
	await act(async () => {
		target.matches = matches;
		target.dispatchEvent(new Event('change'));
		await tick();
	});
}

function setup() {
	const { container } = render(LandingJourney);
	const root = container.querySelector<HTMLElement>('[data-stage]')!;
	const articles = Array.from(root.querySelectorAll<HTMLElement>('article'));
	articles.forEach((article, index) => {
		vi.spyOn(article, 'getBoundingClientRect').mockImplementation(() => ({ top: tops[index] }) as DOMRect);
	});
	const buttons = within(within(root).getByRole('group')).getAllByRole('button');
	return { root, articles, buttons };
}

function activeArticles(articles: HTMLElement[]) {
	return articles.flatMap((article, index) => (article.dataset.active === 'true' ? [index] : []));
}

// The activation line sits at 32% of jsdom's 768px viewport (no nav offset): about 246px.
const geometryAt = (stage: number) => [0, 1, 2, 3].map((index) => (index <= stage ? 100 - (stage - index) * 400 : 400 + index * 400));

beforeEach(() => {
	roomy = Object.assign(new EventTarget(), { matches: false });
	reduced = Object.assign(new EventTarget(), { matches: false });
	frames = [];
	tops = geometryAt(0);
	vi.stubGlobal('matchMedia', vi.fn((media: string) => (media === REDUCED_MOTION_QUERY ? reduced : roomy)));
	vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => frames.push(callback)));
	vi.stubGlobal('cancelAnimationFrame', vi.fn());
	vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
});

afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

describe('LandingJourney', () => {
	it('moves the scene, caption, pressed button and article together when a stage is chosen', async () => {
		const { root, articles, buttons } = setup();
		const caption = root.querySelector('figcaption p')!;

		for (const stage of [2, 3, 0, 1]) {
			await fireEvent.click(buttons[stage]);
			expect(buttons.map((button) => button.getAttribute('aria-pressed'))).toEqual(buttons.map((_, index) => String(index === stage)));
			expect(root.dataset.stage).toBe(String(stage));
			expect(activeArticles(articles)).toEqual([stage]);
			expect(caption.textContent?.startsWith(buttons[stage].textContent!.trim())).toBe(true);
		}
	});

	it('follows the reading position on roomy viewports and keeps a chosen stage until the reader scrolls again', async () => {
		roomy.matches = true;
		const { root, articles, buttons } = setup();
		await flushFrames();
		expect(root.classList.contains('motion-enabled')).toBe(true);
		expect(root.dataset.stage).toBe('0');

		tops = geometryAt(2);
		await scrollPage();
		expect(root.dataset.stage).toBe('2');
		expect(activeArticles(articles)).toEqual([2]);

		await fireEvent.click(buttons[0]);
		tops = geometryAt(3);
		await scrollPage();
		expect(root.dataset.stage).toBe('0');

		window.dispatchEvent(new Event('wheel'));
		await scrollPage();
		expect(root.dataset.stage).toBe('3');
		expect(activeArticles(articles)).toEqual([3]);
	});

	it.each([
		['compact', false, false],
		['reduced motion', true, true]
	])('changes only through the buttons in the %s layout', async (_name, isRoomy, isReduced) => {
		roomy.matches = isRoomy;
		reduced.matches = isReduced;
		const { root, buttons } = setup();
		await flushFrames();
		expect(root.classList.contains('motion-enabled')).toBe(false);

		tops = geometryAt(3);
		await scrollPage();
		expect(root.dataset.stage).toBe('0');

		await fireEvent.click(buttons[2]);
		expect(root.dataset.stage).toBe('2');
	});

	it('reconfigures geometry-driven selection when media preferences change', async () => {
		roomy.matches = true;
		const { root } = setup();
		await flushFrames();

		await setMedia(reduced, true);
		expect(root.classList.contains('motion-enabled')).toBe(false);
		tops = geometryAt(2);
		await scrollPage();
		expect(root.dataset.stage).toBe('0');

		await setMedia(reduced, false);
		await flushFrames();
		expect(root.classList.contains('motion-enabled')).toBe(true);
		expect(root.dataset.stage).toBe('2');

		await setMedia(roomy, false);
		expect(root.classList.contains('motion-enabled')).toBe(false);
		tops = geometryAt(3);
		await scrollPage();
		expect(root.dataset.stage).toBe('2');

		await setMedia(roomy, true);
		await flushFrames();
		expect(root.classList.contains('motion-enabled')).toBe(true);
		expect(root.dataset.stage).toBe('3');
	});
});
