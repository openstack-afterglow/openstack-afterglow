import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import TopologyCanvas from '../TopologyCanvas.svelte';
import GlobalTopology from '$lib/components/GlobalTopology.svelte';
import { groupNetworksByDomain } from '../../domainGroups';
import { createTopologyDerivedController } from '../../topologyDerivedController.svelte';
import { buildGraph, matchesQuery } from '../topologyGraph';
import { applyManualPositions, autoLayout, computeGeometry, contentBounds, packDomainGroups } from '../topologyLayout';
import { makeDomainFixture, makeFixture } from './fixtures';
import type { Rect } from '../types';

import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';
const intersects = (a: Rect, b: Rect) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const contains = (outer: Rect, inner: Rect) => inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h;
const adminGraph = () => buildGraph(makeDomainFixture(), { projectId: null, showAll: true, adminView: true });

afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });

describe('native administrator domain ownership', () => {
	it('groups duplicate domain names by UUID, with multiple networks and explicit unavailable owners', () => {
		const data = makeDomainFixture();
		const groups = groupNetworksByDomain(data.networks);
		expect(groups.filter((group) => group.name === 'Research').map((group) => group.domainId)).toEqual(['domain-a', 'domain-b']);
		expect(groups.find((group) => group.id === 'domain:domain-a')?.netIds).toContain('net-pub');
		expect(groups.find((group) => group.id === 'domain:domain-a')?.netIds).toContain('net-transit');
		expect(groups.find((group) => group.id === 'domain:deleted-domain')?.status).toBe('deleted_domain');
		expect(groups.find((group) => group.id === 'project:deleted-project')?.status).toBe('deleted_project');
		expect(groups.find((group) => group.id === 'owner:unknown')?.netIds).toEqual(['net-unknown']);
		expect(groups.flatMap((group) => group.netIds).sort()).toEqual(data.networks.map((network) => network.id).sort());
		const legacy = makeFixture().networks.filter((network) => network.project_id);
		expect(groupNetworksByDomain(legacy).every((group) => group.status === 'unknown_owner')).toBe(true);
	});

	it('contains child network zones, separates adjacent groups and includes domain padding in fit bounds', () => {
		const graph = adminGraph();
		const layout = autoLayout(graph);
		const geometry = computeGeometry(graph, layout);
		const boxes = [...geometry.domains.values()];
		for (const group of graph.domainGroups!) {
			const box = geometry.domains.get(group.id)!;
			for (const id of group.netIds) expect(contains(box, geometry.zones.get(id)!)).toBe(true);
			for (const netId of group.netIds) {
				expect(contains(box, layout.pos.get('sw:' + netId)!)).toBe(true);
				const internet = layout.pos.get('internet:' + netId);
				if (internet) expect(contains(box, internet)).toBe(true);
			}
		}
		for (let i = 0; i < boxes.length; i++) for (const box of boxes.slice(i + 1)) expect(intersects(boxes[i], box)).toBe(false);
		const bounds = contentBounds(geometry.zones, layout.pos, geometry.domains);
		for (const box of boxes) expect(contains(bounds, box)).toBe(true);
		expect(layout.bands.RIGHT_X).toBeGreaterThanOrEqual(bounds.x + bounds.w);
		expect(layout.bands.BOTTOM_Y).toBeGreaterThanOrEqual(bounds.y + bounds.h);
	});

	it('does not create domain links or remove native cross-domain NIC/router edges', () => {
		const data = makeDomainFixture();
		const grouped = buildGraph(data, { projectId: null, showAll: true, adminView: true });
		const original = buildGraph(data, { projectId: null, showAll: true });
		expect(grouped.edges).toEqual(original.edges);
		const layout = autoLayout(grouped);
		const domainByNet = new Map(grouped.domainGroups!.flatMap((group) => group.netIds.map((id) => [id, group.id] as const)));
		for (const homes of layout.home.values()) expect(new Set(homes.map((id) => domainByNet.get(id))).size).toBeLessThanOrEqual(1);
	});

	it('retains persisted node intentions and resolves expanded domain groups after manual placement', () => {
		const graph = adminGraph();
		const layout = autoLayout(graph);
		const target = layout.pos.get('sw:net-other')!;
		const manual = { 'sw:net-web': { x: target.x + 20, y: target.y + 150 } };
		expect(applyManualPositions(layout, manual)).toEqual(manual);
		packDomainGroups(graph, layout, false);
		const boxes = [...computeGeometry(graph, layout).domains.values()];
		for (let i = 0; i < boxes.length; i++) for (const box of boxes.slice(i + 1)) expect(intersects(boxes[i], box)).toBe(false);
		const fresh = autoLayout(graph);
		expect(applyManualPositions(fresh, manual)).toEqual(manual);
		packDomainGroups(graph, fresh, false);
		expect([...fresh.pos]).toEqual([...layout.pos]);
	});

	it('finds exact domain IDs without merging equal display labels and keeps consumer graph/layout unchanged', () => {
		const graph = adminGraph();
		expect(matchesQuery(graph, 'domain-b')?.nets).toEqual(new Set(['net-other']));
		const consumer = buildGraph(makeDomainFixture(), { projectId: null, showAll: true });
		expect(consumer.domainGroups).toBeUndefined();
		expect(computeGeometry(consumer, autoLayout(consumer)).domains.size).toBe(0);
		// Ownership metadata has no influence at all outside the administrator view.
		const before = makeDomainFixture();
		for (const network of before.networks) {
			delete network.domain_id; delete network.domain_name; delete network.owner_status; delete network.project_name;
		}
		expect([...autoLayout(consumer).pos]).toEqual([...autoLayout(buildGraph(before, { projectId: null, showAll: true })).pos]);
	});

	it('keeps IP and MAC search from matching owner UUID fragments', () => {
		const data = makeDomainFixture();
		for (const network of data.networks) Object.assign(network, { domain_id: 'domain-192-fa16', domain_name: 'Research', project_id: 'project-192-fa16', owner_status: 'known' });
		const graph = buildGraph(data, { projectId: null, showAll: true, adminView: true });
		expect(matchesQuery(graph, '192')?.nets).toEqual(new Set(['net-mgmt']));
		expect(matchesQuery(graph, 'fa16')?.nets.has('net-unknown')).toBe(false);
	});

	it('assigns a real cross-domain router to one network home and keeps domain boxes separate', () => {
		const data = makeDomainFixture();
		const router = data.routers.find((row) => row.id === 'rtr-edge')!;
		router.connected_subnet_ids.push('sn-other');
		router.interface_ips.push({ ip_address: '10.20.1.1', subnet_id: 'sn-other' });
		const graph = buildGraph(data, { projectId: null, showAll: true, adminView: true });
		const layout = autoLayout(graph);
		const geometry = computeGeometry(graph, layout);
		const groups = graph.domainGroups!.filter((group) => {
			const box = geometry.domains.get(group.id)!;
			return contains(box, layout.pos.get(router.id)!);
		});
		expect(groups.map((group) => group.id)).toEqual(['domain:domain-a']);
		expect(graph.edges.some((edge) => edge.from === router.id && edge.to === 'sw:net-other')).toBe(true);
		const boxes = [...geometry.domains.values()];
		for (let i = 0; i < boxes.length; i++) for (const box of boxes.slice(i + 1)) expect(intersects(boxes[i], box)).toBe(false);
	});

	it('renders labeled admin parents once, preserves child selection/search, and hides parents from consumers', async () => {
		vi.stubGlobal('matchMedia', (query: string) => ({ matches: query === REDUCED_MOTION_QUERY, media: query, addEventListener() {}, removeEventListener() {} }));
		const onSelectNetwork = vi.fn();
		const utils = render(TopologyCanvas, { data: makeDomainFixture(), showAll: true, adminView: true, onSelectNetwork });
		expect(utils.container.querySelectorAll('[data-domain-box]')).toHaveLength(5);
		expect(utils.container.querySelector('[data-domain-label="domain:domain-a"]')?.textContent).toContain('domain-a');
		expect(utils.container.querySelector('[data-domain-label="domain:domain-b"]')?.textContent).toContain('domain-b');
		expect(utils.container.querySelectorAll('[data-zone-net="net-pub"]')).toHaveLength(1);
		await fireEvent.click(utils.container.querySelector('[data-zone-label="net-web"]')!);
		expect(onSelectNetwork).toHaveBeenCalledWith('net-web');
		await fireEvent.input(screen.getByRole('searchbox', { name: '토폴로지 검색' }), { target: { value: 'domain-b' } });
		expect(utils.container.querySelector('[data-zone-net="net-other"]')?.classList.contains('is-match')).toBe(true);
		expect(utils.container.querySelector('[data-zone-net="net-web"]')?.classList.contains('is-dim')).toBe(true);
		const viewport = screen.getByRole('application', { name: '네트워크 토폴로지 캔버스' });
		const world = utils.container.querySelector<HTMLElement>('.topology-world')!;
		const before = world.style.transform;
		await fireEvent.keyDown(viewport, { key: 'ArrowRight' });
		const frame = Promise.withResolvers<void>();
		requestAnimationFrame(() => requestAnimationFrame(() => frame.resolve()));
		await frame.promise;
		expect(world.style.transform).not.toBe(before);
		const panned = world.style.transform;
		await fireEvent.keyDown(viewport, { key: '+' });
		expect(world.style.transform).not.toBe(panned);
		const moved = world.style.transform;
		await utils.rerender({ data: makeDomainFixture(), showAll: true, adminView: true, onSelectNetwork });
		expect(world.style.transform).toBe(moved);
		expect(utils.container.querySelectorAll('[data-domain-box]')).toHaveLength(5);
		expect((screen.getByRole('searchbox', { name: '토폴로지 검색' }) as HTMLInputElement).value).toBe('domain-b');
		await utils.rerender({ data: makeDomainFixture(), showAll: true, adminView: false, onSelectNetwork });
		expect(utils.container.querySelector('[data-domain-box]')).toBeNull();
	});

	it('keeps admin lanes contiguous by stable domain, without changing consumer order or adding links', () => {
		const data = makeDomainFixture();
		const controller = (adminView: boolean) => createTopologyDerivedController({ data: () => data, projectId: () => null, showAll: () => true, adminView: () => adminView, traffic: () => null, selectedId: () => null, hoveredId: () => null, anchors: () => new Map(), sidebarHeight: () => 600, searchTerm: () => '' });
		const admin = controller(true), consumer = controller(false);
		const groups = groupNetworksByDomain(admin.orderedNetworks);
		expect(admin.orderedNetworks.map((network) => network.id)).toEqual(groups.flatMap((group) => group.netIds));
		expect(admin.connections.map((connection) => connection.key).sort()).toEqual(consumer.connections.map((connection) => connection.key).sort());
		expect(consumer.orderedNetworks[0].id).toBe(makeFixture().networks[0].id);
		vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
		const utils = render(GlobalTopology, { data, showAll: true, adminView: true });
		expect(utils.container.querySelectorAll('[data-lane-domain]')).toHaveLength(5);
	});
});
