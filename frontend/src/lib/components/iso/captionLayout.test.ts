import { describe, expect, it } from 'vitest';
import { placeCaptions } from './captionLayout';
import { layoutScene } from './layout';
import type { IsoScene } from './types';

const scene: IsoScene = {
	nodes: [{ id: 'server', kind: 'vpn-server', tone: 'gateway', label: 'VPN server', status: 'ok', x: 0, y: 0 }],
	platforms: [{ id: 'clients', label: 'Clients', sublabel: '198.51.100.0/24', tone: 'shared', style: 'zone', x: 0, y: 0, w: 2, h: 2 }],
	edges: [],
};

describe('caption placement', () => {
	it('counter-scales resource captions and merges reported status into the name row', () => {
		const { nodes, platforms, edges } = layoutScene(scene);
		const { items } = placeCaptions(nodes, platforms, edges, 0.5, () => 'Online');
		expect(items.get('server')).toMatchObject({ name: 'VPN server', status: 'Online', height: 24, scale: 1.6 });
	});

	it('moves a zone label away from the block footprint without changing either resource', () => {
		const { nodes, platforms, edges } = layoutScene(scene);
		const { items } = placeCaptions(nodes, platforms, edges, 0.62, () => 'Online');
		const { position, width, height, scale } = items.get('clients')!;
		const avoidsBlock = Math.abs(position.x) > 42 + width * scale / 2 || position.y + height * scale <= -45 || position.y >= 24;
		expect(avoidsBlock).toBe(true);
	});
});
