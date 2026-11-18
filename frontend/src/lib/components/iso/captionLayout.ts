import { isoLabel, labelAnchor, nodeScale, pillWidth, type GridRect, type PlacedEdge, type PlacedNode, type PlacedPlatform, type Point } from './layout';
import type { IsoNode, IsoPlatform, IsoStatus } from './types';

export interface Caption {
	position: Point;
	width: number;
	height: number;
	scale: number;
	name: string;
	status: string;
	meta: string;
}

type CaptionSeed = Pick<Caption, 'name' | 'status' | 'meta' | 'scale'>;

function place(seed: CaptionSeed, anchors: Point[], obstacles: GridRect[]): Caption {
	const headerWidth = pillWidth(seed.name, 20) + (seed.status ? pillWidth(seed.status, 21) : 0);
	let best: Caption | undefined;
	let bestArea = Infinity;
	for (const meta of seed.meta ? [seed.meta, ''] : ['']) {
		const width = Math.max(headerWidth, meta ? pillWidth(meta, 20) : 0);
		const height = meta ? 39 : 24;
		const w = width * seed.scale, h = height * seed.scale;
		for (const position of anchors) {
			const left = position.x - w / 2 - 3, right = position.x + w / 2 + 3;
			let overlap = 0;
			for (const box of obstacles) {
				if (left >= box.x + box.w || box.x >= right || position.y >= box.y + box.h || box.y >= position.y + h + 3) continue;
				overlap += (Math.min(right, box.x + box.w) - Math.max(left, box.x)) * (Math.min(position.y + h + 3, box.y + box.h) - Math.max(position.y, box.y));
				if (overlap >= bestArea) break;
			}
			const score = overlap + (meta === seed.meta ? 0 : 4);
			if (score < bestArea) {
				best = { ...seed, position, width, height, meta };
				bestArea = score;
			}
			if (overlap === 0) break;
		}
		if (bestArea <= 0) break;
	}
	const caption = best!;
	obstacles.push({ x: caption.position.x - caption.width * caption.scale / 2, y: caption.position.y,
		w: caption.width * caption.scale, h: caption.height * caption.scale });
	return caption;
}

function nodeSeed(node: IsoNode, scale: number, statusText: (status: IsoStatus) => string): CaptionSeed {
	const badges = (node.badges ?? []).slice(0, 2).map(({ text }) => text);
	return {
		name: isoLabel(node.label, 21),
		status: node.status ? statusText(node.status) : '',
		meta: isoLabel([node.sublabel, ...badges].filter(Boolean).join(' · '), 36),
		scale,
	};
}

function platformSeed(platform: IsoPlatform, scale: number): CaptionSeed {
	return { name: isoLabel(platform.label, 26), status: '', meta: isoLabel(platform.sublabel ?? '', 34), scale };
}

/** Arrange readable captions in world coordinates; viewport pan does not change placement. */
export function placeCaptions(nodes: PlacedNode[], platforms: PlacedPlatform[], routes: PlacedEdge[], k: number, statusText: (status: IsoStatus) => string) {
	const scale = Math.max(1, Math.min(1.85, 0.8 / k));
	const obstacles: GridRect[] = nodes.map(({ node, point }) => {
		const size = nodeScale(node);
		return { x: point.x - 42 * size, y: point.y - 45 * size, w: 84 * size, h: 69 * size };
	});
	const result = new Map<string, Caption>();
	for (const { platform, label: p } of platforms) {
		const seed = platformSeed(platform, scale);
		const zone = platform.style === 'zone';
		const y = p.y + (zone ? -(seed.meta ? 39 : 24) * scale - 5 : 8);
		result.set(platform.id, place(seed, [
			{ x: p.x, y }, { x: p.x + 48 * scale, y }, { x: p.x - 48 * scale, y },
			{ x: p.x + 85 * scale, y: y + (zone ? -48 : 38) * scale }, { x: p.x - 85 * scale, y: y + (zone ? -48 : 38) * scale },
		], obstacles));
	}
	for (const { node, point: p } of nodes) {
		const seed = nodeSeed(node, scale, statusText);
		const y = p.y + 26 * nodeScale(node);
		result.set(node.id, place(seed, [
			{ x: p.x, y }, { x: p.x + 45 * scale, y }, { x: p.x - 45 * scale, y },
			{ x: p.x, y: y + 29 * scale }, { x: p.x, y: p.y - 95 * scale },
			{ x: p.x - 88 * scale, y: y + 36 * scale }, { x: p.x + 88 * scale, y: y + 36 * scale },
		], obstacles));
	}
	const edgeLabels = new Map<string, { point: Point; text: string; width: number; scale: number }>();
	if (k >= 0.45) for (const { edge, points } of routes) {
		if (!edge.label) continue;
		const text = isoLabel(edge.label, 25);
		const width = pillWidth(text, 16);
		const w = width * scale, h = 21 * scale;
		const point = labelAnchor(points, w, obstacles, h);
		const x = point.x - w / 2, y = point.y - h / 2;
		if (obstacles.some((box) => x < box.x + box.w && box.x < x + w && y < box.y + box.h && box.y < y + h)) continue;
		edgeLabels.set(edge.id, { point, text, width, scale });
		obstacles.push({ x, y, w, h });
	}
	return { items: result, edgeLabels };
}
