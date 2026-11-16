import { cubicOut } from 'svelte/easing';
import type { AnimationConfig } from 'svelte/animate';
import type { TransitionConfig } from 'svelte/transition';
import { MOTION_DURATION_MS, MOTION_EASING } from '$lib/design/tokens';
import { canAnimate, reflow } from './motion';

/**
 * Motion for keyed list rows that refresh in place.
 *
 * A refresh must only show what changed: a row that appears fades in, a row that disappears fades out,
 * siblings slide to their new place and a row whose displayed data changed flashes once. Unchanged rows
 * are never touched, and the whole list is never replaced by a loader. Each helper is a no-op under
 * reduced motion and in runtimes without Web Animations.
 *
 * Usage on the immediate child of a keyed `{#each}`:
 *   <tr in:rowEnter out:rowExit use:rowChanged={row}>
 *   <div class="grid ..." in:rowEnter out:rowExit animate:rowReflow use:rowChanged={row}>
 *
 * Never put `animate:` on a `<tr>`: Svelte pins every outgoing animated row with `position: absolute`, which
 * takes a table row out of table layout so its cells collapse to content width during the fade. Rows that are
 * `display: grid` blocks keep their width and may use `animate:rowReflow` for the sibling slide.
 */
/**
 * A refresh changes a handful of rows; a page turn, filter or scope switch replaces them all. Animating the
 * latter keeps every outgoing row in the DOM beside the incoming ones, so the table would briefly double in
 * height. Svelte runs a deferred transition (a function returned by the transition) in a microtask after every
 * row of the same update has registered, so the registered count is the size of the batch by then. A batch
 * larger than this plays no row motion.
 */
export const ROW_MOTION_BATCH_LIMIT = 6;

const registered = { enter: 0, exit: 0 };
let resetScheduled = false;

function register(kind: 'enter' | 'exit'): () => boolean {
	registered[kind] += 1;
	if (!resetScheduled) {
		resetScheduled = true;
		// A macrotask: strictly after Svelte's microtask that evaluates this batch's deferred transitions.
		setTimeout(() => {
			registered.enter = 0;
			registered.exit = 0;
			resetScheduled = false;
		}, 0);
	}
	return () => registered[kind] <= ROW_MOTION_BATCH_LIMIT;
}

/** Row that appears after the list was first rendered. Svelte transitions are local, so the first paint never animates. */
export function rowEnter(node: Element): () => TransitionConfig {
	const withinBatch = register('enter');
	return () => {
		if (!canAnimate(node) || !withinBatch()) return { duration: 0 };
		return {
			duration: MOTION_DURATION_MS.panel,
			easing: cubicOut,
			css: (t, u) => `opacity: ${t}; transform: translateY(${-6 * u}px);`,
		};
	};
}

/** Row that is removed from the list; the node stays until the fade completes. */
export function rowExit(node: Element): () => TransitionConfig {
	const withinBatch = register('exit');
	return () => {
		if (!canAnimate(node) || !withinBatch()) return { duration: 0 };
		return {
			duration: MOTION_DURATION_MS.base,
			easing: cubicOut,
			css: (t, u) => `opacity: ${t}; transform: translateX(${8 * u}px);`,
		};
	};
}
/** Siblings slide into the gap left by an added or removed row. */
export function rowReflow(node: Element, rects: { from: DOMRect; to: DOMRect }): AnimationConfig {
	return reflow(node, rects, { duration: MOTION_DURATION_MS.panel });
}

/** Stable signature of what a row displays; objects are compared by value, not identity. */
export function rowSignature(value: unknown): string {
	try {
		return JSON.stringify(value) ?? '';
	} catch {
		return String(value);
	}
}

/**
 * Flashes the row once when its data changes after the first render. The first value only records the baseline,
 * so initial paint, filtering and pagination never flash. A refresh that returns an equal row leaves it still.
 */
export function rowChanged(node: HTMLElement, value: unknown) {
	let signature = rowSignature(value);
	return {
		update(next: unknown) {
			const nextSignature = rowSignature(next);
			if (nextSignature === signature) return;
			signature = nextSignature;
			if (!canAnimate(node)) return;
			node.animate(
				[
					{ backgroundColor: 'var(--color-surface-selected)' },
					{ backgroundColor: 'var(--color-surface-selected)', offset: 0.35 },
					{ backgroundColor: 'transparent' },
				],
				{ duration: MOTION_DURATION_MS.data * 2, easing: MOTION_EASING.emphasized },
			);
		},
	};
}
