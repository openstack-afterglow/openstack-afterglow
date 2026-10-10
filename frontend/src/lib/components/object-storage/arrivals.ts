import { MOTION_STAGGER_LIMIT } from '$lib/design/tokens';

/**
 * First-arrival bookkeeping for keyed bucket/object lists.
 *
 * `next(key)` returns the cascade slot (`--motion-index`) for a key that has never rendered in
 * this list and `null` afterwards, so auto-refresh, loading swaps and filter typing that remount
 * the same keys never replay the entrance. Keys first rendered in the same flush share one
 * cascade capped at `MOTION_STAGGER_LIMIT`; a later single arrival enters without delay.
 */
export function createArrivals() {
	const seen = new Set<string>();
	let batch = 0;

	return {
		next(key: string): number | null {
			if (seen.has(key)) return null;
			seen.add(key);
			if (batch === 0) queueMicrotask(() => { batch = 0; });
			return Math.min(batch++, MOTION_STAGGER_LIMIT);
		},
		/** Forget every key, e.g. when the list starts showing a different container. */
		reset() {
			seen.clear();
			batch = 0;
		},
	};
}
