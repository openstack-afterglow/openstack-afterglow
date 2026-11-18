import type { GridRect, PlacedEdge, Point } from './layout';

export const PACKET_LIMIT = 96;
export const PACKET_COHORT_MS = 3600;

function segmentIntersects(a: Point, b: Point, view: GridRect) {
	const right = view.x + view.w, bottom = view.y + view.h;
	if (Math.min(a.x, b.x) > right || Math.max(a.x, b.x) < view.x
		|| Math.min(a.y, b.y) > bottom || Math.max(a.y, b.y) < view.y) return false;
	const dx = b.x - a.x, dy = b.y - a.y;
	if (!dx || !dy) return true;
	const enterX = ((dx > 0 ? view.x : right) - a.x) / dx;
	const exitX = ((dx > 0 ? right : view.x) - a.x) / dx;
	const enterY = ((dy > 0 ? view.y : bottom) - a.y) / dy;
	const exitY = ((dy > 0 ? bottom : view.y) - a.y) / dy;
	return Math.max(enterX, enterY, 0) <= Math.min(exitX, exitY, 1);
}

/** Select by routed geometry, so an edge crossing the view counts even when both ends are outside. */
export function visiblePacketEdges(edges: readonly PlacedEdge[], view: GridRect): string[] {
	const ids: string[] = [];
	for (const { edge, points } of edges) {
		if (edge.flow === false) continue;
		for (let i = 1; i < points.length; i++) {
			if (!segmentIntersects(points[i - 1], points[i], view)) continue;
			ids.push(edge.id);
			break;
		}
	}
	return ids;
}

/** An ordered round robin; every visible edge appears within ceil(count / budget) cohorts. */
export function packetCohort(visibleIds: readonly string[], turn: number): Set<string> {
	const count = visibleIds.length;
	if (count <= PACKET_LIMIT) return new Set(visibleIds);
	const start = (turn * PACKET_LIMIT) % count;
	const ids = new Set<string>();
	for (let i = 0; i < PACKET_LIMIT; i++) ids.add(visibleIds[(start + i) % count]);
	return ids;
}
