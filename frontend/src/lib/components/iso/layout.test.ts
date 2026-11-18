import { describe, expect, it } from 'vitest';
import { layoutScene, packNodes, project, routeEdge, stackPlatforms } from './layout';
import type { IsoScene } from './types';

const scene: IsoScene = {
	platforms: [{ id: 'lan', label: 'LAN', tone: 'internal', style: 'slab', x: 0, y: 1, w: 2, h: 2 }],
	nodes: [
		{ id: 'a', label: 'A', x: 1, y: 0, kind: 'router', tone: 'router' },
		{ id: 'b', label: 'B', x: 1, y: 2, kind: 'instance', tone: 'internal', platformId: 'lan' },
	],
	edges: [{ id: 'route', from: 'a', to: 'lan', kind: 'link', tone: 'router', directed: true }],
};

describe('isometric geometry', () => {
	it('projects both axes at 30 degrees and lifts without changing X', () => {
		const a = project({ x: 1, y: 0 });
		const b = project({ x: 0, y: 1 });
		expect(a.x).toBe(-b.x);
		expect(a.y).toBe(b.y);
		expect(Math.atan2(a.y, a.x)).toBeCloseTo(Math.PI / 6);
		expect(project({ x: 1, y: 0 }, 1)).toEqual({ x: a.x, y: a.y - 28 });
	});

	it('packs nonoverlapping cells and wraps ordered platforms within their tiers', () => {
		const { w, h, positions } = packNodes(15);
		expect(new Set(positions.map(({ x, y }) => `${x}:${y}`)).size).toBe(15);
		for (const { x, y } of positions) {
			expect(x).toBeGreaterThan(0);
			expect(x).toBeLessThan(w);
			expect(y).toBeGreaterThan(0);
			expect(y).toBeLessThan(h);
		}
		const [external, tenant] = stackPlatforms([[{ w: 4, h: 3 }], [{ w: 6, h: 2 }, { w: 6, h: 2 }]]);
		expect(external).toEqual([{ x: 0, y: 0 }]);
		expect(tenant).toEqual([{ x: 0, y: 4 }, { x: 0, y: 7 }]);
	});

	it('chooses a clear orthogonal detour and never mutates the endpoints', () => {
		const a = Object.freeze({ x: 0, y: 0 });
		const b = Object.freeze({ x: 3, y: 0 });
		const obstacle = { x: 1.5, y: 0 };
		const path = routeEdge(a, b, [obstacle]);
		expect(path.length).toBeGreaterThan(2);
		expect(path[0]).toEqual(a);
		expect(path.at(-1)).toEqual(b);
		for (const [index, point] of path.slice(1).entries()) {
			const last = path[index];
			expect(point.x === last.x || point.y === last.y).toBe(true);
			if (point.y === 0 && last.y === 0) expect((point.x - obstacle.x) * (last.x - obstacle.x)).toBeGreaterThan(0);
		}
	});

	it('routes platform endpoints, drops dangling records and returns finite bounds', () => {
		const placed = layoutScene({ ...scene, edges: [...scene.edges,
			{ id: 'missing', from: 'b', to: 'unknown', kind: 'link', tone: 'neutral' },
		] });
		expect(placed.edges.map(({ edge }) => edge.id)).toEqual(['route']);
		expect(placed.edges[0].path).toMatch(/^M.* L/);
		expect(placed.items.map(({ id }) => id)).toEqual(['a', 'b', 'lan']);
		expect(Object.values(placed.bounds).every(Number.isFinite)).toBe(true);
	});

	it('slides edge labels past a zone caption without moving either endpoint', () => {
		const nodes: IsoScene['nodes'] = [
			{ id: 'a', label: 'A', x: 0, y: 0, kind: 'port', tone: 'neutral' },
			{ id: 'b', label: 'B', x: 3, y: 0, kind: 'port', tone: 'neutral' },
		];
		const edges: IsoScene['edges'] = [{ id: 'rule', from: 'a', to: 'b', kind: 'ingress', tone: 'success', label: 'TCP 8443' }];
		const baseline = layoutScene({ nodes, edges, platforms: [] }).edges[0];
		const platform: IsoScene['platforms'][number] = { id: 'zone', label: 'Security group', x: 1.5, y: 0, w: 2, h: 1, tone: 'neutral', style: 'zone' };
		const placed = layoutScene({ nodes, edges, platforms: [platform] }).edges[0];
		expect(placed.path).toBe(baseline.path);
		expect(placed.label).not.toEqual(baseline.label);
	});

	it('lays out 300 nodes and 600 edges without dropping connections', () => {
		const nodes = Array.from({ length: 300 }, (_, i) => ({ id: `${i}`, label: `node-${i}`, x: i % 20, y: Math.floor(i / 20), kind: 'instance', tone: 'internal' } as const));
		const edges = Array.from({ length: 600 }, (_, i) => ({ id: `${i}`, from: `${i % 300}`, to: `${(i + (i < 300 ? 21 : 23)) % 300}`, kind: 'link', tone: 'internal' } as const));
		const layout = layoutScene({ nodes, edges, platforms: [] });
		expect(layout.items).toHaveLength(300);
		expect(layout.edges).toHaveLength(600);
	});
});
