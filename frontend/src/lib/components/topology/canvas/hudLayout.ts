import type { Pt, Rect } from './types';

export interface HudPlacementInput extends Rect { key: string; }
const GAP = 6;

/** Screen-space packing. World-space zone overlap is intentional for shared NICs,
 * so it cannot decide whether rendered text is safe. Keep every HUD item, reserve
 * resource/address cards, and search obstacle boundaries rather than pixel steps.
 */
export function placeHudItems(items: readonly HudPlacementInput[], obstacles: readonly Rect[], viewport?: Rect): Map<string, Rect> {
	const placed = new Map<string, Rect>();
	const occupied = [...obstacles];
	for (const item of items) {
		const nearest = (bounds?: Rect): Rect | null => {
			const minX = bounds?.x ?? -Infinity, maxX = bounds ? bounds.x + bounds.w - item.w : Infinity;
			const minY = bounds?.y ?? -Infinity, maxY = bounds ? bounds.y + bounds.h - item.h : Infinity;
			if (maxX < minX || maxY < minY) return null;
			const clampX = (x: number) => Math.max(minX, Math.min(maxX, x));
			const xs = new Set([clampX(item.x)]);
			for (const box of occupied) { xs.add(clampX(box.x - GAP - item.w)); xs.add(clampX(box.x + box.w + GAP)); }
			let best: Rect | null = null, distance = Infinity;
			for (const x of xs) {
				const dx = x - item.x;
				if (dx * dx > distance) continue;
				// These open intervals are the forbidden top positions for this x.
				const intervals = occupied.filter((b) => x < b.x + b.w + GAP && b.x - GAP < x + item.w)
					.map((b) => [b.y - GAP - item.h, b.y + b.h + GAP] as const).sort((a, b) => a[0] - b[0]);
				const merged: Array<[number, number]> = [];
				for (const [start, end] of intervals) {
					const last = merged[merged.length - 1];
					if (last && start < last[1]) last[1] = Math.max(last[1], end);
					else merged.push([start, end]);
				}
				const preferredY = Math.max(minY, Math.min(maxY, item.y));
				const blocked = merged.find(([start, end]) => start < preferredY && preferredY < end);
				const ys = blocked ? [blocked[0], blocked[1]] : [preferredY];
				for (const y of ys) {
					if (y < minY || y > maxY) continue;
					const score = dx * dx + (y - item.y) ** 2;
					if (score < distance) { distance = score; best = { x, y, w: item.w, h: item.h }; }
				}
			}
			return best;
		};
		// Do not pull offscreen networks back into view during pan. If the visible
		// board is genuinely full, retain the nearest collision-free position;
		// panning can reach it rather than silently dropping or overlapping text.
		const bounds = viewport && item.x < viewport.x + viewport.w && viewport.x < item.x + item.w
			&& item.y < viewport.y + viewport.h && viewport.y < item.y + item.h ? viewport : undefined;
		const rect = nearest(bounds) ?? nearest()!;
		placed.set(item.key, rect);
		occupied.push(rect);
	}
	return placed;
}

/** End at the chip boundary so its leader never paints over its own text. */
export function hudLeader(anchor: Pt, rect: Rect): string | null {
	const x = Math.max(rect.x, Math.min(rect.x + rect.w, anchor.x));
	const y = Math.max(rect.y, Math.min(rect.y + rect.h, anchor.y));
	if (Math.hypot(x - anchor.x, y - anchor.y) < 3) return null;
	return `M ${anchor.x} ${anchor.y} L ${x} ${y}`;
}
