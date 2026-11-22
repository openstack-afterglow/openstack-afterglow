import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { classifyRouteScene, runRouteScene, type RouteSceneNavigation } from '../routeScene';

function navigation(from: string, to: string, overrides: Partial<RouteSceneNavigation> = {}): RouteSceneNavigation {
	return {
		from: { url: new URL(from, 'https://cloud.example') },
		to: { url: new URL(to, 'https://cloud.example') },
		willUnload: false,
		complete: Promise.resolve(),
		...overrides,
	};
}

function stubTransition() {
	const updates: Array<() => Promise<void>> = [];
	const start = vi.fn((update: () => Promise<void>) => {
		updates.push(update);
		const done = Promise.resolve().then(() => update());
		return { ready: done, updateCallbackDone: done, finished: done };
	});
	(document as unknown as { startViewTransition?: unknown }).startViewTransition = start;
	return { start, updates };
}

function setReducedMotion(matches: boolean) {
	window.matchMedia = ((query: string) => ({
		media: query, matches, onchange: null,
		addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
	})) as typeof window.matchMedia;
}

describe('classifyRouteScene', () => {
	it('names only the landing ↔ login pair', () => {
		expect(classifyRouteScene('/', '/login')).toBe('auth-enter');
		expect(classifyRouteScene('/login', '/')).toBe('auth-leave');
		expect(classifyRouteScene('/login', '/dashboard')).toBeNull();
		expect(classifyRouteScene('/', '/docs')).toBeNull();
		expect(classifyRouteScene('/', '/')).toBeNull();
		expect(classifyRouteScene(undefined, '/login')).toBeNull();
	});
});

describe('runRouteScene', () => {
	const originalMatchMedia = window.matchMedia;
	beforeEach(() => {
		setReducedMotion(false);
		document.body.innerHTML = '<section data-route-scene-part="art"></section>';
		const art = document.querySelector('section')!;
		art.getBoundingClientRect = () => ({ top: 64, bottom: 700, left: 0, right: 1200, width: 1200, height: 636, x: 0, y: 64, toJSON() {} });
	});
	afterEach(() => {
		delete (document as unknown as { startViewTransition?: unknown }).startViewTransition;
		delete document.documentElement.dataset.routeScene;
		delete document.documentElement.dataset.routeSceneArt;
		window.matchMedia = originalMatchMedia;
		document.body.innerHTML = '';
	});

	it('leaves unrelated navigations, unloads and unsupported browsers untouched', () => {
		expect(runRouteScene(navigation('/', '/login'))).toBeUndefined();
		const { start } = stubTransition();
		expect(runRouteScene(navigation('/login', '/dashboard'))).toBeUndefined();
		expect(runRouteScene(navigation('/', '/login', { willUnload: true }))).toBeUndefined();
		expect(start).not.toHaveBeenCalled();
		expect(document.documentElement.dataset.routeScene).toBeUndefined();
	});

	it('never starts a scene under reduced motion', () => {
		setReducedMotion(true);
		const { start } = stubTransition();
		expect(runRouteScene(navigation('/', '/login'))).toBeUndefined();
		expect(start).not.toHaveBeenCalled();
	});

	it('marks the scene for its lifetime and lets navigation continue inside the update callback', async () => {
		let finishNavigation!: () => void;
		const complete = new Promise<void>((resolve) => { finishNavigation = resolve; });
		const { start } = stubTransition();
		const pending = runRouteScene(navigation('/', '/login', { complete }));
		expect(pending).toBeInstanceOf(Promise);
		expect(document.documentElement.dataset.routeScene).toBe('auth-enter');
		expect(document.documentElement.dataset.routeSceneArt).toBeUndefined();
		await pending;
		expect(start).toHaveBeenCalledOnce();
		expect(document.documentElement.dataset.routeScene).toBe('auth-enter');
		finishNavigation();
		await vi.waitFor(() => expect(document.documentElement.dataset.routeScene).toBeUndefined());
	});

	it('detaches the art morph when the hero is scrolled away', async () => {
		const art = document.querySelector('section')!;
		art.getBoundingClientRect = () => ({ top: -2400, bottom: -1800, left: 0, right: 1200, width: 1200, height: 600, x: 0, y: -2400, toJSON() {} });
		let finishNavigation!: () => void;
		const complete = new Promise<void>((resolve) => { finishNavigation = resolve; });
		stubTransition();
		await runRouteScene(navigation('/', '/login', { complete }));
		expect(document.documentElement.dataset.routeSceneArt).toBe('detached');
		finishNavigation();
		await vi.waitFor(() => expect(document.documentElement.dataset.routeSceneArt).toBeUndefined());
	});

	it('survives a cancelled navigation without unhandled rejections', async () => {
		stubTransition();
		const complete = Promise.reject(new Error('cancelled'));
		await runRouteScene(navigation('/login', '/', { complete }));
		await vi.waitFor(() => expect(document.documentElement.dataset.routeScene).toBeUndefined());
	});
});
