import { describe, expect, it } from 'vitest';
import { hudLeader, placeHudItems, type HudPlacementInput } from '../hudLayout';
import type { Rect } from '../types';

function expectSeparated(rects: readonly Rect[], obstacles: readonly Rect[] = []) {
	for (let i = 0; i < rects.length; i++) for (const b of [...rects.slice(i + 1), ...obstacles]) {
		const a = rects[i];
		expect(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h, JSON.stringify({ a, b })).toBe(false);
	}
}

describe('screen-space HUD placement', () => {
	it('keeps clear anchors unchanged instead of pushing labels by the preceding zone width', () => {
		const items = [{ key: 'public', x: 30, y: 60, w: 310, h: 24 }, { key: 'shared', x: 60, y: 120, w: 240, h: 24 }];
		const result = placeHudItems(items, []);
		for (const { key, ...rect } of items) expect(result.get(key)).toEqual(rect);
	});

	it.each([0.35, 0.5, 0.65, 1, 1.25, 2.2])('separates overlapping network labels, card names/IP rows and badges at zoom %s', (k) => {
		const project = (r: Rect) => ({ x: r.x * k + 40, y: r.y * k + 20, w: r.w * k, h: r.h * k });
		const obstacles = [project({ x: 20, y: 120, w: 232, h: 106 }), project({ x: 260, y: 60, w: 232, h: 68 })];
		const items: HudPlacementInput[] = [
			{ key: 'public', x: 40 * k + 40, y: 100 * k + 20, w: 310, h: 44 },
			{ key: 'shared', x: 60 * k + 40, y: 100 * k + 20, w: 290, h: 44 },
			{ key: 'other-band', x: 50 * k + 40, y: 115 * k + 20, w: 280, h: 24 },
			{ key: 'uplink', x: 80 * k + 40, y: 130 * k + 20, w: 130, h: 40 },
		];
		const result = placeHudItems(items, obstacles, { x: 6, y: 6, w: 1000, h: 700 });
		expect(result.size).toBe(items.length);
		expectSeparated([...result.values()], obstacles);
		expect(placeHudItems(items, obstacles, { x: 6, y: 6, w: 1000, h: 700 })).toEqual(result);
	});

	it.each([320, 390, 768, 1024, 1440])('uses measured wrapped dimensions at %spx without discarding names or addresses', (width) => {
		const viewport = { x: 6, y: 6, w: width - 12, h: 700 };
		const items = Array.from({ length: 4 }, (_, i) => ({ key: String(i), x: width - 50, y: 70, w: Math.min(400, width - 12), h: width < 400 ? 64 : 44 }));
		const obstacles = [{ x: 0, y: 140, w: width, h: 100 }];
		const result = [...placeHudItems(items, obstacles, viewport).values()];
		expect(result).toHaveLength(items.length);
		expectSeparated(result, obstacles);
		for (const r of result) {
			expect(r.x).toBeGreaterThanOrEqual(viewport.x);
			expect(r.x + r.w).toBeLessThanOrEqual(viewport.x + viewport.w);
			expect(r.y).toBeGreaterThanOrEqual(viewport.y);
			expect(r.y + r.h).toBeLessThanOrEqual(viewport.y + viewport.h);
		}
	});

	it('reflows after a drag, a font/content size change and domain-header collision', () => {
		const label = { key: 'network', x: 20, y: 40, w: 200, h: 24 };
		const first = placeHudItems([label], []);
		const obstacles = [{ x: 10, y: 30, w: 250, h: 90 }, { x: 0, y: 0, w: 500, h: 24 }];
		const next = placeHudItems([{ ...label, w: 350, h: 64 }], obstacles);
		expect(next.get(label.key)).not.toEqual(first.get(label.key));
		expectSeparated([...next.values()], obstacles);
	});

	it('does not pin offscreen networks into the viewport or drop labels when the board is full', () => {
		const offscreen = { key: 'offscreen', x: -500, y: -400, w: 200, h: 24 };
		expect(placeHudItems([offscreen], [], { x: 0, y: 0, w: 320, h: 200 }).get(offscreen.key)).toMatchObject({ x: -500, y: -400 });
		const card = { x: 0, y: 0, w: 320, h: 200 };
		const result = placeHudItems([{ key: 'network', x: 20, y: 20, w: 200, h: 44 }], [card], card);
		expect(result.size).toBe(1);
		expectSeparated([...result.values()], [card]);
	});

	it('leaders stop at the chip boundary and are absent at the original anchor', () => {
		expect(hudLeader({ x: 10, y: 20 }, { x: 10, y: 8, w: 200, h: 24 })).toBeNull();
		expect(hudLeader({ x: 10, y: 20 }, { x: 30, y: 50, w: 200, h: 44 })).toBe('M 10 20 L 30 50');
	});
});
