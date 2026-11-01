/**
 * Shared step clock for the character-interface loading family (output/afterglow-loading/progress.js).
 * One 140ms interval serves every mounted indicator; it stops with no subscribers, while the
 * document is hidden, and under reduced motion (indicators then show their static frame).
 */
import { readable } from 'svelte/store';
import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';

// Starts on a frame whose flow segment is visible, so a frozen (reduced-motion/hidden) bar never reads as empty.
const FIRST_VISIBLE_STEP = 14;

export const characterStep = readable(FIRST_VISIBLE_STEP, set => {
	if (typeof window === 'undefined') return;
	const reduce = matchMedia(REDUCED_MOTION_QUERY);
	let step = FIRST_VISIBLE_STEP, timer = 0;
	const sync = () => {
		clearInterval(timer); timer = 0;
		if (!document.hidden && !reduce.matches) timer = window.setInterval(() => set(++step), 140);
	};
	reduce.addEventListener('change', sync);
	document.addEventListener('visibilitychange', sync);
	sync();
	return () => {
		clearInterval(timer);
		reduce.removeEventListener('change', sync);
		document.removeEventListener('visibilitychange', sync);
	};
});

/** `[···###:··]` — an indeterminate flow bar that never implies a percentage. */
export function flowBar(step: number, size = 32): string {
	const start = step % (size + 9) - 9;
	let bar = '[';
	for (let i = 0; i < size; i++) bar += i >= start && i < start + 8 ? '#' : i >= start - 3 && i < start ? ':' : '·';
	return bar + ']';
}

/** `[####······]` — a determinate character bar for an observed 0–100 value. */
export function characterBar(percent: number, cells = 26): string {
	const filled = Math.round(Math.max(0, Math.min(100, percent)) / 100 * cells);
	return '[' + '#'.repeat(filled) + '·'.repeat(cells - filled) + ']';
}

/** One skeleton table cell: `··::··` drifting by row/column offset. */
export function skeletonCell(step: number, offset: number): string {
	let cell = '';
	for (let j = 0; j < 10; j++) { const k = (j + offset + step) % 9; cell += k < 3 ? ':' : k < 5 ? '·' : ' '; }
	return cell;
}
