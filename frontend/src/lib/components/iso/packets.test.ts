import { describe, expect, it } from 'vitest';
import type { PlacedEdge, Point } from './layout';
import { packetCohort, PACKET_LIMIT, visiblePacketEdges } from './packets';

function route(id: string, points: Point[], flow?: boolean): PlacedEdge {
	return { edge: { id, from: 'a', to: 'b', kind: 'link', tone: 'neutral', flow }, points, path: '', length: 0, label: points[0] };
}

const rect = { x: 0, y: 0, w: 20, h: 20 };

describe('packet cohorts', () => {
	it('animates every one of 600 visible routes in at most seven cohorts with no overshoot', () => {
		const ids = Array.from({ length: 600 }, (_, i) => `route-${i}`);
		const visited = new Set<string>();
		for (let turn = 0; turn < 7; turn++) {
			const cohort = packetCohort(ids, turn);
			expect(cohort.size).toBe(PACKET_LIMIT);
			for (const id of cohort) visited.add(id);
		}
		expect(visited.size).toBe(600);
		expect(packetCohort(ids, 0).has('route-96')).toBe(false);
		expect(packetCohort(ids, 1).has('route-96')).toBe(true);
	});

	it('prioritizes a late route that actually crosses the viewport', () => {
		const offscreen = Array.from({ length: 100 }, (_, i) => route(`off-${i}`, [{ x: -30, y: 0 }, { x: -1, y: 0 }]));
		const routes = [
			...offscreen,
			route('crossing', [{ x: 30, y: 10 }, { x: -30, y: 10 }]),
			route('bbox-only', [{ x: -10, y: 1 }, { x: 1, y: -10 }]),
			route('flow-disabled', [{ x: 30, y: 10 }, { x: 0, y: 10 }], false),
		];
		expect([...packetCohort(visiblePacketEdges(routes, rect), 0)]).toEqual(['crossing']);
	});
});
