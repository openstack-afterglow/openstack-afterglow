import type { IsoEdge, IsoNode, IsoPlatform, IsoScene } from './types';

export interface Point { x: number; y: number }
export interface GridRect extends Point { w: number; h: number }

export const CELL_X = 96;
export const CELL_Y = CELL_X / Math.sqrt(3);
const LEVEL = 28;
const PACK_STEP = 1.2;

/** +x is down-right; +y is down-left. Both axes meet the horizon at 30°. */
export function project({ x, y }: Point, z = 0): Point {
	return { x: (x - y) * CELL_X, y: (x + y) * CELL_Y - z * LEVEL };
}

export function packNodes(count: number) {
	const columns = Math.max(1, Math.ceil(Math.sqrt(count)));
	const rows = Math.max(1, Math.ceil(count / columns));
	return {
		w: 0.7 + PACK_STEP * columns,
		h: 0.7 + PACK_STEP * rows,
		positions: Array.from({ length: count }, (_, i) => ({
			x: 0.85 + (i % columns) * PACK_STEP,
			y: 0.85 + Math.floor(i / columns) * PACK_STEP,
		})),
	};
}

/** Stack ordered tiers in iso space. Inside a tier wrap wide rows in stable order. */
export function stackPlatforms(tiers: readonly (readonly Pick<GridRect, 'w' | 'h'>[])[]): Point[][] {
	let depth = 0;
	return tiers.map((tier) => {
		let x = 0;
		let rowHeight = 0;
		const origins: Point[] = [];
		const rowWidth = Math.max(10, Math.sqrt(tier.reduce((area, { w, h }) => area + (w + 1) * (h + 1), 0)));
		for (const { w, h } of tier) {
			if (x && x + w > rowWidth) {
				depth += rowHeight + 1;
				x = rowHeight = 0;
			}
			origins.push({ x, y: depth });
			x += w + 1;
			rowHeight = Math.max(rowHeight, h);
		}
		if (tier.length) depth += rowHeight + 1;
		return origins;
	});
}

export function slabCorners({ x, y, w, h }: GridRect, z = 0) {
	return [project({ x, y }, z), project({ x: x + w, y }, z), project({ x: x + w, y: y + h }, z), project({ x, y: y + h }, z)] as const;
}

export function pointString(points: readonly Point[]) {
	return points.map(({ x, y }) => `${x},${y}`).join(' ');
}

export function nodeScale(node: IsoNode) {
	return node.size === 'lg' ? 1.15 : node.size === 'sm' ? 0.82 : 1;
}

const same = (a: Point, b: Point) => a.x === b.x && a.y === b.y;
const length = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
function toward(a: Point, b: Point, distance: number): Point {
	const ratio = Math.min(0.5, distance / (length(a, b) || 1));
	return { x: a.x + (b.x - a.x) * ratio, y: a.y + (b.y - a.y) * ratio };
}

function crosses(a: Point, b: Point, p: Point) {
	const radius = 0.31;
	return a.x === b.x
		? Math.abs(a.x - p.x) < radius && p.y >= Math.min(a.y, b.y) - radius && p.y <= Math.max(a.y, b.y) + radius
		: Math.abs(a.y - p.y) < radius && p.x >= Math.min(a.x, b.x) - radius && p.x <= Math.max(a.x, b.x) + radius;
}

/** Score a constant number of Manhattan paths in logical grid space. */
export function routeEdge(from: Point, to: Point, obstacles: readonly Point[] = []): Point[] {
	const midX = (from.x + to.x) / 2;
	const midY = (from.y + to.y) / 2;
	const candidates = [
		[{ x: to.x, y: from.y }], [{ x: from.x, y: to.y }],
		...[midX, Math.min(from.x, to.x) - 0.54, Math.max(from.x, to.x) + 0.54].map((x) => [{ x, y: from.y }, { x, y: to.y }]),
		...[midY, Math.min(from.y, to.y) - 0.54, Math.max(from.y, to.y) + 0.54].map((y) => [{ x: from.x, y }, { x: to.x, y }]),
	];
	let best: Point[] = [];
	let bestScore = Infinity;
	for (const bends of candidates) {
		const points = [from, ...bends, to].filter((point, i, all) => !i || !same(point, all[i - 1]));
		let score = (points.length - 2) * 0.25;
		for (let i = 1; i < points.length; i++) {
			const a = points[i - 1];
			const b = points[i];
			score += Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
			for (const obstacle of obstacles) {
				if (!same(obstacle, from) && !same(obstacle, to) && crosses(a, b, obstacle)) score += 5;
			}
			if (score >= bestScore) break;
		}
		if (score < bestScore) {
			best = points;
			bestScore = score;
		}
	}
	return best;
}

function roundedPath(points: Point[]): string {
	const start = points[0];
	let path = `M${start.x},${start.y}`;
	for (let i = 1; i < points.length - 1; i++) {
		const corner = points[i];
		const a = toward(corner, points[i - 1], 10);
		const b = toward(corner, points[i + 1], 10);
		path += ` L${a.x},${a.y} Q${corner.x},${corner.y} ${b.x},${b.y}`;
	}
	const end = points.at(-1)!;
	return `${path} L${end.x},${end.y}`;
}

