import { flip } from 'svelte/animate';
import { backOut, cubicOut } from 'svelte/easing';
import type { AnimationConfig } from 'svelte/animate';
import type { TransitionConfig } from 'svelte/transition';
import { MOTION_DURATION_MS, MOTION_STAGGER_LIMIT, REDUCED_MOTION_QUERY } from '$lib/design/tokens';

/** Returns false during SSR and in runtimes without media-query support. */
export function prefersReducedMotion(): boolean {
	return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
		? window.matchMedia(REDUCED_MOTION_QUERY).matches
		: false;
}

/** Returns an immediate Svelte/Web Animation duration when reduced motion is requested. */
export function motionDuration(durationMs: number): number {
	return prefersReducedMotion() ? 0 : durationMs;
}

/**
 * Whether a Web Animation may run on `node`: reduced motion opts out, and runtimes without
 * `Element.animate` (SSR, jsdom) skip instead of throwing. Svelte transitions run on Web Animations,
 * so every transition helper below gates on this.
 */
export function canAnimate(node?: Element | null): boolean {
	if (prefersReducedMotion()) return false;
	const target = node ?? (typeof document === 'undefined' ? null : document.documentElement);
	return target !== null && typeof (target as HTMLElement).animate === 'function';
}

/** Delay for the item at `index` in a cascade; capped so long lists never wait more than a beat. */
export function staggerDelay(index: number, step: number = MOTION_DURATION_MS.stagger): number {
	if (prefersReducedMotion() || !Number.isFinite(index)) return 0;
	return Math.min(Math.max(0, Math.floor(index)), MOTION_STAGGER_LIMIT) * step;
}

export interface EnterParams {
	delay?: number;
	duration?: number;
	/** Start offset in px; positive x enters from the right, positive y from below. */
	x?: number;
	y?: number;
}

/** Fade + translate transition. It replaces the node's own transform while it runs. */
export function enter(
	node: Element,
	{ delay = 0, duration = MOTION_DURATION_MS.panel, x = 0, y = 6 }: EnterParams = {},
): TransitionConfig {
	if (!canAnimate(node)) return { duration: 0 };
	return {
		delay,
		duration,
		easing: cubicOut,
		css: (t, u) => `opacity: ${t}; transform: translate(${u * x}px, ${u * y}px);`,
	};
}

export interface PopParams {
	delay?: number;
	duration?: number;
	/** Scale the node starts from. */
	start?: number;
}

/** Fade + scale transition with a slight overshoot, for things that appear in place. */
export function pop(
	node: Element,
	{ delay = 0, duration = MOTION_DURATION_MS.panel, start = 0.94 }: PopParams = {},
): TransitionConfig {
	if (!canAnimate(node)) return { duration: 0 };
	return {
		delay,
		duration,
		easing: backOut,
		css: (t) => `opacity: ${Math.min(1, t)}; transform: scale(${start + (1 - start) * t});`,
	};
}

/** Opacity-only transition; safe on nodes whose transform carries layout (positioned cards). */
export function fadeMotion(
	node: Element,
	{ delay = 0, duration = MOTION_DURATION_MS.base }: { delay?: number; duration?: number } = {},
): TransitionConfig {
	if (!canAnimate(node)) return { duration: 0 };
	return { delay, duration, easing: cubicOut, css: (t) => `opacity: ${t};` };
}

/** `animate:` helper that slides keyed siblings into their new place after an insert or removal. */
export function reflow(
	node: Element,
	rects: { from: DOMRect; to: DOMRect },
	params: { delay?: number; duration?: number } = {},
): AnimationConfig {
	if (!canAnimate(node)) return { duration: 0 };
	return flip(node, rects, { duration: MOTION_DURATION_MS.panel, easing: cubicOut, ...params });
}

/**
 * Route content entrance: an opacity-only fade of every top-level child of the route container.
 * Opacity keeps fixed descendants (deep-linked panels, dialogs) on the viewport containing block,
 * which a transform would capture for the duration of the entrance.
 */
export function playRouteEntrance(root: HTMLElement | null): void {
	if (!root || !canAnimate(root)) return;
	for (const child of Array.from(root.children)) {
		if (typeof (child as HTMLElement).animate !== 'function') continue;
		(child as HTMLElement).animate([{ opacity: 0 }, { opacity: 1 }], {
			duration: MOTION_DURATION_MS.panel,
			easing: 'ease-out',
		});
	}
}

/** True for client navigations that changed the route path; hydration and query-only updates do not animate. */
export function isRouteChange(
	navigation: { type: string; from: { url: URL } | null; to: { url: URL } | null },
): boolean {
	if (navigation.type === 'enter' || !navigation.from || !navigation.to) return false;
	return navigation.from.url.pathname !== navigation.to.url.pathname;
}
