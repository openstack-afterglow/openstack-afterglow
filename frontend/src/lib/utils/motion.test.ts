import { afterEach, describe, expect, it, vi } from 'vitest';
import { MOTION_DURATION_MS, MOTION_STAGGER_LIMIT } from '$lib/design/tokens';
import {
	canAnimate,
	enter,
	fadeMotion,
	isRouteChange,
	motionDuration,
	playRouteEntrance,
	pop,
	prefersReducedMotion,
	staggerDelay,
} from './motion';

function reduceMotion(matches: boolean) {
	vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches }));
}

function animatable(): HTMLElement {
	const node = document.createElement('div');
	(node as HTMLElement & { animate: unknown }).animate = vi.fn();
	return node;
}

const originalMatchMedia = window.matchMedia;

afterEach(() => {
	vi.unstubAllGlobals();
	Object.defineProperty(window, 'matchMedia', { configurable: true, value: originalMatchMedia });
});

describe('motion preferences', () => {
	it('returns false when matchMedia is unavailable', () => {
		vi.stubGlobal('matchMedia', undefined);
		expect(prefersReducedMotion()).toBe(false);
	});

	it('returns false when reduced motion does not match', () => {
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
		expect(prefersReducedMotion()).toBe(false);
		expect(motionDuration(200)).toBe(200);
	});

	it('returns true and zero duration when reduced motion matches', () => {
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
		expect(prefersReducedMotion()).toBe(true);
		expect(motionDuration(200)).toBe(0);
	});
});

describe('stagger delay', () => {
	it('steps by the stagger token and stops growing at the cap', () => {
		reduceMotion(false);
		expect(staggerDelay(0)).toBe(0);
		expect(staggerDelay(3)).toBe(3 * MOTION_DURATION_MS.stagger);
		expect(staggerDelay(MOTION_STAGGER_LIMIT + 40)).toBe(MOTION_STAGGER_LIMIT * MOTION_DURATION_MS.stagger);
	});

	it('never delays invalid indexes or reduced-motion users', () => {
		reduceMotion(false);
		expect(staggerDelay(-2)).toBe(0);
		expect(staggerDelay(Number.NaN)).toBe(0);
		reduceMotion(true);
		expect(staggerDelay(5)).toBe(0);
	});
});

describe('transition helpers', () => {
	it('skip instead of calling Web Animations when the runtime lacks them', () => {
		reduceMotion(false);
		const bare = document.createElement('div');
		expect(canAnimate(bare)).toBe(false);
		for (const transition of [enter, pop, fadeMotion]) {
			expect(transition(bare).duration).toBe(0);
		}
	});

	it('are immediate for reduced-motion users even when animation is available', () => {
		reduceMotion(true);
		const node = animatable();
		expect(canAnimate(node)).toBe(false);
		expect(enter(node, { x: 24 }).duration).toBe(0);
		expect(pop(node).duration).toBe(0);
	});

	it('start hidden and offset, then settle visible in place', () => {
		reduceMotion(false);
		const config = enter(animatable(), { x: 24, y: 0 });
		expect(config.duration).toBe(MOTION_DURATION_MS.panel);
		expect(config.css?.(0, 1)).toBe('opacity: 0; transform: translate(24px, 0px);');
		expect(config.css?.(1, 0)).toBe('opacity: 1; transform: translate(0px, 0px);');
		expect(pop(animatable(), { start: 0.9 }).css?.(0, 1)).toBe('opacity: 0; transform: scale(0.9);');
	});
});

describe('route entrance', () => {
	it('fades each route child with opacity only so fixed descendants keep the viewport', () => {
		reduceMotion(false);
		const root = animatable();
		const first = animatable();
		const second = animatable();
		root.append(first, second);
		playRouteEntrance(root);
		for (const child of [first, second]) {
			const [keyframes] = vi.mocked(child.animate).mock.calls[0];
			expect(keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }]);
		}
	});

	it('does not animate for reduced-motion users', () => {
		reduceMotion(true);
		const root = animatable();
		const child = animatable();
		root.append(child);
		playRouteEntrance(root);
		expect(child.animate).not.toHaveBeenCalled();
	});

	it('animates only client navigations that change the path', () => {
		const at = (path: string) => ({ url: new URL(path, 'http://console.test') });
		expect(isRouteChange({ type: 'enter', from: null, to: at('/dashboard') })).toBe(false);
		expect(isRouteChange({ type: 'goto', from: at('/dashboard/volumes'), to: at('/dashboard/volumes?status=error') })).toBe(false);
		expect(isRouteChange({ type: 'link', from: at('/dashboard'), to: at('/dashboard/volumes') })).toBe(true);
	});
});