function rectCenter(rect: GridRect): Point {
	return { x: rect.x + rect.w / 2, y: rect.y + rect.h / 2 };
}

function platformAnchor(rect: GridRect, other: Point): Point {
	const center = rectCenter(rect);
	const dx = other.x - center.x;
	const dy = other.y - center.y;
	const ratio = Math.max(Math.abs(dx) / (rect.w / 2), Math.abs(dy) / (rect.h / 2));
	return ratio ? { x: center.x + dx / ratio, y: center.y + dy / ratio } : { x: center.x, y: rect.y };
}

export function isoLabel(value: string, limit = 20): string {
	const chars = Array.from(value);
	return chars.length > limit ? `${chars.slice(0, limit - 1).join('')}…` : value;
}

/** Reserve more space for wide scripts; never measure DOM to lay out the graph. */
export function pillWidth(value: string, padding = 16): number {
	let width = padding;
	for (const char of value) width += (char.codePointAt(0) ?? 0) >= 0x2e80 ? 12 : 7;
	return width;
}

export type PlacedEdge = { edge: IsoEdge; path: string; label: Point; length: number };
export type PlacedNode = { node: IsoNode; point: Point };
export type PlacedPlatform = { platform: IsoPlatform; corners: readonly [Point, Point, Point, Point]; label: Point };

export function layoutScene(scene: IsoScene) {
	const nodesById = new Map(scene.nodes.map((node) => [node.id, node]));
	const platformsById = new Map(scene.platforms.map((platform) => [platform.id, platform]));
	let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
	function include({ x, y }: Point, horizontal = 0, above = 0, below = above) {
		minX = Math.min(minX, x - horizontal); maxX = Math.max(maxX, x + horizontal);
		minY = Math.min(minY, y - above); maxY = Math.max(maxY, y + below);
	}
	const nodes = scene.nodes.map((node) => {
		const ground = project(node);
		const point = project(node, node.z);
		const half = Math.max(pillWidth(isoLabel(node.label), 22), pillWidth(isoLabel(node.sublabel ?? ''))) / 2;
		include(point, Math.max(half, 58), 65, 37 + 19 * Math.min(node.badges?.length ?? 0, 2));
		include(ground);
		return { node, point };
	}).sort((a, b) => a.node.x + a.node.y - b.node.x - b.node.y || a.point.x - b.point.x);
	const platforms = scene.platforms.map((platform) => {
		const corners = slabCorners(platform);
		const label = platform.style === 'zone' ? corners[0] : corners[2];
		for (const corner of corners) include(corner, 0, 0, 8);
		include(label, Math.max(pillWidth(isoLabel(platform.label, 26)), pillWidth(isoLabel(platform.sublabel ?? '', 30))) / 2, 23, 42);
		return { platform, corners, label };
	}).sort((a, b) => Number(a.platform.style !== 'zone') - Number(b.platform.style !== 'zone') || a.corners[0].y - b.corners[0].y);

	const items = [
		...nodes.map(({ node, point }) => ({ id: node.id, label: node.label, point })),
		...platforms.map(({ platform, label }) => ({ id: platform.id, label: platform.label, point: label })),
	].sort((a, b) => a.point.y - b.point.y || a.point.x - b.point.x);
	const edges: PlacedEdge[] = [];
	for (const edge of scene.edges) {
		const aNode = nodesById.get(edge.from), bNode = nodesById.get(edge.to);
		const aSlab = platformsById.get(edge.from), bSlab = platformsById.get(edge.to);
		const a = aNode ?? (aSlab && rectCenter(aSlab));
		const b = bNode ?? (bSlab && rectCenter(bSlab));
		if (!a || !b || edge.from === edge.to) continue;
		const points = routeEdge(aSlab ? platformAnchor(aSlab, b) : a, bSlab ? platformAnchor(bSlab, a) : b, scene.nodes).map((p) => project(p));
		if (points.length < 2) continue;
		const last = points.length - 1;
		const endpoint = (node: IsoNode | undefined, point: Point, next: Point) => {
			if (!node) return point;
			const clipped = toward(point, next, 37 * nodeScale(node));
			return { x: clipped.x, y: clipped.y - (node.z ?? 0) * LEVEL };
		};
		const start = endpoint(aNode, points[0], points[1]);
		points[last] = endpoint(bNode, points[last], points[last - 1]);
		points[0] = start;
		let longest = 0, total = 0;
		let label = start;
		for (let i = 1; i <= last; i++) {
			const segment = length(points[i - 1], points[i]);
			total += segment;
			if (segment > longest) {
				longest = segment;
				label = { x: (points[i - 1].x + points[i].x) / 2, y: (points[i - 1].y + points[i].y) / 2 };
			}
		}
		for (const point of points) include(point);
		if (edge.label) include(label, pillWidth(isoLabel(edge.label, 25)) / 2, 14);
		edges.push({ edge, path: roundedPath(points), label, length: total });
	}
	const bounds = Number.isFinite(minX)
		? { x: minX - 30, y: minY - 30, w: maxX - minX + 60, h: maxY - minY + 60 }
		: { x: -160, y: -100, w: 320, h: 200 };
	return { bounds, nodes, platforms, edges, items, nodesById, platformsById };
}
